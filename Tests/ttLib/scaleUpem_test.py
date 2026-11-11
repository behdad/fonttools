from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.beyond64k import upper_tables
from fontTools.ttLib.scaleUpem import ScalerVisitor, scale_upem
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.scaleUpem import scale_upem
from fontTools.ttLib.tables import otTables as ot
from fontTools.otlLib.builder import buildMathTable
from fontTools.pens.recordingPen import RecordingPen
from fontTools.varLib.multiVarStore import MultiVarStoreInstancer
from copy import deepcopy
import pytest
from io import BytesIO
import difflib
import os
import shutil
import sys
import tempfile
import unittest


class OutlinePen(RecordingPen):
    def addVarComponent(self, *args, **kwargs):
        raise AttributeError


def record_varc_outlines(font, location):
    glyph_set = font.getGlyphSet(location=location, normalized=True)
    result = {}
    for name in font["VARC"].table.Coverage.glyphs:
        pen = OutlinePen()
        glyph_set[name].draw(pen)
        result[name] = pen.value
    return result


def scale_and_roundtrip(font):
    scale_upem(font, font["head"].unitsPerEm * 2)
    data = BytesIO()
    font.save(data)
    return TTFont(BytesIO(data.getvalue()))


def assert_scaled_outlines(before, after):
    assert before.keys() == after.keys()
    for name in before:
        assert len(before[name]) == len(after[name])
        for (op, points), (new_op, new_points) in zip(before[name], after[name]):
            assert op == new_op
            assert len(points) == len(new_points)
            for point, new_point in zip(points, new_points):
                if point is None:
                    assert new_point is None
                else:
                    assert new_point == pytest.approx(tuple(2 * v for v in point))


@pytest.mark.parametrize(
    "filename",
    [
        "varc-ac00-ac01.ttf",
        "varc-6868.ttf",
        "varc-ac01-conditional.ttf",
        "varc-static-gvar.ttf",
    ],
)
@pytest.mark.parametrize("uppercase", [False, True])
def test_scale_upem_varc_outlines(filename, uppercase):
    font = TTFont(ScaleUpemTest.get_path(filename))
    fvar = font.get("fvar")
    locations = [{}, {a.axisTag: 1 for a in fvar.axes}] if fvar is not None else [{}]
    if uppercase:
        upper_tables(font)
    before = [record_varc_outlines(font, loc) for loc in locations]
    font = scale_and_roundtrip(font)
    for loc, expected in zip(locations, before):
        assert_scaled_outlines(expected, record_varc_outlines(font, loc))
    if fvar is None:
        assert font["VARC"].table.MultiVarStore is None
        assert "fvar" not in font


def test_scale_upem_first_variation_is_transform_only():
    font = TTFont(ScaleUpemTest.get_path("varc-6868.ttf"))
    composites = font["VARC"].table.VarCompositeGlyphs.VarCompositeGlyph
    component = next(
        c
        for g in composites
        for c in g.components
        if c.axisValuesVarIndex == ot.NO_VARIATION_INDEX
        and c.transformVarIndex != ot.NO_VARIATION_INDEX
    )
    composites[0].components.insert(0, deepcopy(component))
    location = {a.axisTag: 1 for a in font["fvar"].axes}
    before = record_varc_outlines(font, location)
    font = scale_and_roundtrip(font)
    assert_scaled_outlines(before, record_varc_outlines(font, location))


@pytest.mark.parametrize("wrapper_format", [None, 3, 4, 5])
@pytest.mark.parametrize("delta", [0, 2])
def test_scale_upem_preserves_condition_variations(wrapper_format, delta):
    font = TTFont(ScaleUpemTest.get_path("varc-ac01-conditional.ttf"))
    varc = font["VARC"].table
    data = varc.MultiVarStore.MultiVarData[0]
    data.Item.append([delta] * data.VarRegionCount)
    condition = ot.ConditionTable()
    condition.Format = 2
    condition.DefaultValue = -1
    condition.VarIdx = len(data.Item) - 1
    if wrapper_format is None:
        outer = condition
    else:
        outer = ot.ConditionTable()
        outer.Format = wrapper_format
        if wrapper_format == 5:
            outer.ConditionTable = condition
        else:
            outer.ConditionCount = 1
            outer.ConditionTable = [condition]
    varc.ConditionList.ConditionTable[0] = outer
    axes = font["fvar"].axes
    locations = [{}, {axes[0].axisTag: 1}]
    before = [record_varc_outlines(font, loc) for loc in locations]
    values = [
        tuple(MultiVarStoreInstancer(varc.MultiVarStore, axes, loc)[condition.VarIdx])
        for loc in locations
    ]
    font = scale_and_roundtrip(font)
    varc = font["VARC"].table
    condition = varc.ConditionList.ConditionTable[0]
    if wrapper_format is not None:
        condition = (
            condition.ConditionTable
            if wrapper_format == 5
            else condition.ConditionTable[0]
        )
    assert condition.DefaultValue == -1
    for loc, expected, value in zip(locations, before, values):
        deltas = MultiVarStoreInstancer(varc.MultiVarStore, font["fvar"].axes, loc)[
            condition.VarIdx
        ]
        assert (deltas[0] if deltas else 0) == (value[0] if value else 0)
        assert_scaled_outlines(expected, record_varc_outlines(font, loc))


