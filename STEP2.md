# Fase 2 — Parser e qualità dei dati

> Documento storico della fase 2. Per la versione corrente e la nuova politica dei quiz vedere [STEP3.md](STEP3.md). I conteggi di idoneità meccanica qui riportati non sono più i criteri di ammissione ai quiz valutativi.

## Stato della consegna

La candidata è stata generata separatamente, confrontata con la KB precedente e adottata **nella copia locale** solo dopo i controlli. Non è stato fatto alcun push, commit o deploy su Render.

Questa versione comprende anche tutte le modifiche della fase 1. Non richiede nuove env né cambia webhook, porta, stato in memoria o politica sugli update in attesa.

## Risultati sui contenuti

| Contenuto | Prima | Ora |
|---|---:|---:|
| Capitoli | 25 | 25 |
| Schede esercizio | 269 | **270** |
| Verbi | 145 | **145**, con celle complete |
| Voci del glossario | 91 | **93** |
| Esempi legacy grezzi | 1.595 | 1.595, conservati |
| Coppie errore/correzione grezze | 68 | 68, conservate con correzioni runtime separate |

### Esercizi e risposte

- Recuperato il gruppo F non numerato del capitolo 4: capitalizzazione di `we visited paris last december and learned some french.`
- Rimossa la sua soluzione dalla risposta del precedente esercizio E, a cui era stata erroneamente accodata.
- Rimossa la nota del gruppo E dalla risposta `has` del gruppo D.
- Eliminate le intestazioni di pagina e le pagine divisorie che contaminavano dieci schede.
- Domande e risposte abbinate per gruppo, numerazione e posizione locale controllata. Sono gestiti sia numeri che ripartono da 1 sia risposte numerate globalmente.
- La build non ignora più gruppi non riconosciuti, numeri saltati, risposte mancanti o in eccesso: fallisce esplicitamente.
- Ogni esercizio ha `source_id`, numero della domanda/risposta e pagine PDF di provenienza. `source_q` conserva la consegna sorgente, anche quando il testo mostrato diventa una lacuna MCQ.
- Le sotto-domande a), b), c) del capitolo 20 restano riunite in schede `compound`: **non** vengono trasformate in una singola scelta multipla. Dividerle in micro-esercizi è un possibile intervento successivo di UX.

Il confronto delle 269 schede preesistenti ha rilevato sei cambiamenti nel testo mostrato delle domande: quattro rimozioni di intestazioni e due normalizzazioni della lunghezza delle lacune. In 145 risposte cambia la serializzazione; otto hanno differenze lessicali riconducibili alle contaminazioni confermate, le altre riguardano punteggiatura e ricomposizione tipografica. Le correzioni editoriali della fase 1 sono già applicate nella base del confronto.

### Verbi

La build legge la tabella alfabetica, non la prima occorrenza del verbo nelle tabelle per pattern. Le celle vengono ricomposte anche se distribuite su più righe, inclusa la forma base `under‐` / `stand`.

Correzioni verificate nel PDF:

- `dream → dreamt / dreamed → dreamt / dreamed` — pagina 324;
- `quit → quit / quitted → quit / quitted` — pagina 326, con variante già prevista nella tabella completa.

Una cella che termina con `/` o una forma base incompleta blocca la build. Le 145 chiavi dei verbi originali sono tutte presenti.

### Glossario e ricerca

Recuperate due voci omesse dal vecchio parser, entrambe a pagina 337:

- `Participle (present/past)`;
- `Particle`.

La ricerca ora normalizza nello stesso modo query ed etichette (parentesi, trattini, slash e spazi), dà priorità al risultato esatto e rispetta il limite richiesto. Tutte le **93 etichette** ritrovano la propria voce nei test.

La ricerca generale riconosce anche forme flesse come `went`, `gone`, `dreamed`, `quitted`, indirizzandole ai verbi. Le omografie come `saw` e `lay` non hanno ancora una disambiguazione conversazionale.

### Paragrafi e quattro correzioni troncate

Titolo e introduzione dei capitoli sono separati. Un cambio pagina non forza più un cambio paragrafo: la sintesi del capitolo 1 ricomincia correttamente con `Welcome.`, non a metà frase. Le tabelle teoriche sono ancora rese come testo; questa fase non introduce un renderer universale di tabelle.

In `data/content_overrides.json` sono ricostruite quattro risposte:

- `A problem occurred` e `The book (that) I read was good`: verificate e riabilitate nel quiz;
- `Most people` e `The book (that) I read…`: ricostruite, ma ancora escluse dalla domanda «quale frase è corretta?» perché la fonte presenta frammenti.

Le correzioni sono ora idempotenti e funzionano sia sul vecchio JSON sia sui testi già ripristinati dalla nuova build, senza abbinamenti vaghi o per indice.

## Nuova pipeline di build

### Un solo backend, nessun fallback silenzioso

`build_kb.py` usa un estrattore geometrico basato su **PyMuPDF 2.1**. Il vecchio codice `pdftotext`/`pypdf` è stato rimosso dal generatore, non lasciato come percorso alternativo che potrebbe produrre una KB diversa.

Le righe sono ricostruite per coordinate e posizione dei segmenti: questo recupera anche i numeri degli elenchi salvati dal PDF in blocchi separati. Header e footer sono eliminati per posizione; le pagine divisorie sono escluse prima di delimitare i capitoli.

