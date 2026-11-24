# -*- coding: utf-8 -*-
"""Accesso alla knowledge base (kb.json) e ricerca argomenti senza AI.

La ricerca è deterministica: sinonimi curati IT/EN -> capitolo, poi indice
di parole (titoli, sinonimi, glossario, verbi), infine frequenza di parole
nel testo dei capitoli. Nessuna chiamata a servizi esterni."""
import json
import re
from pathlib import Path

from tutor.content import DEFAULT_CORRECTIONS, prepare_content
from tutor.book_quiz import DEFAULT_NOTES, load_notes
from tutor.editorial import DEFAULT_REVIEW

DEFAULT_KB = Path(__file__).resolve().parent.parent / "data" / "kb.json"

TOKEN_RE = re.compile(r"[a-zà-ÿ']{3,}")


def load_kb(path=None, corrections_path=DEFAULT_CORRECTIONS, review_path=DEFAULT_REVIEW,
            notes_path=DEFAULT_NOTES):
    p = Path(path) if path else DEFAULT_KB
    with open(p, encoding="utf-8") as f:
        kb = json.load(f)
    prepare_content(kb, corrections_path, review_path)
    kb["_notes_it"] = load_notes(kb, notes_path) if notes_path is not None else {
        "exercises": {}, "items": {}, "sections": {}}
    kb["_chapters"] = {c["num"]: c for c in kb["chapters"]}
    kb["_by_title_words"] = {}
    kb["_word_index"] = {}   # parola -> {capitolo: peso}
    kb["_syn_sorted"] = sorted(kb["synonyms"].items(), key=lambda kv: -len(kv[0]))
    for num, c in kb["_chapters"].items():
        for w in TOKEN_RE.findall(c["title"].lower()):
            kb["_word_index"].setdefault(w, {}).setdefault(num, 3.0)
    for key, chs in kb["synonyms"].items():
        for w in TOKEN_RE.findall(key):
            for num in chs:
                d = kb["_word_index"].setdefault(w, {})
                d[num] = max(d.get(num, 0), 2.0)
    for g in kb["glossary"]:
        for w in TOKEN_RE.findall(g["term"].lower()):
            d = kb["_word_index"].setdefault(w, {})
            d[-2] = max(d.get(-2, 0), 2.0)
    for v in kb["verbs"]:
        kb["_word_index"].setdefault(v, {})[-1] = 2.5
    return kb


def _norm(q):
    return " ".join(re.sub(r"[^a-zà-ÿ' 0-9]", " ", q.lower()).split())


def search(kb, query):
    """Ritorna (risultato, etichetta). risultato: ('chapter', num) |
    ('verbs', None) | ('glossary', None) | ('none', None)."""
    q = _norm(query)
    if not q:
        return ("none", None), "empty"

    # casi speciali: un solo token (anche corto) che è un verbo, un termine di
    # glossario, o un argomento breve noto
    single = q.split()
    if len(single) == 1:
        w = single[0]
        hit = verb_lookup(kb, w)
        if hit:
            return ("verbs", hit[0]), "verbi-corto"
        if w == "if":
            return ("chapter", 15), "sinonimi"
        for g in kb["glossary"]:
            if w == g["term"].lower():
                return ("glossary", None), "glossario-corto"

    # 1) sinonimo più lungo contenuto nella domanda
    for key, chs in kb["_syn_sorted"]:
        if key in q:
            num = chs[0]
            if num == -1:
                return ("verbs", None), "sinonimi"
            if num == -2:
                return ("glossary", None), "sinonimi"
            return ("chapter", num), "sinonimi"

    toks = TOKEN_RE.findall(q)

    # 2) verbo irregolare citato esplicitamente in una domanda corta
    if len(toks) <= 3:
        for t in toks:
            if t in kb["verbs"]:
                return ("verbs", t), "verbi"

    # 3) indice di parole (titoli, sinonimi, glossario)
    votes = {}
    for t in toks:
        for num, w in kb["_word_index"].get(t, {}).items():
            votes[num] = votes.get(num, 0.0) + w
    if votes:
        best = max(votes.items(), key=lambda kv: kv[1])
        if best[1] >= 2.0:
            num = best[0]
            if num == -1:
                return ("verbs", None), "indice"
            if num == -2:
                return ("glossary", None), "indice"
            return ("chapter", num), "indice"

    # 4) frequenza nel testo dei capitoli
    scores = {}
    for t in toks:
        for num, c in kb["_chapters"].items():
            n = c["text"].lower().count(t)
            if n:
                scores[num] = scores.get(num, 0.0) + min(n, 15) * 0.2
    if scores:
        best = max(scores.items(), key=lambda kv: kv[1])
        if best[1] >= 1.5:
            return ("chapter", best[0]), "testo"
    # fallback: la query è contenuta nel titolo di un capitolo
    for num, c in kb["_chapters"].items():
        if q in c["title"].lower():
            return ("chapter", num), "titolo"
    return ("none", None), "nessuna"


