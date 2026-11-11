import io
import itertools
from fontTools import ttLib
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.beyond64k import upper_tables
from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.merge import Merger, main as merge_main
from fontTools.otlLib.builder import buildMathTable
import difflib
import os
import re
import shutil
import sys
import tempfile
import unittest
import pathlib
import pytest


class MergeIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = None
        self.num_tempfiles = 0

    def tearDown(self):
        if self.tempdir:
            shutil.rmtree(self.tempdir)

    @staticmethod
    def getpath(testfile):
        path, _ = os.path.split(__file__)
        return os.path.join(path, "data", testfile)

    def temp_path(self, suffix):
        if not self.tempdir:
            self.tempdir = tempfile.mkdtemp()
        self.num_tempfiles += 1
        return os.path.join(self.tempdir, "tmp%d%s" % (self.num_tempfiles, suffix))

    IGNORED_LINES_RE = re.compile(
        "^(<ttFont |    <(checkSumAdjustment|created|modified) ).*"
    )

    def read_ttx(self, path):
        lines = []
        with open(path, "r", encoding="utf-8") as ttx:
            for line in ttx.readlines():
                # Elide lines with data that often change.
                if self.IGNORED_LINES_RE.match(line):
                    lines.append("\n")
                else:
                    lines.append(line.rstrip() + "\n")
        return lines

    def expect_ttx(self, font, expected_ttx, tables=None):
        path = self.temp_path(suffix=".ttx")
        font.saveXML(path, tables=tables)
        actual = self.read_ttx(path)
        expected = self.read_ttx(expected_ttx)
        if actual != expected:
            for line in difflib.unified_diff(
                expected, actual, fromfile=expected_ttx, tofile=path
            ):
                sys.stdout.write(line)
            self.fail("TTX output is different from expected")

    def compile_font(self, path, suffix):
        savepath = self.temp_path(suffix=suffix)
        font = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False)
        font.importXML(path)
        font.save(savepath, reorderTables=None)
        return font, savepath

    # -----
    # Tests
    # -----

    def test_merge_cff(self):
        _, fontpath1 = self.compile_font(self.getpath("CFFFont1.ttx"), ".otf")
        _, fontpath2 = self.compile_font(self.getpath("CFFFont2.ttx"), ".otf")
        mergedpath = self.temp_path(".otf")
        merge_main([fontpath1, fontpath2, "--output-file=%s" % mergedpath])
        mergedfont = ttLib.TTFont(mergedpath)
        self.expect_ttx(mergedfont, self.getpath("CFFFont_expected.ttx"))

    def test_merge_cff_objects(self):
        fonts = []
        for name in ("CFFFont1.ttx", "CFFFont2.ttx"):
            font = ttLib.TTFont(recalcBBoxes=False, recalcTimestamp=False)
            font.importXML(self.getpath(name))
            fonts.append(font)
        merged = _merge_and_recompile(fonts)
        self.expect_ttx(merged, self.getpath("CFFFont_expected.ttx"))


class gaspMergeUnitTest(unittest.TestCase):
    def setUp(self):
        self.merger = Merger()

        self.table1 = ttLib.newTable("gasp")
        self.table1.version = 1
        self.table1.gaspRange = {
            0x8: 0xA,
            0x10: 0x5,
        }

        self.table2 = ttLib.newTable("gasp")
        self.table2.version = 1
        self.table2.gaspRange = {
            0x6: 0xB,
            0xFF: 0x4,
        }

        self.result = ttLib.newTable("gasp")

    def test_gasp_merge_basic(self):
        result = self.result.merge(self.merger, [self.table1, self.table2])
        self.assertEqual(result, self.table1)

        result = self.result.merge(self.merger, [self.table2, self.table1])
        self.assertEqual(result, self.table2)

    def test_gasp_merge_notImplemented(self):
        result = self.result.merge(self.merger, [NotImplemented, self.table1])
        self.assertEqual(result, NotImplemented)

        result = self.result.merge(self.merger, [self.table1, NotImplemented])
        self.assertEqual(result, self.table1)


