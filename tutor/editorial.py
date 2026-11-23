"""Registro esplicito dei quiz revisionati: nessuna approvazione per difetto.

Il PDF serve solo ai test di integrazione. A runtime si verificano riferimenti,
contenuto citato, pagine e hash della fonte registrato nella KB.
La revisione assistita non è una certificazione umana del libro.
"""
import copy
import json
from pathlib import Path

DEFAULT_REVIEW = Path(__file__).resolve().parent.parent / 'data' / 'reviewed_quiz.json'


def _require(condition, message):
    if not condition:
        raise ValueError('Registro editoriale: ' + message)


def _bilingual(value):
    return isinstance(value, dict) and all(
        isinstance(value.get(lang), str) and value[lang].strip()
        for lang in ('it', 'en'))


def apply_review(kb, review_path=DEFAULT_REVIEW):
    # Il materiale grezzo rimane consultabile, mai fonte implicita di punti.
    kb['_reviewed_quiz'] = []
    for section in ('examples', 'fixes', 'exercises'):
        for item in kb[section]:
            item['_mechanically_eligible'] = item.get('quiz_eligible', True)
            item['quiz_eligible'] = False
            item['quiz_review_status'] = 'consultation_only'
    if review_path is None:
        return kb
    doc = json.loads(Path(review_path).read_text(encoding='utf-8'))
    _require(doc.get('schema_version') == 1, 'schema non supportato')
    _require(doc.get('review', {}).get('method') == 'assistant_editorial_review'
             and doc['review'].get('human_certified') is False, 'tipo di revisione non valido')
    _require(doc.get('source_pdf_sha256') == kb.get('meta', {}).get('source_pdf_sha256'),
             'hash della fonte diverso')
    chapters = {c['num']: c for c in kb['chapters']}
    norm = lambda text: ' '.join(text.split())
    _require(isinstance(doc.get('questions'), list), 'domande mancanti')
    result, ids, contents = [], set(), set()
    for original in doc['questions']:
        _require(isinstance(original, dict), 'domanda non valida')
        q = copy.deepcopy(original)
        name, ch, kind = q.get('id'), q.get('ch'), q.get('type')
        _require(isinstance(name, str) and name and name not in ids, 'ID mancante/duplicato')
        ids.add(name)
        _require(type(ch) is int and ch in chapters, name + ': capitolo non valido')
        _require(q.get('review_status') == 'assistant_checked', name + ': non revisionata')
        _require(kind in ('tf', 'mcq'), name + ': tipo non supportato')
        _require(_bilingual(q.get('explanation')), name + ': spiegazione IT/EN mancante')
        if 'context' in q:
            _require(_bilingual(q['context']), name + ': contesto IT/EN mancante')
        text = q.get('t' if kind == 'tf' else 'q')
        _require(isinstance(text, str) and bool(text.strip()), name + ': testo mancante')
        content_key = (ch, kind, text)
        _require(content_key not in contents, name + ': domanda duplicata')
        contents.add(content_key)
        if kind == 'tf':
            _require(type(q.get('ok')) is bool, name + ': etichetta non booleana')
            if not q['ok']:
                _require(isinstance(q.get('correction'), str) and q['correction'].strip()
                         and q['correction'] != text, name + ': correzione mancante')
            ref = q.get('legacy_ref')
            _require(ref == {'ch': ch, 't': text, 'ok': q['ok']}, name + ': riferimento TF incoerente')
            _require(any(all(e.get(k) == v for k, v in ref.items()) for e in kb['examples']),
                     name + ': esempio sorgente cambiato')
        else:
            options, index = q.get('options'), q.get('answer_idx')
            _require(isinstance(options, list) and 2 <= len(options) <= 6
                     and all(isinstance(o, str) and o.strip() for o in options), name + ': opzioni non valide')
            _require(len(set(options)) == len(options), name + ': opzioni duplicate')
            _require(type(index) is int and 0 <= index < len(options), name + ': soluzione non valida')
        src = q.get('source', {})
        _require(src.get('chapter') == ch and src.get('kind') in (
            'verbatim_example', 'contextual_reconstruction', 'editorial_rewrite'), name + ': fonte non valida')
        citations = src.get('citations')
        _require(isinstance(citations, list) and bool(citations), name + ': citazioni mancanti')
        for cit in citations:
            _require(isinstance(cit, dict), name + ': citazione non valida')
            quote, pages = cit.get('quote'), cit.get('pages')
            _require(isinstance(quote, str) and bool(quote.strip()) and
                     norm(quote) in norm(chapters[ch]['text']), name + ': citazione non trovata nel capitolo')
            _require(isinstance(pages, list) and 1 <= len(pages) <= 2
                     and all(type(p) is int and chapters[ch]['pdf_page_start'] <= p <=
                             chapters[ch]['pdf_page_end'] for p in pages)
                     and pages == list(range(pages[0], pages[-1] + 1)), name + ': pagine non valide')
        if kind == 'tf':
            _require(any(norm(text) in norm(c['quote']) for c in citations), name + ': testo TF non citato')
        if src['kind'] == 'editorial_rewrite':
            ref = q.get('exercise_ref', {})
            matches = [e for e in kb['exercises'] if e.get('source_id') == ref.get('source_id')]
            _require(len(matches) == 1, name + ': esercizio sorgente non trovato')
            e = matches[0]
            _require(all(e.get(key) == value for key, value in ref.items()) and
                     all(q[key] == e[key] for key in ('q', 'options', 'answer_idx')),
                     name + ': esercizio/soluzione sorgente cambiati')
            _require(e.get('editorial_note') and e['ch'] == ch, name + ': override editoriale mancante')
        q['quiz_eligible'] = True
        result.append(q)
    kb['_reviewed_quiz'] = result
    return kb
