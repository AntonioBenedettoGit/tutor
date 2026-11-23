#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_kb.py — Trasforma il PDF "English Grammar: A Complete Guide" (A1-C1)
in una knowledge base JSON per il bot tutor Telegram, SENZA AI.

Uso:
    python3 build_kb.py "percorso/al/libro.pdf" [output.json]

Se pdftotext (poppler-utils) non è installato, prova con pypdf.
L'output di default è data/kb.json.
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

SOFT_HYPHENS = ("\u2010", "\u00ad")  # hyphen di a-capo e soft hyphen

# ---------------------------------------------------------------- capitolario
CHAPTERS = [
    (1,  "How English Grammar Works", "I"),
    (2,  "The Parts of Speech", "I"),
    (3,  "Sentence Structure & Word Order", "I"),
    (4,  "Nouns: Countable, Uncountable & Plurals", "II"),
    (5,  "Articles: a, an, the & the Zero Article", "II"),
    (6,  "Determiners & Quantifiers", "II"),
    (7,  "Pronouns & Possessives", "II"),
    (8,  "The Present Tenses", "III"),
    (9,  "The Past Tenses", "III"),
    (10, "The Perfect Tenses & Aspect", "III"),
    (11, "Talking About the Future", "III"),
    (12, "The English Tense System: Putting It All Together", "III"),
    (13, "Modal Verbs", "III"),
    (14, "The Passive Voice", "III"),
    (15, "Conditionals & the Unreal", "III"),
    (16, "Reported Speech", "III"),
    (17, "Gerunds & Infinitives", "III"),
    (18, "Phrasal Verbs", "III"),
    (19, "Adjectives & Adverbs", "IV"),
    (20, "Comparatives & Superlatives", "IV"),
    (21, "Prepositions", "IV"),
    (22, "Conjunctions & Linking Words", "IV"),
    (23, "Relative Clauses", "IV"),
    (24, "Questions, Negatives & Question Tags", "V"),
    (25, "Punctuation, Capitalization & Common Mistakes", "V"),
]
PARTS = {
    "I":   "Part I - The Foundations of Grammar",
    "II":  "Part II - Nouns, Articles & Pronouns",
    "III": "Part III - The Verb System",
    "IV":  "Part IV - Describing & Connecting",
    "V":   "Part V - Sentences, Style & Reference",
}

# Mappa di sinonimi IT/EN -> capitolo (per la ricerca spiegazioni).
# -1 = Appendice A (verbi irregolari), -2 = Appendice B (glossario)
SYNONYMS = {
    "parti del discorso": [2], "parts of speech": [2], "word class": [2],
    "struttura frase": [3], "word order": [3], "ordine parole": [3],
    "soggetto verbo oggetto": [3], "subject verb object": [3], "svo": [3],
    "sostantivi": [4], "nouns": [4], "plurali": [4], "plurals": [4],
    "countable uncountable": [4], "numerabili non numerabili": [4],
    "articoli": [5], "articles": [5], "a an the": [5], "zero article": [5],
    "determiners": [6], "quantificatori": [6], "quantifiers": [6],
    "some any much many": [6], "determinanti": [6],
    "pronomi": [7], "pronouns": [7], "possessivi": [7], "possessives": [7],
    "present simple": [8], "present continuous": [8],
    "presente semplice": [8], "presente continuo": [8], "present tenses": [8],
    "past simple": [9], "past continuous": [9], "passato semplice": [9],
    "past tenses": [9], "used to": [9],
    "present perfect": [10], "past perfect": [10], "perfect tenses": [10],
    "aspetto": [10], "aspect": [10], "for since": [10],
    "futuro": [11], "future": [11], "will": [11], "going to": [11],
    "future continuous": [11], "future perfect": [11],
    "sistema tempi verbali": [12], "tense system": [12], "tutti i tempi": [12],
    "modali": [13], "modal verbs": [13], "can could": [13], "must should": [13],
    "may might": [13], "obbligo": [13], "permesso": [13],
    "passivo": [14], "passive voice": [14], "passive": [14],
    "condizionali": [15], "conditionals": [15], "if clauses": [15],
    "periodo ipotetico": [15], "second conditional": [15], "third conditional": [15],
    "wish": [15], "unreal": [15],
    "discorso indiretto": [16], "reported speech": [16], "direct speech": [16],
    "gerundio": [17], "infinito": [17], "gerunds infinitives": [17],
    "gerund or infinitive": [17], "verb patterns": [17],
    "phrasal verbs": [18], "phrasal": [18], "verbi frasali": [18],
    "aggettivi": [19], "avverbi": [19], "adjectives adverbs": [19],
    "adjective order": [19], "adverbs": [19], "adjectives": [19],
    "comparativi": [20], "superlativi": [20], "comparatives superlatives": [20],
    "as as": [20], "comparison": [20],
    "preposizioni": [21], "prepositions": [21], "in on at": [21],
    "congiunzioni": [22], "conjunctions": [22], "linking words": [22],
    "connettivi": [22],
    "relative clauses": [23], "proposizioni relative": [23],
    "who which that": [23], "defining non-defining": [23],
    "domande": [24], "questions": [24], "negazioni": [24], "negatives": [24],
    "question tags": [24], "short answers": [24],
    "punteggiatura": [25], "punctuation": [25], "maiuscole": [25],
    "capitalization": [25], "common mistakes": [25], "errori comuni": [25],
    "verbi irregolari": [-1], "irregular verbs": [-1], "irregular": [-1],
    "glossario": [-2], "glossary": [-2], "grammar terms": [-2],
}


