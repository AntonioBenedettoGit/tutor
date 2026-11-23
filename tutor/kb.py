# -*- coding: utf-8 -*-
"""Accesso alla knowledge base (kb.json) e ricerca argomenti senza AI.

La ricerca è deterministica: sinonimi curati IT/EN -> capitolo, poi indice
di parole (titoli, sinonimi, glossario, verbi), infine frequenza di parole
nel testo dei capitoli. Nessuna chiamata a servizi esterni."""
import json
import re
from pathlib import Path

from tutor.content import DEFAULT_CORRECTIONS, prepare_content
from tutor.editorial import DEFAULT_REVIEW

DEFAULT_KB = Path(__file__).resolve().parent.parent / "data" / "kb.json"

TOKEN_RE = re.compile(r"[a-zà-ÿ']{3,}")


def load_kb(path=None, corrections_path=DEFAULT_CORRECTIONS, review_path=DEFAULT_REVIEW):
    p = Path(path) if path else DEFAULT_KB
    with open(p, encoding="utf-8") as f:
        kb = json.load(f)
    prepare_content(kb, corrections_path, review_path)
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


def chapter_pages(kb, num, size=3600):
    """Testo completo del capitolo in pagine da <= size caratteri."""
    text = kb["_chapters"][num]["text"]
    return paginate(text, size)


def explain_summary(kb, num, size=3600):
    """Sintesi del capitolo: introduzione + box regole/errori + esempi."""
    blocks = kb["_chapters"][num]["text"].split("\n\n")
    keep = []
    intro_len = 0
    rule_words = ("Rule:", "Remember:", "Common mistake", "Watch out",
                  "Tip:", "Good to know", "Quick test", "Note —")
    for b in blocks:
        if len(b) > 900:
            continue
        if any(b.startswith(w) for w in rule_words):
            keep.append(b)
        elif intro_len < 700 and not b.startswith(("Chapter", "Practice",
                                                   "Answers", "Quick Review")):
            keep.append(b)
            intro_len += len(b)
    # Solo esempi TF revisionati nelle liste riepilogative.
    reviewed = [e for e in kb.get("_reviewed_quiz", [])
                if e["ch"] == num and e["type"] == "tf"]
    ex_ok = [e["t"] for e in reviewed if e["ok"]][:4]
    ex_bad = [e["t"] for e in reviewed if not e["ok"]][:2]
    if ex_ok:
        keep.append("Examples from this chapter:\n" +
                    "\n".join("✓ " + e for e in ex_ok))
    if ex_bad:
        keep.append("Common mistakes:\n" +
                    "\n".join("✗ " + e for e in ex_bad))
    summary = "\n\n".join(keep)
    return paginate(summary, size)


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
