"""Fase 5.1: server web su Render — /health per il monitor, webhook con segreto,
nessun messaggio scartato al risveglio. Server reale su localhost, bot finto: nessuna rete esterna."""
import asyncio
import json
import re
import socket
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from tornado.httpclient import AsyncHTTPClient, HTTPClientError

import app

TOKEN = '123456:OFFLINE_TEST_TOKEN'


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class FakeApplication:
    """Quanto basta di telegram.ext.Application per serve_webhook."""
    def __init__(self):
        self.update_queue = asyncio.Queue()
        self.bot = SimpleNamespace(set_webhook=AsyncMock(return_value=True))
        self.post_init = AsyncMock()
        self.calls = []

    async def __aenter__(self):
        self.calls.append('initialize')
        return self

    async def __aexit__(self, *exc):
        self.calls.append('shutdown')

    async def start(self):
        self.calls.append('start')

    async def stop(self):
        self.calls.append('stop')


class WebServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.port = free_port()
        self.ptb = FakeApplication()
        self.stop = asyncio.Event()
        self.task = asyncio.create_task(app.serve_webhook(
            TOKEN, 'https://tutor.example.onrender.com/', self.port, self.stop, self.ptb))
        for _ in range(100):
            if 'start' in self.ptb.calls:
                break
            await asyncio.sleep(0.01)
        self.client = AsyncHTTPClient()
        self.base = f'http://127.0.0.1:{self.port}'

    async def asyncTearDown(self):
        self.stop.set()
        await asyncio.wait_for(self.task, 5)

    async def fetch(self, path, method='GET', body=None, headers=None):
        try:
            r = await self.client.fetch(self.base + path, method=method, body=body,
                                        headers=headers or {}, raise_error=False,
                                        allow_nonstandard_methods=True)
        except HTTPClientError as exc:  # pragma: no cover
            r = exc.response
        return r

    async def test_health_endpoints_answer_ok(self):
        for path in ('/', '/health', '/healthz'):
            r = await self.fetch(path)
            self.assertEqual((r.code, r.body), (200, b'ok'), path)
            r = await self.fetch(path, method='HEAD')
            self.assertEqual(r.code, 200, path)

    async def test_webhook_registered_without_dropping_pending_updates(self):
        kw = self.ptb.bot.set_webhook.await_args.kwargs
        self.assertFalse(kw['drop_pending_updates'])
        self.assertEqual(kw['secret_token'], app.webhook_secret(TOKEN))
        self.assertEqual(kw['url'], 'https://tutor.example.onrender.com' + app.webhook_path(TOKEN))
        self.assertNotIn(TOKEN, kw['url'])
        self.assertNotIn(TOKEN.split(':')[1], kw['url'])
        self.assertRegex(kw['secret_token'], r'^[A-Za-z0-9_-]{1,256}$')
        self.assertEqual(self.ptb.calls[:2], ['initialize', 'start'])
        self.ptb.post_init.assert_awaited_once()

    async def test_update_with_secret_is_queued(self):
        body = json.dumps({'update_id': 42, 'message': None})
        r = await self.fetch(app.webhook_path(TOKEN), 'POST', body,
                             {'X-Telegram-Bot-Api-Secret-Token': app.webhook_secret(TOKEN),
                              'Content-Type': 'application/json'})
        self.assertEqual(r.code, 200)
        update = self.ptb.update_queue.get_nowait()
        self.assertEqual(update.update_id, 42)

    async def test_requests_without_valid_secret_are_rejected(self):
        body = json.dumps({'update_id': 1})
        for headers in ({}, {'X-Telegram-Bot-Api-Secret-Token': 'sbagliato'},
                        {'X-Telegram-Bot-Api-Secret-Token': app.webhook_secret('altro:token')}):
            with self.assertLogs('tutor-web', level='WARNING'):
                r = await self.fetch(app.webhook_path(TOKEN), 'POST', body, headers)
            self.assertEqual(r.code, 403)
        self.assertTrue(self.ptb.update_queue.empty())

    async def test_invalid_bodies_and_old_token_path(self):
        secret = {'X-Telegram-Bot-Api-Secret-Token': app.webhook_secret(TOKEN)}
        for body in ('non json', '[]', '{"message": {}}'):
            with self.assertLogs('tutor-web', level='WARNING'):
                r = await self.fetch(app.webhook_path(TOKEN), 'POST', body, secret)
            self.assertEqual(r.code, 400, body)
        r = await self.fetch('/' + TOKEN, 'POST', '{"update_id": 1}', secret)   # vecchio URL col token
        self.assertEqual(r.code, 404)
        r = await self.fetch(app.webhook_path(TOKEN))                             # GET sul webhook
        self.assertEqual(r.code, 405)
        self.assertTrue(self.ptb.update_queue.empty())

    async def test_clean_shutdown(self):
        self.stop.set()
        await asyncio.wait_for(self.task, 5)
        self.assertEqual(self.ptb.calls, ['initialize', 'start', 'stop', 'shutdown'])


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_webhook_retries_network_errors(self):
        from telegram.error import NetworkError
        api = SimpleNamespace(set_webhook=AsyncMock(side_effect=[NetworkError('x'), NetworkError('y'), True]))
        with self.assertLogs('tutor-web', level='WARNING'):
            self.assertTrue(await app.set_webhook_with_retry(api, TOKEN, 'https://x', first_delay=0))
        self.assertEqual(api.set_webhook.await_count, 3)

    async def test_set_webhook_gives_up_after_attempts(self):
        from telegram.error import NetworkError
        api = SimpleNamespace(set_webhook=AsyncMock(side_effect=NetworkError('down')))
        with self.assertLogs('tutor-web', level='WARNING'), self.assertRaises(NetworkError):
            await app.set_webhook_with_retry(api, TOKEN, 'https://x', attempts=2, first_delay=0)

    def test_path_and_secret_are_stable_and_distinct(self):
        self.assertEqual(app.webhook_path(TOKEN), app.webhook_path(TOKEN))
        self.assertNotEqual(app.webhook_path(TOKEN), app.webhook_path('999:OTHER'))
        self.assertTrue(re.fullmatch(r'/tg/[0-9a-f]{32}', app.webhook_path(TOKEN)))
        self.assertNotIn(app.webhook_path(TOKEN)[4:], app.webhook_secret(TOKEN))


if __name__ == '__main__':
    unittest.main()
