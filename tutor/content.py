"""Correzioni editoriali non distruttive e quarantena prudenziale per i quiz.

La KB originale non viene sovrascritta. Le correzioni sono abbinate al contenuto,
mai alla posizione nella lista; un abbinamento mancante/ambiguo blocca il caricamento.
Questi controlli NON sostituiscono la revisione didattica dell'intero libro.
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from tutor.editorial import DEFAULT_REVIEW, apply_review

DEFAULT_CORRECTIONS = Path(__file__).resolve().parent.parent / 'data' / 'content_overrides.json'
HEADER = re.compile(r'C H A P T E R|\bPART [IV]+\b')


def target_span(text, target):
    matches = list(re.finditer(r'(?<!\w)' + re.escape(target) + r'(?!\w)', text))
    if len(matches) != 1:
        raise ValueError('Il bersaglio deve comparire esattamente una volta nella domanda')
    return matches[0].span()


def prepare_content(kb, corrections_path=DEFAULT_CORRECTIONS, review_path=DEFAULT_REVIEW):
    # Ripristina solo il flag meccanico prima di riapplicare patch/quarantena.
    for section in ('examples', 'fixes', 'exercises'):
        for item in kb[section]:
            if '_mechanically_eligible' in item:
                item['quiz_eligible'] = item.pop('_mechanically_eligible')
    if corrections_path is not None:
        doc = json.loads(Path(corrections_path).read_text(encoding='utf-8'))
        if doc.get('schema_version') != 1:
            raise ValueError('Versione delle correzioni non supportata')
        seen = set()
        for section in ('exercises', 'fixes'):
            for patch in doc.get(section, []):
                if patch['id'] in seen:
                    raise ValueError('ID di correzione duplicato: ' + patch['id'])
                seen.add(patch['id'])
                # Accetta anche il valore finale approvato: rende le correzioni
                # riapplicabili dopo una build, senza matching vago o per indice.
                matches = [e for e in kb[section] if all(
                    e.get(key) == value or
                    key in patch['set'] and e.get(key) == patch['set'][key]
                    for key, value in patch['match'].items())]
                if len(matches) != 1:
                    raise ValueError('Correzione non applicabile univocamente: ' + patch['id'])
                e = matches[0]
                e.update(patch['set'])
                e['id'] = patch['id']
                if e.get('target'):
                    target_span(e['q'], e['target'])

    # Conserva gli esempi per la consultazione, ma non valuta testi danneggiati.
    labels = defaultdict(set)
    norm = lambda text: ' '.join(text.casefold().split())
    for e in kb['examples']:
        labels[norm(e['t'])].add(e['ok'])
    for section in ('examples', 'fixes', 'exercises'):
        for item in kb[section]:
            reasons = []
            if section == 'examples':
                text = item['t']
                if len(labels[norm(text)]) > 1:
                    reasons.append('conflicting_labels')
                if text.count('“') != text.count('”'):
                    reasons.append('unbalanced_quotes')
            elif section == 'fixes':
                text = item['good']
                if item['ch'] == 14 and item['bad'] == 'A problem was occurred' and text == 'A problem':
                    reasons.append('known_truncated_correction')
            else:
                text = item['q'] + '\n' + item['answer']
            if text.count('(') != text.count(')'):
                reasons.append('unbalanced_parentheses')
            if HEADER.search(text):
                reasons.append('page_header')
            if '**' in text or '~~' in text:
                reasons.append('unresolved_markup')
            if reasons:
                item['quiz_eligible'] = False
                item['quiz_exclusion_reasons'] = reasons
    return apply_review(kb, review_path)
