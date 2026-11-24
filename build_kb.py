#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build specifica e protetta del libro A1-C1, senza fallback testuali.

    pip install -r requirements-build.txt
    python build_kb.py libro.pdf data/kb.candidate.json

La KB attiva si sostituisce soltanto con --replace, dopo tutti i controlli e
con backup. Dalla versione 3 teoria, esempi, coppie e soluzioni sono estratti dal
PDF con la formattazione; ogni contenuto deve corrispondere al profilo approvato
(data/book_profile.json, rigenerabile solo con tools/approve_profile.py).
"""
import argparse
import json
from pathlib import Path
import sys

from tutor.kb_builder import BuildError, atomic_json, build_candidate, digest, publish_candidate

ROOT = Path(__file__).resolve().parent

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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('output', type=Path, nargs='?', default=ROOT/'data/kb.candidate.json')
    parser.add_argument('--baseline', type=Path, default=ROOT/'data/kb.json')
    parser.add_argument('--profile', type=Path, default=ROOT/'data/book_profile.json')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--replace', action='store_true', help='Consenti sostituzione della baseline con backup')
    args = parser.parse_args(argv)
    try:
        if args.report and args.report.resolve() in {args.baseline.resolve(),args.output.resolve(),args.profile.resolve(),args.pdf.resolve()}:
            raise BuildError('Il report deve avere un percorso diverso da input, profilo e output')
        if args.output.resolve() in {args.pdf.resolve(),args.profile.resolve()}:
            raise BuildError('L’output non può sovrascrivere il PDF o il profilo')
        baseline_bytes = args.baseline.read_bytes()
        baseline = json.loads(baseline_bytes)
        profile = json.loads(args.profile.read_text(encoding='utf-8'))
        candidate = build_candidate(args.pdf,baseline,profile,CHAPTERS,PARTS,SYNONYMS)
        report = publish_candidate(candidate,profile,baseline,args.output,args.baseline,args.replace)
        report.update(source_pdf_sha256=profile['pdf_sha256'],
                      baseline_sha256=digest(baseline_bytes),extractor=candidate['meta']['extractor'])
        if args.report:
            try:
                atomic_json(args.report,report)
            except OSError as exc:
                # La KB è già validata/scritta: non dichiarare falsamente che la
                # sostituzione sia stata rifiutata se fallisce solo il report.
                report['report_warning'] = f'KB scritta; report non salvato: {type(exc).__name__}'
                print(report['report_warning'],file=sys.stderr)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except (BuildError, OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
        print(f'Build rifiutata: {exc}',file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
