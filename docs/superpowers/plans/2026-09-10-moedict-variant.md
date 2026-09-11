# moedict Pinyin Variant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Taiwanese MOE dictionary (moedict) as a second selectable pinyin source, chosen via `variant='moedict'`, without changing any existing behaviour.

**Architecture:** moedict ships Hanyu Pinyin with diacritics that the existing `parser.parse_pinyin()` already reads. A new `parser.parse_moedict()` ingests it into an ordinary `data.Data` object, which is pickled to a second file `pinyin_moedict.pkl` and loaded lazily. Because a variant is a whole `Data` and `conversion.convert_pinyin_single_solution(data, …)` already takes one, variant selection is just "which `Data` do I pass" — `conversion.py`, `logic.py` and `syllables.py` are not touched at all.

**Tech Stack:** Python 3.7+, jieba, hanzidentifier, pytest. Standard library `json`, `lzma`, `urllib.request`, `collections`.

**Spec:** `docs/superpowers/specs/2026-09-10-moedict-variant-design.md`

## Global Constraints

- **Every existing test must keep passing, unmodified.** This is the primary regression guard. Do not edit any file under `tests/` that already exists.
- **Do not modify** `pinyin_jyutping/conversion.py`, `pinyin_jyutping/logic.py`, `pinyin_jyutping/syllables.py`, or `pinyin_jyutping/data.py`. If you believe you need to, stop and raise it.
- Variant names are exactly `'cedict'` (default) and `'moedict'`. No `'tw'` alias.
- The moedict variant is **traditional-only**. Unknown characters pass through unchanged; never raise on them, and never fall back to the CC-CEDICT map.
- Pinned source commit: `a6dc997417507eb510fc29822bc514de2c92728c`.
- The repo uses 4-space indent, `logger = logging.getLogger(__file__)`, and f-strings. Match the surrounding style in each file.
- Tests requiring `pinyin_moedict.pkl` must skip when it is absent, so a fresh checkout passes.

---

### Task 1: Erhua rewrite

moedict writes erhua as a bare trailing `r` (`一會兒` → `yī huǐr`), which `parse_pinyin` cannot read. This task adds the rewrite that splits it into its own `er5` syllable.

**Files:**
- Modify: `pinyin_jyutping/parser.py` (append a new section at end of file)
- Test: `tests/test_moedict_parsing.py` (create)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `parser.moedict_rewrite_erhua(pinyin: str) -> str` and `parser.MOEDICT_ER_SYLLABLES: set[str]`, used by Task 2.

**Critical design note — read before implementing.** Do not implement this as a regex with a lookbehind. It looks like `re.sub(r'(?<!e)r(?=\s|$)', ' er5', pinyin)` should work; it does not, for two independent reasons:

1. `(?<!e)` never fires on `èr`, because `è` is U+00E8, not `e`.
2. Even a corrected class like `(?<![eēéěè])` is wrong, because it then blocks *legitimate* erhua on syllables ending in an e-vowel: `zhèr` (這兒), `yèr` (葉兒), `gér` (閣兒), `juér` (角兒). These must split.

The distinguishing question is not "what character precedes the `r`" but "is this whole token the syllable *er*?". Hence the token-level rule below.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_moedict_parsing.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_moedict_parsing.py -v`
Expected: FAIL with `AttributeError: module 'pinyin_jyutping.parser' has no attribute 'moedict_rewrite_erhua'`

- [ ] **Step 3: Write the implementation**

Append to the end of `pinyin_jyutping/parser.py`:

```python
# moedict parsing logic
# =====================

# tokens that are the syllable "er" in their own right. every other token ending
# in 'r' is erhua, where moedict attaches the 兒 to the preceding syllable
# (一會兒 -> 'yī huǐr'). note this must be decided per token: a lookbehind on the
# preceding character cannot separate èr (the syllable) from zhèr (erhua).
MOEDICT_ER_SYLLABLES = {'er', 'ēr', 'ér', 'ěr', 'èr'}


def moedict_rewrite_erhua(pinyin):
    tokens = []
    for token in pinyin.split(' '):
        if token.endswith('r') and token not in MOEDICT_ER_SYLLABLES:
            logger.debug(f'moedict: splitting erhua token {token}')
            tokens.append(token[:-1])
            tokens.append('er5')
        else:
            tokens.append(token)
    return ' '.join(tokens)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_moedict_parsing.py -v`
Expected: 6 passed

- [ ] **Step 5: Run the full suite to confirm nothing regressed**

Run: `pytest tests`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add pinyin_jyutping/parser.py tests/test_moedict_parsing.py
git commit -m "feat: add moedict erhua rewrite"
```

