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
        "quiz_start": "Nuovo quiz: {n} domande selezionate e revisionate sulla base del libro. "
                      "Rispondi con i bottoni qui sotto.",
        "quiz_tf": "Domanda {i}/{n} — la frase è corretta nello scritto standard neutro?",
        "quiz_which": "Domanda {i}/{n} — quale delle due frasi è corretta?",
        "quiz_fill": "Domanda {i}/{n} — scegli la risposta:",
        "btn_correct": "Corretta",
        "btn_wrong": "Errata",
        "quiz_right": "Esatto!",
        "quiz_wrong": "No, non è così.",
        "reviewed_answer": "Risposta revisionata: {a}",
        "reviewed_correction": "Una versione corretta: {a}",
        "reviewed_source": "Revisione assistita; riferimento alla fonte: pagine PDF {p}.",
        "consultation_source": "Testo della fonte per consultazione: non interamente revisionato; può contenere imprecisioni. I quiz usano un registro separato.",
        "consultation_only": "Esercizio estratto dal libro per consultazione: non assegna punti. La soluzione non è stata revisionata editorialmente.",
        "ex_edited_answer": "Soluzione corretta editorialmente:\n{a}",
        "quiz_tf_ok": "La frase è un esempio CORRETTO del libro (cap. {ch}).",
        "quiz_tf_bad": "La frase è un esempio DI ERRORE nel libro (cap. {ch}).",
        "quiz_fix": "La versione corretta è:\n✓ {good}\n(quella errata era: ✗ {bad}, cap. {ch})",
        "quiz_book_answer": "Risposta del libro: {a}",
        "score": "Punteggio: {c}/{t}",
        "expired": "Questo pulsante non è più attivo. Usa quelli dell’attività corrente o /menu.",
        "ex_target_pos": "Che parte del discorso è {target} nella frase?",
        "ex_target_pronoun": "Riscrivi la frase sostituendo {target} con un pronome.",
        "btn_next_ex": "Prossimo esercizio",
        "btn_next": "Prossima domanda",
        "btn_stop_quiz": "Chiudi il quiz",
        "quiz_done": "Quiz finito! Punteggio: {c}/{t}.\nVuoi riprovare con nuove domande?",
        "quiz_again": "Ancora un quiz",
        "quiz_few": "Questo capitolo ha {n} domande revisionate: il quiz resta nel capitolo scelto.",
        "ex_choose": "Scegli il capitolo di cui vuoi fare gli esercizi:",
        "ex_q": "Esercizio {i}/{n} — Capitolo {ch}: {title}\n\n{instr}\n\n{q}\n\n"
                "(Puoi anche scrivere la tua risposta qui in chat: ti mostro quella del libro per confronto.)",
        "btn_show": "Mostra la risposta",
        "btn_skip": "Salta",
        "ex_answer": "Risposta del libro:\n{a}",
        "ex_typed": "Confronta la tua risposta con quella del libro:\n{a}",
        "ex_done": "Esercizi del capitolo {n} finiti! Trovi altri esercizi nel menu.",
        "exp_ask": "Modalità spiegazioni attiva.\n\nScrivi l'argomento, in italiano o inglese. "
                   "Esempi: «present perfect», «passivo», «phrasal verbs», «articoli», "
                   "«condizionali». Il bot cerca il capitolo giusto nel libro e te lo riassume.",
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
                "/esercizi — esercizi del libro, capitolo per capitolo\n"
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
        "quiz_start": "New quiz: {n} selected, reviewed questions based on the book. "
                      "Answer with the buttons below.",
        "quiz_tf": "Question {i}/{n} — is this correct in neutral standard written English?",
        "quiz_which": "Question {i}/{n} — which sentence is correct?",
        "quiz_fill": "Question {i}/{n} — choose the answer:",
        "btn_correct": "Correct",
        "btn_wrong": "Incorrect",
        "quiz_right": "Correct!",
        "quiz_wrong": "No, that's not it.",
        "reviewed_answer": "Reviewed answer: {a}",
        "reviewed_correction": "One correct version: {a}",
        "reviewed_source": "Assistant editorial review; source reference: PDF pages {p}.",
        "consultation_source": "Source text for consultation: not fully reviewed and may contain inaccuracies. Quizzes use a separate register.",
        "consultation_only": "Book exercise for consultation: no points are awarded. Its solution has not been editorially reviewed.",
        "ex_edited_answer": "Editorially corrected solution:\n{a}",
        "quiz_tf_ok": "The sentence is a CORRECT example from the book (ch. {ch}).",
        "quiz_tf_bad": "The sentence is an example of a MISTAKE in the book (ch. {ch}).",
        "quiz_fix": "The correct version is:\n✓ {good}\n(the wrong one was: ✗ {bad}, ch. {ch})",
        "quiz_book_answer": "Book answer: {a}",
        "score": "Score: {c}/{t}",
        "expired": "This button is no longer active. Use the current activity buttons or /menu.",
        "ex_target_pos": "What part of speech is {target} in this sentence?",
        "ex_target_pronoun": "Rewrite the sentence, replacing {target} with a pronoun.",
        "btn_next_ex": "Next exercise",
        "btn_next": "Next question",
        "btn_stop_quiz": "End quiz",
        "quiz_done": "Quiz finished! Score: {c}/{t}.\nWant to try again with new questions?",
        "quiz_again": "Another quiz",
        "quiz_few": "This chapter has {n} reviewed questions: the quiz stays within the selected chapter.",
        "ex_choose": "Choose the chapter you want to practise:",
        "ex_q": "Exercise {i}/{n} — Chapter {ch}: {title}\n\n{instr}\n\n{q}\n\n"
                "(You can also type your answer here in chat: I will show you the book's answer to compare.)",
        "btn_show": "Show answer",
        "btn_skip": "Skip",
        "ex_answer": "Book answer:\n{a}",
        "ex_typed": "Compare your answer with the book's:\n{a}",
        "ex_done": "Chapter {n} exercises finished! You will find more in the menu.",
        "exp_ask": "Explanations mode on.\n\nType a topic, in English or your own language. "
                   "Examples: «present perfect», «passive», «phrasal verbs», «articles», "
                   "«conditionals». The bot finds the right chapter in the book and summarises it.",
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
                "/esercizi — book exercises, chapter by chapter\n"
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
