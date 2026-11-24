# -*- coding: utf-8 -*-
"""Interfaccia bilingue IT/EN del bot. Nessun messaggio è generato da AI:
tutte le stringhe sono fisse, i contenuti didattici vengono dal libro.

Stile (fase UI): poche emoji fisse, una per sezione —
🧠 quiz · ✍️ esercizi · 📘 teoria · 🔎 cerca · 🔤 verbi · 📖 glossario/fonte · ✅ ❌ esito.
I testi con markup sono HTML Telegram (b, i, u, s, code, blockquote).
"""

ICON = {"quiz": "🧠", "ex": "✍️", "theory": "📘", "search": "🔎", "verbs": "🔤",
        "glos": "📖", "help": "❔", "menu": "☰", "lang": "🌐", "done": "🏁"}

# Un'unica lista di comandi: menu «/» di Telegram (setMyCommands) e /help.
COMMANDS = [
    ("menu", "Menu principale", "Main menu"),
    ("quiz", "Quiz con domande dal libro", "Quiz with questions from the book"),
    ("esercizi", "Esercizi del libro con correzione", "Book exercises with scoring"),
    ("capitoli", "Teoria: i 25 capitoli del libro", "Theory: the book's 25 chapters"),
    ("spiega", "Cerca un argomento (es. /spiega passivo)", "Look up a topic (e.g. /spiega passive)"),
    ("verbi", "Verbi irregolari", "Irregular verbs"),
    ("glossario", "Glossario dei termini grammaticali", "Glossary of grammar terms"),
    ("app", "Apri la mini app", "Open the mini app"),
    ("lang", "Cambia lingua (IT/EN)", "Change language (IT/EN)"),
    ("help", "Come funziona il bot", "How the bot works"),
]

# Testo mostrato prima di «Avvia» (setMyDescription, max 512) e nel profilo (setMyShortDescription, max 120).
DESCRIPTION = {
    "it": ("Tutor di grammatica inglese basato sul libro «English Grammar: A Complete Guide (A1-C1)».\n\n"
           "🧠 Quiz con esempi e frasi del libro\n"
           "✍️ Esercizi con correzione e spiegazione\n"
           "📘 Teoria dei 25 capitoli\n"
           "🔤 Verbi irregolari · 📖 Glossario\n\n"
           "Niente AI: tutto il contenuto viene dal libro."),
    "en": ("English grammar tutor based on the book «English Grammar: A Complete Guide (A1-C1)».\n\n"
           "🧠 Quizzes with the book's examples and sentences\n"
           "✍️ Exercises with scoring and explanations\n"
           "📘 Theory for all 25 chapters\n"
           "🔤 Irregular verbs · 📖 Glossary\n\n"
           "No AI: all content comes from the book."),
}
SHORT_DESCRIPTION = {
    "it": "Grammatica inglese dal libro «English Grammar: A Complete Guide»: quiz, esercizi e teoria. Niente AI.",
    "en": "English grammar from the book «English Grammar: A Complete Guide»: quizzes, exercises, theory. No AI.",
}

PARTS = {
    "I": ("Le basi della grammatica", "The Foundations of Grammar"),
    "II": ("Nomi, articoli e pronomi", "Nouns, Articles & Pronouns"),
    "III": ("Il sistema verbale", "The Verb System"),
    "IV": ("Descrivere e collegare", "Describing & Connecting"),
    "V": ("Frasi, stile e riferimento", "Sentences, Style & Reference"),
}

CHAPTER_IT = {
    1: "Come funziona la grammatica inglese", 2: "Le parti del discorso",
    3: "Struttura della frase e ordine delle parole", 4: "Nomi: numerabili, non numerabili e plurali",
    5: "Articoli: a, an, the e articolo zero", 6: "Determinanti e quantificatori",
    7: "Pronomi e possessivi", 8: "I tempi presenti", 9: "I tempi passati",
    10: "I tempi perfect e l'aspetto", 11: "Parlare del futuro",
    12: "Il sistema dei tempi: quadro d'insieme", 13: "I verbi modali", 14: "La forma passiva",
    15: "Periodo ipotetico e irreale", 16: "Il discorso indiretto", 17: "Gerundio e infinito",
    18: "I phrasal verbs", 19: "Aggettivi e avverbi", 20: "Comparativi e superlativi",
    21: "Le preposizioni", 22: "Congiunzioni e connettivi", 23: "Le proposizioni relative",
    24: "Domande, negazioni e question tags", 25: "Punteggiatura, maiuscole ed errori comuni",
}

