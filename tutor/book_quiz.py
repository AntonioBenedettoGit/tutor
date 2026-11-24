"""Fase 4.3: quiz ed esercizi dal libro, con punteggio.

- Il pool del quiz usa gli esempi ✓/✗, le coppie ✗ → ✓ e le scelte multiple del libro.
- Gli esercizi si correggono in automatico quando la soluzione del libro è breve; per le
  riscritture e le risposte libere si mostra la soluzione e lo studente si autovaluta.
- Il contenuto del libro non viene corretto: si mostra la versione originale. La nota in
  italiano (data/notes_it.json) affianca la spiegazione del libro, non la sostituisce.
"""
import json
from pathlib import Path
import random
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NOTES = ROOT / 'data' / 'notes_it.json'
QUIZ_SIZE = 10
ZERO = '—'

# Sinonimi italiani per le risposte-etichetta del libro (parti del discorso, ecc.).
LABELS = {
    'noun': ['sostantivo', 'nome'], 'verb': ['verbo'], 'adjective': ['aggettivo'],
    'adverb': ['avverbio'], 'preposition': ['preposizione'], 'conjunction': ['congiunzione'],
    'interjection': ['interiezione', 'esclamazione'], 'determiner': ['determinante'],
    'pronoun': ['pronome'], 'article': ['articolo'],
    'phrase': ['sintagma', 'gruppo di parole'], 'clause': ['proposizione'],
    'u': ['uncountable', 'non numerabile', 'non contabile', 'uncountable noun'],
    'c': ['countable', 'numerabile', 'contabile', 'countable noun'],
    'no comma': ['nessuna virgola', 'senza virgola', 'no'],
    'no': ['non si può', 'non può essere omesso'], 'yes': ['si', 'sì'],
    'intransitive': ['intransitivo'], 'separable': ['separabile'], 'inseparable': ['inseparabile'],
    'three-part': ['tre parti', 'three part'],
}
ZERO_VARIANTS = ['—', '-', '–', 'x', '0', '/', 'no article', 'nessun articolo', 'niente', 'nothing',
                 'zero', 'zero article', 'none', 'nessuno', 'ø', '∅']
CONTRACTIONS = [
    (r"\bwon't\b", 'will not'), (r"\bcan't\b", 'cannot'), (r"\bshan't\b", 'shall not'),
    (r"n't\b", ' not'), (r"'m\b", ' am'), (r"'re\b", ' are'), (r"'ve\b", ' have'),
    (r"'ll\b", ' will'), (r"\blet's\b", 'let us'),
]


# --------------------------------------------------------------------------- note italiane
def load_notes(kb, path=DEFAULT_NOTES):
    """Note in italiano: per esercizio, per singolo esempio/coppia, o per sezione del capitolo.
    Fail-closed: ogni chiave deve esistere nella KB, nessuna nota vuota."""
    path = Path(path)
    if not path.exists():
        return {'exercises': {}, 'items': {}, 'sections': {}}
    doc = json.loads(path.read_text(encoding='utf-8'))
    if doc.get('schema_version') != 1:
        raise ValueError('Note IT: versione non supportata')
    ex_ids = {e['source_id'] for e in kb['exercises']}
    item_ids = {e['id'] for e in kb['examples']} | {f['id'] for f in kb['fixes']}
    sections = {section_key(e) for e in kb['examples'] + kb['fixes']}
    notes = {'exercises': doc.get('exercises', {}), 'items': doc.get('items', {}),
             'sections': doc.get('sections', {})}
    for kind, valid in (('exercises', ex_ids), ('items', item_ids), ('sections', sections)):
        for key, text in notes[kind].items():
            if key not in valid:
                raise ValueError(f'Note IT: chiave sconosciuta in {kind}: {key}')
            if not isinstance(text, str) or not text.strip() or len(text) > 600:
                raise ValueError(f'Note IT: nota vuota o troppo lunga: {key}')
    return notes


def section_key(item):
    return f"{item['ch']}|{item['section']}"


def note_for(kb, item, kind):
    notes = kb.get('_notes_it') or {}
    if kind == 'exercise':
        return notes.get('exercises', {}).get(item['source_id'], '')
    return notes.get('items', {}).get(item['id']) or notes.get('sections', {}).get(section_key(item), '')