# ------------------------------------------------------------------- pulizia
def strip_running_headers(lines):
    """Rimuove intestazioni di pagina in maiuscolo e numeri di pagina isolati."""
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append(ln)
            continue
        # numero di pagina isolato
        if re.fullmatch(r"\d{1,3}", s):
            continue
        up = s.upper()
        # running header: contiene em-dash, è tutto maiuscolo, è lungo,
        # e contiene una parola chiave dei titoli di pagina
        letters = re.sub(r"[^A-Za-z]", "", s)
        if ("—" in s or "–" in s) and len(letters) > 12 and letters == letters.upper():
            kw = ("CHAPTER", "APPENDIX", "INTRODUCTION", "PART")
            if any(k in up for k in kw):
                continue
        # riga letter-spaced (es. "C H A P T E R 1 4 — T H E ...", anche con cifre)
        toks = s.split()
        if len(toks) >= 6 and all(re.fullmatch(r"[A-Z\d]{1,2}|—|·", t) for t in toks):
            continue
        # divider "PART I · THE FOUNDATIONS OF GRAMMAR"
        if re.match(r"^[A-Z ]{3,12}·[A-Z ]{3,60}$", s):
            continue
        out.append(ln)
    return out


def fix_hyphenation(text):
    """Unisce le parole spezzate con trattino di a-capo (U+2010 / soft hyphen)."""
    for h in SOFT_HYPHENS:
        text = re.sub(h + r"[ \t]*\n[ \t]*([a-zà-ÿ])", r"\1", text)
        text = text.replace(h + "\n", "\n")
    return text


STRUCT_START = re.compile(
    r"^(?:"
    r"[•]\s*|"
    r"- |"
    r"\d{1,2}\.\s|"
    r"[A-D]\.\s|"
    r"[✓✗]\s*|"
    r"Chapter \d+ — |"
    r"Appendix [AB] — |"
    r"(?:Rule|Tip|Remember|Watch out|Common mistake|Quick Review|Practice|"
    r"Answers|Notes|Good to know|Quick test|Note)\b"
    r")"
)


STANDALONE_HEADERS = {"Practice", "Answers", "Quick Review", "Notes", "VERBS"}


def rebuild_paragraphs(text):
    """Ricostruisce blocchi: unisce le righe della stessa riga tipografica,
    forzando il ritorno a capo prima degli elementi strutturati e rendendo
    autonomi gli header di sezione (Practice, Answers, ...)."""
    out_blocks, current = [], []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            if current:
                out_blocks.append(" ".join(current))
                current = []
            continue
        if current and (STRUCT_START.match(s) or len(" ".join(current)) > 600):
            out_blocks.append(" ".join(current))
            current = [s]
        else:
            current.append(s)
        if s in STANDALONE_HEADERS:
            out_blocks.append(" ".join(current))
            current = []
    if current:
        out_blocks.append(" ".join(current))
    return "\n\n".join(out_blocks)


def clean(raw_text):
    lines = strip_running_headers(raw_text.split("\n"))
    lines = [l.rstrip() for l in lines]
    text = fix_hyphenation("\n".join(lines))
    # versione 'lineare': solo intestazioni e sillabazione, per il parsing
    # di glossario e verbi che si basano su riga iniziale di ciascuna voce
    text_linear = fix_hyphenation("\n".join(
        [l.strip() for l in strip_running_headers(raw_text.split("\n"))]))
    text = rebuild_paragraphs(text)
    text = re.sub(r"[ \t]+", " ", text)
    text_linear = re.sub(r"[ \t]+", " ", text_linear)
    return text, text_linear