T = {
    "it": {
        "lang_choose": "Benvenuto nel tutor di grammatica inglese, basato sul libro "
                       "«English Grammar: A Complete Guide (A1-C1)».\n\n"
                       "Scegli la lingua dell'interfaccia:",
        "welcome": "<b>Pronto!</b> Tutto quello che vedi viene dal libro: niente AI, "
                   "nessun dato inviato a servizi esterni.\n\n"
                   "I bottoni qui sotto restano sempre a portata di mano.",
        "menu": "<b>☰ Menu</b>\nCosa vuoi fare?",
        # menu principale (inline)
        "btn_quiz": "🧠 Quiz misto",
        "btn_quiz_pick": "🧠 Quiz per capitolo",
        "btn_ex": "✍️ Esercizi",
        "btn_exp": "🔎 Cerca argomento",
        "btn_chap": "📘 Teoria",
        "btn_verbs": "🔤 Verbi irregolari",
        "btn_glos": "📖 Glossario",
        "btn_help": "❔ Aiuto",
        "btn_app": "📱 Mini app",
        "app_open": "<b>📱 Mini app</b>\nLa versione «app» del tutor, dentro Telegram: teoria, esercizi, "
                    "quiz, verbi irregolari e glossario, con i progressi salvati nel tuo account Telegram "
                    "(separati da quelli della chat).\n\nLa chat resta disponibile come sempre: usa quella "
                    "che preferisci.",
        "app_unavailable": "La mini app è disponibile solo quando il bot gira online (su Render).",
        "btn_menu": "☰ Menu",
        # tastiera fissa in basso
        "kb_quiz": "🧠 Quiz",
        "kb_ex": "✍️ Esercizi",
        "kb_theory": "📘 Teoria",
        "kb_menu": "☰ Menu",
        # scelta del capitolo
        "pick_part_chap": "<b>📘 Teoria</b>\nScegli una parte del libro:",
        "pick_part_ex": "<b>✍️ Esercizi</b>\nScegli una parte del libro:",
        "pick_part_quiz": "<b>🧠 Quiz per capitolo</b>\nScegli una parte del libro:",
        "pick_chapter": "<b>{icon} Parte {p} — {t}</b>\nScegli il capitolo:",
        "part_btn": "{p} · {t} ({a}–{b})",
        "btn_parts": "◀️ Parti",
        "btn_back_part": "◀️ Parte {p}",
        # quiz
        "quiz_start": "<b>🧠 Nuovo quiz</b> — {n} domande dal libro: esempi ✓/✗, frasi da "
                      "correggere e scelte multiple.",
        "quiz_head": "<b>🧠 Domanda {i}/{n}</b>  {bar}",
        "quiz_tf": "Secondo il libro, questa frase è corretta?",
        "quiz_which": "Quale delle due frasi è corretta?",
        "quiz_fill": "Scegli la risposta:",
        "btn_correct": "✓ Corretta",
        "btn_wrong": "✗ Errata",
        "quiz_right": "✅ Esatto!",
        "quiz_wrong": "❌ Non è così.",
        "tf_is_ok": "Nel libro è un esempio corretto:",
        "tf_is_bad": "Nel libro è un esempio di errore:",
        "book_note": "Spiegazione del libro: {a}",
        "book_answer": "Risposta del libro: {a}",
        "book_solution": "<b>Soluzione del libro</b>",
        "fix_book_form": "(nel libro: «{a}»)",
        "quiz_fix": "Versione corretta nel libro:\n✓ {good}\n✗ {bad}",
        "src_chapter": "Cap. {n} — {t}",
        "src_exercise": "esercizio {n}",
        "src_pages": "p. {p}",
        "score": "Punteggio {c}/{t}",
        "btn_next": "Prossima domanda ▶️",
        "btn_stop_quiz": "Chiudi il quiz",
        "quiz_done": "<b>🏁 Quiz finito</b>",
        "result_line": "{stars}  <b>{c}/{t}</b>",
        "verdict_4": "Eccellente!",
        "verdict_3": "Molto bene!",
        "verdict_2": "Buon lavoro, continua così.",
        "verdict_1": "Ripassa i capitoli suggeriti e riprova.",
        "review_head": "<b>Da ripassare</b>",
        "btn_redo": "🔁 Rifai gli errori ({n})",
        "quiz_again": "🧠 Nuovo quiz",
        "btn_review_ch": "📘 Ripassa cap. {n}",
        "ch_short": "cap. {n}",
        "quiz_few": "Questo capitolo ha {n} domande: il quiz resta nel capitolo scelto.",
        # esercizi
        "ex_head": "<b>✍️ Esercizio {i}/{n}</b>  {bar}\n<i>Cap. {ch} — {title}</i>",
        "ex_how_automatico": "Scrivi la risposta qui in chat: la confronto con la soluzione del libro.",
        "ex_how_parti": "Scrivi una risposta per ogni parte, una per riga (a, b, c…) oppure separate da virgole.",
        "ex_how_scelta_multipla": "Scegli la risposta con i bottoni.",
        "ex_how_autovalutazione": "Scrivi la tua risposta qui in chat (o pensala), poi guarda la soluzione "
                                  "del libro e dimmi se hai risposto bene.",
        "ex_target_pos": "Che parte del discorso è {target} nella frase?",
        "ex_target_pronoun": "Riscrivi la frase sostituendo {target} con un pronome.",
        "ex_right": "✅ Esatto!",
        "ex_wrong": "❌ Non coincide con la soluzione del libro.",
        "ex_your": "La tua risposta: {a}",
        "ex_parts": "Parti corrette: {c}/{t}",
        "ex_shown": "Soluzione mostrata senza risposta: nessun punto.",
        "ex_self_ask": "Confronta con la soluzione: hai risposto bene?",
        "ex_use_buttons": "Per questo esercizio scegli una delle risposte con i bottoni.",
        "btn_self_ok": "✓ Ho risposto bene",
        "btn_self_ko": "✗ Ho risposto male",
        "btn_show": "Mostra la soluzione",
        "btn_skip": "Salta",
        "btn_next_ex": "Prossimo esercizio ▶️",
        "ex_score": "Punteggio esercizi {c}/{t}",
        "ex_done": "<b>🏁 Esercizi del capitolo {n} finiti</b>",
        "ex_skipped": "Saltati: {s}",
        "btn_redo_ex": "🔁 Rifai il capitolo",
        "btn_next_chapter": "✍️ Capitolo {n} ▶️",
        "btn_theory_ch": "📘 Teoria cap. {n}",
        # teoria e ricerca
        "theory_head": "<b>📘 Cap. {n} — {t}</b>",
        "theory_sub": "<i>{t}pagina {i}/{k}</i>",
        "summary_sub": "Sintesi dal libro · ",
        "btn_prev": "◀️",
        "btn_nextpage": "▶️",
        "btn_full": "📘 Capitolo completo",
        "btn_ex_ch": "✍️ Esercizi",
        "btn_quiz_ch": "🧠 Quiz sul capitolo",
        "exp_ask": "<b>🔎 Cerca argomento</b>\n\nScrivi l'argomento, in italiano o inglese. "
                   "Esempi: «present perfect», «passivo», «phrasal verbs», «articoli», "
                   "«condizionali». Ti mostro il capitolo giusto del libro.",
        "exp_notfound": "Non ho trovato questo argomento nel libro. Prova con parole più "
                        "generali (es. «present perfect», «plurali», «question tags») oppure "
                        "apri 📘 Teoria.",
        "page_of": "Pagina {i}/{n}",
        # verbi e glossario
        "verbs_ask": "<b>🔤 Verbi irregolari</b>\n\nScrivi un verbo inglese (forma base, past o participio) "
                     "e ti do le tre forme del libro.",
        "verbs_res": "<b>🔤 {b}</b>\n\n<b>{b}</b> → <b>{p}</b> → <b>{pp}</b>\n"
                     "<i>base → past simple → past participle</i>",
        "verbs_nf": "«{w}» non è nella lista dei verbi irregolari del libro: "
                    "probabilmente è un verbo regolare (aggiungi -ed).",
        "glos_ask": "<b>📖 Glossario</b>\n\nScrivi un termine grammaticale (es. «gerund», «article», "
                    "«clause») e ti mostro la definizione del libro.",
        "glos_res": "<b>📖 {t}</b>\n\n{d}",
        "glos_pick": "<b>📖 Glossario</b>\nHo trovato più termini, quale ti interessa?",
        "glos_nf": "Nessun termine trovato nel glossario. Prova con un altro.",
        # aiuto
        "help_head": "<b>❔ Aiuto</b>",
        "help_foot": "Puoi usare anche i bottoni fissi in basso: 🧠 Quiz · ✍️ Esercizi · 📘 Teoria · ☰ Menu.\n\n"
                     "Tutto il contenuto viene dal libro «English Grammar: A Complete Guide»: "
                     "niente AI, nessun dato inviato online.",
        "lang_changed": "Interfaccia in italiano.",
        "already": "Questa domanda è già stata risolta: usa i bottoni qui sopra.",
        "expired": "Questo pulsante non è più attivo. Usa quelli dell’attività corrente o ☰ Menu.",
    },
    "en": {
        "lang_choose": "Welcome to the English grammar tutor, based on the book "
                       "«English Grammar: A Complete Guide (A1-C1)».\n\n"
                       "Choose the interface language:",
        "welcome": "<b>All set!</b> Everything you see comes from the book: no AI, "
                   "no data sent to external services.\n\n"
                   "The buttons below are always at hand.",
        "menu": "<b>☰ Menu</b>\nWhat would you like to do?",
        "btn_quiz": "🧠 Mixed quiz",
        "btn_quiz_pick": "🧠 Quiz by chapter",
        "btn_ex": "✍️ Exercises",
        "btn_exp": "🔎 Look up a topic",
        "btn_chap": "📘 Theory",
        "btn_verbs": "🔤 Irregular verbs",
        "btn_glos": "📖 Glossary",
        "btn_help": "❔ Help",
        "btn_app": "📱 Mini app",
        "app_open": "<b>📱 Mini app</b>\nThe «app» version of the tutor, inside Telegram: theory, exercises, "
                    "quizzes, irregular verbs and the glossary, with progress saved in your Telegram account "
                    "(separate from the chat).\n\nThe chat is still available as always: use whichever you prefer.",
        "app_unavailable": "The mini app is only available when the bot runs online (on Render).",
        "btn_menu": "☰ Menu",
        "kb_quiz": "🧠 Quiz",
        "kb_ex": "✍️ Exercises",
        "kb_theory": "📘 Theory",
        "kb_menu": "☰ Menu",
        "pick_part_chap": "<b>📘 Theory</b>\nChoose a part of the book:",
        "pick_part_ex": "<b>✍️ Exercises</b>\nChoose a part of the book:",
        "pick_part_quiz": "<b>🧠 Quiz by chapter</b>\nChoose a part of the book:",
        "pick_chapter": "<b>{icon} Part {p} — {t}</b>\nChoose a chapter:",
        "part_btn": "{p} · {t} ({a}–{b})",
        "btn_parts": "◀️ Parts",
        "btn_back_part": "◀️ Part {p}",
        "quiz_start": "<b>🧠 New quiz</b> — {n} questions from the book: ✓/✗ examples, sentences to "
                      "correct and multiple choice.",
        "quiz_head": "<b>🧠 Question {i}/{n}</b>  {bar}",
        "quiz_tf": "According to the book, is this sentence correct?",
        "quiz_which": "Which sentence is correct?",
        "quiz_fill": "Choose the answer:",
        "btn_correct": "✓ Correct",
        "btn_wrong": "✗ Incorrect",
        "quiz_right": "✅ Correct!",
        "quiz_wrong": "❌ That's not it.",
        "tf_is_ok": "In the book this is a correct example:",
        "tf_is_bad": "In the book this is an example of a mistake:",
        "book_note": "Book explanation: {a}",
        "book_answer": "Book answer: {a}",
        "book_solution": "<b>Book solution</b>",
        "fix_book_form": "(in the book: «{a}»)",
        "quiz_fix": "Correct version in the book:\n✓ {good}\n✗ {bad}",
        "src_chapter": "Ch. {n} — {t}",
        "src_exercise": "exercise {n}",
        "src_pages": "p. {p}",
        "score": "Score {c}/{t}",
        "btn_next": "Next question ▶️",
        "btn_stop_quiz": "End quiz",
        "quiz_done": "<b>🏁 Quiz finished</b>",
        "result_line": "{stars}  <b>{c}/{t}</b>",
        "verdict_4": "Excellent!",
        "verdict_3": "Very good!",
        "verdict_2": "Good work, keep going.",
        "verdict_1": "Review the suggested chapters and try again.",
        "review_head": "<b>To review</b>",
        "btn_redo": "🔁 Retry mistakes ({n})",
        "quiz_again": "🧠 New quiz",
        "btn_review_ch": "📘 Review ch. {n}",
        "ch_short": "ch. {n}",
        "quiz_few": "This chapter has {n} questions: the quiz stays within the selected chapter.",
        "ex_head": "<b>✍️ Exercise {i}/{n}</b>  {bar}\n<i>Ch. {ch} — {title}</i>",
        "ex_how_automatico": "Type your answer here in chat: I will check it against the book's solution.",
        "ex_how_parti": "Type one answer per part, one per line (a, b, c…) or separated by commas.",
        "ex_how_scelta_multipla": "Choose the answer with the buttons.",
        "ex_how_autovalutazione": "Type your answer here in chat (or just think it), then look at the book's "
                                  "solution and tell me whether you got it right.",
        "ex_target_pos": "What part of speech is {target} in this sentence?",
        "ex_target_pronoun": "Rewrite the sentence, replacing {target} with a pronoun.",
        "ex_right": "✅ Correct!",
        "ex_wrong": "❌ This does not match the book's solution.",
        "ex_your": "Your answer: {a}",
        "ex_parts": "Correct parts: {c}/{t}",
        "ex_shown": "Solution shown without an answer: no points.",
        "ex_self_ask": "Compare with the solution: did you get it right?",
        "ex_use_buttons": "For this exercise, choose one of the answers with the buttons.",
        "btn_self_ok": "✓ I got it right",
        "btn_self_ko": "✗ I got it wrong",
        "btn_show": "Show solution",
        "btn_skip": "Skip",
        "btn_next_ex": "Next exercise ▶️",
        "ex_score": "Exercise score {c}/{t}",
        "ex_done": "<b>🏁 Chapter {n} exercises finished</b>",
        "ex_skipped": "Skipped: {s}",
        "btn_redo_ex": "🔁 Redo the chapter",
        "btn_next_chapter": "✍️ Chapter {n} ▶️",
        "btn_theory_ch": "📘 Theory ch. {n}",
        "theory_head": "<b>📘 Ch. {n} — {t}</b>",
        "theory_sub": "<i>{t}page {i}/{k}</i>",
        "summary_sub": "Summary from the book · ",
        "btn_prev": "◀️",
        "btn_nextpage": "▶️",
        "btn_full": "📘 Full chapter",
        "btn_ex_ch": "✍️ Exercises",
        "btn_quiz_ch": "🧠 Chapter quiz",
        "exp_ask": "<b>🔎 Look up a topic</b>\n\nType a topic, in English or Italian. "
                   "Examples: «present perfect», «passive», «phrasal verbs», «articles», "
                   "«conditionals». I will show you the right chapter of the book.",
        "exp_notfound": "I could not find that topic in the book. Try broader words "
                        "(e.g. «present perfect», «plurals», «question tags») or open 📘 Theory.",
        "page_of": "Page {i}/{n}",
        "verbs_ask": "<b>🔤 Irregular verbs</b>\n\nType an English verb (base, past or participle form) "
                     "and I will give you all three forms from the book.",
        "verbs_res": "<b>🔤 {b}</b>\n\n<b>{b}</b> → <b>{p}</b> → <b>{pp}</b>\n"
                     "<i>base → past simple → past participle</i>",
        "verbs_nf": "«{w}» is not in the book's irregular verb list: "
                    "it is probably a regular verb (just add -ed).",
        "glos_ask": "<b>📖 Glossary</b>\n\nType a grammar term (e.g. «gerund», «article», «clause») "
                    "and I will show you the book's definition.",
        "glos_res": "<b>📖 {t}</b>\n\n{d}",
        "glos_pick": "<b>📖 Glossary</b>\nI found several terms — which one do you want?",
        "glos_nf": "No term found in the glossary. Try another one.",
        "help_head": "<b>❔ Help</b>",
        "help_foot": "You can also use the fixed buttons at the bottom: 🧠 Quiz · ✍️ Exercises · 📘 Theory · ☰ Menu.\n\n"
                     "All content comes from the book «English Grammar: A Complete Guide»: "
                     "no AI, no data sent online.",
        "lang_changed": "Interface in English.",
        "already": "This question has already been answered: use the buttons above.",
        "expired": "This button is no longer active. Use the current activity buttons or ☰ Menu.",
    },
}


