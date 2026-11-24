"""Fase 4: contenuti del libro nel quiz, senza quarantena editoriale.

La KB originale non viene sovrascritta. Le correzioni (data/content_overrides.json)
servono solo a riparare il testo estratto dal PDF, mai a cambiare ciò che il libro dice;
sono abbinate al contenuto, mai alla posizione: un abbinamento mancante o ambiguo
blocca il caricamento.

Ogni esempio, coppia ed esercizio del libro è valutabile, salvo difetti meccanici del
testo (virgolette/parentesi sbilanciate, intestazioni di pagina, marcatori residui,
frammenti che il libro presenta con «…» e che da soli non si possono giudicare).
"""
import json
import re
from collections import defaultdict
from pathlib import Path

from tutor.editorial import DEFAULT_REVIEW, apply_review

DEFAULT_CORRECTIONS = Path(__file__).resolve().parent.parent / 'data' / 'content_overrides.json'
HEADER = re.compile(r'C H A P T E R|\bPART [IV]+\b')
PART_LABEL = re.compile(r'(?<![\w(])[a-h]\)')        # «a) easy b) expensive»: etichette, non parentesi


def target_span(text, target):
    matches = list(re.finditer(r'(?<!\w)' + re.escape(target) + r'(?!\w)', text))
    if len(matches) != 1:
        raise ValueError('Il bersaglio deve comparire esattamente una volta nella domanda')
    return matches[0].span()


def _apply_overrides(kb, corrections_path):
    doc = json.loads(Path(corrections_path).read_text(encoding='utf-8'))
    if doc.get('schema_version') != 1:
        raise ValueError('Versione delle correzioni non supportata')
    seen = set()
    for section in ('examples', 'exercises', 'fixes'):
        for patch in doc.get(section, []):
            if patch['id'] in seen:
                raise ValueError('ID di correzione duplicato: ' + patch['id'])
            seen.add(patch['id'])
            # Accetta anche il valore finale approvato: le correzioni restano
            # riapplicabili dopo una build, senza matching vago o per indice.
            matches = [e for e in kb[section] if all(
                e.get(key) == value or key in patch['set'] and e.get(key) == patch['set'][key]
                for key, value in patch['match'].items())]
            if len(matches) != 1:
                raise ValueError('Correzione non applicabile univocamente: ' + patch['id'])
            e = matches[0]
            e.update(patch['set'])
            if section != 'examples':
                e['id'] = patch['id']
            if e.get('target'):
                target_span(e['q'], e['target'])


def _exclusion_reasons(section, item, labels):
    reasons = []
    if section == 'examples':
        text = item['t']
        # Sensibile alle maiuscole: «I love Summer.» ✗ e «I love summer.» ✓ sono esempi diversi.
        if len(labels[' '.join(text.split())]) > 1:
            reasons.append('conflicting_labels')
        if text.count('“') != text.count('”'):
            reasons.append('unbalanced_quotes')
        if re.match(r'^\s*(?:…|\.\.\.)', text):
            reasons.append('fragment')              # «(✗ …every.)»: dipende dalla frase precedente
    elif section == 'fixes':
        text = item['bad'] + '\n' + item['good']
    else:
        text = PART_LABEL.sub('', item['q'] + '\n' + item['answer'])
    if text.count('(') != text.count(')'):
        reasons.append('unbalanced_parentheses')
    if HEADER.search(text):
        reasons.append('page_header')
    if '**' in text or '~~' in text:
        reasons.append('unresolved_markup')
    return reasons


def prepare_content(kb, corrections_path=DEFAULT_CORRECTIONS, review_path=DEFAULT_REVIEW):
    # Idempotente: l'idoneità si ricalcola sempre da zero (le correzioni si riapplicano).
    for section in ('examples', 'fixes', 'exercises'):
        for item in kb[section]:
            for key in ('_mechanically_eligible', 'quiz_review_status', 'quiz_exclusion_reasons',
                        'quiz_eligible'):
                item.pop(key, None)
    if corrections_path is not None:
        _apply_overrides(kb, corrections_path)

    labels = defaultdict(set)
    for e in kb['examples']:
        labels[' '.join(e['t'].split())].add(e['ok'])
    for section in ('examples', 'fixes', 'exercises'):
        for item in kb[section]:
            reasons = _exclusion_reasons(section, item, labels)
            if reasons:
                item['quiz_eligible'] = False
                item['quiz_exclusion_reasons'] = reasons
            elif 'quiz_eligible' not in item:
                item['quiz_eligible'] = True
    return apply_review(kb, review_path)
