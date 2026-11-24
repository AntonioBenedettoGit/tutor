#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Launcher per Render (Web Service, modalità webhook).

Render NON blocca l'uscita verso api.telegram.org, quindi qui NON serve
il Cloudflare Worker né TELEGRAM_API_BASE: il bot parla direttamente con
Telegram. Render inietta automaticamente PORT e RENDER_EXTERNAL_URL (HTTPS).

Senza RENDER_EXTERNAL_URL (es. in locale) parte in polling.
Tutto il resto (handlers, KB, testi) è riusato da bot.py.

Server web (fase 5.1), un piccolo server tornado al posto di run_webhook:
- GET/HEAD /health (anche / e /healthz) → 200 «ok»: serve a un monitor esterno
  (UptimeRobot, cron-job.org) per tenere sveglio il servizio free di Render;
- POST /tg/<hash> → update di Telegram, accettato solo con l'header segreto
  X-Telegram-Bot-Api-Secret-Token; il token del bot non compare più nell'URL;
- i messaggi arrivati mentre il servizio dormiva NON vengono scartati
  (drop_pending_updates=False): il primo messaggio riceve risposta, in ritardo.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bot  # noqa: E402
from tutor.logging_config import configure_logging  # noqa: E402
from telegram import Update  # noqa: E402
from telegram.ext import Application  # noqa: E402
from tornado.httpserver import HTTPServer  # noqa: E402
from tornado.web import Application as WebApp, RequestHandler  # noqa: E402

log = logging.getLogger("tutor-web")
MAX_BODY = 1_000_000            # un update Telegram è di pochi KB
HEALTH_PATHS = ("/", "/health", "/healthz")


def build_app(token):
    # post_init: menu «/» con descrizioni e testo prima di «Avvia» (IT/EN), vedi bot._sync_profile
    app = (Application.builder().token(token).concurrent_updates(False)
           .post_init(bot.post_init).build())
    return bot.register_handlers(app)


# ------------------------------------------------------------------ server web
def webhook_secret(token):
    """Segreto per l'header di Telegram (A-Z a-z 0-9 _ -, max 256): derivato dal token,
    quindi nessuna nuova variabile d'ambiente su Render."""
    return hashlib.sha256(f"tutor-webhook-secret:{token}".encode()).hexdigest()


def webhook_path(token):
    """Percorso del webhook senza il token in chiaro (non finisce nei log di accesso)."""
    return "/tg/" + hashlib.sha256(f"tutor-webhook-path:{token}".encode()).hexdigest()[:32]


class HealthHandler(RequestHandler):
    def get(self):
        self.set_header("Content-Type", "text/plain; charset=utf-8")
        self.set_header("Cache-Control", "no-store")
        self.write("ok")

    def head(self):
        self.set_header("Cache-Control", "no-store")
        self.set_status(200)


class TelegramHandler(RequestHandler):
    def initialize(self, ptb, secret):        # «application» è un nome riservato di tornado
        self.ptb = ptb
        self.secret = secret

    async def post(self):
        got = self.request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(got.encode(), self.secret.encode()):
            log.warning("Richiesta webhook rifiutata: segreto assente o errato")
            self.set_status(403)
            return
        try:
            data = json.loads(self.request.body)
            if not isinstance(data, dict) or "update_id" not in data:
                raise ValueError("non è un update")
            update = Update.de_json(data, self.ptb.bot)
        except Exception as exc:  # noqa: BLE001 - corpo non valido: si rifiuta senza fermare il server
            log.warning("Update non valido: %s", type(exc).__name__)
            self.set_status(400)
            return
        await self.ptb.update_queue.put(update)
        self.set_status(200)


def make_web_app(application, token):
    secret, path = webhook_secret(token), webhook_path(token)
    routes = [(p, HealthHandler) for p in HEALTH_PATHS]
    routes.append((path, TelegramHandler, {"ptb": application, "secret": secret}))
    return WebApp(routes, log_function=_quiet_access_log)


def _quiet_access_log(handler):
    # il monitor chiama /health ogni pochi minuti: nei log solo errori e webhook rifiutati
    status = handler.get_status()
    if status >= 400:
        log.info("%s %s → %s", handler.request.method, handler.request.path, status)


async def set_webhook_with_retry(bot_api, token, public_url, attempts=4, first_delay=2.0):
    """Subito dopo il risveglio la rete può essere lenta: qualche tentativo prima di arrendersi."""
    from telegram.error import NetworkError, RetryAfter
    delay = first_delay
    for attempt in range(1, attempts + 1):
        try:
            return await bot_api.set_webhook(
                url=public_url.rstrip("/") + webhook_path(token),
                secret_token=webhook_secret(token),
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=False,      # i messaggi arrivati mentre dormiva non si perdono
                max_connections=1,               # un update alla volta, come concurrent_updates(False)
            )
        except (NetworkError, RetryAfter) as exc:
            if attempt == attempts:
                raise
            wait = float(getattr(exc, "retry_after", 0) or delay)
            if hasattr(wait, "total_seconds"):
                wait = wait.total_seconds()
            log.warning("setWebhook non riuscito (%s), nuovo tentativo tra %.0f s", type(exc).__name__, wait)
            await asyncio.sleep(wait)
            delay *= 2


async def serve_webhook(token, public_url, port, stop_event=None, application=None):
    application = application or build_app(token)
    server = HTTPServer(make_web_app(application, token), max_body_size=MAX_BODY, xheaders=True)
    # in ascolto subito: dopo il risveglio Render consegna la richiesta in attesa appena la porta è aperta;
    # l'update resta in coda e viene elaborato appena il bot è pronto
    server.listen(port, address="0.0.0.0")
    stop = stop_event or asyncio.Event()
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop.set)
            except (NotImplementedError, RuntimeError, ValueError):
                pass
        async with application:                      # initialize() … shutdown()
            if application.post_init:
                await application.post_init(application)
            await set_webhook_with_retry(application.bot, token, public_url)
            await application.start()
            log.info("Webhook attivo; controllo di salute su /health")
            await stop.wait()
            await application.stop()
    finally:
        server.stop()


def main():
    token = bot.load_bot_token()
    if not token:
        print("Token mancante. Imposta la env var BOT_TOKEN su Render (o export BOT_TOKEN).")
        sys.exit(1)
    configure_logging(token)

    c = bot.KB["meta"]["counts"]
    bot.log.info("KB: %s capitoli, %s esempi, %s esercizi, %s verbi, %s glossario",
                 c["chapters"], c["examples_ok"] + c["examples_bad"],
                 c["exercises"], c["verbs"], c["glossary"])
    print("Tutor avviato. Ctrl-C per fermare.")

    render_url = os.environ.get("RENDER_EXTERNAL_URL")  # es. https://tuo-bot.onrender.com
    if render_url:
        # --- WEBHOOK (Render Web Service) ---
        port = int(os.environ.get("PORT", 10000))
        asyncio.run(serve_webhook(token, render_url, port))
    else:
        # --- POLLING (locale / Oracle / Raspberry) ---
        app = build_app(token)
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
