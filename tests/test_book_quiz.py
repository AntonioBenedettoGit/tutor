"""Fase 4.3: confronto delle risposte con la soluzione del libro e rendering HTML (offline)."""
import random
import unittest

import bot
from tutor import book_quiz
from tutor.book_quiz import check_answer, check_parts
from tutor.render import tidy_html

EX = bot.EXERCISES


class CheckAnswerTests(unittest.TestCase):
    def accepts(self, name, *answers):
        for a in answers:
            with self.subTest(name=name, answer=a):
                self.assertTrue(check_answer(EX[name], a))

    def rejects(self, name, *answers):
        for a in answers:
            with self.subTest(name=name, answer=a):
                self.assertFalse(check_answer(EX[name], a))

    def test_every_automatic_exercise_accepts_its_own_book_answer(self):
        for e in bot.KB['exercises']:
            if e['check_mode'].startswith('automatico'):
                self.assertTrue(check_answer(e, e['answer_core']), e['source_id'])
            if e['check_mode'] == 'parti':
                typed = '\n'.join(p['answer_core'] for p in e['parts'])
                self.assertTrue(all(ok for _, _, ok in check_parts(e, typed)), e['source_id'])

    def test_multi_gap_and_prepositions(self):
        self.accepts('ch21-main-6', 'arrived in')
        self.rejects('ch21-main-6', 'arrived at')
        self.accepts('ch21-main-1', 'at on', 'at … on', 'at 9 o’clock on Monday morning.')
        self.rejects('ch21-main-1', 'in on')

    def test_zero_article_and_contractions(self):
        zero = next(e for e in bot.KB['exercises'] if e['answer_core'] == book_quiz.ZERO)
        for typed in ('-', 'nessun articolo', 'no article'):
            self.assertTrue(check_answer(zero, typed))
        self.assertFalse(check_answer(zero, 'the'))

    def test_empty_and_wrong_answers(self):
        for e in bot.KB['exercises'][:40]:
            if e['check_mode'].startswith('automatico'):
                self.assertFalse(check_answer(e, ''))
                self.assertFalse(check_answer(e, 'zzzz qqqq'))

    def test_parts_with_labels_and_commas(self):
        e = EX['ch20-main-1']
        labelled = '\n'.join(f"{p['label']}) {p['answer_core']}" for p in e['parts'])
        self.assertTrue(all(ok for _, _, ok in check_parts(e, labelled)))
        wrong = check_parts(e, 'a) easyer / the easyest')
        self.assertFalse(wrong[0][2])
        self.assertTrue(all(not ok for _, _, ok in wrong[1:]))


class PoolTests(unittest.TestCase):
    def test_pool_mix_and_no_duplicates(self):
        rng = random.Random(7)
        for _ in range(50):
            pool = book_quiz.build_pool(bot.KB, rng=rng)
            self.assertEqual(len(pool), 10)
            self.assertEqual(len({(r['type'], r['ref']) for r in pool}), 10)
            self.assertGreaterEqual(sum(r['type'] == 'fix' for r in pool), 4)
            self.assertGreaterEqual(sum(r['type'] == 'mcq' for r in pool), 2)


class HtmlTests(unittest.TestCase):
    def test_tidy_html(self):
        self.assertEqual(tidy_html('<b><b>A</b> · <b>B</b></b>'), '<b>A · B</b>')
        self.assertEqual(tidy_html('<b>x<i>y</b>z</i>'), '<b>x<i>y</i></b><i>z</i>')
        self.assertEqual(tidy_html('a</b>c'), 'ac')
        self.assertEqual(tidy_html('<i>open'), '<i>open</i>')

    def test_theory_pages_are_html_and_short(self):
        from test_foundations import StrictHTML
        for ch in range(1, 26):
            for pages in (bot.kbmod.chapter_pages(bot.KB, ch), bot.kbmod.explain_summary(bot.KB, ch)):
                self.assertTrue(pages and pages[0])
                for page in pages:
                    self.assertLessEqual(len(page), 3500)
                    parser = StrictHTML()
                    parser.feed(page)
                    parser.close()
                    self.assertFalse(parser.stack)
            text = '\n'.join(bot.kbmod.chapter_pages(bot.KB, ch))
            self.assertNotIn('Answers', text.split('\n')[-1])


if __name__ == '__main__':
    unittest.main()
