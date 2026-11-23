"""Regressioni parser/build fase 2. Fixture del PDF; integrazione completa opzionale.
TUTOR_TEST_PDF=/percorso/libro.pdf python -m unittest discover -s tests -v
"""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import build_kb
from tutor import kb as kbmod
from tutor.content import prepare_content
from tutor.kb_builder import (BuildError, apply_mcq_policy, atomic_json, build_candidate,
                              extract_glossary, extract_reference_verbs, group_sections,
                              numbered_items, option_question, parse_exercises,
                              publish_candidate, validate_candidate)
from tutor.pdf_source import Line, extract_pages, join_text, paragraphs, partition_book, practice_sections

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = Path(os.environ.get('TUTOR_CANDIDATE_KB',ROOT/'data/kb.json'))
PROFILE = json.loads((ROOT/'data/book_profile.json').read_text())
FIXTURE = json.loads((ROOT/'tests/fixtures/pdf_sections.json').read_text())


def lines(rows):
    return [Line(r['text'],r.get('page',1),r.get('y',70),r.get('bottom',82),
                 r.get('size',10.8),r.get('heading',False),tuple(r.get('cells',()))) for r in rows]


def exercise_fixture(chapter):
    data=FIXTURE[str(chapter)]
    return lines(data['practice']),lines(data['answers'])


