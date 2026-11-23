> Documento storico della fase 1. La versione corrente comprende anche la [fase 2](STEP2.md), che aggiorna la KB e porta la suite a 92 test. I conteggi e i limiti sotto descrivono la consegna della sola fase 1.

# Fase 1 — Prime correzioni fondamentali

## Stato

Patch locale pronta per una prova Telegram, **non ancora pubblicata né distribuita su Render**. Non richiede nuove variabili d’ambiente. Non modifica token, URL del webhook, porte o politica `drop_pending_updates`.

Test offline: **42 test superati** con Python 3.11.18 e 3.13.18, usando python-telegram-bot 22.8. La dipendenza è ora fissata a questa versione; le dipendenze transitive non sono ancora bloccate in un lockfile.

## 1. Pulsanti e stato della conversazione

- Quiz ed esercizi hanno un ID di sessione e una posizione nei callback.
- Risposte, Next e Stop delle vecchie sessioni vengono rifiutati senza modificare lo stato.
- Una risposta non può essere conteggiata due volte.
- Next nel quiz richiede una risposta; Next negli esercizi richiede che la soluzione sia stata mostrata. Salta rimane disponibile.
- Le tastiere usate tramite callback vengono rimosse quando possibile. La verifica sul server resta attiva anche se Telegram non consente la modifica del messaggio.
- I callback della stessa chat sono protetti da un lock; il launcher mantiene l’elaborazione sequenziale degli update.
- Entrare in una nuova attività chiude quella precedente, anche passando da Help, cambio lingua o vecchi pulsanti di navigazione.
- Pagine e risultati del glossario sono associati alla consultazione corrente.
- È stato corretto anche il ramo delle spiegazioni multipagina, che provava a modificare una tupla.

**Comportamento intenzionale dopo il deploy:** i vecchi pulsanti di risposta/avanzamento non saranno più attivi. Aprire `/menu` e iniziare una nuova attività. Le sessioni sono ancora in memoria e si perdono ai riavvii.

## 2. Quindici esercizi ora comprensibili

I bersagli mancanti nel PDF sono definiti in `data/content_overrides.json`:

- Capitolo 1: speech, race, quietly, under.
- Capitolo 2: river, patiently, kind, on, but, water, Wow, that.
- Capitolo 18: the lights, the newspaper, the children.

Le consegne nominano il bersaglio e lo mostrano in grassetto nella frase. Per i capitoli 1–2 chiedono la parte del discorso; per il capitolo 18 chiedono di sostituire il sintagma con un pronome. Le consegne adattate sono disponibili in IT/EN.

Gli esercizi vengono inviati in HTML con escaping dei contenuti. Il pulsante successivo degli esercizi si chiama ora «Prossimo esercizio», non «Prossima domanda».

## 3. Correzioni non distruttive e quarantena del quiz

`data/kb.json` è rimasto identico all’originale. Le correzioni vengono applicate al caricamento e non dipendono dagli indici della lista. Ogni abbinamento editoriale deve individuare esattamente una scheda: in caso contrario l’avvio fallisce con un errore esplicito, anziché applicare una correzione a una domanda sbagliata.

Due conversioni errate in scelta multipla sono ripristinate come esercizi aperti:

- Capitolo 12: `(already / see)` è una traccia di coniugazione, non una scelta fra due risposte.
- Capitolo 20: l’esercizio composto a), b), c) mantiene le tre richieste e non offre più opzioni relative soltanto alla prima.

Il quiz esclude prudenzialmente:

- testi con etichette corretto/errato contraddittorie, anche dopo normalizzazione di maiuscole e spazi;
- esempi con virgolette o parentesi non bilanciate;
- correzioni note come troncate;
- testi con intestazioni di pagina o residui di markup evidenti;
- le due MCQ errate ripristinate come esercizi aperti.

Con i dati attuali: 58 schede esempio e 4 coppie errore/correzione vengono escluse dal punteggio. Le MCQ utilizzabili passano da 39 a 36: due tornano esercizi aperti e una è esclusa perché contiene un’intestazione. Il pool disponibile comprende 1.537 schede vero/falso, 64 coppie e 36 MCQ.

**Importante:** «ammesso dai controlli» non significa «interamente revisionato da un punto di vista grammaticale». Le esclusioni sono una barriera prudenziale, non la risoluzione definitiva dei problemi del parser. I dati esclusi non sono cancellati: alcuni restano visibili nel capitolo completo o negli esercizi aperti, in attesa della fase 2.

## 4. Logging e protezioni di sviluppo

- I logger `httpx` e `httpcore` non registrano più richieste a livello INFO.
- Il formatter maschera il token noto e i pattern dei token Bot API, anche nei traceback gestiti dai logger configurati.
- Aggiunti `.gitignore`, `.dockerignore` e `.env.example` per ridurre il rischio di includere credenziali locali.
- Aggiunta CI con Python 3.11 e 3.13. Il workflow è scritto ma sarà eseguito dalla piattaforma solo dopo la pubblicazione del codice.

Questo non cancella eventuali log già esistenti. Se il token reale è stato condiviso attraverso log o screenshot, va ruotato tramite BotFather.

## Test

Dalla cartella del progetto:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Non occorrono token né PDF per i test. Le richieste Telegram sono simulate. I test coprono anche il rendering di tutti i 269 esercizi con relative soluzioni e di tutti gli elementi quiz ammessi dai filtri, in entrambe le lingue.

## Checklist prima del deploy sul bot usato quotidianamente

Preferire un bot Telegram di prova con un servizio separato; non far girare due istanze sullo stesso token.

1. `/start` → italiano → esercizi del capitolo 1: verificare bersaglio, grassetto e consegna.
2. Capitolo 18, gruppo B: verificare che la consegna chieda di sostituire l’oggetto con un pronome.
3. Quiz: rispondere, poi premere due volte Next; deve avanzare una sola volta.
4. Aprire un nuovo quiz e provare Stop o una risposta del quiz vecchio: il nuovo deve rimanere intatto.
5. Dal quiz aprire Help o Verbi: i pulsanti del quiz precedente devono risultare scaduti.
6. Provare la stessa sequenza con interfaccia inglese.
7. Controllare i log e confermare che non compaia il token.

Quando si pubblica questa patch, includere anche i nuovi file `tutor/content.py`, `tutor/logging_config.py` e `data/content_overrides.json`: non basta sostituire `bot.py`.

Se il servizio Render è collegato al repository con auto-deploy, il deploy partirà soltanto dopo che le modifiche saranno state pubblicate nel repository. Questa sessione non ha effettuato push, commit o deploy.

## Prossimo passo: fase 2, qualità e generazione dei contenuti

Restano da affrontare separatamente:

- parser PDF, intestazioni e paragrafi, celle su più righe, esercizi non numerati e sotto-domande;
- controlli bloccanti prima di sovrascrivere una KB, incluso il fallback che perde esercizi e verbi;
- ricostruzione e revisione delle coppie e degli esempi in quarantena;
- errori editoriali del libro nei capitoli 15 e 22;
- verbo dream, ricerca glossario, ricerca delle forme verbali, sintesi frammentarie;
- messaggi privacy, persistenza, gestione dei gruppi e degli errori di rete, scelta sugli update in attesa;
- un restyling più ampio dell’interfaccia.

Non rigenerare ancora la KB distribuita dal PDF: il generatore originale non è stato modificato in questa fase.
