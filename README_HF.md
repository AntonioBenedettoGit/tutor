# Deploy su Hugging Face Spaces (Docker SDK)

Questa cartella è pronta da pushere su uno Space HF di tipo **Docker**.

## Cosa contiene
- `bot.py`, `tutor/` (kb.py, texts.py) — il bot (invariato)
- `data/kb.json` — la knowledge base
- `requirements.txt` — solo python-telegram-bot
- `app.py` — entrypoint: fa **webhook** se trova `SPACE_HOST`, altrimenti polling
- `Dockerfile` — immagine python:3.11-slim, ascolta su PORT (7860)

## Passi su HF
1. Crea/usa uno Space con **SDK = Docker**.
2. Settings → **Variables and Secrets**: aggiungi `BOT_TOKEN` (token di @BotFather).
   NON mettere il token nel `.env` committato.
3. Carica tutti i file di questa cartella alla root dello Space (git clone dello
   Space, copia, commit, push — oppure trascina i file nell'editor web).
4. HF builda l'immagine e avvia `python app.py`. `app.py` vede `SPACE_HOST`
   e registra il webhook `https://<SPACE_HOST>/<token>` su Telegram.
5. Scrivi `/start` al bot su Telegram.

## GitHub (opzionale)
Nello Space: Settings → **Link to a GitHub repo** → ogni push su GitHub fa
auto-deploy. (Il repo originale `tutor` conteneva solo lo zip; per il sync
conviene usare un repo con questi file estratti.)

## Note
- Lo Space free dorme dopo 48h di inattività; il primo messaggio lo sveglia
  (cold-start 15–90s) e `drop_pending_updates=True` scarta i messaggi persi.
- Se HF bloccasse l'outbound verso api.telegram.org, serve un proxy
  (es. Cloudflare Worker) e `webhook_url`/chiamate via proxy.
