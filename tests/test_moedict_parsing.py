import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pinyin_jyutping.parser


class MoedictErhuaTests(unittest.TestCase):
    """moedict writes erhua as a bare trailing r on the preceding syllable"""

    def test_splits_trailing_erhua(self):
        self.assertEqual(
            pinyin_jyutping.parser.moedict_rewrite_erhua('yī huǐr '),
            'yī huǐ er5 ')

    def test_preserves_standalone_er_syllable(self):
        # 二碴兒: the leading èr is the syllable er and must survive,
        # while the trailing r on chár is erhua and must split
        self.assertEqual(
            pinyin_jyutping.parser.moedict_rewrite_erhua('èr chár '),
            'èr chá er5 ')

    def test_splits_erhua_after_e_vowel(self):
        # 這兒 / 葉兒 / 角兒: erhua on a syllable ending in an e-vowel.
        # a lookbehind implementation gets these wrong.
        self.assertEqual(pinyin_jyutping.parser.moedict_rewrite_erhua('zhèr '), 'zhè er5 ')
        self.assertEqual(pinyin_jyutping.parser.moedict_rewrite_erhua('yèr '), 'yè er5 ')
        self.assertEqual(pinyin_jyutping.parser.moedict_rewrite_erhua('juér '), 'jué er5 ')

    def test_splits_erhua_mid_string(self):
        # 老哥兒倆
        self.assertEqual(
            pinyin_jyutping.parser.moedict_rewrite_erhua('lǎo gēr liǎ '),
            'lǎo gē er5 liǎ ')

    def test_leaves_ordinary_pinyin_untouched(self):
        self.assertEqual(pinyin_jyutping.parser.moedict_rewrite_erhua('bìng shí'), 'bìng shí')

    def test_rewritten_erhua_parses_to_correct_syllable_count(self):
        # 一會兒 is 3 characters, so it must yield 3 syllables
        syllables = pinyin_jyutping.parser.parse_pinyin(
            pinyin_jyutping.parser.moedict_rewrite_erhua('yī huǐr '))
        self.assertEqual(len(syllables), 3)
        self.assertEqual(str(syllables[2]), 'er5')