---

### Task 2: moedict ingestion

**Files:**
- Modify: `pinyin_jyutping/parser.py` (extend the moedict section from Task 1; add `json`, `lzma`, `collections` imports at top)
- Test: `tests/test_moedict_parsing.py` (extend)

**Interfaces:**
- Consumes: `parser.moedict_rewrite_erhua` from Task 1. Existing `parser.parse_pinyin`, `parser.clean_chinese`, `parser.process_word`, `errors.PinyinSyllableNotFound`, `data.Data`.
- Produces: `parser.parse_moedict(filepath, data) -> collections.Counter`, used by Task 3. Accepts either a `.json` or a `.xz` path. Counter keys are exactly: `ingested`, `skipped_no_pinyin`, `erhua_rewritten`, `tai_overlay`, `failed_parse`, `skipped_length_mismatch`, `skipped_pua_title`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_moedict_parsing.py`:

```python
import json
import tempfile

import pinyin_jyutping.data


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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_moedict_parsing.py -k MoedictIngestion -v`
Expected: FAIL with `AttributeError: module 'pinyin_jyutping.parser' has no attribute 'parse_moedict'`

- [ ] **Step 3: Add the required imports**

At the top of `pinyin_jyutping/parser.py`, alongside the existing `import logging` / `import pprint` / `import re` / `import copy`:

```python
import collections
import json
import lzma
```

- [ ] **Step 4: Write the implementation**

Append to the moedict section of `pinyin_jyutping/parser.py`:

```python
# moedict marks characters with no Unicode encoding like {[8ff0]}
MOEDICT_PUA_MARKER = '{['

# moedict spells every compound with 臺, while everyday Taiwanese writing uses 台.
# register both so that 台灣 / 台北 / 電台 resolve as words rather than falling back
# to character-by-character conversion.
MOEDICT_TAI_DICTIONARY = '臺'
MOEDICT_TAI_COMMON = '台'


def moedict_open(filepath):
    if filepath.endswith('.xz'):
        return lzma.open(filepath, 'rt', encoding='utf8')
    return open(filepath, 'r', encoding='utf8')


def parse_moedict(filepath, data):
    counter = collections.Counter()
    with moedict_open(filepath) as filehandle:
        entries = json.load(filehandle)
    logger.debug(f'moedict: loaded {len(entries)} entries from {filepath}')
    for entry in entries:
        title = entry['title']
        if MOEDICT_PUA_MARKER in title:
            logger.warning(f'moedict: skipping entry with unencodable title: {title}')
            counter['skipped_pua_title'] += 1
            continue
        for heteronym in entry.get('heteronyms', []):
            parse_moedict_heteronym(title, heteronym, data, counter)
    logger.info(f'moedict: ingestion complete, {dict(counter)}')
    return counter


def parse_moedict_heteronym(title, heteronym, data, counter):
    pinyin = heteronym.get('pinyin')
    if not pinyin:
        logger.warning(f'moedict: no pinyin for {title}, skipping')
        counter['skipped_no_pinyin'] += 1
        return

    logger.debug(f'moedict: parsing {title} [{pinyin}]')
    try:
        syllables = parse_pinyin(pinyin)
    except errors.PinyinSyllableNotFound:
        rewritten = moedict_rewrite_erhua(pinyin)
        logger.debug(f'moedict: retrying {title} with erhua rewrite [{rewritten}]')
        try:
            syllables = parse_pinyin(rewritten)
        except errors.PinyinSyllableNotFound as e:
            logger.error(f'moedict: could not parse {title} [{pinyin}]: {e}')
            counter['failed_parse'] += 1
            return
        counter['erhua_rewritten'] += 1

    chinese = clean_chinese(title)
    if len(chinese) != len(syllables):
        logger.warning(f'moedict: inconsistent lengths for {title} [{pinyin}], '
                       f'{len(chinese)} characters and {len(syllables)} syllables, skipping')
        counter['skipped_length_mismatch'] += 1
        return

    logger.debug(f'moedict: ingesting {chinese} as {syllables}')
    process_word(chinese, syllables, data.pinyin_map)
    counter['ingested'] += 1

    if MOEDICT_TAI_DICTIONARY in chinese:
        overlay = chinese.replace(MOEDICT_TAI_DICTIONARY, MOEDICT_TAI_COMMON)
        logger.debug(f'moedict: registering 台 spelling {overlay} for {chinese}')
        process_word(overlay, syllables, data.pinyin_map)
        counter['tai_overlay'] += 1
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_moedict_parsing.py -v`
Expected: 10 passed

- [ ] **Step 6: Run the full suite**

Run: `pytest tests`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add pinyin_jyutping/parser.py tests/test_moedict_parsing.py
git commit -m "feat: add moedict ingestion with 臺/台 orthographic overlay"
```

