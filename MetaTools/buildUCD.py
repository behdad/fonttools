#!/usr/bin/env python3
"""
Tools to parse data files from the Unicode Character Database.

Running this script regenerates blocks, scripts, script extensions and bidi
mirroring data. Use --ucd-path to read a local UCD directory instead of downloading.
"""

from urllib.request import urlopen
import re
import logging
import os
from os.path import abspath, dirname, join as pjoin, pardir, sep
from typing import List

UNIDATA_URL = "https://unicode.org/Public/UNIDATA/"
UNIDATA_LICENSE_URL = "http://unicode.org/copyright.html#License"

# by default save output files to ../Lib/fontTools/unicodedata/
UNIDATA_PATH = (
    pjoin(abspath(dirname(__file__)), pardir, "Lib", "fontTools", "unicodedata") + sep
)

SRC_ENCODING = "# -*- coding: utf-8 -*-\n"

NOTICE = "# NOTE: This file was auto-generated with MetaTools/buildUCD.py.\n"

MAX_UNICODE = 0x10FFFF

log = logging.getLogger()


def read_unidata_file(filename, local_ucd_path=None) -> List[str]:
    """Read a UCD file from https://unicode.org or optionally from a local directory.

    Return the list of lines.
    """
    if local_ucd_path is not None:
        with open(pjoin(local_ucd_path, filename), "r", encoding="utf-8-sig") as f:
            return f.readlines()
    else:
        url = UNIDATA_URL + filename
        with urlopen(url) as response:
            return response.read().decode("utf-8").splitlines(keepends=True)


def parse_unidata_header(file_lines: List[str]):
    """Read the top header of data files, until the first line
    that does not start with '#'.
    """
    header = []
    for line in file_lines:
        if line.startswith("#"):
            header.append(line)
        else:
            break
    return "".join(header)


def parse_range_properties(infile: List[str], default=None, is_set=False):
    """Parse a Unicode data file containing a column with one character or
    a range of characters, and another column containing a property value
    separated by a semicolon. Comments after '#' are ignored.

    If the ranges defined in the data file are not continuous, assign the
    'default' property to the unassigned codepoints.

    Return a list of (start, end, property_name) tuples.
    """
    ranges = []
    line_regex = re.compile(
        r"^"
        r"([0-9A-F]{4,6})"  # first character code
        r"(?:\.\.([0-9A-F]{4,6}))?"  # optional second character code
        r"\s*;\s*"
        r"([^#]+)"
    )  # everything up to the potential comment
    for line in infile:
        match = line_regex.match(line)
        if not match:
            continue

        first, last, data = match.groups()
        if last is None:
            last = first

        first = int(first, 16)
        last = int(last, 16)
        data = str(data.rstrip())

        ranges.append((first, last, data))

    ranges.sort()

    # fill the gaps between explicitly defined ranges
    last_start, last_end = -1, -1
    full_ranges = []
    for start, end, value in ranges:
        assert last_end < start
        assert start <= end
        if start - last_end > 1:
            full_ranges.append((last_end + 1, start - 1, default))
        if is_set:
            value = set(value.split())
        full_ranges.append((start, end, value))
        last_start, last_end = start, end
    if last_end != MAX_UNICODE:
        full_ranges.append((last_end + 1, MAX_UNICODE, default))

    # reduce total number of ranges by combining continuous ones
    last_start, last_end, last_value = full_ranges.pop(0)
    merged_ranges = []
    for start, end, value in full_ranges:
        if value == last_value:
            continue
        else:
            merged_ranges.append((last_start, start - 1, last_value))
            last_start, line_end, last_value = start, end, value
    merged_ranges.append((last_start, MAX_UNICODE, last_value))

    # make sure that the ranges cover the full unicode repertoire
    assert merged_ranges[0][0] == 0
    for (cs, ce, cv), (ns, ne, nv) in zip(merged_ranges, merged_ranges[1:]):
        assert ce + 1 == ns
    assert merged_ranges[-1][1] == MAX_UNICODE

    return merged_ranges


def parse_semicolon_separated_data(infile):
    """Parse a Unicode data file where each line contains a lists of values
    separated by a semicolon (e.g. "PropertyValueAliases.txt").
    The number of the values on different lines may be different.

    Returns a list of lists each containing the values as strings.
    """
    data = []
    for line in infile:
        line = line.split("#", 1)[0].strip()  # remove the comment
        if not line:
            continue
        fields = [str(field.strip()) for field in line.split(";")]
        data.append(fields)
    return data


def _set_repr(value):
    return (
        "None"
        if value is None
        else "{{{}}}".format(", ".join(repr(v) for v in sorted(value)))
    )


