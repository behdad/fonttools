import io
import os
import re
import random
import tempfile
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import (
    TTFont,
    TTLibError,
    newTable,
    registerCustomTableClass,
    unregisterCustomTableClass,
)
from fontTools.ttLib.standardGlyphOrder import standardGlyphOrder
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
import pytest

DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "data")


@pytest.mark.parametrize("glyph_zero", [".notdef", "zero"])
@pytest.mark.parametrize("dmap_format", [4, 12, 13])
def test_getBestCmap_DMAP_zero_fallback(glyph_zero, dmap_format):
    font = TTFont()
    font.setGlyphOrder([glyph_zero, "baseA", "baseB", "dmapB"])
    for tag, format, mapping in (
        ("cmap", 4, {0x41: "baseA", 0x42: "baseB"}),
        ("DMAP", dmap_format, {0x41: glyph_zero, 0x42: "dmapB"}),
    ):
        table = CmapSubtable.newSubtable(format)
        table.platformID = 3
        table.platEncID = 1 if format == 4 else 10
        table.language = 0
        table.cmap = mapping
        font[tag] = newTable(tag)
        font[tag].tableVersion = 0
        font[tag].tables = [table]

    assert font.getBestCmap() == {0x41: "baseA", 0x42: "dmapB"}
    assert font["DMAP"].getBestCmap() == {0x41: glyph_zero, 0x42: "dmapB"}
    del font["cmap"]
    assert font.getBestCmap() == {0x42: "dmapB"}
    font["DMAP"].tables[0].cmap = {0x41: glyph_zero}
    assert font.getBestCmap() == {}


class CustomTableClass(DefaultTable):
    def decompile(self, data, ttFont):
        self.numbers = list(data)

    def compile(self, ttFont):
        return bytes(self.numbers)

    # not testing XML read/write


table_C_U_S_T_ = CustomTableClass  # alias for testing


TABLETAG = "CUST"


def normalize_TTX(string):
    string = re.sub(' ttLibVersion=".*"', "", string)
    string = re.sub('checkSumAdjustment value=".*"', "", string)
    string = re.sub('modified value=".*"', "", string)
    return string


def test_registerCustomTableClass():
    font = TTFont()
    font[TABLETAG] = newTable(TABLETAG)
    font[TABLETAG].data = b"\x00\x01\xff"
    f = io.BytesIO()
    font.save(f)
    f.seek(0)
    assert font[TABLETAG].data == b"\x00\x01\xff"
    registerCustomTableClass(TABLETAG, "ttFont_test", "CustomTableClass")
    try:
        font = TTFont(f)
        assert font[TABLETAG].numbers == [0, 1, 255]
        assert font[TABLETAG].compile(font) == b"\x00\x01\xff"
    finally:
        unregisterCustomTableClass(TABLETAG)


def test_registerCustomTableClassStandardName():
    registerCustomTableClass(TABLETAG, "ttFont_test")
    try:
        font = TTFont()
        font[TABLETAG] = newTable(TABLETAG)
        font[TABLETAG].numbers = [4, 5, 6]
        assert font[TABLETAG].compile(font) == b"\x04\x05\x06"
    finally:
        unregisterCustomTableClass(TABLETAG)


ttxTTF = r"""<?xml version="1.0" encoding="UTF-8"?>
<ttFont sfntVersion="\x00\x01\x00\x00" ttLibVersion="4.9.0">
  <hmtx>
    <mtx name=".notdef" width="300" lsb="0"/>
  </hmtx>
</ttFont>
"""


ttxOTF = """<?xml version="1.0" encoding="UTF-8"?>
<ttFont sfntVersion="OTTO" ttLibVersion="4.9.0">
  <hmtx>
    <mtx name=".notdef" width="300" lsb="0"/>
  </hmtx>
</ttFont>
"""


def test_sfntVersionFromTTX():
    # https://github.com/fonttools/fonttools/issues/2370
    font = TTFont()
    assert font.sfntVersion == "\x00\x01\x00\x00"
    ttx = io.StringIO(ttxOTF)
    # Font is "empty", TTX file will determine sfntVersion
    font.importXML(ttx)
    assert font.sfntVersion == "OTTO"
    ttx = io.StringIO(ttxTTF)
    # Font is not "empty", sfntVersion in TTX file will be ignored
    font.importXML(ttx)
    assert font.sfntVersion == "OTTO"