---

### Task 3: Build pipeline and packaging

Produces `pinyin_jyutping/pinyin_moedict.pkl`. Everything after this task depends on that file existing.

**Files:**
- Modify: `pinyin_jyutping/constants.py:3` (add constants below `PICKLE_DATA_FILENAME`)
- Modify: `tools/build_data.py`
- Modify: `MANIFEST.in`
- Modify: `README.rst` (attribution only; usage docs come in Task 4)

**Interfaces:**
- Consumes: `parser.parse_moedict` from Task 2.
- Produces: `constants.VARIANT_CEDICT`, `constants.VARIANT_MOEDICT`, `constants.PICKLE_MOEDICT_DATA_FILENAME`, `constants.PICKLE_FILENAME_MAP` (a `dict[str, str]` mapping variant name to pickle filename), all used by Task 4. Plus the built pickle file.

Note: `temp_data/` is already in `.gitignore:24`, so no change is needed there.

- [ ] **Step 1: Add the constants**

In `pinyin_jyutping/constants.py`, replace line 3 (`PICKLE_DATA_FILENAME='pinyin_jyutping.pkl'`) with:

```python
VARIANT_CEDICT = 'cedict'
VARIANT_MOEDICT = 'moedict'

PICKLE_DATA_FILENAME='pinyin_jyutping.pkl'
PICKLE_MOEDICT_DATA_FILENAME='pinyin_moedict.pkl'

PICKLE_FILENAME_MAP = {
    VARIANT_CEDICT: PICKLE_DATA_FILENAME,
    VARIANT_MOEDICT: PICKLE_MOEDICT_DATA_FILENAME,
}

# pinned so that rebuilds are reproducible. bump deliberately, and re-run the
# ingestion count test (FULL_MOEDICT_PARSING_TESTS=yes) when you do.
MOEDICT_REPO_COMMIT = 'a6dc997417507eb510fc29822bc514de2c92728c'
MOEDICT_SOURCE_FILENAME = 'dict-revised.json.xz'
MOEDICT_SOURCE_URL = f'https://raw.githubusercontent.com/g0v/moedict-data/{MOEDICT_REPO_COMMIT}/{MOEDICT_SOURCE_FILENAME}'
MOEDICT_TEMP_DATA_DIRECTORY = 'temp_data'
```

- [ ] **Step 2: Extend the build script**

In `tools/build_data.py`, add `import urllib.request` and `import jieba` to the imports at the top, then insert this before the `# write output` section and after the jyutping ingestion:

```python
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
```

`logger.warning` is used rather than `logger.info` because `build_data.py:7` configures `logging.basicConfig(level=logging.WARN)`, so `info` would not print.

- [ ] **Step 3: Run the build**

Run: `python tools/build_data.py`
Expected: takes roughly a minute (14.7MB download, then ~15s of ingestion) and prints a counter matching:

```
{'ingested': 162424, 'skipped_no_pinyin': 1479, 'erhua_rewritten': 1641,
 'tai_overlay': 381, 'failed_parse': 6, 'skipped_length_mismatch': 5,
 'skipped_pua_title': 4}
```

If the numbers differ, the pinned commit has probably been changed — stop and report rather than adjusting the expected values.

- [ ] **Step 4: Verify the pickle**

Run:
```bash
python -c "
import pickle
d = pickle.load(open('pinyin_jyutping/pinyin_moedict.pkl','rb'))
print('map size:', len(d.pinyin_map))
print('台灣 present:', '台灣' in d.pinyin_map)
"
```
Expected: `map size: 174621` and `台灣 present: True`

- [ ] **Step 5: Add the pickle to the distribution**

In `MANIFEST.in`, append a line so the file reads:

```
include pinyin_jyutping/dict.txt.big
include pinyin_jyutping/pinyin_jyutping.pkl
include pinyin_jyutping/pinyin_moedict.pkl
```

- [ ] **Step 6: Add attribution to the README**

In `README.rst`, in the `How it works` section, append this paragraph after the existing CC-Canto sentence:

```rst
Traditional Chinese can optionally be converted using the Taiwanese Ministry of Education's 重編國語辭典修訂本 instead, via the ``moedict`` variant. That data comes from https://github.com/g0v/moedict-data and is used under the Ministry's public licence; only pronunciations are used, not definitions.
```

