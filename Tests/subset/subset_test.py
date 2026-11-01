import io
from fontTools.ttLib.tables._n_a_m_e import NameRecordVisitor
import fontTools.ttLib.tables.otBase
from fontTools.misc.testTools import getXML, stripVariableItemsFromTTX
from fontTools.misc.textTools import tobytes, tostr
from fontTools import subset
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.misc.loggingTools import CapturingLogHandler
from fontTools.subset.svg import etree
import difflib
import logging
import os
import shutil
import sys
import tempfile
import unittest
import pathlib
import pytest
from types import SimpleNamespace


class SubsetTest:
    @classmethod
    def setup_class(cls):
        cls.tempdir = None
        cls.num_tempfiles = 0

    @classmethod
    def teardown_class(cls):
        if cls.tempdir:
            shutil.rmtree(cls.tempdir, ignore_errors=True)

    @staticmethod
    def getpath(*testfile):
        path, _ = os.path.split(__file__)
        return os.path.join(path, "data", *testfile)

    @classmethod
    def temp_path(cls, suffix):
        if not cls.tempdir:
            cls.tempdir = tempfile.mkdtemp()
        cls.num_tempfiles += 1
        return os.path.join(cls.tempdir, "tmp%d%s" % (cls.num_tempfiles, suffix))

    @staticmethod
    def read_ttx(path):
        with open(path, "r", encoding="utf-8") as f:
            ttx = f.read()
        # don't care whether TTF or OTF, thus strip sfntVersion as well
        return stripVariableItemsFromTTX(ttx, sfntVersion=True).splitlines(True)

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
            pytest.fail("TTX output is different from expected")

    def compile_font(self, path, suffix):
        savepath = self.temp_path(suffix=suffix)
        font = TTFont(recalcBBoxes=False, recalcTimestamp=False)
        font.importXML(path)
        font.save(savepath, reorderTables=None)
        return savepath

    # -----
    # Tests
    # -----

    @pytest.mark.parametrize("vertical", [False, True])
    @pytest.mark.parametrize("retain_gids", [False, True])
    def test_uppercase_companion_tables(self, vertical, retain_gids):
        from fontTools.ttLib.beyond64k import upper_tables

        fb = FontBuilder(1000)
        order = [".notdef", "a", "b", "unused"]
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap({0x61: "a", 0x62: "b"})
        fb.setupGlyf({name: TTGlyphPen(None).glyph() for name in order})
        fb.setupHorizontalMetrics({name: (500, 0) for name in order})
        fb.setupHorizontalHeader()
        if vertical:
            fb.setupVerticalMetrics({name: (1000, 0) for name in order})
            fb.setupVerticalHeader()
        fb.setupNameTable({"familyName": "Uppercase subset", "styleName": "Regular"})
        fb.setupOS2()
        fb.setupPost()
        upper_tables(fb.font)
        source = self.temp_path(".ttf")
        output = self.temp_path(".ttf")
        fb.font.save(source)

        args = [source, "--unicodes=U+0062", "--output-file=" + output]
        if retain_gids:
            args.append("--retain-gids")
        subset.main(args)
        font = TTFont(output)
        count = 3 if retain_gids else 2
        assert font["MAXP"].numGlyphs == count
        assert "GLYF" in font and "LOCA" in font
        assert len(font["LOCA"].locations) == count + 1
        assert font["HHEA"].numberOfHMetrics == (count if retain_gids else 1)
        assert font["HMTX"].metrics["b"] == (500, 0)
        if vertical:
            assert font["VHEA"].numberOfVMetrics == (count if retain_gids else 1)
            assert font["VMTX"].metrics["b"] == (1000, 0)
        assert not {"maxp", "glyf", "loca", "hhea", "hmtx", "vhea", "vmtx"} & set(
            font.keys()
        )

    def test_layout_scripts(self):
        fontpath = self.compile_font(self.getpath("layout_scripts.ttx"), ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--glyphs=*",
                "--layout-features=*",
                "--layout-scripts=latn,arab.URD,arab.dflt",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("expect_layout_scripts.ttx"), ["GPOS", "GSUB"]
        )

    def test_no_notdef_outline_otf(self):
        fontpath = self.compile_font(self.getpath("TestOTF-Regular.ttx"), ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--no-notdef-outline",
                "--gids=0",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("expect_no_notdef_outline_otf.ttx"), ["CFF "]
        )

    def test_no_notdef_outline_cid(self):
        fontpath = self.compile_font(self.getpath("TestCID-Regular.ttx"), ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--no-notdef-outline",
                "--gids=0",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("expect_no_notdef_outline_cid.ttx"), ["CFF "]
        )

    def test_no_notdef_outline_ttf(self):
        fontpath = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [
                fontpath,
                "--no-notdef-outline",
                "--gids=0",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont,
            self.getpath("expect_no_notdef_outline_ttf.ttx"),
            ["glyf", "hmtx"],
        )

    def test_subset_ankr(self):
        fontpath = self.compile_font(self.getpath("TestANKR.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=one", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_ankr.ttx"), ["ankr"])

    def test_subset_ankr_remove(self):
        fontpath = self.compile_font(self.getpath("TestANKR.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=two", "--output-file=%s" % subsetpath])
        assert "ankr" not in TTFont(subsetpath)

    def test_subset_bsln_format_0(self):
        fontpath = self.compile_font(self.getpath("TestBSLN-0.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=one", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_bsln_0.ttx"), ["bsln"])

    def test_subset_bsln_format_0_from_format_1(self):
        # TestBSLN-1 defines the ideographic baseline to be the font's default,
        # and specifies that glyphs {.notdef, zero, one, two} use the roman
        # baseline instead of the default ideographic baseline. As we request
        # a subsetted font with {zero, one} and the implicit .notdef, all
        # glyphs in the resulting font use the Roman baseline. In this case,
        # we expect a format 0 'bsln' table because it is the most compact.
        fontpath = self.compile_font(self.getpath("TestBSLN-1.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [fontpath, "--unicodes=U+0030-0031", "--output-file=%s" % subsetpath]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_bsln_0.ttx"), ["bsln"])

    def test_subset_bsln_format_1(self):
        # TestBSLN-1 defines the ideographic baseline to be the font's default,
        # and specifies that glyphs {.notdef, zero, one, two} use the roman
        # baseline instead of the default ideographic baseline. We request
        # a subset where the majority of glyphs use the roman baseline,
        # but one single glyph (uni2EA2) is ideographic. In the resulting
        # subsetted font, we expect a format 1 'bsln' table whose default
        # is Roman, but with an override that uses the ideographic baseline
        # for uni2EA2.
        fontpath = self.compile_font(self.getpath("TestBSLN-1.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [fontpath, "--unicodes=U+0030-0031,U+2EA2", "--output-file=%s" % subsetpath]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_bsln_1.ttx"), ["bsln"])

    def test_subset_bsln_format_2(self):
        # The 'bsln' table in TestBSLN-2 refers to control points in glyph 'P'
        # for defining its baselines. Therefore, the subsetted font should
        # include this glyph even though it is not requested explicitly.
        fontpath = self.compile_font(self.getpath("TestBSLN-2.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=one", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_bsln_2.ttx"), ["bsln"])

    def test_subset_bsln_format_2_from_format_3(self):
        # TestBSLN-3 defines the ideographic baseline to be the font's default,
        # and specifies that glyphs {.notdef, zero, one, two, P} use the roman
        # baseline instead of the default ideographic baseline. As we request
        # a subsetted font with zero and the implicit .notdef and P for
        # baseline measurement, all glyphs in the resulting font use the Roman
        # baseline. In this case, we expect a format 2 'bsln' table because it
        # is the most compact encoding.
        fontpath = self.compile_font(self.getpath("TestBSLN-3.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--unicodes=U+0030", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_bsln_2.ttx"), ["bsln"])

    def test_subset_bsln_format_3(self):
        # TestBSLN-3 defines the ideographic baseline to be the font's default,
        # and specifies that glyphs {.notdef, zero, one, two} use the roman
        # baseline instead of the default ideographic baseline. We request
        # a subset where the majority of glyphs use the roman baseline,
        # but one single glyph (uni2EA2) is ideographic. In the resulting
        # subsetted font, we expect a format 1 'bsln' table whose default
        # is Roman, but with an override that uses the ideographic baseline
        # for uni2EA2.
        fontpath = self.compile_font(self.getpath("TestBSLN-3.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [fontpath, "--unicodes=U+0030-0031,U+2EA2", "--output-file=%s" % subsetpath]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_bsln_3.ttx"), ["bsln"])

    def test_subset_BASE(self):
        fontpath = self.compile_font(self.getpath("TestBASE.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--gids=2,3", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_BASE.ttx"), ["BASE"])

    def test_subset_clr(self):
        fontpath = self.compile_font(self.getpath("TestCLR-Regular.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=smileface", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont,
            self.getpath("expect_keep_colr.ttx"),
            ["GlyphOrder", "hmtx", "glyf", "COLR", "CPAL"],
        )

    def test_subset_gvar(self):
        fontpath = self.compile_font(self.getpath("TestGVAR.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [fontpath, "--unicodes=U+002B,U+2212", "--output-file=%s" % subsetpath]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont,
            self.getpath("expect_keep_gvar.ttx"),
            ["GlyphOrder", "avar", "fvar", "gvar", "name"],
        )

    def test_subset_gvar_notdef_outline(self):
        fontpath = self.compile_font(self.getpath("TestGVAR.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [
                fontpath,
                "--unicodes=U+0030",
                "--notdef_outline",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont,
            self.getpath("expect_keep_gvar_notdef_outline.ttx"),
            ["GlyphOrder", "avar", "fvar", "gvar", "name"],
        )

    def test_subset_lcar_remove(self):
        fontpath = self.compile_font(self.getpath("TestLCAR-0.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=one", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        assert "lcar" not in subsetfont

    def test_subset_lcar_format_0(self):
        fontpath = self.compile_font(self.getpath("TestLCAR-0.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--unicodes=U+FB01", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_lcar_0.ttx"), ["lcar"])

    def test_subset_lcar_format_1(self):
        fontpath = self.compile_font(self.getpath("TestLCAR-1.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--unicodes=U+FB01", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_lcar_1.ttx"), ["lcar"])

    def test_subset_math(self):
        fontpath = self.compile_font(self.getpath("TestMATH-Regular.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [
                fontpath,
                "--unicodes=U+0041,U+0028,U+0302,U+1D400,U+1D435",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont,
            self.getpath("expect_keep_math.ttx"),
            ["GlyphOrder", "CFF ", "MATH", "hmtx"],
        )

    def test_subset_math_partial(self):
        fontpath = self.compile_font(self.getpath("test_math_partial.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--text=A", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_math_partial.ttx"), ["MATH"])

    def test_subset_math_closure_drops_added_glyph_constructions(self):
        # Regression test for https://github.com/fonttools/fonttools/pull/4096
        # The test font has glyphs ".notdef, A, A.size1, A.size2"; only "A" is
        # reachable via cmap. "A.size1" is both a vertical variant of "A" and a
        # construction base of its own that grows into "A.size2". Subsetting to
        # "A" pulls in "A.size1" via closure but must not retain "A.size1"'s
        # construction, which would dangle a reference to the never-closed-over
        # "A.size2".
        fontpath = self.compile_font(self.getpath("test_math_closure.ttx"), ".ttf")
        font = TTFont(fontpath)

        subsetter = subset.Subsetter()
        subsetter.populate(text="A")
        subsetter.subset(font)

        glyph_set = set(font.getGlyphOrder())
        # "A.size1" survives: it is a legitimate variant of the requested "A".
        assert "A.size1" in glyph_set
        # "A.size2" was never closed over, so it is not in the subset.
        assert "A.size2" not in glyph_set

        math_variants = font["MATH"].table.MathVariants
        # Only "A" keeps a construction; "A.size1"'s construction is dropped
        # because "A.size1" entered the subset solely through closure.
        assert list(math_variants.VertGlyphCoverage.glyphs) == ["A"]
        assert math_variants.VertGlyphCount == 1
        # No surviving construction references a glyph outside the subset.
        for cons in math_variants.VertGlyphConstruction:
            for rec in cons.MathGlyphVariantRecord:
                assert rec.VariantGlyph in glyph_set

    def test_subset_opbd_remove(self):
        # In the test font, only the glyphs 'A' and 'zero' have an entry in
        # the Optical Bounds table. When subsetting, we do not request any
        # of those glyphs. Therefore, the produced subsetted font should
        # not contain an 'opbd' table.
        fontpath = self.compile_font(self.getpath("TestOPBD-0.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=one", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        assert "opbd" not in subsetfont

    def test_subset_opbd_format_0(self):
        fontpath = self.compile_font(self.getpath("TestOPBD-0.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=A", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_opbd_0.ttx"), ["opbd"])

    def test_subset_opbd_format_1(self):
        fontpath = self.compile_font(self.getpath("TestOPBD-1.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=A", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_opbd_1.ttx"), ["opbd"])

    def test_subset_prop_remove_default_zero(self):
        # If all glyphs have an AAT glyph property with value 0,
        # the "prop" table should be removed from the subsetted font.
        fontpath = self.compile_font(self.getpath("TestPROP.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--unicodes=U+0041", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        assert "prop" not in subsetfont

    def test_subset_prop_0(self):
        # If all glyphs share the same AAT glyph properties, the "prop" table
        # in the subsetted font should use format 0.
        #
        # Unless the shared value is zero, in which case the subsetted font
        # should have no "prop" table at all. But that case has already been
        # tested above in test_subset_prop_remove_default_zero().
        fontpath = self.compile_font(self.getpath("TestPROP.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [
                fontpath,
                "--unicodes=U+0030-0032",
                "--no-notdef-glyph",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_prop_0.ttx"), ["prop"])

    def test_subset_prop_1(self):
        # If not all glyphs share the same AAT glyph properties, the subsetted
        # font should contain a "prop" table in format 1. To save space, the
        # DefaultProperties should be set to the most frequent value.
        fontpath = self.compile_font(self.getpath("TestPROP.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [
                fontpath,
                "--unicodes=U+0030-0032",
                "--notdef-outline",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_prop_1.ttx"), ["prop"])

    def test_options(self):
        # https://github.com/fonttools/fonttools/issues/413
        opt1 = subset.Options()
        assert "Xyz-" not in opt1.layout_features
        opt2 = subset.Options()
        opt2.layout_features.append("Xyz-")
        assert "Xyz-" in opt2.layout_features
        assert "Xyz-" not in opt1.layout_features

    def test_google_color(self):
        fontpath = self.compile_font(self.getpath("google_color.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--gids=0,1", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        assert "CBDT" in subsetfont
        assert "CBLC" in subsetfont
        assert "x" in subsetfont["CBDT"].strikeData[0]
        assert "y" not in subsetfont["CBDT"].strikeData[0]

    def test_google_color_all(self):
        fontpath = self.compile_font(self.getpath("google_color.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--unicodes=*", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        assert "x" in subsetfont["CBDT"].strikeData[0]
        assert "y" in subsetfont["CBDT"].strikeData[0]

    def test_sbix(self):
        fontpath = self.compile_font(self.getpath("sbix.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--gids=0,1", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_sbix.ttx"), ["sbix"])

    def test_varComposite(self):
        fontpath = self.getpath("..", "..", "ttLib", "data", "varc-ac00-ac01.ttf")
        origfont = TTFont(fontpath)
        assert len(origfont.getGlyphOrder()) == 11
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--unicodes=ac00", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        assert len(subsetfont.getGlyphOrder()) == 6
        varc = subsetfont["VARC"].table
        assert len(varc.AxisIndicesList.Item) == 2
        assert len(varc.MultiVarStore.MultiVarData) == 1
        assert len(varc.MultiVarStore.MultiVarData[0].Item) == 2
        assert len(varc.MultiVarStore.SparseVarRegionList.Region) == 3
        subset.main([fontpath, "--unicodes=ac01", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        assert len(subsetfont.getGlyphOrder()) == 8
        varc = subsetfont["VARC"].table
        assert len(varc.AxisIndicesList.Item) == 2
        assert len(varc.MultiVarStore.MultiVarData) == 1
        assert len(varc.MultiVarStore.MultiVarData[0].Item) == 5
        assert len(varc.MultiVarStore.SparseVarRegionList.Region) == 3

    @pytest.mark.parametrize(
        "edges",
        [
            {"a": ["a"]},
            {"a": ["b"], "b": ["a"]},
            {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []},
        ],
    )
    def test_varComposite_closure_visited(self, edges):
        varc = newTable("VARC")
        varc.table = ot.VARC()
        varc.table.Coverage = ot.Coverage()
        varc.table.Coverage.glyphs = list(edges)
        varc.table.VarCompositeGlyphs = ot.VarCompositeGlyphs()
        records = varc.table.VarCompositeGlyphs.VarCompositeGlyph = []
        for names in edges.values():
            glyph = ot.VarCompositeGlyph()
            glyph.components = []
            for name in names:
                component = ot.VarComponent()
                component.glyphName = name
                glyph.components.append(component)
            records.append(glyph)
        state = SimpleNamespace(glyphs={"a"})
        varc.closure_glyphs(state)
        assert state.glyphs == set(edges)

    def test_varComposite_self_reference_subset(self):
        font = TTFont(self.getpath("..", "..", "cffLib", "data", "varc-short-cff2.otf"))
        varc = font["VARC"].table
        varc.Coverage.glyphs.insert(0, "leaf")
        component = ot.VarComponent()
        component.glyphName = "leaf"
        glyph = ot.VarCompositeGlyph()
        glyph.components = [component]
        varc.VarCompositeGlyphs.VarCompositeGlyph.insert(0, glyph)

        sub = subset.Subsetter()
        sub.populate(glyphs=["composite"])
        sub.subset(font)
        data = io.BytesIO()
        font.save(data)
        font = TTFont(io.BytesIO(data.getvalue()))
        glyphSet = font.getGlyphSet()
        composite = font.getBestCmap()[65]
        pen = BoundsPen(glyphSet)
        glyphSet[composite].draw(pen)
        assert pen.bounds == (600, 0, 800, 200)
        assert len(font["VARC"].table.Coverage.glyphs) == 2

    def test_varComposite_condition_varidx(self):
        fontpath = self.getpath("..", "..", "ttLib", "data", "varc-ac00-ac01.ttf")
        font = TTFont(fontpath)
        varc = font["VARC"].table

        def makeCondition(varIdx):
            condition = ot.ConditionTable()
            condition.Format = 2
            condition.DefaultValue = 0
            condition.VarIdx = varIdx
            return condition

        unusedCondition = makeCondition(5)
        negatedCondition = ot.ConditionTable()
        negatedCondition.Format = 5
        negatedCondition.ConditionTable = makeCondition(4)
        usedCondition = ot.ConditionTable()
        usedCondition.Format = 3
        negatedNull = ot.ConditionTable()
        negatedNull.Format = 5
        negatedNull.ConditionTable = None
        usedCondition.ConditionTable = [
            None,
            makeCondition(6),
            negatedCondition,
            negatedNull,
        ]

        conditionList = ot.ConditionList()
        conditionList.ConditionTable = [unusedCondition, usedCondition, None]
        varc.ConditionList = conditionList
        varc.VarCompositeGlyphs.VarCompositeGlyph[0].components[0].conditionIndex = 1
        varc.VarCompositeGlyphs.VarCompositeGlyph[0].components[1].conditionIndex = 2

        inputpath = self.temp_path(".ttf")
        font.save(inputpath)
        subsetpath = self.temp_path(".ttf")
        subset.main([inputpath, "--unicodes=ac00", "--output-file=%s" % subsetpath])

        subsetfont = TTFont(subsetpath)
        varc = subsetfont["VARC"].table
        assert len(varc.ConditionList.ConditionTable) == 2
        assert varc.ConditionList.ConditionTable[1] is None
        condition = varc.ConditionList.ConditionTable[0]
        assert condition.ConditionTable[0] is None
        assert condition.ConditionTable[1].VarIdx == 3
        assert condition.ConditionTable[2].ConditionTable.VarIdx == 2
        assert condition.ConditionTable[3].ConditionTable is None
        assert len(varc.MultiVarStore.MultiVarData) == 1
        assert len(varc.MultiVarStore.MultiVarData[0].Item) == 4

    def test_varComposite_drops_empty_auxiliary_data(self):
        fontpath = self.getpath("..", "..", "ttLib", "data", "varc-ac00-ac01.ttf")
        font = TTFont(fontpath)
        varc = font["VARC"].table
        for glyph in varc.VarCompositeGlyphs.VarCompositeGlyph:
            for component in glyph.components:
                component.axisIndicesIndex = None
                component.axisValues = ()
                component.axisValuesVarIndex = ot.NO_VARIATION_INDEX
                component.transformVarIndex = ot.NO_VARIATION_INDEX

        conditionList = ot.ConditionList()
        condition = ot.ConditionTable()
        condition.Format = 1
        condition.AxisIndex = 0
        condition.FilterRangeMinValue = 0
        condition.FilterRangeMaxValue = 1
        conditionList.ConditionTable = [condition]
        varc.ConditionList = conditionList

        inputpath = self.temp_path(".ttf")
        font.save(inputpath)
        subsetpath = self.temp_path(".ttf")
        subset.main([inputpath, "--unicodes=ac00", "--output-file=%s" % subsetpath])

        varc = TTFont(subsetpath)["VARC"].table
        assert varc.MultiVarStore is None
        assert varc.ConditionList is None
        assert varc.AxisIndicesList is None

    def test_timing_publishes_parts(self):
        fontpath = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")

        options = subset.Options()
        options.timing = True
        subsetter = subset.Subsetter(options)
        subsetter.populate(text="ABC")
        font = TTFont(fontpath)
        with CapturingLogHandler("fontTools.subset.timer", logging.DEBUG) as captor:
            subsetter.subset(font)
        logs = captor.records

        assert len(logs) > 5
        assert len(logs) == len(
            [l for l in logs if "msg" in l.args and "time" in l.args]
        )
        # Look for a few things we know should happen
        assert filter(lambda l: l.args["msg"] == "load 'cmap'", logs)
        assert filter(lambda l: l.args["msg"] == "subset 'cmap'", logs)
        assert filter(lambda l: l.args["msg"] == "subset 'glyf'", logs)

    def test_passthrough_tables(self):
        fontpath = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")
        font = TTFont(fontpath)
        unknown_tag = "ZZZZ"
        unknown_table = newTable(unknown_tag)
        unknown_table.data = b"\0" * 10
        font[unknown_tag] = unknown_table
        font.save(fontpath)

        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)

        # tables we can't subset are dropped by default
        assert unknown_tag not in subsetfont

        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--passthrough-tables", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)

        # unknown tables are kept if --passthrough-tables option is passed
        assert unknown_tag in subsetfont

    def test_non_BMP_text_arg_input(self):
        fontpath = self.compile_font(
            self.getpath("TestTTF-Regular_non_BMP_char.ttx"), ".ttf"
        )
        subsetpath = self.temp_path(".ttf")
        text = tostr("A\U0001f6d2", encoding="utf-8")

        subset.main([fontpath, "--text=%s" % text, "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)

        assert subsetfont["maxp"].numGlyphs == 3
        assert subsetfont.getGlyphOrder() == [".notdef", "A", "u1F6D2"]

    def test_non_BMP_text_file_input(self):
        fontpath = self.compile_font(
            self.getpath("TestTTF-Regular_non_BMP_char.ttx"), ".ttf"
        )
        subsetpath = self.temp_path(".ttf")
        text = tobytes("A\U0001f6d2", encoding="utf-8")
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(text)

        try:
            subset.main(
                [fontpath, "--text-file=%s" % tmp.name, "--output-file=%s" % subsetpath]
            )
            subsetfont = TTFont(subsetpath)
        finally:
            os.remove(tmp.name)

        assert subsetfont["maxp"].numGlyphs == 3
        assert subsetfont.getGlyphOrder() == [".notdef", "A", "u1F6D2"]

    def test_no_hinting_CFF(self):
        ttxpath = self.getpath("Lobster.subset.ttx")
        fontpath = self.compile_font(ttxpath, ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--no-hinting",
                "--notdef-outline",
                "--output-file=%s" % subsetpath,
                "*",
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("expect_no_hinting_CFF.ttx"), ["CFF "])

    def test_desubroutinize_CFF(self):
        ttxpath = self.getpath("Lobster.subset.ttx")
        fontpath = self.compile_font(ttxpath, ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--desubroutinize",
                "--notdef-outline",
                "--output-file=%s" % subsetpath,
                "*",
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("expect_desubroutinize_CFF.ttx"), ["CFF "]
        )

    def test_desubroutinize_hinted_subrs_CFF(self):
        ttxpath = self.getpath("test_hinted_subrs_CFF.ttx")
        fontpath = self.compile_font(ttxpath, ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--desubroutinize",
                "--notdef-outline",
                "--output-file=%s" % subsetpath,
                "*",
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("test_hinted_subrs_CFF.desub.ttx"), ["CFF "]
        )

    def test_desubroutinize_cntrmask_CFF(self):
        ttxpath = self.getpath("test_cntrmask_CFF.ttx")
        fontpath = self.compile_font(ttxpath, ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--desubroutinize",
                "--notdef-outline",
                "--output-file=%s" % subsetpath,
                "*",
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("test_cntrmask_CFF.desub.ttx"), ["CFF "]
        )

    def test_no_hinting_desubroutinize_CFF(self):
        ttxpath = self.getpath("test_hinted_subrs_CFF.ttx")
        fontpath = self.compile_font(ttxpath, ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--no-hinting",
                "--desubroutinize",
                "--notdef-outline",
                "--output-file=%s" % subsetpath,
                "*",
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont,
            self.getpath("expect_no_hinting_desubroutinize_CFF.ttx"),
            ["CFF "],
        )

    def test_no_hinting_TTF(self):
        fontpath = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [
                fontpath,
                "--no-hinting",
                "--notdef-outline",
                "--output-file=%s" % subsetpath,
                "*",
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("expect_no_hinting_TTF.ttx"), ["glyf", "maxp"]
        )
        for tag in subset.Options().hinting_tables:
            assert tag not in subsetfont

    def test_notdef_width_cid(self):
        # https://github.com/fonttools/fonttools/pull/845
        fontpath = self.compile_font(self.getpath("NotdefWidthCID-Regular.ttx"), ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--no-notdef-outline",
                "--gids=0,1",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("expect_notdef_width_cid.ttx"), ["CFF "]
        )

    def test_recalc_bounds_ttf(self):
        ttxpath = self.getpath("TestTTF-Regular.ttx")
        font = TTFont()
        font.importXML(ttxpath)
        head = font["head"]
        bounds = [head.xMin, head.yMin, head.xMax, head.yMax]

        fontpath = self.compile_font(ttxpath, ".ttf")
        subsetpath = self.temp_path(".ttf")

        # by default, the subsetter does not recalculate the bounding box
        subset.main([fontpath, "--output-file=%s" % subsetpath, "*"])
        head = TTFont(subsetpath)["head"]
        assert bounds == [head.xMin, head.yMin, head.xMax, head.yMax]

        subset.main([fontpath, "--recalc-bounds", "--output-file=%s" % subsetpath, "*"])
        head = TTFont(subsetpath)["head"]
        bounds = [132, 304, 365, 567]
        assert bounds == [head.xMin, head.yMin, head.xMax, head.yMax]

    def test_recalc_bounds_otf(self):
        ttxpath = self.getpath("TestOTF-Regular.ttx")
        font = TTFont()
        font.importXML(ttxpath)
        head = font["head"]
        bounds = [head.xMin, head.yMin, head.xMax, head.yMax]

        fontpath = self.compile_font(ttxpath, ".otf")
        subsetpath = self.temp_path(".otf")

        # by default, the subsetter does not recalculate the bounding box
        subset.main([fontpath, "--output-file=%s" % subsetpath, "*"])
        head = TTFont(subsetpath)["head"]
        assert bounds == [head.xMin, head.yMin, head.xMax, head.yMax]

        subset.main([fontpath, "--recalc-bounds", "--output-file=%s" % subsetpath, "*"])
        head = TTFont(subsetpath)["head"]
        bounds = [132, 304, 365, 567]
        assert bounds == [head.xMin, head.yMin, head.xMax, head.yMax]

    def test_recalc_timestamp_ttf(self):
        ttxpath = self.getpath("TestTTF-Regular.ttx")
        font = TTFont()
        font.importXML(ttxpath)
        modified = font["head"].modified
        fontpath = self.compile_font(ttxpath, ".ttf")
        subsetpath = self.temp_path(".ttf")

        # by default, the subsetter does not recalculate the modified timestamp
        subset.main([fontpath, "--output-file=%s" % subsetpath, "*"])
        assert modified == TTFont(subsetpath)["head"].modified

        subset.main(
            [fontpath, "--recalc-timestamp", "--output-file=%s" % subsetpath, "*"]
        )
        assert modified < TTFont(subsetpath)["head"].modified

    def test_recalc_timestamp_otf(self):
        ttxpath = self.getpath("TestOTF-Regular.ttx")
        font = TTFont()
        font.importXML(ttxpath)
        modified = font["head"].modified
        fontpath = self.compile_font(ttxpath, ".otf")
        subsetpath = self.temp_path(".otf")

        # by default, the subsetter does not recalculate the modified timestamp
        subset.main([fontpath, "--output-file=%s" % subsetpath, "*"])
        assert modified == TTFont(subsetpath)["head"].modified

        subset.main(
            [fontpath, "--recalc-timestamp", "--output-file=%s" % subsetpath, "*"]
        )
        assert modified < TTFont(subsetpath)["head"].modified

    def test_recalc_max_context(self):
        ttxpath = self.getpath("Lobster.subset.ttx")
        font = TTFont()
        font.importXML(ttxpath)
        max_context = font["OS/2"].usMaxContext
        fontpath = self.compile_font(ttxpath, ".otf")
        subsetpath = self.temp_path(".otf")

        # by default, the subsetter does not recalculate the usMaxContext
        subset.main(
            [fontpath, "--drop-tables+=GSUB,GPOS", "--output-file=%s" % subsetpath]
        )
        assert max_context == TTFont(subsetpath)["OS/2"].usMaxContext

        subset.main(
            [
                fontpath,
                "--recalc-max-context",
                "--drop-tables+=GSUB,GPOS",
                "--output-file=%s" % subsetpath,
            ]
        )
        assert 0 == TTFont(subsetpath)["OS/2"].usMaxContext

    def test_retain_gids_ttf(self):
        fontpath = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")
        font = TTFont(fontpath)

        assert font["hmtx"]["A"] == (500, 132)
        assert font["hmtx"]["B"] == (400, 132)

        assert font["glyf"]["A"].numberOfContours > 0
        assert font["glyf"]["B"].numberOfContours > 0

        subsetpath = self.temp_path(".ttf")
        subset.main(
            [
                fontpath,
                "--retain-gids",
                "--output-file=%s" % subsetpath,
                "--glyph-names",
                "B",
            ]
        )
        subsetfont = TTFont(subsetpath)

        assert subsetfont.getGlyphOrder() == font.getGlyphOrder()[0:3]

        hmtx = subsetfont["hmtx"]
        assert hmtx["A"] == (0, 0)
        assert hmtx["B"] == (400, 132)

        glyf = subsetfont["glyf"]
        assert glyf["A"].numberOfContours == 0
        assert glyf["B"].numberOfContours > 0

    def test_retain_gids_cff(self):
        fontpath = self.compile_font(self.getpath("TestOTF-Regular.ttx"), ".otf")
        font = TTFont(fontpath)

        assert font["hmtx"]["A"] == (500, 132)
        assert font["hmtx"]["B"] == (400, 132)
        assert font["hmtx"]["C"] == (500, 0)

        font["CFF "].cff[0].decompileAllCharStrings()
        cs = font["CFF "].cff[0].CharStrings
        assert len(cs["A"].program) > 0
        assert len(cs["B"].program) > 0
        assert len(cs["C"].program) > 0

        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--retain-gids",
                "--output-file=%s" % subsetpath,
                "--glyph-names",
                "B",
            ]
        )
        subsetfont = TTFont(subsetpath)

        assert subsetfont.getGlyphOrder() == font.getGlyphOrder()[0:3]

        hmtx = subsetfont["hmtx"]
        assert hmtx["A"] == (0, 0)
        assert hmtx["B"] == (400, 132)

        subsetfont["CFF "].cff[0].decompileAllCharStrings()
        cs = subsetfont["CFF "].cff[0].CharStrings

        assert cs["A"].program == ["endchar"]
        assert len(cs["B"].program) > 0

    def test_retain_gids_cff2(self):
        ttx_path = self.getpath(
            "../../varLib/data/master_ttx_varfont_otf/TestCFF2VF.ttx"
        )
        fontpath = self.compile_font(ttx_path, ".otf")
        font = TTFont(fontpath)

        assert font["hmtx"]["A"] == (600, 31)
        assert font["hmtx"]["T"] == (600, 41)

        font["CFF2"].cff[0].decompileAllCharStrings()
        cs = font["CFF2"].cff[0].CharStrings
        assert len(cs["A"].program) > 0
        assert len(cs["T"].program) > 0

        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--retain-gids",
                "--output-file=%s" % subsetpath,
                "T",
            ]
        )
        subsetfont = TTFont(subsetpath)

        assert len(subsetfont.getGlyphOrder()) == len(font.getGlyphOrder()[0:3])

        hmtx = subsetfont["hmtx"]
        assert hmtx["glyph00001"] == (0, 0)
        assert hmtx["T"] == (600, 41)

        subsetfont["CFF2"].cff[0].decompileAllCharStrings()
        cs = subsetfont["CFF2"].cff[0].CharStrings
        assert cs["glyph00001"].program == []
        assert len(cs["T"].program) > 0

    def test_HVAR_VVAR(self):
        fontpath = self.compile_font(self.getpath("TestHVVAR.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--text=BD", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont,
            self.getpath("expect_HVVAR.ttx"),
            ["GlyphOrder", "HVAR", "VVAR", "avar", "fvar"],
        )

    def test_HVAR_VVAR_retain_gids(self):
        fontpath = self.compile_font(self.getpath("TestHVVAR.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main(
            [fontpath, "--text=BD", "--retain-gids", "--output-file=%s" % subsetpath]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont,
            self.getpath("expect_HVVAR_retain_gids.ttx"),
            ["GlyphOrder", "HVAR", "VVAR", "avar", "fvar"],
        )

    def test_subset_flavor_woff(self):
        fontpath = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")
        woff_path = self.temp_path(".woff")

        subset.main(
            [
                fontpath,
                "*",
                "--flavor=woff",
                "--output-file=%s" % woff_path,
            ]
        )
        woff = TTFont(woff_path)

        assert woff.flavor == "woff"

    def test_subset_flavor_woff2(self):
        # skip if brotli is not importable, required for woff2
        pytest.importorskip("brotli")

        fontpath = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")
        woff2_path = self.temp_path(".woff2")

        subset.main(
            [
                fontpath,
                "*",
                "--flavor=woff2",
                "--output-file=%s" % woff2_path,
            ]
        )
        woff2 = TTFont(woff2_path)

        assert woff2.flavor == "woff2"

    def test_subset_flavor_none(self):
        fontpath = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")
        ttf_path = self.temp_path(".ttf")

        subset.main(
            [
                fontpath,
                "*",
                "--output-file=%s" % ttf_path,
            ]
        )
        ttf = TTFont(ttf_path)

        assert ttf.flavor is None

    @pytest.mark.parametrize("flavor", ["woff", "woff2"])
    def test_subset_inherits_flavor(self, flavor):
        if flavor == "woff2":
            pytest.importorskip("brotli")

        ttf_path = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")
        input_path = self.temp_path(f".{flavor}")
        font = TTFont(ttf_path)
        font.flavor = flavor
        font.save(input_path)

        subset.main([input_path, "*"])
        output_path = os.path.splitext(input_path)[0] + f".subset.{flavor}"

        assert TTFont(output_path).flavor == flavor

    @pytest.mark.parametrize("token", ["none", "None", "NONE", ""])
    @pytest.mark.parametrize("flavor", ["woff", "woff2"])
    def test_subset_flavor_none_from_woff(self, token, flavor):
        if flavor == "woff2":
            pytest.importorskip("brotli")

        ttf_path = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")
        input_path = self.temp_path(f".{flavor}")
        font = TTFont(ttf_path)
        font.flavor = flavor
        font.save(input_path)

        subset.main([input_path, "*", f"--flavor={token}"])
        output_path = os.path.splitext(input_path)[0] + ".subset.ttf"

        assert os.path.isfile(output_path)
        assert TTFont(output_path).flavor is None

    def test_subset_flavor_none_from_cff_woff_uses_otf_extension(self):
        otf_path = self.compile_font(self.getpath("TestOTF-Regular.ttx"), ".otf")
        input_path = self.temp_path(".woff")
        font = TTFont(otf_path)
        font.flavor = "woff"
        font.save(input_path)

        subset.main([input_path, "*", "--flavor=none"])
        output_path = os.path.splitext(input_path)[0] + ".subset.otf"

        assert os.path.isfile(output_path)
        out = TTFont(output_path)
        assert out.flavor is None
        assert out.sfntVersion == "OTTO"

    def test_subset_flavor_invalid(self, capsys):
        fontpath = self.compile_font(self.getpath("TestTTF-Regular.ttx"), ".ttf")

        rc = subset.main([fontpath, "*", "--flavor=ttf"])

        assert rc == 2
        err = capsys.readouterr().err
        assert "Invalid --flavor" in err

    def test_subset_context_subst_format_3(self):
        # https://github.com/fonttools/fonttools/issues/1879
        # Test font contains 'calt' feature with Format 3 ContextSubst lookup subtables
        ttx = self.getpath("TestContextSubstFormat3.ttx")
        fontpath = self.compile_font(ttx, ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--unicodes=*", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        # check all glyphs are kept via GSUB closure, no changes expected
        self.expect_ttx(subsetfont, ttx)

    def test_cmap_prune_format12(self):
        fontpath = self.compile_font(self.getpath("CmapSubsetTest.ttx"), ".ttf")
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "--glyphs=a", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("CmapSubsetTest.subset.ttx"), ["cmap"])

    def test_cmap_format14(self):
        fontpath = self.compile_font(self.getpath("cmap14_font1.ttx"), ".otf")
        subsetpath = self.temp_path(".otf")

        subset.main([fontpath, "--unicodes=4e05", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("cmap14_font1.no_uvs.ttx"), ["cmap"])

        subset.main(
            [fontpath, "--unicodes=4e05,e0100", "--output-file=%s" % subsetpath]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, self.getpath("cmap14_font1.uvs.ttx"), ["cmap"])

        subset.main([fontpath, "--unicodes=4e10", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("cmap14_font1.no_uvs_non_default.ttx"), ["cmap"]
        )

        subset.main(
            [fontpath, "--unicodes=4e10,e0100", "--output-file=%s" % subsetpath]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont, self.getpath("cmap14_font1.uvs_non_default.ttx"), ["cmap"]
        )

    @pytest.mark.parametrize("cmap_format", [14, 15])
    @pytest.mark.parametrize("unicodes", [[0x4E05], [0x4E05, 0xE0100]])
    def test_retain_all_variation_sequences(self, cmap_format, unicodes):
        fontpath = self.compile_font(self.getpath("cmap14_font1.ttx"), ".otf")
        font = TTFont(fontpath)
        old_table = next(t for t in font["cmap"].tables if t.format == 14)
        table = CmapSubtable.newSubtable(cmap_format)
        table.platformID = old_table.platformID
        table.platEncID = old_table.platEncID
        table.language = old_table.language
        table.cmap = {}
        table.uvsDict = old_table.uvsDict
        table.uvsDict[0xFE00] = [(0x4E05, "g14"), (0x4E06, "g16")]
        table.uvsDict[0xE0101] = [(0x4E05, "g13"), (0x4E06, "g16")]
        font["cmap"].tables[font["cmap"].tables.index(old_table)] = table

        options = subset.Options()
        options.glyph_names = True
        options.retain_all_variation_sequences = True
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=unicodes)
        subsetter.subset(font)

        stream = io.BytesIO()
        font.save(stream)
        font = TTFont(io.BytesIO(stream.getvalue()))
        assert font.getBestCmap() == {0x4E05: "g15"}
        assert font.getGlyphOrder() == [".notdef", "g13", "g14", "g15"]
        table = next(t for t in font["cmap"].tables if t.format == cmap_format)
        assert table.uvsDict == {
            0xFE00: [(0x4E05, "g14")],
            0xE0100: [(0x4E05, None)],
            0xE0101: [(0x4E05, "g13")],
        }

    def test_cmap_format15(self):
        fontpath = self.compile_font(self.getpath("cmap14_font1.ttx"), ".otf")
        inputpath = self.temp_path(".otf")
        subsetpath = self.temp_path(".otf")

        font = TTFont(fontpath)
        cmap14 = next(t for t in font["cmap"].tables if t.format == 14)
        cmap15 = CmapSubtable.newSubtable(15)
        cmap15.platformID = cmap14.platformID
        cmap15.platEncID = cmap14.platEncID
        cmap15.language = cmap14.language
        cmap15.cmap = {}
        cmap15.uvsDict = cmap14.uvsDict
        font["cmap"].tables[font["cmap"].tables.index(cmap14)] = cmap15
        font.save(inputpath)

        subset.main(
            [inputpath, "--unicodes=4e10,e0100", "--output-file=%s" % subsetpath]
        )
        subsetfont = TTFont(subsetpath)
        cmap15 = next(t for t in subsetfont["cmap"].tables if t.format == 15)

        assert cmap15.uvsDict == {0xE0100: [(0x4E10, "g25")]}

    def test_DMAP_precedes_cmap(self):
        glyph_order = [
            ".notdef",
            "cmapA",
            "dmapA",
            "baseB",
            "cmapB.var",
            "dmapB.var",
        ]
        fb = FontBuilder(1024, isTTF=True)
        fb.setupGlyphOrder(glyph_order)
        fb.setupCharacterMap(
            {0x41: "cmapA", 0x42: "baseB"},
            uvs=[(0x42, 0xFE00, "cmapB.var")],
        )
        fb.setupGlyf({name: Glyph() for name in glyph_order})
        fb.setupHorizontalMetrics({name: (500, 0) for name in glyph_order})
        fb.setupHorizontalHeader()
        fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
        fb.setupOS2()
        fb.setupPost()

        dmap4 = CmapSubtable.newSubtable(4)
        dmap4.platformID = 3
        dmap4.platEncID = 1
        dmap4.language = 0
        dmap4.cmap = {0x41: "dmapA"}
        dmap14 = CmapSubtable.newSubtable(14)
        dmap14.platformID = 0
        dmap14.platEncID = 5
        dmap14.language = 0xFF
        dmap14.cmap = {}
        dmap14.uvsDict = {0xFE00: [(0x42, "dmapB.var")]}
        fb.font["DMAP"] = newTable("DMAP")
        fb.font["DMAP"].tableVersion = 0
        fb.font["DMAP"].tables = [dmap4, dmap14]

        subsetter = subset.Subsetter()
        subsetter.populate(unicodes=[0x41, 0x42, 0xFE00])
        subsetter.subset(fb.font)

        assert fb.font.getGlyphOrder() == [
            ".notdef",
            "dmapA",
            "baseB",
            "dmapB.var",
        ]
        assert fb.font["cmap"].getBestCmap() == {0x42: "baseB"}
        assert not any(t.format in (14, 15) for t in fb.font["cmap"].tables)
        assert fb.font["DMAP"].getBestCmap() == {0x41: "dmapA"}
        assert next(
            t for t in fb.font["DMAP"].tables if t.format in (14, 15)
        ).uvsDict == {0xFE00: [(0x42, "dmapB.var")]}

        data = io.BytesIO()
        fb.font.save(data)
        data.seek(0)
        font = TTFont(data)
        assert font.getBestCmap() == {0x41: "A", 0x42: "B"}
        assert font.getGlyphID(font.getBestCmap()[0x41]) == 1
        assert font.getGlyphID(font.getBestCmap()[0x42]) == 2

    @pytest.mark.parametrize("notdef_glyph", [False, True])
    @pytest.mark.parametrize("from_xml", [False, True])
    @pytest.mark.parametrize("glyph_zero", [".notdef", "zero"])
    @pytest.mark.parametrize("dmap_format", [4, 12, 13])
    def test_DMAP_nominal_zero_fallback(
        self, dmap_format, glyph_zero, from_xml, notdef_glyph
    ):
        order = [glyph_zero, "baseA", "baseB", "dmapB"]
        fb = FontBuilder(1024)
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap({0x41: "baseA", 0x42: "baseB"})
        fb.setupGlyf({name: Glyph() for name in order})
        fb.setupHorizontalMetrics({name: (500, 0) for name in order})
        fb.setupHorizontalHeader()
        fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
        fb.setupOS2()
        fb.setupPost()
        table = CmapSubtable.newSubtable(dmap_format)
        table.platformID = 3
        table.platEncID = 1 if dmap_format == 4 else 10
        table.language = 0
        table.cmap = {0x41: glyph_zero, 0x42: "dmapB"}
        font = fb.font
        font["DMAP"] = newTable("DMAP")
        font["DMAP"].tableVersion = 0
        font["DMAP"].tables = [table]
        if from_xml:
            data = io.BytesIO()
            font.save(data)
            font = TTFont(io.BytesIO(data.getvalue()))
            font["DMAP"].tables[0].cmap[0x41] = glyph_zero
            stream = io.StringIO()
            font.saveXML(stream)
            stream.seek(0)
            font = TTFont()
            font.importXML(stream)

        options = subset.Options()
        options.glyph_names = True
        options.notdef_glyph = notdef_glyph
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=[0x41, 0x42])
        subsetter.subset(font)
        assert font.getGlyphOrder() == ([glyph_zero] if notdef_glyph else []) + [
            "baseA",
            "dmapB",
        ]
        assert font.getBestCmap() == {0x41: "baseA", 0x42: "dmapB"}
        assert font["DMAP"].getBestCmap() == {0x42: "dmapB"}
        stream = io.BytesIO()
        font.save(stream)
        reloaded = TTFont(io.BytesIO(stream.getvalue()))
        # Without .notdef, baseA becomes glyph zero and binary cmap omits it.
        assert reloaded.getBestCmap() == (
            font.getBestCmap() if notdef_glyph else {0x42: "dmapB"}
        )

    @pytest.mark.parametrize("unicodes", [[0x41, 0x42], [0x42]])
    def test_DMAP_multiple_unicode_subtables(self, unicodes):
        glyph_order = [".notdef", "baseA", "baseB", "dmapA", "dmapB"]
        fb = FontBuilder(1024, isTTF=True)
        fb.setupGlyphOrder(glyph_order)
        fb.setupCharacterMap({0x41: "baseA", 0x42: "baseB"})
        fb.setupGlyf({name: Glyph() for name in glyph_order})
        fb.setupHorizontalMetrics({name: (500, 0) for name in glyph_order})
        fb.setupHorizontalHeader()
        fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
        fb.setupOS2()
        fb.setupPost()

        dmap12 = CmapSubtable.newSubtable(12)
        dmap12.platformID = 3
        dmap12.platEncID = 10
        dmap12.language = 0
        dmap12.cmap = {0x41: "dmapA"}
        dmap4 = CmapSubtable.newSubtable(4)
        dmap4.platformID = 3
        dmap4.platEncID = 1
        dmap4.language = 0
        dmap4.cmap = {0x42: "dmapB"}
        fb.font["DMAP"] = newTable("DMAP")
        fb.font["DMAP"].tableVersion = 0
        fb.font["DMAP"].tables = [dmap12, dmap4]

        stream = io.BytesIO()
        fb.font.save(stream)
        font = TTFont(io.BytesIO(stream.getvalue()))
        preferences = [[(3, 10), (3, 1)], [(3, 1)]]
        expected = [
            {u: g for u, g in font.getBestCmap(p).items() if u in unicodes}
            for p in preferences
        ]

        options = subset.Options()
        options.glyph_names = True
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(unicodes=unicodes)
        subsetter.subset(font)

        stream = io.BytesIO()
        font.save(stream)
        font = TTFont(io.BytesIO(stream.getvalue()))
        assert [font.getBestCmap(p) for p in preferences] == expected

    @pytest.mark.parametrize("retain_all_variation_sequences", [False, True])
    @pytest.mark.parametrize("cmap_format", [14, 15])
    @pytest.mark.parametrize("dmap_format", [14, 15])
    @pytest.mark.parametrize("glyph_zero", [".notdef", "zero"])
    @pytest.mark.parametrize("dmap_mapping", ["zero", "default", "nonzero"])
    def test_DMAP_UVS_fallback(
        self,
        cmap_format,
        dmap_format,
        glyph_zero,
        dmap_mapping,
        retain_all_variation_sequences,
    ):
        glyph_order = [glyph_zero, "baseA", "cmapA.var", "dmapA.var"]
        fb = FontBuilder(1024, isTTF=True)
        fb.setupGlyphOrder(glyph_order)
        fb.setupCharacterMap({0x41: "baseA"})
        fb.setupGlyf({name: Glyph() for name in glyph_order})
        fb.setupHorizontalMetrics({name: (500, 0) for name in glyph_order})
        fb.setupHorizontalHeader()
        fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
        fb.setupOS2()
        fb.setupPost()

        def uvs_table(format, glyph):
            table = CmapSubtable.newSubtable(format)
            table.platformID = 0
            table.platEncID = 5
            table.language = 0xFF
            table.cmap = {}
            table.uvsDict = {0xFE00: [(0x41, glyph)]}
            return table

        dmap_glyph = {
            "zero": glyph_zero,
            "default": None,
            "nonzero": "dmapA.var",
        }[dmap_mapping]
        fb.font["cmap"].tables.append(uvs_table(cmap_format, "cmapA.var"))
        fb.font["DMAP"] = newTable("DMAP")
        fb.font["DMAP"].tableVersion = 0
        fb.font["DMAP"].tables = [uvs_table(dmap_format, dmap_glyph)]

        stream = io.BytesIO()
        fb.font.save(stream)
        font = TTFont(io.BytesIO(stream.getvalue()))
        options = subset.Options()
        options.glyph_names = True
        options.retain_all_variation_sequences = retain_all_variation_sequences
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(
            unicodes=[0x41] if retain_all_variation_sequences else [0x41, 0xFE00]
        )
        subsetter.subset(font)

        expected_glyphs = [glyph_zero, "baseA"]
        if dmap_mapping == "zero":
            expected_glyphs.append("cmapA.var")
        elif dmap_mapping == "nonzero":
            expected_glyphs.append("dmapA.var")
        assert font.getGlyphOrder() == expected_glyphs

        stream = io.BytesIO()
        font.save(stream)
        font = TTFont(io.BytesIO(stream.getvalue()))
        assert font.getGlyphOrder() == expected_glyphs
        cmap_uvs = [t for t in font["cmap"].tables if t.format in (14, 15)]
        if dmap_mapping == "zero":
            assert len(cmap_uvs) == 1
            assert cmap_uvs[0].uvsDict == {0xFE00: [(0x41, "cmapA.var")]}
        else:
            assert not cmap_uvs
        assert font["DMAP"].tables[0].uvsDict == {0xFE00: [(0x41, dmap_glyph)]}

    @pytest.mark.parametrize("text, n", [("!", 1), ("#", 2)])
    def test_GPOS_PairPos_Format2_useClass0(self, text, n):
        # Check two things related to class 0 ('every other glyph'):
        # 1) that it's reused for ClassDef1 when it becomes empty as the subset glyphset
        #    is intersected with the table's Coverage
        # 2) that it is never reused for ClassDef2 even when it happens to become empty
        #    because of the subset glyphset. In this case, we don't keep a PairPosClass2
        #    subtable if only ClassDef2's class0 survived subsetting.
        # The test font (from Harfbuzz test suite) is constructed to trigger these two
        # situations depending on the input subset --text.
        # https://github.com/fonttools/fonttools/pull/2221
        fontpath = self.compile_font(
            self.getpath("GPOS_PairPos_Format2_PR_2221.ttx"), ".ttf"
        )
        subsetpath = self.temp_path(".ttf")

        expected_ttx = self.getpath(
            f"GPOS_PairPos_Format2_ClassDef{n}_useClass0.subset.ttx"
        )
        subset.main(
            [
                fontpath,
                f"--text='{text}'",
                "--layout-features+=test",
                "--output-file=%s" % subsetpath,
            ]
        )
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(subsetfont, expected_ttx, ["GPOS"])

    def test_GPOS_SinglePos_prune_post_subset_no_value(self):
        fontpath = self.compile_font(
            self.getpath("GPOS_SinglePos_no_value_issue_2312.ttx"), ".ttf"
        )
        subsetpath = self.temp_path(".ttf")
        subset.main([fontpath, "*", "--glyph-names", "--output-file=%s" % subsetpath])
        subsetfont = TTFont(subsetpath)
        self.expect_ttx(
            subsetfont,
            self.getpath("GPOS_SinglePos_no_value_issue_2312.subset.ttx"),
            ["GlyphOrder", "GPOS"],
        )

    @pytest.mark.parametrize(
        "installed, enabled, ok",
        [
            pytest.param(True, None, True, id="installed-auto-ok"),
            pytest.param(True, None, False, id="installed-auto-fail"),
            pytest.param(True, True, True, id="installed-enabled-ok"),
            pytest.param(True, True, False, id="installed-enabled-fail"),
            pytest.param(True, False, True, id="installed-disabled"),
            pytest.param(False, True, True, id="not_installed-enabled"),
            pytest.param(False, False, True, id="not_installed-disabled"),
        ],
    )
    def test_harfbuzz_repacker(self, caplog, monkeypatch, installed, enabled, ok):
        # Use a mock to test the pure-python serializer is used when uharfbuzz
        # returns an error or is not installed
        have_uharfbuzz = fontTools.ttLib.tables.otBase.have_uharfbuzz
        if installed:
            if not have_uharfbuzz:
                pytest.skip("uharfbuzz is not installed")
            if not ok:
                # pretend hb.serialize_with_tag return an error
                import uharfbuzz as hb

                def mock_serialize_with_tag(tag, data, obj_list):
                    raise hb.RepackerError("mocking")

                monkeypatch.setattr(hb, "serialize_with_tag", mock_serialize_with_tag)
        else:
            if have_uharfbuzz:
                # pretend uharfbuzz is not installed
                monkeypatch.setattr(
                    fontTools.ttLib.tables.otBase, "have_uharfbuzz", False
                )

        fontpath = self.compile_font(self.getpath("harfbuzz_repacker.ttx"), ".otf")
        subsetpath = self.temp_path(".otf")
        args = [
            fontpath,
            "--unicodes=0x53a9",
            "--layout-features=*",
            f"--output-file={subsetpath}",
        ]
        if enabled is True:
            args.append("--harfbuzz-repacker")
        elif enabled is False:
            args.append("--no-harfbuzz-repacker")
        # elif enabled is None: ... is the default

        if enabled is True and not installed:
            # raise if enabled but not installed
            with pytest.raises(ImportError, match="uharfbuzz"):
                subset.main(args)
            return

        with caplog.at_level(logging.DEBUG, "fontTools.ttLib.tables.otBase"):
            subset.main(args)

        subsetfont = TTFont(subsetpath)
        # both hb.repack and pure-python serializer compile to the same ttx
        self.expect_ttx(
            subsetfont, self.getpath("expect_harfbuzz_repacker.ttx"), ["GSUB"]
        )

        if enabled or enabled is None:
            if installed:
                assert "serializing 'GSUB' with hb.repack" in caplog.text

        if enabled is None and not installed:
            assert (
                "uharfbuzz not found, compiling 'GSUB' with pure-python serializer"
            ) in caplog.text

        if enabled is False:
            assert (
                "hb.repack disabled, compiling 'GSUB' with pure-python serializer"
            ) in caplog.text

        # test we emit a log.error if hb.repack fails (and we don't if successful)
        assert (
            (
                "hb.repack failed to serialize 'GSUB', attempting fonttools resolutions "
                "; the error message was: RepackerError: mocking"
            )
            in caplog.text
        ) ^ ok

    def test_retain_east_asian_spacing_features(self):
        # This test font contains halt and vhal features, check that
        # they are retained by default after subsetting.
        ttx_path = self.getpath("NotoSansCJKjp-Regular.subset.ttx")
        ttx = pathlib.Path(ttx_path).read_text()
        assert 'FeatureTag value="halt"' in ttx
        assert 'FeatureTag value="vhal"' in ttx

        fontpath = self.compile_font(ttx_path, ".otf")
        subsetpath = self.temp_path(".otf")
        subset.main(
            [
                fontpath,
                "--unicodes=*",
                "--output-file=%s" % subsetpath,
            ]
        )
        # subset output is the same as the input
        self.expect_ttx(TTFont(subsetpath), ttx_path)


@pytest.fixture
def featureVarsTestFont():
    fb = FontBuilder(unitsPerEm=100)
    fb.setupGlyphOrder([".notdef", "f", "f_f", "dollar", "dollar.rvrn"])
    fb.setupCharacterMap({ord("f"): "f", ord("$"): "dollar"})
    fb.setupNameTable({"familyName": "TestFeatureVars", "styleName": "Regular"})
    fb.setupPost()
    fb.setupFvar(axes=[("wght", 100, 400, 900, "Weight")], instances=[])
    fb.addOpenTypeFeatures("""\
        feature dlig {
            sub f f by f_f;
        } dlig;
    """)
    fb.addFeatureVariations(
        [([{"wght": (0.20886, 1.0)}], {"dollar": "dollar.rvrn"})], featureTag="rvrn"
    )
    buf = io.BytesIO()
    fb.save(buf)
    buf.seek(0)

    return TTFont(buf)


def addLookupVariation(font):
    gsub = font["GSUB"].table
    featureIndices = {
        record.FeatureTag: index
        for index, record in enumerate(gsub.FeatureList.FeatureRecord)
    }

    condition = ot.ConditionTable()
    condition.Format = 1
    condition.AxisIndex = 0
    condition.FilterRangeMinValue = 0.25
    condition.FilterRangeMaxValue = 1.0

    lookupIndices = ot.LookupIndexList()
    lookupIndices.LookupIndex = list(
        gsub.FeatureList.FeatureRecord[featureIndices["dlig"]].Feature.LookupListIndex
    )
    lookupIndices.LookupIndexCount = len(lookupIndices.LookupIndex)

    lookupCondition = ot.LookupConditionRecord()
    lookupCondition.ConditionTable = condition
    lookupCondition.LookupIndexList = lookupIndices

    featureLookups = ot.FeatureLookupsTable()
    featureLookups.Version = 0x00010000
    featureLookups.Flags = 1
    featureLookups.LookupConditionRecord = [lookupCondition]
    featureLookups.LookupConditionCount = 1

    lookupVariation = ot.LookupVariationRecord()
    lookupVariation.FeatureIndex = featureIndices["rvrn"]
    lookupVariation.FeatureLookupsTable = featureLookups

    gsub.FeatureVariations.Version = 0x00010001
    gsub.FeatureVariations.LookupVariationRecord = [lookupVariation]
    gsub.FeatureVariations.LookupVariationCount = 1


def test_subset_feature_variations_keep_all(featureVarsTestFont):
    font = featureVarsTestFont

    options = subset.Options()
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord("f"), ord("$")])
    subsetter.subset(font)

    featureTags = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    # 'dlig' is discretionary so it is dropped by default
    assert "dlig" not in featureTags
    assert "f_f" not in font.getGlyphOrder()
    # 'rvrn' is required so it is kept by default
    assert "rvrn" in featureTags
    assert "dollar.rvrn" in font.getGlyphOrder()


def test_subset_feature_variations_drop_all(featureVarsTestFont):
    font = featureVarsTestFont

    options = subset.Options()
    options.layout_features.remove("rvrn")  # drop 'rvrn'
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord("f"), ord("$")])
    subsetter.subset(font)

    featureTags = {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord}
    glyphs = set(font.getGlyphOrder())

    assert "rvrn" not in featureTags
    assert glyphs == {".notdef", "f", "dollar"}
    # all FeatureVariationRecords were dropped
    assert font["GSUB"].table.FeatureVariations is None
    assert font["GSUB"].table.Version == 0x00010000


def test_subset_lookup_variations_remaps_features_and_lookups(featureVarsTestFont):
    font = featureVarsTestFont
    addLookupVariation(font)

    options = subset.Options()
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord("f"), ord("$")])
    subsetter.subset(font)

    gsub = font["GSUB"].table
    featureIndices = {
        record.FeatureTag: index
        for index, record in enumerate(gsub.FeatureList.FeatureRecord)
    }
    assert "dlig" not in featureIndices
    assert "f_f" in font.getGlyphOrder()

    record = gsub.FeatureVariations.LookupVariationRecord[0]
    assert record.FeatureIndex == featureIndices["rvrn"]
    lookupIndices = record.FeatureLookupsTable.LookupConditionRecord[
        0
    ].LookupIndexList.LookupIndex
    assert len(lookupIndices) == 1
    assert lookupIndices[0] < gsub.LookupList.LookupCount

    output = io.BytesIO()
    font.save(output)
    output.seek(0)
    roundtripped = TTFont(output)["GSUB"].table.FeatureVariations
    assert roundtripped.LookupVariationCount == 1
    assert (
        roundtripped.LookupVariationRecord[0].FeatureLookupsTable.LookupConditionCount
        == 1
    )


def test_subset_lookup_variations_keeps_empty_override(featureVarsTestFont):
    font = featureVarsTestFont
    addLookupVariation(font)

    options = subset.Options()
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord("$")])
    subsetter.subset(font)

    variations = font["GSUB"].table.FeatureVariations
    assert variations.LookupVariationCount == 1
    assert (
        variations.LookupVariationRecord[0].FeatureLookupsTable.LookupConditionCount
        == 0
    )


@pytest.mark.parametrize("lookupVariations", [False, True])
@pytest.mark.parametrize("varIdx", [1, 7, 0x10000])
def test_subset_preserves_condition_varstore(
    featureVarsTestFont, lookupVariations, varIdx
):
    from fontTools.varLib.builder import buildVarData, buildVarRegionList, buildVarStore
    from fontTools.varLib.varStore import VarStoreInstancer

    font = featureVarsTestFont
    value = ot.ConditionTable()
    value.Format = 2
    value.DefaultValue = -1
    value.VarIdx = varIdx
    negate = ot.ConditionTable()
    negate.Format = 5
    negate.ConditionTable = value
    condition = ot.ConditionTable()
    condition.Format = 3
    condition.ConditionTable = [None, negate]
    condition.ConditionCount = 2
    variations = font["GSUB"].table.FeatureVariations
    if lookupVariations:
        addLookupVariation(font)
        variations.LookupVariationRecord[0].FeatureLookupsTable.LookupConditionRecord[
            0
        ].ConditionTable = condition
        variations.FeatureVariationRecord = []
        variations.FeatureVariationCount = 0
    else:
        variations.FeatureVariationRecord[0].ConditionSet.ConditionTable = [condition]

    gdef = ot.GDEF()
    gdef.Version = 0x00010003
    gdef.GlyphClassDef = gdef.AttachList = gdef.LigCaretList = None
    gdef.MarkAttachClassDef = gdef.MarkGlyphSetsDef = None
    gdef.VarStore = buildVarStore(
        buildVarRegionList([{"wght": (0, 1, 1)}], ["wght"]),
        [buildVarData([0], [[99], [2]], optimize=False)],
    )
    font["GDEF"] = newTable("GDEF")
    font["GDEF"].table = gdef

    subsetter = subset.Subsetter()
    subsetter.populate(unicodes=[ord("f"), ord("$")])
    subsetter.subset(font)
    if varIdx == 1:
        assert value.VarIdx == 0
        assert font["GDEF"].table.VarStore.VarData[0].Item == [[2]]
    else:
        assert value.VarIdx == ot.NO_VARIATION_INDEX
        assert "GDEF" not in font

    output = io.BytesIO()
    font.save(output)
    output.seek(0)
    roundtripped = TTFont(output)
    variations = roundtripped["GSUB"].table.FeatureVariations
    if lookupVariations:
        condition = (
            variations.LookupVariationRecord[0]
            .FeatureLookupsTable.LookupConditionRecord[0]
            .ConditionTable
        )
    else:
        condition = variations.FeatureVariationRecord[0].ConditionSet.ConditionTable[0]
    value = condition.ConditionTable[1].ConditionTable
    assert value.VarIdx == (0 if varIdx == 1 else ot.NO_VARIATION_INDEX)
    evaluator = VarStoreInstancer(
        roundtripped["GDEF"].table.VarStore if "GDEF" in roundtripped else None,
        roundtripped["fvar"].axes,
        {"wght": 1},
    )
    assert value.DefaultValue + evaluator[value.VarIdx] == (1 if varIdx == 1 else -1)


def test_subset_lookup_variations_prevents_feature_dedup(featureVarsTestFont):
    font = featureVarsTestFont
    addLookupVariation(font)
    gsub = font["GSUB"].table
    featureIndices = {
        record.FeatureTag: index
        for index, record in enumerate(gsub.FeatureList.FeatureRecord)
    }
    dligIndex = featureIndices["dlig"]
    gsub.FeatureVariations.LookupVariationRecord[0].FeatureIndex = dligIndex

    duplicate = ot.FeatureRecord()
    duplicate.FeatureTag = "dlig"
    duplicate.Feature = gsub.FeatureList.FeatureRecord[dligIndex].Feature
    duplicateIndex = len(gsub.FeatureList.FeatureRecord)
    gsub.FeatureList.FeatureRecord.append(duplicate)
    gsub.FeatureList.FeatureCount += 1

    for scriptRecord in gsub.ScriptList.ScriptRecord:
        langSystems = [scriptRecord.Script.DefaultLangSys]
        langSystems.extend(
            record.LangSys for record in scriptRecord.Script.LangSysRecord
        )
        for langSystem in filter(None, langSystems):
            if dligIndex in langSystem.FeatureIndex:
                langSystem.FeatureIndex.append(duplicateIndex)
                langSystem.FeatureCount += 1

    options = subset.Options()
    options.layout_features = ["*"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord("f"), ord("$")])
    subsetter.subset(font)

    assert [record.FeatureTag for record in gsub.FeatureList.FeatureRecord].count(
        "dlig"
    ) == 2


@pytest.mark.parametrize("explicit_empty", [False, True])
@pytest.mark.parametrize("drop_feature", [False, True])
@pytest.mark.parametrize("lazy", [False, True])
def test_subset_feature_variations_null_substitution(
    featureVarsTestFont, explicit_empty, drop_feature, lazy
):
    from copy import deepcopy

    font = featureVarsTestFont
    variations = font["GSUB"].table.FeatureVariations
    first = deepcopy(variations.FeatureVariationRecord[0])
    first.ConditionSet.ConditionTable[0].FilterRangeMinValue = 0.5
    if explicit_empty:
        first.FeatureTableSubstitution.SubstitutionRecord = []
        first.FeatureTableSubstitution.SubstitutionCount = 0
    else:
        first.FeatureTableSubstitution = None
    last = deepcopy(first)
    last.ConditionSet.ConditionTable[0].FilterRangeMinValue = -1
    last.ConditionSet.ConditionTable[0].FilterRangeMaxValue = 0
    variations.FeatureVariationRecord.insert(0, first)
    variations.FeatureVariationRecord.append(last)
    variations.FeatureVariationCount = 3
    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    font = TTFont(buf, lazy=lazy)

    options = subset.Options()
    options.glyph_names = True
    if drop_feature:
        options.layout_features.remove("rvrn")
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord("f"), ord("$")])
    subsetter.subset(font)

    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    gsub = TTFont(buf)["GSUB"].table
    if drop_feature:
        assert getattr(gsub, "FeatureVariations", None) is None
        assert gsub.Version == 0x00010000
    else:
        # The first empty record blocks the later substitution; only the last
        # empty record can be removed without changing first-match behavior.
        variations = gsub.FeatureVariations
        assert variations.FeatureVariationCount == 2
        first, second = variations.FeatureVariationRecord
        assert first.ConditionSet.ConditionTable[0].FilterRangeMinValue == 0.5
        if explicit_empty:
            assert first.FeatureTableSubstitution.SubstitutionCount == 0
        else:
            assert first.FeatureTableSubstitution is None
        substitution = second.FeatureTableSubstitution.SubstitutionRecord[0]
        lookup = gsub.LookupList.Lookup[substitution.Feature.LookupListIndex[0]]
        assert lookup.SubTable[0].mapping == {"dollar": "dollar.rvrn"}


# TODO test_subset_feature_variations_drop_from_end_empty_records
# https://github.com/fonttools/fonttools/issues/1881#issuecomment-619415044


@pytest.fixture
def singlepos2_font():
    fb = FontBuilder(unitsPerEm=1000)
    fb.setupGlyphOrder([".notdef", "a", "b", "c"])
    fb.setupCharacterMap({ord("a"): "a", ord("b"): "b", ord("c"): "c"})
    fb.setupNameTable({"familyName": "TestSingePosFormat", "styleName": "Regular"})
    fb.setupPost()
    fb.addOpenTypeFeatures("""
        feature kern {
            pos a -50;
            pos b -40;
            pos c -50;
        } kern;
    """)

    buf = io.BytesIO()
    fb.save(buf)
    buf.seek(0)

    return TTFont(buf)


@pytest.mark.parametrize("keep_classes", [False, True])
@pytest.mark.parametrize("extended", [False, True])
def test_subset_null_gdef_varstore(singlepos2_font, keep_classes, extended):
    font = singlepos2_font
    gdef = ot.GDEF()
    gdef.Version = 0x00010003
    gdef.AttachList = gdef.LigCaretList = None
    gdef.MarkAttachClassDef = gdef.MarkGlyphSetsDef = None
    gdef.VarStore = None
    gdef.GlyphClassDef = ot.ClassDef()
    gdef.GlyphClassDef.classDefs = {"a" if keep_classes else "b": 1}
    font["GDEF"] = newTable("GDEF")
    font["GDEF"].table = gdef

    if extended:
        gdef.Version = 0x00010004

    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    font = TTFont(buf)
    assert font["GDEF"].table.VarStore is None

    subsetter = subset.Subsetter()
    subsetter.populate(text="a")
    subsetter.subset(font)
    assert ("GDEF" in font) == keep_classes
    if keep_classes:
        table = font["GDEF"].table
        class_def = table.GlyphClassDef2 if extended else table.GlyphClassDef
        assert class_def.classDefs == {"a": 1}
        assert font["GDEF"].table.Version == (0x00010004 if extended else 0x00010000)

    output = io.BytesIO()
    font.save(output)
    output.seek(0)
    assert ("GDEF" in TTFont(output)) == keep_classes


@pytest.mark.parametrize("beyond64k", [False, True])
@pytest.mark.parametrize("lazy", [None, False, True])
@pytest.mark.parametrize("xml_roundtrip", [False, True])
def test_subset_variable_notdef_table_order(beyond64k, lazy, xml_roundtrip):
    fb = FontBuilder(1000, beyond64k=beyond64k)
    order = [".notdef", "A"]
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x41: "A"})
    pen = TTGlyphPen(None)
    for points in (
        [(50, 0), (50, 700), (450, 700), (450, 0)],
        [(100, 50), (400, 50), (400, 650), (100, 650)],
    ):
        pen.moveTo(points[0])
        for point in points[1:]:
            pen.lineTo(point)
        pen.closePath()
    notdef = pen.glyph()
    fb.setupGlyf({".notdef": notdef, "A": notdef})
    fb.setupHorizontalMetrics({name: (500, 50) for name in order})
    fb.setupHorizontalHeader()
    fb.setupNameTable({"familyName": "Variable Notdef", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.setupFvar([("wght", 100, 400, 900, "Weight")], [])
    deltas = [
        (-20, 0),
        (-20, 0),
        (20, 0),
        (20, 0),
        (-10, -5),
        (10, -5),
        (10, 5),
        (-10, 5),
        (0, 0),
        (40, 0),
        (0, 0),
        (0, 0),
    ]
    fb.setupGvar(
        {name: [TupleVariation({"wght": (0, 1, 1)}, deltas)] for name in order}
    )
    font = fb.font
    if xml_roundtrip:
        xml = io.StringIO()
        font.saveXML(xml)
        xml.seek(0)
        font = TTFont()
        font.importXML(xml)
    stream = io.BytesIO()
    font.save(stream)
    stream.seek(0)
    font = TTFont(stream, lazy=lazy)

    subsetter = subset.Subsetter()
    subsetter.populate(unicodes=[0x41])
    subsetter.subset(font)
    stream = io.BytesIO()
    font.save(stream)
    stream.seek(0)
    result = TTFont(stream)
    glyf_tag, gvar_tag = ("GLYF", "GVAR") if beyond64k else ("glyf", "gvar")
    assert result[glyf_tag][".notdef"].numberOfContours == 0
    assert result[gvar_tag].variations[".notdef"] == []
    assert result[gvar_tag].variations["A"][0].coordinates == deltas


@pytest.mark.parametrize("extension", [False, True])
@pytest.mark.parametrize("extended_header", [False, True])
@pytest.mark.parametrize("extended_formats", [False, True])
@pytest.mark.parametrize("lazy", [False, True])
@pytest.mark.parametrize("retain_gids", [False, True])
def test_subset_extended_layout(
    extension, extended_header, extended_formats, lazy, retain_gids, monkeypatch
):
    from fontTools.ttLib.beyond64k import (
        _convert_layout_formats,
        lower_tables,
        upper_tables,
    )

    fb = FontBuilder(1000)
    order = [
        ".notdef",
        "a",
        "b",
        "c",
        "d",
        "a.alt",
        "b.alt",
        "a_b",
        "acute",
        "grave",
        "unused",
    ]
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(
        {
            97: "a",
            98: "b",
            99: "c",
            100: "d",
            0x301: "acute",
            0x300: "grave",
            120: "unused",
        }
    )
    fb.setupGlyf({name: TTGlyphPen(None).glyph() for name in order})
    fb.setupHorizontalMetrics({name: (500, 0) for name in order})
    fb.setupHorizontalHeader()
    fb.setupNameTable({"familyName": "Extended Layout", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.addOpenTypeFeatures("""
        languagesystem DFLT dflt;
        markClass acute <anchor 0 0> @TOP;
        markClass grave <anchor 50 0> @TOP;
        feature salt { sub b from [b.alt c]; } salt;
        feature liga { sub a b by a_b; } liga;
        feature ccmp { sub d by a b; } ccmp;
        feature calt {
            lookupflag UseMarkFilteringSet [acute grave];
            sub c a' b by a.alt;
        } calt;
        feature rclt { rsub c a' b by a.alt; } rclt;
        feature kern {
            pos a -50;
            pos a b -30;
            pos [a c] [b d] -15;
        } kern;
        feature curs {
            pos cursive a <anchor 0 0> <anchor 300 0>;
            pos cursive b <anchor 0 0> <anchor 300 0>;
        } curs;
        feature mark {
            pos base a <anchor 100 300> mark @TOP;
            pos ligature a_b <anchor 100 300> mark @TOP
                ligComponent <anchor 200 300> mark @TOP;
        } mark;
        feature mkmk { pos mark acute <anchor 100 300> mark @TOP; } mkmk;
    """)

    def roundtrip(font, lazy=False):
        buf = io.BytesIO()
        font.save(buf)
        return TTFont(io.BytesIO(buf.getvalue()), lazy=lazy)

    if extension:
        for tag, extension_type, lookup_type in (
            ("GSUB", ot.ExtensionSubst, 7),
            ("GPOS", ot.ExtensionPos, 9),
        ):
            for lookup in fb.font[tag].table.LookupList.Lookup:
                wrapped = []
                for subtable in lookup.SubTable:
                    wrapper = extension_type()
                    wrapper.Format = 1
                    wrapper.ExtensionLookupType = lookup.LookupType
                    wrapper.ExtSubTable = subtable
                    wrapped.append(wrapper)
                lookup.SubTable = wrapped
                lookup.LookupType = lookup_type

    reference = roundtrip(fb.font)
    font = roundtrip(fb.font)
    if extended_header:
        upper_tables(font, tables=["GDEF", "GSUB", "GPOS"])
    for tag in ("GSUB", "GPOS"):
        _convert_layout_formats(font[tag].table, extended_formats)
    font = roundtrip(font, lazy=lazy)

    if not extended_header and not extended_formats:

        def no_recursive_walk(*args, **kwargs):
            pytest.fail("Compact layout adaptation traversed a classic table")

        monkeypatch.setattr(
            "fontTools.ttLib.beyond64k.dfs_base_table", no_recursive_walk
        )

    options = subset.Options()
    options.retain_gids = retain_gids
    options.glyph_names = True
    options.layout_features = ["*"]
    for target in (reference, font):
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(text="abcd\u0301\u0300")
        subsetter.subset(target)
    assert font.getGlyphOrder() == reference.getGlyphOrder()
    assert "a.alt" in font.getGlyphOrder()
    assert "a_b" in font.getGlyphOrder()
    assert "unused" not in font.getGlyphOrder()

    for tag in ("GSUB", "GPOS"):
        assert font[tag].table.Version == (
            0x00010002 if extended_header else 0x00010000
        )
    assert font["GDEF"].table.Version == (0x00010004 if extended_header else 0x00010002)
    monkeypatch.undo()
    font = roundtrip(font)
    lower_tables(font, tables=["GDEF", "GSUB", "GPOS"])
    for tag in ("GDEF", "GSUB", "GPOS"):
        assert getXML(font[tag].table.toXML, font) == getXML(
            reference[tag].table.toXML, reference
        )


@pytest.mark.parametrize("lazy", [False, True])
@pytest.mark.parametrize("retain_gids", [False, True])
def test_subset_extended_layout_high_glyph_ids(lazy, retain_gids):
    fb = FontBuilder(1000, beyond64k=True)
    order = [".notdef"] + [f"unused{i}" for i in range(1, 0x10000)] + ["a", "b", "a_b"]
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({97: "a", 98: "b"})
    fb.setupGlyf({name: TTGlyphPen(None).glyph() for name in order})
    fb.setupHorizontalMetrics({name: (500, 0) for name in order})
    fb.setupHorizontalHeader()
    fb.setupNameTable({"familyName": "High Layout GIDs", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.addOpenTypeFeatures("""
        feature liga { sub a b by a_b; } liga;
        feature kern { pos a b -30; } kern;
        table GDEF { GlyphClassDef [a b], [a_b], , ; } GDEF;
    """)
    buf = io.BytesIO()
    fb.font.save(buf)
    font = TTFont(io.BytesIO(buf.getvalue()), lazy=lazy)

    options = subset.Options()
    options.retain_gids = retain_gids
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text="ab")
    subsetter.subset(font)
    output = io.BytesIO()
    font.save(output)
    font = TTFont(io.BytesIO(output.getvalue()))
    assert len(font.getGlyphOrder()) == (0x10003 if retain_gids else 4)
    ligature = font["GSUB"].table.LookupList2.Lookup[0].SubTable[0].ligatures["a"][0]
    assert font.getGlyphID(ligature.LigGlyph) == (0x10002 if retain_gids else 3)
    assert ligature.Component == ["b"]
    assert font["GDEF"].table.GlyphClassDef2.classDefs[ligature.LigGlyph] == 2
    pair = (
        font["GPOS"]
        .table.LookupList2.Lookup[0]
        .SubTable[0]
        .PairSet[0]
        .PairValueRecord[0]
    )
    assert pair.SecondGlyph == "b"
    assert pair.Value1.XAdvance == -30


def test_subset_single_pos_format(singlepos2_font):
    font = singlepos2_font
    # The input font has a SinglePos Format 2 subtable where each glyph has
    # different ValueRecords
    assert getXML(font["GPOS"].table.LookupList.Lookup[0].toXML, font) == [
        "<Lookup>",
        '  <LookupType value="1"/>',
        '  <LookupFlag value="0"/>',
        "  <!-- SubTableCount=1 -->",
        '  <SinglePos index="0" Format="2">',
        "    <Coverage>",
        '      <Glyph value="a"/>',
        '      <Glyph value="b"/>',
        '      <Glyph value="c"/>',
        "    </Coverage>",
        '    <ValueFormat value="4"/>',
        "    <!-- ValueCount=3 -->",
        '    <Value index="0" XAdvance="-50"/>',
        '    <Value index="1" XAdvance="-40"/>',
        '    <Value index="2" XAdvance="-50"/>',
        "  </SinglePos>",
        "</Lookup>",
    ]

    options = subset.Options()
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord("a"), ord("c")])
    subsetter.subset(font)

    # All the subsetted glyphs from the original SinglePos Format2 subtable
    # now have the same ValueRecord, so we use a more compact Format 1 subtable.
    assert getXML(font["GPOS"].table.LookupList.Lookup[0].toXML, font) == [
        "<Lookup>",
        '  <LookupType value="1"/>',
        '  <LookupFlag value="0"/>',
        "  <!-- SubTableCount=1 -->",
        '  <SinglePos index="0" Format="1">',
        "    <Coverage>",
        '      <Glyph value="a"/>',
        '      <Glyph value="c"/>',
        "    </Coverage>",
        '    <ValueFormat value="4"/>',
        '    <Value XAdvance="-50"/>',
        "  </SinglePos>",
        "</Lookup>",
    ]


def test_subset_single_pos_format2_all_None(singlepos2_font):
    # https://github.com/fonttools/fonttools/issues/2602
    font = singlepos2_font
    gpos = font["GPOS"].table
    subtable = gpos.LookupList.Lookup[0].SubTable[0]
    assert subtable.Format == 2
    # Hack a SinglePosFormat2 with ValueFormat = 0; our own buildSinglePos
    # never makes these as a SinglePosFormat1 is more compact, but they can
    # be found in the wild.
    subtable.Value = [None] * subtable.ValueCount
    subtable.ValueFormat = 0

    assert getXML(subtable.toXML, font) == [
        '<SinglePos Format="2">',
        "  <Coverage>",
        '    <Glyph value="a"/>',
        '    <Glyph value="b"/>',
        '    <Glyph value="c"/>',
        "  </Coverage>",
        '  <ValueFormat value="0"/>',
        "  <!-- ValueCount=3 -->",
        "</SinglePos>",
    ]

    options = subset.Options()
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord("a"), ord("c")])
    subsetter.subset(font)

    # Check it was downgraded to Format1 after subsetting
    assert getXML(font["GPOS"].table.LookupList.Lookup[0].SubTable[0].toXML, font) == [
        '<SinglePos Format="1">',
        "  <Coverage>",
        '    <Glyph value="a"/>',
        '    <Glyph value="c"/>',
        "  </Coverage>",
        '  <ValueFormat value="0"/>',
        "</SinglePos>",
    ]


@pytest.fixture
def ttf_path(tmp_path):
    # $(dirname $0)/../ttLib/data
    ttLib_data = pathlib.Path(__file__).parent.parent / "ttLib" / "data"
    font = TTFont()
    font.importXML(ttLib_data / "TestTTF-Regular.ttx")
    font_path = tmp_path / "TestTTF-Regular.ttf"
    font.save(font_path)
    return font_path


def test_subset_empty_glyf(tmp_path, ttf_path):
    subset_path = tmp_path / (ttf_path.name + ".subset")
    # only keep empty .notdef and space glyph, resulting in an empty glyf table
    subset.main(
        [
            str(ttf_path),
            "--no-notdef-outline",
            "--glyph-names",
            f"--output-file={subset_path}",
            "--glyphs=.notdef space",
        ]
    )
    subset_font = TTFont(subset_path)

    assert subset_font.getGlyphOrder() == [".notdef", "space"]
    assert subset_font.reader["glyf"] == b"\x00"

    glyf = subset_font["glyf"]
    assert all(glyf[g].numberOfContours == 0 for g in subset_font.getGlyphOrder())

    loca = subset_font["loca"]
    assert all(loc == 0 for loc in loca)


@pytest.mark.parametrize("hinting", [False, True])
def test_subset_remaps_24bit_glyf_component(hinting):
    glyph_order = [".notdef"] + [None] * 0xFFFF + ["component", "composite"]
    glyf = newTable("GLYF")
    glyf.glyphOrder = glyph_order
    glyf.glyphs = {}

    for name in (".notdef", "component"):
        glyph = glyf.glyphs[name] = Glyph()
        glyph.data = b""
    composite = glyf.glyphs["composite"] = Glyph()
    composite.data = (
        b"\xff\xff"  # numberOfContours
        b"\0\0\0\0\0\0\0\0"  # bounds
        b"\x21\x02"  # GID_IS_24_BIT | WE_HAVE_INSTRUCTIONS | ARGS_ARE_XY_VALUES
        b"\x01\x00\x00"  # component glyph ID 0x10000
        b"\x0a\x14"  # x, y
        b"\0\x03\xb0\x01\x21"  # PUSHB 1; POP
    )

    subsetter = subset.Subsetter()
    subsetter.glyphs = {".notdef", "component", "composite"}
    subsetter.glyphs_emptied = frozenset()

    glyf.subset_glyphs(subsetter)
    options = subset.Options()
    options.hinting = hinting
    glyf.prune_post_subset(TTFont(), options)

    assert glyf.glyphOrder == [".notdef", "component", "composite"]
    assert composite.data[12:15] == b"\0\0\x01"
    assert composite.getComponentNames(glyf) == ["component"]
    composite.expand(glyf)
    assert (composite.components[0].x, composite.components[0].y) == (10, 20)
    assert hasattr(composite, "program") == hinting
    if hinting:
        assert composite.program.getBytecode() == b"\xb0\x01\x21"


@pytest.mark.parametrize("extended", [False, True])
@pytest.mark.parametrize("retain_gids", [False, True])
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("varc", [False, True])
def test_subset_composite_closure(extended, retain_gids, nested, varc):
    from fontTools.ttLib.beyond64k import upper_tables
    from fontTools.pens.recordingPen import DecomposingRecordingPen

    order = [".notdef", "leaf", "unused", "composite"]
    glyphs = {name: TTGlyphPen(None).glyph() for name in order}
    pen = TTGlyphPen(None)
    pen.moveTo((100, 0))
    pen.lineTo((200, 0))
    pen.lineTo((100, 100))
    pen.closePath()
    glyphs["leaf"] = pen.glyph()
    if nested:
        pen = TTGlyphPen(glyphs)
        pen.addComponent("leaf", (1, 0, 0, 1, 100, 50))
        glyphs["unused"] = pen.glyph()
    pen = TTGlyphPen(glyphs)
    pen.addComponent("unused" if nested else "leaf", (1, 0, 0, 1, 100, 50))
    glyphs["composite"] = pen.glyph()

    fb = FontBuilder(1000)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({65: "composite"})
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (500, 100) for name in order})
    fb.setupHorizontalHeader()
    fb.setupNameTable({"familyName": "Composite closure", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    if extended:
        upper_tables(fb.font)
    if varc:
        component = ot.VarComponent()
        component.glyphName = "composite"
        glyph = ot.VarCompositeGlyph()
        glyph.components = [component]
        table = ot.VARC()
        table.Version = 0x10000
        table.Coverage = ot.Coverage()
        table.Coverage.glyphs = ["composite"]
        table.MultiVarStore = table.AxisIndicesList = table.ConditionList = None
        table.VarCompositeGlyphs = ot.VarCompositeGlyphs()
        table.VarCompositeGlyphs.VarCompositeGlyph = [glyph]
        fb.font["VARC"] = newTable("VARC")
        fb.font["VARC"].table = table

    stream = io.BytesIO()
    fb.font.save(stream)
    font = TTFont(io.BytesIO(stream.getvalue()))
    glyph_set = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set["composite"].draw(pen)
    expected = pen.value

    options = subset.Options()
    options.glyph_names = True
    options.retain_gids = retain_gids
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[65])
    subsetter.subset(font)
    assert "leaf" in subsetter.glyphs_retained
    if nested:
        assert "unused" in subsetter.glyphs_retained
    stream = io.BytesIO()
    font.save(stream)
    font = TTFont(io.BytesIO(stream.getvalue()))
    glyph_set = font.getGlyphSet()
    pen = DecomposingRecordingPen(glyph_set)
    glyph_set["composite"].draw(pen)
    assert pen.value == expected


def test_colr_paint_glyph2_closure():
    paint = ot.Paint()
    paint.Format = ot.PaintFormat.PaintGlyph2
    paint.Glyph = "high"
    paint.Paint = ot.Paint()
    paint.Paint.Format = ot.PaintFormat.PaintSolid
    paint.Paint.PaletteIndex = 0
    paint.Paint.Alpha = 1.0

    assert subset._paint_glyph_names(paint, ot.COLR()) == {"high"}


@pytest.fixture
def colrv1_path(tmp_path):
    base_glyph_names = ["uni%04X" % i for i in range(0xE000, 0xE000 + 10)]
    layer_glyph_names = ["glyph%05d" % i for i in range(10, 20)]
    glyph_order = [".notdef"] + base_glyph_names + layer_glyph_names

    pen = TTGlyphPen(glyphSet=None)
    pen.moveTo((0, 0))
    pen.lineTo((0, 500))
    pen.lineTo((500, 500))
    pen.lineTo((500, 0))
    pen.closePath()
    glyph = pen.glyph()
    glyphs = {g: glyph for g in glyph_order}

    fb = FontBuilder(unitsPerEm=1024, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({int(name[3:], 16): name for name in base_glyph_names})
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({g: (500, 0) for g in glyph_order})
    fb.setupHorizontalHeader()
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "TestCOLRv1", "styleName": "Regular"})

    fb.setupCOLR(
        {
            "uniE000": (
                ot.PaintFormat.PaintColrLayers,
                [
                    {
                        "Format": ot.PaintFormat.PaintGlyph,
                        "Paint": (ot.PaintFormat.PaintSolid, 0),
                        "Glyph": "glyph00010",
                    },
                    {
                        "Format": ot.PaintFormat.PaintGlyph,
                        "Paint": (ot.PaintFormat.PaintSolid, 2, 0.3),
                        "Glyph": "glyph00011",
                    },
                ],
            ),
            "uniE001": (
                ot.PaintFormat.PaintColrLayers,
                [
                    {
                        "Format": ot.PaintFormat.PaintTransform,
                        "Paint": {
                            "Format": ot.PaintFormat.PaintGlyph,
                            "Paint": {
                                "Format": ot.PaintFormat.PaintRadialGradient,
                                "x0": 250,
                                "y0": 250,
                                "r0": 250,
                                "x1": 200,
                                "y1": 200,
                                "r1": 0,
                                "ColorLine": {
                                    "ColorStop": [(0.0, 1), (1.0, 2)],
                                    "Extend": "repeat",
                                },
                            },
                            "Glyph": "glyph00012",
                        },
                        "Transform": (0.7071, 0.7071, -0.7071, 0.7071, 0, 0),
                    },
                    {
                        "Format": ot.PaintFormat.PaintGlyph,
                        "Paint": (ot.PaintFormat.PaintSolid, 1, 0.5),
                        "Glyph": "glyph00013",
                    },
                ],
            ),
            "uniE002": (
                ot.PaintFormat.PaintColrLayers,
                [
                    {
                        "Format": ot.PaintFormat.PaintGlyph,
                        "Paint": {
                            "Format": ot.PaintFormat.PaintLinearGradient,
                            "x0": 0,
                            "y0": 0,
                            "x1": 500,
                            "y1": 500,
                            "x2": -500,
                            "y2": 500,
                            "ColorLine": {"ColorStop": [(0.0, 1), (1.0, 2)]},
                        },
                        "Glyph": "glyph00014",
                    },
                    {
                        "Format": ot.PaintFormat.PaintTransform,
                        "Paint": {
                            "Format": ot.PaintFormat.PaintGlyph,
                            "Paint": (ot.PaintFormat.PaintSolid, 1),
                            "Glyph": "glyph00015",
                        },
                        "Transform": (1, 0, 0, 1, 400, 400),
                    },
                ],
            ),
            "uniE003": {
                "Format": ot.PaintFormat.PaintRotateAroundCenter,
                "Paint": {
                    "Format": ot.PaintFormat.PaintColrGlyph,
                    "Glyph": "uniE001",
                },
                "angle": 45,
                "centerX": 250,
                "centerY": 250,
            },
            "uniE004": [
                ("glyph00016", 1),
                ("glyph00017", 0xFFFF),  # special palette index for foreground text
                ("glyph00018", 2),
            ],
        },
        clipBoxes={
            "uniE000": (0, 0, 200, 300),
            "uniE001": (0, 0, 500, 500),
            "uniE002": (-50, -50, 400, 400),
            "uniE003": (-50, -50, 400, 400),
        },
    )
    fb.setupCPAL(
        [
            [
                (1.0, 0.0, 0.0, 1.0),  # red
                (0.0, 1.0, 0.0, 1.0),  # green
                (0.0, 0.0, 1.0, 1.0),  # blue
            ],
        ],
    )

    output_path = tmp_path / "TestCOLRv1.ttf"
    fb.save(output_path)

    return output_path


@pytest.fixture
def colrv1_cpalv1_path(colrv1_path):
    # upgrade CPAL from v0 to v1 by adding labels
    font = TTFont(colrv1_path)
    fb = FontBuilder(font=font)
    fb.setupCPAL(
        [
            [
                (1.0, 0.0, 0.0, 1.0),  # red
                (0.0, 1.0, 0.0, 1.0),  # green
                (0.0, 0.0, 1.0, 1.0),  # blue
            ],
        ],
        paletteLabels=["test palette"],
        paletteEntryLabels=["first color", "second color", "third color"],
    )

    output_path = colrv1_path.parent / "TestCOLRv1CPALv1.ttf"
    fb.save(output_path)

    return output_path


@pytest.fixture
def colrv1_cpalv1_share_nameID_path(colrv1_path):
    font = TTFont(colrv1_path)
    fb = FontBuilder(font=font)
    fb.setupCPAL(
        [
            [
                (1.0, 0.0, 0.0, 1.0),  # red
                (0.0, 1.0, 0.0, 1.0),  # green
                (0.0, 0.0, 1.0, 1.0),  # blue
            ],
        ],
        paletteLabels=["test palette"],
        paletteEntryLabels=["first color", "second color", "third color"],
    )

    # Set the name ID of the first color to use nameID 1 = familyName = "TestCOLRv1"
    fb.font["CPAL"].paletteEntryLabels[0] = 1

    output_path = colrv1_path.parent / "TestCOLRv1CPALv1.ttf"
    fb.save(output_path)

    return output_path


def test_subset_COLRv1_and_CPAL(colrv1_path):
    subset_path = colrv1_path.parent / (colrv1_path.name + ".subset")

    subset.main(
        [
            str(colrv1_path),
            "--glyph-names",
            f"--output-file={subset_path}",
            "--unicodes=E002,E003,E004",
        ]
    )
    subset_font = TTFont(subset_path)

    glyph_set = set(subset_font.getGlyphOrder())

    # uniE000 and its children are excluded from subset
    assert "uniE000" not in glyph_set
    assert "glyph00010" not in glyph_set
    assert "glyph00011" not in glyph_set

    # uniE001 and children are pulled in indirectly as PaintColrGlyph by uniE003
    assert "uniE001" in glyph_set
    assert "glyph00012" in glyph_set
    assert "glyph00013" in glyph_set

    assert "uniE002" in glyph_set
    assert "glyph00014" in glyph_set
    assert "glyph00015" in glyph_set

    assert "uniE003" in glyph_set

    assert "uniE004" in glyph_set
    assert "glyph00016" in glyph_set
    assert "glyph00017" in glyph_set
    assert "glyph00018" in glyph_set

    assert "COLR" in subset_font
    colr = subset_font["COLR"].table
    assert colr.Version == 1
    assert len(colr.BaseGlyphRecordArray.BaseGlyphRecord) == 1
    assert len(colr.BaseGlyphList.BaseGlyphPaintRecord) == 3  # was 4

    base = colr.BaseGlyphList.BaseGlyphPaintRecord[0]
    assert base.BaseGlyph == "uniE001"
    layers = colr.LayerList.Paint[
        base.Paint.FirstLayerIndex : base.Paint.FirstLayerIndex + base.Paint.NumLayers
    ]
    assert len(layers) == 2
    # check v1 palette indices were remapped
    assert layers[0].Paint.Paint.ColorLine.ColorStop[0].PaletteIndex == 0
    assert layers[0].Paint.Paint.ColorLine.ColorStop[1].PaletteIndex == 1
    assert layers[1].Paint.PaletteIndex == 0

    baseRecV0 = colr.BaseGlyphRecordArray.BaseGlyphRecord[0]
    assert baseRecV0.BaseGlyph == "uniE004"
    layersV0 = colr.LayerRecordArray.LayerRecord
    assert len(layersV0) == 3
    # check v0 palette indices were remapped (except for 0xFFFF)
    assert layersV0[0].PaletteIndex == 0
    assert layersV0[1].PaletteIndex == 0xFFFF
    assert layersV0[2].PaletteIndex == 1

    clipBoxes = colr.ClipList.clips
    assert {"uniE001", "uniE002", "uniE003"} == set(clipBoxes)
    assert clipBoxes["uniE002"] == clipBoxes["uniE003"]

    assert "CPAL" in subset_font
    cpal = subset_font["CPAL"]
    assert [
        tuple(v / 255 for v in (c.red, c.green, c.blue, c.alpha))
        for c in cpal.palettes[0]
    ] == [
        # the first color 'red' was pruned
        (0.0, 1.0, 0.0, 1.0),  # green
        (0.0, 0.0, 1.0, 1.0),  # blue
    ]


def test_subset_COLRv1_and_CPALv1(colrv1_cpalv1_path):
    subset_path = colrv1_cpalv1_path.parent / (colrv1_cpalv1_path.name + ".subset")

    subset.main(
        [
            str(colrv1_cpalv1_path),
            "--glyph-names",
            f"--output-file={subset_path}",
            "--unicodes=E002,E003,E004",
        ]
    )
    subset_font = TTFont(subset_path)

    assert "CPAL" in subset_font
    cpal = subset_font["CPAL"]
    name_table = subset_font["name"]
    assert [
        name_table.getDebugName(name_id) for name_id in cpal.paletteEntryLabels
    ] == [
        # "first color",  # The first color was pruned
        "second color",
        "third color",
    ]
    # check that the "first color" name is dropped from name table
    font = TTFont(colrv1_cpalv1_path)

    first_color_nameID = None
    for n in font["name"].names:
        if n.toUnicode() == "first color":
            first_color_nameID = n.nameID
            break
    assert first_color_nameID is not None
    assert all(n.nameID != first_color_nameID for n in name_table.names)


def test_subset_COLRv1_and_CPALv1_keep_nameID(colrv1_cpalv1_path):
    subset_path = colrv1_cpalv1_path.parent / (colrv1_cpalv1_path.name + ".subset")

    # figure out the name ID of first color so we can keep it
    font = TTFont(colrv1_cpalv1_path)

    first_color_nameID = None
    for n in font["name"].names:
        if n.toUnicode() == "first color":
            first_color_nameID = n.nameID
            break
    assert first_color_nameID is not None

    subset.main(
        [
            str(colrv1_cpalv1_path),
            "--glyph-names",
            f"--output-file={subset_path}",
            "--unicodes=E002,E003,E004",
            f"--name-IDs={first_color_nameID}",
        ]
    )
    subset_font = TTFont(subset_path)

    assert "CPAL" in subset_font
    cpal = subset_font["CPAL"]
    name_table = subset_font["name"]
    assert [
        name_table.getDebugName(name_id) for name_id in cpal.paletteEntryLabels
    ] == [
        # "first color",  # The first color was pruned
        "second color",
        "third color",
    ]

    # Check that the name ID is kept
    assert any(n.nameID == first_color_nameID for n in name_table.names)


def test_subset_COLRv1_and_CPALv1_share_nameID(colrv1_cpalv1_share_nameID_path):
    subset_path = colrv1_cpalv1_share_nameID_path.parent / (
        colrv1_cpalv1_share_nameID_path.name + ".subset"
    )

    subset.main(
        [
            str(colrv1_cpalv1_share_nameID_path),
            "--glyph-names",
            f"--output-file={subset_path}",
            "--unicodes=E002,E003,E004",
        ]
    )
    subset_font = TTFont(subset_path)

    assert "CPAL" in subset_font
    cpal = subset_font["CPAL"]
    name_table = subset_font["name"]
    assert [
        name_table.getDebugName(name_id) for name_id in cpal.paletteEntryLabels
    ] == [
        # "first color",  # The first color was pruned
        "second color",
        "third color",
    ]

    # Check that the name ID 1 is kept
    assert any(n.nameID == 1 for n in name_table.names)


def test_subset_COLRv1_and_CPAL_drop_empty(colrv1_path):
    subset_path = colrv1_path.parent / (colrv1_path.name + ".subset")

    subset.main(
        [
            str(colrv1_path),
            "--glyph-names",
            f"--output-file={subset_path}",
            "--glyphs=glyph00010",
        ]
    )
    subset_font = TTFont(subset_path)

    glyph_set = set(subset_font.getGlyphOrder())

    assert "glyph00010" in glyph_set
    assert "uniE000" not in glyph_set

    assert "COLR" not in subset_font
    assert "CPAL" not in subset_font


def test_subset_COLRv1_downgrade_version(colrv1_path):
    subset_path = colrv1_path.parent / (colrv1_path.name + ".subset")

    subset.main(
        [
            str(colrv1_path),
            "--glyph-names",
            f"--output-file={subset_path}",
            "--unicodes=E004",
        ]
    )
    subset_font = TTFont(subset_path)

    assert set(subset_font.getGlyphOrder()) == {
        ".notdef",
        "uniE004",
        "glyph00016",
        "glyph00017",
        "glyph00018",
    }

    assert "COLR" in subset_font
    assert subset_font["COLR"].version == 0


def test_subset_COLRv1_drop_all_v0_glyphs(colrv1_path):
    subset_path = colrv1_path.parent / (colrv1_path.name + ".subset")

    subset.main(
        [
            str(colrv1_path),
            "--glyph-names",
            f"--output-file={subset_path}",
            "--unicodes=E003",
        ]
    )
    subset_font = TTFont(subset_path)

    assert set(subset_font.getGlyphOrder()) == {
        ".notdef",
        "uniE001",
        "uniE003",
        "glyph00012",
        "glyph00013",
    }

    assert "COLR" in subset_font
    colr = subset_font["COLR"]
    assert colr.version == 1
    assert colr.table.BaseGlyphRecordCount == 0
    assert colr.table.BaseGlyphRecordArray is None
    assert colr.table.LayerRecordArray is None
    assert colr.table.LayerRecordCount == 0


def test_subset_COLRv1_no_ClipList(colrv1_path):
    font = TTFont(colrv1_path)
    font["COLR"].table.ClipList = None  # empty ClipList
    font.save(colrv1_path)

    subset_path = colrv1_path.parent / (colrv1_path.name + ".subset")
    subset.main(
        [
            str(colrv1_path),
            f"--output-file={subset_path}",
            "--unicodes=*",
        ]
    )
    subset_font = TTFont(subset_path)
    assert subset_font["COLR"].table.ClipList is None


def test_subset_keep_size_drop_empty_stylistic_set():
    fb = FontBuilder(unitsPerEm=1000, isTTF=True)
    glyph_order = [".notdef", "a", "b", "b.ss01"]
    fb.setupGlyphOrder(glyph_order)
    fb.setupGlyf({g: TTGlyphPen(None).glyph() for g in glyph_order})
    fb.setupCharacterMap({ord("a"): "a", ord("b"): "b"})
    fb.setupHorizontalMetrics({g: (500, 0) for g in glyph_order})
    fb.setupHorizontalHeader()
    fb.setupOS2()
    fb.setupPost()
    fb.setupNameTable({"familyName": "TestKeepSizeFeature", "styleName": "Regular"})
    fb.addOpenTypeFeatures("""
        feature size {
          parameters 10.0 0;
        } size;
        feature ss01 {
          featureNames {
            name "Alternate b";
          };
          sub b by b.ss01;
        } ss01;
    """)

    buf = io.BytesIO()
    fb.save(buf)
    buf.seek(0)

    font = TTFont(buf)

    gpos_features = font["GPOS"].table.FeatureList.FeatureRecord
    assert gpos_features[0].FeatureTag == "size"
    assert isinstance(gpos_features[0].Feature.FeatureParams, ot.FeatureParamsSize)
    assert gpos_features[0].Feature.LookupCount == 0
    gsub_features = font["GSUB"].table.FeatureList.FeatureRecord
    assert gsub_features[0].FeatureTag == "ss01"
    assert isinstance(
        gsub_features[0].Feature.FeatureParams, ot.FeatureParamsStylisticSet
    )

    options = subset.Options(layout_features=["*"])
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[ord("a")])
    subsetter.subset(font)

    # empty size feature was kept
    gpos_features = font["GPOS"].table.FeatureList.FeatureRecord
    assert gpos_features[0].FeatureTag == "size"
    assert isinstance(gpos_features[0].Feature.FeatureParams, ot.FeatureParamsSize)
    assert gpos_features[0].Feature.LookupCount == 0
    # empty ss01 feature was dropped
    assert font["GSUB"].table.FeatureList.FeatureCount == 0


@pytest.mark.skipif(etree is not None, reason="lxml is installed")
def test_subset_svg_missing_lxml(ttf_path):
    # add dummy SVG table and confirm we raise ImportError upon trying to subset it
    font = TTFont(ttf_path)
    font["SVG "] = newTable("SVG ")
    font["SVG "].docList = [('<svg><g id="glyph1"/></svg>', 1, 1)]
    font.save(ttf_path)

    with pytest.raises(ImportError):
        subset.main([str(ttf_path), "--gids=0,1"])


def test_subset_COLR_glyph_closure(tmp_path):
    # https://github.com/fonttools/fonttools/issues/2461
    font = TTFont()
    ttx = pathlib.Path(__file__).parent / "data" / "BungeeColor-Regular.ttx"
    font.importXML(ttx)

    color_layers = font["COLR"].ColorLayers
    assert ".notdef" in color_layers
    assert "Agrave" in color_layers
    assert "grave" in color_layers

    font_path = tmp_path / "BungeeColor-Regular.ttf"
    subset_path = font_path.with_suffix(".subset.ttf)")
    font.save(font_path)

    subset.main(
        [
            str(font_path),
            "--glyph-names",
            f"--output-file={subset_path}",
            "--glyphs=Agrave",
        ]
    )
    subset_font = TTFont(subset_path)

    glyph_order = subset_font.getGlyphOrder()

    assert glyph_order == [
        ".notdef",  # '.notdef' is always included automatically
        "A",
        "grave",
        "Agrave",
        ".notdef.alt001",
        ".notdef.alt002",
        "A.alt002",
        "Agrave.alt001",
        "Agrave.alt002",
        "grave.alt002",
    ]

    color_layers = subset_font["COLR"].ColorLayers
    assert ".notdef" in color_layers
    assert "Agrave" in color_layers
    # Agrave 'glyf' uses grave. It should be retained in 'glyf' but NOT in
    # COLR when we subset down to Agrave.
    assert "grave" not in color_layers


def test_subset_recalc_xAvgCharWidth(ttf_path):
    # Note that the font in in the *ttLib*/data/TestTTF-Regular.ttx file,
    # not this subset/data folder.
    font = TTFont(ttf_path)
    xAvgCharWidth_before = font["OS/2"].xAvgCharWidth

    subset_path = ttf_path.with_suffix(".subset.ttf")
    subset.main(
        [
            str(ttf_path),
            f"--output-file={subset_path}",
            # Keep only the ellipsis, which is very wide, that ought to bump up the average
            "--glyphs=ellipsis",
            "--recalc-average-width",
            "--no-prune-unicode-ranges",
        ]
    )
    subset_font = TTFont(subset_path)
    xAvgCharWidth_after = subset_font["OS/2"].xAvgCharWidth

    # Check that the value gets updated
    assert xAvgCharWidth_after != xAvgCharWidth_before

    # Check that the value gets updated to the actual new value
    subset_font["OS/2"].recalcAvgCharWidth(subset_font)
    assert xAvgCharWidth_after == subset_font["OS/2"].xAvgCharWidth


def test_subset_prune_gdef_markglyphsetsdef():
    # GDEF_MarkGlyphSetsDef
    fb = FontBuilder(unitsPerEm=1000, isTTF=True)
    glyph_order = [
        ".notdef",
        "A",
        "Aacute",
        "Acircumflex",
        "Adieresis",
        "a",
        "aacute",
        "acircumflex",
        "adieresis",
        "dieresiscomb",
        "acutecomb",
        "circumflexcomb",
    ]
    fb.setupGlyphOrder(glyph_order)
    fb.setupGlyf({g: TTGlyphPen(None).glyph() for g in glyph_order})
    fb.setupHorizontalMetrics({g: (500, 0) for g in glyph_order})
    fb.setupHorizontalHeader()
    fb.setupPost()
    fb.setupNameTable(
        {"familyName": "TestGDEFMarkGlyphSetsDef", "styleName": "Regular"}
    )
    fb.addOpenTypeFeatures("""
        feature ccmp {
            lookup ccmp_1 {
                lookupflag UseMarkFilteringSet [acutecomb];
                sub a acutecomb by aacute;
                sub A acutecomb by Aacute;
            } ccmp_1;
            lookup ccmp_2 {
                lookupflag UseMarkFilteringSet [circumflexcomb];
                sub a circumflexcomb by acircumflex;
                sub A circumflexcomb by Acircumflex;
            } ccmp_2;
            lookup ccmp_3 {
                lookupflag UseMarkFilteringSet [dieresiscomb];
                sub a dieresiscomb by adieresis;
                sub A dieresiscomb by Adieresis;
                sub A acutecomb by Aacute;
            } ccmp_3;
        } ccmp;
    """)

    buf = io.BytesIO()
    fb.save(buf)
    buf.seek(0)

    font = TTFont(buf)

    features = font["GSUB"].table.FeatureList.FeatureRecord
    assert features[0].FeatureTag == "ccmp"
    lookups = font["GSUB"].table.LookupList.Lookup
    assert lookups[0].LookupFlag == 16
    assert lookups[0].MarkFilteringSet == 0
    assert lookups[1].LookupFlag == 16
    assert lookups[1].MarkFilteringSet == 1
    assert lookups[2].LookupFlag == 16
    assert lookups[2].MarkFilteringSet == 2
    marksets = font["GDEF"].table.MarkGlyphSetsDef.Coverage
    assert marksets[0].glyphs == ["acutecomb"]
    assert marksets[1].glyphs == ["circumflexcomb"]
    assert marksets[2].glyphs == ["dieresiscomb"]

    options = subset.Options(layout_features=["*"])
    subsetter = subset.Subsetter(options)
    subsetter.populate(glyphs=["A", "a", "acutecomb", "dieresiscomb"])
    subsetter.subset(font)

    features = font["GSUB"].table.FeatureList.FeatureRecord
    assert features[0].FeatureTag == "ccmp"
    lookups = font["GSUB"].table.LookupList.Lookup
    assert lookups[0].LookupFlag == 16
    assert lookups[0].MarkFilteringSet == 0
    assert lookups[1].LookupFlag == 16
    assert lookups[1].MarkFilteringSet == 1
    marksets = font["GDEF"].table.MarkGlyphSetsDef.Coverage
    assert marksets[0].glyphs == ["acutecomb"]
    assert marksets[1].glyphs == ["dieresiscomb"]

    buf = io.BytesIO()
    fb.save(buf)
    buf.seek(0)

    font = TTFont(buf)

    options = subset.Options(layout_features=["*"], layout_closure=False)
    subsetter = subset.Subsetter(options)
    subsetter.populate(glyphs=["A", "acutecomb", "Aacute"])
    subsetter.subset(font)

    features = font["GSUB"].table.FeatureList.FeatureRecord
    assert features[0].FeatureTag == "ccmp"
    lookups = font["GSUB"].table.LookupList.Lookup
    assert lookups[0].LookupFlag == 16
    assert lookups[0].MarkFilteringSet == 0
    assert lookups[1].LookupFlag == 8
    assert lookups[1].MarkFilteringSet == None
    marksets = font["GDEF"].table.MarkGlyphSetsDef.Coverage
    assert marksets[0].glyphs == ["acutecomb"]


def test_prune_user_name_IDs_with_keep_all(ttf_path):
    font = TTFont(ttf_path)

    keepNameIDs = {n.nameID for n in font["name"].names}

    for i in range(10):
        font["name"].addName(f"Test{i}")

    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]

    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=font.getBestCmap().keys())
    subsetter.subset(font)

    nameIDs = {n.nameID for n in font["name"].names}
    assert not any(n > 255 for n in nameIDs)
    assert nameIDs == keepNameIDs


def test_prune_unused_user_name_IDs_with_keep_all(ttf_path):
    font = TTFont(ttf_path)

    keepNameIDs = {n.nameID for n in font["name"].names}

    for i in range(10):
        font["name"].addName(f"Test{i}")

    nameID = font["name"].addName("Test STAT")
    keepNameIDs.add(nameID)

    font["STAT"] = newTable("STAT")
    font["STAT"].table = ot.STAT()
    font["STAT"].table.ElidedFallbackNameID = nameID

    options = subset.Options()
    options.name_IDs = ["*"]
    options.name_legacy = True
    options.name_languages = ["*"]

    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=font.getBestCmap().keys())
    subsetter.subset(font)

    nameIDs = {n.nameID for n in font["name"].names}
    assert nameIDs == keepNameIDs


def test_cvXX_feature_params_nameIDs_are_retained():
    # https://github.com/fonttools/fonttools/issues/3616
    font = TTFont()
    ttx = pathlib.Path(__file__).parent / "data" / "Andika-Regular.subset.ttx"
    font.importXML(ttx)

    keepNameIDs = {n.nameID for n in font["name"].names}

    options = subset.Options()
    options.glyph_names = True
    # that's where the FeatureParamsCharacteVariants are stored
    options.layout_features.append("cv43")

    subsetter = subset.Subsetter(options)
    subsetter.populate(glyphs=font.getGlyphOrder())
    subsetter.subset(font)

    # we expect that all nameIDs are retained, including all the nameIDs
    # used by the FeatureParamsCharacterVariants
    nameIDs = {n.nameID for n in font["name"].names}
    assert nameIDs == keepNameIDs


def test_preserve_name_ids_when_used_elsewhere():
    font = TTFont()
    ttx = pathlib.Path(__file__).parent / "data" / "PreserveSillyNamesTest.ttx"
    font.importXML(ttx)

    visitor = NameRecordVisitor()
    visitor.visit(font)
    assert visitor.seen.intersection(subset.NAME_IDS_TO_OBFUSCATE)

    options = subset.Options(obfuscate_names=True)
    subsetter = subset.Subsetter(options)
    subsetter.populate(glyphs=font.getGlyphOrder())
    subsetter.subset(font)

    # After obfuscation, all names should use an id >= 256, except for id 5,
    # which is not obfuscated.
    visitor = NameRecordVisitor()
    visitor.TABLES = ("STAT", "fvar")
    visitor.visit(font)
    assert all(id >= 256 or id == 5 for id in visitor.seen)


if __name__ == "__main__":
    sys.exit(unittest.main())
