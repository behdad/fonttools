from fontTools.fontBuilder import FontBuilder
from fontTools.misc.fixedTools import otRound
from fontTools.misc.roundTools import noRound
from fontTools.misc.testTools import getXML, parseXML
from fontTools.misc.transform import Transform
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.recordingPen import RecordingPen, RecordingPointPen
from fontTools.pens.pointPen import PointToSegmentPen
from fontTools.ttLib import TTFont, newTable, TTLibError
from fontTools.ttLib.beyond64k import upper_tables
from fontTools.ttLib.tables._g_l_y_f import (
    Glyph,
    GlyphCoordinates,
    GlyphComponent,
    dropImpliedOnCurvePoints,
    flagOnCurve,
    flagCubic,
    ARGS_ARE_XY_VALUES,
    SCALED_COMPONENT_OFFSET,
    UNSCALED_COMPONENT_OFFSET,
    WE_HAVE_A_SCALE,
    WE_HAVE_A_TWO_BY_TWO,
    WE_HAVE_AN_X_AND_Y_SCALE,
)
from fontTools.ttLib.tables import ttProgram
import sys
import struct
import array
from collections.abc import ValuesView, ItemsView
from copy import deepcopy
from io import StringIO, BytesIO
from pathlib import Path
import itertools
import pytest
import re
import os
import unittest


class GlyphCoordinatesTest(object):
    def test_translate(self):
        g = GlyphCoordinates([(1, 2)])
        g.translate((0.5, 0))
        assert g == GlyphCoordinates([(1.5, 2.0)])

    def test_scale(self):
        g = GlyphCoordinates([(1, 2)])
        g.scale((0.5, 0))
        assert g == GlyphCoordinates([(0.5, 0.0)])

    def test_transform(self):
        g = GlyphCoordinates([(1, 2)])
        g.transform(((0.5, 0), (0.2, 0.5)))
        assert g[0] == GlyphCoordinates([(0.9, 1.0)])[0]

    def test__eq__(self):
        g = GlyphCoordinates([(1, 2)])
        g2 = GlyphCoordinates([(1.0, 2)])
        g3 = GlyphCoordinates([(1.5, 2)])
        assert g == g2
        assert not g == g3
        assert not g2 == g3
        assert not g == object()

    def test__ne__(self):
        g = GlyphCoordinates([(1, 2)])
        g2 = GlyphCoordinates([(1.0, 2)])
        g3 = GlyphCoordinates([(1.5, 2)])
        assert not (g != g2)
        assert g != g3
        assert g2 != g3
        assert g != object()

    def test__pos__(self):
        g = GlyphCoordinates([(1, 2)])
        g2 = +g
        assert g == g2

    def test__neg__(self):
        g = GlyphCoordinates([(1, 2)])
        g2 = -g
        assert g2 == GlyphCoordinates([(-1, -2)])

    def test__round__(self):
        g = GlyphCoordinates([(-1.5, 2)])
        g2 = round(g)
        assert g2 == GlyphCoordinates([(-1, 2)])

    def test__add__(self):
        g1 = GlyphCoordinates([(1, 2)])
        g2 = GlyphCoordinates([(3, 4)])
        g3 = GlyphCoordinates([(4, 6)])
        assert g1 + g2 == g3
        assert g1 + (1, 1) == GlyphCoordinates([(2, 3)])
        with pytest.raises(TypeError) as excinfo:
            assert g1 + object()
        assert "unsupported operand" in str(excinfo.value)

    def test__sub__(self):
        g1 = GlyphCoordinates([(1, 2)])
        g2 = GlyphCoordinates([(3, 4)])
        g3 = GlyphCoordinates([(-2, -2)])
        assert g1 - g2 == g3
        assert g1 - (1, 1) == GlyphCoordinates([(0, 1)])
        with pytest.raises(TypeError) as excinfo:
            assert g1 - object()
        assert "unsupported operand" in str(excinfo.value)

    def test__rsub__(self):
        g = GlyphCoordinates([(1, 2)])
        # other + (-self)
        assert (1, 1) - g == GlyphCoordinates([(0, -1)])

    def test__mul__(self):
        g = GlyphCoordinates([(1, 2)])
        assert g * 3 == GlyphCoordinates([(3, 6)])
        assert g * (3, 2) == GlyphCoordinates([(3, 4)])
        assert g * (1, 1) == g
        with pytest.raises(TypeError) as excinfo:
            assert g * object()
        assert "unsupported operand" in str(excinfo.value)

    def test__truediv__(self):
        g = GlyphCoordinates([(1, 2)])
        assert g / 2 == GlyphCoordinates([(0.5, 1)])
        assert g / (1, 2) == GlyphCoordinates([(1, 1)])
        assert g / (1, 1) == g
        with pytest.raises(TypeError) as excinfo:
            assert g / object()
        assert "unsupported operand" in str(excinfo.value)

    def test__iadd__(self):
        g = GlyphCoordinates([(1, 2)])
        g += (0.5, 0)
        assert g == GlyphCoordinates([(1.5, 2.0)])
        g2 = GlyphCoordinates([(3, 4)])
        g += g2
        assert g == GlyphCoordinates([(4.5, 6.0)])

    def test__isub__(self):
        g = GlyphCoordinates([(1, 2)])
        g -= (0.5, 0)
        assert g == GlyphCoordinates([(0.5, 2.0)])
        g2 = GlyphCoordinates([(3, 4)])
        g -= g2
        assert g == GlyphCoordinates([(-2.5, -2.0)])

    def __test__imul__(self):
        g = GlyphCoordinates([(1, 2)])
        g *= (2, 0.5)
        g *= 2
        assert g == GlyphCoordinates([(4.0, 2.0)])
        g = GlyphCoordinates([(1, 2)])
        g *= 2
        assert g == GlyphCoordinates([(2, 4)])

    def test__itruediv__(self):
        g = GlyphCoordinates([(1, 3)])
        g /= (0.5, 1.5)
        g /= 2
        assert g == GlyphCoordinates([(1.0, 1.0)])

    def test__bool__(self):
        g = GlyphCoordinates([])
        assert bool(g) == False
        g = GlyphCoordinates([(0, 0), (0.0, 0)])
        assert bool(g) == True
        g = GlyphCoordinates([(0, 0), (1, 0)])
        assert bool(g) == True
        g = GlyphCoordinates([(0, 0.5), (0, 0)])
        assert bool(g) == True

    def test_double_precision_float(self):
        # https://github.com/fonttools/fonttools/issues/963
        afloat = 242.50000000000003
        g = GlyphCoordinates([(afloat, 0)])
        g.toInt()
        # this would return 242 if the internal array.array typecode is 'f',
        # since the Python float is truncated to a C float.
        # when using typecode 'd' it should return the correct value 243
        assert g[0][0] == otRound(afloat)

    def test__checkFloat_overflow(self):
        g = GlyphCoordinates([(1, 1)])
        g.append((0x8000, 0))
        assert list(g.array) == [1.0, 1.0, 32768.0, 0.0]


CURR_DIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
DATA_DIR = os.path.join(CURR_DIR, "data")

GLYF_TTX = os.path.join(DATA_DIR, "_g_l_y_f_outline_flag_bit6.ttx")
GLYF_BIN = os.path.join(DATA_DIR, "_g_l_y_f_outline_flag_bit6.glyf.bin")
HEAD_BIN = os.path.join(DATA_DIR, "_g_l_y_f_outline_flag_bit6.head.bin")
LOCA_BIN = os.path.join(DATA_DIR, "_g_l_y_f_outline_flag_bit6.loca.bin")
MAXP_BIN = os.path.join(DATA_DIR, "_g_l_y_f_outline_flag_bit6.maxp.bin")
INST_TTX = os.path.join(DATA_DIR, "_g_l_y_f_instructions.ttx")


def strip_ttLibVersion(string):
    return re.sub(' ttLibVersion=".*"', "", string)


