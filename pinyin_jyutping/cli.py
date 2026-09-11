import argparse
import csv
import os
import sys
import tempfile

from . import constants

MODE_PINYIN = 'pinyin'
MODE_JYUTPING = 'jyutping'


def parse_delimiter(value):
    # a literal backslash-t is easier to type than a tab in most shells
    if value == '\\t':
        return '\t'
    if len(value) != 1:
        raise argparse.ArgumentTypeError(
            f"delimiter must be a single character, got '{value}'")
    return value


def parse_column_spec(value):
    parts = value.split(':')
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise argparse.ArgumentTypeError(
            f"expected INPUT_COLUMN:OUTPUT_COLUMN, got '{value}'")
    return parts[0], parts[1]


def convert_rows(fieldnames, rows, pairs, convert, warn=None):
    output_fieldnames = list(fieldnames)
    for input_column, output_column in pairs:
        if output_column not in output_fieldnames:
            output_fieldnames.append(output_column)
    # row 1 of the file is the header, so the first data row is row 2
    for row_number, row in enumerate(rows, start=2):
        for input_column, output_column in pairs:
            text = row.get(input_column) or ''
            if not text.strip():
                row[output_column] = ''
                continue
            try:
                row[output_column] = convert(text)
            except Exception as e:
                row[output_column] = ''
                if warn != None:
                    warn(f"row {row_number}, column '{input_column}': "
                         f"could not convert '{text}': {e}")
    return output_fieldnames, rows


def read_csv(filename, delimiter, encoding):
    """returns (fieldnames, rows), raising OSError/UnicodeDecodeError on bad input"""
    with open(filename, 'r', newline='', encoding=encoding) as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)
        return reader.fieldnames, rows


def write_csv(filename, fieldnames, rows, delimiter, encoding):
    """write atomically, so an interrupted run cannot truncate an existing file"""
    directory = os.path.dirname(os.path.abspath(filename))
    handle, temp_filename = tempfile.mkstemp(dir=directory, suffix='.csv')
    os.close(handle)
    try:
        with open(temp_filename, 'w', newline='', encoding=encoding) as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_filename, filename)
    except BaseException:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        raise


def build_converter(mode, variant, tone_numbers, spaces):
    # imported here so that --help and argument errors don't pay for loading
    # the pickled dictionaries
    from . import PinyinJyutping
    instance = PinyinJyutping(variant=variant)
    if mode == MODE_JYUTPING:
        return lambda text: instance.jyutping(
            text, tone_numbers=tone_numbers, spaces=spaces)
    return lambda text: instance.pinyin(
        text, tone_numbers=tone_numbers, spaces=spaces)


def build_parser():
    parser = argparse.ArgumentParser(
        prog='pinyin-jyutping',
        description='Convert Chinese columns of a CSV file to Pinyin or Jyutping.')
    parser.add_argument('input_file',
                        help='CSV file to read, must have a header row')
    parser.add_argument('output_file', nargs='?',
                        help='CSV file to write, omit when using --inplace')
    parser.add_argument('--column', dest='columns', action='append',
                        type=parse_column_spec, required=True,
                        metavar='HANZI:OUTPUT',
                        help='column pair to convert, repeatable. the output column '
                             'is overwritten if it already exists, appended otherwise')
    parser.add_argument('--mode', choices=[MODE_PINYIN, MODE_JYUTPING],
                        default=MODE_PINYIN,
                        help='conversion to apply to every column pair (default: pinyin)')
    parser.add_argument('--inplace', action='store_true',
                        help='write the result back to the input file')
    parser.add_argument('--variant', choices=sorted(constants.PICKLE_FILENAME_MAP.keys()),
                        default=constants.VARIANT_CEDICT,
                        help='pinyin dictionary to use (default: cedict)')
    parser.add_argument('--tone-numbers', action='store_true',
                        help='output tone numbers instead of diacritics')
    parser.add_argument('--spaces', action='store_true',
                        help='put a space between every syllable')
    parser.add_argument('--delimiter', default=',', type=parse_delimiter,
                        help="CSV field delimiter, accepts \\t for tab (default: ',')")
    parser.add_argument('--encoding', default='utf-8',
                        help='CSV file encoding (default: utf-8)')
    return parser


def validate_arguments(parser, args):
    if args.inplace and args.output_file != None:
        parser.error('--inplace cannot be combined with an output file, '
                     'pass one or the other')
    if not args.inplace and args.output_file == None:
        parser.error('an output file is required, or pass --inplace to overwrite '
                     'the input file')
    if args.mode == MODE_JYUTPING and args.variant != constants.VARIANT_CEDICT:
        parser.error(f'--mode jyutping is not available for the {args.variant} '
                     f'variant, which only holds pinyin data')
    seen_output_columns = set()
    for input_column, output_column in args.columns:
        if output_column in seen_output_columns:
            parser.error(f"output column '{output_column}' is named by more than "
                         f"one --column")
        seen_output_columns.add(output_column)


def validate_columns(parser, fieldnames, pairs):
    if fieldnames == None:
        parser.error('input file has no header row')
    for input_column, output_column in pairs:
        if input_column not in fieldnames:
            parser.error(f"input column '{input_column}' is not in the input file, "
                         f"available columns: {', '.join(fieldnames)}")


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_arguments(parser, args)

    try:
        fieldnames, rows = read_csv(args.input_file, args.delimiter, args.encoding)
    except (OSError, UnicodeDecodeError) as e:
        parser.error(f'cannot read {args.input_file}: {e}')
    validate_columns(parser, fieldnames, args.columns)

    convert = build_converter(args.mode, args.variant, args.tone_numbers, args.spaces)
    output_fieldnames, output_rows = convert_rows(
        fieldnames, rows, args.columns, convert,
        warn=lambda message: print(f'warning: {message}', file=sys.stderr))

    output_file = args.input_file if args.inplace else args.output_file
    try:
        write_csv(output_file, output_fieldnames, output_rows,
                  args.delimiter, args.encoding)
    except (OSError, UnicodeEncodeError) as e:
        parser.error(f'cannot write {output_file}: {e}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
