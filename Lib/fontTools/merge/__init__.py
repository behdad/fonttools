# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Behdad Esfahbod, Roozbeh Pournader

"""Merge multiple fonts into one.

usage: fonttools merge [font1 ... fontN] [--input-file=filelist.txt] [--output-file=merged.ttf] [--import-file=tables.ttx]
                                   [--drop-tables=tags] [--verbose] [--timing]

 font1 ... fontN              Files to merge.
 --input-file=<filename>      Read files to merge from a text file, each path new line. # Comment lines allowed.
 --output-file=<filename>     Specify output file name (default: merged.ttf).
 --import-file=<filename>     TTX file to import after merging. This can be used to set metadata.
 --drop-tables=<table tags>   Comma separated list of table tags to skip, case sensitive.
 --verbose                    Output progress information.
 --timing                     Output progress timing.
 -h, --help                   Show this help message and exit.
"""

from fontTools import ttLib
import fontTools.merge.base
from fontTools.merge.cmap import (
    computeMegaGlyphOrder,
    computeMegaCmap,
    renameCFFCharStrings,
    _flattenDmap,
)
from fontTools.merge.layout import layoutPreMerge, layoutPostMerge
from fontTools.merge.options import Options
from fontTools.ttLib.beyond64k import upper_tables, _compact_layout_tables
import fontTools.merge.tables
from fontTools.misc.loggingTools import Timer
from functools import reduce
import sys
import logging

log = logging.getLogger("fontTools.merge")
timer = Timer(logger=logging.getLogger(__name__ + ".timer"), level=logging.INFO)


_UPPER_TABLES = {"GLYF", "GVAR", "HHEA", "HMTX", "LOCA", "MAXP", "VHEA", "VMTX"}
_COMPANION_TABLES = {
    "glyf",
    "gvar",
    "hhea",
    "hmtx",
    "loca",
    "maxp",
    "vhea",
    "vmtx",
}


def _fontHasUpperTables(font):
    return bool(_UPPER_TABLES.intersection(font.keys())) or any(
        tag in font and font[tag].table.Version >= version
        for tag, version in (
            ("GDEF", 0x00010004),
            ("GSUB", 0x00010002),
            ("GPOS", 0x00010002),
        )
    )


