"""Fase 5.3: teoria, esercizi e quiz nella mini app.

Il punto chiave: chat e mini app devono dare risultati identici. Questi test fanno passare OGNI esercizio
e OGNI domanda del quiz sia dalla chat (bot.py, con una chat finta) sia dalle API della mini app, e
confrontano esito e testo della soluzione/spiegazione del libro. Poi provano le API su un server vero
(localhost): firma obbligatoria, richieste malformate rifiutate, nessuno stato sul server."""
import asyncio
import copy
from html import unescape
import json
import random
import re
import socket
from types import SimpleNamespace
import unittest

from tornado.httpclient import AsyncHTTPClient

import app
import bot
from tutor import book_quiz, render, webapp
from tutor import kb as kbmod
from tutor.texts import T

from tests.test_foundations import FakeChat
from tests.test_webapp import TOKEN, FakeApplication, sign, user_fields

KB = bot.KB


def plain(html):
    """Testo visibile di un messaggio HTML della chat, senza spazi (le due interfacce impaginano diversamente)."""
    return re.sub(r'\s+', '', unescape(re.sub(r'<[^>]+>', '', html)))


def flat(nodes):
    return re.sub(r'\s+', '', webapp.nodes_text(nodes))


def answers_for(e):
    """Risposte di prova: quella del libro (breve e completa), una parziale e una sbagliata."""
    out = [e.get('answer_core') or '', e.get('answer') or '', 'xyz qwerty']
    if e['check_mode'] == 'parti':
        parts = e.get('parts') or []
        out.append('\n'.join(f"{p['label']}) {p['answer_core']}" for p in parts))
        out.append('\n'.join(f"{p['label']}) {p['answer_core'] if i else 'nope'}" for i, p in enumerate(parts)))
        out.append(', '.join(p['answer_core'] for p in parts))
    words = (e.get('answer_core') or '').split()
    if len(words) > 1:
        out.append(words[0])
    return [a for a in dict.fromkeys(out) if a.strip()]


class ChatParityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bot.STATE.clear()
        self.chat = FakeChat()
        self.update = SimpleNamespace(effective_chat=self.chat, callback_query=None, message=None)

    def chat_session(self, lang, kind, payload):
        s = bot.st(self.chat.id)
        s['lang'] = lang
        s['mode'] = kind
        s[kind] = payload
        self.chat.messages.clear()
        return s

    async def chat_exercise(self, lang, e, typed=None, choice=None, reveal=False):
        self.chat_session(lang, 'ex', {'id': 'p', 'ch': e['ch'], 'items': [e['source_id']], 'idx': 0, 'shown': False,
                                       'graded': False, 'score': 0, 'done': 0, 'skipped': 0})
        if reveal:
            await bot.ex_reveal(self.update, None, self.chat.id)
        elif choice is not None:
            await bot.ex_grade_choice(self.update, None, self.chat.id, choice)
        else:
            await bot.ex_answer_typed(self.update, None, self.chat.id, typed)
        return self.chat.messages[-1]['text'] if self.chat.messages else ''

    def assert_same_exercise(self, lang, e, chat_text, res, what):
        self.assertEqual(T[lang]['ex_right'] in chat_text, bool(res.get('good')), what)
        self.assertIn(flat(res['solution']), plain(chat_text), what)

    async def test_every_exercise_graded_like_the_chat(self):
        checked = 0
        for e in webapp.exercise_items(KB):
            mode = e['check_mode']
            if mode == 'scelta_multipla':
                for j in range(len(e['options'])):
                    text = await self.chat_exercise('it', e, choice=j)
                    res = webapp.grade_exercise(KB, 'it', e['source_id'], 'choice', j)
                    self.assert_same_exercise('it', e, text, res, (e['source_id'], j))
                    checked += 1
                for typed in ('a', 'B)', e['options'][-1]):
                    text = await self.chat_exercise('it', e, typed=typed)
                    res = webapp.grade_exercise(KB, 'it', e['source_id'], 'answer', typed)
                    self.assert_same_exercise('it', e, text, res, (e['source_id'], typed))
            elif mode == 'autovalutazione':
                text = await self.chat_exercise('it', e, typed='my answer')
                res = webapp.grade_exercise(KB, 'it', e['source_id'], 'answer', 'my answer')
                self.assertTrue(res['self'])
                self.assertIn(T['it']['ex_self_ask'], text)
                self.assertIn(flat(res['solution']), plain(text))
            else:
                for typed in answers_for(e):
                    text = await self.chat_exercise('it', e, typed=typed)
                    res = webapp.grade_exercise(KB, 'it', e['source_id'], 'answer', typed)
                    self.assert_same_exercise('it', e, text, res, (e['source_id'], typed))
                    if mode == 'parti':
                        right = sum(p['ok'] for p in res['parts'])
                        self.assertIn(T['it']['ex_parts'].format(c=right, t=len(res['parts'])), text)
                    checked += 1
            # «Mostra la soluzione»: zero punti (o autovalutazione), come in chat
            text = await self.chat_exercise('en', e, reveal=True)
            res = webapp.grade_exercise(KB, 'en', e['source_id'], 'reveal')
            if mode == 'autovalutazione':
                self.assertTrue(res['self'])
            else:
                self.assertIs(res['good'], False)
                self.assertIn(T['en']['ex_shown'], text)
            self.assertIn(flat(res['solution']), plain(text))
        self.assertGreater(checked, 600)

    async def chat_quiz(self, lang, ref_item, given):
        self.chat_session(lang, 'quiz', {'id': 'p', 'pool': [ref_item], 'idx': 0, 'score': 0, 'answered': False,
                                         'wrong': [], 'chapter': None, 'redo': False})
        await bot.quiz_feedback(self.update, None, self.chat.id, given)
        return self.chat.messages[-1]['text']

    async def test_every_quiz_question_graded_like_the_chat(self):
        rng = random.Random(7)
        langs = {'it': None, 'en': None}
        count = 0
        for n, ref in enumerate(book_quiz.quiz_items(KB)):
            lang = 'it' if n % 3 else 'en'
            item = book_quiz.resolve(KB, ref)
            q = webapp.quiz_question(KB, lang, ref, rng)
            if ref['type'] == 'tf':
                answers = [(True, True), (False, False)]
            elif ref['type'] == 'fix':
                answers = [(0, 0), (1, 1)]
            else:
                answers = [(j, j) for j in range(len(item['options']))]
            for chat_given, web_given in answers:
                chat_ref = dict(ref)
                if ref['type'] == 'fix':                 # stesso ordine di opzioni nelle due interfacce
                    chat_ref['opts'] = list(q['options'])
                    chat_ref['answer_idx'] = q['options'].index(item['good'])
                text = await self.chat_quiz(lang, chat_ref, chat_given)
                res = webapp.grade_quiz(KB, lang, ref['type'], ref['ref'], web_given,
                                        q['options'] if ref['type'] == 'fix' else None)
                self.assertEqual(T[lang]['quiz_right'] in text, res['good'], (ref, chat_given))
                self.assertTrue(plain(text).endswith(flat(res['body'])), ref)
                count += 1
            # la domanda mostra lo stesso testo della chat
            chat_q = render.quiz_question(KB, lang, {**ref, 'opts': q['options']}, item, 1, 10,
                                          q['options'] if ref['type'] == 'fix' else None)
            for part in (q['ask'], q['sub'], q['text']):
                self.assertIn(flat(part), plain(chat_q), ref)
            for o in q['options']:
                self.assertIn(re.sub(r'\s+', '', o), plain(chat_q), ref)
            langs[lang] = True
        self.assertGreater(count, 3500)
        self.assertTrue(all(langs.values()))


