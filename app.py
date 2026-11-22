#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Launcher per Hugging Face Spaces (Docker SDK, piano a pagamento).
Avvia il bot come WEBHOOK quando gira in uno Space (usa SPACE_HOST/PORT di HF),
altrimenti fa il normale polling (utile in locale).
Tutto il resto (handlers, KB, testi) è riusato da bot.py senza modifiche.
"""
import logging
import os
import sys
from pathlib import Path

# rendi importabile bot.py che sta nella root del progetto
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bot  # noqa: E402  (carica KB, handlers, load_bot_token)
from telegram import Update  # noqa: E402
from telegram.ext import Application  # noqa: E402


def build_app(token):
    app = Application.builder().token(token).build()
    # --- stessa registrazione di bot.main() ---
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
        print("Token mancante. Imposta il secret BOT_TOKEN nello Space (o export BOT_TOKEN).")
        sys.exit(1)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    c = bot.KB["meta"]["counts"]
    bot.log.info("KB: %s capitoli, %s esempi, %s esercizi, %s verbi, %s glossario",
                 c["chapters"], c["examples_ok"] + c["examples_bad"],
                 c["exercises"], c["verbs"], c["glossary"])
    print(f"Tutor avviato. Ctrl-C per fermare.")

    space_host = os.environ.get("SPACE_HOST")  # es. tuo-nome-tutor.hf.space
    if space_host:
        # --- Modalità WEBHOOK (Hugging Face Spaces) ---
        port = int(os.environ.get("PORT", 7860))
        app = build_app(token)
        # PTB registra il webhook su https://<SPACE_HOST>/<token>
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=token,
            webhook_url=f"https://{space_host}",
            drop_pending_updates=True,  # scarta i messaggi arrivati mentre lo Space dormiva
        )
    else:
        # --- Modalità POLLING (locale / VPS / Oracle / Raspberry) ---
        app = build_app(token)
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