def tr(lang, key, **kwargs):
    s = T[lang][key]
    return s.format(**kwargs) if kwargs else s


def help_text(lang):
    from html import escape
    col = 1 if lang == "it" else 2
    lines = [f"/{c[0]} — {escape(c[col], quote=False)}" for c in COMMANDS]
    return f"{tr(lang, 'help_head')}\n\n" + "\n".join(lines) + "\n\n" + tr(lang, "help_foot")


def chapter_title(kb, num, lang):
    """Titolo del capitolo nella lingua dell'interfaccia (il libro è in inglese)."""
    if lang == "it" and num in CHAPTER_IT:
        return CHAPTER_IT[num]
    return kb["_chapters"][num]["title"]


def part_of(chapter):
    """«Part III - The Verb System» → «III»."""
    import re
    m = re.match(r"Part\s+([IVX]+)\b", chapter.get("part") or "")
    return m[1] if m else "I"


def progress_bar(i, n, width=10):
    """Barra sobria: ▰ fatte, ▱ da fare (scalata a `width` segmenti)."""
    if n <= 0:
        return ""
    done = round(width * min(i, n) / n)
    return "▰" * done + "▱" * (width - done)


def stars(c, t):
    k = round(5 * c / t) if t else 0
    return "★" * k + "☆" * (5 - k)


