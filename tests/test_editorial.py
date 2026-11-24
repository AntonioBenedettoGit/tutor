"""Fase 4: registro residuo (domande ricostruite), note italiane, provenienza. Tutto offline."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import bot
from tutor import book_quiz
from tutor.book_quiz import load_notes
from tutor.content import prepare_content
from tutor.editorial import DEFAULT_REVIEW
from tutor.kb import load_kb
from test_foundations import FakeChat

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / 'data' / 'notes_it.json'


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(DEFAULT_REVIEW.read_text(encoding='utf-8'))
        self.raw = json.loads((ROOT / 'data/kb.json').read_text(encoding='utf-8'))

    def load_doc(self, doc):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'review.json'
            path.write_text(json.dumps(doc), encoding='utf-8')
            return prepare_content(copy.deepcopy(self.raw), review_path=path)

    def test_all_book_content_preserved_and_scored(self):
        loaded = load_kb()
        for section in ('examples', 'fixes', 'exercises'):
            self.assertEqual(len(loaded[section]), len(self.raw[section]))
            excluded = [e for e in loaded[section] if not e['quiz_eligible']]
            self.assertLessEqual(len(excluded), 4, section)
            self.assertTrue(all('consultation' not in json.dumps(e) for e in loaded[section]))
        self.assertEqual(loaded['chapters'], self.raw['chapters'])
        from tutor.kb_builder import items_digest
        profile = json.loads((ROOT / 'data/book_profile.json').read_text(encoding='utf-8'))
        self.assertEqual(items_digest(self.raw), profile['items_sha256'])

    def test_register_only_contextual_reconstructions(self):
        questions = bot.KB['_reviewed_quiz']
        self.assertEqual(len(questions), 8)
        self.assertTrue(all(q['type'] == 'mcq' and q['source']['kind'] == 'contextual_reconstruction'
                            for q in questions))
        ids = {r['ref'] for r in book_quiz.quiz_items(bot.KB) if r['type'] == 'mcq'}
        self.assertTrue({q['id'] for q in questions} <= ids)

    def test_editorial_rewrites_rejected(self):
        doc = copy.deepcopy(self.doc)
        doc['questions'][0]['source']['kind'] = 'editorial_rewrite'
        with self.assertRaises(ValueError):
            self.load_doc(doc)

    def test_pool_limits_and_scope(self):
        self.assertEqual(bot.build_quiz_pool(bot.KB, 999), [])
        self.assertEqual(bot.build_quiz_pool(bot.KB, limit=0), [])
        pool = bot.build_quiz_pool(bot.KB)
        self.assertEqual(len(pool), 10)
        self.assertEqual({r['type'] for r in book_quiz.quiz_items(bot.KB)}, {'tf', 'fix', 'mcq'})

    def test_missing_register_fails(self):
        with self.assertRaises(FileNotFoundError):
            prepare_content(self.raw, review_path=ROOT / 'missing-register.json')

    def test_invalid_review_records_rejected(self):
        mutations = {
            'schema': lambda d: d.update(schema_version=2),
            'hash': lambda d: d.update(source_pdf_sha256='changed'),
            'human_certification': lambda d: d['review'].update(human_certified=True),
            'duplicate_id': lambda d: d['questions'].append(copy.deepcopy(d['questions'][0])),
            'status': lambda d: d['questions'][0].update(review_status='pending'),
            'chapter': lambda d: d['questions'][0].update(ch=100),
            'boolean_chapter': lambda d: d['questions'][0].update(ch=True),
            'type': lambda d: d['questions'][0].update(type='unsupported'),
            'explanation': lambda d: d['questions'][0]['explanation'].pop('it'),
            'context': lambda d: d['questions'][-1]['context'].pop('en'),
            'quote': lambda d: d['questions'][0]['source']['citations'][0].update(quote='not in the book'),
            'pages': lambda d: d['questions'][0]['source']['citations'][0].update(pages=[999]),
            'missing_quote': lambda d: d['questions'][0]['source'].update(citations=[]),
            'options': lambda d: d['questions'][-1].update(options=['same', 'same']),
            'answer_index': lambda d: d['questions'][-1].update(answer_idx=2),
            'boolean_index': lambda d: d['questions'][-1].update(answer_idx=True),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                doc = copy.deepcopy(self.doc)
                mutation(doc)
                with self.assertRaises(ValueError):
                    self.load_doc(doc)

    def test_chapter_citation_drift_rejected(self):
        self.raw['chapters'][10]['text'] = 'Different book text'
        with self.assertRaisesRegex(ValueError, 'citazione non trovata'):
            prepare_content(self.raw)

    def test_british_and_american_punctuation_contexts_distinct(self):
        us = next(q for q in self.doc['questions'] if q['id'] == 'rev-ch25-quote-us')
        uk = next(q for q in self.doc['questions'] if q['id'] == 'rev-ch25-quote-uk')
        self.assertIn('American', us['context']['en'])
        self.assertIn('British', uk['context']['en'])
        self.assertEqual(us['options'][us['answer_idx']], '“brilliant.”')
        self.assertEqual(uk['options'][uk['answer_idx']], '‘brilliant’.')

    def test_preparation_idempotent(self):
        kb = load_kb()
        kb.pop('_index', None)
        before = copy.deepcopy(kb)
        prepare_content(kb)
        self.assertEqual(kb, before)


class NotesTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(NOTES.read_text(encoding='utf-8'))

    def load(self, doc):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'notes.json'
            path.write_text(json.dumps(doc), encoding='utf-8')
            return load_notes(bot.KB, path)

    def test_coverage(self):
        notes = bot.KB['_notes_it']
        sections = {book_quiz.section_key(e) for e in bot.KB['examples'] + bot.KB['fixes']}
        self.assertEqual(set(notes['sections']), sections)
        missing = {e['source_id'] for e in bot.KB['exercises']} - set(notes['exercises'])
        # decisione utente: nessuna nota sugli errori/ambiguità del libro
        self.assertEqual(missing, {'ch15-main-7', 'ch22-B-5', 'ch06-A-3', 'ch13-main-8',
                                   'ch13-main-10', 'ch19-A-4', 'ch22-B-8'})

    def test_fail_closed(self):
        mutations = {
            'schema': lambda d: d.update(schema_version=2),
            'unknown_exercise': lambda d: d['exercises'].update({'ch99-x-1': 'nota'}),
            'unknown_section': lambda d: d['sections'].update({'1|Nope': 'nota'}),
            'unknown_item': lambda d: d['items'].update({'ex-nope': 'nota'}),
            'empty': lambda d: d['exercises'].update({'ch01-A-1': '  '}),
            'too_long': lambda d: d['exercises'].update({'ch01-A-1': 'x' * 601}),
            'not_text': lambda d: d['exercises'].update({'ch01-A-1': 5}),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                doc = copy.deepcopy(self.doc)
                mutation(doc)
                with self.assertRaises(ValueError):
                    self.load(doc)


class FeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconstructed_questions_feedback(self):
        chat = FakeChat()
        chat.id = 303
        update = SimpleNamespace(effective_chat=chat, callback_query=None, message=None)
        for lang in ('it', 'en'):
            for original in bot.KB['_reviewed_quiz']:
                for correct in (True, False):
                    state = bot.enter_mode(chat.id, 'quiz')
                    state['lang'] = lang
                    ref = {'type': 'mcq', 'ref': original['id'], 'ch': original['ch']}
                    state['quiz'] = {'id': 'review-test', 'pool': [ref], 'idx': 0, 'score': 0, 'answered': False}
                    await bot.send_next_question(update, None, chat.id)
                    self.assertIn(bot.render.esc(original['context'][lang]), chat.messages[-1]['text'])
                    given = original['answer_idx'] if correct else 1 - original['answer_idx']
                    await bot.quiz_feedback(update, None, chat.id, given)
                    self.assertEqual(state['quiz']['score'], int(correct))
                    feedback = chat.messages[-1]['text']
                    self.assertIn(bot.render.esc(original['explanation'][lang]), feedback)
                    self.assertIn(str(original['source']['citations'][0]['pages'][0]), feedback)
        bot.STATE.pop(chat.id, None)


@unittest.skipUnless(os.environ.get('TUTOR_TEST_PDF'), 'PDF richiesto per verifica citazioni')
class EditorialPDFTests(unittest.TestCase):
    def test_every_citation_and_original_book_errors_in_pdf(self):
        from tutor.pdf_source import extract_pages, join_text
        pdf = Path(os.environ['TUTOR_TEST_PDF'])
        doc = json.loads(DEFAULT_REVIEW.read_text(encoding='utf-8'))
        self.assertEqual(hashlib.sha256(pdf.read_bytes()).hexdigest(), doc['source_pdf_sha256'])
        pages, _ = extract_pages(pdf)
        norm = lambda text: ' '.join(text.split())
        for q in doc['questions']:
            for citation in q['source']['citations']:
                text = join_text([line.text for p in citation['pages'] for line in pages[p - 1]])
                self.assertIn(norm(citation['quote']), norm(text), q['id'])
        # gli errori del libro arrivano al bot esattamente come nel PDF
        for name in ('ch15-main-7', 'ch22-B-5'):
            e = bot.EXERCISES[name]
            text = join_text([line.text for line in pages[e['answer_pdf_page'] - 1]])
            self.assertIn(norm(e['answer']), norm(text))


if __name__ == '__main__':
    unittest.main()
