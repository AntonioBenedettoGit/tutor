# -*- coding: utf-8 -*-
"""Interfaccia bilingue IT/EN del bot. Nessun messaggio è generato da AI:
tutte le stringhe sono fisse, i contenuti didattici vengono dal libro."""

T = {
    "it": {
        "lang_choose": "Benvenuto nel tutor di grammatica inglese, basato sul libro "
                       "«English Grammar: A Complete Guide (A1-C1)».\n\n"
                       "Scegli la lingua dell'interfaccia:",
        "welcome": "Perfetto. Il bot usa SOLO il contenuto del libro: niente AI, "
                   "nessun dato inviato a servizi esterni.",
        "menu": "Cosa vuoi fare?",
        "btn_quiz": "Quiz grammaticale",
        "btn_ex": "Esercizi del libro",
        "btn_exp": "Spiegazioni",
        "btn_chap": "Indice dei capitoli",
        "btn_verbs": "Verbi irregolari",
        "btn_glos": "Glossario",
        "btn_help": "Aiuto",
        "btn_menu": "Menu",
        "quiz_start": "Nuovo quiz: {n} domande prese dal libro (esempi ✓/✗, coppie da correggere, "
                      "scelte multiple). Rispondi con i bottoni qui sotto.",
        "quiz_tf": "Domanda {i}/{n} — secondo il libro, questa frase è corretta?",
        "quiz_which": "Domanda {i}/{n} — quale delle due frasi è corretta?",
        "quiz_fill": "Domanda {i}/{n} — scegli la risposta:",
        "btn_correct": "Corretta",
        "btn_wrong": "Errata",
        "quiz_right": "Esatto!",
        "quiz_wrong": "No, non è così.",
        "tf_is_ok": "Nel libro è un esempio corretto:",
        "tf_is_bad": "Nel libro è un esempio di errore:",
        "book_note": "Spiegazione del libro: {a}",
        "book_answer": "Risposta del libro: {a}",
        "book_solution": "Soluzione del libro:\n{a}",
        "fix_book_form": "(nel libro: «{a}»)",
        "quiz_fix": "Versione corretta nel libro:\n✓ {good}\n✗ {bad}",
        "src_chapter": "Cap. {n} — {t}",
        "src_exercise": "esercizio {n}",
        "src_pages": "p. {p}",
        "score": "Punteggio: {c}/{t}",
        "expired": "Questo pulsante non è più attivo. Usa quelli dell’attività corrente o /menu.",
        "ex_target_pos": "Che parte del discorso è {target} nella frase?",
        "ex_target_pronoun": "Riscrivi la frase sostituendo {target} con un pronome.",
        "btn_next_ex": "Prossimo esercizio",
        "btn_next": "Prossima domanda",
        "btn_stop_quiz": "Chiudi il quiz",
        "quiz_done": "Quiz finito! Punteggio: {c}/{t}.\nVuoi riprovare con nuove domande?",
        "quiz_again": "Ancora un quiz",
        "quiz_few": "Questo capitolo ha {n} domande: il quiz resta nel capitolo scelto.",
        "ex_choose": "Scegli il capitolo di cui vuoi fare gli esercizi:",
        "ex_head": "Esercizio {i}/{n} — Capitolo {ch}: {title}",
        "ex_how_automatico": "Scrivi la risposta qui in chat: la confronto con la soluzione del libro.",
        "ex_how_parti": "Scrivi una risposta per ogni parte, una per riga (a, b, c…) oppure separate da virgole.",
        "ex_how_scelta_multipla": "Scegli la risposta con i bottoni.",
        "ex_how_autovalutazione": "Scrivi la tua risposta qui in chat (o pensala), poi guarda la soluzione "
                                  "del libro e dimmi se hai risposto bene.",
        "ex_right": "✅ Esatto!",
        "ex_wrong": "❌ Non coincide con la soluzione del libro.",
        "ex_your": "La tua risposta: {a}",
        "ex_parts": "Parti corrette: {c}/{t}",
        "ex_shown": "Soluzione mostrata senza risposta: nessun punto.",
        "ex_self_ask": "Confronta con la soluzione: hai risposto bene?",
        "ex_use_buttons": "Per questo esercizio scegli una delle risposte con i bottoni.",
        "btn_self_ok": "Ho risposto bene",
        "btn_self_ko": "Ho risposto male",
        "btn_show": "Mostra la soluzione",
        "btn_skip": "Salta",
        "ex_score": "Punteggio esercizi: {c}/{t}",
        "ex_done": "Esercizi del capitolo {n} finiti! Punteggio: {c}/{t} (saltati: {s}).",
        "exp_ask": "Modalità spiegazioni attiva.\n\nScrivi l'argomento, in italiano o inglese. "
                   "Esempi: «present perfect», «passivo», «phrasal verbs», «articoli», "
                   "«condizionali». Il bot cerca il capitolo giusto nel libro e ti mostra la teoria.",
        "exp_notfound": "Non ho trovato questo argomento nel libro. Prova con parole più "
                        "generali (es. «present perfect», «plurali», «question tags») oppure "
                        "usa l'indice dei capitoli.",
        "exp_source": "Fonte — Capitolo {n}: {t}",
        "btn_full": "Capitolo completo",
        "btn_quiz_ch": "Quiz su questo capitolo",
        "chap_list": "Il libro ha 25 capitoli. Scegli:",
        "verbs_ask": "Scrivi un verbo inglese (forma base, past o participio) "
                     "e ti do le tre forme del libro.",
        "verbs_res": "{b} → {p} → {pp}\n\n(base → past simple → past participle)",
        "verbs_nf": "«{w}» non è nella lista dei verbi irregolari del libro: "
                    "probabilmente è un verbo regolare (aggiungi -ed).",
        "glos_ask": "Scrivi un termine grammaticale (es. «gerund», «article», «clause») "
                    "e ti mostro la definizione del glossario del libro.",
        "glos_pick": "Ho trovato più termini, quale ti interessa?",
        "glos_nf": "Nessun termine trovato nel glossario. Prova con un altro.",
        "page_of": "Pagina {i}/{n}",
        "btn_nextpage": "Pagina successiva",
        "help": "Comandi:\n"
                "/menu — menu principale\n"
                "/quiz — quiz a domande prese dal libro\n"
                "/esercizi — esercizi del libro con correzione, capitolo per capitolo\n"
                "/spiega <argomento> — spiegazioni dal libro\n"
                "/capitoli — indice dei 25 capitoli\n"
                "/verbi — cerca un verbo irregolare\n"
                "/glossario — cerca un termine nel glossario\n"
                "/lang — cambia lingua interfaccia (IT/EN)\n\n"
                "Tutto il contenuto viene dal libro «English Grammar: A Complete Guide»: "
                "niente AI, nessun dato inviato online.",
        "lang_changed": "Interfaccia in italiano.",
        "already": "Questa domanda è già stata risolta: usa i bottoni qui sopra.",
    },
    "en": {
        "lang_choose": "Welcome to the English grammar tutor, based on the book "
                       "«English Grammar: A Complete Guide (A1-C1)».\n\n"
                       "Choose the interface language:",
        "welcome": "Done. This bot uses ONLY the book content: no AI, no data sent "
                   "to external services.",
        "menu": "What would you like to do?",
        "btn_quiz": "Grammar quiz",
        "btn_ex": "Book exercises",
        "btn_exp": "Explanations",
        "btn_chap": "Chapter index",
        "btn_verbs": "Irregular verbs",
        "btn_glos": "Glossary",
        "btn_help": "Help",
        "btn_menu": "Menu",
        "quiz_start": "New quiz: {n} questions from the book (✓/✗ examples, sentences to correct, "
                      "multiple choice). Answer with the buttons below.",
        "quiz_tf": "Question {i}/{n} — according to the book, is this sentence correct?",
        "quiz_which": "Question {i}/{n} — which sentence is correct?",
        "quiz_fill": "Question {i}/{n} — choose the answer:",
        "btn_correct": "Correct",
        "btn_wrong": "Incorrect",
        "quiz_right": "Correct!",
        "quiz_wrong": "No, that's not it.",
        "tf_is_ok": "In the book this is a correct example:",
        "tf_is_bad": "In the book this is an example of a mistake:",
        "book_note": "Book explanation: {a}",
        "book_answer": "Book answer: {a}",
        "book_solution": "Book solution:\n{a}",
        "fix_book_form": "(in the book: «{a}»)",
        "quiz_fix": "Correct version in the book:\n✓ {good}\n✗ {bad}",
        "src_chapter": "Ch. {n} — {t}",
        "src_exercise": "exercise {n}",
        "src_pages": "p. {p}",
        "score": "Score: {c}/{t}",
        "expired": "This button is no longer active. Use the current activity buttons or /menu.",
        "ex_target_pos": "What part of speech is {target} in this sentence?",
        "ex_target_pronoun": "Rewrite the sentence, replacing {target} with a pronoun.",
        "btn_next_ex": "Next exercise",
        "btn_next": "Next question",
        "btn_stop_quiz": "End quiz",
        "quiz_done": "Quiz finished! Score: {c}/{t}.\nWant to try again with new questions?",
        "quiz_again": "Another quiz",
        "quiz_few": "This chapter has {n} questions: the quiz stays within the selected chapter.",
        "ex_choose": "Choose the chapter you want to practise:",
        "ex_head": "Exercise {i}/{n} — Chapter {ch}: {title}",
        "ex_how_automatico": "Type your answer here in chat: I will check it against the book's solution.",
        "ex_how_parti": "Type one answer per part, one per line (a, b, c…) or separated by commas.",
        "ex_how_scelta_multipla": "Choose the answer with the buttons.",
        "ex_how_autovalutazione": "Type your answer here in chat (or just think it), then look at the book's "
                                  "solution and tell me whether you got it right.",
        "ex_right": "✅ Correct!",
        "ex_wrong": "❌ This does not match the book's solution.",
        "ex_your": "Your answer: {a}",
        "ex_parts": "Correct parts: {c}/{t}",
        "ex_shown": "Solution shown without an answer: no points.",
        "ex_self_ask": "Compare with the solution: did you get it right?",
        "ex_use_buttons": "For this exercise, choose one of the answers with the buttons.",
        "btn_self_ok": "I got it right",
        "btn_self_ko": "I got it wrong",
        "btn_show": "Show solution",
        "btn_skip": "Skip",
        "ex_score": "Exercise score: {c}/{t}",
        "ex_done": "Chapter {n} exercises finished! Score: {c}/{t} (skipped: {s}).",
        "exp_ask": "Explanations mode on.\n\nType a topic, in English or your own language. "
                   "Examples: «present perfect», «passive», «phrasal verbs», «articles», "
                   "«conditionals». The bot finds the right chapter in the book and shows you the theory.",
        "exp_notfound": "I could not find that topic in the book. Try broader words "
                        "(e.g. «present perfect», «plurals», «question tags») or use the chapter index.",
        "exp_source": "Source — Chapter {n}: {t}",
        "btn_full": "Full chapter",
        "btn_quiz_ch": "Quiz on this chapter",
        "chap_list": "The book has 25 chapters. Choose:",
        "verbs_ask": "Type an English verb (base, past or participle form) "
                     "and I will give you all three forms from the book.",
        "verbs_res": "{b} → {p} → {pp}\n\n(base → past simple → past participle)",
        "verbs_nf": "«{w}» is not in the book's irregular verb list: "
                    "it is probably a regular verb (just add -ed).",
        "glos_ask": "Type a grammar term (e.g. «gerund», «article», «clause») "
                    "and I will show you the definition from the book's glossary.",
        "glos_pick": "I found several terms — which one do you want?",
        "glos_nf": "No term found in the glossary. Try another one.",
        "page_of": "Page {i}/{n}",
        "btn_nextpage": "Next page",
        "help": "Commands:\n"
                "/menu — main menu\n"
                "/quiz — quiz with questions taken from the book\n"
                "/esercizi — book exercises with scoring, chapter by chapter\n"
                "/spiega <topic> — explanations from the book\n"
                "/capitoli — index of the 25 chapters\n"
                "/verbi — look up an irregular verb\n"
                "/glossario — look up a glossary term\n"
                "/lang — switch interface language (IT/EN)\n\n"
                "All content comes from the book «English Grammar: A Complete Guide»: "
                "no AI, no data sent online.",
        "lang_changed": "Interface in English.",
        "already": "This question has already been answered: use the buttons above.",
    },
}


def tr(lang, key, **kwargs):
    s = T[lang][key]
    return s.format(**kwargs) if kwargs else s


def menu_keyboard(lang):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    b = [
        [InlineKeyboardButton(tr(lang, "btn_quiz"), callback_data="menu:quiz"),
         InlineKeyboardButton(tr(lang, "btn_ex"), callback_data="menu:ex")],
        [InlineKeyboardButton(tr(lang, "btn_exp"), callback_data="menu:exp"),
         InlineKeyboardButton(tr(lang, "btn_chap"), callback_data="menu:chap")],
        [InlineKeyboardButton(tr(lang, "btn_verbs"), callback_data="menu:verbs"),
         InlineKeyboardButton(tr(lang, "btn_glos"), callback_data="menu:glos")],
        [InlineKeyboardButton(tr(lang, "btn_help"), callback_data="menu:help")],
    ]
    return InlineKeyboardMarkup(b)


def lang_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Italiano", callback_data="lang:it"),
        InlineKeyboardButton("English", callback_data="lang:en"),
    ]])
