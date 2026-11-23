# Fase 3 — Revisione editoriale e quiz separati dalla fonte

## Stato

Consegna **locale**, comprensiva delle fasi 1 e 2. Nessun commit, push, deploy o collegamento al Telegram reale. Il bot funzionante su Render non è stato toccato.

La KB grezza `data/kb.json`, il backup e il profilo della fase 2 non sono stati modificati in questa fase. Nessuna nuova variabile d’ambiente o dipendenza runtime.

**Questa è una revisione assistita dall’assistente, non una certificazione umana indipendente né la revisione grammaticale integrale del libro.**

## Il problema risolto

La validità dell’estrazione non coincide con la validità di una domanda valutativa. Il libro contiene anche preferenze di stile, esempi dipendenti dal contesto e soluzioni contraddittorie. Un esempio con ✗ non può diventare automaticamente un vero/falso.

Prima, il quiz ammetteva per difetto ogni elemento non bloccato dai controlli meccanici. Ora:

1. Esempi, coppie di correzione ed esercizi grezzi rimangono disponibili per consultazione, ma non alimentano direttamente il punteggio.
2. Il quiz usa **solo `data/reviewed_quiz.json`**, un registro esplicito con domanda, soluzione, spiegazione IT/EN e citazioni della fonte.
3. Le domande senza approvazione esplicita non entrano nel pool. Un registro mancante/non valido blocca il caricamento: non si ripiega silenziosamente sui dati grezzi.
4. I quiz di capitolo non vengono più completati pescando da altri capitoli.
5. Le risposte revisionate non vengono presentate impropriamente come «risposta del libro».

## Primo insieme revisionato

| Contenuto valutativo | Numero |
|---|---:|
| Vero/falso selezionati, con spiegazione e correzione quando falsa | 150 |
| Domande contestuali ricostruite | 8 |
| Domande basate sulle due correzioni editoriali | 2 |
| **Totale** | **160** |

Ogni capitolo ha almeno 6 domande. Capitolo 11: 8; capitoli 15 e 22: 7 ciascuno; capitoli 16 e 25: 9 ciascuno. Gli altri capitoli: 6 ciascuno. Il quiz generale conserva fino a 10 domande; quello tematico utilizza solo quelle effettivamente disponibili nel capitolo.

Sono rimasti intatti, come dati grezzi, **1.595 esempi, 68 coppie di correzione e 270 esercizi**. Non significa che siano stati tutti revisionati. Le 37 MCQ già estratte restano consultabili, ma non sono approvate in blocco per il punteggio. Le 10 MCQ del registro sono le 8 ricostruzioni e le 2 correzioni sopra indicate, non una certificazione delle 37 precedenti.

Non si usano in questo primo registro le coppie legacy «quale frase è corretta»: il codice di resa rimane compatibile, ma il loro ingresso nel quiz richiederà revisione esplicita.

## Due correzioni della fonte

### Capitolo 15 — `ch15-main-7`, pagina PDF 189

Fonte:

> I won’t lend you the car (unless / as long as) you don’t drive too fast.

La soluzione selezionava `as long as`, ma la frase significava un rifiuto del prestito condizionato alla guida prudente. Anche l’alternativa con `unless` proposta nella spiegazione invertiva la logica.

**Intervento dichiarato:** per costruire una domanda chiara sulla condizione di guida prudente, si riscrive:

> I’ll lend you the car **as long as** you don’t drive too fast.

Equivalente coerente:

> I won’t lend you the car **unless** you drive safely.

Non si sostiene che la frase originaria fosse sintatticamente impossibile: il difetto è l’incoerenza logico-didattica fra testo, intento e spiegazione. La riscrittura è segnalata come editoriale e la consegna specifica esplicitamente l’intento: il proprietario presta l’auto solo se chi la prende guida prudentemente. Non si chiede di distinguere due connettivi sulla sola grammaticalità.

### Capitolo 22 — `ch22-B-5`, domanda PDF 278, soluzione PDF 279

> (**Despite** / Although) the heavy traffic, we arrived on time.

`The heavy traffic` è un sintagma nominale: la risposta è **Despite**. `Although` richiederebbe una proposizione, per esempio `although the traffic was heavy`.

La soluzione originale iniziava con `Although`, per poi contraddirsi e arrivare a `Despite`. Ora viene mostrata una spiegazione univoca.

### Conservazione degli originali

Le due patch sono in `data/content_overrides.json` e sono applicate solo in memoria. Ogni esercizio mantiene:

- `source_id` e `source_q`;
- `source_answer`, con la soluzione originale completa;
- pagine PDF della domanda e della soluzione;
- `editorial_note` in italiano e inglese.

Il testo completo del capitolo rimane quello della fonte: non è stato riscritto silenziosamente. Nell’interfaccia è esplicitamente materiale per consultazione, potenzialmente contenente imprecisioni.

## Dialoghi e punteggiatura recuperati

- **Capitolo 11:** telefono che squilla e chiusura della finestra, con entrambe le battute complete. Si chiede la funzione contestuale di `will`, senza bollare ogni alternativa con `going to` come sgrammaticata.
- **Capitolo 16:** discorso diretto completo; domanda di Tom sulla stazione e sua trasformazione con ordine dichiarativo; avvertimento della guida con `warned us not to touch`.
- **Capitolo 25:** domanda citata di James, maiuscola e punto interrogativo; convenzione americana del punto dentro le virgolette; convenzione britannica logica del punto fuori. La varietà richiesta è esplicita.