class GlyfTableTest(unittest.TestCase):
    def __init__(self, methodName):
        unittest.TestCase.__init__(self, methodName)
        # Python 3 renamed assertRaisesRegexp to assertRaisesRegex,
        # and fires deprecation warnings if a program uses the old name.
        if not hasattr(self, "assertRaisesRegex"):
            self.assertRaisesRegex = self.assertRaisesRegexp

    @classmethod
    def setUpClass(cls):
        with open(GLYF_BIN, "rb") as f:
            cls.glyfData = f.read()
        with open(HEAD_BIN, "rb") as f:
            cls.headData = f.read()
        with open(LOCA_BIN, "rb") as f:
            cls.locaData = f.read()
        with open(MAXP_BIN, "rb") as f:
            cls.maxpData = f.read()
        with open(GLYF_TTX, "r") as f:
            cls.glyfXML = strip_ttLibVersion(f.read()).splitlines()

    def test_toXML(self):
        font = TTFont(sfntVersion="\x00\x01\x00\x00")
        glyfTable = font["glyf"] = newTable("glyf")
        font["head"] = newTable("head")
        font["loca"] = newTable("loca")
        font["maxp"] = newTable("maxp")
        font["maxp"].decompile(self.maxpData, font)
        font["head"].decompile(self.headData, font)
        font["loca"].decompile(self.locaData, font)
        glyfTable.decompile(self.glyfData, font)
        out = StringIO()
        font.saveXML(out)
        glyfXML = strip_ttLibVersion(out.getvalue()).splitlines()
        self.assertEqual(glyfXML, self.glyfXML)

    def test_fromXML(self):
        font = TTFont(sfntVersion="\x00\x01\x00\x00")
        font.importXML(GLYF_TTX)
        glyfTable = font["glyf"]
        glyfData = glyfTable.compile(font)
        self.assertEqual(glyfData, self.glyfData)

    def test_instructions_roundtrip(self):
        font = TTFont(sfntVersion="\x00\x01\x00\x00")
        font.importXML(INST_TTX)
        glyfTable = font["glyf"]
        self.glyfData = glyfTable.compile(font)
        out = StringIO()
        font.saveXML(out)
        glyfXML = strip_ttLibVersion(out.getvalue()).splitlines()
        with open(INST_TTX, "r") as f:
            origXML = strip_ttLibVersion(f.read()).splitlines()
        self.assertEqual(glyfXML, origXML)

    def test_recursiveComponent(self):
        glyphSet = {}
        pen_dummy = TTGlyphPen(glyphSet)
        glyph_dummy = pen_dummy.glyph()
        glyphSet["A"] = glyph_dummy
        glyphSet["B"] = glyph_dummy
        pen_A = TTGlyphPen(glyphSet)
        pen_A.addComponent("B", (1, 0, 0, 1, 0, 0))
        pen_B = TTGlyphPen(glyphSet)
        pen_B.addComponent("A", (1, 0, 0, 1, 0, 0))
        glyph_A = pen_A.glyph()
        glyph_B = pen_B.glyph()
        glyphSet["A"] = glyph_A
        glyphSet["B"] = glyph_B
        with self.assertRaisesRegex(
            TTLibError, "glyph '.' contains a recursive component reference"
        ):
            glyph_A.getCoordinates(glyphSet)

    def _makeComponentGlyph(self, glyphSet, name, ref, dx, dy):
        pen = TTGlyphPen(glyphSet)
        pen.addComponent(ref, (1, 0, 0, 1, dx, dy))
        glyphSet[name] = pen.glyph()

    def test_recalcBounds_recursiveComponent(self):
        # Integer-translate-only components take the fast path
        # (tryRecalcBoundsComposite); a recursive reference there must raise
        # TTLibError just like the getCoordinates slow path, rather than let a
        # raw RecursionError escape.
        # https://github.com/fonttools/fonttools/issues/3899
        # A -> B -> A cycle, all plain integer translates.
        glyphSet = {}
        glyphSet["A"] = glyphSet["B"] = TTGlyphPen(glyphSet).glyph()
        self._makeComponentGlyph(glyphSet, "A", "B", 10, 0)
        self._makeComponentGlyph(glyphSet, "B", "A", 0, 10)
        # sanity check that this exercises the integer-translate fast path
        self.assertTrue(glyphSet["A"].components[0]._hasOnlyIntegerTranslate())
        with self.assertRaisesRegex(
            TTLibError, "glyph '.' contains a recursive component reference"
        ):
            glyphSet["A"].recalcBounds(glyphSet)
        # and via the boundsDone set that table__g_l_y_f.compile() passes
        with self.assertRaisesRegex(
            TTLibError, "glyph '.' contains a recursive component reference"
        ):
            glyphSet["A"].recalcBounds(glyphSet, boundsDone=set())

    def test_recalcBounds_selfReferencingComponent(self):
        glyphSet = {}
        glyphSet["A"] = TTGlyphPen(glyphSet).glyph()
        self._makeComponentGlyph(glyphSet, "A", "A", 5, 5)
        with self.assertRaisesRegex(
            TTLibError, "glyph 'A' contains a recursive component reference"
        ):
            glyphSet["A"].recalcBounds(glyphSet)

    def test_recalcBounds_acyclicComposite(self):
        # A valid acyclic integer-translate composite must still compute the
        # correct bounds (the recursion guard must not affect normal glyphs).
        glyphSet = {}
        pen = TTGlyphPen(glyphSet)
        pen.moveTo((5, 5))
        pen.lineTo((10, 10))
        pen.lineTo((10, 5))
        pen.lineTo((5, 5))
        pen.closePath()
        glyphSet["base"] = pen.glyph()
        self._makeComponentGlyph(glyphSet, "A", "base", 100, 200)
        glyphSet["base"].recalcBounds(glyphSet)
        glyphSet["A"].recalcBounds(glyphSet, boundsDone=set())
        self.assertEqual(
            (
                glyphSet["A"].xMin,
                glyphSet["A"].yMin,
                glyphSet["A"].xMax,
                glyphSet["A"].yMax,
            ),
            (105, 205, 110, 210),
        )

    def test_trim_remove_hinting_composite_glyph(self):
        glyphSet = {"dummy": TTGlyphPen(None).glyph()}

        pen = TTGlyphPen(glyphSet)
        pen.addComponent("dummy", (1, 0, 0, 1, 0, 0))
        composite = pen.glyph()
        p = ttProgram.Program()
        p.fromAssembly(["SVTCA[0]"])
        composite.program = p
        glyphSet["composite"] = composite

        glyfTable = newTable("glyf")
        glyfTable.glyphs = glyphSet
        glyfTable.glyphOrder = sorted(glyphSet)

        composite.compact(glyfTable)

        self.assertTrue(hasattr(composite, "data"))

        # remove hinting from the compacted composite glyph, without expanding it
        composite.trim(remove_hinting=True)

        # check that, after expanding the glyph, we have no instructions
        composite.expand(glyfTable)
        self.assertFalse(hasattr(composite, "program"))

        # now remove hinting from expanded composite glyph
        composite.program = p
        composite.trim(remove_hinting=True)

        # check we have no instructions
        self.assertFalse(hasattr(composite, "program"))

        composite.compact(glyfTable)

    def test_bit6_draw_to_pen_issue1771(self):
        # https://github.com/fonttools/fonttools/issues/1771
        font = TTFont(sfntVersion="\x00\x01\x00\x00")
        # glyph00003 contains a bit 6 flag on the first point,
        # which triggered the issue
        font.importXML(GLYF_TTX)
        glyfTable = font["glyf"]
        pen = RecordingPen()
        glyfTable["glyph00003"].draw(pen, glyfTable=glyfTable)
        expected = [
            ("moveTo", ((501, 1430),)),
            ("lineTo", ((683, 1430),)),
            ("lineTo", ((1172, 0),)),
            ("lineTo", ((983, 0),)),
            ("lineTo", ((591, 1193),)),
            ("lineTo", ((199, 0),)),
            ("lineTo", ((12, 0),)),
            ("closePath", ()),
            ("moveTo", ((249, 514),)),
            ("lineTo", ((935, 514),)),
            ("lineTo", ((935, 352),)),
            ("lineTo", ((249, 352),)),
            ("closePath", ()),
        ]
        self.assertEqual(pen.value, expected)

    def test_bit6_draw_to_pointpen(self):
        # https://github.com/fonttools/fonttools/issues/1771
        font = TTFont(sfntVersion="\x00\x01\x00\x00")
        # glyph00003 contains a bit 6 flag on the first point
        # which triggered the issue
        font.importXML(GLYF_TTX)
        glyfTable = font["glyf"]
        pen = RecordingPointPen()
        glyfTable["glyph00003"].drawPoints(pen, glyfTable=glyfTable)
        expected = [
            ("beginPath", (), {}),
            ("addPoint", ((501, 1430), "line", False, None), {}),
            ("addPoint", ((683, 1430), "line", False, None), {}),
            ("addPoint", ((1172, 0), "line", False, None), {}),
            ("addPoint", ((983, 0), "line", False, None), {}),
        ]
        self.assertEqual(pen.value[: len(expected)], expected)

    def test_draw_vs_drawpoints(self):
        font = TTFont(sfntVersion="\x00\x01\x00\x00")
        font.importXML(GLYF_TTX)
        glyfTable = font["glyf"]
        pen1 = RecordingPen()
        pen2 = RecordingPen()
        glyfTable["glyph00003"].draw(pen1, glyfTable)
        glyfTable["glyph00003"].drawPoints(PointToSegmentPen(pen2), glyfTable)
        self.assertEqual(pen1.value, pen2.value)

    def test_compile_empty_table(self):
        font = TTFont(sfntVersion="\x00\x01\x00\x00")
        font.importXML(GLYF_TTX)
        glyfTable = font["glyf"]
        # set all glyphs to zero contours
        glyfTable.glyphs = {glyphName: Glyph() for glyphName in font.getGlyphOrder()}
        glyfData = glyfTable.compile(font)
        self.assertEqual(glyfData, b"\x00")
        self.assertEqual(list(font["loca"]), [0] * (font["maxp"].numGlyphs + 1))

    def test_decompile_empty_table(self):
        font = TTFont()
        glyphNames = [".notdef", "space"]
        font.setGlyphOrder(glyphNames)
        font["loca"] = newTable("loca")
        font["loca"].locations = [0] * (len(glyphNames) + 1)
        font["glyf"] = newTable("glyf")
        font["glyf"].decompile(b"\x00", font)
        self.assertEqual(len(font["glyf"]), 2)
        self.assertEqual(font["glyf"][".notdef"].numberOfContours, 0)
        self.assertEqual(font["glyf"]["space"].numberOfContours, 0)

    def test_getPhantomPoints(self):
        # https://github.com/fonttools/fonttools/issues/2295
        font = TTFont()
        glyphNames = [".notdef"]
        font.setGlyphOrder(glyphNames)
        font["loca"] = newTable("loca")
        font["loca"].locations = [0] * (len(glyphNames) + 1)
        font["glyf"] = newTable("glyf")
        font["glyf"].decompile(b"\x00", font)
        font["hmtx"] = newTable("hmtx")
        font["hmtx"].metrics = {".notdef": (100, 0)}
        font["head"] = newTable("head")
        font["head"].unitsPerEm = 1000
        with pytest.deprecated_call():
            self.assertEqual(
                font["glyf"].getPhantomPoints(".notdef", font, 0),
                [(0, 0), (100, 0), (0, 0), (0, -1000)],
            )

    def test_getGlyphID(self):
        # https://github.com/fonttools/fonttools/pull/3301#discussion_r1360405861
        glyf = newTable("glyf")
        glyf.setGlyphOrder([".notdef", "a", "b"])
        glyf.glyphs = {}
        for glyphName in glyf.glyphOrder:
            glyf[glyphName] = Glyph()

        assert glyf.getGlyphID("a") == 1

        with pytest.raises(ValueError):
            glyf.getGlyphID("c")

        glyf["c"] = Glyph()
        assert glyf.getGlyphID("c") == 3

        del glyf["b"]
        assert glyf.getGlyphID("c") == 2

    # __setitem__ uses the reverse glyph map for O(1) membership; the tests below
    # check it keeps glyphOrder and the reverse map consistent across the
    # supported paths.

    def test_setitem_prepopulated_glyphOrder_no_duplicate(self):
        # with glyphOrder already populated, assigning a glyph by an
        # already-listed name must not re-append it to glyphOrder.
        glyf = newTable("glyf")
        glyf.glyphs = {}
        glyf.glyphOrder = [".notdef", "a", "b"]
        for name in list(glyf.glyphOrder):
            glyf[name] = Glyph()
        assert glyf.glyphOrder == [".notdef", "a", "b"]
        assert glyf.getGlyphID("b") == 2

    def test_setitem_appends_new_glyph(self):
        # assigning a name that isn't in glyphOrder appends it and resolves
        glyf = newTable("glyf")
        glyf.glyphs = {}
        glyf.glyphOrder = [".notdef", "a"]
        for name in list(glyf.glyphOrder):
            glyf[name] = Glyph()
        glyf["b"] = Glyph()
        assert glyf.glyphOrder == [".notdef", "a", "b"]
        assert glyf.getGlyphID("b") == 2

    def test_setitem_after_setGlyphOrder_reorder(self):
        # reordering through the public setGlyphOrder clears the reverse map, so
        # re-assigning an already-listed glyph afterwards must not duplicate it
        glyf = newTable("glyf")
        glyf.glyphs = {}
        glyf.glyphOrder = [".notdef", "a", "b"]
        for name in list(glyf.glyphOrder):
            glyf[name] = Glyph()
        glyf.setGlyphOrder(["b", "a", ".notdef"])
        glyf["a"] = Glyph()
        assert glyf.glyphOrder == ["b", "a", ".notdef"]
        assert glyf.getGlyphID("a") == 1

    def test_setitem_after_delitem(self):
        # deletion invalidates the reverse map and shifts later ids; a following
        # assignment must still keep glyphOrder and the map consistent
        glyf = newTable("glyf")
        glyf.glyphs = {}
        glyf.glyphOrder = [".notdef", "a", "b"]
        for name in list(glyf.glyphOrder):
            glyf[name] = Glyph()
        del glyf["a"]
        assert glyf.glyphOrder == [".notdef", "b"]
        glyf["c"] = Glyph()
        assert glyf.glyphOrder == [".notdef", "b", "c"]
        assert glyf.getGlyphID("c") == 2