# ------------------------------------------------------- estrazione capitoli
def split_chapters(text):
    """{num: (start, end)} usando l'ultima occorrenza del marker di capitolo."""
    bounds = {}
    for num, _t, _p in CHAPTERS:
        m = list(re.finditer(rf"^Chapter {num} — .*$", text, re.MULTILINE))
        if m:
            bounds[num] = m[-1].start()
    ordered = sorted(bounds.items(), key=lambda kv: kv[1])
    ranges = {}
    for i, (num, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(text)
        ranges[num] = (start, end)
    return ranges


def get_chapter_title(text, start):
    seg = text[start:start + 180]
    lines = [l for l in seg.split("\n") if l.strip()][:3]
    title = re.sub(r"^Chapter \d+ —\s*", "", lines[0]).strip()
    for extra in lines[1:]:
        if (len(extra) <= 42 and len(extra.split()) <= 5
                and not re.search(r"[.!?]$", extra)
                and not extra.startswith(("Every ", "Welcome", "Grammar has"))):
            title += " " + extra.strip()
        else:
            break
    return title.strip()


# ------------------------------------------------------ estrazione esempi ✓✗
EXAMPLE_OK = re.compile(r'✓\s+([A-Z“\'"][^✓✗\n]{8,140}?[.!?])')
EXAMPLE_BAD = re.compile(r'✗\s+([A-Z“\'"][^✓✗\n]{8,140}?[.!?])')
JUNK_WORDS = ("examples show", "marks ", "the rule in action")


def _clean_example(s):
    s = " ".join(s.split())
    low = s.lower()
    if any(j in low for j in JUNK_WORDS):
        return None
    if "_" in s or "|" in s or "→" in s:
        return None
    if len(s.split()) < 3:
        return None
    if re.fullmatch(r"[A-Z\s\d.,]{4,}", s):
        return None
    # parentesi non bilanciate (residui di tabella)
    if s.count("(") != s.count(")"):
        return None
    return s


def extract_examples(ch_text):
    ok, bad = [], []
    for m in EXAMPLE_OK.finditer(ch_text):
        s = _clean_example(m.group(1))
        if s:
            ok.append(s)
    for m in EXAMPLE_BAD.finditer(ch_text):
        s = _clean_example(m.group(1))
        if s:
            bad.append(s)
    return ok, bad


# --------------------------------------------------------- coppie ✗ X -> ✓ Y
FIX_PAIR = re.compile(
    r"✗\s*([^\n✓✗→]{4,110}?)\s*→\s*✓\s*([^\n✓✗]{4,110}?)(?=[.;)\n]|$)")


_NOTE_RE = re.compile(
    r"\s+(Error|Mistake|Note|Tip|Watch out|Remember|Common mistake|"
    r"Quick test|Quick Review)\b", re.I
)


def _strip_note(s):
    m = _NOTE_RE.search(s)
    if m:
        return s[: m.start()].strip()
    return s.strip()


def extract_fixes(ch_text):
    fixes = []
    for m in FIX_PAIR.finditer(ch_text):
        bad, good = m.group(1).strip(), m.group(2).strip()
        bad = bad.rstrip(" -–—.(").strip()
        good = good.rstrip(" -–—( ").strip()
        bad = _strip_note(bad)
        good = _strip_note(good)
        if "/" in bad or "*" in bad or "/" in good or "*" in good:
            continue
        if len(bad.split()) < 1 or len(good.split()) < 2:
            continue
        if bad == good or not good[0].isupper():
            continue
        if len(good) > 80 or len(bad) > 80:
            continue
        fixes.append({"bad": bad, "good": good})
    return fixes


# ---------------------------------------------- parsing Practice + Answers
def parse_numbered(text):
    """Estrae gli item in ordine dai marcatori 'N.'. La catena parte dal primo
    numero incontrato (la numerazione può ripartire per gruppo o essere
    continua) e prosegue solo se consecutiva; i numeri fuori sequenza
    (pagine, riferimenti tipo 'Chapter 10.') vengono ignorati."""
    items, pos = [], 0
    expected = None
    pattern = re.compile(r"(?:^|\s)(\d{1,2})\.\s")
    while True:
        m = pattern.search(text, pos)
        if not m:
            break
        n = int(m.group(1))
        if expected is None:
            expected = n
            nxt = pattern.search(text, m.end())
            items.append(" ".join(
                text[m.end(): nxt.start() if nxt else len(text)].split()))
        elif n == expected + 1:
            expected = n
            nxt = pattern.search(text, m.end())
            items.append(" ".join(
                text[m.end(): nxt.start() if nxt else len(text)].split()))
        pos = m.end()
    return items


def parse_answers(answers_text):
    """Risposte ufficiali: accetta numerazione continua o riavvii per gruppo
    (n == precedente+1, oppure n == 1 che fa ripartire la catena)."""
    items, pos, last = [], 0, None
    pattern = re.compile(r"(?:^|\s)(\d{1,2})\.\s")
    while True:
        m = pattern.search(answers_text, pos)
        if not m:
            break
        n = int(m.group(1))
        if last is None or n == last + 1 or n == 1:
            nxt = pattern.search(answers_text, m.end())
            items.append(" ".join(
                answers_text[m.end(): nxt.start() if nxt else len(answers_text)].split()))
            last = n
        pos = m.end()
    return items


def parse_groups(practice_text):
    """Divide il Practice nei gruppi A./B./C./D.: istruzione + item.
    Se non ci sono etichette di gruppo, tutto il testo è un gruppo unico."""
    groups = []
    parts = re.split(r"(?:^|\s)([A-F])\.\s", "\n" + practice_text.strip())
    i = 1
    while i < len(parts) - 1:
        letter, body = parts[i], parts[i + 1]
        body = " ".join(body.split())
        m = re.search(r"(?:^|\s)(\d{1,2})\.\s", body)
        if m:
            instr, items_text = body[: m.start()].strip(), body[m.start():]
        else:
            instr, items_text = body, ""
        groups.append({"letter": letter, "instr": instr,
                       "items": parse_numbered(items_text) if items_text else []})
        i += 2
    if not groups:
        body = " ".join(practice_text.strip().split())
        m = re.search(r"(?:^|\s)(\d{1,2})\.\s", body)
        instr = body[: m.start()].strip() if m else body
        items_text = body[m.start():] if m else ""
        groups.append({"letter": "", "instr": instr,
                       "items": parse_numbered(items_text) if items_text else []})
    return groups


def options_from_instruction(instr):
    """Opzioni dichiarate nell'istruzione: 'Write C for ... or F for ...'
    oppure '(SV, SVO, SVC, SVOO, or SVOC)'."""
    opts = []
    m = re.search(r"[Ww]rite ([A-Z]) for[^,.]{0,60} or ([A-Z]) for", instr)
    if m:
        opts = [m.group(1), m.group(2)]
    if not opts:
        m = re.search(r"\(([A-Z]{1,6}(?:,\s*[A-Z]{1,6})+),?\s+or\s+([A-Z]{1,6})\)",
                      instr)
        if m:
            opts = [o.strip() for o in m.group(1).split(",")] + [m.group(2).strip()]
    return opts


def options_from_item(item):
    """Opzioni tra parentesi dentro l'item: 'The cat (sit / sits) on ...'."""
    m = re.search(r"\(([A-Za-z][A-Za-z\'’ ]*?(?:\s*/\s*[A-Za-z][A-Za-z\'’ ]*?)+)\)",
                  item)
    if not m:
        return None
    opts = [o.strip() for o in m.group(1).split("/")]
    if not (2 <= len(opts) <= 4) or any(len(o) > 22 or not o for o in opts):
        return None
    if "___" in item:
        # il libro usa già le lacune: togli solo la parentesi, niente doppia lacuna
        q = (item[:m.start()] + item[m.end():]).strip()
    else:
        q = (item[:m.start()] + "_____" + item[m.end():]).strip()
    q = re.sub(r"_{2,}(?:\s*_{2,})+", "_____", q)  # collassa lacune adiacenti
    return {"options": opts, "question": " ".join(q.split())}


def match_option(answer_text, options):
    """Trova quale opzione compare nella risposta ufficiale del libro."""
    low = answer_text.lower()
    hits = []
    for i, o in enumerate(options):
        if re.search(r"(?<![a-z])" + re.escape(o.lower()) + r"(?![a-z])", low):
            hits.append(i)
    return hits


def build_exercises(ch_num, practice_text, answers_text):
    """Abbina item del Practice e risposte in ordine; tenta la conversione MCQ."""
    answers = parse_answers(answers_text)
    groups = parse_groups(practice_text)
    flat = [(g["letter"], g["instr"], it) for g in groups for it in g["items"]]
    exercises = []
    if not answers or len(answers) != len(flat):
        return exercises, len(flat), len(answers)
    for (letter, instr, item), ans in zip(flat, answers):
        ex = {"ch": ch_num, "group": letter, "instr": instr, "q": item,
              "options": None, "answer": ans, "answer_idx": None}
        opts = options_from_item(item)
        if not opts:
            io = options_from_instruction(instr)
            if io:
                opts = {"options": io, "question": item}
        if opts:
            hits = match_option(ans, opts["options"])
            if len(hits) == 1:
                ex["options"] = opts["options"]
                ex["answer_idx"] = hits[0]
                ex["q"] = opts["question"]
        ans_clean = re.sub(r"\s+[A-F](?:\s+[A-F])?\.?$", "", ans).strip()
        ex["answer"] = ans_clean
        exercises.append(ex)
    return exercises, len(flat), len(answers)


# ------------------------------------------------------------ appendice A/B
VERB_OK = re.compile(r"[a-z][a-z' -]{1,24}")
PHRASAL_BASES = ("out", "up", "down", "off", "on", "in", "over", "away", "around")
NOTE_HINTS = ("only", "also", "ame", "bre", "regular", "not ", "used ",
              "passive", "usually", "often", "both", "same", "no ", "rare")


def parse_verbs(appx_text):
    """Estrae le triple base-past-participle dalla tabella verbi irregolari.
    Le celle sono separate da righe vuote nel testo lineare; una cella con
    più parole è una nota e viene scartata per mantenere l'allineamento."""
    verbs, buf = {}, []
    cells = [c.strip() for c in re.split(r"\n[ \t]*\n", appx_text) if c.strip()]
    headers = {"base form", "past simple", "past participle", "notes", "verbs",
               "note", "form", "simple", "participle"}
    for cell in cells:
        low = cell.lower()
        if low in headers:
            continue
        if cell.startswith(("Pattern Group", "Appendix", "Each verb",
                            "Most English", "Irregular verbs", "English has")):
            continue
        if re.fullmatch(r"[A-Z\s\d]{3,}", cell):
            continue
        # rimuovi le parentesi tonde e il loro contenuto: "born (bear)" -> "born"
        cleaned = re.sub(r"\([^)]*\)", "", cell).strip()
        low = cleaned.lower()
        if not re.fullmatch(r"[a-z][a-z'-]{1,20}", low):
            continue  # nota o testo: scarta (protegge l'allineamento)
        buf.append(low)
        if len(buf) == 3:
            base, past, part = buf
            verbs.setdefault(base, [past, part])
            buf = []
    return verbs


LAYOUT_ROW = re.compile(
    r"^\s*([a-z][a-z'\-/ ]{1,22}?)\s{2,}"
    r"([a-z][a-z'\-/ ]{1,22}?)\s{2,}"
    r"([a-z][a-z'\-/ ]{1,22}?)"
    r"(?:\s{2,}(.+))?\s*$")


def extract_verbs_layout(pdf_path, first_page=315, last_page=331):
    """Estrae i verbi con pdftotext -layout, che preserva le colonne della
    tabella. Ritorna None se pdftotext non è disponibile o non trova righe."""
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", "-f", str(first_page), "-l", str(last_page),
             str(pdf_path), "-"],
            capture_output=True, text=True, check=True, timeout=60)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    verbs = {}
    for ln in out.stdout.split("\n"):
        m = LAYOUT_ROW.match(ln)
        if not m:
            continue
        base, past, part = (m.group(i).strip() for i in (1, 2, 3))
        if base in ("base form", "past simple", "past participle"):
            continue
        if " " in base:
            continue
        verbs.setdefault(base, [past, part])
    return verbs if len(verbs) >= 100 else None