class ParsingTests(unittest.TestCase):
    def test_chapter_four_singleton_recovered(self):
        p,a=exercise_fixture(4)
        items=parse_exercises(4,p,a)
        self.assertEqual(len(items),24)
        singleton=items[-1]
        self.assertEqual(singleton['source_id'],'ch04-F-single')
        self.assertEqual(singleton['q'],'we visited paris last december and learned some french.')
        self.assertEqual(singleton['answer'],'We visited Paris last December and learned some French.')
        self.assertEqual(singleton['pdf_page'],59)

    def test_group_notes_and_singleton_not_attached_to_previous_answer(self):
        p,a=exercise_fixture(4);items=parse_exercises(4,p,a)
        self.assertEqual(items[19]['answer'],'has')
        self.assertEqual(items[22]['answer'],'a loaf of bread')
        self.assertNotIn('F.',items[22]['answer'])

    def test_restarted_question_numbers_and_global_answers_aligned(self):
        p,a=exercise_fixture(1);items=parse_exercises(1,p,a)
        self.assertEqual(items[4]['source_number'],1)
        self.assertEqual(items[4]['answer_number'],5)
        self.assertTrue(items[4]['answer'].startswith('Phrase'))
        self.assertEqual(items[-1]['source_id'],'ch01-D-1')

    def test_flat_answers_align_across_question_groups(self):
        p,a=exercise_fixture(3);items=parse_exercises(3,p,a)
        self.assertEqual(len(items),14)
        self.assertEqual(items[4]['source_number'],5)
        self.assertTrue(items[4]['answer'].startswith('SV —'))

    def test_missing_answer_rejected(self):
        p,a=exercise_fixture(3)
        a=[line for line in a if not line.text.startswith('14.')]
        with self.assertRaises(BuildError):parse_exercises(3,p,a)

    def test_unexpected_answer_prefix_not_silently_discarded(self):
        p,a=exercise_fixture(3)
        a=lines([{'text':'An unexpected unnumbered solution.'}])+a
        with self.assertRaises(BuildError):parse_exercises(3,p,a)

    def test_unused_answer_rejected(self):
        p,a=exercise_fixture(3)
        a+=lines([{'text':'15. An extra solution.'}])
        with self.assertRaises(BuildError):parse_exercises(3,p,a)

    def test_wrong_group_rejected(self):
        p,a=exercise_fixture(1)
        a=copy.deepcopy(a);a[0].text=a[0].text.replace('A.','Z.',1)
        with self.assertRaises(BuildError):parse_exercises(1,p,a)

    def test_duplicate_and_missing_numbers_rejected(self):
        for text in ['1. First 3. Third','1. First 1. Repeated','0. Zero 1. First']:
            with self.assertRaises(BuildError):numbered_items(text)

    def test_group_duplicates_rejected(self):
        with self.assertRaises(BuildError):
            group_sections(lines([{'text':'A. Choose. 1. First'},{'text':'A. Again. 1. Repeated'}]))

    def test_unknown_unnumbered_group_not_silently_dropped(self):
        p=lines([{'text':'A. An unrecognised exercise.'}])
        a=lines([{'text':'A. A solution.'}])
        with self.assertRaises(BuildError):parse_exercises(1,p,a)

    def test_no_mcq_inference_from_slash(self):
        p=lines([{'text':'Complete the tense.'},{'text':'1. I ___ (already / see) it.'}])
        a=lines([{'text':'1. have already seen'}])
        item=parse_exercises(12,p,a)[0]
        apply_mcq_policy([item],{})
        self.assertIsNone(item['options'])
        self.assertIn('(already / see)',item['q'])

    def test_compound_kept_whole_and_not_mcq(self):
        p,a=exercise_fixture(20);items=parse_exercises(20,p,a)
        item=items[1]
        self.assertEqual(item['kind'],'compound')
        self.assertIn('c) Today',item['q'])
        with self.assertRaises(BuildError):
            apply_mcq_policy(items,{item['source_id']:{'options':['high','higher','highest'],'correct':'higher'}})

    def test_mcq_requires_exact_approved_options(self):
        q='The cat (sit / sits) here.'
        self.assertEqual(option_question(q,['sit','sits']),'The cat _____ here.')
        with self.assertRaises(BuildError):option_question(q,['go','goes'])
        with self.assertRaises(BuildError):option_question(q+' (sit / sits)',['sit','sits'])

    def test_multiline_cells_and_base_form_reassembled(self):
        verbs,pages=extract_reference_verbs(lines(FIXTURE['verbs']))
        self.assertEqual(verbs['dream'],['dreamt / dreamed','dreamt / dreamed'])
        self.assertEqual(verbs['understand'],['understood','understood'])
        self.assertEqual(verbs['quit'],['quit / quitted','quit / quitted'])
        self.assertEqual(pages['dream'],324)

    def test_incomplete_verb_cell_rejected(self):
        source=lines(FIXTURE['verbs'])
        source=[l for l in source if l.text!='dreamed dreamed']
        with self.assertRaises(BuildError):extract_reference_verbs(source)

    def test_glossary_continuations_and_hyphenation(self):
        source=lines([{'text':'A'},{'text':'Particle — A short word used in a phrasal verb.','page':337},
                      {'text':'Participle (present/past) — A verb form used in com‐','page':337},
                      {'text':'pound tenses.'}])
        entries=extract_glossary(source)
        self.assertEqual(len(entries),2)
        self.assertIn('compound tenses',entries[1]['def'])
        self.assertEqual(entries[1]['pdf_page'],337)

    def test_page_break_not_forced_paragraph_break(self):
        source=lines([{'text':'A problem','page':1},{'text':'occurred.','page':2}])
        self.assertEqual(paragraphs(source),'A problem occurred.')
        self.assertEqual(join_text(['de‐','cision']),'decision')

    def test_practice_missing_or_ambiguous_rejected(self):
        for texts in [['Practice','Q'],['Practice','Practice','Answers'],['Q','Answers']]:
            with self.assertRaises(ValueError):practice_sections(lines([{'text':t} for t in texts]))

    def test_missing_pdf_backend_has_no_silent_fallback(self):
        with patch.dict('sys.modules',{'pymupdf':None}):
            with self.assertRaisesRegex(RuntimeError,'requirements-build'):
                extract_pages('/irrelevant.pdf')


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference=json.loads(REFERENCE.read_text())

    def setUp(self):
        self.candidate=copy.deepcopy(self.reference)
        self.baseline=copy.deepcopy(self.reference)

    def reject(self):
        with self.assertRaises(BuildError):validate_candidate(self.candidate,PROFILE,self.baseline)

    def test_reference_passes(self):
        result=validate_candidate(self.candidate,PROFILE,self.baseline)
        self.assertEqual(result['status'],'passed')
        self.assertEqual(result['counts']['exercises'],270)
        self.assertEqual(result['counts']['glossary'],93)

    def test_lost_chapter_rejected(self):
        self.candidate['chapters'].pop();self.reject()

    def test_lost_exercise_rejected_even_if_counts_adjusted(self):
        self.candidate['exercises'].pop()
        self.candidate['meta']['counts']['exercises']-=1
        self.reject()

    def test_answer_swap_same_counts_rejected(self):
        a,b=self.candidate['exercises'][:2]
        a['answer'],b['answer']=b['answer'],a['answer']
        self.reject()

    def test_corrupt_display_question_rejected(self):
        self.candidate['exercises'][0]['q']='A different question.'
        self.reject()

    def test_duplicate_id_rejected(self):
        self.candidate['exercises'][1]['source_id']=self.candidate['exercises'][0]['source_id']
        self.reject()

    def test_changed_provenance_rejected(self):
        self.candidate['exercises'][0]['pdf_page']=22
        self.reject()

    def test_lost_or_truncated_verbs_rejected(self):
        self.candidate['verbs']['dream']=['dreamt /','dreamt /'];self.reject()
        self.candidate=copy.deepcopy(self.reference)
        del self.candidate['verbs']['go'];self.reject()

    def test_missing_or_truncated_glossary_rejected(self):
        self.candidate['glossary'].pop();self.reject()
        self.candidate=copy.deepcopy(self.reference)
        self.candidate['glossary'][0]['def']='Truncated.';self.reject()

    def test_truncated_chapter_rejected(self):
        self.candidate['chapters'][0]['text']='Only a title.';self.reject()

    def test_unapproved_backend_or_version_rejected(self):
        self.candidate['meta']['extractor']['backend']='pypdf';self.reject()
        self.candidate=copy.deepcopy(self.reference)
        self.candidate['meta']['extractor']['version']='future-version';self.reject()

    def test_legacy_pool_cannot_be_silently_reimported(self):
        self.candidate['examples'].pop();self.reject()

    def test_malformed_schema_rejected(self):
        del self.candidate['exercises'][0]['source_q'];self.reject()

    def test_unapproved_mcq_or_wrong_answer_rejected(self):
        e=next(e for e in self.candidate['exercises'] if e['options'])
        e['answer_idx']=(e['answer_idx']+1)%len(e['options'])
        self.reject()

    def test_invalid_build_never_overwrites_output(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'existing.json';output.write_text('KEEP THIS FILE')
            self.candidate['exercises'].pop()
            with self.assertRaises(BuildError):
                publish_candidate(self.candidate,PROFILE,self.baseline,output,Path(temp)/'base.json')
            self.assertEqual(output.read_text(),'KEEP THIS FILE')
            self.assertFalse((Path(temp)/'backups').exists())

    def test_active_kb_needs_replace_flag(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'kb.json';output.write_text(json.dumps(self.baseline))
            old=output.read_bytes()
            with self.assertRaisesRegex(BuildError,'--replace'):
                publish_candidate(self.candidate,PROFILE,self.baseline,output,output)
            self.assertEqual(output.read_bytes(),old)

    def test_explicit_replace_keeps_exact_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'kb.json';output.write_text(json.dumps(self.baseline))
            old=output.read_bytes()
            report=publish_candidate(self.candidate,PROFILE,self.baseline,output,output,replace=True)
            self.assertEqual(Path(report['backup']).read_bytes(),old)
            self.assertEqual(json.loads(output.read_text()),self.candidate)

    def test_changed_baseline_not_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'kb.json';output.write_text('{}')
            with self.assertRaisesRegex(BuildError,'cambiata'):
                publish_candidate(self.candidate,PROFILE,self.baseline,output,output,replace=True)
            self.assertEqual(output.read_text(),'{}')

    def test_interrupted_atomic_replace_keeps_old_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'kb.json';output.write_text('OLD')
            with patch('tutor.kb_builder.os.replace',side_effect=OSError('simulated disk error')):
                with self.assertRaises(OSError):atomic_json(output,{'new':'data'})
            self.assertEqual(output.read_text(),'OLD')
            self.assertEqual([p.name for p in Path(temp).iterdir()],['kb.json'])

    def test_unknown_pdf_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            pdf=Path(temp)/'other.pdf';pdf.write_bytes(b'NOT THE BOOK')
            with patch('tutor.kb_builder.extract_pages') as extract:
                with self.assertRaisesRegex(BuildError,'PDF diverso'):
                    build_candidate(pdf,self.baseline,PROFILE,build_kb.CHAPTERS,build_kb.PARTS,build_kb.SYNONYMS)
                extract.assert_not_called()

    def test_report_write_failure_does_not_misreport_valid_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)/'base.json';base.write_text(json.dumps(self.baseline))
            output=Path(temp)/'out.json'
            report_dir=Path(temp)/'report';report_dir.mkdir()
            with patch.object(build_kb,'build_candidate',return_value=self.candidate), \
                    patch('sys.stdout',new_callable=io.StringIO) as stdout, \
                    patch('sys.stderr',new_callable=io.StringIO):
                result=build_kb.main(['book.pdf',str(output),'--baseline',str(base),
                                     '--report',str(report_dir)])
            self.assertEqual(result,0)
            self.assertEqual(json.loads(output.read_text()),self.candidate)
            self.assertIn('report_warning',stdout.getvalue())

    def test_cli_does_not_allow_report_to_overwrite_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp)/'kb.json';base.write_text('KEEP')
            with patch('sys.stderr',new_callable=io.StringIO):
                result=build_kb.main(['missing.pdf',str(Path(temp)/'out.json'),
                                     '--baseline',str(base),'--report',str(base)])
            self.assertEqual(result,1)
            self.assertEqual(base.read_text(),'KEEP')


class RuntimeDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kb=kbmod.load_kb(REFERENCE)

    def test_all_glossary_terms_find_themselves(self):
        self.assertEqual(len(self.kb['glossary']),93)
        for i,g in enumerate(self.kb['glossary']):
            self.assertIn(i,kbmod.glossary_search(self.kb,g['term']),g['term'])

    def test_glossary_new_entries_restored(self):
        terms={g['term'] for g in self.kb['glossary']}
        self.assertIn('Particle',terms)
        self.assertIn('Participle (present/past)',terms)

    def test_glossary_normalisation_limit_and_exact_precedence(self):
        hits=kbmod.glossary_search(self.kb,'  NON DEFINING RELATIVE CLAUSE  ')
        self.assertEqual(self.kb['glossary'][hits[0]]['term'],'Non-defining relative clause')
        self.assertEqual(len(kbmod.glossary_search(self.kb,'clause',limit=2)),2)
        self.assertEqual(kbmod.glossary_search(self.kb,'',limit=12),[])
        self.assertEqual(kbmod.glossary_search(self.kb,'clause',limit=0),[])

    def test_inflected_verbs_routed_to_verbs(self):
        for form,base in [('went','go'),('gone','go'),('dreamed','dream'),('quitted','quit')]:
            self.assertEqual(kbmod.search(self.kb,form)[0],('verbs',base))

    def test_four_corrections_reconstructed_without_reenabling_fragments(self):
        by_id={f.get('id'):f for f in self.kb['fixes']}
        self.assertEqual(by_id['fix-ch14-34']['good'],'A problem occurred')
        self.assertTrue(by_id['fix-ch14-34']['_mechanically_eligible'])
        self.assertFalse(by_id['fix-ch14-34']['quiz_eligible'])
        self.assertEqual(by_id['fix-ch23-57']['good'],'The book (that) I read was good')
        self.assertTrue(by_id['fix-ch23-57']['_mechanically_eligible'])
        self.assertFalse(by_id['fix-ch23-57']['quiz_eligible'])
        self.assertFalse(by_id['fix-ch23-53']['quiz_eligible'])
        self.assertFalse(by_id['fix-ch06-08']['quiz_eligible'])

    def test_runtime_corrections_are_idempotent(self):
        before=copy.deepcopy(self.kb)
        prepare_content(self.kb)
        self.assertEqual(before,self.kb)

    def test_intro_not_mid_sentence(self):
        self.assertTrue(kbmod.explain_summary(self.kb,1)[0].startswith('Welcome.'))
        self.assertNotIn('C H A P T E R',self.kb['_chapters'][4]['text'])


@unittest.skipUnless(os.environ.get('TUTOR_TEST_PDF'),'PDF non incluso nella repo: impostare TUTOR_TEST_PDF')
class FullPDFIntegrationTests(unittest.TestCase):
    def test_full_pdf_build_matches_reference_and_is_loadable(self):
        baseline=json.loads(REFERENCE.read_text())
        candidate=build_candidate(Path(os.environ['TUTOR_TEST_PDF']),baseline,PROFILE,
                                  build_kb.CHAPTERS,build_kb.PARTS,build_kb.SYNONYMS)
        report=validate_candidate(candidate,PROFILE,baseline)
        self.assertEqual(report['counts']['exercises'],270)
        self.assertEqual(report['counts']['glossary'],93)
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'candidate.json'
            publish_candidate(candidate,PROFILE,baseline,output,REFERENCE)
            loaded=kbmod.load_kb(output)
            self.assertEqual(loaded['verbs']['dream'],['dreamt / dreamed','dreamt / dreamed'])


if __name__=='__main__':
    unittest.main()
