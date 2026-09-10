# Design: moedict as a selectable pinyin dictionary variant

Date: 2026-09-10
Status: approved for planning

## Context

Pinyin conversion is currently driven by a single source, CC-CEDICT, ingested by
`parser.parse_cedict()` into `data.Data.pinyin_map`. CC-CEDICT carries
predominantly mainland readings.

The Taiwanese Ministry of Education's 重編國語辭典修訂本, published in machine-readable
form at [g0v/moedict-data](https://github.com/g0v/moedict-data), is an alternative
source for the same mapping. Each entry already carries Hanyu Pinyin with
diacritics, one syllable per character, which the existing `parser.parse_pinyin()`
reads natively. Feeding all 162,435 readings through the current parser unmodified
produces 160,783 (99.0%) that both parse and match their headword's character count.

This design adds moedict as a second selectable source rather than replacing
CC-CEDICT.

## Goals

- Make moedict available as an alternative pinyin dictionary, selected per instance
  or per call.
- Leave the default behaviour, the existing pickle, and every existing test
  untouched.
- Leave Jyutping conversion entirely untouched.

## Non-goals

- **Simplified Chinese under the moedict variant.** moedict is traditional-only.
  This is a documented contract, not a defect: see "Unknown characters" below.
- **Erhua rendering.** `一會兒` renders as `yīhuǐer` rather than `yīhuǐr`. CC-CEDICT
  already produces `yíhuìer` today, so this is pre-existing rendering behaviour
  shared by both variants and out of scope here.
- **Bopomofo output.** moedict ships a `bopomofo` field; this design ignores it.
- **A second heteronym ranking mechanism.** See "Ranking" below.

## Naming

Variants are named after their source: `'cedict'` (the default) and `'moedict'`.

A locale-based name such as `'tw'` was rejected. moedict is the MOE's prescriptive
citation standard, not Taiwanese Mandarin as spoken — it prescribes `企業 qìyè` and
`和 hàn`, which many speakers in Taiwan do not use. `'moedict'` promises exactly what
the data is. The same argument applies in reverse to CC-CEDICT, which is a mixed
community dictionary rather than a mainland standard. Naming one variant after a
source and the other after a locale would also be an incoherent taxonomy. No `'tw'`
alias is provided.

## Data source

Repository: `https://github.com/g0v/moedict-data`
File: `dict-revised.json.xz` (14.7MB compressed, 80.3MB raw)

The build pins a specific commit rather than tracking `main`, so that a rebuild
produces the same dictionary:

```python
# constants.py
MOEDICT_REPO_COMMIT = 'a6dc997417507eb510fc29822bc514de2c92728c'  # 2026-07-11
MOEDICT_SOURCE_URL = (
    f'https://raw.githubusercontent.com/g0v/moedict-data/{MOEDICT_REPO_COMMIT}/dict-revised.json.xz'
)
```

`tools/build_data.py` downloads into the gitignored `temp_data/` directory and
reuses the file if already present, so repeated builds hit the network once.
Decompression uses `lzma` from the standard library. The source file is not
committed to this repository.

### Structure

```json
{"title": "並時",
 "heteronyms": [{"bopomofo": "ㄅㄧㄥˋ ㄕˊ",
                 "pinyin": "bìng shí",
                 "definitions": [...]}]}
```

161,194 entries, 163,918 heteronyms. Only `title` and `heteronyms[].pinyin` are
consumed; definitions, radicals and stroke counts are ignored.

## Data model and packaging

Two pickles, each containing an ordinary `data.Data`:

| File | `pinyin_map` | `jyutping_map` |
|---|---|---|
| `pinyin_jyutping.pkl` | CC-CEDICT | CC-Canto |
| `pinyin_moedict.pkl` | moedict | empty |

Because the moedict variant is a whole `Data` object rather than a third map inside
the existing one, `conversion.py`, `logic.py`, `syllables.py` and `constants.py`
need no structural changes — `conversion.convert_pinyin_single_solution(data, …)`
already accepts a `Data` and reads `.pinyin_map`. Variant selection reduces to
choosing which `Data` to pass.

This also keeps the existing pickle byte-identical in structure, so an older pickle
still loads.

`pinyin_moedict.pkl` is roughly 8MB and is added to `MANIFEST.in`.

## Ingestion

New function in `parser.py`:

```python
def parse_moedict(filepath, data) -> collections.Counter
```

Rules, applied per heteronym in order:

1. Skip entries whose `title` contains `{[…]}` — a placeholder for characters with
   no Unicode encoding (2 entries).
2. Skip heteronyms with no `pinyin` field (1,481).
3. `parse_pinyin(pinyin)`. On `PinyinSyllableNotFound`, retry once with erhua
   rewritten, then give up.
4. Skip when `len(clean_chinese(title)) != len(syllables)`.
5. `process_word(chinese, syllables, data.pinyin_map)` — unchanged, so tokenized
   subwords and per-character entries are generated exactly as for CC-CEDICT.
6. If the title contains `臺`, call `process_word` a second time with `臺` replaced
   by `台`. See "Orthographic variants" below.

### Orthographic variants: 臺 and 台

moedict spells every compound with `臺` and never with `台`. Everyday Taiwanese
writing overwhelmingly does the opposite. Without a fix, the most ordinary
vocabulary in the variant's own target language misses at the word level:

```
台灣 台北 台中 台南 台東 電台 舞台 台幣 台語 台商 平台 後台 櫃台
  → 13 of 13 absent from moedict as headwords
  → 12 of 13 present under 臺
```

These still convert correctly today, because the per-character fallback finds
`台 → tái`. But that is luck, not design: it holds only while `tái` stays the
top-ranked reading of `台`, and it forfeits both word-level heteronym
disambiguation and `conversion.improve_tokenization`, which tests `word in
word_map` and so silently stops improving tokenization for every one of these
words.

Step 6 therefore registers the `台` spelling of every `臺` headword:

```
moedict headwords containing 臺: 380  (381 readings, one has two heteronyms)
collisions with an existing 台 entry: 2  (天臺 / 天台 and 臺 / 台, identical readings)
```

Verified against a prototype build: 12 of the 13 words above become headwords. The
holdout is `台東`, which moedict does not carry under either spelling — it has no
`臺東` entry to overlay. That word continues to rely on per-character fallback, which
renders it correctly.

Only this one pair is handled. moedict holds the modern standard form of the other
common 異體字 pairs — `裡 為 麵 群 峰 床 眾 抬 偽` — so no overlay is needed for them;
input written with the archaic counterpart (`裏 爲 麪 羣 峯 牀 衆 擡 僞`) falls under
the passthrough contract below. `臺/台` is the exception because it is the one pair
where moedict's choice is the *less* common spelling in real use.

### Erhua rewrite

moedict writes erhua as a bare trailing `r` on the preceding syllable (`一會兒` →
`yī huǐr`), which is not a syllable the parser knows. The rewrite splits it into its
own neutral-tone `er` syllable, which also restores the one-syllable-per-character
invariant that step 4 checks.

The rule operates on whitespace-separated tokens, not as a regex over the whole
string:

```python
MOEDICT_ER_SYLLABLES = {'er', 'ēr', 'ér', 'ěr', 'èr'}

def moedict_rewrite_erhua(pinyin):
    tokens = []
    for token in pinyin.split(' '):
        if token.endswith('r') and token not in MOEDICT_ER_SYLLABLES:
            tokens.append(token[:-1])
            tokens.append('er5')
        else:
            tokens.append(token)
    return ' '.join(tokens)
```

Token-level comparison is required, and a character lookbehind cannot substitute for
it. The ambiguity is between `èr`, which is the syllable *er* and must be left alone,
and `zhèr`, `yèr`, `gér`, `juér`, which are erhua on a syllable ending in an e-vowel
and must be split. Both have `r` preceded by an e-form vowel, so no lookbehind can
separate them — only "is this whole token an er-syllable?" can. A naive `(?<!e)`
additionally fails to protect `èr` at all, since `è` is U+00E8 and not `e`.

This recovers all 1,641 erhua entries.

### Expected yield

These are the exact counter keys `parse_moedict` returns, and the values the
ingestion test asserts:

| Counter key | Count |
|---|---|
| `ingested` | 162,424 |
| `skipped_no_pinyin` | 1,479 |
| `erhua_rewritten` | 1,641 |
| `tai_overlay` | 381 |
| `failed_parse` | 6 |
| `skipped_length_mismatch` | 5 |
| `skipped_pua_title` | 4 |

Resulting `pinyin_map` size: 174,621 keys.

`skipped_pua_title` counts *entries*, skipped before their heteronyms are examined;
every other key counts heteronyms. The eleven parse failures and length mismatches
are all traceable to defects in the source data — `啐` given as `"q"`, `塞` as
`"seī"`, two entries with unconverted bopomofo, `誒` as `"ề"`, and four titles
containing `．` or a mid-sentence `，`.

`ingested` counts readings. `tai_overlay` re-registers 381 of them under their `台`
spelling and is reported separately rather than added to `ingested`.

Build time is approximately 13 seconds.

### Logging

Following the conventions already in `parser.py`:

- `logger.debug` — per-entry: the title and pinyin being parsed, and the syllables
  produced.
- `logger.debug` — when the erhua rewrite is attempted, and whether it succeeded.
- `logger.warning` — per skipped entry, with the title, the pinyin, and the reason
  (missing field, length mismatch, PUA title). These are individually recoverable
  conditions, matching how `parse_cedict_entries` warns.
- `logger.error` — per entry that cannot be parsed even after the erhua retry,
  matching `parse_cccanto_definition_generator`.
- `logger.info` — one summary line at the end with the full counter.

`parse_moedict` returns the same counts as a `collections.Counter` in addition to
logging them, so tests can assert on the numbers directly rather than capturing log
output.

## Public API

`variant` is accepted by the constructor as an instance default, and by each pinyin
method as a per-call override:

```python
p = pinyin_jyutping.PinyinJyutping(variant='moedict')
p.pinyin('垃圾分類')                        # 'lèsè fēnlèi'

p = pinyin_jyutping.PinyinJyutping()        # unchanged default
p.pinyin('垃圾分类')                        # 'lājī fēnlèi'
p.pinyin('垃圾分類', variant='moedict')      # 'lèsè fēnlèi'
```

- Accepted values are `'cedict'` (default) and `'moedict'`; any other value raises
  `ValueError`.
- `variant` applies to `pinyin()` and `pinyin_all_solutions()`.
- `jyutping()` and `jyutping_all_solutions()` ignore it — `jyutping_map` is
  unaffected by this change.
- `load_pinyin_corrections()` takes `variant`, defaulting to the instance default,
  so a correction lands in one variant's map rather than silently in both.
  `load_jyutping_corrections()` is unchanged.

### Loading

`pinyin_moedict.pkl` is read on first use of the moedict variant and cached on the
instance, so callers who never use it pay nothing at import. Passing
`variant='moedict'` to the constructor triggers the load eagerly, so the cost is
paid predictably at construction rather than on a later call.

## Behaviour

### Unknown characters

Characters absent from the moedict map pass through unchanged, exactly as the
existing non-Chinese passthrough in `conversion.solutions_array_for_word` does.

The consequence is that simplified input silently half-converts, because many
characters are shared between the scripts: `我们` yields `wǒ们` (no space — jieba keeps
it as a single token, and the unmatched character renders inline). This is documented
as the traditional-only contract of the moedict variant rather than guarded against.
No error is raised and no fallback to the CC-CEDICT map occurs — a fallback would
silently mix two sources' conventions in a single output.

The same applies to archaic 異體字 that moedict does not carry (`裏 爲 麪 羣 峯 牀 衆
擡 僞` and similar): they emit as raw hanzi. Around 23 of the 3,000 most frequent
traditional characters fall into this category. CC-CEDICT carries both forms of each
pair, so the default variant is unaffected.

### Tone sandhi

moedict stores citation tones and does not encode sandhi: `一定` is `yī dìng`, `不對`
is `bù duì`. The existing `logic.apply_pinyin_tone_change` keys off the characters
一 and 不 directly rather than off dictionary contents, so it applies unchanged and
these render as `yí dìng` and `bú duì`.

This is deliberate: it matches how Taiwanese Mandarin is spoken and keeps behaviour
consistent between the two variants.

### Ranking

moedict carries no frequency data, and its heteronyms are ordered phonetically
rather than by frequency — `會` lists `guì, kuài, huǐ, huì`; `行` lists `háng, hàng,
xíng, xìng`. Ranking therefore relies entirely on the existing occurrence-counting
in `process_word`, which accumulates across every headword containing a reading.

Measured against CC-CEDICT's top choice, over *traditional* characters ranked by
frequency derived from the vendored `dict.txt.big`. Restricting to traditional
characters is what makes the comparison meaningful — of the 3,000 most frequent
characters overall, 716 are simplified-only and therefore outside this variant's
domain by design.

| Most frequent traditional characters | Covered by moedict | Top-1 differs |
|---|---|---|
| 300 | 298 (99.3%) | 5 (1.7%) |
| 1,000 | 995 (99.5%) | 29 (2.9%) |
| 3,000 | 2,977 (99.2%) | 137 (4.6%) |

Coverage is effectively complete; the handful missing are variant forms (`爲 裏 衆
羣 牀 峯`) that moedict indexes under their standard form instead.

At 300 the differences are `個 ge4→ge5`, `期 qī→qí`, `場 chǎng→cháng`, `么 me→yāo`
and `万 wàn→mò`. The first three are correct MOE standard. The last two are a
genuine artifact and are described below.

This is good enough that seeding occurrence counts from a frequency list is not
worth introducing a second ranking mechanism. If the 4.6% figure at 3,000 proves
troublesome in practice, that decision can be revisited independently.

### Out of contract: simplified forms that collide with rare traditional characters

`么` and `万` are in common modern use as simplified forms of `麼` and `萬`, but each
also exists as a distinct rare traditional character with its own reading. moedict,
being a traditional dictionary, knows only the rare reading: `么 yāo` and
`万 mò` (as in `万俟`). Under this variant they convert that way.

These are **simplified characters, and therefore already outside this variant's
traditional-only contract** — well-formed traditional input writes `麼` and `萬`.
They are recorded here and pinned by test so the behaviour is a decision rather than
an accident, but they are not special-cased. Adding an override list for input the
variant does not claim to accept would invite indefinite additions.

Note the contrast with `臺/台` above, which is *not* this class: `台` is legitimate
traditional Taiwanese orthography and so must work by design rather than by luck.

### Expected differences from the default variant

```
垃圾分類     lājī fēnlèi          →  lèsè fēnlèi
企業管理     qǐyè guǎnlǐ          →  qìyè guǎnlǐ
星期日       xīngqīrì             →  xīngqírì
研究所學生    yánjiūsuǒ xuésheng   →  yánjiùsuǒ xuéshēng
我喜歡吃…     xǐhuan               →  xǐhuān
```

Note the systematic one: the MOE standard largely does not use neutral tone, so
`學生 xuéshēng`, `名字 míngzì`, `事情 shìqíng`.

### Coverage

moedict has 162,079 multi-character headwords to CC-CEDICT's 186,281, with 55,294 in
common. The two sources trade rather than nest: moedict is deeper on idioms and
literary vocabulary, CC-CEDICT on modern terms and proper nouns. This is a further
argument for keeping both variants rather than replacing one with the other.

## Testing

Every existing test targets the default variant and must keep passing unmodified.
That is the primary regression guard for this change.

New tests:

- **Erhua rewrite** — unit tests covering both sides of the ambiguity: `èr chár`
  (leading er-syllable preserved, trailing erhua split) and `zhèr`, `juér`, `yèr`
  (erhua on an e-vowel syllable, which must still split). These are the cases a
  lookbehind implementation gets wrong, so they are the tests that pin the design.
  Plus `一會兒` end to end.
- **Ingestion counts** — assert the returned `Counter` against the expected-yield
  table, guarding against silent source-format drift. Requires the source file, so
  it follows the existing `FULL_CEDICT_PARSING_TESTS` env-var pattern and skips by
  default.
- **Variant selection** — constructor default, per-call override, per-call override
  of a non-default instance default, and `ValueError` on an unknown variant.
- **Lazy loading** — the moedict pickle is not read when the variant is never used.
- **Unknown-character passthrough** — `我们` under the moedict variant yields
  `wǒ们`.
- **Reading signature** — the `垃圾 / 企業 / 星期日 / 研究 / 喜歡 / 學生` set above, as
  the behavioural fingerprint of the variant.
- **Orthographic overlay** — `台灣 台北 台中 電台 舞台 平台` are present as *headwords*, not
  merely reachable via per-character fallback. Asserting map membership rather than
  only the rendered output is the point: the rendered output was already correct
  before the overlay existed, so an output-only test would pass without the feature.
- **Out-of-contract artifact** — `么` and `万` convert as `yāo` and `mò`, pinned
  deliberately so the behaviour is a recorded decision rather than an accident that
  later drifts.
- **Corrections** — a correction loaded for one variant does not affect the other.

Tests that need `pinyin_moedict.pkl` skip when it is absent, so a checkout that has
only run the default build still passes.

## Licensing and attribution

The MOE text is licensed CC BY-ND 3.0 TW. The MOE's own published interpretation is
that the no-derivatives restriction applies to the text itself and does not restrict
format conversion or downstream application. This design consumes only readings —
facts about pronunciation — and no definition text. The g0v repository's own
reformatting is released by @kcwu under CC0.

This package is GPL. Attribution for the moedict source is added to `README.rst`
alongside the existing CC-Canto attribution.

## Risks and open items

- **Source drift.** Mitigated by pinning a commit; the ingestion-count test surfaces
  drift when the pin is moved.
- **Build requires network.** New, and a change from the fully vendored CC-CEDICT
  build. The download is cached in `temp_data/` and only the maintainer runs
  `build_data.py`, so end users are unaffected.
- **Package size.** The distribution grows by roughly 8MB. Accepted; there is no
  lazy-download mechanism in scope.
