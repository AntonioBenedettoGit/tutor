"""Fase 3: registro, provenienza, fail-closed e feedback. Tutto offline."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

import bot
from tutor.content import prepare_content
from tutor.editorial import DEFAULT_REVIEW
from tutor.kb import load_kb
from test_foundations import FakeChat

ROOT = Path(__file__).resolve().parents[1]


class EditorialTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(DEFAULT_REVIEW.read_text(encoding='utf-8'))
        self.raw = json.loads((ROOT / 'data/kb.json').read_text(encoding='utf-8'))

    def load_doc(self, doc):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'review.json'
            path.write_text(json.dumps(doc), encoding='utf-8')
            return prepare_content(copy.deepcopy(self.raw), review_path=path)

    def test_all_raw_content_preserved_and_not_scored(self):
        loaded = load_kb()
        for section in ('examples', 'fixes', 'exercises'):
            self.assertEqual(len(loaded[section]), len(self.raw[section]))
            self.assertTrue(all(not e['quiz_eligible'] for e in loaded[section]))
        self.assertEqual(loaded['chapters'], self.raw['chapters'])
        self.assertEqual(hashlib.sha256((ROOT / 'data/kb.json').read_bytes()).hexdigest(),
                         'cb832b59c5929b474592cc4b4492660916b972713b49dcf4f3c297f528eabeeb')

    def test_counts_ids_and_chapter_scope(self):
        questions = bot.KB['_reviewed_quiz']
        self.assertEqual(len(questions), 160)
        self.assertEqual(sum(q['type'] == 'tf' for q in questions), 150)
        self.assertEqual(sum(q['type'] == 'mcq' for q in questions), 10)
        self.assertEqual(len({q['id'] for q in questions}), 160)
        for chapter in range(1, 26):
            expected = sum(q['ch'] == chapter for q in questions)
            for _ in range(10):
                pool = bot.build_quiz_pool(bot.KB, chapter)
                self.assertEqual(len(pool), expected)
                self.assertTrue(all(q['ch'] == chapter for q in pool))
                self.assertEqual(len({q['id'] for q in pool}), expected)

    def test_no_implicit_legacy_fallback(self):
        self.assertEqual(bot.build_quiz_pool(self.raw), [])
        prepared = prepare_content(self.raw, review_path=None)
        self.assertEqual(bot.build_quiz_pool(prepared), [])
        self.assertEqual(bot.build_quiz_pool(bot.KB, 999), [])
        self.assertEqual(bot.build_quiz_pool(bot.KB, limit=0), [])
        self.assertEqual(len(bot.build_quiz_pool(bot.KB)), 10)

    def test_missing_register_fails_instead_of_approving_raw(self):
        with self.assertRaises(FileNotFoundError):
            prepare_content(self.raw, review_path=ROOT / 'missing-register.json')

    def test_unreviewed_or_disabled_question_never_selected(self):
        kb = copy.deepcopy(bot.KB)
        kb['_reviewed_quiz'][0]['review_status'] = 'pending'
        kb['_reviewed_quiz'][1]['quiz_eligible'] = False
        pool = bot.build_quiz_pool(kb, limit=1000)
        ids = {q['id'] for q in pool}
        self.assertNotIn(kb['_reviewed_quiz'][0]['id'], ids)
        self.assertNotIn(kb['_reviewed_quiz'][1]['id'], ids)
        self.assertEqual(len(pool), 158)

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
            'tf_label': lambda d: d['questions'][0].update(ok='yes'),
            'tf_correction': lambda d: d['questions'][3].pop('correction'),
            'tf_reference': lambda d: d['questions'][0]['legacy_ref'].update(t='changed'),
            'quote': lambda d: d['questions'][0]['source']['citations'][0].update(quote='not in the book'),
            'pages': lambda d: d['questions'][0]['source']['citations'][0].update(pages=[999]),
            'missing_quote': lambda d: d['questions'][0]['source'].update(citations=[]),
            'options': lambda d: d['questions'][-1].update(options=['same', 'same']),
            'answer_index': lambda d: d['questions'][-1].update(answer_idx=2),
            'boolean_index': lambda d: d['questions'][-1].update(answer_idx=True),
            'exercise_drift': lambda d: d['questions'][-1]['exercise_ref'].update(answer='new answer'),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                doc = copy.deepcopy(self.doc)
                mutation(doc)
                with self.assertRaises(ValueError):
                    self.load_doc(doc)

    def test_source_example_drift_rejected(self):
        target = self.doc['questions'][0]['legacy_ref']
        next(e for e in self.raw['examples'] if all(e.get(k) == v for k, v in target.items()))['t'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'sorgente cambiato'):
            prepare_content(self.raw)

    def test_chapter_citation_drift_rejected(self):
        self.raw['chapters'][0]['text'] = 'Different book text'
        with self.assertRaisesRegex(ValueError, 'citazione non trovata'):
            prepare_content(self.raw)

    def test_overrides_preserve_original_text_and_answer(self):
        for name, answer, fragment in [('ch15-main-7', 'as long as', 'I’ll lend'),
                                        ('ch22-B-5', 'Despite', '(Despite / Although)')]:
            e = next(e for e in bot.KB['exercises'] if e['source_id'] == name)
            raw = next(e for e in self.raw['exercises'] if e['source_id'] == name)
            self.assertEqual(e['source_q'], raw['q'])
            self.assertEqual(e['source_answer'], raw['answer'])
            self.assertIn(fragment, e['q'])
            self.assertEqual(e['options'][e['answer_idx']], answer)
            self.assertNotEqual(e['answer'], raw['answer'])
            self.assertTrue(e['editorial_note']['it'])
            if name == 'ch15-main-7':
                self.assertIn('only if', e['instr'])
                self.assertEqual(e['source_instr'], raw['instr'])
                reviewed = next(q for q in bot.KB['_reviewed_quiz'] if q.get('exercise_ref', {}).get('source_id') == name)
                self.assertIn('only on condition', reviewed['context']['en'])

    def test_all_known_contextual_traps_excluded_from_tf(self):
        traps = ['Tom called Tom’s mother because Tom missed Tom’s mother.',
                 'We are meeting tomorrow in town.', 'I like the music.',
                 'I had visited Rome in 2010.', 'The thieves were arrested by the police.',
                 'If you will help me, I’ll be grateful.', 'To smoke damages your health.',
                 'I am boring.', 'She kept working, although she was tired.',
                 'You like coffee?', 'I’d like to thank my parents, Oprah and God.']
        tf = {q['t'] for q in bot.KB['_reviewed_quiz'] if q['type'] == 'tf'}
        self.assertTrue(tf.isdisjoint(traps))
        self.assertTrue(any(e['t'] in traps for e in bot.KB['examples']))

    def test_capitalisation_not_collapsed_by_casefold(self):
        questions = [q for q in bot.KB['_reviewed_quiz'] if q['id'] in ('rev-ch04-tf-02', 'rev-ch04-tf-06')]
        self.assertEqual({q['ok'] for q in questions}, {True, False})
        self.assertTrue(all(q['context'] for q in questions))

    def test_complete_quotes_in_recovered_dialogues(self):
        questions = [q for q in bot.KB['_reviewed_quiz'] if q['source']['kind'] == 'contextual_reconstruction']
        self.assertEqual(len(questions), 8)
        for q in questions:
            self.assertEqual(q['q'].count('“'), q['q'].count('”'))
            for lang in ('it', 'en'):
                self.assertIn(q['context'][lang], bot.quiz_question_text(lang, q, 1, 1))

    def test_british_and_american_punctuation_contexts_distinct(self):
        us = next(q for q in self.doc['questions'] if q['id'] == 'rev-ch25-quote-us')
        uk = next(q for q in self.doc['questions'] if q['id'] == 'rev-ch25-quote-uk')
        self.assertIn('American', us['context']['en'])
        self.assertIn('British', uk['context']['en'])
        self.assertEqual(us['options'][us['answer_idx']], '“brilliant.”')
        self.assertEqual(uk['options'][uk['answer_idx']], '‘brilliant’.')

    def test_preparation_idempotent(self):
        kb = load_kb()
        before = copy.deepcopy(kb)
        prepare_content(kb)
        self.assertEqual(kb, before)


class EditorialFeedbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_explanations_corrections_sources_and_scores_for_every_item(self):
        chat = FakeChat()
        chat.id = 303
        update = SimpleNamespace(effective_chat=chat, callback_query=None, message=None)
        for lang in ('it', 'en'):
            for original in bot.KB['_reviewed_quiz']:
                for correct in (True, False):
                    state = bot.enter_mode(chat.id, 'quiz')
                    state['lang'] = lang
                    q = copy.deepcopy(original)
                    state['quiz'] = {'id':'review-test', 'pool':[q], 'idx':0,
                                     'score':0, 'answered':False}
                    await bot.send_next_question(update, None, chat.id)
                    given = (q['ok'] if correct else not q['ok']) if q['type'] == 'tf' else (
                        q['answer_idx'] if correct else 1 - q['answer_idx'])
                    await bot.quiz_feedback(update, None, chat.id, given)
                    self.assertEqual(state['quiz']['score'], int(correct))
                    feedback = chat.messages[-1]['text']
                    self.assertIn(q['explanation'][lang], feedback)
                    if q.get('correction'):
                        self.assertIn(q['correction'], feedback)
                    self.assertIn(str(q['source']['citations'][0]['pages'][0]), feedback)
                    self.assertNotIn('Risposta del libro:', feedback)
                    self.assertNotIn('Book answer:', feedback)
        bot.STATE.pop(chat.id, None)


@unittest.skipUnless(os.environ.get('TUTOR_TEST_PDF'), 'PDF richiesto per verifica citazioni editoriali')
class EditorialPDFTests(unittest.TestCase):
    def test_every_citation_and_original_solution_in_pdf(self):
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
        raw = json.loads((ROOT / 'data/kb.json').read_text(encoding='utf-8'))
        for name in ('ch15-main-7', 'ch22-B-5'):
            e = next(e for e in raw['exercises'] if e['source_id'] == name)
            text = join_text([line.text for line in pages[e['answer_pdf_page'] - 1]])
            self.assertIn(norm(e['answer']), norm(text))
