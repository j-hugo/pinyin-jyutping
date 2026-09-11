import unittest
import pytest
import argparse
import io
import sys
import os
import csv
import tempfile
import contextlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pinyin_jyutping import cli
from pinyin_jyutping import constants


def write_csv_file(path, fieldnames, rows, delimiter=',', encoding='utf-8'):
    with open(path, 'w', newline='', encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def read_csv_file(path, delimiter=',', encoding='utf-8'):
    with open(path, 'r', newline='', encoding=encoding) as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return reader.fieldnames, list(reader)


def run_cli(argv):
    """run the cli, returning (exit_code, stdout, stderr)"""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            exit_code = cli.main(argv)
        except SystemExit as e:
            exit_code = e.code
    return exit_code, stdout.getvalue(), stderr.getvalue()


class ColumnSpecTests(unittest.TestCase):
    def test_splits_input_and_output_column(self):
        self.assertEqual(cli.parse_column_spec('hanzi:pinyin'), ('hanzi', 'pinyin'))

    def test_rejects_spec_without_colon(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            cli.parse_column_spec('hanzi')

    def test_rejects_empty_input_column(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            cli.parse_column_spec(':pinyin')

    def test_rejects_empty_output_column(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            cli.parse_column_spec('hanzi:')

    def test_rejects_extra_colon(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            cli.parse_column_spec('hanzi:pinyin:extra')


def fake_convert(text):
    return f'[{text}]'


class ConvertRowsTests(unittest.TestCase):
    def test_appends_new_output_column_to_fieldnames(self):
        fieldnames, rows = cli.convert_rows(
            ['hanzi'],
            [{'hanzi': '忘拿'}],
            [('hanzi', 'pinyin')],
            fake_convert)
        self.assertEqual(fieldnames, ['hanzi', 'pinyin'])
        self.assertEqual(rows, [{'hanzi': '忘拿', 'pinyin': '[忘拿]'}])

    def test_existing_output_column_keeps_its_position(self):
        fieldnames, rows = cli.convert_rows(
            ['hanzi', 'pinyin', 'english'],
            [{'hanzi': '忘拿', 'pinyin': 'stale', 'english': 'forgot'}],
            [('hanzi', 'pinyin')],
            fake_convert)
        self.assertEqual(fieldnames, ['hanzi', 'pinyin', 'english'])
        self.assertEqual(rows[0]['pinyin'], '[忘拿]')

    def test_converts_multiple_pairs_in_one_pass(self):
        fieldnames, rows = cli.convert_rows(
            ['front', 'back'],
            [{'front': '忘拿', 'back': '东西'}],
            [('front', 'front_pinyin'), ('back', 'back_pinyin')],
            fake_convert)
        self.assertEqual(fieldnames, ['front', 'back', 'front_pinyin', 'back_pinyin'])
        self.assertEqual(rows[0]['front_pinyin'], '[忘拿]')
        self.assertEqual(rows[0]['back_pinyin'], '[东西]')

    def test_empty_cell_produces_empty_output_without_converting(self):
        converted = []

        def recording_convert(text):
            converted.append(text)
            return fake_convert(text)

        fieldnames, rows = cli.convert_rows(
            ['hanzi'],
            [{'hanzi': ''}, {'hanzi': '   '}],
            [('hanzi', 'pinyin')],
            recording_convert)
        self.assertEqual([row['pinyin'] for row in rows], ['', ''])
        self.assertEqual(converted, [])

    def test_missing_cell_produces_empty_output(self):
        fieldnames, rows = cli.convert_rows(
            ['hanzi'], [{'hanzi': None}], [('hanzi', 'pinyin')], fake_convert)
        self.assertEqual(rows[0]['pinyin'], '')

    def test_conversion_failure_leaves_output_blank_and_warns(self):
        def fail(text):
            raise ValueError('boom')

        warnings = []
        fieldnames, rows = cli.convert_rows(
            ['hanzi'],
            [{'hanzi': '忘拿'}, {'hanzi': '东西'}],
            [('hanzi', 'pinyin')],
            fail,
            warn=warnings.append)
        self.assertEqual([row['pinyin'] for row in rows], ['', ''])
        self.assertEqual(len(warnings), 2)
        self.assertIn('boom', warnings[0])
        self.assertIn('hanzi', warnings[0])

    def test_warning_identifies_the_failing_row(self):
        def fail_on_second(text):
            if text == '东西':
                raise ValueError('boom')
            return fake_convert(text)

        warnings = []
        cli.convert_rows(
            ['hanzi'],
            [{'hanzi': '忘拿'}, {'hanzi': '东西'}],
            [('hanzi', 'pinyin')],
            fail_on_second,
            warn=warnings.append)
        self.assertEqual(len(warnings), 1)
        self.assertIn('row 3', warnings[0])


class ArgumentValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.input_file = os.path.join(self.directory.name, 'input.csv')
        self.output_file = os.path.join(self.directory.name, 'output.csv')
        write_csv_file(self.input_file, ['hanzi'], [{'hanzi': '你好'}])

    def test_inplace_with_output_file_is_an_error(self):
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--inplace', '--column', 'hanzi:pinyin'])
        self.assertEqual(exit_code, 2)
        self.assertIn('--inplace', stderr)
        self.assertFalse(os.path.exists(self.output_file))

    def test_missing_output_file_without_inplace_is_an_error(self):
        exit_code, stdout, stderr = run_cli([self.input_file, '--column', 'hanzi:pinyin'])
        self.assertEqual(exit_code, 2)
        self.assertIn('--inplace', stderr)

    def test_duplicate_output_columns_are_an_error(self):
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file,
             '--column', 'hanzi:pinyin', '--column', 'hanzi:pinyin'])
        self.assertEqual(exit_code, 2)
        self.assertIn('pinyin', stderr)
        self.assertFalse(os.path.exists(self.output_file))

    def test_unknown_input_column_is_an_error_listing_available_columns(self):
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin'])
        self.assertEqual(exit_code, 2)
        self.assertIn('chinese', stderr)
        self.assertIn('hanzi', stderr)
        self.assertFalse(os.path.exists(self.output_file))

    def test_jyutping_with_moedict_variant_is_an_error(self):
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'hanzi:jyut',
             '--mode', 'jyutping', '--variant', 'moedict'])
        self.assertEqual(exit_code, 2)
        self.assertIn('moedict', stderr)

    def test_missing_column_argument_is_an_error(self):
        exit_code, stdout, stderr = run_cli([self.input_file, self.output_file])
        self.assertEqual(exit_code, 2)
        self.assertIn('--column', stderr)

    def test_malformed_column_argument_is_an_error(self):
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'hanzi'])
        self.assertEqual(exit_code, 2)
        self.assertIn('INPUT_COLUMN:OUTPUT_COLUMN', stderr)

    def test_missing_input_file_is_an_error(self):
        exit_code, stdout, stderr = run_cli(
            [os.path.join(self.directory.name, 'nope.csv'), self.output_file,
             '--column', 'hanzi:pinyin'])
        self.assertEqual(exit_code, 2)
        self.assertIn('nope.csv', stderr)

    def test_empty_input_file_is_an_error(self):
        empty_file = os.path.join(self.directory.name, 'empty.csv')
        open(empty_file, 'w').close()
        exit_code, stdout, stderr = run_cli(
            [empty_file, self.output_file, '--column', 'hanzi:pinyin'])
        self.assertEqual(exit_code, 2)
        self.assertIn('header', stderr)