class CmapMergeUnitTest(unittest.TestCase):
    def setUp(self):
        self.merger = Merger()
        self.table1 = ttLib.newTable("cmap")
        self.table2 = ttLib.newTable("cmap")
        self.mergedTable = ttLib.newTable("cmap")
        pass

    def tearDown(self):
        pass

    def makeSubtable(self, format, platformID, platEncID, cmap):
        module = ttLib.getTableModule("cmap")
        subtable = module.cmap_classes[format](format)
        subtable.platformID, subtable.platEncID, subtable.language, subtable.cmap = (
            platformID,
            platEncID,
            0,
            cmap,
        )
        return subtable

    def makeUvsSubtable(self, format, platformID, platEncID, uvsDict):
        subtable = self.makeSubtable(format, platformID, platEncID, {})
        subtable.uvsDict = uvsDict
        return subtable

    # 4-3-1 table merged with 12-3-10 table with no dupes with codepoints outside BMP
    def test_cmap_merge_no_dupes(self):
        table1 = self.table1
        table2 = self.table2
        mergedTable = self.mergedTable

        cmap1 = {0x2603: "SNOWMAN"}
        table1.tables = [self.makeSubtable(4, 3, 1, cmap1)]

        cmap2 = {0x26C4: "SNOWMAN WITHOUT SNOW"}
        cmap2Extended = {0x1F93C: "WRESTLERS"}
        cmap2Extended.update(cmap2)
        table2.tables = [
            self.makeSubtable(4, 3, 1, cmap2),
            self.makeSubtable(12, 3, 10, cmap2Extended),
        ]

        self.merger.alternateGlyphsPerFont = [{}, {}]
        mergedTable.merge(self.merger, [table1, table2])

        expectedCmap = cmap2.copy()
        expectedCmap.update(cmap1)
        expectedCmapExtended = cmap2Extended.copy()
        expectedCmapExtended.update(cmap1)
        self.assertEqual(mergedTable.numSubTables, 2)
        self.assertEqual(
            [
                (table.format, table.platformID, table.platEncID, table.language)
                for table in mergedTable.tables
            ],
            [(4, 3, 1, 0), (12, 3, 10, 0)],
        )
        self.assertEqual(mergedTable.tables[0].cmap, expectedCmap)
        self.assertEqual(mergedTable.tables[1].cmap, expectedCmapExtended)

    # Tests Issue #322
    def test_cmap_merge_three_dupes(self):
        table1 = self.table1
        table2 = self.table2
        mergedTable = self.mergedTable

        cmap1 = {0x20: "space#0", 0xA0: "space#0"}
        table1.tables = [self.makeSubtable(4, 3, 1, cmap1)]
        cmap2 = {0x20: "space#1", 0xA0: "uni00A0#1"}
        table2.tables = [self.makeSubtable(4, 3, 1, cmap2)]

        self.merger.duplicateGlyphsPerFont = [{}, {}]
        mergedTable.merge(self.merger, [table1, table2])

        expectedCmap = cmap1.copy()
        self.assertEqual(mergedTable.numSubTables, 1)
        table = mergedTable.tables[0]
        self.assertEqual(
            (table.format, table.platformID, table.platEncID, table.language),
            (4, 3, 1, 0),
        )
        self.assertEqual(table.cmap, expectedCmap)
        self.assertEqual(
            self.merger.duplicateGlyphsPerFont, [{}, {"space#0": "space#1"}]
        )

    def test_cmap_merge_format_14(self):
        table1 = self.table1
        table2 = self.table2
        mergedTable = self.mergedTable

        cmap1 = {0x3404: "uni3404"}
        uvsDict1 = {0xFE00: [(0x0030, "uni0030.FE00")], 0xE0101: [(0x3404, "uni3404")]}
        table1.tables = [
            self.makeUvsSubtable(14, 0, 5, uvsDict1),
            self.makeSubtable(4, 3, 1, cmap1),
        ]
        uvsDict2 = {0xFE00: [(0x20122, "u2F803")], 0xE0102: [(0x34FF, "uni34FF.var2")]}
        table2.tables = [self.makeUvsSubtable(14, 0, 5, uvsDict2)]

        self.merger.duplicateGlyphsPerFont = [{}, {}]
        mergedTable.merge(self.merger, [table1, table2])

        self.assertEqual(mergedTable.numSubTables, 2)
        uvsTable, cmapTable = mergedTable.tables

        self.assertEqual(
            (
                uvsTable.format,
                uvsTable.platformID,
                uvsTable.platEncID,
                uvsTable.language,
            ),
            (14, 0, 5, 0),
        )
        self.assertEqual(
            (
                cmapTable.format,
                cmapTable.platformID,
                cmapTable.platEncID,
                cmapTable.language,
            ),
            (4, 3, 1, 0),
        )

        expectedUvsDict = {
            0xFE00: [(0x0030, "uni0030.FE00"), (0x20122, "u2F803")],
            0xE0101: [(0x3404, None)],
            0xE0102: [(0x34FF, "uni34FF.var2")],
        }
        self.assertEqual(uvsTable.uvsDict, expectedUvsDict)

    def test_cmap_merge_format_14_dupes(self):
        table1 = self.table1
        table2 = self.table2
        mergedTable = self.mergedTable

        cmap1 = {0x2F803: "u2F803#0"}
        uvsDict1 = {0xFE00: [(0x20122, "u2F803#0")], 0xE0101: [(0x3404, "uni3404")]}
        table1.tables = [
            self.makeUvsSubtable(14, 0, 5, uvsDict1),
            self.makeSubtable(12, 3, 10, cmap1),
        ]
        cmap2 = {0x2F803: "u2F803#1"}
        uvsDict2 = {
            0xFE00: [(0x20122, "u2F803#1")],
            0xE0102: [(0x34FF, "uni34FF.var2")],
        }
        table2.tables = [
            self.makeUvsSubtable(14, 0, 5, uvsDict2),
            self.makeSubtable(12, 3, 10, cmap2),
        ]

        self.merger.duplicateGlyphsPerFont = [{}, {}]
        mergedTable.merge(self.merger, [table1, table2])

        self.assertEqual(mergedTable.numSubTables, 3)
        uvsTable, cmap_4_3_1_Table, cmap_12_3_10_Table = mergedTable.tables

        self.assertEqual(
            (
                uvsTable.format,
                uvsTable.platformID,
                uvsTable.platEncID,
                uvsTable.language,
            ),
            (14, 0, 5, 0),
        )
        self.assertEqual(
            (
                cmap_4_3_1_Table.format,
                cmap_4_3_1_Table.platformID,
                cmap_4_3_1_Table.platEncID,
                cmap_4_3_1_Table.language,
            ),
            (4, 3, 1, 0),
        )
        self.assertEqual(
            (
                cmap_12_3_10_Table.format,
                cmap_12_3_10_Table.platformID,
                cmap_12_3_10_Table.platEncID,
                cmap_12_3_10_Table.language,
            ),
            (12, 3, 10, 0),
        )

        expectedUvsDict = {
            0xFE00: [(0x20122, "u2F803#0")],
            0xE0101: [(0x3404, "uni3404")],
            0xE0102: [(0x34FF, "uni34FF.var2")],
        }
        self.assertEqual(uvsTable.uvsDict, expectedUvsDict)
        self.assertEqual(
            self.merger.duplicateGlyphsPerFont, [{}, {"u2F803#0": "u2F803#1"}]
        )


