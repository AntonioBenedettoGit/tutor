"""Fase 4.2: segmentazione di esempi ✓/✗ e soluzioni su testo con stili sintetico (senza PDF)."""
import unittest

from tutor.book_parser import (ZERO_ANSWER, check_mode, complete_good, enrich_exercise, finalize_items,
                               segment_marks, split_answer, _pair_runs, _realign_core)
from tutor.pdf_rich import clean_book_markup, rich_join, to_html, to_plain


def rich(*parts):
    """rich(('testo', 'i'), ('altro', '')) -> lista di (carattere, stile, pagina)."""
    return [(c, style, 1) for text, style in parts for c in text]


def examples(chars):
    return [(it['mark'], to_plain(it['chars'])) for it in segment_marks(clean_book_markup(chars))]


class SegmentTests(unittest.TestCase):
    def test_scattered_emphasis_keeps_whole_sentence(self):
        chars = rich(('• ✓ ', ''), ('They', 'bi'), ('* invited ', 'b'), ('us ', ''), ('to ', 'b'),
                     ('their* ', ''), ('house.', 'i'))
        self.assertEqual(examples(chars), [('✓', 'They invited us to their house.')])

    def test_roman_comment_after_italic_example_is_note(self):
        chars = rich(('✓ ', ''), ('I wish I were taller.', 'i'), (' (use were for all persons)', ''))
        items = segment_marks(clean_book_markup(chars))
        self.assertEqual(to_plain(items[0]['chars']), 'I wish I were taller.')
        self.assertIn('use were', items[0]['note'])

    def test_arrow_pairs_and_slash_runs(self):
        chars = rich(('✗ ', ''), ('informations', 'i'), (' → ✓ ', ''), ('information', 'i'), (' | ✗ ', ''),
                     ('advices', 'i'), (' → ✓ ', ''), ('advice', 'i'))
        items = segment_marks(clean_book_markup(chars))
        pairs = [(to_plain(b[0]['chars']), to_plain(g[0]['chars'])) for b, g in _pair_runs(items)]
        self.assertEqual(pairs, [('informations', 'information'), ('advices', 'advice')])

    def test_symbol_mention_in_prose_is_not_example(self):
        chars = rich(('Look at the ✓ and ✗ examples below.', ''))
        self.assertEqual(examples(chars), [])

    def test_strikethrough_markup_becomes_style(self):
        chars = clean_book_markup(rich(('✗ ', ''), ('~~a furniture~~', 'i')))
        self.assertIn('<s>', to_html(chars))
        self.assertEqual(to_plain(chars), '✗ a furniture')


class FixAndAnswerTests(unittest.TestCase):
    def test_partial_book_correction_completed(self):
        self.assertEqual(complete_good('The dog wagged it’s tail.', 'its tail.'), 'The dog wagged its tail.')
        self.assertEqual(complete_good('Do you like it? — Yes, I like.', 'Yes, I do.'),
                         'Do you like it? — Yes, I do.')
        self.assertIsNone(complete_good('She is teacher.', 'She is a teacher.'))

    def test_duplicates_removed_only_within_chapter(self):
        ex = [{'t': 'I like tea.', 'ok': True, 'ch': 1, 'page': 3}, {'t': 'I like tea', 'ok': True, 'ch': 1, 'page': 5},
              {'t': 'I like tea.', 'ok': True, 'ch': 2, 'page': 9}]
        out, _ = finalize_items(ex, [])
        self.assertEqual([(e['ch'], e['page']) for e in out], [(1, 3), (2, 9)])
        self.assertEqual(out[0]['also_pages'], [5])

    def test_answer_split_bold_answer_and_explanation(self):
        chars = rich(('an', 'b'), (' — ', ''), ('hour', 'i'), (' has a silent h.', ''))
        core, expl, scheme, _ = split_answer(chars)
        self.assertEqual((core, expl, scheme), ('an', 'hour has a silent h.', 'risposta_e_spiegazione'))

    def test_zero_article_answer(self):
        chars = rich(('—', 'b'), (' (no article) — languages take the zero article.', ''))
        core, expl, scheme, _ = split_answer(chars)
        self.assertEqual(core, ZERO_ANSWER)
        self.assertIn('zero article', expl)

    def test_true_hyphen_at_line_end_kept_without_space(self):
        joined = rich_join(rich(('all-', ''), ('\n', ''), ('important', '')))
        self.assertEqual(to_plain(joined), 'all-important')
        soft = rich_join(rich(('impor\u2010', ''), ('\n', ''), ('tant', '')))
        self.assertEqual(to_plain(soft), 'important')


class Phase43ParserTests(unittest.TestCase):
    def test_do_not_kept_before_arrow(self):
        chars = rich(('✓', ''), ('do not', 'i'), (' → ', ''), ('don’t', 'i'), (', I am → I’m', ''))
        items = segment_marks(clean_book_markup(chars))
        self.assertEqual(to_plain(items[0]['chars']), 'do not')

    def test_broken_emphasis_with_asterisks_keeps_whole_list(self):
        chars = rich(('✓', ''), ('the', 'bi'), ('* rich, ', 'b'), ('the', ''), (' poor, ', 'b'),
                     ('the*', ''), (' unemployed', 'i'))
        items = segment_marks(clean_book_markup(chars), broken=True)
        self.assertEqual(to_plain(items[0]['chars']), 'the rich, the poor, the unemployed')

    def test_table_labels_and_symbol_pairs_are_not_examples(self):
        self.assertEqual(examples(rich(('✓ (singular)', ''))), [])
        self.assertEqual(examples(rich(('you get the rule and a ✓/✗ example.', ''))), [])

    def test_realign_shifted_emphasis(self):
        core, expl = _realign_core('No. That', 'No. That is the subject of the clause.')
        self.assertEqual((core, expl), ('No.', 'That is the subject of the clause.'))

    def test_two_gap_answer_sentence(self):
        a = rich(('at', 'b'), (' 9 o’clock ', ''), ('on', 'b'), (' Monday morning. (clock time → at; day → on)', ''))
        plain_a = to_plain(a)
        e = {'source_id': 't', 'source_q': 'The lesson begins _ 9 o’clock _ Monday morning.', 'q': 'x',
             'answer': plain_a, 'instr': '', 'kind': 'open'}
        enrich_exercise(e, {'q': [], 'answer': a, 'instr': []})
        self.assertEqual(e['answer_core'], 'at 9 o’clock on Monday morning.')
        self.assertEqual(e['answer_explanation'], 'clock time → at; day → on')
        self.assertEqual(e['check_mode'], 'automatico_con_varianti')

    def test_check_mode_short_and_long(self):
        e = {'kind': 'open', 'source_q': 'Are you afraid ____ the dark?'}
        self.assertEqual(check_mode(e, 'of'), 'automatico')
        self.assertEqual(check_mode(e, 'Answers may vary: any sentence with of the dark.'), 'autovalutazione')


if __name__ == '__main__':
    unittest.main()
