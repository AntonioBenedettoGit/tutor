"""Regressioni fase 1. Tutto offline: nessuna richiesta a Telegram."""
import asyncio
import copy
import io
import json
import logging
from html.parser import HTMLParser
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

import bot
import app
from tutor import kb
from tutor.content import prepare_content, target_span
from tutor.logging_config import RedactingFormatter, configure_logging
from tutor.texts import T

ROOT = Path(__file__).resolve().parents[1]


class StrictHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []

    def handle_starttag(self, tag, attrs):
        assert tag in ('b', 'i', 's', 'u', 'code', 'pre', 'blockquote'), tag
        if tag == 'blockquote':
            assert attrs in ([], [('expandable', None)]), attrs
            assert 'blockquote' not in self.stack          # Telegram: niente citazioni annidate
        else:
            assert not attrs
        self.stack.append(tag)

    def handle_endtag(self, tag):
        assert self.stack.pop() == tag


class FakeChat:
    id = 101

    def __init__(self):
        self.messages = []

    async def send_message(self, text, reply_markup=None, parse_mode=None):
        assert text and len(text) <= 4096
        if parse_mode == 'HTML':
            parser = StrictHTML()
            parser.feed(text)
            parser.close()
            assert not parser.stack
        if reply_markup:
            for row in getattr(reply_markup, 'inline_keyboard', ()):
                for button in row:
                    assert len(button.text) <= 64
                    if button.callback_data:
                        assert len(button.callback_data.encode()) <= 64
        self.messages.append({'text': text, 'keyboard': reply_markup, 'parse_mode': parse_mode})
        return SimpleNamespace(message_id=len(self.messages))


def inline_rows(markup):
    return getattr(markup, 'inline_keyboard', ()) if markup else ()


def query_update(chat, data):
    async def edit_text(text, parse_mode=None, reply_markup=None):
        # una modifica (pagine di teoria, navigazione) viene registrata come ultimo messaggio
        await chat.send_message(text, reply_markup=reply_markup, parse_mode=parse_mode)
        chat.messages[-1]['edited'] = True
    q = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_reply_markup=AsyncMock(),
                        edit_message_text=AsyncMock(side_effect=edit_text))
    return SimpleNamespace(effective_chat=chat, callback_query=q, message=None)


def find_callback(chat, predicate):
    for message in reversed(chat.messages):
        if message['keyboard']:
            for row in inline_rows(message['keyboard']):
                for button in row:
                    if button.callback_data and predicate(button.callback_data):
                        return button.callback_data
    raise AssertionError('Pulsante non trovato')