def test_virtualGlyphId():
    otfpath = os.path.join(DATA_DIR, "TestVGID-Regular.otf")
    ttxpath = os.path.join(DATA_DIR, "TestVGID-Regular.ttx")

    otf = TTFont(otfpath)

    ttx = TTFont()
    ttx.importXML(ttxpath)

    with open(ttxpath, encoding="utf-8") as fp:
        xml = normalize_TTX(fp.read()).splitlines()

    for font in (otf, ttx):
        GSUB = font["GSUB"].table
        assert GSUB.LookupList.LookupCount == 37
        lookup = GSUB.LookupList.Lookup[32]
        assert lookup.LookupType == 8
        subtable = lookup.SubTable[0]
        assert subtable.LookAheadGlyphCount == 1
        lookahead = subtable.LookAheadCoverage[0]
        assert len(lookahead.glyphs) == 46
        assert "glyph00453" in lookahead.glyphs

        out = io.StringIO()
        font.saveXML(out)
        outxml = normalize_TTX(out.getvalue()).splitlines()
        assert xml == outxml


def test_setGlyphOrder_also_updates_glyf_glyphOrder():
    # https://github.com/fonttools/fonttools/issues/2060#issuecomment-1063932428
    font = TTFont()
    font.importXML(os.path.join(DATA_DIR, "TestTTF-Regular.ttx"))
    current_order = font.getGlyphOrder()

    assert current_order == font["glyf"].glyphOrder

    new_order = list(current_order)
    while new_order == current_order:
        random.shuffle(new_order)

    font.setGlyphOrder(new_order)

    assert font.getGlyphOrder() == new_order
    assert font["glyf"].glyphOrder == new_order


def test_setGlyphOrder_also_updates_GLYF_glyphOrder():
    font = TTFont()
    font["GLYF"] = newTable("GLYF")
    font["GLYF"].glyphs = {}

    font.setGlyphOrder([".notdef", "a"])

    assert font["GLYF"].glyphOrder == [".notdef", "a"]


def test_getGlyphOrder_prefers_MAXP():
    font = TTFont()
    font["maxp"] = newTable("maxp")
    font["maxp"].numGlyphs = 1
    font["MAXP"] = newTable("MAXP")
    font["MAXP"].numGlyphs = 2

    assert font.getGlyphOrder() == [".notdef", "glyph00001"]


def test_getGlyphOrder_from_post_uses_MAXP():
    font = TTFont()
    font["MAXP"] = newTable("MAXP")
    font["MAXP"].numGlyphs = 2
    font["post"] = newTable("post")
    font["post"].decode_format_1_0(b"", font)

    assert font.getGlyphOrder() == standardGlyphOrder[:2]


def test_getGlyphSet_prefers_locked_uppercase_tables():
    font = TTFont()
    font.setGlyphOrder([".notdef"])
    font["GLYF"] = newTable("GLYF")
    font["GLYF"].glyphs = {".notdef": object()}
    font["GLYF"].glyphOrder = font.getGlyphOrder()
    font["glyf"] = newTable("glyf")
    font["HMTX"] = newTable("HMTX")
    font["HMTX"].metrics = {".notdef": (500, 0)}
    font["GVAR"] = newTable("GVAR")

    glyphSet = font.getGlyphSet()

    assert glyphSet.glyfTable is font["GLYF"]
    assert glyphSet.hMetrics is font["HMTX"].metrics
    assert glyphSet.gvarTable is font["GVAR"]


def test_saveXML_splitGlyphs_for_GLYF(tmp_path):
    font = TTFont()
    font["GLYF"] = newTable("GLYF")
    received = []
    font["GLYF"].toXML = lambda writer, ttFont, splitGlyphs=False: received.append(
        splitGlyphs
    )

    font.saveXML(tmp_path / "font.ttx", tables=["GLYF"], splitGlyphs=True)

    assert received == [True]


def test_getGlyphOrder_not_true_post_format_1(caplog):
    # https://github.com/fonttools/fonttools/issues/2736
    caplog.set_level("WARNING")
    font = TTFont(os.path.join(DATA_DIR, "bogus_post_format_1.ttf"))
    hmtx = font["hmtx"]
    assert len(hmtx.metrics) > len(standardGlyphOrder)
    log_rec = caplog.records[-1]
    assert log_rec.levelname == "WARNING"
    assert "Not enough names found in the 'post' table" in log_rec.message


