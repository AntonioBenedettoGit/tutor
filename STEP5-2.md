# Fase 5.2: base della mini app

La chat del bot **non cambia**. La mini app è una seconda interfaccia dentro Telegram, sugli stessi dati del libro (`data/kb.json`, invariata). Lo studente sceglie ogni volta quale usare. Come deciso, i progressi della mini app saranno **separati** da quelli della chat e gratuiti, ma arriveranno nelle prossime fasi: questa base non salva nulla.

## Cosa contiene

- **Home:**
  - saluto con il nome Telegram;
  - sezioni disponibili;
  - sezioni «in arrivo» (Teoria, Esercizi, Quiz);
  - scelta Italiano/English.
- **🔤 Verbi irregolari:**
  - i 145 verbi del libro;
  - ricerca istantanea su base, past o participio («went» → go / went / gone);
  - verbo non in lista → messaggio «probabilmente è regolare (+ -ed)»;
  - fonte: Appendice A, pp. 322–328.
- **📖 Glossario:**
  - i 93 termini;
  - ricerca su termine e definizione;
  - definizione con la pagina del libro.
  - Il testo è quello del libro: anche gli asterischi di «reading\*» sono stampati nel PDF.
- **Aspetto:**
  - stessi colori di Telegram, chiaro o scuro, presi automaticamente dal tema dell'utente;
  - tasto «Indietro» nativo di Telegram;
  - leggera vibrazione ai tocchi.
- **Server addormentato:** se Render dorme, la pagina mostra «il server si sta svegliando…» invece di restare bianca.

## Come si apre

- Comando **/app** in chat: risponde con il bottone «📱 Mini app».
- Bottone **«📱 Mini app»** in fondo al ☰ Menu e all'Aiuto.

La lingua passa dalla chat alla mini app: chi usa il bot in inglese la apre in inglese. Aprire la mini app **non interrompe** un esercizio o un quiz in corso in chat. Il bottone compare solo in chat private e solo quando il bot gira online (https). In locale, /app spiega che la mini app non è disponibile.

**Facoltativo, con @BotFather.** Si può impostare la mini app anche come «Main Mini App» del bot. Compare allora un bottone «Apri» sul profilo del bot e nell'elenco delle chat:
1. @BotFather → /mybots → il bot → Bot Settings → Configure Mini App;
2. URL: `https://<tuo-bot>.onrender.com/app`.

Il bottone «Menu» accanto al campo di testo **non è stato toccato**: continua a mostrare i comandi.

## Sicurezza

- **Firma di Telegram:** ogni richiesta di dati (`/api/reference`) deve portare l'`initData` firmato da Telegram.
  - Il server ne verifica la firma con il token del bot, secondo la procedura ufficiale (HMAC-SHA256 con chiave «WebAppData»).
  - Rifiuta i dati scaduti (oltre 24 ore) o con data nel futuro.
  - Senza firma valida la risposta è 401, quindi i contenuti del libro restano riservati agli utenti del bot.
- **Pagina:**
  - nessun testo dei dati viene inserito come HTML (solo nodi di testo), e un test lo verifica;
  - unico script esterno: quello ufficiale di Telegram;
  - intestazioni di sicurezza (Content-Security-Policy, nosniff, no-referrer).
- **Dati:** il server non salva nulla dello studente.

## File

- **Nuovi:**
  - `tutor/webapp.py`: verifica della firma, dati, pagina e API;
  - `webapp/index.html`: la mini app, un solo file con CSS e JS, senza build;
  - `tests/test_webapp.py`: 15 test;
  - `tools/check_webapp_browser.py`: controllo facoltativo in un browser vero.
- **Modificati:**
  - `app.py`: rotte `/app` e `/api/reference`, e URL pubblico passato al bot;
  - `bot.py`: comando /app e bottone nel menu;
  - `tutor/texts.py`: testi IT/EN e comando /app nel menu «/»;
  - `tests/test_foundations.py`: 13 handler.

## Verifiche

| Controllo | Esito |
|---|---|
| Suite completa con il PDF | 186 test superati |
| Senza PDF | 184 superati, 2 saltati |
| Senza PyMuPDF | 184 superati, 2 saltati |
| Comando della CI | OK |
| Sintassi f-string compatibile con Python 3.11 | OK |
| Sintassi JS | OK |

**Browser vero (Chromium, schermo da telefono, Telegram simulato):**
- tema chiaro e scuro;
- ricerca verbi e glossario;
- verbo regolare;
- tasto Indietro;
- cambio lingua;
- firma errata e apertura fuori da Telegram mostrano «Apri la mini app dal bot»;
- nessun errore JavaScript.

## Dopo il deploy

1. In chat scrivi **/app** e tocca «📱 Mini app». Si apre la home con il tuo nome.
2. Prova Verbi: cerca «went», poi «walked».
3. Prova Glossario: cerca «gerund». Poi prova il tasto Indietro di Telegram.
4. Apri `https://<tuo-bot>.onrender.com/api/reference` nel browser: deve rispondere `{"error": "unauthorized"}`. È giusto: fuori da Telegram i dati non escono.

**Rollback:** Render → Events → Rollback, oppure ricarica `tutor-fase5-1.zip`. La chat non dipende dalla mini app.
