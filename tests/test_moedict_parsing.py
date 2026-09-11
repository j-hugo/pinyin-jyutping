import unittest
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pinyin_jyutping.parser
import pinyin_jyutping.data


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


# one entry per ingestion branch, so the counter pins every code path
MOEDICT_SAMPLE = [
    {"title": "並時", "heteronyms": [{"pinyin": "bìng shí"}]},
    {"title": "一會兒", "heteronyms": [{"pinyin": "yī huǐr "}]},
    {"title": "二碴兒", "heteronyms": [{"pinyin": "èr chár "}]},
    {"title": "臺灣", "heteronyms": [{"pinyin": "tái wān"}]},
    {"title": "{[8ff0]}", "heteronyms": [{"pinyin": "zhuàng"}]},
    {"title": "台", "heteronyms": [{"bopomofo": "ㄊㄞ"}]},
    {"title": "啐", "heteronyms": [{"pinyin": "q"}]},
    {"title": "哀嚎", "heteronyms": [{"pinyin": "āi "}]},
]


class MoedictIngestionTests(unittest.TestCase):
    def ingest_sample(self):
        data = pinyin_jyutping.data.Data()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                         encoding='utf8', delete=False) as f:
            json.dump(MOEDICT_SAMPLE, f)
            filepath = f.name
        try:
            counter = pinyin_jyutping.parser.parse_moedict(filepath, data)
        finally:
            os.unlink(filepath)
        return data, counter

    def test_counter_pins_every_branch(self):
        data, counter = self.ingest_sample()
        self.assertEqual(dict(counter), {
            'ingested': 4,
            'erhua_rewritten': 2,
            'tai_overlay': 1,
            'skipped_pua_title': 1,
            'skipped_no_pinyin': 1,
            'failed_parse': 1,
            'skipped_length_mismatch': 1,
        })

    def test_ingests_plain_entry(self):
        data, counter = self.ingest_sample()
        self.assertIn('並時', data.pinyin_map)
        self.assertEqual(str(data.pinyin_map['並時'][0].syllables[0]), 'bing4')

    def test_registers_tai_overlay_spelling(self):
        # moedict only ever writes 臺灣; everyday Taiwanese writing uses 台灣,
        # so both must be headwords
        data, counter = self.ingest_sample()
        self.assertIn('臺灣', data.pinyin_map)
        self.assertIn('台灣', data.pinyin_map)

    def test_erhua_entry_ingested_with_correct_length(self):
        data, counter = self.ingest_sample()
        self.assertIn('一會兒', data.pinyin_map)
        self.assertEqual(len(data.pinyin_map['一會兒'][0].syllables), 3)
