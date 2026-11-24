# Fase 4.3 e 4.4: il bot torna al libro

Il bot ora usa direttamente esempi, coppie, esercizi e spiegazioni del libro. Tutti i contenuti assegnano di nuovo punti. Non ci sono più le etichette «consultazione» né il limite di 6–9 domande per capitolo.

## Quiz (`/quiz`, «Quiz su questo capitolo»)

Ogni quiz ha 10 domande. Il pool contiene **1810 domande**:

| Tipo | Quante | Da dove |
|---|---|---|
| Vero/falso | 1658 | esempi ✓/✗ del libro |
| «Quale frase è corretta?» | 107 | coppie ✗ → ✓ del libro |
| Scelta multipla | 37 + 8 | 37 esercizi a scelta del libro, più 8 domande ricostruite da dialoghi e discorsi del libro (fase 3) |

Ogni quiz contiene almeno 4 coppie e 2 scelte multiple. Ogni capitolo ha almeno 10 domande.

Dopo ogni risposta il bot mostra, in quest'ordine:
1. la versione del libro;
2. la spiegazione del libro;
3. la fonte: 📖 capitolo, sezione e pagina del PDF;
4. 🇮🇹 una breve nota in italiano, solo con l'interfaccia in italiano.

Le domande vero/falso indicano anche la sezione del capitolo. Così, per esempio, «Where you going?» si legge nel contesto «Spoken vs. Written Grammar».

## Esercizi (`/esercizi`)

Si possono fare tutti i 270 esercizi, ognuno con il suo tipo di correzione:

| Tipo di correzione | Esercizi | Come funziona |
|---|---|---|
| automatico (+ varianti) | 129 + 22 | Lo studente scrive la risposta e il bot la confronta con la soluzione del libro. Il confronto accetta contrazioni, maiuscole, «—/nessun articolo», etichette in italiano («sostantivo») e la frase intera. |
| parti a)–e) | 8 | Una risposta per riga o separate da virgole. Il bot corregge ogni parte. |
| scelta multipla | 37 | Bottoni A/B/C, oppure la lettera scritta in chat. |
| autovalutazione | 74 | Per riscritture e risposte libere: lo studente scrive la sua risposta (o la pensa), legge la soluzione del libro e preme «Ho risposto bene» o «Ho risposto male». |

Le altre opzioni funzionano così:
- **«Mostra la soluzione»:** mostra la soluzione senza dare punti, tranne negli esercizi ad autovalutazione.
- **«Salta»:** l'esercizio non viene contato.

A fine capitolo il bot mostra il punteggio e il numero di esercizi saltati.

## Teoria (`/spiega`, `/capitoli`)

La teoria viene dai blocchi del capitolo, con grassetto, corsivo e tabelle del libro. Si ferma prima di «Practice/Answers», così le soluzioni non compaiono nella teoria. Gli esempi della sintesi sono quelli del libro.

## Errori del libro (fase 4.4): decisione «mostra l'originale, nessuna nota»

- **ch15-main-7 e ch22-B-5:** si mostrano e si correggono come nel PDF. La risposta valida è «as long as», nella frase «I won't lend you…», e «Although». Le due riscritture editoriali della fase 3 sono state tolte.
- **Le 5 scelte multiple ambigue** (some/any, needn't have, can/may, very/absolutely exhausted, neither…nor): restano come nel libro.
- **Note:** nessuno di questi 7 esercizi ha una nota in italiano.

## Correzioni del parser in questa fase

Gli errori sono stati riparati dal PDF, senza escludere niente:
- **Enfasi del libro spostata di una parola** (*Who did* **you**, «No.» *That*, «Who wrote…?» «— a»): ora il bersaglio viene riallineato (`_realign_core`).
- **ch21-main-1, esercizio con due spazi:** la risposta è la frase «at 9 o'clock on Monday morning.». La nota tra parentesi è la spiegazione. La correzione è automatica e accetta «at on» e «at … on».
- **«✓ do not → don't, I am → I'm…»** (p. 308): prima diventava «do».
- **«✓ the rich, the poor, the young, the elderly, the unemployed»** (p. 65): prima diventava «the», a causa dei residui di asterischi.
- **Due falsi esempi tolti:** la cella di tabella «✓ (singular)» (p. 77) e il «a ✓/✗ example.» della prosa (p. 311).

Restano nella teoria ma fuori dal quiz 4 frammenti che il libro presenta con «…» o come parola isolata: «…every.», «…where is the station?», «…why didn't she call.» e «(not ✗ have)». Da soli non si possono giudicare.

## Dati

| File | Cosa contiene |
|---|---|
| `data/kb.json` | Ricostruita. SHA `672267043e4e…25bc0`. Backup della KB 4.2 in `data/backups/kb-3dfddb110d298389.json`. |
| `data/book_profile.json` | Aggiornato con `approve_profile.py --write`. |
| `data/notes_it.json` | Nuovo. Contiene 263 note sugli esercizi e 266 note di sezione. Il caricamento è fail-closed: chiavi sconosciute, note vuote o più lunghe di 600 caratteri bloccano l'avvio. |
| `data/content_overrides.json` | Ora vuoto: il parser ripara il testo. Resta solo l'esclusione dal quiz di «(not ✗ have)». |
| `data/reviewed_quiz.json` | Restano le 8 scelte multiple ricostruite. I 150 esempi verbatim sono già nel pool come esempi del libro; le 2 riscritture editoriali sono state rimosse. |

## Test

- **Con il PDF:** 140 test superati.
- **Senza PyMuPDF:** 138 superati, 2 saltati.

I nuovi controlli verificano che:
- ogni esercizio si possa completare con la soluzione del libro, sia in italiano sia in inglese;
- ognuna delle 1810 domande del quiz, sia in IT sia in EN, mostri la spiegazione del libro e la pagina e assegni il punto una sola volta;
- l'HTML sia sempre bilanciato e la teoria resti sotto i 3500 caratteri per pagina.

## Ancora da fare (fase 4.5)

- Prova reale su Telegram.
- Nuovo zip per il caricamento su GitHub, con rollback pronto: `kb.json`, `notes_it.json` e gli override vanno pubblicati insieme.
