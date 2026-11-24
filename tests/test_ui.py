"""Fase UI: menu dei comandi, tastiera fissa, capitoli per Parte, progressi, teoria a pagine,
riepilogo del quiz. Tutto offline: nessuna richiesta a Telegram."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import bot
import app
from tutor import texts
from tutor.texts import COMMANDS, DESCRIPTION, SHORT_DESCRIPTION, T

from tests.test_foundations import FakeChat, find_callback, inline_rows, query_update


def buttons(message):
    return [b for row in inline_rows(message['keyboard']) for b in row]


class StaticUITests(unittest.TestCase):
    def test_command_menu_matches_registered_handlers(self):
        application = app.build_app('123456:OFFLINE_TEST')
        registered = set()
        for h in application.handlers[0]:
            registered |= set(getattr(h, 'commands', ()))
        self.assertEqual({c[0] for c in COMMANDS} | {'start'}, registered)
        self.assertIsNotNone(application.post_init)
        for name, it, en in COMMANDS:
            self.assertRegex(name, r'^[a-z0-9_]{1,32}$')
            for d in (it, en):
                self.assertTrue(1 <= len(d) <= 256)

    def test_profile_texts_within_telegram_limits(self):
        for lang in ('it', 'en'):
            self.assertLessEqual(len(DESCRIPTION[lang]), 512)
            self.assertLessEqual(len(SHORT_DESCRIPTION[lang]), 120)

    def test_same_keys_and_placeholders_in_both_languages(self):
        import string
        self.assertEqual(set(T['it']), set(T['en']))
        fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}
        for key in T['it']:
            self.assertEqual(fields(T['it'][key]), fields(T['en'][key]), key)

    def test_parts_cover_every_chapter_once(self):
        seen = []
        for p in bot.PART_ORDER:
            seen += bot.chapters_of_part(p)
        self.assertEqual(seen, list(range(1, 26)))
        self.assertEqual(bot.chapters_of_part('III'), list(range(8, 19)))
        self.assertEqual(set(texts.CHAPTER_IT), set(range(1, 26)))

    def test_progress_bar_and_stars(self):
        self.assertEqual(texts.progress_bar(0, 10), '▱' * 10)
        self.assertEqual(texts.progress_bar(3, 10), '▰' * 3 + '▱' * 7)
        self.assertEqual(texts.progress_bar(10, 10), '▰' * 10)
        self.assertEqual(texts.progress_bar(1, 24).count('▰') + texts.progress_bar(1, 24).count('▱'), 10)
        self.assertEqual(texts.stars(10, 10), '★★★★★')
        self.assertEqual(texts.stars(0, 10), '☆☆☆☆☆')
        self.assertEqual(texts.stars(0, 0), '☆☆☆☆☆')

    def test_reply_labels_both_languages(self):
        labels = texts.reply_labels()
        for lang in ('it', 'en'):
            for key in ('kb_quiz', 'kb_ex', 'kb_theory', 'kb_menu'):
                self.assertIn(T[lang][key], labels)
        markup = texts.reply_keyboard('it')
        self.assertTrue(markup.is_persistent and markup.resize_keyboard)


class ProfileSyncTests(unittest.IsolatedAsyncioTestCase):
    def fake_api(self, current_cmds=(), desc='', short=''):
        api = SimpleNamespace(
            get_my_commands=AsyncMock(return_value=list(current_cmds)),
            set_my_commands=AsyncMock(),
            get_my_description=AsyncMock(return_value=SimpleNamespace(description=desc)),
            set_my_description=AsyncMock(),
            get_my_short_description=AsyncMock(return_value=SimpleNamespace(short_description=short)),
            set_my_short_description=AsyncMock())
        return api

    async def test_writes_commands_and_descriptions_for_both_languages(self):
        api = self.fake_api()
        await bot._sync_profile(api)
        self.assertEqual(api.set_my_commands.await_count, 2)
        codes = [c.kwargs.get('language_code') for c in api.set_my_description.await_args_list]
        self.assertEqual(codes, [None, 'it'])
        it_cmds = api.set_my_commands.await_args_list[1].args[0]
        self.assertEqual(it_cmds[0].description, COMMANDS[0][1])

    async def test_no_write_when_already_up_to_date(self):
        from telegram import BotCommand
        api = self.fake_api()
        cmds = {None: [BotCommand(c[0], c[2]) for c in COMMANDS], 'it': [BotCommand(c[0], c[1]) for c in COMMANDS]}
        api.get_my_commands.side_effect = lambda **kw: cmds[kw.get('language_code')]
        api.get_my_description.side_effect = lambda **kw: SimpleNamespace(
            description=DESCRIPTION['it' if kw else 'en'])
        api.get_my_short_description.side_effect = lambda **kw: SimpleNamespace(
            short_description=SHORT_DESCRIPTION['it' if kw else 'en'])
        await bot._sync_profile(api)
        api.set_my_commands.assert_not_awaited()
        api.set_my_description.assert_not_awaited()
        api.set_my_short_description.assert_not_awaited()

    async def test_errors_never_stop_startup(self):
        from telegram.error import NetworkError
        api = self.fake_api()
        api.get_my_commands.side_effect = NetworkError('offline')
        with self.assertLogs('tutor-bot', level='WARNING'):
            await bot._sync_profile(api)


class FlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bot.STATE.clear()
        self.chat = FakeChat()
        self.update = SimpleNamespace(effective_chat=self.chat, callback_query=None,
                                      message=SimpleNamespace(text=''))
        self.ctx = SimpleNamespace(args=[])
        bot.st(self.chat.id)['lang'] = 'it'

    def state(self):
        return bot.st(self.chat.id)

    async def click(self, data):
        update = query_update(self.chat, data)
        await bot.on_callback(update, self.ctx)
        return update.callback_query

    async def type(self, text):
        self.update.message = SimpleNamespace(text=text)
        await bot.on_text(self.update, self.ctx)

    async def test_language_choice_installs_persistent_keyboard(self):
        self.state()['lang'] = None
        await self.click('lang:en')
        welcome, menu = self.chat.messages[-2:]
        self.assertEqual(welcome['keyboard'].keyboard[0][0].text, T['en']['kb_quiz'])
        self.assertTrue(welcome['keyboard'].is_persistent)
        self.assertIn('menu:quiz', [b.callback_data for b in buttons(menu)])

    async def test_reply_button_is_never_graded_as_an_answer(self):
        await bot.ex_chapter(self.update, self.ctx, self.chat.id, 21)
        await self.type(T['it']['kb_ex'])
        self.assertIsNone(self.state()['ex'])                 # esercizio chiuso, nessun punteggio
        self.assertIn('part:ex:I', [b.callback_data for b in buttons(self.chat.messages[-1])])

    async def test_reply_buttons_route_to_activities(self):
        await self.type(T['it']['kb_quiz'])
        self.assertEqual(self.state()['mode'], 'quiz')
        await self.type(T['it']['kb_theory'])
        self.assertIsNone(self.state()['quiz'])
        self.assertIn('part:chap:III', [b.callback_data for b in buttons(self.chat.messages[-1])])
        await self.type(T['it']['kb_menu'])
        self.assertIn('menu:quiz', [b.callback_data for b in buttons(self.chat.messages[-1])])

    async def test_reply_button_after_restart_recovers_language(self):
        bot.STATE.clear()
        await self.type(T['en']['kb_theory'])
        self.assertEqual(self.state()['lang'], 'en')
        bot.STATE.clear()
        self.update.effective_user = SimpleNamespace(language_code='it-IT')
        await self.type(T['it']['kb_quiz'])                   # etichetta uguale nelle due lingue
        self.assertEqual(self.state()['lang'], 'it')

    async def test_chapters_grouped_by_part_with_italian_titles(self):
        await bot.chapters_menu(self.update, self.ctx, self.chat.id)
        await self.click('part:chap:II')
        msg = self.chat.messages[-1]
        self.assertTrue(msg.get('edited'))                    # navigazione nello stesso messaggio
        labels = [b.text for b in buttons(msg)]
        self.assertIn('5. Articoli: a, an, the e articolo zero', labels)
        self.assertEqual([b.callback_data for b in buttons(msg)][:4], [f'chap:{n}' for n in (4, 5, 6, 7)])
        self.state()['lang'] = 'en'
        await self.click('part:ex:V')
        labels = [b.text for b in buttons(self.chat.messages[-1])]
        self.assertIn('25. Punctuation, Capitalization & Common Mistakes', labels)
        for bad in ('part:chap:VI', 'part:xx:I', 'part:chap'):
            before = len(self.chat.messages)
            await self.click(bad)
            self.assertEqual(len(self.chat.messages), before)

    async def test_exercise_progress_shown_next_to_chapter(self):
        await bot.ex_chapter(self.update, self.ctx, self.chat.id, 1)
        ex = self.state()['ex']
        total = len(ex['items'])
        for _ in range(total):
            await self.click(bot.session_data('ex', ex, 'skip'))
        summary = self.chat.messages[-1]
        self.assertIn(f'0/{total}', summary['text'])
        self.assertIn('☆☆☆☆☆', summary['text'])
        data = [b.callback_data for b in buttons(summary)]
        self.assertIn('ex:chap:1', data)
        self.assertIn('ex:chap:2', data)
        self.assertIn('chap:1', data)
        await self.click('part:ex:I')
        labels = [b.text for b in buttons(self.chat.messages[-1])]
        self.assertTrue(any(l.startswith('1. ') and l.endswith(f'✅ 0/{total}') for l in labels), labels)
        self.assertFalse(any(l.startswith('2. ') and '✅' in l for l in labels))

    async def test_theory_pages_back_and_forth_in_place(self):
        await bot.send_chapter(self.update, self.ctx, self.chat.id, 9)
        pages = self.state()['pages']
        self.assertGreater(len(pages), 2)
        first = self.chat.messages[-1]
        self.assertIn('<b>📘 Cap. 9 — I tempi passati</b>', first['text'])
        self.assertIn('pagina 1/', first['text'])
        data = [b.callback_data for b in buttons(first)]
        self.assertIn('ex:chap:9', data)
        self.assertIn('exquiz:9', data)
        self.assertIn('part:chap:III', data)
        self.assertFalse(any(d.endswith(':-1') for d in data))
        await self.click(find_callback(self.chat, lambda d: d.endswith(':1') and d.startswith('page:')))
        second = self.chat.messages[-1]
        self.assertTrue(second.get('edited'))
        self.assertIn('pagina 2/', second['text'])
        back = find_callback(self.chat, lambda d: d.startswith('page:') and d.endswith(':0'))
        await self.click(back)
        self.assertEqual(self.state()['page_idx'], 0)
        await self.click(back)                                # già sulla pagina 1: rifiutato
        self.assertEqual(self.state()['page_idx'], 0)
        await self.click('part:chap:III')
        labels = [b.text for b in buttons(self.chat.messages[-1])]
        self.assertIn('9. I tempi passati  ✓', labels)

    async def test_every_theory_page_fits_and_is_valid_html(self):
        from tests.test_foundations import StrictHTML
        for lang in ('it', 'en'):
            self.state()['lang'] = lang
            for num in range(1, 26):
                for opener in (bot.send_chapter, None):
                    if opener:
                        await opener(self.update, self.ctx, self.chat.id, num)
                    else:
                        self.state()['mode'] = 'exp'
                        await bot.open_pages(self.update, self.ctx, self.state(), num,
                                             bot.kbmod.explain_summary(bot.KB, num), summary=True)
                    for idx in range(len(self.state()['pages'])):
                        text = bot.page_text(self.state(), lang, idx)
                        self.assertLessEqual(len(text), 4096)
                        parser = StrictHTML()
                        parser.feed(text)
                        parser.close()
                        self.assertFalse(parser.stack)
                        self.assertNotIn('• •', text)

    async def test_menu_quiz_by_chapter_opens_new_message(self):
        await bot.cmd_menu(self.update, self.ctx)
        await self.click('menu:qpick')
        msg = self.chat.messages[-1]
        self.assertFalse(msg.get('edited'))
        self.assertIn('part:quiz:I', [b.callback_data for b in buttons(msg)])

    async def test_quiz_summary_lists_mistakes_and_redo_once(self):
        oks = [e for e in bot.KB['examples'] if e['ch'] == 5 and e['ok'] and e['quiz_eligible']][:3]
        pool = [{'type': 'tf', 'ref': e['id'], 'ch': 5} for e in oks]
        await bot.start_quiz(self.update, self.ctx, self.chat.id, chapter=5, pre_pool=pool)
        for given in ('tf:0', 'tf:1', 'tf:0'):                # due errori su tre
            await self.click(find_callback(self.chat, lambda d: d.endswith(given)))
            await self.click(find_callback(self.chat, lambda d: d.endswith(':next')))
        summary = self.chat.messages[-1]
        self.assertIn('1/3', summary['text'])
        self.assertIn(bot.render.esc(oks[0]['t'])[:40], summary['text'])
        self.assertEqual(summary['text'].count('✗ '), 2)
        data = [b.callback_data for b in buttons(summary)]
        self.assertIn('chap:5', data)
        self.assertIn('exquiz:5', data)
        redo = next(d for d in data if d.startswith('redo:'))
        await self.click(redo)
        self.assertEqual(self.state()['mode'], 'quiz')
        self.assertEqual([r['ref'] for r in self.state()['quiz']['pool']], [oks[0]['id'], oks[2]['id']])
        q = await self.click(redo)                            # secondo tocco: scaduto
        q.answer.assert_awaited_once_with(T['it']['expired'])
        await bot.chapters_menu(self.update, self.ctx, self.chat.id)
        await self.click('pick:quiz')
        await self.click('part:quiz:II')
        labels = [b.text for b in buttons(self.chat.messages[-1])]
        self.assertTrue(any(l.startswith('5. ') and l.endswith('✅ 1/3') for l in labels), labels)

    async def test_feedback_layout_quote_source_and_note(self):
        e = next(e for e in bot.KB['examples'] if e['ok'] and e['quiz_eligible'] and e.get('note'))
        for lang in ('it', 'en'):
            self.state()['lang'] = lang
            await bot.start_quiz(self.update, self.ctx, self.chat.id,
                                 pre_pool=[{'type': 'tf', 'ref': e['id'], 'ch': e['ch']}])
            question = self.chat.messages[-1]['text']
            self.assertIn('1/1', question)
            self.assertIn('▰' * 10, question)
            await self.click(find_callback(self.chat, lambda d: d.endswith('tf:1')))
            text = self.chat.messages[-1]['text']
            self.assertTrue(text.startswith('<b>✅'))
            self.assertIn('<blockquote>', text)
            self.assertIn('<i>📖 ', text)
            if lang == 'it' and bot.book_quiz.note_for(bot.KB, e, 'item'):
                self.assertIn('<blockquote expandable>🇮🇹', text)
            if lang == 'en':
                self.assertNotIn('🇮🇹', text)

    async def test_help_lists_every_command(self):
        await bot.cmd_help(self.update, self.ctx)
        text = self.chat.messages[-1]['text']
        for name, it, _ in COMMANDS:
            self.assertIn(f'/{name} — ', text)

    async def test_glossary_and_verbs_are_escaped_html(self):
        await bot.verbs_lookup(self.update, self.ctx, self.chat.id, '<go&>')
        self.assertIn('&lt;go&amp;&gt;', self.chat.messages[-1]['text'])
        await bot.verbs_lookup(self.update, self.ctx, self.chat.id, 'went')
        self.assertIn('<b>go</b> → <b>went</b>', self.chat.messages[-1]['text'])
        for i, g in enumerate(bot.KB['glossary']):
            self.chat.messages.clear()
            await self.click(f'gl:none:{i}')                   # scaduto: niente messaggio
            self.assertEqual(self.chat.messages, [])
            await self.chat.send_message(bot.glossary_html('it', g), parse_mode='HTML')


if __name__ == '__main__':
    unittest.main()