def _compile(ttFont):
    buf = io.BytesIO()
    ttFont.save(buf)
    buf.seek(0)
    return buf


def _make_fontfile_with_OS2(*, version, **kwargs):
    upem = 1000
    glyphOrder = [".notdef", "a"]
    cmap = {0x61: "a"}
    glyphs = {gn: Glyph() for gn in glyphOrder}
    hmtx = {gn: (500, 0) for gn in glyphOrder}
    names = {"familyName": "TestOS2", "styleName": "Regular"}

    fb = FontBuilder(unitsPerEm=upem)
    fb.setupGlyphOrder(glyphOrder)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(hmtx)
    fb.setupHorizontalHeader()
    fb.setupNameTable(names)
    fb.setupOS2(version=version, **kwargs)

    return _compile(fb.font)


def _make_fontfile_with_glyphs(first_gid, glyph_count, *, add_layout=False):
    upem = 1000
    glyphOrder = [".notdef"] + [
        f"glyph{gid:05d}" for gid in range(first_gid, first_gid + glyph_count - 1)
    ]
    cmap = {
        first_gid + codepoint: glyphName
        for codepoint, glyphName in enumerate(glyphOrder[1:])
    }
    glyphs = {gn: Glyph() for gn in glyphOrder}
    hmtx = {gn: (500, 0) for gn in glyphOrder}
    names = {"familyName": "TestMerge", "styleName": "Regular"}

    fb = FontBuilder(unitsPerEm=upem)
    fb.setupGlyphOrder(glyphOrder)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(hmtx)
    fb.setupHorizontalHeader()
    fb.setupNameTable(names)
    fb.setupOS2()
    if add_layout:
        glyph1, glyph2 = glyphOrder[1:3]
        addOpenTypeFeaturesFromString(
            fb.font,
            f"feature salt {{ sub {glyph1} by {glyph2}; }} salt;",
        )

    return _compile(fb.font)