Le dipendenze di build sono in `requirements-build.txt`. **Il bot su Render continua a installare solo `requirements.txt`**: non deve aprire il PDF né caricare PyMuPDF durante l’uso.

### Profilo del libro e controlli bloccanti

`data/book_profile.json` è un riferimento di regressione specifico per questo PDF, non un correttore grammaticale automatico. Registra:

- SHA-256 e numero delle 342 pagine del PDF approvato;
- versione del backend;
- conteggi per ciascuno dei 25 capitoli;
- firme del contenuto e dell’abbinamento domanda/risposta dei 270 esercizi;
- ID, pagine e numeri sorgente degli esercizi, controllati tramite le firme;
- elenco/formule dei 145 verbi, termini e definizioni delle 93 voci;
- firme dei testi dei capitoli e del pool legacy preservato;
- una lista esplicita delle 37 MCQ ammesse alla conversione.

Una parentesi con `/` non genera più automaticamente opzioni. Le scelte multiple devono essere nella lista approvata e corrispondere alle opzioni effettive della fonte. Le due conversioni sbagliate della fase 1 restano esercizi aperti; la domanda `has/have`, prima esclusa per l’intestazione, torna utilizzabile dopo la pulizia.

Se cambia il PDF o il risultato dell’estrazione, la build si ferma. Un aggiornamento intenzionale del profilo richiede un nuovo confronto: **non** va rigenerato automaticamente solo per far passare i test.

### Scrittura protetta

- Il percorso predefinito è `data/kb.candidate.json`, non la KB attiva.
- La validazione avviene prima di scrivere l’output.
- Per sostituire la baseline serve `--replace`.
- La baseline viene ricontrollata su disco e salvata in un backup esatto, identificato tramite hash.
- L’output viene scritto in un temporaneo nella stessa cartella e pubblicato con sostituzione atomica.
- Gli errori di validazione o della sostituzione atomica non troncano il file precedente.
- Un eventuale errore nel salvataggio del report è segnalato separatamente: non viene presentato falsamente come un rifiuto di una KB già validata e scritta.

Backup della KB precedente incluso nella consegna:

`data/backups/kb-3e86be3cc0f218f3.json`

Il backup è dei dati, non dell’intera applicazione. Per un rollback completo di codice e test usare la versione/archivio precedente corrispondente.

Report dell’adozione locale: `data/build_report.json`. Il suo hash corrisponde alla nuova KB distribuita.

## Come rigenerare

Dalla cartella del progetto:

```bash
python -m pip install -r requirements-build.txt

# 1. Crea una candidata separata; non modifica data/kb.json.
python build_kb.py "/percorso/english A1-C1.pdf" data/kb.candidate.json \
  --report data/candidate_report.json

# 2. Dopo confronto e test, sostituzione esplicita con backup.
python build_kb.py "/percorso/english A1-C1.pdf" data/kb.json \
  --replace --report data/build_report.json
```

Il PDF non è incluso nell’archivio del progetto. Il profilo riconosce l’esatto documento fornito, non qualsiasi libro con lo stesso titolo.

## Test eseguiti

**92 test superati** con Python 3.11.18 e 3.13.18, includendo la build completa dal PDF reale. Con entrambi gli interpreti la KB generata ha prodotto lo stesso SHA-256 nella verifica effettuata nella stessa giornata.

Copertura aggiunta:

- fixture reali per gruppi, numerazioni, soluzioni e celle spezzate;
- recupero degli elementi mancanti e ricerca di tutte le etichette del glossario;
- rifiuto di numeri doppi/saltati, risposte mancanti/in eccesso e gruppi inattesi;
- rifiuto di scambi domanda/risposta anche a conteggi invariati;
- rifiuto di esercizi, capitoli, verbi o definizioni persi/troncati;
- rifiuto di PDF/backend diversi e di MCQ non approvate;
- backup, sostituzione esplicita e simulazione di errore di scrittura;
- compatibilità delle correzioni e delle protezioni della fase 1.

Test ordinari senza PDF né PyMuPDF:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Questo esegue la suite con un test di integrazione saltato: **91 passano, 1 è saltato**.

Test completo con il PDF:

```bash
python -m pip install -r requirements-build.txt
TUTOR_TEST_PDF="/percorso/english A1-C1.pdf" \
  python -m unittest discover -s tests -v
```

La CI esegue i test offline ordinari: il PDF non è nel repository. Nessuna prova ha contattato il bot Telegram reale.

## Cosa rimane intenzionalmente da fare

Il pool di 1.595 esempi e 68 coppie grezze è conservato dalla baseline, non ri-estratto indiscriminatamente dal PDF. Le quattro correzioni sopra sono separate e verificate. Questa scelta evita di reintrodurre automaticamente dialoghi troncati o esempi sensibili al contesto.

Nel quiz restano ammesse dai controlli tecnici **1.537 schede vero/falso, 66 coppie e 37 MCQ**. «Ammesse» non significa «tutte certificate da una revisione grammaticale»: restano 58 esempi in quarantena e due delle quattro coppie ricostruite ancora escluse.

**Prossimo blocco consigliato:** revisione editoriale del pool valutato, recupero dei dialoghi in quarantena con il contesto completo, e correzione esplicita delle incoerenze del libro nei capitoli 15 e 22. Restano separati il restyling completo, la persistenza, i gruppi, gli errori di rete e la politica sugli update in attesa.