@pytest.mark.parametrize("lazy", [None, True, False])
def test_ensureDecompiled(lazy):
    # test that no matter the lazy value, ensureDecompiled decompiles all tables
    font = TTFont()
    font.importXML(os.path.join(DATA_DIR, "TestTTF-Regular.ttx"))
    # test font has no OTL so we add some, as an example of otData-driven tables
    addOpenTypeFeaturesFromString(
        font,
        """
        feature calt {
            sub period' period' period' space by ellipsis;
        } calt;

        feature dist {
            pos period period -30;
        } dist;
        """,
    )
    # also add an additional cmap subtable that will be lazily-loaded
    cm = CmapSubtable.newSubtable(14)
    cm.platformID = 0
    cm.platEncID = 5
    cm.language = 0
    cm.cmap = {}
    cm.uvsDict = {0xFE00: [(0x002E, None)]}
    font["cmap"].tables.append(cm)

    # save and reload, potentially lazily
    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    font = TTFont(buf, lazy=lazy)

    # check no table is loaded until/unless requested, no matter the laziness
    for tag in font.keys():
        assert not font.isLoaded(tag)

    if lazy is not False:
        # additional cmap doesn't get decompiled automatically unless lazy=False;
        # can't use hasattr or else cmap's maginc __getattr__ kicks in...
        cm = next(st for st in font["cmap"].tables if st.__dict__["format"] == 14)
        assert cm.data is not None
        assert "uvsDict" not in cm.__dict__
        # glyf glyphs are not expanded unless lazy=False
        assert font["glyf"].glyphs["period"].data is not None
        assert not hasattr(font["glyf"].glyphs["period"], "coordinates")

    if lazy is True:
        # OTL tables hold a 'reader' to lazily load when lazy=True
        assert "reader" in font["GSUB"].table.LookupList.__dict__
        assert "reader" in font["GPOS"].table.LookupList.__dict__

    font.ensureDecompiled()

    # all tables are decompiled now
    for tag in font.keys():
        assert font.isLoaded(tag)
    # including the additional cmap
    cm = next(st for st in font["cmap"].tables if st.__dict__["format"] == 14)
    assert cm.data is None
    assert "uvsDict" in cm.__dict__
    # expanded glyf glyphs lost the 'data' attribute
    assert not hasattr(font["glyf"].glyphs["period"], "data")
    assert hasattr(font["glyf"].glyphs["period"], "coordinates")
    # and OTL tables have read their 'reader'
    assert "reader" not in font["GSUB"].table.LookupList.__dict__
    assert "Lookup" in font["GSUB"].table.LookupList.__dict__
    assert "reader" not in font["GPOS"].table.LookupList.__dict__
    assert "Lookup" in font["GPOS"].table.LookupList.__dict__


@pytest.fixture
def testFont_fvar_avar():
    ttxpath = os.path.join(DATA_DIR, "TestTTF_normalizeLocation.ttx")
    ttf = TTFont()
    ttf.importXML(ttxpath)
    return ttf


@pytest.mark.parametrize(
    "userLocation, expectedNormalizedLocation",
    [
        ({}, {"wght": 0.0}),
        ({"wght": 100}, {"wght": -1.0}),
        ({"wght": 250}, {"wght": -0.75}),
        ({"wght": 400}, {"wght": 0.0}),
        ({"wght": 550}, {"wght": 0.75}),
        ({"wght": 625}, {"wght": 0.875}),
        ({"wght": 700}, {"wght": 1.0}),
    ],
)
def test_font_normalizeLocation(
    testFont_fvar_avar, userLocation, expectedNormalizedLocation
):
    normalizedLocation = testFont_fvar_avar.normalizeLocation(userLocation)
    assert expectedNormalizedLocation == normalizedLocation


def test_font_normalizeLocation_no_VF():
    ttf = TTFont()
    with pytest.raises(TTLibError, match="Not a variable font"):
        ttf.normalizeLocation({})