class GlyphTest:
    def test_getCoordinates(self):
        glyphSet = {}
        pen = TTGlyphPen(glyphSet)
        pen.moveTo((0, 0))
        pen.lineTo((100, 0))
        pen.lineTo((100, 100))
        pen.lineTo((0, 100))
        pen.closePath()
        # simple contour glyph
        glyphSet["a"] = a = pen.glyph()

        assert a.getCoordinates(glyphSet) == (
            GlyphCoordinates([(0, 0), (100, 0), (100, 100), (0, 100)]),
            [3],
            array.array("B", [1, 1, 1, 1]),
        )

        # composite glyph with only XY offset
        pen = TTGlyphPen(glyphSet)
        pen.addComponent("a", (1, 0, 0, 1, 10, 20))
        glyphSet["b"] = b = pen.glyph()

        assert b.getCoordinates(glyphSet) == (
            GlyphCoordinates([(10, 20), (110, 20), (110, 120), (10, 120)]),
            [3],
            array.array("B", [1, 1, 1, 1]),
        )

        # composite glyph with a scale (and referencing another composite glyph)
        pen = TTGlyphPen(glyphSet)
        pen.addComponent("b", (0.5, 0, 0, 0.5, 0, 0))
        glyphSet["c"] = c = pen.glyph()

        assert c.getCoordinates(glyphSet) == (
            GlyphCoordinates([(5, 10), (55, 10), (55, 60), (5, 60)]),
            [3],
            array.array("B", [1, 1, 1, 1]),
        )

        # composite glyph with unscaled offset (MS-style)
        pen = TTGlyphPen(glyphSet)
        pen.addComponent("a", (0.5, 0, 0, 0.5, 10, 20))
        glyphSet["d"] = d = pen.glyph()
        d.components[0].flags |= UNSCALED_COMPONENT_OFFSET

        assert d.getCoordinates(glyphSet) == (
            GlyphCoordinates([(10, 20), (60, 20), (60, 70), (10, 70)]),
            [3],
            array.array("B", [1, 1, 1, 1]),
        )

        # composite glyph with a scaled offset (Apple-style)
        pen = TTGlyphPen(glyphSet)
        pen.addComponent("a", (0.5, 0, 0, 0.5, 10, 20))
        glyphSet["e"] = e = pen.glyph()
        e.components[0].flags |= SCALED_COMPONENT_OFFSET

        assert e.getCoordinates(glyphSet) == (
            GlyphCoordinates([(5, 10), (55, 10), (55, 60), (5, 60)]),
            [3],
            array.array("B", [1, 1, 1, 1]),
        )

        # composite glyph where the 2nd and 3rd components use anchor points
        pen = TTGlyphPen(glyphSet)
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        glyphSet["f"] = f = pen.glyph()

        comp1 = GlyphComponent()
        comp1.glyphName = "a"
        # aling the new component's pt 0 to pt 2 of contour points added so far
        comp1.firstPt = 2
        comp1.secondPt = 0
        comp1.flags = 0
        f.components.append(comp1)

        comp2 = GlyphComponent()
        comp2.glyphName = "a"
        # aling the new component's pt 0 to pt 6 of contour points added so far
        comp2.firstPt = 6
        comp2.secondPt = 0
        comp2.transform = [[0.707107, 0.707107], [-0.707107, 0.707107]]  # rotate 45 deg
        comp2.flags = WE_HAVE_A_TWO_BY_TWO
        f.components.append(comp2)

        coords, end_pts, flags = f.getCoordinates(glyphSet)
        assert end_pts == [3, 7, 11]
        assert flags == array.array("B", [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
        assert list(sum(coords, ())) == pytest.approx(
            [
                0,
                0,
                100,
                0,
                100,
                100,
                0,
                100,
                100,
                100,
                200,
                100,
                200,
                200,
                100,
                200,
                200,
                200,
                270.7107,
                270.7107,
                200.0,
                341.4214,
                129.2893,
                270.7107,
            ]
        )

    def test_get_components_nested(self):
        # check that getCoordinates will correctly round with nested
        glyphSet = {}

        pen = TTGlyphPen(glyphSet)
        pen.moveTo((372, 736))
        pen.lineTo((68, 426))
        pen.qCurveTo((68.0, 426.0), (64.25, 414.0), (62.5, 386.25), (64.0, 372.0))
        pen.lineTo((0, 100))
        pen.lineTo((372, 736))
        pen.closePath()

        # turn off rounding here; we're pretending that this glyph has been
        # through cubic->quadratic conversion, which introduced some floats
        glyphSet["base"] = pen.glyph(round=noRound)

        pen = TTGlyphPen(glyphSet)
        # this is a simple translation
        pen.addComponent("base", (1, 0, 0, 1, 10, 10))
        glyphSet["simpleXform"] = pen.glyph()

        pen = TTGlyphPen(glyphSet)
        # this is flipped on the y axis
        pen.addComponent("simpleXform", (-1, 0, 0, -1, 834, 793))
        glyphSet["nestedTrickyXForm"] = trickyXForm = pen.glyph()

        coords, _, _ = trickyXForm.getCoordinates(glyphSet, round=otRound)
        assert all(
            (int(p[0]), int(p[1])) == p for p in coords
        ), f"{[p for p in coords]}"

    @pytest.mark.parametrize("offset", [0, 1, 0.4, 0.5, 0.6, -0.4, -0.5, -0.6, -1.5])
    @pytest.mark.parametrize(
        "offset_flags", [0, SCALED_COMPONENT_OFFSET, UNSCALED_COMPONENT_OFFSET]
    )
    @pytest.mark.parametrize("nested", [False, True])
    def test_get_coordinates_round_component_offsets(
        self, offset, offset_flags, nested
    ):
        glyphs = {}
        pen = TTGlyphPen(glyphs)
        pen.moveTo((0, 0))
        pen.lineTo((1, 0))
        pen.lineTo((1, 1))
        pen.closePath()
        glyphs["base"] = pen.glyph()
        pen = TTGlyphPen(glyphs)
        pen.addComponent("base", (1.5, 0, 0, 1.5, 0, 0))
        glyphs["inner"] = pen.glyph()
        component = glyphs["inner"].components[0]
        component.x, component.y = offset, -offset
        component.flags = offset_flags
        glyph = glyphs["inner"]
        if nested:
            pen = TTGlyphPen(glyphs)
            pen.addComponent("inner", (0.5, 0, 0, 0.5, 0, 0))
            glyph = pen.glyph()

        def expected(x, y):
            scale = 1.5 if offset_flags == SCALED_COMPONENT_OFFSET else 1
            result = [
                (1.5 * px + scale * x, 1.5 * py + scale * y)
                for px, py in glyphs["base"].coordinates
            ]
            return [(px * 0.5, py * 0.5) for px, py in result] if nested else result

        assert list(glyph.getCoordinates(glyphs, round=otRound)[0]) == expected(
            otRound(offset), otRound(-offset)
        )
        for actual, wanted in zip(
            glyph.getCoordinates(glyphs)[0], expected(offset, -offset), strict=True
        ):
            assert actual == pytest.approx(wanted)
        assert (component.x, component.y) == (offset, -offset)

    def test_getCompositeMaxpValues(self):
        # https://github.com/fonttools/fonttools/issues/2044
        glyphSet = {}
        pen = TTGlyphPen(glyphSet)  # empty non-composite glyph
        glyphSet["fraction"] = pen.glyph()
        glyphSet["zero.numr"] = pen.glyph()
        pen = TTGlyphPen(glyphSet)
        pen.addComponent("zero.numr", (1, 0, 0, 1, 0, 0))
        glyphSet["zero.dnom"] = pen.glyph()
        pen = TTGlyphPen(glyphSet)
        pen.addComponent("zero.numr", (1, 0, 0, 1, 0, 0))
        pen.addComponent("fraction", (1, 0, 0, 1, 0, 0))
        pen.addComponent("zero.dnom", (1, 0, 0, 1, 0, 0))
        glyphSet["percent"] = pen.glyph()
        pen = TTGlyphPen(glyphSet)
        pen.addComponent("zero.numr", (1, 0, 0, 1, 0, 0))
        pen.addComponent("fraction", (1, 0, 0, 1, 0, 0))
        pen.addComponent("zero.dnom", (1, 0, 0, 1, 0, 0))
        pen.addComponent("zero.dnom", (1, 0, 0, 1, 0, 0))
        glyphSet["perthousand"] = pen.glyph()
        assert glyphSet["zero.dnom"].getCompositeMaxpValues(glyphSet)[2] == 1
        assert glyphSet["percent"].getCompositeMaxpValues(glyphSet)[2] == 2
        assert glyphSet["perthousand"].getCompositeMaxpValues(glyphSet)[2] == 2

    def test_recalcBounds_empty_components(self):
        glyphSet = {}
        pen = TTGlyphPen(glyphSet)
        # empty simple glyph
        foo = glyphSet["foo"] = pen.glyph()

        pen.moveTo((5, 5))
        pen.lineTo((10, 10))
        pen.lineTo((10, 5))
        pen.lineTo((5, 5))
        pen.closePath()

        # non-empty simple glyph
        doo = glyphSet["doo"] = pen.glyph()

        pen = TTGlyphPen(glyphSet)
        # use the empty 'foo' glyph as a component in 'bar' with some x/y offsets
        pen.addComponent("foo", (1, 0, 0, 1, -80, 50))
        # and use the non-empty 'doo' glyph at origin
        pen.addComponent("doo", (1, 0, 0, 1, 0, 0))
        bar = glyphSet["bar"] = pen.glyph()

        foo.recalcBounds(glyphSet)
        doo.recalcBounds(glyphSet)
        bar.recalcBounds(glyphSet)

        assert (foo.xMin, foo.yMin, foo.xMax, foo.yMax) == (0, 0, 0, 0)
        assert (doo.xMin, doo.yMin, doo.xMax, doo.yMax) == (5, 5, 10, 10)
        # the composite should have bounds identical to 'doo';
        # the empty foo glyph should do nothing
        assert (bar.xMin, bar.yMin, bar.xMax, bar.yMax) == (5, 5, 10, 10)

    def test_recalcBounds_empty_components_nested(self):
        # this differs from the above in an important way: it has a 'foofoo'
        # glyph, which is a composite glyph, where none of its components
        # have any contours; we want to check that when this glyph is referenced
        # it is also treated as not contributing to the parent's bounds.

        glyphSet = {}
        pen = TTGlyphPen(glyphSet)
        # empty simple glyph
        foo = glyphSet["foo"] = pen.glyph()

        pen.addComponent("foo", (1, 0, 0, 1, 20, 20))
        foofoo = glyphSet["foofoo"] = pen.glyph()

        pen = TTGlyphPen(glyphSet)

        pen.moveTo((5, 5))
        pen.lineTo((10, 10))
        pen.lineTo((10, 5))
        pen.lineTo((5, 5))
        pen.closePath()

        # non-empty simple glyph
        doo = glyphSet["doo"] = pen.glyph()

        pen = TTGlyphPen(glyphSet)
        # use the empty 'foo' glyph as a component in 'bar' with some x/y offsets
        pen.addComponent("foofoo", (1, 0, 0, 1, 0, 0))
        # and use the non-empty 'doo' glyph at origin
        pen.addComponent("doo", (1, 0, 0, 1, 0, 0))
        bar = glyphSet["bar"] = pen.glyph()

        foo.recalcBounds(glyphSet)
        foofoo.recalcBounds(glyphSet)
        doo.recalcBounds(glyphSet)
        bar.recalcBounds(glyphSet)

        assert (foo.xMin, foo.yMin, foo.xMax, foo.yMax) == (0, 0, 0, 0)
        assert (doo.xMin, doo.yMin, doo.xMax, doo.yMax) == (5, 5, 10, 10)
        # the composite should have bounds identical to 'doo';
        # the empty foo glyph should do nothing
        assert (bar.xMin, bar.yMin, bar.xMax, bar.yMax) == (5, 5, 10, 10)


class GlyphComponentTest:
    def test_toXML_no_transform(self):
        comp = GlyphComponent()
        comp.glyphName = "a"
        comp.flags = ARGS_ARE_XY_VALUES
        comp.x, comp.y = 1, 2

        assert getXML(comp.toXML) == [
            '<component glyphName="a" x="1" y="2" flags="0x2"/>'
        ]

    def test_toXML_transform_scale(self):
        comp = GlyphComponent()
        comp.glyphName = "a"
        comp.flags = ARGS_ARE_XY_VALUES | WE_HAVE_A_SCALE
        comp.x, comp.y = 1, 2

        comp.transform = [[0.2999878, 0], [0, 0.2999878]]
        assert getXML(comp.toXML) == [
            '<component glyphName="a" x="1" y="2" scale="0.3" flags="0xa"/>'
        ]

    def test_toXML_transform_xy_scale(self):
        comp = GlyphComponent()
        comp.glyphName = "a"
        comp.flags = ARGS_ARE_XY_VALUES | WE_HAVE_AN_X_AND_Y_SCALE
        comp.x, comp.y = 1, 2

        comp.transform = [[0.5999756, 0], [0, 0.2999878]]
        assert getXML(comp.toXML) == [
            '<component glyphName="a" x="1" y="2" scalex="0.6" '
            'scaley="0.3" flags="0x42"/>'
        ]

    def test_toXML_transform_2x2_scale(self):
        comp = GlyphComponent()
        comp.glyphName = "a"
        comp.flags = ARGS_ARE_XY_VALUES | WE_HAVE_A_TWO_BY_TWO
        comp.x, comp.y = 1, 2

        comp.transform = [[0.5999756, -0.2000122], [0.2000122, 0.2999878]]
        assert getXML(comp.toXML) == [
            '<component glyphName="a" x="1" y="2" scalex="0.6" scale01="-0.2" '
            'scale10="0.2" scaley="0.3" flags="0x82"/>'
        ]

    def test_fromXML_no_transform(self):
        comp = GlyphComponent()
        for name, attrs, content in parseXML(
            ['<component glyphName="a" x="1" y="2" flags="0x2"/>']
        ):
            comp.fromXML(name, attrs, content, ttFont=None)

        assert comp.glyphName == "a"
        assert comp.flags & ARGS_ARE_XY_VALUES != 0
        assert (comp.x, comp.y) == (1, 2)
        assert not hasattr(comp, "transform")

    def test_fromXML_transform_scale(self):
        comp = GlyphComponent()
        for name, attrs, content in parseXML(
            ['<component glyphName="a" x="1" y="2" scale="0.3" flags="0xa"/>']
        ):
            comp.fromXML(name, attrs, content, ttFont=None)

        assert comp.glyphName == "a"
        assert comp.flags & ARGS_ARE_XY_VALUES != 0
        assert comp.flags & WE_HAVE_A_SCALE != 0
        assert (comp.x, comp.y) == (1, 2)
        assert hasattr(comp, "transform")
        for value, expected in zip(
            itertools.chain(*comp.transform), [0.2999878, 0, 0, 0.2999878]
        ):
            assert value == pytest.approx(expected)

    def test_fromXML_transform_xy_scale(self):
        comp = GlyphComponent()
        for name, attrs, content in parseXML(
            [
                '<component glyphName="a" x="1" y="2" scalex="0.6" '
                'scaley="0.3" flags="0x42"/>'
            ]
        ):
            comp.fromXML(name, attrs, content, ttFont=None)

        assert comp.glyphName == "a"
        assert comp.flags & ARGS_ARE_XY_VALUES != 0
        assert comp.flags & WE_HAVE_AN_X_AND_Y_SCALE != 0
        assert (comp.x, comp.y) == (1, 2)
        assert hasattr(comp, "transform")
        for value, expected in zip(
            itertools.chain(*comp.transform), [0.5999756, 0, 0, 0.2999878]
        ):
            assert value == pytest.approx(expected)

    def test_fromXML_transform_2x2_scale(self):
        comp = GlyphComponent()
        for name, attrs, content in parseXML(
            [
                '<component glyphName="a" x="1" y="2" scalex="0.6" scale01="-0.2" '
                'scale10="0.2" scaley="0.3" flags="0x82"/>'
            ]
        ):
            comp.fromXML(name, attrs, content, ttFont=None)

        assert comp.glyphName == "a"
        assert comp.flags & ARGS_ARE_XY_VALUES != 0
        assert comp.flags & WE_HAVE_A_TWO_BY_TWO != 0
        assert (comp.x, comp.y) == (1, 2)
        assert hasattr(comp, "transform")
        for value, expected in zip(
            itertools.chain(*comp.transform),
            [0.5999756, -0.2000122, 0.2000122, 0.2999878],
        ):
            assert value == pytest.approx(expected)

    def test_toXML_reference_points(self):
        comp = GlyphComponent()
        comp.glyphName = "a"
        comp.flags = 0
        comp.firstPt = 1
        comp.secondPt = 2

        assert getXML(comp.toXML) == [
            '<component glyphName="a" firstPt="1" secondPt="2" flags="0x0"/>'
        ]

    def test_compile_for_speed(self):
        glyph = Glyph()
        glyph.numberOfContours = 1
        glyph.coordinates = GlyphCoordinates(
            [(0, 0), (1, 0), (1, 0), (1, 1), (1, 1), (0, 1), (0, 1)]
        )
        glyph.flags = array.array("B", [flagOnCurve] + [flagCubic] * 6)
        glyph.endPtsOfContours = [6]
        glyph.program = ttProgram.Program()

        glyph.expand(None)
        sizeBytes = glyph.compile(None, optimizeSize=True)
        glyph.expand(None)
        speedBytes = glyph.compile(None, optimizeSize=False)

        assert len(sizeBytes) < len(speedBytes)

        for data in sizeBytes, speedBytes:
            glyph = Glyph(data)

            pen = RecordingPen()
            glyph.draw(pen, None)

            assert pen.value == [
                ("moveTo", ((0, 0),)),
                ("curveTo", ((1, 0), (1, 0), (1.0, 0.5))),
                ("curveTo", ((1, 1), (1, 1), (0.5, 1.0))),
                ("curveTo", ((0, 1), (0, 1), (0, 0))),
                ("closePath", ()),
            ]

    def test_fromXML_reference_points(self):
        comp = GlyphComponent()
        for name, attrs, content in parseXML(
            ['<component glyphName="a" firstPt="1" secondPt="2" flags="0x0"/>']
        ):
            comp.fromXML(name, attrs, content, ttFont=None)

        assert comp.glyphName == "a"
        assert comp.flags == 0
        assert (comp.firstPt, comp.secondPt) == (1, 2)
        assert not hasattr(comp, "transform")

    def test_items(self):
        glyf = newTable("glyf")
        glyf.glyphs = {}
        glyf.glyphOrder = [".notdef", "a", "b"]
        for name in glyf.glyphOrder:
            glyf[name] = Glyph()
        assert isinstance(glyf.items(), ItemsView)
        items = list(glyf.items())
        assert items == [
            (".notdef", glyf[".notdef"]),
            ("a", glyf["a"]),
            ("b", glyf["b"]),
        ]

    def test_items_lazy(self):
        font = TTFont(
            Path(__file__).parent.parent.parent / "ttx" / "data" / "TestTTF.ttf",
            lazy=True,
        )
        glyf = font["glyf"]
        assert isinstance(glyf.items(), ItemsView)
        items = list(glyf.items())
        assert items[0][1].numberOfContours == 2  # .notdef
        assert items == [
            (".notdef", glyf[".notdef"]),
            (".null", glyf[".null"]),
            ("CR", glyf["CR"]),
            ("space", glyf["space"]),
            ("period", glyf["period"]),
            ("ellipsis", glyf["ellipsis"]),
        ]

    def test_iter(self):
        glyf = newTable("glyf")
        glyf.glyphs = {}
        glyf.glyphOrder = [".notdef", "a", "b"]
        for name in glyf.glyphOrder:
            glyf[name] = Glyph()
        names = [name for name in glyf]
        assert names == [".notdef", "a", "b"]

    def test_iter_lazy(self):
        font = TTFont(
            Path(__file__).parent.parent.parent / "ttx" / "data" / "TestTTF.ttf",
            lazy=True,
        )
        glyf = font["glyf"]
        names = [name for name in glyf]
        assert names == [".notdef", ".null", "CR", "space", "period", "ellipsis"]

    def test_values(self):
        glyf = newTable("glyf")
        glyf.glyphs = {}
        glyf.glyphOrder = [".notdef", "a", "b"]
        for name in glyf.glyphOrder:
            glyf[name] = Glyph()
        assert isinstance(glyf.values(), ValuesView)
        glyphs = list(glyf.values())
        assert glyphs == [glyf[".notdef"], glyf["a"], glyf["b"]]

    def test_values_lazy(self):
        font = TTFont(
            Path(__file__).parent.parent.parent / "ttx" / "data" / "TestTTF.ttf",
            lazy=True,
        )
        glyf = font["glyf"]
        assert isinstance(glyf.values(), ValuesView)
        glyphs = list(glyf.values())
        assert glyphs[0].numberOfContours == 2  # .notdef
        assert glyphs == [
            glyf[".notdef"],
            glyf[".null"],
            glyf["CR"],
            glyf["space"],
            glyf["period"],
            glyf["ellipsis"],
        ]


class GlyphCubicTest:
    @pytest.mark.parametrize("count", [2, 4, 8])
    @pytest.mark.parametrize("cubic", [False, True])
    def test_drawPoints_all_offcurve(self, count, cubic):
        glyph = Glyph()
        glyph.numberOfContours = 1
        glyph.coordinates = GlyphCoordinates([(i, i % 2) for i in range(count)])
        glyph.flags = array.array("B", [flagCubic if cubic else 0] * count)
        glyph.endPtsOfContours = [count - 1]
        glyph.program = ttProgram.Program()
        pen = RecordingPointPen()

        if cubic:
            with pytest.raises(NotImplementedError, match="All-off-curve cubic"):
                glyph.drawPoints(pen, None)
            assert pen.value == []
            glyph.draw(RecordingPen(), None)
        else:
            glyph.drawPoints(pen, None)
            assert [
                args[0] for op, args, kwargs in pen.value if op == "addPoint"
            ] == list(glyph.coordinates)

    @pytest.mark.parametrize("table_tag", ["glyf", "GLYF"])
    @pytest.mark.parametrize("optimize_size", [False, True])
    def test_cubic_requires_extended_serialization(self, table_tag, optimize_size):
        glyph = Glyph()
        glyph.numberOfContours = 1
        glyph.coordinates = GlyphCoordinates([(0, 0), (0, 100), (100, 100), (100, 0)])
        glyph.flags = bytearray([flagOnCurve, flagCubic, flagCubic, flagOnCurve])
        glyph.endPtsOfContours = [3]
        glyph.program = ttProgram.Program()
        table = newTable(table_tag)

        # Drawing an in-memory outline must keep the actual segment type.
        pen = RecordingPen()
        glyph.draw(pen, table)
        assert ("curveTo", ((0, 100), (100, 100), (100, 0))) in pen.value
        point_pen = RecordingPointPen()
        glyph.drawPoints(point_pen, table)
        assert [
            args[1] for op, args, kwargs in point_pen.value if op == "addPoint"
        ] == ["line", None, None, "curve"]

        if table_tag == "glyf":
            with pytest.raises(TTLibError, match="extended GLYF"):
                glyph.compile(table, optimizeSize=optimize_size)
            with pytest.raises(TTLibError, match="extended GLYF"):
                getXML(lambda writer, font: glyph.toXML(writer, font, extended=False))
        else:
            data = glyph.compile(table, optimizeSize=optimize_size)
            reloaded = Glyph(data)
            reloaded.expand(table)
            assert reloaded.flags == glyph.flags
            after = RecordingPen()
            reloaded.draw(after, table)
            assert after.value == pen.value

    @pytest.mark.parametrize("table_tag", ["glyf", "GLYF"])
    def test_import_cubic_flags(self, table_tag):
        font = TTFont()
        font.setGlyphOrder(["a"])
        font[table_tag] = newTable(table_tag)
        xml = """<TTGlyph name="a"><contour>
            <pt x="0" y="0" on="1"/>
            <pt x="0" y="100" on="0" cubic="1"/>
            <pt x="100" y="100" on="0" cubic="1"/>
            <pt x="100" y="0" on="1"/>
        </contour><instructions/></TTGlyph>"""
        if table_tag == "glyf":
            with pytest.raises(TTLibError, match="extended GLYF"):
                for name, attrs, content in parseXML(xml):
                    font[table_tag].fromXML(name, attrs, content, font)
        else:
            for name, attrs, content in parseXML(xml):
                font[table_tag].fromXML(name, attrs, content, font)
            assert list(font[table_tag]["a"].flags) == [1, flagCubic, flagCubic, 1]

    def test_drawPoints_rejects_later_cubic_contour_atomically(self):
        glyph = Glyph()
        glyph.numberOfContours = 2
        glyph.coordinates = GlyphCoordinates(
            [(0, 0), (10, 0), (10, 10), (20, 0), (30, 0), (30, 10), (20, 10)]
        )
        glyph.flags = array.array("B", [flagOnCurve] * 3 + [flagCubic] * 4)
        glyph.endPtsOfContours = [2, 6]
        pen = RecordingPointPen()
        with pytest.raises(NotImplementedError, match="All-off-curve cubic"):
            glyph.drawPoints(pen, None)
        assert pen.value == []

    def test_roundtrip(self):
        font_path = os.path.join(DATA_DIR, "NotoSans-VF-cubic.subset.ttf")
        font = TTFont(font_path)
        upper_tables(
            font,
            tables={"glyf", "loca", "maxp", "hhea", "hmtx", "gvar"},
        )
        tables = [table_tag for table_tag in font.keys() if table_tag not in {"head"}]
        xml = StringIO()
        font.saveXML(xml)
        xml1 = StringIO()
        font.saveXML(xml1, tables=tables)
        xml.seek(0)
        font = TTFont()
        font.importXML(xml)
        ttf = BytesIO()
        font.save(ttf)
        ttf.seek(0)
        font = TTFont(ttf)
        xml2 = StringIO()
        font.saveXML(xml2, tables=tables)
        assert xml1.getvalue() == xml2.getvalue()

    def test_no_oncurves(self):
        glyph = Glyph()
        glyph.numberOfContours = 1
        glyph.coordinates = GlyphCoordinates(
            [(0, 0), (1, 0), (1, 0), (1, 1), (1, 1), (0, 1), (0, 1), (0, 0)]
        )
        glyph.flags = array.array("B", [flagCubic] * 8)
        glyph.endPtsOfContours = [7]
        glyph.program = ttProgram.Program()

        for i in range(2):
            if i == 1:
                glyph.compile(None)

            pen = RecordingPen()
            glyph.draw(pen, None)

            assert pen.value == [
                ("moveTo", ((0, 0),)),
                ("curveTo", ((0, 0), (1, 0), (1, 0))),
                ("curveTo", ((1, 0), (1, 1), (1, 1))),
                ("curveTo", ((1, 1), (0, 1), (0, 1))),
                ("curveTo", ((0, 1), (0, 0), (0, 0))),
                ("closePath", ()),
            ]

    def test_spline(self):
        glyph = Glyph()
        glyph.numberOfContours = 1
        glyph.coordinates = GlyphCoordinates(
            [(0, 0), (1, 0), (1, 0), (1, 1), (1, 1), (0, 1), (0, 1)]
        )
        glyph.flags = array.array("B", [flagOnCurve] + [flagCubic] * 6)
        glyph.endPtsOfContours = [6]
        glyph.program = ttProgram.Program()

        for i in range(2):
            if i == 1:
                glyph.compile(None)

            pen = RecordingPen()
            glyph.draw(pen, None)

            assert pen.value == [
                ("moveTo", ((0, 0),)),
                ("curveTo", ((1, 0), (1, 0), (1.0, 0.5))),
                ("curveTo", ((1, 1), (1, 1), (0.5, 1.0))),
                ("curveTo", ((0, 1), (0, 1), (0, 0))),
                ("closePath", ()),
            ]


@pytest.mark.parametrize("length", [0, 1, 0x8000, 0xFFFF])
@pytest.mark.parametrize("remove_hinting", [False, True])
@pytest.mark.parametrize("expanded", [False, True])
def test_zero_contour_instructions(length, remove_hinting, expanded):
    header = struct.pack(">hhhhh", 0, 0, 0, 0, 0)
    instructions = b"\x00" * length
    data = header + struct.pack(">H", length) + instructions
    glyph = Glyph(data + b"\x00\x00\x00")
    if expanded:
        glyph.expand(None)
        assert glyph.program.getBytecode() == instructions
    glyph.trim(remove_hinting=remove_hinting)
    if remove_hinting or not length:
        glyph.expand(None)
        assert not getattr(glyph, "program", None)
        assert glyph.compile(None) == b""
    else:
        if not expanded:
            assert glyph.data == data
        glyph.expand(None)
        assert glyph.program.getBytecode() == instructions
        assert glyph.compile(None) == data


@pytest.mark.parametrize("data", [b"", b"\x00" * 10, b"\x00" * 11])
@pytest.mark.parametrize("remove_hinting", [False, True])
def test_trim_zero_contour_without_instructions(data, remove_hinting):
    glyph = Glyph(data)
    glyph.trim(remove_hinting=remove_hinting)
    glyph.expand(None)
    assert glyph.compile(None) == b""


@pytest.mark.parametrize("split_glyphs", [False, True])
def test_zero_contour_instructions_xml(tmp_path, split_glyphs):
    font = TTFont(recalcTimestamp=False)
    font.setGlyphOrder([".notdef", "space"])
    font["glyf"] = glyf = newTable("glyf")
    instructions = b"\xb0\x00\x21"
    data = struct.pack(">hhhhhH", 0, 0, 0, 0, 0, len(instructions)) + instructions
    glyf.glyphs = {".notdef": Glyph(), "space": Glyph(data)}
    path = tmp_path / "empty.ttx"
    font.saveXML(path, tables=["GlyphOrder", "glyf"], splitGlyphs=split_glyphs)
    result = TTFont()
    result.importXML(path)
    assert result["glyf"]["space"].compile(result["glyf"]) == data


def build_interpolatable_glyphs(contours, *transforms):
    # given a list of lists of (point, flag) tuples (one per contour), build a Glyph
    # then make len(transforms) copies transformed accordingly, and return a
    # list of such interpolatable glyphs.
    glyph1 = Glyph()
    glyph1.numberOfContours = len(contours)
    glyph1.coordinates = GlyphCoordinates(
        [pt for contour in contours for pt, _flag in contour]
    )
    glyph1.flags = array.array(
        "B", [flag for contour in contours for _pt, flag in contour]
    )
    glyph1.endPtsOfContours = [
        sum(len(contour) for contour in contours[: i + 1]) - 1
        for i in range(len(contours))
    ]
    result = [glyph1]
    for t in transforms:
        glyph = deepcopy(glyph1)
        glyph.coordinates.transform((t[0:2], t[2:4]))
        glyph.coordinates.translate(t[4:6])
        result.append(glyph)
    return result


@pytest.mark.parametrize("extended", [False, True])
@pytest.mark.parametrize("wide_gid", [False, True])
@pytest.mark.parametrize("word_args", [False, True])
@pytest.mark.parametrize(
    "transform",
    [
        (0, ()),
        (WE_HAVE_A_SCALE, (0x2000,)),
        (WE_HAVE_AN_X_AND_Y_SCALE, (0x2000, 0x4000)),
        (WE_HAVE_A_TWO_BY_TWO, (0x2000, 0x1000, 0x1000, 0x4000)),
    ],
)
@pytest.mark.parametrize("remove_hinting", [False, True])
def test_trim_compact_composite(
    extended, wide_gid, word_args, transform, remove_hinting
):
    transform_flag, transform_values = transform
    header = bytes.fromhex("ffff 0000 0000 0064 0064")
    records = []
    for index, gid in enumerate((2, 1)):
        flags = ARGS_ARE_XY_VALUES | transform_flag
        if index == 0:
            flags |= 0x0020  # MORE_COMPONENTS
            if wide_gid:
                flags |= 0x2000  # GID_IS_24_BIT, reserved in lowercase glyf
        else:
            flags |= 0x0100  # WE_HAVE_INSTRUCTIONS
        if word_args:
            flags |= 0x0001  # ARG_1_AND_2_ARE_WORDS
        gid_size = 3 if extended and flags & 0x2000 else 2
        records.append(
            struct.pack(">H", flags)
            + gid.to_bytes(gid_size, "big")
            + struct.pack(">hh" if word_args else ">bb", 123, -42)
            + struct.pack(">" + "h" * len(transform_values), *transform_values)
        )
    program = bytes.fromhex("0003 b00121")
    data = header + b"".join(records) + program
    glyph = Glyph(data + b"\0\0\0")
    glyf = newTable("GLYF" if extended else "glyf")
    glyf.glyphOrder = [".notdef", "a", "b"]
    glyf.glyphs = {"composite": glyph}

    if remove_hinting:
        glyf.removeHinting()
        records[-1] = bytes([records[-1][0] & ~1]) + records[-1][1:]
        expected = header + b"".join(records)
    else:
        glyph.trim(extended=extended)
        expected = data

    assert glyph.data == expected
    glyph.expand(glyf)
    assert [comp.glyphName for comp in glyph.components] == ["b", "a"]
    assert [(comp.x, comp.y) for comp in glyph.components] == [(123, -42)] * 2
    assert hasattr(glyph, "program") == (not remove_hinting)


def test_dropImpliedOnCurvePoints_all_quad_off_curves():
    # Two interpolatable glyphs with same structure, the coordinates of one are 2x the
    # other; all the on-curve points are impliable in each one, thus are dropped from
    # both, leaving contours with off-curve points only.
    glyph1, glyph2 = build_interpolatable_glyphs(
        [
            [
                ((0, 1), flagOnCurve),
                ((1, 1), 0),
                ((1, 0), flagOnCurve),
                ((1, -1), 0),
                ((0, -1), flagOnCurve),
                ((-1, -1), 0),
                ((-1, 0), flagOnCurve),
                ((-1, 1), 0),
            ],
            [
                ((0, 2), flagOnCurve),
                ((2, 2), 0),
                ((2, 0), flagOnCurve),
                ((2, -2), 0),
                ((0, -2), flagOnCurve),
                ((-2, -2), 0),
                ((-2, 0), flagOnCurve),
                ((-2, 2), 0),
            ],
        ],
        Transform().scale(2.0),
    )
    # also add an empty glyph (will be ignored); we use this trick for 'sparse' masters
    glyph3 = Glyph()
    glyph3.numberOfContours = 0

    assert dropImpliedOnCurvePoints(glyph1, glyph2, glyph3) == {
        0,
        2,
        4,
        6,
        8,
        10,
        12,
        14,
    }

    assert glyph1.flags == glyph2.flags == array.array("B", [0, 0, 0, 0, 0, 0, 0, 0])
    assert glyph1.coordinates == GlyphCoordinates(
        [(1, 1), (1, -1), (-1, -1), (-1, 1), (2, 2), (2, -2), (-2, -2), (-2, 2)]
    )
    assert glyph2.coordinates == GlyphCoordinates(
        [(2, 2), (2, -2), (-2, -2), (-2, 2), (4, 4), (4, -4), (-4, -4), (-4, 4)]
    )
    assert glyph1.endPtsOfContours == glyph2.endPtsOfContours == [3, 7]
    assert glyph3.numberOfContours == 0


def test_dropImpliedOnCurvePoints_all_cubic_off_curves():
    # same as above this time using cubic curves
    glyph1, glyph2 = build_interpolatable_glyphs(
        [
            [
                ((0, 1), flagOnCurve),
                ((1, 1), flagCubic),
                ((1, 1), flagCubic),
                ((1, 0), flagOnCurve),
                ((1, -1), flagCubic),
                ((1, -1), flagCubic),
                ((0, -1), flagOnCurve),
                ((-1, -1), flagCubic),
                ((-1, -1), flagCubic),
                ((-1, 0), flagOnCurve),
                ((-1, 1), flagCubic),
                ((-1, 1), flagCubic),
            ]
        ],
        Transform().translate(10.0),
    )
    glyph3 = Glyph()
    glyph3.numberOfContours = 0

    assert dropImpliedOnCurvePoints(glyph1, glyph2, glyph3) == {0, 3, 6, 9}

    assert glyph1.flags == glyph2.flags == array.array("B", [flagCubic] * 8)
    assert glyph1.coordinates == GlyphCoordinates(
        [(1, 1), (1, 1), (1, -1), (1, -1), (-1, -1), (-1, -1), (-1, 1), (-1, 1)]
    )
    assert glyph2.coordinates == GlyphCoordinates(
        [(11, 1), (11, 1), (11, -1), (11, -1), (9, -1), (9, -1), (9, 1), (9, 1)]
    )
    assert glyph1.endPtsOfContours == glyph2.endPtsOfContours == [7]
    assert glyph3.numberOfContours == 0


def test_dropImpliedOnCurvePoints_not_all_impliable():
    # same input as in in test_dropImpliedOnCurvePoints_all_quad_off_curves but we
    # perturbate one of the glyphs such that the 2nd on-curve is no longer half-way
    # between the neighboring off-curves.
    glyph1, glyph2, glyph3 = build_interpolatable_glyphs(
        [
            [
                ((0, 1), flagOnCurve),
                ((1, 1), 0),
                ((1, 0), flagOnCurve),
                ((1, -1), 0),
                ((0, -1), flagOnCurve),
                ((-1, -1), 0),
                ((-1, 0), flagOnCurve),
                ((-1, 1), 0),
            ]
        ],
        Transform().translate(10.0),
        Transform().translate(10.0).scale(2.0),
    )
    p2 = glyph2.coordinates[2]
    glyph2.coordinates[2] = (p2[0] + 2.0, p2[1] - 2.0)

    assert dropImpliedOnCurvePoints(glyph1, glyph2, glyph3) == {
        0,
        # 2,  this is NOT implied because it's no longer impliable for all glyphs
        4,
        6,
    }

    assert glyph2.flags == array.array("B", [0, flagOnCurve, 0, 0, 0])


def test_dropImpliedOnCurvePoints_all_empty_glyphs():
    glyph1 = Glyph()
    glyph1.numberOfContours = 0
    glyph2 = Glyph()
    glyph2.numberOfContours = 0

    assert dropImpliedOnCurvePoints(glyph1, glyph2) == set()


def test_dropImpliedOnCurvePoints_incompatible_number_of_contours():
    glyph1 = Glyph()
    glyph1.numberOfContours = 1
    glyph1.endPtsOfContours = [3]
    glyph1.flags = array.array("B", [1, 1, 1, 1])
    glyph1.coordinates = GlyphCoordinates([(0, 0), (1, 1), (2, 2), (3, 3)])

    glyph2 = Glyph()
    glyph2.numberOfContours = 2
    glyph2.endPtsOfContours = [1, 3]
    glyph2.flags = array.array("B", [1, 1, 1, 1])
    glyph2.coordinates = GlyphCoordinates([(0, 0), (1, 1), (2, 2), (3, 3)])

    with pytest.raises(ValueError, match="Incompatible numberOfContours"):
        dropImpliedOnCurvePoints(glyph1, glyph2)


def test_dropImpliedOnCurvePoints_incompatible_flags():
    glyph1 = Glyph()
    glyph1.numberOfContours = 1
    glyph1.endPtsOfContours = [3]
    glyph1.flags = array.array("B", [1, 1, 1, 1])
    glyph1.coordinates = GlyphCoordinates([(0, 0), (1, 1), (2, 2), (3, 3)])

    glyph2 = Glyph()
    glyph2.numberOfContours = 1
    glyph2.endPtsOfContours = [3]
    glyph2.flags = array.array("B", [0, 0, 0, 0])
    glyph2.coordinates = GlyphCoordinates([(0, 0), (1, 1), (2, 2), (3, 3)])

    with pytest.raises(ValueError, match="Incompatible flags"):
        dropImpliedOnCurvePoints(glyph1, glyph2)


def test_dropImpliedOnCurvePoints_incompatible_endPtsOfContours():
    glyph1 = Glyph()
    glyph1.numberOfContours = 2
    glyph1.endPtsOfContours = [2, 6]
    glyph1.flags = array.array("B", [1, 1, 1, 1, 1, 1, 1])
    glyph1.coordinates = GlyphCoordinates([(i, i) for i in range(7)])

    glyph2 = Glyph()
    glyph2.numberOfContours = 2
    glyph2.endPtsOfContours = [3, 6]
    glyph2.flags = array.array("B", [1, 1, 1, 1, 1, 1, 1])
    glyph2.coordinates = GlyphCoordinates([(i, i) for i in range(7)])

    with pytest.raises(ValueError, match="Incompatible endPtsOfContours"):
        dropImpliedOnCurvePoints(glyph1, glyph2)


@pytest.mark.parametrize("length", [0x7FFF, 0x8000, 0xFFFF, 0x10000])
@pytest.mark.parametrize("composite", [False, True])
def test_unsigned_instruction_length(length, composite):
    glyf = newTable("glyf")
    glyf.glyphOrder = [".notdef", "base"]
    pen = TTGlyphPen(None)
    pen.moveTo((10, 20))
    pen.lineTo((100, 20))
    pen.lineTo((10, 100))
    pen.closePath()
    base = pen.glyph()
    glyf.glyphs = {".notdef": Glyph(), "base": base}
    if composite:
        pen = TTGlyphPen(glyf)
        pen.addComponent("base", (1, 0, 0, 1, 30, 40))
        glyph = pen.glyph()
    else:
        glyph = base
    glyph.program = ttProgram.Program()
    glyph.program.fromBytecode([0] * length)

    if length > 0xFFFF:
        with pytest.raises(struct.error):
            glyph.compile(glyf)
        return
    data = glyph.compile(glyf)
    reloaded = Glyph(data)
    reloaded.expand(glyf)
    assert reloaded.program.getBytecode() == glyph.program.getBytecode()
    assert reloaded.getCoordinates(glyf) == glyph.getCoordinates(glyf)
    assert reloaded.compile(glyf) == data


def build_composite_dag(n):
    """Return a glyf table where composite 'g{k}' uses 'g{k-1}' twice, for k
    from 1 to n, and 'g0' is a square: 'g{k}' flattens to 4 * 2**k points.
    """

    def square():
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((0, 10))
        pen.lineTo((10, 10))
        pen.lineTo((10, 0))
        pen.closePath()
        return pen.glyph()

    glyf = newTable("glyf")
    glyf.glyphOrder = [".notdef"] + [f"g{k}" for k in range(n + 1)]
    glyf.glyphs = {".notdef": square(), "g0": square()}
    for k in range(1, n + 1):
        pen = TTGlyphPen(glyf)
        pen.addComponent(f"g{k-1}", (1, 0, 0, 1, 0, 0))
        pen.addComponent(f"g{k-1}", (1, 0, 0, 1, 0, 0))
        glyf.glyphs[f"g{k}"] = pen.glyph()
    return glyf


def test_composite_dag_under_point_limit():
    glyf = build_composite_dag(13)
    glyph = glyf["g13"]

    coords, endPts, flags = glyph.getCoordinates(glyf)
    assert len(coords) == len(flags) == 32768
    assert endPts == list(range(3, 32768, 4))
    assert list(coords[:4]) == [(0, 0), (0, 10), (10, 10), (10, 0)]
    assert set(coords) == {(0, 0), (0, 10), (10, 10), (10, 0)}

    assert glyph.getCompositeMaxpValues(glyf) == (32768, 8192, 13)
    assert glyph.getCompositeMaxpValues(glyf, maxpValuesCache={}) == (
        32768,
        8192,
        13,
    )


@pytest.mark.parametrize("method", ["getCompositeMaxpValues", "recalcBounds"])
def test_composite_dag_default_cache(method):
    class BoundedGlyphSet(dict):
        lookups = 0

        def __getitem__(self, name):
            self.lookups += 1
            # Bound the work without relying on wall-clock timings.
            assert self.lookups <= 1000, "excessive component traversal"
            return super().__getitem__(name)

    glyf = BoundedGlyphSet(build_composite_dag(12).glyphs)
    glyph = glyf["g12"]
    result = getattr(glyph, method)(glyf)
    if method == "getCompositeMaxpValues":
        assert result == (16384, 4096, 12)
    else:
        assert (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax) == (0, 0, 10, 10)


def test_composite_point_limit():
    glyf = newTable("glyf")
    big = Glyph()
    big.numberOfContours = 1
    big.coordinates = GlyphCoordinates([(i % 100, i // 100) for i in range(0xFFFF)])
    big.endPtsOfContours = [0xFFFF - 1]
    big.flags = array.array("B", [flagOnCurve] * 0xFFFF)
    dot = Glyph()
    dot.numberOfContours = 1
    dot.coordinates = GlyphCoordinates([(0, 0)])
    dot.endPtsOfContours = [0]
    dot.flags = array.array("B", [flagOnCurve])
    glyf.glyphs = {"big": big, "dot": dot}
    for name, components in [("atLimit", ["big"]), ("overLimit", ["big", "dot"])]:
        pen = TTGlyphPen(glyf)
        for component in components:
            pen.addComponent(component, (1, 0, 0, 1, 0, 0))
        glyf.glyphs[name] = pen.glyph()
    glyf.glyphOrder = list(glyf.glyphs)

    coords, endPts, flags = glyf["atLimit"].getCoordinates(glyf)
    assert len(coords) == len(flags) == 0xFFFF
    assert endPts == [0xFFFF - 1]

    with pytest.raises(TTLibError, match="has more than 65535 points"):
        glyf["overLimit"].getCoordinates(glyf)


def test_composite_dag_over_point_limit():
    glyf = build_composite_dag(20)
    with pytest.raises(TTLibError, match="has more than 65535 points"):
        glyf["g20"].getCoordinates(glyf)
    # 4 * 2**14 points is one more than the limit
    with pytest.raises(TTLibError, match="has more than 65535 points"):
        glyf["g14"].getCoordinates(glyf)


def test_composite_dag_empty_leaf():
    glyf = build_composite_dag(22)
    glyf.glyphs["g0"] = Glyph()
    assert glyf["g22"].getCoordinates(glyf) == (GlyphCoordinates(), [], bytearray())


@pytest.mark.parametrize("round", [noRound, otRound])
def test_getCoordinates_reused_component(round):
    glyf = build_composite_dag(1)
    transforms = [
        (0.5, 0, 0, 1.5, 3, 7),
        (1, 0, 0, 1, -20, 5),
        (0.3, 0.2, -0.1, 0.7, 11.5, 0),
    ]
    for i, transform in enumerate(transforms):
        pen = TTGlyphPen(glyf)
        pen.addComponent("g1", transform)
        glyf.glyphs[f"single{i}"] = pen.glyph()
    pen = TTGlyphPen(glyf)
    for transform in transforms + transforms[::-1]:
        pen.addComponent("g1", transform)
    glyf.glyphs["multi"] = pen.glyph()

    coords, endPts, flags = glyf["multi"].getCoordinates(glyf, round=round)
    expected = GlyphCoordinates()
    for i in list(range(len(transforms))) + list(reversed(range(len(transforms)))):
        expected.extend(glyf[f"single{i}"].getCoordinates(glyf, round=round)[0])
    assert coords == expected
    assert endPts == list(range(3, len(expected), 4))
    assert flags == bytearray([flagOnCurve]) * len(expected)


def test_maxp_recalc_composite_dag():
    n = 20
    glyf = build_composite_dag(n)
    fb = FontBuilder(unitsPerEm=1000, isTTF=True)
    fb.setupGlyphOrder(glyf.glyphOrder)
    fb.setupGlyf(glyf.glyphs)
    fb.setupHorizontalMetrics({name: (10, 0) for name in glyf.glyphOrder})
    font = fb.font

    # bounds of composites with integer offsets don't need flattening
    font["glyf"].compile(font)

    maxp = font["maxp"]
    maxp.recalc(font)
    assert maxp.maxPoints == 4
    assert maxp.maxContours == 1
    assert maxp.maxCompositePoints == 4 * 2**n
    assert maxp.maxCompositeContours == 2**n
    assert maxp.maxComponentElements == 2
    assert maxp.maxComponentDepth == n
    head = font["head"]
    assert (head.xMin, head.yMin, head.xMax, head.yMax) == (0, 0, 10, 10)


@pytest.mark.parametrize(
    "path",
    [
        "ttx/data/TestTTF.ttf",
        "qu2cu/data/NotoSansArabic-Regular.quadratic.subset.ttf",
        "subset/data/BungeeColor-Regular.ttx",
        "varLib/data/MutatorSans_All_Variable.ttx",
        "varLib/instancer/data/PartialInstancerTest3-VF.ttx",
        None,
    ],
)
def test_getCompositeMaxpValues_cache(path):
    if path is None:
        glyf = build_composite_dag(12)
    else:
        path = Path(__file__).parent.parent.parent / path
        if path.suffix == ".ttx":
            font = TTFont()
            font.importXML(path)
        else:
            font = TTFont(path)
        glyf = font["glyf"]
    composites = [name for name in glyf.glyphOrder if glyf[name].isComposite()]
    assert composites

    for depth in (1, 3):
        expected = {
            name: glyf[name].getCompositeMaxpValues(glyf, depth) for name in composites
        }
        for glyphNames in (composites, composites[::-1]):
            cache = {}
            for name in glyphNames:
                assert (
                    glyf[name].getCompositeMaxpValues(
                        glyf, depth, maxpValuesCache=cache
                    )
                    == expected[name]
                )


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