def _upper_fontfile(fontfile):
    font = ttLib.TTFont(fontfile)
    upper_tables(font)
    return _compile(font)


def _merge_and_recompile(fontfiles, options=None):
    merger = Merger(options)
    merged = merger.merge(fontfiles)
    buf = _compile(merged)
    return ttLib.TTFont(buf)


@pytest.mark.parametrize("first_in_memory", [False, True])
def test_merge_ttfont_inputs(first_in_memory, tmp_path):
    first = ttLib.TTFont(_make_fontfile_with_glyphs(0xE000, 2))
    second = ttLib.TTFont(_make_fontfile_with_glyphs(0xE000, 2))
    first.ensureDecompiled()
    FontBuilder(font=first).setupPost()
    second.ensureDecompiled()
    FontBuilder(font=second).setupPost()
    glyph_name = second.getBestCmap()[0xE000]
    for subtable in second["cmap"].tables:
        if subtable.isUnicode():
            subtable.cmap = {0xE001: glyph_name}
    second["hmtx"].metrics[glyph_name] = (777, 11)

    if not first_in_memory:
        first_path = tmp_path / "first.ttf"
        first.save(first_path)
        first = first_path
    merged = _merge_and_recompile([first, second])
    cmap = merged.getBestCmap()
    assert set(cmap) == {0xE000, 0xE001}
    assert cmap[0xE000] != cmap[0xE001]
    assert merged["hmtx"].metrics[cmap[0xE000]] == (500, 0)
    assert merged["hmtx"].metrics[cmap[0xE001]] == (777, 11)


@pytest.mark.parametrize("first_format", [14, 15])
@pytest.mark.parametrize("second_format", [14, 15])
@pytest.mark.parametrize("high_glyph_ids", [False, True])
def test_merge_extended_uvs(first_format, second_format, high_glyph_ids):
    fontfiles = []
    count = 0x8001 if high_glyph_ids else 4
    for index, format in enumerate((first_format, second_format)):
        font = ttLib.TTFont(_make_fontfile_with_glyphs(0x10000 * (index + 1), count))
        glyphOrder = font.getGlyphOrder()
        uvs = ttLib.getTableModule("cmap").CmapSubtable.newSubtable(format)
        uvs.platformID = 0
        uvs.platEncID = 5
        uvs.language = 0
        uvs.cmap = {}
        uvs.uvsDict = {
            0xFE00: [(0x10000 * (index + 1), glyphOrder[-1])],
            0xE0100 + index: [(0x10000 * (index + 1) + 1, None)],
        }
        font["cmap"].tables.append(uvs)
        fontfiles.append(_compile(font))

    merger = Merger()
    merged = merger.merge(fontfiles)
    assert merged["cmap"].tables[0].format == (15 if high_glyph_ids else 14)
    expected = {
        0xFE00: [
            (0x10000, merger.glyphOrder[count - 1]),
            (0x20000, merger.glyphOrder[-1]),
        ],
        0xE0100: [(0x10001, None)],
        0xE0101: [(0x20001, None)],
    }
    assert merged["cmap"].tables[0].uvsDict == expected
    roundtripped = ttLib.TTFont(_compile(merged))
    actual = roundtripped["cmap"].tables[0].uvsDict
    for selector, mappings in expected.items():
        assert [codepoint for codepoint, _ in actual[selector]] == [
            codepoint for codepoint, _ in mappings
        ]
        for (_, actualGlyph), (_, expectedGlyph) in zip(actual[selector], mappings):
            if expectedGlyph is None:
                assert actualGlyph is None
            else:
                assert roundtripped.getGlyphID(actualGlyph) == merged.getGlyphID(
                    expectedGlyph
                )