def _build_cff_font_without_font_matrix():
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder([".notdef", "A"])
    fb.setupCharacterMap({0x41: "A"})
    pen = T2CharStringPen(600, None)
    pen.moveTo((100, 0))
    pen.lineTo((500, 0))
    pen.lineTo((300, 700))
    pen.closePath()
    charString = pen.getCharString()
    fb.setupCFF("Test-Regular", {}, {".notdef": charString, "A": charString}, {})
    fb.setupHorizontalMetrics({".notdef": (600, 100), "A": (600, 100)})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    data = BytesIO()
    fb.save(data)
    return TTFont(BytesIO(data.getvalue()))


def test_scale_upem_cff_default_font_matrix():
    # https://github.com/fonttools/fonttools/issues/4251
    from fontTools.cffLib import TopDict

    default = list(TopDict.defaults["FontMatrix"])
    font = _build_cff_font_without_font_matrix()
    topDict = font["CFF "].cff.topDictIndex[0]
    assert "FontMatrix" not in topDict.rawDict

    try:
        font = scale_and_roundtrip(font)
        # The shared class-level default is left alone...
        assert TopDict.defaults["FontMatrix"] == default
    finally:
        # ...and restored even if not, so a regression cannot leak into other tests.
        TopDict.defaults["FontMatrix"][:] = default
    # ...and the scaled matrix is written explicitly.
    topDict = font["CFF "].cff.topDictIndex[0]
    assert font["head"].unitsPerEm == 2000
    assert "FontMatrix" in topDict.rawDict
    assert topDict.FontMatrix == [0.0005, 0, 0, 0.0005, 0, 0]


def test_scale_upem_math():
    font = TTFont(ScaleUpemTest.get_path("I.ttf"))
    notdef, glyph = font.getGlyphOrder()
    buildMathTable(
        font,
        constants={
            "ScriptPercentScaleDown": 80,
            "ScriptScriptPercentScaleDown": 60,
            "DelimitedSubFormulaMinHeight": 1500,
            "DisplayOperatorMinHeight": 1300,
            "RadicalDegreeBottomRaisePercent": 55,
        },
        minConnectorOverlap=50,
        vertGlyphVariants={glyph: [(glyph, 1000), (notdef, 1400)]},
        vertGlyphAssembly={glyph: ([(notdef, 1, 20, 30, 400)], 0)},
    )

    font = scale_and_roundtrip(font)

    math = font["MATH"].table
    # Percentages and flags are not design units: they must stay as they are.
    assert math.MathConstants.ScriptPercentScaleDown == 80
    assert math.MathConstants.ScriptScriptPercentScaleDown == 60
    assert math.MathConstants.RadicalDegreeBottomRaisePercent == 55
    assert math.MathConstants.DelimitedSubFormulaMinHeight == 3000
    assert math.MathConstants.DisplayOperatorMinHeight == 2600
    assert math.MathVariants.MinConnectorOverlap == 100
    (construction,) = math.MathVariants.VertGlyphConstruction
    variants = construction.MathGlyphVariantRecord
    assert [v.AdvanceMeasurement for v in variants] == [2000, 2800]
    (part,) = construction.GlyphAssembly.PartRecords
    assert part.StartConnectorLength == 40
    assert part.EndConnectorLength == 60
    assert part.FullAdvance == 800
    assert part.PartFlags == 1


class ScaleUpemTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = None
        self.num_tempfiles = 0

    def tearDown(self):
        if self.tempdir:
            shutil.rmtree(self.tempdir)

    @staticmethod
    def get_path(test_file_or_folder):
        parent_dir = os.path.dirname(__file__)
        return os.path.join(parent_dir, "data", test_file_or_folder)

    def temp_path(self, suffix):
        self.temp_dir()
        self.num_tempfiles += 1
        return os.path.join(self.tempdir, "tmp%d%s" % (self.num_tempfiles, suffix))

    def temp_dir(self):
        if not self.tempdir:
            self.tempdir = tempfile.mkdtemp()

    def read_ttx(self, path):
        lines = []
        with open(path, "r", encoding="utf-8") as ttx:
            for line in ttx.readlines():
                # Elide ttFont attributes because ttLibVersion may change.
                if line.startswith("<ttFont "):
                    lines.append("<ttFont>\n")
                else:
                    lines.append(line.rstrip() + "\n")
        return lines

    def expect_ttx(self, font, expected_ttx, tables):
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

    def test_scale_upem_ttf(self):
        font = TTFont(self.get_path("I.ttf"))
        tables = [table_tag for table_tag in font.keys() if table_tag != "head"]

        scale_upem(font, 512)

        expected_ttx_path = self.get_path("I-512upem.ttx")
        self.expect_ttx(font, expected_ttx_path, tables)

    def test_scale_upem_beyond64k_ttf(self):
        font = TTFont(self.get_path("I.ttf"))
        upper_tables(font)

        scale_upem(font, 512)

        assert font["head"].unitsPerEm == 512
        assert font["HHEA"].ascent == 475
        assert font["HHEA"].descent == -125
        assert font["HMTX"]["I"] == (136, 44)
        assert font["GLYF"]["I"].xMin == 44
        assert font["GLYF"]["I"].xMax == 92
        assert font["GVAR"].variations["I"][0].coordinates[1] == (-24, 0)

        # Save / load to ensure calculated companion-table values are valid.
        iobytes = BytesIO()
        font.save(iobytes)
        iobytes.seek(0)
        font = TTFont(iobytes)
        assert {"GLYF", "LOCA", "MAXP", "HHEA", "HMTX"} <= set(font.keys())
        assert font["HMTX"]["I"] == (136, 44)

    def test_scale_upem_otf(self):
        # Just test that it doesn't crash

        font = TTFont(self.get_path("TestVGID-Regular.otf"))

        scale_upem(font, 500)

    def test_scale_upem_varComposite(self):
        font = TTFont(self.get_path("varc-ac00-ac01.ttf"))
        tables = [table_tag for table_tag in font.keys() if table_tag != "head"]

        scale_upem(font, 500)

        # Save / load to ensure calculated values are correct
        # XXX This wans't needed before. So needs investigation.
        iobytes = BytesIO()
        font.save(iobytes)
        # Just saving is enough to fix the numbers. Sigh...

        expected_ttx_path = self.get_path("varc-ac00-ac01-500upem.ttx")
        self.expect_ttx(font, expected_ttx_path, tables)

        # Scale our other varComposite font as well; without checking the expected
        font = TTFont(self.get_path("varc-6868.ttf"))
        scale_upem(font, 500)

    def test_scale_upem_vorg(self):
        font = TTFont(self.get_path("TestVGID-Regular.otf"))
        order = font.getGlyphOrder()
        vorg = font["VORG"] = newTable("VORG")
        vorg.majorVersion, vorg.minorVersion = 1, 0
        vorg.defaultVertOriginY = 800
        vorg.VOriginRecords = {order[1]: 900, order[2]: -321}

        scale_upem(font, font["head"].unitsPerEm * 2)

        stream = BytesIO()
        font.save(stream)
        font = TTFont(BytesIO(stream.getvalue()))
        assert font["VORG"].defaultVertOriginY == 1600
        assert font["VORG"][order[0]] == 1600
        assert font["VORG"].VOriginRecords == {order[1]: 1800, order[2]: -642}


def test_scale_upem_paint_glyph2():
    paint = otTables.Paint()
    paint.Format = otTables.PaintFormat.PaintGlyph2
    paint.Glyph = "high"
    paint.Paint = otTables.Paint()
    paint.Paint.Format = otTables.PaintFormat.PaintSolid
    paint.Paint.PaletteIndex = 0
    paint.Paint.Alpha = 1.0

    ScalerVisitor(2).visit(paint)

    assert paint.Format == otTables.PaintFormat.PaintScaleUniform
    assert paint.Paint.Format == otTables.PaintFormat.PaintGlyph2
    assert paint.Paint.Glyph == "high"


@pytest.mark.parametrize("factor", [0.5, 2, 3])
def test_scale_upem_colrv1_saves(factor):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((0, 500))
    pen.lineTo((500, 500))
    pen.closePath()
    glyph = pen.glyph()
    glyphOrder = [".notdef", "A", "layer"]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(glyphOrder)
    fb.setupCharacterMap({0x41: "A"})
    fb.setupGlyf({name: glyph for name in glyphOrder})
    fb.setupHorizontalMetrics({name: (500, 0) for name in glyphOrder})
    fb.setupHorizontalHeader()
    fb.setupNameTable({"familyName": "TestCOLRv1", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.setupCPAL([[(1.0, 0.0, 0.0, 1.0)]])
    fb.setupCOLR(
        {
            "A": {
                "Format": ot.PaintFormat.PaintGlyph,
                "Paint": (ot.PaintFormat.PaintSolid, 0),
                "Glyph": "layer",
            }
        }
    )
    font = fb.font

    scale_upem(font, int(1000 * factor))
    stream = BytesIO()
    font.save(stream)
    font = TTFont(BytesIO(stream.getvalue()))

    # The base glyph paint is scaled by the factor, and the PaintGlyph inside
    # by its inverse: a factor of 2 or 0.5 needs a scale of 2 somewhere, which
    # does not fit in the F2Dot14 of PaintScaleUniform.
    paint = font["COLR"].table.BaseGlyphList.BaseGlyphPaintRecord[0].Paint
    for scale in (factor, 1 / factor):
        if scale < 2:
            assert paint.Format == ot.PaintFormat.PaintScaleUniform
        else:
            assert paint.Format == ot.PaintFormat.PaintTransform
            assert paint.Transform.xx == paint.Transform.yy == scale
        paint = paint.Paint
    assert paint.Format == ot.PaintFormat.PaintGlyph