def parse_glossary(appx_text):
    """Estrae le voci 'Termine — definizione' dal glossario."""
    entries, cur_term, cur_def = [], None, []
    for ln in appx_text.split("\n"):
        s = ln.strip()
        if not s:
            continue
        if re.fullmatch(r"[A-Z]{1,2}", s):  # lettera di sezione
            continue
        m = re.match(r"^([A-Z][A-Za-z’' ()/-]{1,45}) — (.*)$", s)
        if m and not m.group(1).startswith(("Appendix", "Chapter", "Part")):
            if cur_term:
                entries.append({"term": cur_term,
                                "def": " ".join(" ".join(cur_def).split())})
            cur_term, cur_def = m.group(1).strip(), [m.group(2)]
        elif cur_term:
            cur_def.append(s)
    if cur_term:
        entries.append({"term": cur_term, "def": " ".join(" ".join(cur_def).split())})
    return entries


# -------------------------------------------------------------------- main
def extract_pdf_text(pdf_path):
    try:
        out = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True, text=True, check=True, timeout=120)
        return out.stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("Serve 'pdftotext' (poppler-utils) oppure 'pip install pypdf'.")
    reader = PdfReader(str(pdf_path))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("book.pdf")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/kb.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    raw = extract_pdf_text(pdf)
    text, text_linear = clean(raw)

    appx_a = text.rfind("Appendix A — Irregular Verbs")
    appx_b = text.rfind("Appendix B — Glossary of")
    if appx_a == -1 or appx_b == -1:
        sys.exit("Appendici non trovate: PDF diverso dal previsto?")
    appx_a_lin = text_linear.rfind("Appendix A — Irregular Verbs")
    appx_b_lin = text_linear.rfind("Appendix B — Glossary of")
    body = text[:appx_a]

    ranges = split_chapters(body)
    chapters, examples, fixes, exercises = [], [], [], []
    diag = []

    for num, title, part in CHAPTERS:
        if num not in ranges:
            diag.append(f"ch{num}: MARKER NON TROVATO")
            continue
        start, end = ranges[num]
        ch_text = text[start:end]
        real_title = title  # titolo canonico dal sommario del libro
        ok_ex, bad_ex = extract_examples(ch_text)
        ch_fixes = extract_fixes(ch_text)
        for s in ok_ex:
            examples.append({"t": s, "ok": True, "ch": num})
        for s in bad_ex:
            examples.append({"t": s, "ok": False, "ch": num})
        for f in ch_fixes:
            f["ch"] = num
            fixes.append(f)

        pm = re.search(r"^Practice\s*$\n\n(.*)", ch_text, re.MULTILINE | re.DOTALL)
        n_items = n_ans = 0
        if pm:
            seg = pm.group(1)
            am = re.search(r"\n\n^Answers\s*$\n\n(.*)", seg,
                           re.MULTILINE | re.DOTALL)
            if am:
                exs, n_items, n_ans = build_exercises(
                    num, seg[:am.start()], am.group(1))
                exercises.extend(exs)
        diag.append(
            f"ch{num:2d} '{real_title[:44]}': +{len(ok_ex)} ok, {len(bad_ex)} bad, "
            f"{len(ch_fixes)} fix, esercizi {n_items}/{n_ans}")

        chapters.append({"num": num, "title": real_title, "part": PARTS[part],
                         "text": ch_text})

    verbs = extract_verbs_layout(pdf)
    if verbs is None:
        verbs = parse_verbs(text_linear[appx_a_lin:appx_b_lin])
    glossary = parse_glossary(text_linear[appx_b_lin:])

    kb = {
        "meta": {
            "title": "English Grammar: A Complete Guide (A1-C1)",
            "source": pdf.name,
            "built": str(date.today()),
            "counts": {
                "chapters": len(chapters),
                "examples_ok": sum(1 for e in examples if e["ok"]),
                "examples_bad": sum(1 for e in examples if not e["ok"]),
                "fixes": len(fixes),
                "exercises": len(exercises),
                "exercises_mcq": sum(1 for e in exercises if e["options"]),
                "verbs": len(verbs),
                "glossary": len(glossary),
            },
        },
        "chapters": chapters,
        "examples": examples,
        "fixes": fixes,
        "exercises": exercises,
        "verbs": verbs,
        "glossary": glossary,
        "synonyms": SYNONYMS,
    }
    out_path.write_text(json.dumps(kb, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    c = kb["meta"]["counts"]
    print(f"KB scritta in {out_path} ({out_path.stat().st_size/1024:.0f} KB)")
    print(f"Capitoli: {c['chapters']} | Esempi ok: {c['examples_ok']} "
          f"bad: {c['examples_bad']} | Coppie fix: {c['fixes']}")
    print(f"Esercizi: {c['exercises']} (MCQ: {c['exercises_mcq']})")
    print(f"Verbi irregolari: {c['verbs']} | Glossario: {c['glossary']} voci")
    print("\nDiagnostica per capitolo:")
    for d in diag:
        print(" ", d)


if __name__ == "__main__":
    main()
