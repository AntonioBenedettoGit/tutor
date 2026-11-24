# Fase 5.1: il bot su Render e il risveglio

## Il problema

Il Web Service free di Render dorme dopo 15 minuti senza traffico.
1. Il messaggio dello studente sveglia il servizio, che riparte in circa un minuto.
2. All'avvio, però, `app.py` registrava il webhook con `drop_pending_updates=True`.
3. Così chiedeva a Telegram di **cancellare i messaggi in attesa**, cioè proprio quello che aveva svegliato il bot.

Risultato: il primo messaggio restava senza risposta. Era un difetto del nostro codice, non solo del sonno di Render.

## Cosa cambia (solo `app.py`; bot, testi e KB invariati)

| | Prima | Ora |
|---|---|---|
| Messaggi arrivati durante il sonno | cancellati all'avvio | **conservati**: arriva una risposta, in ritardo (`drop_pending_updates=False`) |
| Controllo di salute | nessuno: `GET /` dava 404 | `GET`/`HEAD` su `/health`, `/healthz` e `/` rispondono `ok`, senza scrivere nel log |
| URL del webhook | `https://…onrender.com/<TOKEN>`, con il token nei log di accesso | `https://…onrender.com/tg/<hash>`: il token non compare più |
| Autenticità delle richieste | chiunque conoscesse l'URL poteva inviare update falsi | Telegram invia un header segreto (`secret_token`) e senza header la risposta è 403 |
| Rete lenta al risveglio | un errore su `setWebhook` faceva fallire l'avvio | 4 tentativi con attesa crescente |
| Spegnimento | gestito da PTB | SIGTERM gestito: stop pulito del bot e del server |

Altri dettagli:
- Il segreto e il percorso sono **derivati dal token** (SHA-256), quindi su Render non serve nessuna nuova variabile d'ambiente.
- A ogni avvio il webhook viene registrato di nuovo con i valori giusti.
- Il vecchio URL `/<token>` ora risponde 404.
- Il primo avvio dopo il deploy aggiorna da solo l'indirizzo registrato su Telegram.
- In locale, senza `RENDER_EXTERNAL_URL`, il bot resta in polling come prima.

Backlog chiuso con questa fase (blocco A):
- primo messaggio perso dopo il sonno;
- `secret_token` del webhook;
- token nell'URL;
- riprova di rete all'avvio.

## Tenerlo sveglio: le opzioni

| Opzione | Costo | Pro | Contro |
|---|---|---|---|
| **UptimeRobot**, monitor HTTP(s) su `/health` ogni 5 min | gratis | 2 minuti di configurazione; avvisa via email se il bot è giù | uso al limite del piano free; Render può comunque riavviare il servizio |
| cron-job.org ogni 10 min | gratis | stesso effetto, intervallo a scelta | come sopra |
| GitHub Actions programmato | gratis | — | le esecuzioni possono essere ritardate o saltate: **sconsigliato** |
| **Render Starter** | 7 $/mese | non dorme mai; anche quiz e progressi in memoria restano | a pagamento |
| Oracle Cloud Always Free / Raspberry Pi | gratis | sempre acceso, in polling | server da gestire |

Due vincoli da tenere presenti:
- **750 ore gratuite al mese per workspace:** bastano per **un solo** servizio free sempre acceso (31 giorni = 744 ore). Con due servizi tenuti svegli, verso fine mese Render sospende tutti i servizi free.
- **Riavvii e deploy:** Render può riavviare il servizio anche se è sveglio. Quiz in corso e progressi (✅) si azzerano, finché non faremo il salvataggio permanente (backlog).

## Verifiche

- `tests/test_webserver.py` (nuovo, 9 test), con un server vero su localhost:
  - `/health` con GET e HEAD;
  - update accettato solo con il segreto giusto;
  - corpi non validi rifiutati (400);
  - vecchio URL col token che risponde 404;
  - `setWebhook` con `drop_pending_updates=False` e senza token nell'URL;
  - riprova sugli errori di rete;
  - spegnimento pulito.
- Prova end-to-end con la vera applicazione PTB e una finta Bot API: `/start` inviato al webhook, il bot risponde con `sendMessage`.
- Suite completa:

| Ambiente | Esito |
|---|---|
| con il PDF | 171 test superati |
| senza PDF | 169 superati, 2 saltati |
| senza PyMuPDF | 169 superati, 2 saltati |
| comando della CI | OK |

## Dopo il deploy

1. Nel log di Render compare «Webhook attivo; controllo di salute su /health».
2. Apri `https://<tuo-bot>.onrender.com/health` nel browser: deve rispondere `ok`.
3. Scrivi `/start` al bot e verifica che risponda.
4. UptimeRobot: crea un monitor **HTTP(s)** sull'URL `/health` con intervallo **5 minuti**.
5. Facoltativo: in Render → Settings imposta **Health Check Path** a `/health`.

**Rollback:** Render → Events → Rollback, oppure ricarica `tutor-fase5.zip`. Il vecchio launcher registra di nuovo il suo URL all'avvio.