class Merger(object):
    """Font merger.

    This class merges multiple files into a single OpenType font, taking into
    account complexities such as OpenType layout (``GSUB``/``GPOS``) tables and
    cross-font metrics (for example ``hhea.ascent`` is set to the maximum value
    across all the fonts).

    If multiple glyphs map to the same Unicode value, and the glyphs are considered
    sufficiently different (that is, they differ in any of paths, widths, or
    height), then subsequent glyphs are renamed and a lookup in the ``locl``
    feature will be created to disambiguate them. For example, if the arguments
    are an Arabic font and a Latin font and both contain a set of parentheses,
    the Latin glyphs will be renamed to ``parenleft.1`` and ``parenright.1``,
    and a lookup will be inserted into the to ``locl`` feature (creating it if
    necessary) under the ``latn`` script to substitute ``parenleft`` with
    ``parenleft.1`` etc.

    Restrictions:

    - All fonts must have the same units per em.
    - If duplicate glyph disambiguation takes place as described above then the
      fonts must have a ``GSUB`` table.

    Attributes:
            options: Currently unused.
    """

    def __init__(self, options=None):
        if not options:
            options = Options()

        self.options = options

    def _openFonts(self, fontfiles):
        fonts = [ttLib.TTFont(fontfile) for fontfile in fontfiles]
        for font, fontfile in zip(fonts, fontfiles):
            font._merger__fontfile = fontfile
            font._merger__name = font["name"].getDebugName(4)
        return fonts

    def merge(self, fontfiles):
        """Merges fonts together.

        Args:
                fontfiles: A list of file names to be merged

        Returns:
                A :class:`fontTools.ttLib.TTFont` object. Call the ``save`` method on
                this to write it out to an OTF file.

        DMAP overrides are folded into the merged cmap table.
        """
        #
        # Settle on a mega glyph order.
        #
        fonts = self._openFonts(fontfiles)
        glyphOrders = [list(font.getGlyphOrder()) for font in fonts]
        computeMegaGlyphOrder(self, glyphOrders)
        # maxp.numGlyphs is uint16: needs upper tables above 0xFFFF, not 0x10000.
        self.beyond64k = len(self.glyphOrder) > 0xFFFF or any(
            _fontHasUpperTables(font) for font in fonts
        )

        # Take first input file sfntVersion
        sfntVersion = fonts[0].sfntVersion

        # Reload fonts and set new glyph names on them.
        fonts = self._openFonts(fontfiles)
        for font, glyphOrder in zip(fonts, glyphOrders):
            font.setGlyphOrder(glyphOrder)
            if "CFF " in font:
                renameCFFCharStrings(self, glyphOrder, font["CFF "])
            if self.beyond64k:
                upper_tables(font, tables=_COMPANION_TABLES)
            if "DMAP" in font and "DMAP" not in self.options.drop_tables:
                _flattenDmap(font)

        cmaps = [font["cmap"] for font in fonts]
        self.duplicateGlyphsPerFont = [{} for _ in fonts]
        computeMegaCmap(self, cmaps)

        mega = ttLib.TTFont(sfntVersion=sfntVersion)
        mega.setGlyphOrder(self.glyphOrder)

        for font in fonts:
            # Inputs are owned by the merger; normalize without restoring them.
            # The output is upgraded before serialization when needed.
            with _compact_layout_tables(font, restore=False):
                self._preMerge(font)

        self.fonts = fonts

        allTags = reduce(set.union, (list(font.keys()) for font in fonts), set())
        allTags.remove("GlyphOrder")

        for tag in sorted(allTags):
            if tag in self.options.drop_tables:
                continue

            with timer("merge '%s'" % tag):
                tables = [font.get(tag, NotImplemented) for font in fonts]

                log.info("Merging '%s'.", tag)
                clazz = ttLib.getTableClass(tag)
                table = clazz(tag).merge(self, tables)
                # XXX Clean this up and use:  table = mergeObjects(tables)

                if table is not NotImplemented and table is not False:
                    mega[tag] = table
                    log.info("Merged '%s'.", tag)
                else:
                    log.info("Dropped '%s'.", tag)

        del self.duplicateGlyphsPerFont
        del self.fonts

        self._postMerge(mega)
        if self.beyond64k:
            upper_tables(mega)

        return mega

    def mergeObjects(self, returnTable, logic, tables):
        # Right now we don't use self at all.  Will use in the future
        # for options and logging.

        allKeys = set.union(
            set(),
            *(vars(table).keys() for table in tables if table is not NotImplemented),
        )
        for key in allKeys:
            log.info(" %s", key)
            try:
                mergeLogic = logic[key]
            except KeyError:
                try:
                    mergeLogic = logic["*"]
                except KeyError:
                    raise Exception(
                        "Don't know how to merge key %s of class %s"
                        % (key, returnTable.__class__.__name__)
                    )
            if mergeLogic is NotImplemented:
                continue
            value = mergeLogic(getattr(table, key, NotImplemented) for table in tables)
            if value is not NotImplemented:
                setattr(returnTable, key, value)

        return returnTable

    def _preMerge(self, font):
        layoutPreMerge(font)

    def _postMerge(self, font):
        layoutPostMerge(font)
        self._dropPostGlyphNamesIfNeeded(font)

        if "OS/2" in font:
            # https://github.com/fonttools/fonttools/issues/2538
            # TODO: Add an option to disable this?
            font["OS/2"].recalcAvgCharWidth(font)

    def _dropPostGlyphNamesIfNeeded(self, font):
        if "post" not in font or len(font.getGlyphOrder()) <= 0xFFFF:
            return
        post = font["post"]
        if post.formatType == 2.0:
            post.formatType = 3.0
            post.extraNames = []
            post.mapping = {}


__all__ = ["Options", "Merger", "main"]


@timer("make one with everything (TOTAL TIME)")
def main(args=None):
    """Merge multiple fonts into one"""
    from fontTools import configLogger

    if args is None:
        args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0

    options = Options()
    args = options.parse_opts(args)
    fontfiles = []
    if options.input_file:
        with open(options.input_file) as inputfile:
            fontfiles = [
                line.strip()
                for line in inputfile.readlines()
                if not line.lstrip().startswith("#")
            ]
    for g in args:
        fontfiles.append(g)

    if len(fontfiles) < 1:
        print(__doc__, file=sys.stderr)
        return 1

    configLogger(level=logging.INFO if options.verbose else logging.WARNING)
    if options.timing:
        timer.logger.setLevel(logging.DEBUG)
    else:
        timer.logger.disabled = True

    merger = Merger(options=options)
    font = merger.merge(fontfiles)

    if options.import_file:
        font.importXML(options.import_file)

    with timer("compile and save font"):
        font.save(options.output_file)


if __name__ == "__main__":
    sys.exit(main())
