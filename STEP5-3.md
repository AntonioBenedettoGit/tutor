# Fase 5.3: teoria, esercizi e quiz nella mini app

Con questa fase la mini app diventa la versione «app» completa del tutor:

| Sezione | Contenuto |
|---|---|
| 📘 Teoria | i 25 capitoli |
| ✍️ Esercizi | i 270 esercizi |
| 🧠 Quiz | domande dal libro |
| 🔤 Verbi | 145 verbi irregolari |
| 📖 Glossario | 93 termini |

**La chat non cambia**: stessi comandi e stessi bottoni. Cambia solo il testo del bottone /app, che ora elenca tutto. Lo studente sceglie l'interfaccia che preferisce.

## Cosa trova lo studente

### Home

- Le sezioni «Studia» (Teoria, Esercizi, Quiz) e «Consulta» (Verbi, Glossario), con i propri progressi: capitoli letti, esercizi fatti, quiz fatti.
- La scelta della lingua.
- Il link «Azzera i progressi della mini app», con conferma.

### 📘 Teoria

- **Capitoli:** i 25 capitoli divisi nelle Parti I–V, con il titolo italiano e quello originale.
  - Accanto al nome compare ✓ quando il capitolo è stato letto fino in fondo.
- **Ricerca:** cerca un argomento come /spiega in chat. Per esempio «present perfect» apre il cap. 10, «passivo» il cap. 14, «went» i verbi e «gerund» il glossario.
- **Pagina del capitolo:**
  - tutta la teoria su una pagina da scorrere, con grassetto, corsivo e tabelle del libro;
  - l'**indice** dei paragrafi;
  - in fondo, i collegamenti a Esercizi, Quiz e al capitolo successivo.

### ✍️ Esercizi

**Prima pagina del capitolo**
- Un pallino per ogni esercizio: verde se giusto, rosso se sbagliato, grigio se saltato.
- I bottoni:
  - «Continua dall'esercizio N»;
  - «Ricomincia da capo»;
  - «Rifai sbagliati e saltati».

**Un esercizio alla volta**
- Ci sono gli stessi 5 tipi della chat:

| Tipo | Come si risponde |
|---|---|
| risposta scritta | una casella di testo |
| esercizio a parti | una casella per parte (a, b, c…) |
| scelta multipla | bottoni con il testo completo delle opzioni |
| autovalutazione | casella facoltativa, poi «Ho risposto bene / male» |

- «Mostra la soluzione» dà 0 punti, come in chat; «Salta» passa all'esercizio dopo.

**Dopo ogni risposta**
- L'esito, poi la **soluzione del libro** con la sua spiegazione e la pagina.
- La **nota in italiano**, nell'interfaccia italiana.
- Gli errori del libro restano nella forma originale, senza note aggiunte.

**Fine del capitolo**
- Stelle, punteggio e giudizio.
- I bottoni:
  - Rifai il capitolo;
  - Capitolo successivo;
  - Teoria;
  - Home.

### 🧠 Quiz

- **Tipi di quiz:** il quiz misto su tutto il libro, oppure il quiz di un capitolo, scelto per Parte. Accanto a ogni capitolo compare il miglior risultato.
- **Domande:** 10 domande con lo stesso mix della chat: almeno 4 frasi da correggere e 2 scelte multiple, il resto vero/falso.
- **Dopo ogni risposta:**
  - la risposta giusta si colora di verde e quella sbagliata di rosso;
  - poi compare la spiegazione del libro, con fonte e nota italiana.
- **Riepilogo:**
  - stelle, punteggio e giudizio;
  - l'elenco «Da ripassare», dove ogni frase apre il suo capitolo;
  - i bottoni:
    - «Rifai gli errori»;
    - «Ripassa cap. N»;
    - «Nuovo quiz».
- **Uscita:** se esci a metà con il tasto Indietro, la mini app chiede conferma.

## Stessi risultati della chat: come è garantito

La mini app **non ha una sua correzione**. Il server usa le stesse funzioni della chat:
- `book_quiz.check_answer` / `check_parts` per gli esercizi;
- `book_quiz.build_pool` per il quiz;
- `render.solution_html` / `render.quiz_feedback_body` per soluzioni e spiegazioni;
- gli stessi blocchi di teoria.

Per riusarle ho separato in `tutor/render.py` le parti comuni (`quiz_question_parts`, `quiz_feedback_body`, `exercise_parts`, `clean_for_display`). Un controllo su **11.990 testi** generati dalla chat (ogni domanda, risposta, esercizio, soluzione e pagina di teoria, in IT e in EN) conferma che l'uscita della chat è **identica byte per byte** a prima.

I test (`tests/test_webapp_study.py`) fanno passare **ogni** esercizio e **ogni** domanda del quiz sia dalla chat sia dalla mini app, e controllano che esito e testo della soluzione coincidano.