def verdict(lang, c, t):
    ratio = c / t if t else 0
    level = 4 if ratio >= 0.9 else 3 if ratio >= 0.7 else 2 if ratio >= 0.5 else 1
    return tr(lang, f"verdict_{level}")


def reply_labels():
    """Testi dei bottoni fissi in basso, in entrambe le lingue → azione."""
    out = {}
    for lang in T:
        for key in ("kb_quiz", "kb_ex", "kb_theory", "kb_menu"):
            out[T[lang][key]] = key[3:]
    return out


def app_button(lang, webapp_url):
    """Bottone che apre la mini app (solo chat private), con la lingua scelta in chat."""
    from telegram import InlineKeyboardButton, WebAppInfo
    return InlineKeyboardButton(tr(lang, "btn_app"), web_app=WebAppInfo(url=f"{webapp_url}?lang={lang}"))


def menu_keyboard(lang, webapp_url=None):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    b = [
        [InlineKeyboardButton(tr(lang, "btn_quiz"), callback_data="menu:quiz"),
         InlineKeyboardButton(tr(lang, "btn_quiz_pick"), callback_data="menu:qpick")],
        [InlineKeyboardButton(tr(lang, "btn_ex"), callback_data="menu:ex"),
         InlineKeyboardButton(tr(lang, "btn_chap"), callback_data="menu:chap")],
        [InlineKeyboardButton(tr(lang, "btn_exp"), callback_data="menu:exp"),
         InlineKeyboardButton(tr(lang, "btn_verbs"), callback_data="menu:verbs")],
        [InlineKeyboardButton(tr(lang, "btn_glos"), callback_data="menu:glos"),
         InlineKeyboardButton(tr(lang, "btn_help"), callback_data="menu:help")],
    ]
    if webapp_url:
        b.append([app_button(lang, webapp_url)])
    return InlineKeyboardMarkup(b)


def reply_keyboard(lang):
    """Tastiera fissa in basso: le azioni principali sempre a portata."""
    from telegram import KeyboardButton, ReplyKeyboardMarkup
    return ReplyKeyboardMarkup(
        [[KeyboardButton(tr(lang, "kb_quiz")), KeyboardButton(tr(lang, "kb_ex"))],
         [KeyboardButton(tr(lang, "kb_theory")), KeyboardButton(tr(lang, "kb_menu"))]],
        resize_keyboard=True, is_persistent=True)


def lang_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Italiano", callback_data="lang:it"),
        InlineKeyboardButton("English", callback_data="lang:en"),
    ]])
