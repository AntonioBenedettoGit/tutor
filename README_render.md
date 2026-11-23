# Deploy su Render (Web Service) — senza proxy

Render NON blocca l'uscita verso api.telegram.org, quindi qui NON serve il
Cloudflare Worker né TELEGRAM_API_BASE.

## Passi
1. Su https://dashboard.render.com → **New → Web Service** → collega il repo
   (o usa "Deploy from existing image"/carica i file).
2. **Build Command**: (lasciare vuoto; Render usa Python e installa requirements.txt)
   oppure `pip install -r requirements.txt`
   **Start Command**: `python app.py`
3. **Environment**: aggiungi `BOT_TOKEN` (token di @BotFather).
   Render inietta da solo `PORT` e `RENDER_EXTERNAL_URL`.
4. Deploy. `app.py` vede `RENDER_EXTERNAL_URL` e parte in webhook, registrando
   `https://<tuo-bot>.onrender.com/<token>` su Telegram.
5. Scrivi `/start` al bot.

## Nota free tier
Il Web Service free di Render dorme dopo ~15 min di inattività e si sveglia al
prossimo messaggio (Telegram ritenta la consegna, quindi i messaggi non si
perdono, solo un piccolo ritardo al primo dopo la pausa). Per always-on senza
sleep serve il piano pagato (~$19/mese). In alternativa, per 24/7 gratis e
senza sleep: Oracle Cloud Always Free o un Raspberry Pi in sede.