def test_getGlyphID():
    font = TTFont()
    font.importXML(os.path.join(DATA_DIR, "TestTTF-Regular.ttx"))

    assert font.getGlyphID("space") == 3
    assert font.getGlyphID("glyph12345") == 12345  # virtual glyph
    with pytest.raises(KeyError):
        font.getGlyphID("non_existent")
    with pytest.raises(KeyError):
        font.getGlyphID("glyph_prefix_but_invalid_id")


def test_hasExtendedGlyphIDs():
    font = TTFont()
    font.setGlyphOrder(["glyph"] * 0x10000)
    assert not font.hasExtendedGlyphIDs()
    font.setGlyphOrder(["glyph"] * 0x10001)
    assert font.hasExtendedGlyphIDs()


def test_spooled_tempfile_may_not_have_attribute_seekable():
    # SpooledTemporaryFile only got a seekable attribute on Python 3.11
    # https://github.com/fonttools/fonttools/issues/3052
    font = TTFont()
    font.importXML(os.path.join(DATA_DIR, "TestTTF-Regular.ttx"))
    tmp = tempfile.SpooledTemporaryFile()
    font.save(tmp)
    # this should not fail
    _ = TTFont(tmp)


def test_unseekable_file_lazy_loading_fails():
    class NonSeekableFile:
        def __init__(self):
            self.file = io.BytesIO()

        def read(self, size):
            return self.file.read(size)

        def seekable(self):
            return False

    f = NonSeekableFile()
    with pytest.raises(TTLibError, match="Input file must be seekable when lazy=True"):
        TTFont(f, lazy=True)


def test_unsupported_seek_operation_lazy_loading_fails():
    class UnsupportedSeekFile:
        def __init__(self):
            self.file = io.BytesIO()

        def read(self, size):
            return self.file.read(size)

        def seek(self, offset):
            raise io.UnsupportedOperation("Unsupported seek operation")

    f = UnsupportedSeekFile()
    with pytest.raises(TTLibError, match="Input file must be seekable when lazy=True"):
        TTFont(f, lazy=True)


@pytest.mark.parametrize(
    "file_name",
    [
        "duplicate_glyph_name.ttf",
        "duplicate_glyph_name.otf",
    ],
)
def test_duplicate_glyph_names(file_name):
    font_path = os.path.join(DATA_DIR, file_name)
    font = TTFont(font_path)

    assert font.getGlyphOrder() == [".notdef", "space", "A", "A.2", "A.1"]

    if "CFF " not in font:
        post = font["post"]
        assert post.mapping == {"A.2": "A"}


def test_saveXML_default_dumps_all_tables():
    """tables=None (default) should dump all tables (regression test for #4025)."""
    font = TTFont()
    font.importXML(os.path.join(DATA_DIR, "TestTTF-Regular.ttx"))
    out = io.StringIO()
    font.saveXML(out)
    xml = out.getvalue()
    assert "<head>" in xml
    assert "<hhea>" in xml


def test_saveXML_specific_tables():
    """Passing tables=['head'] should dump only head."""
    font = TTFont()
    font.importXML(os.path.join(DATA_DIR, "TestTTF-Regular.ttx"))
    out = io.StringIO()
    font.saveXML(out, tables=["head"])
    xml = out.getvalue()
    assert "<head>" in xml
    assert "<hhea>" not in xml


@pytest.mark.skipif(
    os.name == "nt", reason="Windows filenames cannot contain tabs or newlines"
)
@pytest.mark.parametrize("whitespace", ["\t", "\n"])
def test_split_xml_whitespace_filename_roundtrip(tmp_path, whitespace):
    font = TTFont()
    font["name"] = newTable("name")
    font["name"].setName("Example", 1, 3, 1, 0x409)
    path = tmp_path / f"name{whitespace}file.ttx"
    font.saveXML(path, tables=["name"], splitTables=True)

    restored = TTFont()
    restored.importXML(path)
    assert restored["name"].getDebugName(1) == "Example"


def test_saveXML_skipTables():
    """skipTables should exclude specified tables when tables is None."""
    font = TTFont()
    font.importXML(os.path.join(DATA_DIR, "TestTTF-Regular.ttx"))
    out = io.StringIO()
    font.saveXML(out, skipTables=["head"])
    xml = out.getvalue()
    assert "<head>" not in xml
    assert "<hhea>" in xml