@pytest.mark.parametrize("reverse_order", [False, True])
def test_merge_prefers_format15_uvs(reverse_order):
    font = ttLib.TTFont(_make_fontfile_with_glyphs(0x10000, 4))
    glyphOrder = font.getGlyphOrder()
    subtables = []
    for format, glyph in ((14, glyphOrder[2]), (15, glyphOrder[3])):
        uvs = ttLib.getTableModule("cmap").CmapSubtable.newSubtable(format)
        uvs.platformID = 0
        uvs.platEncID = 5
        uvs.language = 0
        uvs.cmap = {}
        uvs.uvsDict = {0xFE00: [(0x10000, glyph)]}
        subtables.append(uvs)
    font["cmap"].tables.extend(reversed(subtables) if reverse_order else subtables)

    merger = Merger()
    merger.glyphOrder = glyphOrder
    merger.duplicateGlyphsPerFont = [{}]
    merged = ttLib.newTable("cmap").merge(merger, [font["cmap"]])
    assert merged.tables[0].uvsDict == {0xFE00: [(0x10000, glyphOrder[3])]}


@pytest.mark.parametrize("uvs_format", [14, 15])
@pytest.mark.parametrize("dmap_uvs", ["default", "nondefault", "zero"])
@pytest.mark.parametrize("dmap_only", [False, True])
@pytest.mark.parametrize("high_glyph_ids", [False, True])
def test_merge_dmap(uvs_format, dmap_uvs, dmap_only, high_glyph_ids):
    font = ttLib.TTFont(_make_fontfile_with_glyphs(0x10000, 4))
    glyphOrder = font.getGlyphOrder()
    module = ttLib.getTableModule("cmap")
    nominal = module.CmapSubtable.newSubtable(12)
    nominal.platformID = 3
    nominal.platEncID = 10
    nominal.language = 0
    nominal.cmap = {
        0x10000: glyphOrder[2],
        0x10001: glyphOrder[0],
        0x30000: glyphOrder[3],
    }
    base_uvs = module.CmapSubtable.newSubtable(uvs_format)
    base_uvs.platformID = 0
    base_uvs.platEncID = 5
    base_uvs.language = 0
    base_uvs.cmap = {}
    base_uvs.uvsDict = {
        0xFE00: [(0x10000, glyphOrder[3]), (0x10001, None)],
        0xE0100: [(0x10000, None)],
    }
    font["cmap"].tables.append(base_uvs)
    delta_uvs = module.CmapSubtable.newSubtable(uvs_format)
    delta_uvs.platformID = 0
    delta_uvs.platEncID = 5
    delta_uvs.language = 0
    delta_uvs.cmap = {}
    delta_uvs.uvsDict = {
        0xFE00: [
            (
                0x10000,
                {"default": None, "nondefault": glyphOrder[1], "zero": glyphOrder[0]}[
                    dmap_uvs
                ],
            ),
            (0x30000, glyphOrder[2]),
        ]
    }
    font["DMAP"] = ttLib.newTable("DMAP")
    font["DMAP"].tableVersion = 0
    font["DMAP"].tables = [delta_uvs, nominal]
    if dmap_only:
        del font["cmap"]

    second = _make_fontfile_with_glyphs(0x20000, 0xFFFF if high_glyph_ids else 4)
    first = _compile(font)
    merged = _merge_and_recompile(
        [second, first] if high_glyph_ids else [first, second]
    )
    glyph_offset = 0xFFFF if high_glyph_ids else 0
    assert "DMAP" not in merged
    cmap = merged.getBestCmap()
    assert merged.getGlyphID(cmap[0x10000]) == glyph_offset + 2
    assert merged.getGlyphID(cmap[0x30000]) == glyph_offset + 3
    assert merged.getGlyphID(cmap[0x20000]) == (1 if high_glyph_ids else 5)
    if dmap_only:
        assert 0x10001 not in cmap
    else:
        assert merged.getGlyphID(cmap[0x10001]) == glyph_offset + 2
    assert merged["cmap"].tables[0].format == (15 if high_glyph_ids else 14)
    uvs = {
        selector: dict(entries)
        for selector, entries in merged["cmap"].tables[0].uvsDict.items()
    }
    expected = {"default": None, "nondefault": 1, "zero": None if dmap_only else 3}[
        dmap_uvs
    ]
    if dmap_uvs == "zero" and dmap_only:
        assert 0x10000 not in uvs[0xFE00]
    elif expected is None:
        assert uvs[0xFE00][0x10000] is None
    else:
        assert merged.getGlyphID(uvs[0xFE00][0x10000]) == glyph_offset + expected
    assert merged.getGlyphID(uvs[0xFE00][0x30000]) == glyph_offset + 2
    if not dmap_only:
        assert uvs[0xFE00][0x10001] is None
        assert uvs[0xE0100][0x10000] is None


