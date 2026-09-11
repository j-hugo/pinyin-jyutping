import unittest
import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pinyin_jyutping
import pinyin_jyutping.constants

MOEDICT_PICKLE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'pinyin_jyutping',
    pinyin_jyutping.constants.PICKLE_MOEDICT_DATA_FILENAME))

requires_moedict_pickle = pytest.mark.skipif(
    not os.path.isfile(MOEDICT_PICKLE_PATH),
    reason='pinyin_moedict.pkl not built, run python tools/build_data.py')


class VariantSelectionTests(unittest.TestCase):
    def test_unknown_variant_raises_in_constructor(self):
        with self.assertRaises(ValueError):
            pinyin_jyutping.PinyinJyutping(variant='tw')

    def test_unknown_variant_raises_on_call(self):
        instance = pinyin_jyutping.PinyinJyutping()
        with self.assertRaises(ValueError):
            instance.pinyin('上課', variant='tw')

    def test_moedict_not_loaded_when_unused(self):
        instance = pinyin_jyutping.PinyinJyutping()
        instance.pinyin('上課')
        self.assertNotIn(pinyin_jyutping.constants.VARIANT_MOEDICT, instance.data_map)

    @requires_moedict_pickle
    def test_moedict_loaded_lazily_on_first_use(self):
        instance = pinyin_jyutping.PinyinJyutping()
        instance.pinyin('垃圾分類', variant='moedict')
        self.assertIn(pinyin_jyutping.constants.VARIANT_MOEDICT, instance.data_map)

    @requires_moedict_pickle
    def test_constructor_variant_becomes_default(self):
        instance = pinyin_jyutping.PinyinJyutping(variant='moedict')
        self.assertEqual(instance.pinyin('垃圾分類'), 'lèsè fēnlèi')

    @requires_moedict_pickle
    def test_per_call_variant_overrides_default(self):
        instance = pinyin_jyutping.PinyinJyutping()
        self.assertEqual(instance.pinyin('垃圾分類'), 'lājī fēnlèi')
        self.assertEqual(instance.pinyin('垃圾分類', variant='moedict'), 'lèsè fēnlèi')

    @requires_moedict_pickle
    def test_per_call_variant_overrides_non_default_instance(self):
        instance = pinyin_jyutping.PinyinJyutping(variant='moedict')
        self.assertEqual(instance.pinyin('垃圾分類', variant='cedict'), 'lājī fēnlèi')

    @requires_moedict_pickle
    def test_all_solutions_honours_variant(self):
        instance = pinyin_jyutping.PinyinJyutping()
        output = instance.pinyin_all_solutions('垃圾', variant='moedict')
        self.assertEqual(output['solutions'][0][0], 'lèsè')

    @requires_moedict_pickle
    def test_jyutping_unaffected_by_moedict_default(self):
        instance = pinyin_jyutping.PinyinJyutping(variant='moedict')
        self.assertEqual(instance.jyutping('我出去攞野食'), 'ngǒ cēothêoi ló jěsik')


class VariantCorrectionsTests(unittest.TestCase):
    @requires_moedict_pickle
    def test_correction_is_scoped_to_one_variant(self):
        # a deliberately wrong reading, so that "the correction was applied"
        # and "this variant was already like that" cannot be confused
        instance = pinyin_jyutping.PinyinJyutping()
        instance.load_pinyin_corrections(
            [{'chinese': '學生', 'pinyin': 'ping2guo3'}], variant='moedict')
        self.assertEqual(instance.pinyin('學生', variant='moedict'), 'píngguǒ')
        # the cedict map must be untouched by a moedict correction
        self.assertEqual(instance.pinyin('學生', variant='cedict'), 'xuésheng')

    @requires_moedict_pickle
    def test_correction_defaults_to_instance_variant(self):
        instance = pinyin_jyutping.PinyinJyutping(variant='moedict')
        instance.load_pinyin_corrections([{'chinese': '學生', 'pinyin': 'ping2guo3'}])
        self.assertEqual(instance.pinyin('學生'), 'píngguǒ')
        self.assertEqual(instance.pinyin('學生', variant='cedict'), 'xuésheng')