# --------------------------------------------------------------------------- confronto risposte
def norm(text):
    text = unicodedata.normalize('NFKC', text or '').lower()
    text = text.replace('’', "'").replace('‘', "'").replace('`', "'")
    text = re.sub(r'[“”"«»]', '', text)
    text = text.replace('…', ' ').replace('...', ' ')
    text = re.sub(r'^\s*[✓✔]\s*', '', text)
    text = re.sub(r"[^\w'/—–-]+", ' ', text)
    return ' '.join(text.split())


def _strip_quotes(t):
    return ' '.join(re.sub(r"(?<!\w)'|'(?!\w)", ' ', t).split())   # apostrofi isolati, non don't


def expand(text):
    """Forma confrontabile: minuscole, senza punteggiatura, contrazioni sciolte (I'm → I am)."""
    t = norm(text)
    for pattern, repl in CONTRACTIONS:
        t = re.sub(pattern, repl, t)
    t = re.sub(r"\b(it|he|she|that|there|what|who|where|here)'s\b", r"\1 is", t)
    t = re.sub(r"(?<!\w)'s\b", ' is', t)
    t = re.sub(r"(?<!\w)'d\b", ' would', t)
    return _strip_quotes(t)


def _alternatives(core):
    """Forme accettate a partire dalla soluzione del libro (solo ciò che il libro scrive)."""
    out = {core}
    for sep in (' / ', ' or '):
        for c in list(out):
            if sep in c:
                out.update(p.strip() for p in c.split(sep) if p.strip())
    for c in list(out):
        if '(' in c:
            out.add(re.sub(r'\s*\([^()]*\)', '', c))              # parte facoltativa: The book (that) I read
            out.add(re.sub(r'[()]', '', c))
            out.add(re.sub(r'([\w-]+) \(([\w-]+)\)', r'\2', c))     # farther (further): parola alternativa
        m = re.fullmatch(r'(\d+)\s+—\s+(.+)', c)                    # «1 — intransitive»
        if m:
            out.update([m[1], m[2]])
        if ' — ' in c and c.split(' — ')[0].strip():
            out.add(c.split(' — ')[0].strip())
    for c in list(out):
        key = norm(c).rstrip('.')
        out.update(LABELS.get(key, []))
    return {a for a in out if norm(a)}


def _fill(question, typed):
    """Mette la risposta nella frase: «Are you afraid ____ the dark?» + «of».
    Ritorna le frasi candidate (più d'una se due spazi e risposta senza «…»)."""
    q = re.sub(r'\((?:[^()]*?)\)\s*$', '', question).strip()
    q = re.sub(r'\s*\((?!\s*(?:BrE|AmE))[^()]*\)', '', q)                # suggerimenti (sing), (not / finish)
    gaps = list(re.finditer(r'_{1,}', q))
    if not gaps:
        return []
    pieces = [p.strip() for p in re.split(r'\s*(?:…|\.\.\.)\s*', typed) if p.strip()]
    options = [pieces]
    if len(gaps) == 2 and len(pieces) == 1:
        words = pieces[0].split()
        options = [[' '.join(words[:k]), ' '.join(words[k:])] for k in range(1, len(words))]
    out = []
    for parts in options:
        text, last = [], 0
        for i, g in enumerate(gaps):
            text.append(q[last:g.start()])
            text.append(parts[i] if i < len(parts) else '')
            last = g.end()
        text.append(q[last:])
        out.append(''.join(text))
    return out


def check_answer(e, typed):
    """True se la risposta digitata coincide con la soluzione del libro (forme ammesse dal libro)."""
    core = e.get('answer_core', '')
    if not typed or not typed.strip() or not core:
        return False
    if core == ZERO:
        return norm(typed) in {norm(v) for v in ZERO_VARIANTS + e.get('answer_variants', [])} or typed.strip() in ZERO_VARIANTS
    t = expand(typed).rstrip('.')
    accepted = {expand(a).rstrip('.') for a in _alternatives(core)}
    accepted |= {expand(v).rstrip('.') for v in e.get('answer_variants', []) if v != ZERO}
    if t in accepted or t.replace(' / ', ' ').replace('/', ' ') in {a.replace(' / ', ' ').replace('/', ' ') for a in accepted}:
        return True
    q = e.get('source_q') or e.get('q') or ''
    for filled in _fill(q, typed):
        f = expand(filled).rstrip('.')
        for a in accepted:
            if len(a.split()) >= 2 and (a == f or a in f):
                return True
            if any(expand(full).rstrip('.') == f for full in _fill(q, a)):
                return True
    # frase intera scritta dallo studente: deve coincidere con la frase completata dal libro
    if len(t.split()) >= 3:
        for a in accepted:
            if any(expand(full).rstrip('.') == t for full in _fill(q, a)):
                return True
    # due spazi, una risposta sola senza «…»: «mix get» per «mix … get»
    if ' … ' in core and expand(core.replace(' … ', ' ')).rstrip('.') == t:
        return True
    return False


