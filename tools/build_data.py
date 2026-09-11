import os
import sys
import pickle
import logging
import urllib.request
import jieba
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logging.basicConfig(level=logging.WARN)

logger = logging.getLogger(__file__)

import pinyin_jyutping.data
import pinyin_jyutping.parser
import pinyin_jyutping.constants

data = pinyin_jyutping.data.Data()

# ingest cedict data
# ==================

filename = 'source_data/cedict_1_0_ts_utf-8_mdbg.txt'
pinyin_jyutping.parser.parse_cedict(filename, data)

# ingest jyutping data
# ====================

pinyin_jyutping.parser.parse_jyutping_cccanto_definition_process_words('source_data/cccanto-webdist-160115.txt', data)
pinyin_jyutping.parser.parse_jyutping_ccedit_canto_readings_process_words('source_data/cccedict-canto-readings-150923.txt', data)

# ingest moedict data
# ===================

# process_word tokenizes with jieba, and the runtime always uses dict.txt.big
# (see PinyinJyutping.initialize_jieba), so the build must use it too or the
# tokenized sub-word entries will not match what conversion looks up. this is
# set only now, after the cedict and jyutping ingestion above, so that
# pinyin_jyutping.pkl is built exactly as it always has been.
jieba.set_dictionary('pinyin_jyutping/dict.txt.big')


def download_moedict_source():
    os.makedirs(pinyin_jyutping.constants.MOEDICT_TEMP_DATA_DIRECTORY, exist_ok=True)
    filepath = os.path.join(pinyin_jyutping.constants.MOEDICT_TEMP_DATA_DIRECTORY,
                            pinyin_jyutping.constants.MOEDICT_SOURCE_FILENAME)
    if os.path.isfile(filepath):
        logger.warning(f'{filepath} already present, skipping download')
        return filepath
    url = pinyin_jyutping.constants.MOEDICT_SOURCE_URL
    logger.warning(f'downloading {url} to {filepath}')
    urllib.request.urlretrieve(url, filepath)
    return filepath

moedict_data = pinyin_jyutping.data.Data()
counter = pinyin_jyutping.parser.parse_moedict(download_moedict_source(), moedict_data)
logger.warning(f'moedict ingestion: {dict(counter)}')

moedict_pickle_file_path = f'pinyin_jyutping/{pinyin_jyutping.constants.PICKLE_MOEDICT_DATA_FILENAME}'
moedict_file = open(moedict_pickle_file_path, 'wb')
pickle.dump(moedict_data, moedict_file)
moedict_file.close()
logger.warning(f'wrote {moedict_pickle_file_path}')

# write output
# ============

pickle_file_path = f'pinyin_jyutping/{pinyin_jyutping.constants.PICKLE_DATA_FILENAME}'
data_file = open(pickle_file_path, 'wb')
pickle.dump(data, data_file)
data_file.close()

logger.info(f'wrote {pickle_file_path}')