- [ ] **Step 7: Confirm the existing suite still passes**

Run: `pytest tests`
Expected: all pass (the new pickle is not read by anything yet)

- [ ] **Step 8: Commit**

```bash
git add pinyin_jyutping/constants.py tools/build_data.py MANIFEST.in README.rst
git commit -m "feat: build pinyin_moedict.pkl from pinned moedict source"
```

Note: `pinyin_jyutping/pinyin_moedict.pkl` is **not** committed — `.gitignore:12` excludes `*.pkl`, matching how the existing pickle is handled.

---

### Task 4: Variant selection API

**Files:**
- Modify: `pinyin_jyutping/__init__.py` (rewrite the class body; the file is 56 lines)
- Modify: `README.rst` (usage docs)
- Test: `tests/test_moedict_variant.py` (create)

**Interfaces:**
- Consumes: `constants.VARIANT_CEDICT`, `constants.VARIANT_MOEDICT`, `constants.PICKLE_FILENAME_MAP` from Task 3, and the built pickle.
- Produces: `PinyinJyutping(variant=...)`, `.pinyin(text, tone_numbers, spaces, variant=None)`, `.pinyin_all_solutions(text, tone_numbers, spaces, variant=None)`, `.load_pinyin_corrections(corrections, variant=None)`, and the internal `.data_map` dict used by the lazy-loading test.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_moedict_variant.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_moedict_variant.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'variant'`

- [ ] **Step 3: Write the implementation**

Replace the body of `pinyin_jyutping/__init__.py` from the `class PinyinJyutping():` line to the end of the file with:

```python
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
```

Note `self.data` is kept and still points at the CC-CEDICT `Data`, so the jyutping methods and any external code reading `.data` are unaffected.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_moedict_variant.py -v`
Expected: 11 passed

- [ ] **Step 5: Run the full suite**

Run: `pytest tests`
Expected: all pass, including every pre-existing test unmodified

- [ ] **Step 6: Document the variant in the README**

In `README.rst`, after the `**Jyutping**` block and before `How it works`, add:

```rst
**Taiwan / moedict pinyin**

Pinyin can be generated from the Taiwanese Ministry of Education dictionary instead of CC-CEDICT, which gives Taiwan-standard readings:

>>> import pinyin_jyutping
>>> p = pinyin_jyutping.PinyinJyutping(variant='moedict')
>>> p.pinyin('垃圾分類')
'lèsè fēnlèi'
>>> p.pinyin('研究所學生')
'yánjiùsuǒ xuéshēng'

The variant can also be chosen per call:

>>> p = pinyin_jyutping.PinyinJyutping()
>>> p.pinyin('垃圾分類', variant='moedict')
'lèsè fēnlèi'

The ``moedict`` variant expects Traditional Chinese. Simplified characters are not in the dictionary and pass through unconverted.
```

- [ ] **Step 7: Commit**

```bash
git add pinyin_jyutping/__init__.py tests/test_moedict_variant.py README.rst
git commit -m "feat: add variant selection to PinyinJyutping"
```

---

### Task 5: Behavioural test suite

Pins the reading differences, the traditional-only contract, and the ingestion counts against the real source.

**Files:**
- Test: `tests/test_moedict_conversion.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the tests**

Create `tests/test_moedict_conversion.py`:

```python
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
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/test_moedict_conversion.py -v`
Expected: 8 passed, 1 skipped (the full-source test)

- [ ] **Step 3: Run the full-source ingestion test**

Run: `FULL_MOEDICT_PARSING_TESTS=yes pytest tests/test_moedict_conversion.py -k test_ingestion_counts -v`
Expected: PASS. Takes roughly 15 seconds.

- [ ] **Step 4: Run the whole suite one final time**

Run: `pytest tests`
Expected: all pass. Confirm no pre-existing test file was modified:

```bash
git status --short tests/
```
Expected: only the three new `test_moedict_*.py` files appear.

- [ ] **Step 5: Commit**

```bash
git add tests/test_moedict_conversion.py
git commit -m "test: pin moedict reading signature and ingestion counts"
```

---

## Verification checklist

After all tasks, confirm:

- [ ] `pytest tests` passes with no pre-existing test modified
- [ ] `FULL_MOEDICT_PARSING_TESTS=yes pytest tests` passes
- [ ] `PinyinJyutping()` with no arguments never opens `pinyin_moedict.pkl`
- [ ] `python tools/build_data.py` is re-runnable and reuses the cached download
- [ ] `git status` shows no `.pkl` file staged