class ContentTests(unittest.TestCase):
    def test_original_kb_not_modified(self):
        path = ROOT / 'data/kb.json'
        before = path.read_bytes()
        loaded = kb.load_kb()
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(len(loaded['exercises']), 270)
        self.assertEqual(len(loaded['chapters']), 25)
        self.assertEqual(len(loaded['verbs']), 145)

    def test_all_fifteen_targets_are_unique(self):
        targeted = [e for e in bot.KB['exercises'] if e.get('target')]
        self.assertEqual(len(targeted), 15)
        self.assertEqual(len({e['id'] for e in targeted}), 15)
        for e in targeted:
            a, b = target_span(e['q'], e['target'])
            self.assertEqual(e['q'][a:b], e['target'])

    def test_bad_targets_rejected(self):
        for text, target in [('test test', 'test'), ('a speech', 'missing')]:
            with self.assertRaises(ValueError):
                target_span(text, target)

    def test_known_mcqs_restored_as_open_exercises(self):
        # Il parser fase 4 ripristina la consegna; gli esercizi sono di nuovo valutati.
        for name, prompt, mode in [('ch12-main-7', '(already / see)', 'automatico'),
                                   ('ch20-main-2', '(high / higher / highest)', 'parti')]:
            e = bot.EXERCISES[name]
            self.assertIn(prompt, e['q'])
            self.assertIsNone(e['options'])
            self.assertIsNone(e['answer_idx'])
            self.assertTrue(e['quiz_eligible'])
            self.assertEqual(e['check_mode'], mode)

    def test_conflicting_labels_not_quizzed(self):
        # Confronto sensibile alle maiuscole: «I love Summer.» ✗ / «I love summer.» ✓ restano entrambi.
        labels = {}
        for e in bot.KB['examples']:
            if e.get('quiz_eligible', True):
                labels.setdefault(' '.join(e['t'].split()), set()).add(e['ok'])
        self.assertTrue(all(len(values) == 1 for values in labels.values()))
        pair = {e['t']: e for e in bot.KB['examples'] if e['t'] in ('I love Summer.', 'I love summer.')}
        self.assertEqual({e['ok'] for e in pair.values()}, {True, False})
        self.assertTrue(all(e['quiz_eligible'] for e in pair.values()))

    def test_book_fragments_kept_but_not_quizzed(self):
        texts = {e['t']: e for e in bot.KB['examples']}
        for t in ('…every.', '…where is the station?', '…why didn’t she call.', 'have'):
            self.assertIn(t, texts)
            self.assertFalse(texts[t]['quiz_eligible'])

    def test_incomplete_fixes_excluded(self):
        for e in bot.KB['fixes']:
            if e['good'] in ('A problem', 'The book (that', 'Most people (general'):
                self.assertFalse(e['quiz_eligible'])

    def test_unbalanced_dialogues_excluded(self):
        for e in bot.KB['examples']:
            if e['t'].count('“') != e['t'].count('”'):
                self.assertFalse(e['quiz_eligible'])

    def test_corrected_exercises_do_not_depend_on_list_order(self):
        raw = json.loads((ROOT / 'data/kb.json').read_text())
        raw['exercises'].reverse()
        prepare_content(raw)
        self.assertEqual(sum(bool(e.get('target')) for e in raw['exercises']), 15)

    def _overrides(self, doc):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / 'patches.json'
        path.write_text(json.dumps(doc), encoding='utf-8')
        return path

    def test_mismatched_correction_fails_closed(self):
        raw = json.loads((ROOT / 'data/kb.json').read_text())
        doc = json.loads((ROOT / 'data/content_overrides.json').read_text())
        doc['exercises'].append({'id': 'test-mismatch', 'match': {'source_id': 'ch01-A-1', 'q': 'non esiste'},
                                 'set': {'answer': 'x'}, 'reason': 'test'})
        with self.assertRaisesRegex(ValueError, 'test-mismatch'):
            prepare_content(raw, self._overrides(doc))
        raw = json.loads((ROOT / 'data/kb.json').read_text())
        next(e for e in raw['examples'] if e['t'] == 'have' and not e['ok'])['t'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'ex-ch06-not-have'):
            prepare_content(raw)

    def test_duplicate_patch_id_rejected(self):
        raw = json.loads((ROOT / 'data/kb.json').read_text())
        doc = json.loads((ROOT / 'data/content_overrides.json').read_text())
        doc['examples'].append(doc['examples'][0])
        with self.assertRaisesRegex(ValueError, 'duplicato'):
            prepare_content(raw, self._overrides(doc))

    def test_book_errors_not_corrected(self):
        # Decisione utente: errori del libro mostrati in originale, nessuna correzione/nota.
        doc = json.loads((ROOT / 'data/content_overrides.json').read_text())
        self.assertEqual(doc['exercises'], [])
        self.assertEqual(doc['fixes'], [])
        e = bot.EXERCISES['ch15-main-7']
        self.assertIn('I won’t lend you the car', e['q'])
        self.assertTrue(e['answer'].startswith('as long as'))
        self.assertTrue(bot.EXERCISES['ch22-B-5']['answer'].startswith('Although'))
        for name in ('ch15-main-7', 'ch22-B-5', 'ch06-A-3', 'ch13-main-8', 'ch13-main-10', 'ch19-A-4', 'ch22-B-8'):
            self.assertNotIn('editorial_note', bot.EXERCISES[name])
            self.assertNotIn(name, bot.KB['_notes_it']['exercises'])

    def test_quarantine_respected_by_quiz_pool(self):
        from tutor import book_quiz
        damaged = copy.deepcopy(bot.KB)
        damaged.pop('_index', None)
        for section in ['exercises', 'examples', 'fixes', '_reviewed_quiz']:
            for e in damaged[section]:
                e['quiz_eligible'] = False
        self.assertEqual(bot.build_quiz_pool(damaged), [])
        for chapter in range(1, 26):
            available = len(book_quiz.quiz_items(bot.KB, chapter))
            self.assertGreaterEqual(available, 10)
            for _ in range(5):
                pool = bot.build_quiz_pool(bot.KB, chapter)
                self.assertEqual(len(pool), 10)
                self.assertEqual(len({(q['type'], q['ref']) for q in pool}), 10)
                for ref in pool:
                    item = book_quiz.resolve(bot.KB, ref)
                    self.assertEqual(item['ch'], chapter)
                    self.assertTrue(item['quiz_eligible'])

    def test_translation_keys_match(self):
        self.assertEqual(set(T['it']), set(T['en']))

    def test_launcher_has_sequential_updates_and_handlers(self):
        application = app.build_app('123456:OFFLINE_TEST')
        self.assertEqual(application.concurrent_updates, 1)  # max un update alla volta
        self.assertEqual(len(application.handlers[0]), 13)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bot.STATE.clear()
        self.chat = FakeChat()
        self.update = SimpleNamespace(effective_chat=self.chat, callback_query=None,
                                      message=SimpleNamespace(text='speech'))
        self.ctx = SimpleNamespace(args=[])
        bot.st(self.chat.id)['lang'] = 'it'
        oks = [e for e in bot.KB['examples'] if e['ch'] == 1 and e['ok'] and e['quiz_eligible']][:3]
        self.pool = [{'type': 'tf', 'ref': e['id'], 'ch': 1} for e in oks]

    async def start(self, pool=None):
        await bot.start_quiz(self.update, self.ctx, self.chat.id, pre_pool=pool or self.pool)

    async def click(self, data):
        update = query_update(self.chat, data)
        await bot.on_callback(update, self.ctx)
        return update.callback_query

    def state(self):
        return bot.st(self.chat.id)

    async def test_correct_answer_counted_once(self):
        await self.start()
        answer = find_callback(self.chat, lambda d: d.endswith(':tf:1'))
        await self.click(answer)
        duplicate = await self.click(answer)
        self.assertEqual(self.state()['quiz']['score'], 1)
        duplicate.answer.assert_awaited_once_with(T['it']['expired'])

    async def test_next_requires_answer(self):
        await self.start()
        data = bot.session_data('quiz', self.state()['quiz'], 'next')
        await self.click(data)
        self.assertEqual(self.state()['quiz']['idx'], 0)

    async def test_double_next_does_not_skip(self):
        await self.start()
        await self.click(find_callback(self.chat, lambda d: d.endswith(':tf:1')))
        data = find_callback(self.chat, lambda d: d.endswith(':next'))
        await self.click(data)
        await self.click(data)
        self.assertEqual(self.state()['quiz']['idx'], 1)
        self.assertFalse(self.state()['quiz']['answered'])

    async def test_old_answer_cannot_answer_new_question(self):
        await self.start()
        old = find_callback(self.chat, lambda d: d.endswith(':tf:1'))
        await self.click(old)
        await self.click(find_callback(self.chat, lambda d: d.endswith(':next')))
        await self.click(old)
        self.assertEqual(self.state()['quiz']['score'], 1)
        self.assertFalse(self.state()['quiz']['answered'])

    async def test_old_stop_cannot_stop_new_session(self):
        await self.start()
        old = find_callback(self.chat, lambda d: d.endswith(':stop'))
        await self.start()
        new_id = self.state()['quiz']['id']
        await self.click(old)
        self.assertEqual(self.state()['quiz']['id'], new_id)

    async def test_legacy_callbacks_rejected(self):
        await self.start()
        for data in ['quiz:next','quiz:tf:1','quiz:ans:0','quiz:stop','ex:next','page:1','gl:0']:
            await self.click(data)
        self.assertEqual(self.state()['quiz']['idx'], 0)
        self.assertEqual(self.state()['quiz']['score'], 0)

    async def test_concurrent_double_answer_only_scores_once(self):
        await self.start()
        data = find_callback(self.chat, lambda d: d.endswith(':tf:1'))
        updates = [query_update(self.chat, data) for _ in range(2)]
        async def yield_to_other_callback(*args, **kwargs):
            await asyncio.sleep(0)
        for update in updates:
            update.callback_query.answer.side_effect = yield_to_other_callback
        await asyncio.gather(*(bot.on_callback(update, self.ctx) for update in updates))
        self.assertEqual(self.state()['quiz']['score'], 1)

    async def test_invalid_answer_type_rejected(self):
        await self.start()
        await self.click(bot.session_data('quiz', self.state()['quiz'], 'ans:0'))
        self.assertFalse(self.state()['quiz']['answered'])

    async def test_invalid_mcq_indices_rejected(self):
        e = next(e for e in bot.KB['exercises'] if e['options'] and len(e['options']) == 2)
        pool = [{'type': 'mcq', 'ref': e['source_id'], 'ch': e['ch']}]
        await self.start(pool)
        for value in ['-1','2','9999999999999','²','x','0:1']:
            await self.click(bot.session_data('quiz',self.state()['quiz'],'ans:'+value))
        self.assertFalse(self.state()['quiz']['answered'])
        await self.click(bot.session_data('quiz',self.state()['quiz'],f"ans:{e['answer_idx']}"))
        self.assertEqual(self.state()['quiz']['score'], 1)

    async def test_keyboard_removed_after_answer(self):
        await self.start()
        q = await self.click(find_callback(self.chat, lambda d: d.endswith(':tf:1')))
        q.edit_message_reply_markup.assert_awaited_once_with(reply_markup=None)

    async def test_deleted_message_does_not_break_session(self):
        from telegram.error import BadRequest
        await self.start()
        update = query_update(self.chat, find_callback(self.chat, lambda d: d.endswith(':tf:1')))
        update.callback_query.edit_message_reply_markup.side_effect = BadRequest('message not found')
        with self.assertLogs('tutor-bot', level='WARNING'):
            await bot.on_callback(update, self.ctx)
        self.assertEqual(self.state()['quiz']['score'],1)

    async def test_help_invalidates_quiz(self):
        await self.start()
        old = find_callback(self.chat, lambda d: d.endswith(':tf:1'))
        await bot.cmd_help(self.update,self.ctx)
        await self.click(old)
        self.assertIsNone(self.state()['quiz'])
        self.assertIsNone(self.state()['mode'])

    async def test_all_activity_transitions_clear_previous_sessions(self):
        calls = [lambda:bot.cmd_menu(self.update,self.ctx),
                 lambda:bot.cmd_start(self.update,self.ctx),
                 lambda:bot.cmd_lang(self.update,self.ctx),
                 lambda:bot.cmd_spiega(self.update,self.ctx),
                 lambda:bot.cmd_verbi(self.update,self.ctx),
                 lambda:bot.start_exercises(self.update,self.ctx,self.chat.id),
                 lambda:bot.send_chapter(self.update,self.ctx,self.chat.id,1),
                 lambda:bot.start_glossary(self.update,self.ctx,self.chat.id)]
        for call in calls:
            await self.start()
            await call()
            self.assertIsNone(self.state()['quiz'])
        await bot.cmd_verbi(self.update,self.ctx)
        await bot.ex_chapter(self.update,self.ctx,self.chat.id,1)
        self.assertEqual(self.state()['mode'],'ex')
        self.assertIsNotNone(self.state()['ex'])

    async def test_exercise_next_requires_solution_and_is_idempotent(self):
        await bot.ex_chapter(self.update,self.ctx,self.chat.id,1)
        ex=self.state()['ex']
        await self.click(bot.session_data('ex',ex,'next'))
        self.assertEqual(ex['idx'],0)
        show=bot.session_data('ex',ex,'show')
        await self.click(show)
        before=len(self.chat.messages)
        await self.click(show)
        self.assertEqual(len(self.chat.messages),before)
        if bot.current_exercise(ex)['check_mode']=='autovalutazione':
            await self.click(bot.session_data('ex',ex,'next'))
            self.assertEqual(ex['idx'],0)          # serve prima l'autovalutazione
            await self.click(bot.session_data('ex',ex,'self:1'))
        data=bot.session_data('ex',ex,'next')
        await self.click(data)
        await self.click(data)
        self.assertEqual(ex['idx'],1)

    async def test_self_assessment_scored_once(self):
        name = next(e['source_id'] for e in bot.KB['exercises'] if e['check_mode']=='autovalutazione')
        await bot.ex_chapter(self.update,self.ctx,self.chat.id,bot.EXERCISES[name]['ch'])
        ex=self.state()['ex']
        ex['idx']=ex['items'].index(name)
        self.update.message=SimpleNamespace(text='my attempt')
        await bot.on_text(self.update,self.ctx)
        self.assertIn('my attempt',self.chat.messages[-1]['text'])
        ok=bot.session_data('ex',ex,'self:1')
        await self.click(ok)
        await self.click(ok)
        await self.click(bot.session_data('ex',ex,'self:0'))
        self.assertEqual((ex['score'],ex['done']),(1,1))

    async def test_typed_answers_scored_against_the_book(self):
        e = bot.EXERCISES['ch21-main-6']
        for typed, good in [('arrived in', True), ('arrived at', False)]:
            await bot.ex_chapter(self.update,self.ctx,self.chat.id,e['ch'])
            ex=self.state()['ex']
            ex['idx']=ex['items'].index('ch21-main-6')
            self.update.message=SimpleNamespace(text=typed)
            await bot.on_text(self.update,self.ctx)
            self.assertEqual(ex['score'],int(good))
            self.assertIn(e['answer_explanation'].split()[0],self.chat.messages[-1]['text'])
            await bot.on_text(self.update,self.ctx)           # seconda risposta: ignorata
            self.assertEqual(ex['done'],1)

    async def test_old_exercise_skip_does_not_affect_new_session(self):
        await bot.ex_chapter(self.update,self.ctx,self.chat.id,1)
        old=bot.session_data('ex',self.state()['ex'],'skip')
        await bot.ex_chapter(self.update,self.ctx,self.chat.id,2)
        await self.click(old)
        self.assertEqual(self.state()['ex']['idx'],0)
        self.assertEqual(self.state()['ex']['ch'],2)

    async def test_old_page_rejected_after_opening_different_chapter(self):
        await bot.send_chapter(self.update,self.ctx,self.chat.id,1)
        old=find_callback(self.chat,lambda d:d.startswith('page:'))
        await bot.send_chapter(self.update,self.ctx,self.chat.id,2)
        await self.click(old)
        self.assertEqual(self.state()['page_idx'],0)
        current=find_callback(self.chat,lambda d:d.startswith('page:'))
        await self.click(current)
        await self.click(current)
        self.assertEqual(self.state()['page_idx'],1)

    async def test_glossary_selection_scoped_to_query(self):
        await bot.start_glossary_query(self.update,self.ctx,self.chat.id,'clause')
        old=find_callback(self.chat,lambda d:d.startswith('gl:'))
        await bot.start_glossary_query(self.update,self.ctx,self.chat.id,'article')
        before=len(self.chat.messages)
        await self.click(old)
        self.assertEqual(len(self.chat.messages),before)

    async def test_multipage_summary_markup(self):
        with patch.object(bot.kbmod,'explain_summary',return_value=['First','Second']):
            await bot.explain(self.update,self.ctx,self.chat.id,'present perfect')
        data=find_callback(self.chat,lambda d:d.startswith('page:'))
        await self.click(data)
        self.assertEqual(self.state()['page_idx'],1)
        self.assertIn('Second',self.chat.messages[-1]['text'])

    async def test_quiz_completion_clears_session(self):
        await self.start([self.pool[0]])
        await self.click(find_callback(self.chat,lambda d:d.endswith(':tf:1')))
        await self.click(find_callback(self.chat,lambda d:d.endswith(':next')))
        self.assertIsNone(self.state()['quiz'])
        self.assertIsNone(self.state()['mode'])

    async def test_targets_rendered_with_specific_instructions(self):
        for lang in ['it','en']:
            self.state()['lang']=lang
            for ch in [1,2,18]:
                await bot.ex_chapter(self.update,self.ctx,self.chat.id,ch)
                ex=self.state()['ex']
                for i,name in enumerate(ex['items']):
                    e=bot.EXERCISES[name]
                    if e.get('target'):
                        ex['idx']=i
                        await bot.send_exercise(self.update,self.ctx,self.chat.id)
                        text=self.chat.messages[-1]['text']
                        self.assertIn('<b>'+e['target']+'</b>',text)
                        self.assertIn('<u>'+e['target']+'</u>',text)
                        self.assertNotIn('bold word',text)
                        self.assertNotIn('underlined',text)
                        if ch==18:
                            self.assertIn('pronome' if lang=='it' else 'pronoun',text)
                        else:
                            self.assertIn('parte del discorso' if lang=='it' else 'part of speech',text)

    async def complete(self, e, lang):
        """Completa l'esercizio come uno studente che conosce la soluzione del libro."""
        ex=self.state()['ex']
        mode=e['check_mode']
        if mode=='scelta_multipla':
            await self.click(bot.session_data('ex',ex,f"ans:{e['answer_idx']}"))
        else:
            if mode=='parti':
                typed='\n'.join(f"{p['label']}) {p['answer_core']}" for p in e['parts'])
            else:
                typed=e['answer_core']
            self.update.message=SimpleNamespace(text=typed)
            await bot.on_text(self.update,self.ctx)
            if mode=='autovalutazione':
                await self.click(bot.session_data('ex',ex,'self:1'))

    async def test_every_exercise_completable_and_scored_both_languages(self):
        for lang in ['it','en']:
            self.state()['lang']=lang
            for ch in range(1,26):
                await bot.ex_chapter(self.update,self.ctx,self.chat.id,ch)
                ex=self.state()['ex']
                names=list(ex['items'])
                for name in names:
                    e=bot.EXERCISES[name]
                    shown=len(self.chat.messages)
                    await self.complete(e, lang)
                    self.assertTrue(ex['graded'], name)
                    text='\n'.join(m['text'] for m in self.chat.messages[shown:])
                    self.assertIn(f"p. {e['pdf_page']}", text)
                    note=bot.KB['_notes_it']['exercises'].get(name)
                    if note and lang=='it':
                        self.assertIn(bot.render.esc(note), text)
                    if lang=='en':
                        self.assertNotIn('🇮🇹', text)
                    await self.click(bot.session_data('ex',ex,'next'))
                self.assertIsNone(self.state()['ex'])
                self.assertIn(f"{len(names)}/{len(names)}", self.chat.messages[-1]['text'])

    async def test_html_special_characters_escaped(self):
        fake={'source_id':'fake-1','ch':1,'q':'A < B & speech.','target':'speech','instr':'<unsafe>',
              'group':'','answer':'test & <b>','check_mode':'autovalutazione','pdf_page':1,
              'answer_pdf_page':1,'source_number':1}
        with patch.dict(bot.EXERCISES,{'fake-1':fake}):
            await bot.ex_chapter(self.update,self.ctx,self.chat.id,1)
            ex=self.state()['ex']
            ex['items']=['fake-1']
            await bot.send_exercise(self.update,self.ctx,self.chat.id)
            text=self.chat.messages[-1]['text']
            self.assertIn('&lt;',text)
            self.assertIn('&amp;',text)
            self.assertNotIn('<unsafe>',text)
            self.update.message=SimpleNamespace(text='<script>&')
            await bot.on_text(self.update,self.ctx)
            self.assertIn('&lt;script&gt;&amp;',self.chat.messages[-1]['text'])

    async def test_render_and_feedback_all_eligible_quiz_items(self):
        from tutor import book_quiz
        refs = book_quiz.quiz_items(bot.KB)
        self.assertEqual(len(refs), 1810)
        for lang in ['it','en']:
            for original in refs:
                for correct in (True, False):
                    state=bot.enter_mode(self.chat.id,'quiz')
                    state['lang']=lang
                    state['quiz']={'id':'offline','pool':[copy.deepcopy(original)],'idx':0,'score':0,'answered':False}
                    await bot.send_next_question(self.update,self.ctx,self.chat.id)
                    ref=state['quiz']['pool'][0]
                    item=book_quiz.resolve(bot.KB,ref)
                    if ref['type']=='tf':
                        given=item['ok'] if correct else not item['ok']
                    else:
                        right=ref['answer_idx'] if ref['type']=='fix' else item['answer_idx']
                        given=right if correct else (right+1)%len(bot.quiz_options(ref))
                    await bot.quiz_feedback(self.update,self.ctx,self.chat.id,given)
                    self.assertEqual(state['quiz']['score'],int(correct))
                    text=self.chat.messages[-1]['text']
                    self.assertIn('📖',text)
                    if item.get('note') and ref['type']!='mcq':
                        self.assertIn(bot.render.esc(item['note']),text)
                    if 'page' in item:
                        self.assertIn(f"p. {item['page']}",text)

    async def test_valid_glossary_selection_then_duplicate_rejected(self):
        await bot.start_glossary_query(self.update,self.ctx,self.chat.id,'clause')
        data=find_callback(self.chat,lambda d:d.startswith('gl:'))
        await self.click(data)
        before=len(self.chat.messages)
        await self.click(data)
        self.assertEqual(len(self.chat.messages),before)
        self.assertIsNone(self.state()['glos'])

    async def test_two_chats_do_not_share_sessions(self):
        await self.start()
        old_id=self.state()['quiz']['id']
        other=FakeChat();other.id=202
        update=SimpleNamespace(effective_chat=other,callback_query=None,message=None)
        bot.st(other.id)['lang']='en'
        await bot.start_quiz(update,self.ctx,other.id,pre_pool=self.pool)
        self.assertNotEqual(old_id,bot.st(other.id)['quiz']['id'])
        self.assertEqual(self.state()['quiz']['id'],old_id)


