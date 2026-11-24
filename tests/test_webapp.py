"""Fase 5.2: mini app — firma initData, API riservate, pagina /app, comando /app.
Server reale su localhost con bot finto: nessuna richiesta a Telegram."""
import asyncio
import hashlib
import hmac
import json
import re
import socket
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import urlencode

from tornado.httpclient import AsyncHTTPClient

import app
import bot
from tutor import webapp
from tutor.texts import T

from tests.test_foundations import FakeChat, inline_rows

TOKEN = '123456:OFFLINE_TEST_TOKEN'


def sign(fields, token=TOKEN):
    """Firma come Telegram: data-check-string ordinata, chiave HMAC("WebAppData", token)."""
    check = '\n'.join(f'{k}={fields[k]}' for k in sorted(fields))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, 'hash': digest})


def user_fields(**extra):
    fields = {'auth_date': str(int(time.time())), 'query_id': 'AAHdF6IQAAAAAN0XohDhrOrc',
              'user': json.dumps({'id': 279058397, 'first_name': 'Società & <Test>', 'language_code': 'it'},
                                 ensure_ascii=False, separators=(',', ':')),
              'signature': 'abc-DEF_123'}
    fields.update(extra)
    return fields


class InitDataTests(unittest.TestCase):
    def test_valid_init_data_accepted_including_signature_field(self):
        data = webapp.validate_init_data(sign(user_fields()), TOKEN)
        self.assertEqual(data['user']['id'], 279058397)
        self.assertEqual(data['user']['first_name'], 'Società & <Test>')

    def test_tampering_and_wrong_token_rejected(self):
        good = sign(user_fields())
        tampered = good.replace('279058397', '279058398')
        for bad, token in [(tampered, TOKEN), (good, '999:OTHER'), (good.replace('hash=', 'hash=0'), TOKEN),
                           (re.sub(r'&hash=[0-9a-f]+', '', good), TOKEN), ('', TOKEN),
                           (good + '&auth_date=1', TOKEN), ('%%%', TOKEN), ('x' * 9000, TOKEN)]:
            with self.assertRaises(webapp.InvalidInitData, msg=bad[:40]):
                webapp.validate_init_data(bad, token)

    def test_expired_or_future_auth_date_rejected(self):
        old = sign(user_fields(auth_date=str(int(time.time()) - webapp.MAX_AGE - 10)))
        future = sign(user_fields(auth_date=str(int(time.time()) + 3600)))
        for bad in (old, future):
            with self.assertRaises(webapp.InvalidInitData):
                webapp.validate_init_data(bad, TOKEN)
        recent = sign(user_fields(auth_date=str(int(time.time()) - 3600)))
        webapp.validate_init_data(recent, TOKEN)

    def test_malformed_user_rejected(self):
        for user in ('not json', '[]', '{"id":"12"}'):
            with self.assertRaises(webapp.InvalidInitData):
                webapp.validate_init_data(sign(user_fields(user=user)), TOKEN)

    def test_reference_payload_is_the_book_data(self):
        p = webapp.reference_payload(bot.KB)
        self.assertEqual(p['counts']['verbs'], len(bot.KB['verbs']))
        self.assertEqual(p['counts']['glossary'], len(bot.KB['glossary']))
        go = next(v for v in p['verbs'] if v['b'] == 'go')
        self.assertEqual((go['p'], go['pp']), tuple(bot.KB['verbs']['go']))
        self.assertTrue(all(g['p'] for g in p['glossary']))
        self.assertEqual(len(p['verb_pages']), 2)
        self.assertTrue(all(isinstance(x, int) for x in p['verb_pages']))
        self.assertLessEqual(p['verb_pages'][0], p['verb_pages'][1])
        self.assertEqual(go['pg'], bot.KB['verb_pages']['go'])


class FakeApplication:
    def __init__(self):
        self.update_queue = asyncio.Queue()
        self.bot = SimpleNamespace(set_webhook=AsyncMock(return_value=True))
        self.post_init = None
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    async def start(self):
        self.calls.append('start')

    async def stop(self):
        pass


class WebAppServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            self.port = s.getsockname()[1]
        self.saved_url = bot.WEBAPP_URL
        self.ptb = FakeApplication()
        self.stop = asyncio.Event()
        self.task = asyncio.create_task(app.serve_webhook(
            TOKEN, 'https://tutor.example.onrender.com', self.port, self.stop, self.ptb))
        for _ in range(100):
            if 'start' in self.ptb.calls:
                break
            await asyncio.sleep(0.01)
        self.client = AsyncHTTPClient()

    async def asyncTearDown(self):
        self.stop.set()
        await asyncio.wait_for(self.task, 5)
        bot.WEBAPP_URL = self.saved_url

    async def fetch(self, path, headers=None, method='GET'):
        return await self.client.fetch(f'http://127.0.0.1:{self.port}{path}', headers=headers or {},
                                       method=method, raise_error=False)

    async def test_page_served_with_security_headers(self):
        r = await self.fetch('/app?lang=it')
        self.assertEqual(r.code, 200)
        self.assertIn('telegram-web-app.js', r.body.decode())
        csp = r.headers['Content-Security-Policy']
        self.assertIn("connect-src 'self'", csp)
        self.assertIn('https://telegram.org', csp)
        self.assertNotIn('X-Frame-Options', r.headers)        # Telegram Web apre le mini app in un iframe
        self.assertEqual((await self.fetch('/app', method='HEAD')).code, 200)

    async def test_public_url_given_to_the_bot(self):
        self.assertEqual(bot.WEBAPP_URL, 'https://tutor.example.onrender.com/app')

    async def test_api_requires_valid_signature(self):
        for headers in ({}, {'Authorization': 'tma '}, {'Authorization': 'Bearer ' + sign(user_fields())},
                        {'Authorization': 'tma ' + sign(user_fields(), '999:OTHER')}):
            with self.assertLogs('tutor-web', level='INFO'):
                r = await self.fetch('/api/reference', headers)
            self.assertEqual(r.code, 401, headers)
            self.assertEqual(json.loads(r.body), {'error': 'unauthorized'})
            self.assertNotIn(b'verbs', r.body)

    async def test_api_returns_book_reference_data(self):
        r = await self.fetch('/api/reference', {'Authorization': 'tma ' + sign(user_fields())})
        self.assertEqual(r.code, 200)
        body = json.loads(r.body)
        self.assertEqual(len(body['verbs']), len(bot.KB['verbs']))
        self.assertEqual(len(body['glossary']), len(bot.KB['glossary']))
        self.assertEqual(body['user'], {'first_name': 'Società & <Test>', 'language_code': 'it'})
        self.assertEqual(r.headers['Cache-Control'], 'no-store')


class BotEntryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bot.STATE.clear()
        self.saved = bot.WEBAPP_URL
        self.chat = FakeChat()
        self.update = SimpleNamespace(effective_chat=self.chat, callback_query=None, message=None)
        self.ctx = SimpleNamespace(args=[])
        bot.st(self.chat.id)['lang'] = 'it'

    async def asyncTearDown(self):
        bot.WEBAPP_URL = self.saved

    def web_buttons(self, message):
        return [b for row in inline_rows(message['keyboard']) for b in row if b.web_app]

    async def test_app_command_and_menu_button(self):
        bot.WEBAPP_URL = 'https://tutor.example.onrender.com/app'
        await bot.cmd_app(self.update, self.ctx)
        [button] = self.web_buttons(self.chat.messages[-1])
        self.assertEqual(button.web_app.url, 'https://tutor.example.onrender.com/app?lang=it')
        await bot.cmd_menu(self.update, self.ctx)
        self.assertEqual(len(self.web_buttons(self.chat.messages[-1])), 1)
        bot.st(self.chat.id)['lang'] = 'en'
        await bot.cmd_help(self.update, self.ctx)
        self.assertTrue(self.web_buttons(self.chat.messages[-1])[0].web_app.url.endswith('?lang=en'))

    async def test_app_command_keeps_the_chat_activity(self):
        bot.WEBAPP_URL = 'https://tutor.example.onrender.com/app'
        await bot.ex_chapter(self.update, self.ctx, self.chat.id, 1)
        ex = bot.st(self.chat.id)['ex']
        await bot.cmd_app(self.update, self.ctx)
        self.assertIs(bot.st(self.chat.id)['ex'], ex)          # l'esercizio in chat resta aperto

    async def test_no_button_without_https_or_outside_private_chats(self):
        for url, chat_type in ((None, 'private'), ('http://localhost:8000/app', 'private'),
                               ('https://tutor.example.onrender.com/app', 'group')):
            bot.WEBAPP_URL = url
            self.chat.type = chat_type
            await bot.cmd_menu(self.update, self.ctx)
            self.assertEqual(self.web_buttons(self.chat.messages[-1]), [])
            await bot.cmd_app(self.update, self.ctx)
            self.assertEqual(self.chat.messages[-1]['text'], T['it']['app_unavailable'])
        del self.chat.type


class PageStaticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = webapp.INDEX_HTML.read_text(encoding='utf-8')
        m = re.search(r'<script type="application/json" id="i18n">(.*?)</script>', cls.html, re.S)
        cls.i18n = json.loads(m.group(1))

    def test_same_texts_in_both_languages(self):
        self.assertEqual(set(self.i18n['it']), set(self.i18n['en']))
        used = set(re.findall(r'data-i18n="(\w+)"', self.html)) | set(re.findall(r'\bt\("(\w+)"', self.html))
        self.assertLessEqual(used, set(self.i18n['it']))

    def test_no_html_injection_points(self):
        script = self.html.split('id="i18n">', 1)[1]
        for risky in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'eval('):
            self.assertNotIn(risky, script)

    def test_only_telegram_script_is_external(self):
        external = re.findall(r'(?:src|href)="(https?://[^"]+)"', self.html)
        self.assertEqual(external, ['https://telegram.org/js/telegram-web-app.js'])
        self.assertIn('fetch("/api/reference"', self.html)
        self.assertIn('"Authorization": "tma " + initData', self.html)


if __name__ == '__main__':
    unittest.main()
