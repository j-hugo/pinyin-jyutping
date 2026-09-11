import unittest
import pytest
import sys
import os
import pickle
import jieba

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pinyin_jyutping
import pinyin_jyutping.constants
import pinyin_jyutping.data
import pinyin_jyutping.parser

MOEDICT_PICKLE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'pinyin_jyutping',
    pinyin_jyutping.constants.PICKLE_MOEDICT_DATA_FILENAME))

requires_moedict_pickle = pytest.mark.skipif(
    not os.path.isfile(MOEDICT_PICKLE_PATH),
    reason='pinyin_moedict.pkl not built, run python tools/build_data.py')

ENABLE_FULL_MOEDICT_PARSING_TESTS = os.environ.get('FULL_MOEDICT_PARSING_TESTS', 'no') == 'yes'


@requires_moedict_pickle
class MoedictConversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maxDiff = None
        cls.instance = pinyin_jyutping.PinyinJyutping(variant='moedict')

    def test_taiwan_reading_signature(self):
        """the readings that distinguish moedict from CC-CEDICT"""
        self.assertEqual(self.instance.pinyin('垃圾分類'), 'lèsè fēnlèi')
        self.assertEqual(self.instance.pinyin('企業管理'), 'qìyè guǎnlǐ')
        self.assertEqual(self.instance.pinyin('星期日'), 'xīngqírì')
        self.assertEqual(self.instance.pinyin('研究所學生'), 'yánjiùsuǒ xuéshēng')

    def test_no_neutral_tone_where_moe_standard_has_none(self):
        self.assertEqual(self.instance.pinyin('學生'), 'xuéshēng')
        self.assertEqual(self.instance.pinyin('我喜歡吃麵包'), 'wǒ xǐhuān chī miàn bāo')

    def test_tone_sandhi_still_applies(self):
        """moedict stores citation tones; the 一/不 rules run on top of them"""
        self.assertEqual(self.instance.pinyin('一定'), 'yídìng')
        self.assertEqual(self.instance.pinyin('不對'), 'bú duì')

    def test_simplified_input_passes_through(self):
        """traditional-only contract: unknown characters are emitted unchanged"""
        self.assertEqual(self.instance.pinyin('我们'), 'wǒ们')

    def test_out_of_contract_simplified_collisions(self):
        """么 and 万 are simplified forms; moedict knows only the rare
        traditional readings. pinned so the behaviour is a decision, not a drift."""
        self.assertEqual(self.instance.pinyin('么'), 'yāo')
        self.assertEqual(self.instance.pinyin('万'), 'mò')

    def test_erhua_entry_converts(self):
        self.assertEqual(self.instance.pinyin('一會兒'), 'yīhuǐer')


@requires_moedict_pickle
class MoedictOrthographyTests(unittest.TestCase):
    """the 台 spellings must be real headwords, not merely reachable by
    character-by-character fallback. asserting rendered output alone would pass
    even without the overlay, so assert map membership."""

    @classmethod
    def setUpClass(cls):
        f = open(MOEDICT_PICKLE_PATH, 'rb')
        cls.data = pickle.load(f)
        f.close()

    def test_tai_spellings_are_headwords(self):
        for word in ['台灣', '台北', '台中', '電台', '舞台', '平台']:
            self.assertIn(word, self.data.pinyin_map, f'{word} should be a headword')

    def test_dictionary_spellings_still_present(self):
        for word in ['臺灣', '臺北', '電臺', '舞臺']:
            self.assertIn(word, self.data.pinyin_map, f'{word} should be a headword')


class MoedictFullSourceTests(unittest.TestCase):
    @pytest.mark.skipif(not ENABLE_FULL_MOEDICT_PARSING_TESTS,
                        reason='set FULL_MOEDICT_PARSING_TESTS=yes')
    def test_ingestion_counts(self):
        """guards against silent drift in the moedict source format.
        run: FULL_MOEDICT_PARSING_TESTS=yes pytest tests/test_moedict_conversion.py
        requires temp_data/dict-revised.json.xz, produced by tools/build_data.py"""
        filepath = os.path.join(
            pinyin_jyutping.constants.MOEDICT_TEMP_DATA_DIRECTORY,
            pinyin_jyutping.constants.MOEDICT_SOURCE_FILENAME)
        if not os.path.isfile(filepath):
            self.skipTest(f'{filepath} not present, run python tools/build_data.py')
        # the map size depends on how process_word tokenizes, so pin the
        # tokenizer rather than depending on whatever a previous test left set
        jieba.set_dictionary(os.path.abspath(os.path.join(
            os.path.dirname(__file__), '..', 'pinyin_jyutping', 'dict.txt.big')))
        data = pinyin_jyutping.data.Data()
        counter = pinyin_jyutping.parser.parse_moedict(filepath, data)
        self.assertEqual(dict(counter), {
            'ingested': 162424,
            'skipped_no_pinyin': 1479,
            'erhua_rewritten': 1641,
            'tai_overlay': 381,
            'failed_parse': 6,
            'skipped_length_mismatch': 5,
            'skipped_pua_title': 4,
        })
        self.assertEqual(len(data.pinyin_map), 174621)
