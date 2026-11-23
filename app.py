#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Launcher per Render (Web Service, modalità webhook).

Render NON blocca l'uscita verso api.telegram.org, quindi qui NON serve
il Cloudflare Worker né TELEGRAM_API_BASE: il bot parla direttamente con
Telegram. Render inietta automaticamente PORT e RENDER_EXTERNAL_URL (HTTPS).

Senza RENDER_EXTERNAL_URL (es. in locale) parte in polling.
Tutto il resto (handlers, KB, testi) è riusato da bot.py senza modifiche.
"""
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bot  # noqa: E402
from tutor.logging_config import configure_logging  # noqa: E402
from telegram import Update  # noqa: E402
from telegram.ext import Application  # noqa: E402


def build_app(token):
    app = Application.builder().token(token).concurrent_updates(False).build()
    app.add_handler(bot.CommandHandler("start", bot.cmd_start))
    app.add_handler(bot.CommandHandler("help", bot.cmd_help))
    app.add_handler(bot.CommandHandler("menu", bot.cmd_menu))
    app.add_handler(bot.CommandHandler("quiz", bot.cmd_quiz))
    app.add_handler(bot.CommandHandler("esercizi", bot.cmd_ex))
    app.add_handler(bot.CommandHandler("spiega", bot.cmd_spiega))
    app.add_handler(bot.CommandHandler("capitoli", bot.cmd_capitoli))
    app.add_handler(bot.CommandHandler("verbi", bot.cmd_verbi))
    app.add_handler(bot.CommandHandler("glossario", bot.cmd_glossario))
    app.add_handler(bot.CommandHandler("lang", bot.cmd_lang))
    app.add_handler(bot.CallbackQueryHandler(bot.on_callback))
    app.add_handler(bot.MessageHandler(bot.filters.TEXT & ~bot.filters.COMMAND, bot.on_text))
    return app


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
        app = build_app(token)
        # NOTA: PTB usa webhook_url COSÌ COM'È (non ci aggiunge il path),
        # quindi deve contenere /<token> altrimenti Telegram posta sulla radice
        # e il server locale (che ascolta su /<token>) risponde 404 -> bot muto.
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"{render_url.rstrip('/')}/{token}",
            drop_pending_updates=True,
        )
    else:
        # --- POLLING (locale / Oracle / Raspberry) ---
        app = build_app(token)
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