def test_merge_dmap_respects_drop_tables():
    font = ttLib.TTFont(_make_fontfile_with_glyphs(0x10000, 4))
    dmap = ttLib.newTable("DMAP")
    dmap.tableVersion = 0
    subtable = ttLib.getTableModule("cmap").CmapSubtable.newSubtable(12)
    subtable.platformID, subtable.platEncID, subtable.language = 3, 10, 0
    subtable.cmap = {0x10000: font.getGlyphOrder()[2]}
    dmap.tables = [subtable]
    font["DMAP"] = dmap
    options = Merger().options
    options.drop_tables = ["DMAP"]
    merged = _merge_and_recompile([_compile(font)], options)
    assert "DMAP" not in merged
    assert merged.getGlyphID(merged.getBestCmap()[0x10000]) == 1


@pytest.mark.parametrize("uvs_format", [14, 15])
def test_merge_dmap_uvs_only(uvs_format):
    font = ttLib.TTFont(_make_fontfile_with_glyphs(0x10000, 4))
    dmap = ttLib.newTable("DMAP")
    dmap.tableVersion = 0
    uvs = ttLib.getTableModule("cmap").CmapSubtable.newSubtable(uvs_format)
    uvs.platformID, uvs.platEncID, uvs.language = 0, 5, 0
    uvs.cmap = {}
    uvs.uvsDict = {0xFE00: [(0x10000, font.getGlyphOrder()[2])]}
    dmap.tables = [uvs]
    font["DMAP"] = dmap
    merged = _merge_and_recompile([_compile(font)])
    assert "DMAP" not in merged
    assert merged.getGlyphID(merged.getBestCmap()[0x10000]) == 1
    glyph = merged["cmap"].tables[0].uvsDict[0xFE00][0][1]
    assert merged.getGlyphID(glyph) == 2