MOEDICT_PICKLE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', 'pinyin_jyutping',
    constants.PICKLE_MOEDICT_DATA_FILENAME))

requires_moedict_pickle = pytest.mark.skipif(
    not os.path.isfile(MOEDICT_PICKLE_PATH),
    reason='pinyin_moedict.pkl not built, run python tools/build_data.py')


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.input_file = os.path.join(self.directory.name, 'input.csv')
        self.output_file = os.path.join(self.directory.name, 'output.csv')

    def test_writes_pinyin_into_a_new_column(self):
        write_csv_file(self.input_file, ['chinese', 'english'],
                       [{'chinese': '忘拿一些东西了', 'english': 'forgot something'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file)
        self.assertEqual(fieldnames, ['chinese', 'english', 'pinyin'])
        self.assertEqual(rows[0]['pinyin'], 'wàng ná yīxiē dōngxī le')
        self.assertEqual(rows[0]['english'], 'forgot something')

    def test_writes_jyutping_when_mode_is_jyutping(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '我出去攞野食'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:jyutping',
             '--mode', 'jyutping'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file)
        self.assertEqual(rows[0]['jyutping'], 'ngǒ cēothêoi ló jěsik')

    def test_tone_numbers_flag(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '忘拿一些东西了'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin',
             '--tone-numbers'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file)
        self.assertEqual(rows[0]['pinyin'], 'wang4 na2 yi1xie1 dong1xi1 le5')

    def test_spaces_flag(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '忘拿一些东西了'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin',
             '--tone-numbers', '--spaces'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file)
        self.assertEqual(rows[0]['pinyin'], 'wang4 na2 yi1 xie1 dong1 xi1 le5')

    def test_output_is_a_string_not_a_list(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '东西'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file)
        # 东西 has several solutions, only the best one is written, unbracketed
        self.assertEqual(rows[0]['pinyin'], 'dōngxī')

    def test_converts_two_column_pairs_in_one_run(self):
        write_csv_file(self.input_file, ['front', 'back'],
                       [{'front': '忘拿一些东西了', 'back': '东西'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file,
             '--column', 'front:front_pinyin', '--column', 'back:back_pinyin'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file)
        self.assertEqual(fieldnames, ['front', 'back', 'front_pinyin', 'back_pinyin'])
        self.assertEqual(rows[0]['front_pinyin'], 'wàng ná yīxiē dōngxī le')
        self.assertEqual(rows[0]['back_pinyin'], 'dōngxī')

    def test_overwrites_an_existing_output_column(self):
        write_csv_file(self.input_file, ['chinese', 'pinyin'],
                       [{'chinese': '东西', 'pinyin': 'stale value'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file)
        self.assertEqual(fieldnames, ['chinese', 'pinyin'])
        self.assertEqual(rows[0]['pinyin'], 'dōngxī')

    def test_empty_cells_stay_empty(self):
        write_csv_file(self.input_file, ['chinese'],
                       [{'chinese': '东西'}, {'chinese': ''}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file)
        self.assertEqual([row['pinyin'] for row in rows], ['dōngxī', ''])

    def test_inplace_rewrites_the_input_file(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '东西'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, '--inplace', '--column', 'chinese:pinyin'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.input_file)
        self.assertEqual(fieldnames, ['chinese', 'pinyin'])
        self.assertEqual(rows[0]['pinyin'], 'dōngxī')

    def test_tab_delimiter(self):
        write_csv_file(self.input_file, ['chinese', 'english'],
                       [{'chinese': '东西', 'english': 'thing'}], delimiter='\t')
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin',
             '--delimiter', '\t'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file, delimiter='\t')
        self.assertEqual(fieldnames, ['chinese', 'english', 'pinyin'])
        self.assertEqual(rows[0]['pinyin'], 'dōngxī')

    def test_escaped_tab_delimiter(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '东西'}], delimiter='\t')
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin',
             '--delimiter', '\\t'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file, delimiter='\t')
        self.assertEqual(rows[0]['pinyin'], 'dōngxī')

    def test_encoding_flag_round_trips(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '东西'}],
                       encoding='utf-8-sig')
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin',
             '--encoding', 'utf-8-sig'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file, encoding='utf-8-sig')
        self.assertEqual(fieldnames, ['chinese', 'pinyin'])
        self.assertEqual(rows[0]['pinyin'], 'dōngxī')

    @requires_moedict_pickle
    def test_moedict_variant(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '垃圾分類'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, self.output_file, '--column', 'chinese:pinyin',
             '--variant', 'moedict'])
        self.assertEqual(exit_code, 0)
        fieldnames, rows = read_csv_file(self.output_file)
        self.assertEqual(rows[0]['pinyin'], 'lèsè fēnlèi')

    def test_inplace_leaves_no_temporary_files_behind(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '东西'}])
        exit_code, stdout, stderr = run_cli(
            [self.input_file, '--inplace', '--column', 'chinese:pinyin'])
        self.assertEqual(exit_code, 0)
        self.assertEqual(os.listdir(self.directory.name), ['input.csv'])

    @unittest.skipIf(hasattr(os, 'geteuid') and os.geteuid() == 0,
                     'root ignores directory permissions')
    def test_failed_write_does_not_destroy_the_input_file(self):
        write_csv_file(self.input_file, ['chinese'], [{'chinese': '东西'}])
        original = open(self.input_file, encoding='utf-8').read()
        # a read-only directory makes the temporary file impossible to create
        os.chmod(self.directory.name, 0o500)
        self.addCleanup(os.chmod, self.directory.name, 0o700)
        exit_code, stdout, stderr = run_cli(
            [self.input_file, '--inplace', '--column', 'chinese:pinyin'])
        self.assertEqual(exit_code, 2)
        self.assertEqual(open(self.input_file, encoding='utf-8').read(), original)
        self.assertEqual(os.listdir(self.directory.name), ['input.csv'])
