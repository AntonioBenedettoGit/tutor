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
        assert tag in ('b',), tag
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
            for row in reply_markup.inline_keyboard:
                for button in row:
                    if button.callback_data:
                        assert len(button.callback_data.encode()) <= 64
        self.messages.append({'text': text, 'keyboard': reply_markup, 'parse_mode': parse_mode})
        return SimpleNamespace(message_id=len(self.messages))


def query_update(chat, data):
    q = SimpleNamespace(data=data, answer=AsyncMock(), edit_message_reply_markup=AsyncMock())
    return SimpleNamespace(effective_chat=chat, callback_query=q, message=None)


def find_callback(chat, predicate):
    for message in reversed(chat.messages):
        if message['keyboard']:
            for row in message['keyboard'].inline_keyboard:
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
        for ch, prompt in [(12, '(already / see)'), (20, '(high / higher / highest)')]:
            e = next(e for e in bot.KB['exercises'] if e.get('id') == f'ch{ch:02d}-restore-prompt')
            self.assertIn(prompt, e['q'])
            self.assertIsNone(e['options'])
            self.assertIsNone(e['answer_idx'])
            self.assertFalse(e['quiz_eligible'])

    def test_conflicting_labels_not_quizzed(self):
        labels = {}
        for e in bot.KB['examples']:
            if e.get('quiz_eligible', True):
                text = ' '.join(e['t'].casefold().split())
                labels.setdefault(text, set()).add(e['ok'])
        self.assertTrue(all(len(values) == 1 for values in labels.values()))
        for e in bot.KB['examples']:
            if e['t'] == 'Thank you so much!':
                self.assertFalse(e['quiz_eligible'])

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

    def test_mismatched_correction_fails_closed(self):
        raw = json.loads((ROOT / 'data/kb.json').read_text())
        raw['exercises'][0]['q'] = 'Una nuova domanda non verificata'
        with self.assertRaisesRegex(ValueError, 'ch01-target-01'):
            prepare_content(raw)

    def test_duplicate_patch_id_rejected(self):
        raw = json.loads((ROOT / 'data/kb.json').read_text())
        doc = json.loads((ROOT / 'data/content_overrides.json').read_text())
        doc['exercises'].append(doc['exercises'][0])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'patches.json'
            path.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, 'duplicato'):
                prepare_content(raw, path)

    def test_quarantine_respected_by_quiz_pool(self):
        damaged = copy.deepcopy(bot.KB)
        for section in ['exercises', 'examples', 'fixes', '_reviewed_quiz']:
            for e in damaged[section]:
                e['quiz_eligible'] = False
        self.assertEqual(bot.build_quiz_pool(damaged), [])
        for chapter in range(1, 26):
            for _ in range(10):
                pool = bot.build_quiz_pool(bot.KB, chapter)
                self.assertEqual(len(pool), min(10, sum(q['ch'] == chapter for q in bot.KB['_reviewed_quiz'])))
                self.assertTrue(all(q['ch'] == chapter for q in pool))
                for q in pool:
                    if q['type'] == 'mcq':
                        self.assertNotIn(q.get('id'), ['ch12-restore-prompt','ch20-restore-prompt'])
                        self.assertNotIn('C H A P T E R', q['q'])
                    if q['type'] == 'fix':
                        self.assertNotEqual(q['good'], 'A problem')
                        self.assertEqual(q['good'].count('('), q['good'].count(')'))

    def test_translation_keys_match(self):
        self.assertEqual(set(T['it']), set(T['en']))

    def test_launcher_has_sequential_updates_and_handlers(self):
        application = app.build_app('123456:OFFLINE_TEST')
        self.assertEqual(application.concurrent_updates, 1)  # max un update alla volta
        self.assertEqual(len(application.handlers[0]), 12)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bot.STATE.clear()
        self.chat = FakeChat()
        self.update = SimpleNamespace(effective_chat=self.chat, callback_query=None,
                                      message=SimpleNamespace(text='speech'))
        self.ctx = SimpleNamespace(args=[])
        bot.st(self.chat.id)['lang'] = 'it'
        self.pool = [{'type': 'tf', 't': f'Test {i}.', 'ok': True, 'ch': 1} for i in range(3)]

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
        pool = [{'type':'mcq','ch':1,'q':'Choose','instr':'','options':['A','B'],
                 'answer_idx':1,'answer':'B'}]
        await self.start(pool)
        for value in ['-1','2','9999999999999','²','x','0:1']:
            await self.click(bot.session_data('quiz',self.state()['quiz'],'ans:'+value))
        self.assertFalse(self.state()['quiz']['answered'])
        await self.click(bot.session_data('quiz',self.state()['quiz'],'ans:1'))
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
        data=bot.session_data('ex',ex,'next')
        await self.click(data)
        await self.click(data)
        self.assertEqual(ex['idx'],1)

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
                for i,e in enumerate(ex['items']):
                    if e.get('target'):
                        ex['idx']=i
                        await bot.send_exercise(self.update,self.ctx,self.chat.id)
                        text=self.chat.messages[-1]['text']
                        self.assertIn('<b>'+e['target']+'</b>',text)
                        self.assertNotIn('bold word',text)
                        self.assertNotIn('underlined',text)
                        if ch==18:
                            self.assertIn('pronome' if lang=='it' else 'pronoun',text)
                        else:
                            self.assertIn('parte del discorso' if lang=='it' else 'part of speech',text)

    async def test_render_all_exercises_and_solutions_both_languages(self):
        for lang in ['it','en']:
            self.state()['lang']=lang
            for ch in range(1,26):
                await bot.ex_chapter(self.update,self.ctx,self.chat.id,ch)
                ex=self.state()['ex']
                for i in range(len(ex['items'])):
                    ex['idx']=i;ex['shown']=False
                    await bot.send_exercise(self.update,self.ctx,self.chat.id)
                    await bot.ex_show_answer(self.update,self.ctx,self.chat.id,typed=True)

    async def test_html_special_characters_escaped(self):
        await bot.ex_chapter(self.update,self.ctx,self.chat.id,1)
        ex=self.state()['ex']
        ex['items']=[{'q':'A < B & speech.','target':'speech','instr':'<unsafe>',
                     'group':'','answer':'test'}]
        await bot.send_exercise(self.update,self.ctx,self.chat.id)
        text=self.chat.messages[-1]['text']
        self.assertIn('&lt;',text)
        self.assertIn('&amp;',text)
        self.assertNotIn('<unsafe>',text)

    async def test_render_and_feedback_all_eligible_quiz_items(self):
        pool = bot.KB['_reviewed_quiz']
        self.assertEqual(len(pool), 160)
        for lang in ['it','en']:
            for original in pool:
                state=bot.enter_mode(self.chat.id,'quiz')
                state['lang']=lang
                state['quiz']={'id':'offline','pool':[copy.deepcopy(original)],'idx':0,'score':0,'answered':False}
                await bot.send_next_question(self.update,self.ctx,self.chat.id)
                item=state['quiz']['pool'][0]
                given=item['ok'] if item['type']=='tf' else item['answer_idx']
                await bot.quiz_feedback(self.update,self.ctx,self.chat.id,given)
                self.assertEqual(state['quiz']['score'],1)

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