def verb_lookup(kb, word):
    """Cerca una forma tra base, past e participio. Ritorna (base, [past, part])
    oppure None."""
    w = word.strip().lower()
    if w in kb["verbs"]:
        return w, kb["verbs"][w]
    for base, forms in kb["verbs"].items():
        for f in forms:
            for part in f.split("/"):
                part = part.strip()
                if part == w:
                    return base, forms
    return None


def glossary_search(kb, query, limit=12):
    """Normalizzazione simmetrica e precedenza alla voce esatta."""
    q = _norm(query)
    if not q or limit <= 0:
        return []
    terms = [(i, _norm(g['term'])) for i,g in enumerate(kb['glossary'])]
    exact = [i for i,t in terms if q == t]
    hits = exact or [i for i,t in terms if q in t or t in q]
    return hits[:limit]


THEORY_STOP = ("Practice", "Answers")
RULE_WORDS = ("Rule:", "Remember:", "Common mistake", "Watch out", "Tip:", "Good to know",
              "Quick test", "Note —", "Key idea")


def _theory_blocks(kb, num):
    """Blocchi di teoria del capitolo (con la formattazione del libro), senza esercizi/soluzioni."""
    out = []
    for b in kb["_chapters"][num].get("blocks", []):
        if b["type"] == "heading" and b["text"].strip() in THEORY_STOP:
            break
        out.append(b)
    return out


def _block_html(b):
    from tutor.render import tidy_html
    html = tidy_html(b.get("html") or "")
    if b["type"] == "bullet":
        return "• " + html
    return html


def chapter_pages(kb, num, size=3500):
    """Teoria completa del capitolo in pagine HTML (Telegram) da <= size caratteri."""
    blocks = _theory_blocks(kb, num)
    if not blocks:
        from html import escape
        return paginate(escape(kb["_chapters"][num]["text"], quote=False), size)
    return paginate_html([_block_html(b) for b in blocks], size)


def explain_summary(kb, num, size=3500):
    """Sintesi del capitolo: introduzione, riquadri regola/errore ed esempi del libro."""
    from tutor.render import example_html
    keep, intro_len = [], 0
    for b in _theory_blocks(kb, num):
        if len(b["text"]) > 900:
            continue
        if b["text"].startswith(RULE_WORDS):
            keep.append(_block_html(b))
        elif intro_len < 700 and b["type"] in ("para", "heading"):
            keep.append(_block_html(b))
            intro_len += len(b["text"])
    book = [e for e in kb["examples"] if e["ch"] == num and e.get("quiz_eligible", True)]
    ok = [e for e in book if e["ok"]][:4]
    bad = [e for e in book if not e["ok"]][:2]
    if ok:
        keep.append("<b>Examples from this chapter:</b>\n" + "\n".join("✓ " + example_html(e) for e in ok))
    if bad:
        keep.append("<b>Common mistakes:</b>\n" + "\n".join("✗ " + example_html(e) for e in bad))
    return paginate_html(keep, size)


def paginate_html(blocks, size=3500):
    """Pagine a confini di blocco: un tag HTML non viene mai spezzato."""
    from html import escape
    import re as _re
    pages, cur = [], ""
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if len(block) > size:
            # caso limite: blocco enorme → testo semplice spezzato (nessun tag da rompere)
            plain = escape(_re.sub(r"<[^>]+>", "", block).replace("&lt;", "<").replace("&gt;", ">")
                           .replace("&amp;", "&"), quote=False)
            if cur:
                pages.append(cur)
                cur = ""
            pages.extend(plain[i:i + size] for i in range(0, len(plain), size))
            continue
        if cur and len(cur) + len(block) + 2 > size:
            pages.append(cur)
            cur = block
        else:
            cur = (cur + "\n\n" + block) if cur else block
    if cur:
        pages.append(cur)
    return pages or [""]


def paginate(text, size=3600):
    """Spezza il testo a confini di paragrafo in pagine <= size caratteri."""
    pages, cur = [], ""
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if len(block) > size:
            if cur:
                pages.append(cur)
                cur = ""
            for i in range(0, len(block), size):
                pages.append(block[i:i + size])
            continue
        if cur and len(cur) + len(block) + 2 > size:
            pages.append(cur)
            cur = block
        else:
            cur = (cur + "\n\n" + block) if cur else block
    if cur:
        pages.append(cur)
    return pages