@pytest.mark.parametrize("upper_family", [False, True])
@pytest.mark.parametrize("extended_header", [False, True])
@pytest.mark.parametrize("extended_formats", [False, True])
@pytest.mark.parametrize("context_format", [1, 2, 3])
@pytest.mark.parametrize("mark_filtering", [False, True])
@pytest.mark.parametrize("chaining", [False, True])
def test_merge_extended_layout(
    upper_family,
    extended_header,
    extended_formats,
    context_format,
    mark_filtering,
    chaining,
):
    from fontTools.otlLib import builder
    from fontTools.ttLib.beyond64k import _convert_layout_formats
    from fontTools.ttLib.tables import otTables as ot

    font = ttLib.TTFont(_make_fontfile_with_glyphs(0xE100, 4))
    first, second = font.getGlyphOrder()[1:3]
    addOpenTypeFeaturesFromString(
        font,
        f"""
        lookup Substitute {{ sub {first} by {second}; }} Substitute;
        lookup Position {{ pos {first} -20; }} Position;
        feature calt {{ sub {first}' lookup Substitute {second}; }} calt;
        feature kern {{ pos {first}' lookup Position {second}; }} kern;
        table GDEF {{
            GlyphClassDef [{first}], [], [{second}], [];
            LigatureCaretByPos {first} 0;
        }} GDEF;
        """,
    )
    for tag, builder_type in (
        ("GSUB", builder.ChainContextSubstBuilder),
        ("GPOS", builder.ChainContextPosBuilder),
    ):
        lookup_builder = builder_type(font, None)
        referenced_lookup = builder.SingleSubstBuilder(font, None)
        referenced_lookup.lookup_index = 0
        rule = builder.ChainContextualRule(
            [[font.getGlyphOrder()[3]]] if chaining else [],
            [[first], [second]],
            [[font.getGlyphOrder()[3]]] if chaining else [],
            [[referenced_lookup], None],
        )
        ruleset = builder.ChainContextualRuleset()
        ruleset.addRule(rule)
        if context_format == 1:
            subtable = lookup_builder.buildFormat1Subtable(ruleset, chaining)
        elif context_format == 2:
            subtable = lookup_builder.buildFormat2Subtable(
                ruleset, ruleset.format2ClassDefs(), chaining
            )
        else:
            subtable = lookup_builder.buildFormat3Subtable(rule, chaining)
        font[tag].table.LookupList.Lookup[1] = builder.buildLookup(
            [subtable], table=tag
        )
    if mark_filtering:
        font["GDEF"].table.MarkGlyphSetsDef = builder.buildMarkGlyphSetsDef(
            [{second}], font.getReverseGlyphMap()
        )
        font["GDEF"].table.Version = 0x00010002
        for tag in ("GSUB", "GPOS"):
            lookup = font[tag].table.LookupList.Lookup[0]
            lookup.LookupFlag |= 0x0010
            lookup.MarkFilteringSet = 0

    other = _make_fontfile_with_glyphs(0xE000, 4, add_layout=True)
    reference = _merge_and_recompile([other, _compile(font)])
    if upper_family:
        upper_tables(font)
    if extended_header:
        upper_tables(font, tables=["GSUB", "GPOS", "GDEF"])
    for tag in ("GSUB", "GPOS"):
        _convert_layout_formats(font[tag].table, extended_formats)
    merged = _merge_and_recompile([other, _compile(font)])
    if upper_family or extended_header:
        upper_tables(reference)
        assert "MAXP" in merged
        assert "maxp" not in merged
    else:
        assert "maxp" in merged
        assert "MAXP" not in merged
    for tag in ("GSUB", "GPOS", "GDEF"):
        assert merged[tag].compile(merged) == reference[tag].compile(reference)


def test_merge_head_different_units_per_em():
    heads = []
    for units_per_em in (1000, 2048):
        head = ttLib.newTable("head")
        head.unitsPerEm = units_per_em
        heads.append(head)

    with pytest.raises(
        ValueError,
        match=r"Cannot merge fonts with different unitsPerEm values: \[1000, 2048\]",
    ):
        ttLib.newTable("head").merge(Merger(), heads)


@pytest.mark.parametrize("v1, v2", list(itertools.permutations(range(5 + 1), 2)))
def test_merge_OS2_mixed_versions(v1, v2):
    # https://github.com/fonttools/fonttools/issues/1865
    fontfiles = [
        _make_fontfile_with_OS2(version=v1),
        _make_fontfile_with_OS2(version=v2),
    ]
    merged = _merge_and_recompile(fontfiles)
    assert merged["OS/2"].version == max(v1, v2)


def test_merge_keeps_compact_tables_below_glyph_limit():
    fontfiles = [
        _make_fontfile_with_glyphs(0xE000, 10),
        _make_fontfile_with_glyphs(0xE100, 10),
    ]

    merged = _merge_and_recompile(fontfiles)

    assert "glyf" in merged
    assert "GLYF" not in merged
    assert "maxp" in merged
    assert "MAXP" not in merged


def test_merge_uses_upper_tables_above_glyph_limit():
    fontfiles = [
        _make_fontfile_with_glyphs(0x10000, 0x8001),
        _make_fontfile_with_glyphs(0x20000, 0x8001),
    ]

    merged = _merge_and_recompile(fontfiles)

    assert merged.hasExtendedGlyphIDs()
    assert "GLYF" in merged
    assert "glyf" not in merged
    assert "MAXP" in merged
    assert "maxp" not in merged
    assert "HHEA" in merged
    assert "HMTX" in merged
    assert "LOCA" in merged


