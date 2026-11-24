#!/usr/bin/env python3
"""Approvazione del profilo v2 del libro (fase 4.2). Non tocca la KB attiva.

    python tools/approve_profile.py libro.pdf OUT_DIR            # solo verifica + report
    python tools/approve_profile.py libro.pdf OUT_DIR --write    # scrive anche data/book_profile.json

1. estrae il libro una sola volta e costruisce la KB v3 candidata;
2. esegue i controlli di contenuto indipendenti dal profilo (markup, simboli, HTML, pagine...);
3. confronta esempi/coppie con la KB attiva (report di copertura per la revisione);
4. con --write registra le nuove impronte, mantenendo i riferimenti già approvati
   (PDF, esercizi, verbi, glossario, MCQ), poi rivalida la candidata col nuovo profilo.
"""
import argparse
import collections
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_kb  # noqa: E402
from tutor.kb_builder import (BuildError, atomic_json, build_candidate, content_errors, extract_book,  # noqa: E402
                              profile_from_candidate, validate_candidate)


def _norm(t):
    return re.sub(r'[^\w]+', ' ', t.replace('*', '').replace('~', '').lower()).strip()


def coverage(baseline, kb):
    """Ogni esempio/coppia della KB attiva: identico, ritrovato (testo uguale salvo punteggiatura,
    oppure più completo/più corto), o assente. Gli assenti vanno motivati nel report di revisione."""
    new = collections.defaultdict(list)
    for e in kb['examples']:
        new[(e['ch'], e['ok'])].append(_norm(e['t']))
    exact = {(e['ch'], e['t'], e['ok']) for e in kb['examples']}
    out = collections.Counter()
    missing = []
    for e in baseline['examples']:
        n, cands = _norm(e['t']), new[(e['ch'], e['ok'])]
        if (e['ch'], e['t'], e['ok']) in exact:
            out['identici'] += 1
        elif n in cands:
            out['solo_punteggiatura_o_markup'] += 1
        elif any(c.startswith(n) for c in cands):
            out['ora_piu_completi'] += 1
        elif any(n.startswith(c) and c for c in cands):
            out['ora_senza_commento_del_libro'] += 1
        else:
            out['assenti'] += 1
            missing.append({'ch': e['ch'], 't': e['t'], 'ok': e['ok']})
    fx = {(_norm(f['bad']), f['ch']) for f in kb['fixes']}
    fixes_missing = [f for f in baseline['fixes'] if (_norm(f['bad']), f['ch']) not in fx]
    return {'examples': dict(out), 'examples_missing': missing,
            'fixes_baseline': len(baseline['fixes']), 'fixes_new': len(kb['fixes']),
            'fixes_missing': [{'ch': f['ch'], 'bad': f['bad'], 'good': f['good']} for f in fixes_missing]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pdf', type=Path)
    ap.add_argument('out_dir', type=Path)
    ap.add_argument('--baseline', type=Path, default=ROOT / 'data/kb.json')
    ap.add_argument('--profile', type=Path, default=ROOT / 'data/book_profile.json')
    ap.add_argument('--write', action='store_true')
    args = ap.parse_args(argv)
    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    current = json.loads(args.profile.read_text(encoding='utf-8'))
    draft = dict(current, schema_version=2)
    extracted = extract_book(args.pdf)
    kb = build_candidate(args.pdf, baseline, draft, build_kb.CHAPTERS, build_kb.PARTS, build_kb.SYNONYMS,
                         extracted=extracted)
    errors = content_errors(kb)
    report = {'counts': kb['meta']['counts'], 'content_errors': errors, 'coverage': coverage(baseline, kb)}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(args.out_dir / 'kb.candidate.json', kb)
    if errors:
        atomic_json(args.out_dir / 'approval_report.json', report)
        print('\n'.join(errors[:50]), file=sys.stderr)
        print(f'Profilo NON approvato: {len(errors)} problemi di contenuto', file=sys.stderr)
        return 1
    profile = profile_from_candidate(kb, current)
    report['validation'] = validate_candidate(kb, profile, baseline)
    atomic_json(args.out_dir / 'book_profile.proposed.json', profile)
    atomic_json(args.out_dir / 'approval_report.json', report)
    if args.write:
        atomic_json(args.profile, profile)
        report['profile_written'] = str(args.profile)
    print(json.dumps({k: v for k, v in report.items() if k != 'coverage'}, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in report['coverage'].items() if k != 'examples_missing'},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except BuildError as exc:
        print(f'Build rifiutata: {exc}', file=sys.stderr)
        sys.exit(1)
