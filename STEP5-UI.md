# Fase 5: interfaccia Telegram più ordinata

**Cosa cambia:** solo l'aspetto e la navigazione.
- I contenuti non cambiano: esempi, esercizi, soluzioni, spiegazioni del libro e note italiane.
- `data/kb.json` non è stato toccato (SHA `672267043e4e…25bc0`).
- La correzione e il punteggio funzionano come nella fase 4.

Le scelte applicate:
- tutti e tre i pacchetti;
- nessuna mini-app;
- durante il quiz ogni domanda resta un messaggio nuovo, con lo storico completo;
- poche emoji, una per sezione (🧠 quiz · ✍️ esercizi · 📘 teoria · 🔎 cerca · 🔤 verbi · 📖 glossario e fonte) più ✅ ❌ per l'esito.

## 1. Ritocchi

| Dove | Prima | Ora |
|---|---|---|
| Menu «/» di Telegram | comandi senza descrizione | 9 comandi con descrizione, in italiano o inglese secondo la lingua del telefono |
| Schermata prima di «Avvia» | vuota | descrizione del bot (cosa fa, “niente AI”) e descrizione breve nel profilo |
| Domanda del quiz | “Domanda 3/10 — …” | **🧠 Domanda 3/10** ▰▰▰▱▱▱▱▱▱▱; la frase del libro sta in un riquadro |
| Esito | testo continuo | **✅ Esatto!** · Punteggio 3/4, poi un riquadro con risposta e spiegazione del libro, poi la fonte in corsivo (📖 Cap. · sezione · p.), poi la nota 🇮🇹 in un riquadro richiudibile |
| Fine quiz | “Quiz finito! 6/10” | stelle ★★★☆☆, giudizio, **elenco delle domande sbagliate**, bottoni «🔁 Rifai gli errori», «📘 Ripassa cap. X», «🧠 Nuovo quiz» |
| Esercizi | stessa logica | intestazione con barra di avanzamento, frase nel riquadro, soluzione del libro nel riquadro, riepilogo finale con stelle e bottoni «Rifai il capitolo», «Capitolo successivo», «Teoria» |
| Aiuto | testo fisso | generato dall'unica lista dei comandi, quindi sempre allineato al menu «/» |

Il menu «/» e le descrizioni vengono scritti all'avvio, in `bot.post_init` e `_sync_profile`:
- il bot scrive solo se il testo è cambiato, così non fa richieste inutili a ogni risveglio di Render;
- un errore in questo passaggio produce solo un avviso nel log e il bot parte comunque.

## 2. Bottoni fissi in basso

Dopo la scelta della lingua compare una tastiera fissa: **🧠 Quiz · ✍️ Esercizi · 📘 Teoria · ☰ Menu**.

- Un tocco su questi bottoni non viene mai corretto come risposta a un esercizio: chiude l'attività e apre quella scelta.
- **Dopo un riavvio di Render** la memoria del bot si azzera. Se lo studente tocca un bottone fisso, la lingua si ricava dal bottone stesso (o dalla lingua del telefono) e il bot risponde subito, senza chiedere di nuovo la lingua.

## 3. Navigazione

- **Capitoli per Parte (I–V):** prima si sceglie la Parte, poi il capitolo.
  - Nell'interfaccia italiana i titoli sono in italiano; nella pagina di teoria il titolo originale inglese resta sotto, in corsivo.
  - Le citazioni (📖) restano con il titolo del libro.
  - Il passaggio da Parti a capitoli e ritorno avviene nello stesso messaggio, senza riempire la chat.
- **Progressi accanto al capitolo:** si vedono durante la sessione.
  - ✅ 7/10 dopo gli esercizi di un capitolo.
  - ✅ 8/10 dopo un quiz su quel capitolo.
  - ✓ per la teoria già aperta.
  - **Limite:** i progressi stanno in memoria e si azzerano quando Render riavvia il bot. Il salvataggio permanente è nel backlog (blocco A).