def test_merge_uses_upper_layout_above_glyph_limit():
    fontfiles = [
        _make_fontfile_with_glyphs(0x10000, 0x8001, add_layout=True),
        _make_fontfile_with_glyphs(0x20000, 0x8001),
    ]

    merged = _merge_and_recompile(fontfiles)

    table = merged["GSUB"].table
    assert table.Version == 0x00010002
    assert table.ScriptList is None
    assert table.FeatureList is None
    assert table.LookupList is None
    assert table.ScriptList2 is not None
    assert table.FeatureList2 is not None
    assert table.LookupList2 is not None


def test_merge_preserves_upper_input_family_below_glyph_limit():
    fontfiles = [
        _upper_fontfile(_make_fontfile_with_glyphs(0xE000, 10)),
        _make_fontfile_with_glyphs(0xE100, 10),
    ]

    merged = _merge_and_recompile(fontfiles)

    assert "GLYF" in merged
    assert "glyf" not in merged
    assert "MAXP" in merged
    assert "maxp" not in merged


def _make_fontfile_with_MATH(glyphs, **kwargs):
    glyphOrder = [".notdef"] + glyphs
    fb = FontBuilder(unitsPerEm=1000)
    fb.setupGlyphOrder(glyphOrder)
    fb.setupCharacterMap({})
    fb.setupGlyf({gn: Glyph() for gn in glyphOrder})
    fb.setupHorizontalMetrics({gn: (500, 0) for gn in glyphOrder})
    fb.setupHorizontalHeader()
    fb.setupNameTable({"familyName": "TestMATH", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    if kwargs:
        buildMathTable(fb.font, **kwargs)
    return _compile(fb.font)


def test_merge_MATH():
    # https://github.com/fonttools/fonttools/issues/3823
    fontfiles = [
        _make_fontfile_with_MATH(
            ["a", "parenleft", "parenleft.size1"],
            constants={"AxisHeight": 250},
            italicsCorrections={"a": 10},
            mathKerns={"a": {"TopRight": ([100], [10, 20])}},
            minConnectorOverlap=20,
            vertGlyphVariants={
                "parenleft": [("parenleft", 700), ("parenleft.size1", 1000)]
            },
        ),
        _make_fontfile_with_MATH(
            ["b", "integral", "minus"],
            constants={"AxisHeight": 300},
            italicsCorrections={"b": 20},
            topAccentAttachments={"b": 250},
            extendedShapes={"integral"},
            minConnectorOverlap=30,
            horizGlyphVariants={"minus": [("minus", 500)]},
        ),
        _make_fontfile_with_MATH(["c"]),
    ]
    merged = _merge_and_recompile(fontfiles)

    table = merged["MATH"].table
    assert table.MathConstants.AxisHeight.Value == 250

    glyphInfo = table.MathGlyphInfo
    italics = glyphInfo.MathItalicsCorrectionInfo
    assert italics.Coverage.glyphs == ["a", "b"]
    assert [v.Value for v in italics.ItalicsCorrection] == [10, 20]
    topAccent = glyphInfo.MathTopAccentAttachment
    assert topAccent.TopAccentCoverage.glyphs == ["b"]
    assert [v.Value for v in topAccent.TopAccentAttachment] == [250]
    assert glyphInfo.ExtendedShapeCoverage.glyphs == ["integral"]
    assert glyphInfo.MathKernInfo.MathKernCoverage.glyphs == ["a"]
    assert len(glyphInfo.MathKernInfo.MathKernInfoRecords) == 1

    variants = table.MathVariants
    assert variants.MinConnectorOverlap == 20
    assert variants.VertGlyphCoverage.glyphs == ["parenleft"]
    assert [
        r.VariantGlyph for r in variants.VertGlyphConstruction[0].MathGlyphVariantRecord
    ] == ["parenleft", "parenleft.size1"]
    assert variants.HorizGlyphCoverage.glyphs == ["minus"]
    assert [
        r.VariantGlyph
        for r in variants.HorizGlyphConstruction[0].MathGlyphVariantRecord
    ] == ["minus"]


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