class LoggingTests(unittest.TestCase):
    def test_token_redacted_in_message_arguments(self):
        token='123456:FAKE_AUDIT_TOKEN'
        record=logging.LogRecord('test',logging.INFO,'',1,'URL %s',
                                 ('https://api.telegram.org/bot'+token+'/getMe',),None)
        text=RedactingFormatter(token).format(record)
        self.assertNotIn(token,text)
        self.assertIn('[BOT_TOKEN]',text)

    def test_unknown_token_redacted_by_pattern(self):
        token='999999:ANOTHER_FAKE_TOKEN'
        record=logging.LogRecord('test',logging.ERROR,'',1,'bot'+token,(),None)
        self.assertNotIn(token,RedactingFormatter().format(record))

    def test_traceback_redacted(self):
        import sys
        token='123456:FAKE_AUDIT_TOKEN'
        try:
            raise RuntimeError('https://api.telegram.org/bot'+token+'/getMe')
        except RuntimeError:
            record=logging.LogRecord('test',logging.ERROR,'',1,'failure',(),sys.exc_info())
        text=RedactingFormatter(token).format(record)
        self.assertNotIn(token,text)
        self.assertIn('RuntimeError',text)

    def test_http_loggers_not_info(self):
        old={name:logging.getLogger(name).level for name in ['httpx','httpcore']}
        root=logging.getLogger();handlers=root.handlers[:];level=root.level
        try:
            root.handlers=[logging.StreamHandler(io.StringIO())]
            configure_logging('123456:FAKE')
            for name in old:
                self.assertEqual(logging.getLogger(name).level,logging.WARNING)
            self.assertIsInstance(root.handlers[0].formatter,RedactingFormatter)
        finally:
            root.handlers=handlers;root.setLevel(level)
            for name,value in old.items():logging.getLogger(name).setLevel(value)


if __name__ == '__main__':
    unittest.main()