def build_ranges(
    filename, local_ucd=None, output_path=None, default=None, is_set=False, aliases=None
):
    """Fetch 'filename' UCD data file from Unicode official website, parse
    the property ranges and values and write them as two Python lists
    to 'fontTools.unicodedata.<filename>.py'.

    'aliases' is an optional mapping of property codes (short names) to long
    name aliases (list of strings, with the first item being the preferred
    alias). When this is provided, the property values are written using the
    short notation, and an additional 'NAMES' dict with the aliases is
    written to the output module.

    To load the data file from a local directory, you can use the
    'local_ucd' argument.
    """
    modname = os.path.splitext(filename)[0] + ".py"
    if not output_path:
        output_path = UNIDATA_PATH + modname

    if local_ucd:
        log.info("loading '%s' from local directory '%s'", filename, local_ucd)
    else:
        log.info("downloading '%s' from '%s'", filename, UNIDATA_URL)

    file_lines = read_unidata_file(filename, local_ucd)
    header = parse_unidata_header(file_lines)
    ranges = parse_range_properties(file_lines, default=default, is_set=is_set)

    if aliases:
        reversed_aliases = {normalize(v[0]): k for k, v in aliases.items()}
        max_value_length = 6  # 4-letter tags plus two quotes for repr
    else:
        max_value_length = min(56, max(len(repr(v)) for _, _, v in ranges))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(SRC_ENCODING)
        f.write("#\n")
        f.write(NOTICE)
        f.write("# Source: {}{}\n".format(UNIDATA_URL, filename))
        f.write("# License: {}\n".format(UNIDATA_LICENSE_URL))
        f.write("#\n")
        f.write(header + "\n")

        f.write("RANGES = [\n")
        for first, last, value in ranges:
            f.write(
                "    0x{:0>4X},  # .. 0x{:0>4X} ; {}\n".format(
                    first, last, _set_repr(value) if is_set else value
                )
            )
        f.write("]\n")

        f.write("\n")
        f.write("VALUES = [\n")
        for first, last, value in ranges:
            comment = "# {:0>4X}..{:0>4X}".format(first, last)
            if is_set:
                value_repr = "{},".format(_set_repr(value))
            else:
                if aliases:
                    # append long name to comment and use the short code
                    comment += " ; {}".format(value)
                    value = reversed_aliases[normalize(value)]
                value_repr = "{!r},".format(value)
            f.write(
                "    {}  {}\n".format(value_repr.ljust(max_value_length + 1), comment)
            )
        f.write("]\n")

        if aliases:
            f.write("\n")
            f.write("NAMES = {\n")
            for value, names in sorted(aliases.items()):
                # we only write the first preferred alias
                f.write("    {!r}: {!r},\n".format(value, names[0]))
            f.write("}\n")

    log.info("saved new file: '%s'", os.path.normpath(output_path))


def build_mirrored(local_ucd=None, output_path=None):
    """Build the MIRRORED mapping from the Unicode BidiMirroring.txt data."""
    filename = "BidiMirroring.txt"
    if not output_path:
        output_path = UNIDATA_PATH + "Mirrored.py"

    if local_ucd:
        log.info("loading '%s' from local directory '%s'", filename, local_ucd)
    else:
        log.info("downloading '%s' from '%s'", filename, UNIDATA_URL)

    file_lines = read_unidata_file(filename, local_ucd)
    header = parse_unidata_header(file_lines)
    data = parse_semicolon_separated_data(file_lines)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(SRC_ENCODING)
        f.write("#\n")
        f.write(NOTICE)
        f.write("# Source: {}{}\n".format(UNIDATA_URL, filename))
        f.write("# License: {}\n".format(UNIDATA_LICENSE_URL))
        f.write("#\n")
        f.write(header + "\n")
        f.write("MIRRORED = {\n")
        for code, mirrored in data:
            f.write(
                "    0x{:04X}: 0x{:04X},\n".format(int(code, 16), int(mirrored, 16))
            )
        f.write("}\n")

    log.info("saved new file: '%s'", os.path.normpath(output_path))


_normalize_re = re.compile(r"[-_ ]+")


def normalize(string):
    """Remove case, strip space, '-' and '_' for loose matching."""
    return _normalize_re.sub("", string).lower()


def parse_property_value_aliases(property_tag, local_ucd=None):
    """Fetch the current 'PropertyValueAliases.txt' from the Unicode website,
    parse the values for the specified 'property_tag' and return a dictionary
    of name aliases (list of strings) keyed by short value codes (strings).

    To load the data file from a local directory, you can use the
    'local_ucd' argument.
    """
    filename = "PropertyValueAliases.txt"
    if local_ucd:
        log.info("loading '%s' from local directory '%s'", filename, local_ucd)
    else:
        log.info("downloading '%s' from '%s'", filename, UNIDATA_URL)

    file_lines = read_unidata_file(filename, local_ucd)
    header = parse_unidata_header(file_lines)
    data = parse_semicolon_separated_data(file_lines)

    aliases = {item[1]: item[2:] for item in data if item[0] == property_tag}

    return aliases


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate fontTools.unicodedata from UCD data files"
    )
    parser.add_argument(
        "--ucd-path", help="Path to local folder containing UCD data files"
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    options = parser.parse_args()

    level = "WARNING" if options.quiet else "INFO"
    logging.basicConfig(level=level, format="%(message)s")

    build_ranges("Blocks.txt", local_ucd=options.ucd_path, default="No_Block")

    script_aliases = parse_property_value_aliases("sc", options.ucd_path)
    build_ranges(
        "Scripts.txt",
        local_ucd=options.ucd_path,
        default="Unknown",
        aliases=script_aliases,
    )
    build_ranges("ScriptExtensions.txt", local_ucd=options.ucd_path, is_set=True)
    build_mirrored(local_ucd=options.ucd_path)


if __name__ == "__main__":
    import sys

    sys.exit(main())
