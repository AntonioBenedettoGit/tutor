# Fase 4.2: parser migliorato (KB v3)

In questa fase il bot non cambia comportamento. Cambiano i dati in `data/kb.json`: ora vengono estratti direttamente dal PDF, conservando la formattazione del libro. Dalla fase 4.3 il bot li userà per quiz ed esercizi con punteggio.

## Cosa contiene la KB v3

| Contenuto | Prima (v2) | Ora (v3) |
|---|---|---|
| Esempi ✓/✗ | 1595, copiati dalla vecchia KB, con residui `**`/`~~` | **1876** (1539 ✓, 337 ✗) estratti dal PDF, con sezione, pagina, nota del libro e testo formattato (`t_html`) |
| Coppie ✗ → ✓ | 68, alcune troncate | **107**: ritrovate tutte quelle vecchie, più 39 nuove (cap. 3, 4, 9, 21, 24…). Le correzioni parziali del libro sono ricostruite in frase intera, e il testo originale resta in `good_book` |
| Esercizi | 270 (testo e soluzione uniti) | Gli stessi 270, con impronte invariate, più consegna/domanda/soluzione formattate, **risposta separata dalla spiegazione del libro**, 15 parole bersaglio recuperate, 8 esercizi a parti a)–e) e una modalità di correzione per ognuno |
| Teoria | Testo semplice, tabelle con colonne mescolate | Blocchi (titolo, paragrafo, elenco, tabella) in testo semplice e HTML Telegram; tabelle lette cella per cella |

Modalità di correzione degli esercizi:
- automatico: 130;
- automatico_con_varianti: 21;
- scelta_multipla: 37;
- parti: 8;
- autovalutazione: 74.

Le risposte «— (no article)» del cap. 5 accettano «—», «-», «no article», «nessun articolo» e simili.

## Confronto con la vecchia KB (1595 esempi)

- **1471 identici.**
- **63 diversi solo per punteggiatura o residui di markup.**
- **31 ora più completi:** dialoghi, alternative con «/», esempi di due frasi.
- **7 ora senza il commento del libro**, che prima finiva dentro la frase. Esempio: «I didn’t see nobody literally means…» ora è «I didn’t see nobody».
- **23 non più tra gli esempi:**
  - 22 sono soluzioni degli esercizi, che restano negli esercizi;
  - 1 è la riga «Key idea» del cap. 12, che non è un esempio.

Le 160 domande della fase 3 restano tutte valide: ogni riferimento è stato ritrovato.

## Controlli e sicurezza

`kb_builder.validate_candidate` adesso controlla anche:
- che non restino residui `*`/`~~`, simboli ✓✗→| o parentesi sbilanciate in esempi e coppie;
- che l'HTML usi solo `b i s u code pre`, con tag bilanciati;
- che il testo semplice coincida con quello formattato;
- che le pagine stiano dentro il capitolo;
- gli ID unici;
- i campi ricchi presenti in tutti gli esercizi.

Il profilo `data/book_profile.json` (v2) mantiene i riferimenti già approvati: PDF, impronte dei 270 esercizi, verbi, glossario, MCQ. In più vincola:
- le impronte della teoria;
- l'impronta di esempi e coppie;
- l'impronta della parte ricca degli esercizi.

Si rigenera solo con `tools/approve_profile.py`, che scrive il profilo soltanto se tutti i controlli di contenuto passano.

```bash
pip install -r requirements-build.txt
python tools/approve_profile.py libro.pdf /tmp/approve            # verifica + report di copertura
python tools/approve_profile.py libro.pdf /tmp/approve --write    # approva il nuovo profilo
python build_kb.py libro.pdf data/kb.candidate.json               # build validata
python build_kb.py libro.pdf data/kb.json --replace               # sostituzione con backup
```

La build è deterministica: due esecuzioni producono un file identico, byte per byte.

Backup della KB precedente: `data/backups/kb-cb832b59c5929b47.json`.

## File

- **Nuovi:**
  - `tutor/pdf_rich.py`: estrazione con stili e tabelle;
  - `tutor/book_parser.py`: blocchi, esempi, coppie e soluzioni;
  - `tools/approve_profile.py`;
  - `tests/test_book_parser.py`.
- **Modificati:**
  - `tutor/kb_builder.py`: build e validazione v3;
  - `build_kb.py`;
  - `data/kb.json`, `data/book_profile.json`, `data/build_report.json`;
  - `data/content_overrides.json`: le 4 correzioni delle coppie ora agganciano il testo corretto estratto dal PDF;
  - i test.

Test: 125 (2 richiedono il PDF, con `TUTOR_TEST_PDF`). Passano tutti, anche senza PyMuPDF installato.

## Punti aperti per la fase 4.3

- Quattro coppie di esempi sulle maiuscole (cap. 2, 4, 25) («I love Summer» ✗ / «I love summer» ✓) oggi risultano «etichette in conflitto», perché il confronto ignora le maiuscole. Il quiz dovrà distinguerle.
- `ch13-main-7` è una scelta fra (a) e (b): può diventare una domanda a scelta multipla.
- Restano in sospeso le decisioni su:
  - spiegazione solo del libro (EN) oppure libro + breve nota IT;
  - errori del libro: versione originale con nota, oppure versione corretta.
