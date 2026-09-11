import os
import pickle
import jieba
import logging
from . import constants
from . import conversion
from . import parser

logger = logging.getLogger(__file__)

class PinyinJyutping():
    def __init__(self, variant=constants.VARIANT_CEDICT):
        self.validate_variant(variant)
        self.variant = variant
        self.data_map = {}
        self.load_data()
        self.initialize_jieba()
        if variant != constants.VARIANT_CEDICT:
            # load eagerly so the cost is paid at construction rather than
            # on some later call
            self.get_data(variant)

    def validate_variant(self, variant):
        if variant not in constants.PICKLE_FILENAME_MAP:
            raise ValueError(f'unknown variant: {variant}, expected one of '
                             f'{sorted(constants.PICKLE_FILENAME_MAP.keys())}')

    def resolve_variant(self, variant):
        if variant == None:
            return self.variant
        self.validate_variant(variant)
        return variant

    def load_data(self):
        module_dir = os.path.dirname(__file__)
        pickle_filepath = os.path.join(module_dir, constants.PICKLE_DATA_FILENAME)
        f = open(pickle_filepath, 'rb')
        self.data = pickle.load(f)
        f.close()
        self.data_map[constants.VARIANT_CEDICT] = self.data

    def get_data(self, variant):
        if variant not in self.data_map:
            module_dir = os.path.dirname(__file__)
            pickle_filepath = os.path.join(module_dir, constants.PICKLE_FILENAME_MAP[variant])
            logger.debug(f'loading {variant} data from {pickle_filepath}')
            f = open(pickle_filepath, 'rb')
            self.data_map[variant] = pickle.load(f)
            f.close()
        return self.data_map[variant]

    def get_pinyin_data(self, variant):
        return self.get_data(self.resolve_variant(variant))

    def initialize_jieba(self):
        module_dir = os.path.dirname(__file__)
        jieba_big_dictionary_filename = os.path.join(module_dir, "dict.txt.big")
        jieba.set_dictionary(jieba_big_dictionary_filename)

    def load_pinyin_corrections(self, corrections, variant=None):
        data = self.get_pinyin_data(variant)
        for correction in corrections:
            try:
                chinese = correction['chinese']
                pinyin = correction['pinyin']
                parser.parse_pinyin_correction(chinese, pinyin, data)
            except Exception as e:
                logger.exception(e)

    def load_jyutping_corrections(self, corrections):
        for correction in corrections:
            try:
                chinese = correction['chinese']
                jyutping = correction['jyutping']
                parser.parse_jyutping_correction(chinese, jyutping, self.data)
            except Exception as e:
                logger.exception(e)

    def pinyin(self, text, tone_numbers=False, spaces=False, variant=None):
        data = self.get_pinyin_data(variant)
        return conversion.convert_pinyin_single_solution(data, text, tone_numbers, spaces)

    def jyutping(self, text, tone_numbers=False, spaces=False):
        return conversion.convert_jyutping_single_solution(self.data, text, tone_numbers, spaces)

    def pinyin_all_solutions(self, text, tone_numbers=False, spaces=False, variant=None):
        data = self.get_pinyin_data(variant)
        return conversion.convert_pinyin_all_solutions(data, text, tone_numbers, spaces)

    def jyutping_all_solutions(self, text, tone_numbers=False, spaces=False):
        return conversion.convert_jyutping_all_solutions(self.data, text, tone_numbers, spaces)