def check_parts(e, typed):
    """Esercizi a parti a)–e): una risposta per riga (o «a) …» in ordine). Ritorna [(label, ok)]."""
    parts = e.get('parts') or []
    lines = [l.strip() for l in re.split(r'\n|;', typed or '') if l.strip()]
    labelled = {}
    for l in lines:
        m = re.match(r'^([a-e])[).:\-]\s*(.+)$', l, flags=re.I)
        if m:
            labelled[m[1].lower()] = m[2]
    if not labelled and len(lines) == 1 and len(parts) > 1:
        lines = [p.strip() for p in lines[0].split(',') if p.strip()]
    result = []
    for i, p in enumerate(parts):
        answer = labelled.get(p['label'].lower()) or (lines[i] if not labelled and i < len(lines) else '')
        sub = {'answer_core': p['answer_core'], 'source_q': p['q'], 'answer_variants': []}
        result.append((p['label'], answer, check_answer(sub, answer)))
    return result


# --------------------------------------------------------------------------- pool del quiz
def _pair_texts(kb):
    texts = set()
    for f in kb['fixes']:
        texts.add((f['ch'], _strip_quotes(norm(f['bad']))))
        texts.add((f['ch'], _strip_quotes(norm(f['good']))))
    return texts


def quiz_items(kb, chapter=None):
    """Tutte le domande possibili dal libro, senza tetti per capitolo."""
    paired = _pair_texts(kb)
    items = []
    for f in kb['fixes']:
        if f.get('quiz_eligible', True) and (chapter is None or f['ch'] == chapter):
            items.append({'type': 'fix', 'ref': f['id'], 'ch': f['ch']})
    for e in kb['examples']:
        if (e.get('quiz_eligible', True) and (chapter is None or e['ch'] == chapter)
                and (e['ch'], _strip_quotes(norm(e['t']))) not in paired):
            items.append({'type': 'tf', 'ref': e['id'], 'ch': e['ch']})
    for e in kb['exercises']:
        if e['options'] and e.get('quiz_eligible', True) and (chapter is None or e['ch'] == chapter):
            items.append({'type': 'mcq', 'ref': e['source_id'], 'ch': e['ch']})
    for q in kb.get('_reviewed_quiz', []):
        # scelte multiple ricostruite da dialoghi/discorsi del libro (fase 3)
        if q.get('quiz_eligible') is True and q['type'] == 'mcq' and (chapter is None or q['ch'] == chapter):
            items.append({'type': 'mcq', 'ref': q['id'], 'ch': q['ch']})
    return items


def build_pool(kb, chapter=None, limit=QUIZ_SIZE, rng=random):
    """Mescola i tre tipi: circa 4 coppie, 2 scelte multiple, il resto vero/falso."""
    items = quiz_items(kb, chapter)
    by = {'fix': [], 'tf': [], 'mcq': []}
    for it in items:
        by[it['type']].append(it)
    for v in by.values():
        rng.shuffle(v)
    want = {'fix': 4, 'mcq': 2}
    pool = by['fix'][:want['fix']] + by['mcq'][:want['mcq']]
    rest = by['fix'][want['fix']:] + by['mcq'][want['mcq']:] + by['tf']
    rng.shuffle(rest)
    tfs = [r for r in rest if r['type'] == 'tf']
    others = [r for r in rest if r['type'] != 'tf']
    pool += (tfs + others)[:max(0, limit - len(pool))]
    pool = pool[:max(0, limit)]
    rng.shuffle(pool)
    return pool


def resolve(kb, ref_item):
    index = kb.get('_index')
    if index is None:
        index = kb['_index'] = {**{e['id']: e for e in kb['examples']}, **{f['id']: f for f in kb['fixes']},
                                **{e['source_id']: e for e in kb['exercises']},
                                **{q['id']: q for q in kb.get('_reviewed_quiz', [])}}
    return index[ref_item['ref']]
