pinyin-jyutping
===============

Python module which converts a Chinese sentence from Simplified/Traditional to Mandarin/Pinyin and Traditional/Simplified to Cantonese/Jyutping, outputting diacritics (accented characters), or tone numbers. I designed this library to create Mandarin and Cantonese flashcards.

Compared to other Pinyin python modules, this one offers the following particular features:

* It can intelligently translate a full sentence, using spaces between words for clarity.
* It will tell you about all the possible transliterations, giving you the option to choose which one is the correct one.

Want to support my work on this module ? Become a supporter: https://www.patreon.com/lucw

Install
-------

.. code:: bash

    $ pip install pinyin_jyutping

Usage
-----

**Pinyin**

generate the best solution:

>>> import pinyin_jyutping
>>> p = pinyin_jyutping.PinyinJyutping()
>>> p.pinyin('忘拿一些东西了')
'wàng ná yīxiē dōngxī le'
>>> p.pinyin('忘拿一些东西了', tone_numbers=True)
'wang4 na2 yi1xie1 dong1xi1 le5'    
>>> p.pinyin('忘拿一些东西了', tone_numbers=True, spaces=True)
'wang4 na2 yi1 xie1 dong1 xi1 le5'    

generate all possible solutions:

>>> import pinyin_jyutping
>>> p = pinyin_jyutping.PinyinJyutping()
>>> p.pinyin_all_solutions('忘拿一些东西了')
{'word_list': ['忘', '拿', '一些', '东西', '了'], 'solutions': [['wàng'], ['ná'], ['yīxiē'], ['dōngxī', 'dōngxi'], ['le', 'liǎo', 'liào']]}

**Jyutping**

generate the best solution:

>>> import pinyin_jyutping
>>> j = pinyin_jyutping.PinyinJyutping()
>>> j.jyutping('我出去攞野食')
'ngǒ cēothêoi ló jěsik'
>>> j.jyutping('我出去攞野食', tone_numbers=True)
'ngo5 ceot1heoi3 lo2 je5sik6'
>>> j.jyutping('我出去攞野食', tone_numbers=True, spaces=True)
'ngo5 ceot1 heoi3 lo2 je5 sik6'    

generate all possible solutions:

>>> import pinyin_jyutping
>>> j = pinyin_jyutping.PinyinJyutping()
>>> j.jyutping_all_solutions('我出去攞野食')
{'word_list': ['我', '出去', '攞', '野食'], 'solutions': [['ngǒ'], ['cēothêoi'], ['ló', 'lō'], ['jěsik', 'jězi', 'jěsit', 'jězik']]}

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

Command line
------------

A ``pinyin-jyutping`` command converts columns of a CSV file, which is handy for Anki exports and other flashcard data. The file must have a header row, and each ``--column`` names an input column holding Chinese and an output column to write the transliteration to:

.. code:: bash

    $ pinyin-jyutping deck.csv deck_with_pinyin.csv --column chinese:pinyin

The output column is overwritten if it already exists, and appended to the file otherwise. ``--column`` can be repeated to convert several columns in one pass:

.. code:: bash

    $ pinyin-jyutping deck.csv out.csv --column front:front_pinyin --column back:back_pinyin

Use ``--inplace`` to write the result back to the input file instead of passing an output file:

.. code:: bash

    $ pinyin-jyutping deck.csv --inplace --column chinese:pinyin

Other options:

* ``--mode pinyin|jyutping`` chooses the conversion, applied to every column pair (default: ``pinyin``)
* ``--variant cedict|moedict`` chooses the pinyin dictionary (default: ``cedict``); ``moedict`` holds no jyutping data
* ``--tone-numbers`` outputs tone numbers instead of diacritics
* ``--spaces`` puts a space between every syllable
* ``--delimiter`` sets the field delimiter, and accepts ``\t`` for tab-separated files (default: ``,``)
* ``--encoding`` sets the file encoding (default: ``utf-8``)

For example, converting a tab-separated Anki export to Jyutping with tone numbers:

.. code:: bash

    $ pinyin-jyutping cantonese.txt out.txt --delimiter '\t' \
        --mode jyutping --tone-numbers --column chinese:jyutping

Empty cells are left empty. If a cell cannot be converted, the output cell is left blank and a warning naming the row is printed to stderr, so one bad row does not stop the run.

How it works
------------

Uses the Jieba library (https://github.com/fxsjy/jieba) to tokenize the sentence. Then words are converted to Pinyin/Jyutping either as a whole, or character by character, using the CC-Canto dictionary (http://cantonese.org/about.html). The Jyutping diacritic conversion is not standard but originally described here: http://www.cantonese.sheik.co.uk/phorum/read.php?1,127274,129006

Traditional Chinese can optionally be converted using the Taiwanese Ministry of Education's 重編國語辭典修訂本 instead, via the ``moedict`` variant. That data comes from https://github.com/g0v/moedict-data and is used under the Ministry's public licence; only pronunciations are used, not definitions.