| Prova | Quantità |
|---|---|
| Esercizi | tutti i 270 |
| Risposte scritte | 564, di cui 216 giuste |
| Scelte multiple | ogni opzione |
| «Mostra la soluzione» | ogni esercizio |
| Domande del quiz | tutte le 1.810, con ogni risposta possibile (oltre 3.500 confronti) |

Ho anche verificato che i test se ne accorgono quando sbagliano: modificando di proposito la correzione della mini app, i test falliscono subito.

## Progressi

**Dove sono salvati**
- Nel **CloudStorage di Telegram** dell'utente: lo spazio dati che Telegram dà a ogni mini app. È gratuito, segue l'account su tutti i dispositivi e non serve un database.
- Sono separati da quelli della chat, come deciso.
- Il server non salva nulla dello studente.

**Cosa si salva**

| Chiave | Contenuto | Esempio |
|---|---|---|
| `th` | capitoli letti | `5,10` |
| `ex<N>` | un carattere per esercizio | `10s.....` = giusto, sbagliato, saltato, da fare |
| `qz<N>`, `qzall` | ultimo risultato, migliore, numero di quiz fatti | `7/10;9/10;3` |

**Telegram vecchio**: se il CloudStorage non è disponibile (versioni molto vecchie di Telegram), i progressi restano solo su quel dispositivo.

## Sicurezza

- **Firma:** ogni API (`/api/theory`, `/api/exercises`, `/api/exercise/check`, `/api/quiz`, `/api/quiz/check`, `/api/search`) richiede l'initData firmato da Telegram. Senza firma risponde 401; i test lo provano su un server vero.
- **Richieste malformate:** le richieste sbagliate (JSON non valido, esercizio inesistente, opzioni del quiz manomesse, risposte troppo lunghe, tipo di contenuto errato) ricevono un 400 senza dettagli.
- **Contenuti:** il server trasforma l'HTML del libro in un albero di nodi. La pagina costruisce tutto con nodi di testo e non inserisce mai HTML preso dai dati; un test lo verifica.
- **Senza stato:** le API non tengono stato, quindi un riavvio di Render non perde nulla della mini app.

## File

**Nuovi**
- `tests/test_webapp_study.py`: confronto chat ↔ mini app e API su server vero.

**Modificati**

| File | Cosa cambia |
|---|---|
| `tutor/webapp.py` | nuove API, trasformazione HTML → nodi |
| `webapp/index.html` | la mini app completa, un solo file senza librerie esterne |
| `tutor/render.py` | parti comuni, uscita della chat invariata |
| `bot.py` | `clean_for_display` ora viene da `render` |
| `tutor/texts.py` | testo del bottone /app |
| `tests/test_webapp.py` | controlli sulla pagina: etichette identiche alla chat, API usate = API servite |
| `tools/check_webapp_browser.py` | percorso completo in un browser vero |

## Verifiche

| Controllo | Esito |
|---|---|
| Suite completa con il PDF | 203 test superati |
| Senza PDF / senza PyMuPDF | 201 superati, 2 saltati |
| Comando della CI | OK |
| `kb.json` | invariata |
| Uscita della chat | identica |
| Memoria con tutta la mini app in uso | circa 55 MB (Render free ne ha 512) |

**Browser vero** (Chromium, schermo da telefono, Telegram simulato): `python tools/check_webapp_browser.py`.
- Teoria: indice, ricerca, «letto».
- Tutti i tipi di esercizio, la ripresa da dove eri e il riepilogo.
- Il quiz completo, «Rifai gli errori» e la conferma all'uscita.
- Progressi ritrovati alla riapertura, tema scuro, inglese, firma errata.
- Nessun errore JavaScript.

## Dopo il deploy

1. **Home:** in chat scrivi /app e tocca «📱 Mini app». La home mostra Studia e Consulta.
2. **Teoria:** apri un capitolo, prova l'indice e scorri fino in fondo. Tornando indietro deve comparire ✓.
3. **Esercizi:** fanne due o tre, poi chiudi la mini app. Riaprendola, il capitolo mostra i pallini e «Continua dall'esercizio…».
4. **Quiz:** fai un quiz misto fino al riepilogo, poi prova «Rifai gli errori».
5. **Facoltativo:** fai lo stesso esercizio in chat e nella mini app, con la stessa risposta. L'esito è lo stesso.

**Rollback:** Render → Events → Rollback, oppure ricarica `tutor-fase5-2.zip`.

## Limiti noti

- **Una sola volta per volta:** un quiz lasciato a metà non si riprende, come in chat. Gli esercizi invece si riprendono, perché ogni risposta viene salvata subito.
- **Render free:** la prima apertura dopo un periodo di inattività aspetta il risveglio del server; la mini app mostra «il server si sta svegliando…». UptimeRobot su `/health` lo evita.
- **Progressi separati:** i progressi della chat restano in memoria e si azzerano al riavvio di Render, come prima. Quelli della mini app invece restano.