Non si riammettono i frammenti originali troncati. Si creano domande autonome con citazioni della fonte completa. Gli altri frammenti restano esclusi dal punteggio, inclusa la coppia sul numero di punti esclamativi che il vecchio parser aveva reso identica.

Caso particolare: `Monday/December` e `monday/december` erano stati confusi dalla normalizzazione senza distinzione di maiuscole. Nel registro si conservano esattamente le lettere e si chiede esplicitamente di valutare anche le maiuscole.

## Ambiguità non trasformate in errori assoluti

Fra i casi esclusi dai vero/falso: `I like the music`, `I am boring`, `The thieves were arrested by the police`, `If you will help me, I’ll be grateful`, `You like coffee?` e le virgole prima di `although`. Sono frasi grammaticali o dipendenti dal contesto, non errori automatici.

Fra le MCQ grezze ancora da rivedere:

- `some/any` in una richiesta;
- `needn’t have/didn’t need to` quando l’azione è stata compiuta;
- `can/may` per possibilità generale;
- `very/absolutely exhausted`;
- accordo con `neither … nor`.

`data/editorial_report.json` elenca tutte le 37 MCQ grezze con stato di consultazione, i 58 esempi esclusi dai controlli meccanici, i conteggi e gli hash della consegna. Quell’elenco meccanico non equivale a dichiarare errati grammaticalmente tutti e 58 gli esempi.

## Comportamento e controlli tecnici

- Validazione dello schema, ID univoci, stato di revisione, tipi di domanda, etichette booleane, opzioni distinte e indice della soluzione.
- Spiegazioni IT/EN obbligatorie; per i vero/falso errati è obbligatoria una correzione diversa dall’originale.
- Hash del PDF registrato nella KB e citazioni presenti nel testo del capitolo, con pagine entro i limiti del capitolo.
- Riferimenti degli esempi abbinati al contenuto, non all’indice nella lista. I duplicati grezzi identici non generano più domande duplicate.
- Verifica delle due domande riscritte contro esercizi e override: se domanda/soluzione di riferimento cambiano, il caricamento si interrompe.
- Test sul PDF reale per tutte le citazioni e per le due soluzioni originali contraddittorie. A runtime il PDF **non serve**: le pagine reali si verificano nei test di integrazione, non durante ogni avvio.
- Applicazione idempotente; i controlli e le protezioni delle fasi precedenti rimangono attivi.
- Il report prodotto da una futura build distingue i conteggi grezzi dal numero di domande revisionate. Il report di pubblicazione `data/build_report.json` resta quello storico della fase 2.

### File principali nuovi o aggiornati nella fase 3

- `tutor/editorial.py`: caricamento e validazione del registro.
- `data/reviewed_quiz.json`: le 160 domande, spiegazioni e riferimenti.
- `data/content_overrides.json`: due nuove correzioni oltre alle patch precedenti.
- `tutor/content.py`, `tutor/kb.py`: separazione fra consultazione e valutazione; nei riepiloghi gli elenchi di esempi usano quelli revisionati.
- `bot.py`, `tutor/texts.py`: pool, contesti, feedback, messaggi di consultazione e quiz tematici senza fallback.
- `tests/test_editorial.py`: regressioni editoriali e citazioni PDF.
- `data/editorial_report.json`: riepilogo verificabile della consegna.

## Test eseguiti

| Ambiente | Esito |
|---|---|
| Python 3.11.18 con PDF e dipendenze di build | 108/108 superati |
| Python 3.13.18 con PDF e dipendenze di build | 108/108 superati |
| Python 3.11, sole dipendenze runtime, backend PDF assente | 106 superati, 2 integrazioni saltate su 108 |

Oltre alle regressioni precedenti: registro assente/alterato, cambiamenti nei riferimenti, nessun ripiego sui dati grezzi, capitoli corretti, citazioni, maiuscole, contesti regionali e **tutte le 160 domande** rese e valutate in IT/EN sia con risposta giusta sia con risposta sbagliata.

Per ripetere:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Per includere le due integrazioni:

```bash
python -m pip install -r requirements-build.txt
TUTOR_TEST_PDF="/percorso/english A1-C1.pdf" python -m unittest discover -s tests -v
```

Il PDF non è distribuito nell’archivio.

## Limiti e prossimo passaggio

Il registro è intenzionalmente ristretto. Non sono stati certificati tutti i 1.595 esempi o i 270 esercizi; il testo e le risposte non revisionati sono segnalati come tali. Per ampliare il quiz si aggiunge una domanda esplicita con contesto, soluzione, spiegazioni e fonte, poi si rieseguono i test. Non si riattiva per difetto il materiale escluso.

Prima di adottare questa versione sul servizio reale resta una prova Telegram controllata: doppio clic e pulsanti scaduti, cambio attività, esercizio con bersaglio, entrambe le correzioni, quiz breve di capitolo, dialoghi e cambio lingua. I test offline non sostituiscono una prova sul webhook reale.

L’archivio include il progetto completo: quando si deciderà di procedere, codice e tutti i JSON editoriali vanno aggiornati insieme. **Non sostituire soltanto `bot.py` o soltanto la KB.** Non è stato eseguito nessuno di questi aggiornamenti sul servizio funzionante.
