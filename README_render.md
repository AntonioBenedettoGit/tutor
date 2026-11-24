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
4. Deploy. `app.py` vede `RENDER_EXTERNAL_URL` e parte in webhook, registrando su Telegram
   `https://<tuo-bot>.onrender.com/tg/<hash>`. Il token non è nell'URL, e un header segreto,
   derivato dal token, protegge il webhook: non serve nessuna nuova variabile d'ambiente.
5. Scrivi `/start` al bot.
6. (Facoltativo) In Render → Settings → **Health Check Path** metti `/health`.

## Nota free tier e «tenerlo sveglio»
Il Web Service free di Render dorme dopo 15 minuti senza traffico e si sveglia in circa un minuto.
- Dalla fase 5.1 il messaggio che lo sveglia **non si perde più**: prima `drop_pending_updates=True`
  lo cancellava a ogni avvio. Arriva una risposta, con il ritardo del risveglio.
- Per evitare anche il ritardo, un monitor esterno chiama `https://<tuo-bot>.onrender.com/health`
  ogni 5 minuti (UptimeRobot, monitor HTTP(s)), oppure ogni 10 minuti (cron-job.org).
  - `/health` risponde `ok` e nei log non compare.
  - Le 750 ore gratuite al mese bastano per **un solo** servizio sempre acceso (31 giorni = 744 ore).
- La documentazione di Render non parla dei ping «tieni sveglio». È un uso al limite del piano free,
  che non è pensato per la produzione.
- La soluzione pulita è il piano **Starter** (7 $/mese): non dorme mai e non perde i progressi in
  memoria. In alternativa, 24/7 gratis: Oracle Cloud Always Free o un Raspberry Pi (`python app.py`,
  senza `RENDER_EXTERNAL_URL`, parte in polling).