class ContentParityTests(unittest.TestCase):
    def test_theory_text_identical_to_the_chat_pages(self):
        for n in KB['_chapters']:
            chat = ''.join(plain(render.clean_for_display(p)) for p in kbmod.chapter_pages(KB, n))
            web = ''.join(flat(b['h']) for b in webapp.theory_payload(KB, n)['blocks'])
            self.assertEqual(chat, web, n)

    def test_theory_keeps_the_book_formatting(self):
        blocks = webapp.theory_payload(KB, 5)['blocks']
        tags = json.dumps(blocks)
        for tag in ('"b"', '"i"'):
            self.assertIn(tag, tags)
        self.assertEqual({b['k'] for b in blocks} - {'para', 'bullet', 'heading', 'table', 'pre'}, set())

    def test_exercise_prompts_identical_to_the_chat(self):
        for lang in ('it', 'en'):
            for n in KB['_chapters']:
                items = webapp.exercises_payload(KB, n, lang)['items']
                self.assertEqual([i['id'] for i in items], [e['source_id'] for e in KB['exercises']
                                                             if e['ch'] == n and e.get('quiz_eligible', True)])
                for it in items:
                    e = webapp._exercise(KB, it['id'])
                    chat = plain(render.exercise_prompt(KB, lang, e, 1, 1))
                    self.assertIn(flat(it['instr']) + flat(it['q']), chat, it['id'])
                    if e.get('target'):
                        self.assertEqual(it['q'][1][0], 'b')          # bersaglio in grassetto sottolineato

    def test_quiz_mix_is_the_chat_mix(self):
        for chapter in (None, 5, 12, 1):
            seed = random.Random(3)
            web = webapp.quiz_payload(KB, 'it', chapter, random.Random(3))['questions']
            pool = book_quiz.build_pool(KB, chapter, book_quiz.QUIZ_SIZE, seed)
            self.assertEqual([q['ref'] for q in web], [r['ref'] for r in pool])
            self.assertEqual(len(web), min(10, len(book_quiz.quiz_items(KB, chapter))))
        mixed = webapp.quiz_payload(KB, 'it')['questions']
        types = [q['type'] for q in mixed]
        self.assertGreaterEqual(types.count('fix'), 4)
        self.assertGreaterEqual(types.count('mcq'), 2)

    def test_html_nodes_are_safe_and_complete(self):
        nodes = webapp.html_nodes('<b>a &amp; <i>b</i></b> <script>alert(1)</script> <a href="x">c</a> '
                                  '<blockquote expandable>🇮🇹 <i>nota</i></blockquote>')
        self.assertEqual(nodes, [['b', ['a & ', ['i', ['b']]]], ' alert(1) c ', ['bqx', ['🇮🇹 ', ['i', ['nota']]]]])
        self.assertEqual(webapp.html_nodes(''), [])
        # un testo con «<» resta testo
        self.assertEqual(webapp.nodes_text(webapp.html_nodes('x &lt;b&gt; y')), 'x <b> y')

    def test_chapter_index_in_reference(self):
        p = webapp.reference_payload(KB)
        self.assertEqual([c['n'] for c in p['chapters']], list(range(1, 26)))
        self.assertEqual(sum(c['ex'] for c in p['chapters']), len(webapp.exercise_items(KB)))
        self.assertEqual(sum(c['q'] for c in p['chapters']), len(book_quiz.quiz_items(KB)))
        self.assertEqual([x['id'] for x in p['parts']], ['I', 'II', 'III', 'IV', 'V'])
        self.assertEqual(p['chapters'][4]['it'], 'Articoli: a, an, the e articolo zero')

    def test_bad_inputs_rejected(self):
        bad = [lambda: webapp.grade_exercise(KB, 'it', 'nope', 'answer', 'x'),
               lambda: webapp.grade_exercise(KB, 'it', 'ch01-A-1', 'answer', ''),
               lambda: webapp.grade_exercise(KB, 'it', 'ch01-A-1', 'answer', 'x' * 3000),
               lambda: webapp.grade_exercise(KB, 'it', 'ch01-A-1', 'choice', 0),
               lambda: webapp.grade_exercise(KB, 'it', 'ch01-A-1', 'hack'),
               lambda: webapp.grade_exercise(KB, 'it', ['ch01-A-1'], 'reveal'),
               lambda: webapp.theory_payload(KB, 99),
               lambda: webapp.quiz_payload(KB, 'it', 99),
               lambda: webapp.search_payload(KB, 'x' * 500)]
        mcq = next(e for e in webapp.exercise_items(KB) if e['check_mode'] == 'scelta_multipla')
        bad += [lambda: webapp.grade_exercise(KB, 'it', mcq['source_id'], 'choice', 9),
                lambda: webapp.grade_exercise(KB, 'it', mcq['source_id'], 'choice', True),
                lambda: webapp.grade_exercise(KB, 'it', mcq['source_id'], 'answer', 'zz')]
        fix = KB['fixes'][0]
        tf = next(r for r in book_quiz.quiz_items(KB) if r['type'] == 'tf')
        bad += [lambda: webapp.grade_quiz(KB, 'it', 'fix', fix['id'], 0, ['a', 'b']),
                lambda: webapp.grade_quiz(KB, 'it', 'fix', fix['id'], 2, [fix['bad'], fix['good']]),
                lambda: webapp.grade_quiz(KB, 'it', 'tf', tf['ref'], 1),
                lambda: webapp.grade_quiz(KB, 'it', 'mcq', tf['ref'], 0),
                lambda: webapp.grade_quiz(KB, 'it', 'tf', 'nope', True)]
        for fn in bad:
            with self.assertRaises(webapp.BadRequest):
                fn()

    def test_search_like_spiega(self):
        self.assertEqual(webapp.search_payload(KB, 'present perfect'), {'kind': 'chapter', 'n': 10})
        self.assertEqual(webapp.search_payload(KB, 'went'), {'kind': 'verbs', 'q': 'go'})
        self.assertEqual(webapp.search_payload(KB, 'gerund')['kind'], 'glossary')
        self.assertEqual(webapp.search_payload(KB, 'xyzzy'), {'kind': 'none'})

    def test_chat_output_unchanged_by_the_refactor(self):
        """quiz_question/quiz_feedback/exercise_prompt ora riusano le parti condivise: stessa uscita di prima."""
        e = KB['exercises'][0]
        self.assertEqual(render.exercise_prompt(KB, 'it', e, 1, 8).split('\n\n', 1)[1].split('\n<i>')[0],
                         render.exercise_parts(KB, 'it', e)[0] + '\n\n' + render.quote(render.exercise_parts(KB, 'it', e)[1]))
        ref = next(r for r in book_quiz.quiz_items(KB) if r['type'] == 'tf')
        item = book_quiz.resolve(KB, ref)
        full = render.quiz_feedback(KB, 'it', ref, item, True, 1, 1)
        self.assertEqual(full, render.feedback_head('it', True, 1, 1) + '\n\n' + render.quiz_feedback_body(KB, 'it', ref, item))
        self.assertIs(bot.clean_for_display, render.clean_for_display)


class StudyApiServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            self.port = s.getsockname()[1]
        self.saved_url = bot.WEBAPP_URL
        self.ptb = FakeApplication()
        self.stop = asyncio.Event()
        self.task = asyncio.create_task(app.serve_webhook(
            TOKEN, 'https://tutor.example.onrender.com', self.port, self.stop, self.ptb))
        for _ in range(100):
            if 'start' in self.ptb.calls:
                break
            await asyncio.sleep(0.01)
        self.client = AsyncHTTPClient()
        self.auth = {'Authorization': 'tma ' + sign(user_fields())}

    async def asyncTearDown(self):
        self.stop.set()
        await asyncio.wait_for(self.task, 5)
        bot.WEBAPP_URL = self.saved_url

    async def call(self, path, body=None, headers=None, raw=None):
        headers = dict(self.auth if headers is None else headers)
        kw = {'method': 'GET'}
        if body is not None or raw is not None:
            headers.setdefault('Content-Type', 'application/json')
            kw = {'method': 'POST', 'body': raw if raw is not None else json.dumps(body)}
        r = await self.client.fetch(f'http://127.0.0.1:{self.port}{path}', headers=headers, raise_error=False, **kw)
        return r.code, json.loads(r.body) if r.body else None

    async def test_every_endpoint_requires_the_telegram_signature(self):
        for path, body in (('/api/theory?n=1', None), ('/api/exercises?n=1', None), ('/api/quiz', None),
                           ('/api/search?q=if', None), ('/api/exercise/check', {'id': 'ch01-A-1', 'action': 'reveal'}),
                           ('/api/quiz/check', {'type': 'tf', 'ref': 'x', 'given': True})):
            for headers in ({}, {'Authorization': 'tma ' + sign(user_fields(), '999:OTHER')}):
                with self.assertLogs('tutor-web', level='INFO'):
                    code, data = await self.call(path, body, headers)
                self.assertEqual((code, data), (401, {'error': 'unauthorized'}), path)

    async def test_theory_exercises_quiz_round_trip(self):
        code, theory = await self.call('/api/theory?n=5')
        self.assertEqual(code, 200)
        self.assertGreater(len(theory['blocks']), 50)
        code, ex = await self.call('/api/exercises?n=1&lang=en')
        self.assertEqual((code, ex['lang'], len(ex['items'])), (200, 'en', 8))
        code, res = await self.call('/api/exercise/check', {'id': 'ch01-A-1', 'lang': 'it', 'action': 'answer', 'value': 'noun'})
        self.assertEqual((code, res['good']), (200, True))
        self.assertIn('Soluzione del libro', webapp.nodes_text(res['solution']))
        code, quiz = await self.call('/api/quiz?lang=it&ch=5')
        self.assertEqual((code, len(quiz['questions'])), (200, 10))
        self.assertTrue(all(q['ch'] == 5 for q in quiz['questions']))
        for q in quiz['questions']:
            given = True if q['type'] == 'tf' else 0
            code, res = await self.call('/api/quiz/check', {'type': q['type'], 'ref': q['ref'], 'given': given,
                                                           'options': q['options'], 'lang': 'it'})
            self.assertEqual(code, 200)
            self.assertIsInstance(res['good'], bool)
            self.assertTrue(res['body'])
        code, res = await self.call('/api/search?q=passivo')
        self.assertEqual(res, {'kind': 'chapter', 'n': 14})

    async def test_malformed_requests_rejected_without_details(self):
        for path, body, raw, headers in (
                ('/api/theory?n=abc', None, None, None), ('/api/theory?n=99', None, None, None),
                ('/api/theory', None, None, None), ('/api/quiz?ch=0', None, None, None),
                ('/api/exercise/check', None, 'not json', None), ('/api/exercise/check', None, '[1]', None),
                ('/api/exercise/check', {'id': 'nope', 'action': 'reveal'}, None, None),
                ('/api/exercise/check', None, json.dumps({'id': 'ch01-A-1', 'action': 'answer', 'value': 'x' * 9000}), None),
                ('/api/exercise/check', {'id': 'ch01-A-1', 'action': 'reveal'}, None,
                 {**self.auth, 'Content-Type': 'text/plain'}),
                ('/api/quiz/check', {'type': 'tf', 'ref': 'nope', 'given': True}, None, None)):
            with self.assertLogs('tutor-web', level='INFO'):
                code, data = await self.call(path, body, headers, raw)
            self.assertEqual((code, data), (400, {'error': 'bad_request'}), path)

    async def test_server_keeps_no_student_state(self):
        before = {k for k in KB if k.startswith('_webapp')}
        for _ in range(3):
            await self.call('/api/exercise/check', {'id': 'ch01-A-1', 'lang': 'it', 'action': 'answer', 'value': 'verb'})
        after = {k for k in KB if k.startswith('_webapp')}
        self.assertLessEqual(after - before, {'_webapp_ex', '_webapp_quiz'})      # solo indici del libro
        self.assertEqual(bot.STATE.get(279058397), None)                         # la chat non viene toccata


if __name__ == '__main__':
    unittest.main()
