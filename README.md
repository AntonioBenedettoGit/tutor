# Tutor di grammatica inglese — Telegram

Bot Python senza servizi AI, basato su «English Grammar: A Complete Guide (A1-C1)».
Interfaccia IT/EN, quiz, esercizi, capitoli, glossario e verbi irregolari.

## Avvio

```bash
python -m pip install -r requirements.txt
# Configura BOT_TOKEN nell'ambiente oppure copia .env.example in .env.
python app.py
```

Su Render, `app.py` usa `RENDER_EXTERNAL_URL` e `PORT` per il webhook. In locale usa il polling. Non avviare due istanze sullo stesso token.

Il runtime legge il JSON già incluso: **non deve elaborare il PDF** e non richiede le dipendenze di build.

## Stato del lavoro

- [Fase 1: sessioni, pulsanti, bersagli degli esercizi e logging](STEP1.md).
- [Fase 2: parser, dati rigenerati, controlli e test](STEP2.md).
- **[Fase 3: revisione editoriale e separazione dei quiz dalla fonte](STEP3.md)** — distribuita su Render.
- **[Fase 4.2: parser migliorato, KB v3 estratta dal libro con formattazione](STEP4-2.md)** — solo dati e build; il comportamento del bot cambia nella fase 4.3.
- **[Fase 4.3–4.4: il bot torna al libro](STEP4-3.md)** — quiz ed esercizi dal libro con punteggio, spiegazione del libro + pagina + nota in italiano; errori del libro mostrati in originale.

La KB attuale contiene 25 capitoli, 270 esercizi, 145 verbi e 93 voci di glossario.
Il punteggio usa **solo le 160 domande del registro editoriale** (150 vero/falso e 10 MCQ), con spiegazioni IT/EN e citazioni. Gli esempi e gli esercizi grezzi restano consultabili senza assegnare punti. I quiz tematici hanno 6–9 domande e non pescano da altri capitoli.

È una revisione assistita, non una certificazione umana dell’intero libro. Le incoerenze dei capitoli 15 e 22 sono corrette con override tracciabili. Vedere limiti e test in **STEP3.md**; nessun deploy è stato eseguito.

## Test offline

```bash
python -m unittest discover -s tests -v
```

Con le sole dipendenze runtime: **108 test eseguiti, 106 superati e 2 integrazioni saltate**. Con le dipendenze di build e `TUTOR_TEST_PDF` impostato sul PDF approvato: **108/108 superati** su Python 3.11 e 3.13.

## Build dei dati (opzionale, non su ogni avvio del bot)

```bash
python -m pip install -r requirements-build.txt
python build_kb.py "/percorso/english A1-C1.pdf" data/kb.candidate.json
```

La build è specifica per il PDF approvato. Non usa fallback silenziosi e non sovrascrive la KB attiva per impostazione predefinita. Per validazione, confronto, backup e sostituzione esplicita seguire **STEP2.md**.

I messaggi transitano tramite Telegram e il server che ospita il bot; non vengono inviati a servizi AI.

Il runtime richiede anche `data/content_overrides.json` e `data/reviewed_quiz.json`: aggiornare codice e dati editoriali insieme. Un registro non valido interrompe il caricamento invece di abilitare domande non revisionate.