- **Teoria a pagine:**
  - ◀️ ▶️ sfogliano **nello stesso messaggio**. È l'unico punto in cui un messaggio viene modificato; quiz ed esercizi restano messaggi nuovi come richiesto.
  - Ogni pagina ha l'intestazione “📘 Cap. N — titolo · pagina i/k” e i bottoni «✍️ Esercizi», «🧠 Quiz sul capitolo», «◀️ Parte N».
- Anche **/spiega** usa le stesse pagine, con in più «📘 Capitolo completo».

## Correzioni minori emerse durante il lavoro

- **Elenchi della teoria:** comparivano con doppio pallino («• • ✓»). Era un difetto già presente in fase 4, ora corretto.
- **Segni ✓/✗:** il PDF li stampa in un font monospazio, e in Telegram apparivano come `codice`. Ora sono testo normale.
- **Escape HTML:** tutti i messaggi sono HTML Telegram, e anche verbi, glossario e testo dello studente passano dall'escape.

## File modificati

- `tutor/texts.py`:
  - testi IT/EN con chiavi identiche;
  - lista unica `COMMANDS`;
  - descrizioni del bot;
  - Parti e titoli italiani dei capitoli;
  - barra ▰▱, stelle e tastiera fissa.
- `tutor/render.py`: riquadri `<blockquote>`, nota 🇮🇹 richiudibile, intestazioni con barra, riga breve per il riepilogo.
- `tutor/kb.py`: doppio pallino e ✓/✗ in monospazio.
- `bot.py`:
  - navigazione per Parte;
  - progressi;
  - pagine ◀️ ▶️;
  - riepiloghi;
  - bottoni fissi;
  - `register_handlers` e `post_init` (registrazione condivisa con `app.py`).
- `app.py`: usa `bot.register_handlers` e `bot.post_init`. Il webhook di Render non cambia.
- Test:
  - `tests/test_ui.py` (nuovo, 22 test);
  - `tests/test_foundations.py`: il controllo HTML ora ammette `blockquote`, ma non annidato.

## Verifiche

| Ambiente | Esito |
|---|---|
| con il PDF | 162 test superati |
| senza PDF | 160 superati, 2 saltati |
| senza PyMuPDF | 160 superati, 2 saltati |
| `python -m unittest discover -s tests` (comando della CI) | OK |
| `compileall` | OK |

Nessuna sintassi f-string 3.12+.

I nuovi test coprono:
- menu «/» uguale ai comandi registrati;
- limiti di lunghezza di Telegram;
- scrittura del profilo solo se cambia;
- un errore di rete all'avvio che non blocca il bot;
- bottoni fissi mai corretti come risposta;
- lingua recuperata dopo un riavvio;
- Parti che coprono i 25 capitoli;
- progressi;
- ◀️ ▶️ con callback vecchi rifiutati;
- tutte le pagine di teoria dei 25 capitoli (complete e sintesi, IT/EN) sotto i 4096 caratteri e con HTML valido;
- riepilogo del quiz con «Rifai gli errori» utilizzabile una sola volta;
- escape di verbi e glossario.

## Dopo il deploy: cosa controllare (2 minuti)

1. Nel log di Render: “KB: 25 capitoli”, nessun avviso “Profilo bot … non aggiornato”.
2. **Menu «/»:** in chat scrivi `/`. Devono comparire i comandi con descrizione. Se Telegram mostra ancora quelli vecchi, chiudi e riapri la chat: il client usa una cache.
3. **Bottoni fissi:** `/start`, poi Italiano. In basso compaiono i 4 bottoni.
4. **📘 Teoria:** Parte II, poi cap. 5. Prova ◀️ ▶️, poi «◀️ Parte II»: accanto al cap. 5 compare ✓.
5. **Quiz:** fai un quiz con qualche errore. A fine quiz controlla l'elenco degli errori e «🔁 Rifai gli errori».
6. **Esercizi:** prova cap. 21, es. 6, con “arrived in”. Deve risultare ✅, con la soluzione nel riquadro.

**Rollback:** Render, Events, Rollback sul deploy precedente, oppure ricarica `tutor-fase4.zip`.
