from fontTools import ttLib
from fontTools.misc.testTools import getXML, parseXML
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.C_O_L_R_ import table_C_O_L_R_

from pathlib import Path
import binascii
import pytest

TEST_DATA_DIR = Path(__file__).parent / "data"


COLR_V0_SAMPLE = (
    (b"\x00\x00", "Version (0)"),
    (b"\x00\x01", "BaseGlyphRecordCount (1)"),
    (
        b"\x00\x00\x00\x0e",
        "Offset to BaseGlyphRecordArray from beginning of table (14)",
    ),
    (b"\x00\x00\x00\x14", "Offset to LayerRecordArray from beginning of table (20)"),
    (b"\x00\x03", "LayerRecordCount (3)"),
    (b"\x00\x06", "BaseGlyphRecord[0].BaseGlyph (6)"),
    (b"\x00\x00", "BaseGlyphRecord[0].FirstLayerIndex (0)"),
    (b"\x00\x03", "BaseGlyphRecord[0].NumLayers (3)"),
    (b"\x00\x07", "LayerRecord[0].LayerGlyph (7)"),
    (b"\x00\x00", "LayerRecord[0].PaletteIndex (0)"),
    (b"\x00\x08", "LayerRecord[1].LayerGlyph (8)"),
    (b"\x00\x01", "LayerRecord[1].PaletteIndex (1)"),
    (b"\x00\t", "LayerRecord[2].LayerGlyph (9)"),
    (b"\x00\x02", "LayerRecord[3].PaletteIndex (2)"),
)

COLR_V0_DATA = b"".join(t[0] for t in COLR_V0_SAMPLE)


COLR_V0_XML = [
    '<version value="0"/>',
    '<ColorGlyph name="glyph00006">',
    '  <layer colorID="0" name="glyph00007"/>',
    '  <layer colorID="1" name="glyph00008"/>',
    '  <layer colorID="2" name="glyph00009"/>',
    "</ColorGlyph>",
]


def dump(table, ttFont=None):
    print("\n".join(getXML(table.toXML, ttFont)))


def diff_binary_fragments(font_bytes, expected_fragments):
    pos = 0
    prev_desc = ""
    errors = 0
    for expected_bytes, description in expected_fragments:
        actual_bytes = font_bytes[pos : pos + len(expected_bytes)]
        if actual_bytes != expected_bytes:
            print(
                f'{description} (previous "{prev_desc}", actual_bytes: {"".join("%02x" % v for v in actual_bytes)} bytes: {str(font_bytes[pos:pos+16])}'
            )
            errors += 1
        pos += len(expected_bytes)
        prev_desc = description
    assert errors == 0
    assert pos == len(
        font_bytes
    ), f"Leftover font bytes, used {pos} of {len(font_bytes)}"


@pytest.fixture
def font():
    font = ttLib.TTFont()
    font.setGlyphOrder(["glyph%05d" % i for i in range(30)])
    return font


class COLR_V0_Test(object):
    def test_decompile_and_compile(self, font):
        colr = table_C_O_L_R_()
        colr.decompile(COLR_V0_DATA, font)
        diff_binary_fragments(colr.compile(font), COLR_V0_SAMPLE)

    def test_decompile_and_dump_xml(self, font):
        colr = table_C_O_L_R_()
        colr.decompile(COLR_V0_DATA, font)

        dump(colr, font)
        assert getXML(colr.toXML, font) == COLR_V0_XML

    def test_load_from_xml_and_compile(self, font):
        colr = table_C_O_L_R_()
        for name, attrs, content in parseXML(COLR_V0_XML):
            colr.fromXML(name, attrs, content, font)

        diff_binary_fragments(colr.compile(font), COLR_V0_SAMPLE)

    def test_round_trip_xml(self, font):
        colr = table_C_O_L_R_()
        for name, attrs, content in parseXML(COLR_V0_XML):
            colr.fromXML(name, attrs, content, font)
        compiled = colr.compile(font)

        colr = table_C_O_L_R_()
        colr.decompile(compiled, font)
        assert getXML(colr.toXML, font) == COLR_V0_XML

    def test_round_trip_xml_empty(self, font):
        colr = table_C_O_L_R_()
        for name, attrs, content in parseXML('<version value="0"/>'):
            colr.fromXML(name, attrs, content, font)
        assert colr.ColorLayers == {}
        compiled = colr.compile(font)

        colr = table_C_O_L_R_()
        colr.decompile(compiled, font)
        assert colr.version == 0
        assert colr.ColorLayers == {}
        assert getXML(colr.toXML, font) == ['<version value="0"/>']


COLR_V1_SAMPLE = (
    (b"\x00\x01", "Version (1)"),
    (b"\x00\x01", "BaseGlyphRecordCount (1)"),
    (
        b"\x00\x00\x00\x22",
        "Offset to BaseGlyphRecordArray from beginning of table (34)",
    ),
    (b"\x00\x00\x00\x28", "Offset to LayerRecordArray from beginning of table (40)"),
    (b"\x00\x03", "LayerRecordCount (3)"),
    (b"\x00\x00\x00\x34", "Offset to BaseGlyphList from beginning of table (52)"),
    (b"\x00\x00\x00\x9f", "Offset to LayerList from beginning of table (159)"),
    (b"\x00\x00\x01\x66", "Offset to ClipList (358)"),
    (b"\x00\x00\x00\x00", "Offset to DeltaSetIndexMap (NULL)"),
    (b"\x00\x00\x00\x00", "Offset to VarStore (NULL)"),
    (b"\x00\x06", "BaseGlyphRecord[0].BaseGlyph (6)"),
    (b"\x00\x00", "BaseGlyphRecord[0].FirstLayerIndex (0)"),
    (b"\x00\x03", "BaseGlyphRecord[0].NumLayers (3)"),
    (b"\x00\x07", "LayerRecord[0].LayerGlyph (7)"),
    (b"\x00\x00", "LayerRecord[0].PaletteIndex (0)"),
    (b"\x00\x08", "LayerRecord[1].LayerGlyph (8)"),
    (b"\x00\x01", "LayerRecord[1].PaletteIndex (1)"),
    (b"\x00\t", "LayerRecord[2].LayerGlyph (9)"),
    (b"\x00\x02", "LayerRecord[2].PaletteIndex (2)"),
    # BaseGlyphList
    (b"\x00\x00\x00\x03", "BaseGlyphList.BaseGlyphCount (3)"),
    (b"\x00\n", "BaseGlyphList.BaseGlyphPaintRecord[0].BaseGlyph (10)"),
    (
        b"\x00\x00\x00\x16",
        "Offset to Paint table from beginning of BaseGlyphList (22)",
    ),
    (b"\x00\x0e", "BaseGlyphList.BaseGlyphPaintRecord[1].BaseGlyph (14)"),
    (
        b"\x00\x00\x00\x1c",
        "Offset to Paint table from beginning of BaseGlyphList (28)",
    ),
    (b"\x00\x0f", "BaseGlyphList.BaseGlyphPaintRecord[2].BaseGlyph (15)"),
    (
        b"\x00\x00\x00\x4a",
        "Offset to Paint table from beginning of BaseGlyphList (74)",
    ),
    # BaseGlyphPaintRecord[0]
    (b"\x01", "BaseGlyphPaintRecord[0].Paint.Format (1)"),
    (b"\x04", "BaseGlyphPaintRecord[0].Paint.NumLayers (4)"),
    (b"\x00\x00\x00\x00", "BaseGlyphPaintRecord[0].Paint.FirstLayerIndex (0)"),
    # BaseGlyphPaintRecord[1]
    (b"\x20", "BaseGlyphPaintRecord[1].Paint.Format (32)"),
    (b"\x00\x00\x0f", "Offset to SourcePaint from beginning of PaintComposite (15)"),
    (b"\x03", "BaseGlyphPaintRecord[1].Paint.CompositeMode [SRC_OVER] (3)"),
    (b"\x00\x00\x08", "Offset to BackdropPaint from beginning of PaintComposite (8)"),
    (b"\x0d", "BaseGlyphPaintRecord[1].Paint.BackdropPaint.Format (13)"),
    (b"\x00\x00\x07", "Offset to Paint from beginning of PaintVarTransform (7)"),
    (
        b"\x00\x00\x0a",
        "Offset to VarAffine2x3 from beginning of PaintVarTransform (10)",
    ),
    (b"\x0b", "BaseGlyphPaintRecord[1].Paint.BackdropPaint.Format (11)"),
    (b"\x00\x0a", "BaseGlyphPaintRecord[1].Paint.BackdropPaint.Glyph (10)"),
    (b"\x00\x01\x00\x00", "VarAffine2x3.xx (1.0)"),
    (b"\x00\x00\x00\x00", "VarAffine2x3.xy (0.0)"),
    (b"\x00\x00\x00\x00", "VarAffine2x3.yx (0.0)"),
    (b"\x00\x01\x00\x00", "VarAffine2x3.yy (1.0)"),
    (b"\x01\x2c\x00\x00", "VarAffine2x3.dx (300.0)"),
    (b"\x00\x00\x00\x00", "VarAffine2x3.dy (0.0)"),
    (b"\x00\x00\x00\x00", "VarIndexBase (0)"),
    (b"\x0a", "BaseGlyphPaintRecord[1].Paint.SourcePaint.Format (10)"),
    (b"\x00\x00\x06", "Offset to Paint subtable from beginning of PaintGlyph (6)"),
    (b"\x00\x0b", "BaseGlyphPaintRecord[1].Paint.SourcePaint.Glyph (11)"),
    (b"\x08", "BaseGlyphPaintRecord[1].Paint.SourcePaint.Paint.Format (8)"),
    (b"\x00\x00\x0c", "Offset to ColorLine from beginning of PaintSweepGradient (12)"),
    (b"\x01\x03", "centerX (259)"),
    (b"\x01\x2c", "centerY (300)"),
    (b"\x10\x00", "startAngle (0.25)"),
    (b"\x30\x00", "endAngle (0.75)"),
    (b"\x00", "ColorLine.Extend (0; pad)"),
    (b"\x00\x02", "ColorLine.StopCount (2)"),
    (b"\x00\x00", "ColorLine.ColorStop[0].StopOffset (0.0)"),
    (b"\x00\x03", "ColorLine.ColorStop[0].PaletteIndex (3)"),
    (b"@\x00", "ColorLine.ColorStop[0].Alpha (1.0)"),
    (b"@\x00", "ColorLine.ColorStop[1].StopOffset (1.0)"),
    (b"\x00\x05", "ColorLine.ColorStop[1].PaletteIndex (5)"),
    (b"@\x00", "ColorLine.ColorStop[1].Alpha (1.0)"),
    # LayerList
    (b"\x00\x00\x00\x05", "LayerList.LayerCount (5)"),
    (
        b"\x00\x00\x00\x18",
        "First Offset to Paint table from beginning of LayerList (24)",
    ),
    (
        b"\x00\x00\x00\x27",
        "Second Offset to Paint table from beginning of LayerList (39)",
    ),
    (
        b"\x00\x00\x00\x52",
        "Third Offset to Paint table from beginning of LayerList (82)",
    ),
    (
        b"\x00\x00\x00\xa2",
        "Fourth Offset to Paint table from beginning of LayerList (162)",
    ),
    (
        b"\x00\x00\x00\xbc",
        "Fifth Offset to Paint table from beginning of LayerList (188)",
    ),
    # BaseGlyphPaintRecord[2]
    (b"\x0a", "BaseGlyphPaintRecord[2].Paint.Format (10)"),
    (b"\x00\x00\x06", "Offset to Paint subtable from beginning of PaintGlyph (6)"),
    (b"\x00\x0b", "BaseGlyphPaintRecord[2].Paint.Glyph (11)"),
    # PaintVarSolid
    (b"\x03", "LayerList.Paint[0].Paint.Format (3)"),
    (b"\x00\x02", "Paint.PaletteIndex (2)"),
    (b" \x00", "Paint.Alpha.value (0.5)"),
    (b"\x00\x00\x00\x06", "VarIndexBase (6)"),
    # PaintGlyph glyph00012
    (b"\x0a", "LayerList.Paint[1].Format (10)"),
    (b"\x00\x00\x06", "Offset to Paint subtable from beginning of PaintGlyph (6)"),
    (b"\x00\x0c", "LayerList.Paint[1].Glyph (glyph00012)"),
    (b"\x04", "LayerList.Paint[1].Paint.Format (4)"),
    (b"\x00\x00\x10", "Offset to ColorLine from beginning of PaintLinearGradient (16)"),
    (b"\x00\x01", "Paint.x0 (1)"),
    (b"\x00\x02", "Paint.y0 (2)"),
    (b"\xff\xfd", "Paint.x1 (-3)"),
    (b"\xff\xfc", "Paint.y1 (-4)"),
    (b"\x00\x05", "Paint.x2 (5)"),
    (b"\x00\x06", "Paint.y2 (6)"),
    (b"\x01", "ColorLine.Extend (1; repeat)"),
    (b"\x00\x03", "ColorLine.StopCount (3)"),
    (b"\x00\x00", "ColorLine.ColorStop[0].StopOffset (0.0)"),
    (b"\x00\x03", "ColorLine.ColorStop[0].PaletteIndex (3)"),
    (b"@\x00", "ColorLine.ColorStop[0].Alpha (1.0)"),
    (b" \x00", "ColorLine.ColorStop[1].StopOffset (0.5)"),
    (b"\x00\x04", "ColorLine.ColorStop[1].PaletteIndex (4)"),
    (b"@\x00", "ColorLine.ColorStop[1].Alpha (1.0)"),
    (b"@\x00", "ColorLine.ColorStop[2].StopOffset (1.0)"),
    (b"\x00\x05", "ColorLine.ColorStop[2].PaletteIndex (5)"),
    (b"@\x00", "ColorLine.ColorStop[2].Alpha (1.0)"),
    # PaintGlyph glyph00013
    (b"\x0a", "LayerList.Paint[2].Format (10)"),
    (b"\x00\x00\x06", "Offset to Paint subtable from beginning of PaintGlyph (6)"),
    (b"\x00\x0d", "LayerList.Paint[2].Glyph (13)"),
    (b"\x0c", "LayerList.Paint[2].Paint.Format (12)"),
    (b"\x00\x00\x07", "Offset to Paint subtable from beginning of PaintTransform (7)"),
    (
        b"\x00\x00\x32",
        "Offset to Affine2x3 subtable from beginning of PaintTransform (50)",
    ),
    (b"\x07", "LayerList.Paint[2].Paint.Paint.Format (7)"),
    (
        b"\x00\x00\x14",
        "Offset to ColorLine from beginning of PaintVarRadialGradient (20)",
    ),
    (b"\x00\x07", "Paint.x0.value (7)"),
    (b"\x00\x08", "Paint.y0.value (8)"),
    (b"\x00\t", "Paint.r0.value (9)"),
    (b"\x00\n", "Paint.x1.value (10)"),
    (b"\x00\x0b", "Paint.y1.value (11)"),
    (b"\x00\x0c", "Paint.r1.value (12)"),
    (b"\xff\xff\xff\xff", "VarIndexBase (0xFFFFFFFF)"),
    (b"\x00", "ColorLine.Extend (0; pad)"),
    (b"\x00\x02", "ColorLine.StopCount (2)"),
    (b"\x00\x00", "ColorLine.ColorStop[0].StopOffset.value (0.0)"),
    (b"\x00\x06", "ColorLine.ColorStop[0].PaletteIndex (6)"),
    (b"@\x00", "ColorLine.ColorStop[0].Alpha.value (1.0)"),
    (b"\xff\xff\xff\xff", "VarIndexBase (0xFFFFFFFF)"),
    (b"@\x00", "ColorLine.ColorStop[1].StopOffset.value (1.0)"),
    (b"\x00\x07", "ColorLine.ColorStop[1].PaletteIndex (7)"),
    (b"\x19\x9a", "ColorLine.ColorStop[1].Alpha.value (0.4)"),
    (b"\x00\x00\x00\x07", "VarIndexBase (7)"),
    (b"\xff\xf3\x00\x00", "Affine2x3.xx (-13)"),
    (b"\x00\x0e\x00\x00", "Affine2x3.xy (14)"),
    (b"\x00\x0f\x00\x00", "Affine2x3.yx (15)"),
    (b"\xff\xef\x00\x00", "Affine2x3.yy (-17)"),
    (b"\x00\x12\x00\x00", "Affine2x3.yy (18)"),
    (b"\x00\x13\x00\x00", "Affine2x3.yy (19)"),
    # PaintTranslate
    (b"\x0e", "LayerList.Paint[3].Format (14)"),
    (b"\x00\x00\x08", "Offset to Paint subtable from beginning of PaintTranslate (8)"),
    (b"\x01\x01", "dx (257)"),
    (b"\x01\x02", "dy (258)"),
    # PaintRotateAroundCenter
    (b"\x1a", "LayerList.Paint[3].Paint.Format (26)"),
    (
        b"\x00\x00\x0a",
        "Offset to Paint subtable from beginning of PaintRotateAroundCenter (11)",
    ),
    (b"\x10\x00", "angle (0.25)"),
    (b"\x00\xff", "centerX (255)"),
    (b"\x01\x00", "centerY (256)"),
    # PaintSkew
    (b"\x1c", "LayerList.Paint[3].Paint.Paint.Format (28)"),
    (
        b"\x00\x00\x08",
        "Offset to Paint subtable from beginning of PaintSkew (8)",
    ),
    (b"\xfc\x17", "xSkewAngle (-0.0611)"),
    (b"\x01\xc7", "ySkewAngle (0.0278)"),
    # PaintGlyph glyph00011 (pointed to by both PaintSkew above and by LayerList[4] offset)
    (b"\x0a", "LayerList.Paint[3].Paint.Paint.Paint.Format (10)"),
    (b"\x00\x00\x06", "Offset to Paint subtable from beginning of PaintGlyph (6)"),
    (b"\x00\x0b", "LayerList.Paint[2].Glyph (11)"),
    # PaintSolid
    (b"\x02", "LayerList.Paint[0].Paint.Paint.Paint.Paint.Format (2)"),
    (b"\x00\x02", "Paint.PaletteIndex (2)"),
    (b" \x00", "Paint.Alpha (0.5)"),
    # ClipList
    (b"\x01", "ClipList.Format (1)"),
    (b"\x00\x00\x00\x02", "ClipList.ClipCount (2)"),
    (b"\x00\x0a", "ClipRecord[0].StartGlyphID (10)"),
    (b"\x00\x0a", "ClipRecord[0].EndGlyphID (10)"),
    (b"\x00\x00\x13", "Offset to ClipBox subtable from beginning of ClipList (19)"),
    (b"\x00\x0e", "ClipRecord[1].StartGlyphID (14)"),
    (b"\x00\x0f", "ClipRecord[1].EndGlyphID (15)"),
    (b"\x00\x00\x20", "Offset to ClipBox subtable from beginning of ClipList (32)"),
    (b"\x02", "ClipBox.Format (2)"),
    (b"\x00\x00", "ClipBox.xMin (0)"),
    (b"\x00\x00", "ClipBox.yMin (0)"),
    (b"\x01\xf4", "ClipBox.xMax (500)"),
    (b"\x01\xf4", "ClipBox.yMax (500)"),
    (b"\x00\x00\x00\t", "ClipBox.VarIndexBase (9)"),
    (b"\x01", "ClipBox.Format (1)"),
    (b"\x00\x00", "ClipBox.xMin (0)"),
    (b"\x00\x00", "ClipBox.yMin (0)"),
    (b"\x03\xe8", "ClipBox.xMax (1000)"),
    (b"\x03\xe8", "ClipBox.yMax (1000)"),
)

COLR_V1_DATA = b"".join(t[0] for t in COLR_V1_SAMPLE)

COLR_V1_XML = [
    '<Version value="1"/>',
    "<!-- BaseGlyphRecordCount=1 -->",
    "<BaseGlyphRecordArray>",
    '  <BaseGlyphRecord index="0">',
    '    <BaseGlyph value="glyph00006"/>',
    '    <FirstLayerIndex value="0"/>',
    '    <NumLayers value="3"/>',
    "  </BaseGlyphRecord>",
    "</BaseGlyphRecordArray>",
    "<LayerRecordArray>",
    '  <LayerRecord index="0">',
    '    <LayerGlyph value="glyph00007"/>',
    '    <PaletteIndex value="0"/>',
    "  </LayerRecord>",
    '  <LayerRecord index="1">',
    '    <LayerGlyph value="glyph00008"/>',
    '    <PaletteIndex value="1"/>',
    "  </LayerRecord>",
    '  <LayerRecord index="2">',
    '    <LayerGlyph value="glyph00009"/>',
    '    <PaletteIndex value="2"/>',
    "  </LayerRecord>",
    "</LayerRecordArray>",
    "<!-- LayerRecordCount=3 -->",
    "<BaseGlyphList>",
    "  <!-- BaseGlyphCount=3 -->",
    '  <BaseGlyphPaintRecord index="0">',
    '    <BaseGlyph value="glyph00010"/>',
    '    <Paint Format="1"><!-- PaintColrLayers -->',
    '      <NumLayers value="4"/>',
    '      <FirstLayerIndex value="0"/>',
    "    </Paint>",
    "  </BaseGlyphPaintRecord>",
    '  <BaseGlyphPaintRecord index="1">',
    '    <BaseGlyph value="glyph00014"/>',
    '    <Paint Format="32"><!-- PaintComposite -->',
    '      <SourcePaint Format="11"><!-- PaintColrGlyph -->',
    '        <Glyph value="glyph00010"/>',
    "      </SourcePaint>",
    '      <CompositeMode value="src_over"/>',
    '      <BackdropPaint Format="13"><!-- PaintVarTransform -->',
    '        <Paint Format="11"><!-- PaintColrGlyph -->',
    '          <Glyph value="glyph00010"/>',
    "        </Paint>",
    "        <Transform>",
    '          <xx value="1.0"/>',
    '          <yx value="0.0"/>',
    '          <xy value="0.0"/>',
    '          <yy value="1.0"/>',
    '          <dx value="300.0"/>',
    '          <dy value="0.0"/>',
    '          <VarIndexBase value="0"/>',
    "        </Transform>",
    "      </BackdropPaint>",
    "    </Paint>",
    "  </BaseGlyphPaintRecord>",
    '  <BaseGlyphPaintRecord index="2">',
    '    <BaseGlyph value="glyph00015"/>',
    '    <Paint Format="10"><!-- PaintGlyph -->',
    '      <Paint Format="8"><!-- PaintSweepGradient -->',
    "        <ColorLine>",
    '          <Extend value="pad"/>',
    "          <!-- StopCount=2 -->",
    '          <ColorStop index="0">',
    '            <StopOffset value="0.0"/>',
    '            <PaletteIndex value="3"/>',
    '            <Alpha value="1.0"/>',
    "          </ColorStop>",
    '          <ColorStop index="1">',
    '            <StopOffset value="1.0"/>',
    '            <PaletteIndex value="5"/>',
    '            <Alpha value="1.0"/>',
    "          </ColorStop>",
    "        </ColorLine>",
    '        <centerX value="259"/>',
    '        <centerY value="300"/>',
    '        <startAngle value="225.0"/>',
    '        <endAngle value="315.0"/>',
    "      </Paint>",
    '      <Glyph value="glyph00011"/>',
    "    </Paint>",
    "  </BaseGlyphPaintRecord>",
    "</BaseGlyphList>",
    "<LayerList>",
    "  <!-- LayerCount=5 -->",
    '  <Paint index="0" Format="10"><!-- PaintGlyph -->',
    '    <Paint Format="3"><!-- PaintVarSolid -->',
    '      <PaletteIndex value="2"/>',
    '      <Alpha value="0.5"/>',
    '      <VarIndexBase value="6"/>',
    "    </Paint>",
    '    <Glyph value="glyph00011"/>',
    "  </Paint>",
    '  <Paint index="1" Format="10"><!-- PaintGlyph -->',
    '    <Paint Format="4"><!-- PaintLinearGradient -->',
    "      <ColorLine>",
    '        <Extend value="repeat"/>',
    "        <!-- StopCount=3 -->",
    '        <ColorStop index="0">',
    '          <StopOffset value="0.0"/>',
    '          <PaletteIndex value="3"/>',
    '          <Alpha value="1.0"/>',
    "        </ColorStop>",
    '        <ColorStop index="1">',
    '          <StopOffset value="0.5"/>',
    '          <PaletteIndex value="4"/>',
    '          <Alpha value="1.0"/>',
    "        </ColorStop>",
    '        <ColorStop index="2">',
    '          <StopOffset value="1.0"/>',
    '          <PaletteIndex value="5"/>',
    '          <Alpha value="1.0"/>',
    "        </ColorStop>",
    "      </ColorLine>",
    '      <x0 value="1"/>',
    '      <y0 value="2"/>',
    '      <x1 value="-3"/>',
    '      <y1 value="-4"/>',
    '      <x2 value="5"/>',
    '      <y2 value="6"/>',
    "    </Paint>",
    '    <Glyph value="glyph00012"/>',
    "  </Paint>",
    '  <Paint index="2" Format="10"><!-- PaintGlyph -->',
    '    <Paint Format="12"><!-- PaintTransform -->',
    '      <Paint Format="7"><!-- PaintVarRadialGradient -->',
    "        <ColorLine>",
    '          <Extend value="pad"/>',
    "          <!-- StopCount=2 -->",
    '          <ColorStop index="0">',
    '            <StopOffset value="0.0"/>',
    '            <PaletteIndex value="6"/>',
    '            <Alpha value="1.0"/>',
    "            <VarIndexBase/>",
    "          </ColorStop>",
    '          <ColorStop index="1">',
    '            <StopOffset value="1.0"/>',
    '            <PaletteIndex value="7"/>',
    '            <Alpha value="0.4"/>',
    '            <VarIndexBase value="7"/>',
    "          </ColorStop>",
    "        </ColorLine>",
    '        <x0 value="7"/>',
    '        <y0 value="8"/>',
    '        <r0 value="9"/>',
    '        <x1 value="10"/>',
    '        <y1 value="11"/>',
    '        <r1 value="12"/>',
    "        <VarIndexBase/>",
    "      </Paint>",
    "      <Transform>",
    '        <xx value="-13.0"/>',
    '        <yx value="14.0"/>',
    '        <xy value="15.0"/>',
    '        <yy value="-17.0"/>',
    '        <dx value="18.0"/>',
    '        <dy value="19.0"/>',
    "      </Transform>",
    "    </Paint>",
    '    <Glyph value="glyph00013"/>',
    "  </Paint>",
    '  <Paint index="3" Format="14"><!-- PaintTranslate -->',
    '    <Paint Format="26"><!-- PaintRotateAroundCenter -->',
    '      <Paint Format="28"><!-- PaintSkew -->',
    '        <Paint Format="10"><!-- PaintGlyph -->',
    '          <Paint Format="2"><!-- PaintSolid -->',
    '            <PaletteIndex value="2"/>',
    '            <Alpha value="0.5"/>',
    "          </Paint>",
    '          <Glyph value="glyph00011"/>',
    "        </Paint>",
    '        <xSkewAngle value="-11.0"/>',
    '        <ySkewAngle value="5.0"/>',
    "      </Paint>",
    '      <angle value="45.0"/>',
    '      <centerX value="255"/>',
    '      <centerY value="256"/>',
    "    </Paint>",
    '    <dx value="257"/>',
    '    <dy value="258"/>',
    "  </Paint>",
    '  <Paint index="4" Format="10"><!-- PaintGlyph -->',
    '    <Paint Format="2"><!-- PaintSolid -->',
    '      <PaletteIndex value="2"/>',
    '      <Alpha value="0.5"/>',
    "    </Paint>",
    '    <Glyph value="glyph00011"/>',
    "  </Paint>",
    "</LayerList>",
    '<ClipList Format="1">',
    "  <Clip>",
    '    <Glyph value="glyph00010"/>',
    '    <ClipBox Format="2">',
    '      <xMin value="0"/>',
    '      <yMin value="0"/>',
    '      <xMax value="500"/>',
    '      <yMax value="500"/>',
    '      <VarIndexBase value="9"/>',
    "    </ClipBox>",
    "  </Clip>",
    "  <Clip>",
    '    <Glyph value="glyph00014"/>',
    '    <Glyph value="glyph00015"/>',
    '    <ClipBox Format="1">',
    '      <xMin value="0"/>',
    '      <yMin value="0"/>',
    '      <xMax value="1000"/>',
    '      <yMax value="1000"/>',
    "    </ClipBox>",
    "  </Clip>",
    "</ClipList>",
]

COLR_V1_VAR_XML = [
    '<VarIndexMap Format="0">',
    "  <!-- Omitted values default to 0xFFFF/0xFFFF (no variations) -->",
    '  <Map index="0" outer="1" inner="0"/>',
    '  <Map index="1"/>',
    '  <Map index="2"/>',
    '  <Map index="3" outer="1" inner="0"/>',
    '  <Map index="4"/>',
    '  <Map index="5"/>',
    '  <Map index="6" outer="0" inner="2"/>',
    '  <Map index="7" outer="0" inner="0"/>',
    '  <Map index="8" outer="0" inner="1"/>',
    '  <Map index="9"/>',
    '  <Map index="10"/>',
    '  <Map index="11" outer="0" inner="3"/>',
    '  <Map index="12" outer="0" inner="3"/>',
    "</VarIndexMap>",
    '<VarStore Format="1">',
    '  <Format value="1"/>',
    "  <VarRegionList>",
    "    <!-- RegionAxisCount=1 -->",
    "    <!-- RegionCount=1 -->",
    '    <Region index="0">',
    '      <VarRegionAxis index="0">',
    '        <StartCoord value="0.0"/>',
    '        <PeakCoord value="1.0"/>',
    '        <EndCoord value="1.0"/>',
    "      </VarRegionAxis>",
    "    </Region>",
    "  </VarRegionList>",
    "  <!-- VarDataCount=2 -->",
    '  <VarData index="0">',
    "    <!-- ItemCount=4 -->",
    '    <NumShorts value="1"/>',
    "    <!-- VarRegionCount=1 -->",
    '    <VarRegionIndex index="0" value="0"/>',
    '    <Item index="0" value="[-3277]"/>',
    '    <Item index="1" value="[6553]"/>',
    '    <Item index="2" value="[8192]"/>',
    '    <Item index="3" value="[500]"/>',
    "  </VarData>",
    '  <VarData index="1">',
    "    <!-- ItemCount=1 -->",
    '    <NumShorts value="32769"/>',
    "    <!-- VarRegionCount=1 -->",
    '    <VarRegionIndex index="0" value="0"/>',
    '    <Item index="0" value="[65536]"/>',
    "  </VarData>",
    "</VarStore>",
]


class COLR_V1_Test(object):
    def test_decompile_and_compile(self, font):
        colr = table_C_O_L_R_()
        colr.decompile(COLR_V1_DATA, font)
        diff_binary_fragments(colr.compile(font), COLR_V1_SAMPLE)

    def test_decompile_and_dump_xml(self, font):
        colr = table_C_O_L_R_()
        colr.decompile(COLR_V1_DATA, font)

        dump(colr, font)
        assert getXML(colr.toXML, font) == COLR_V1_XML

    def test_load_from_xml_and_compile(self, font):
        colr = table_C_O_L_R_()
        for name, attrs, content in parseXML(COLR_V1_XML):
            colr.fromXML(name, attrs, content, font)
        diff_binary_fragments(colr.compile(font), COLR_V1_SAMPLE)

    def test_round_trip_xml(self, font):
        colr = table_C_O_L_R_()
        for name, attrs, content in parseXML(COLR_V1_XML):
            colr.fromXML(name, attrs, content, font)
        compiled = colr.compile(font)

        colr = table_C_O_L_R_()
        colr.decompile(compiled, font)
        assert getXML(colr.toXML, font) == COLR_V1_XML

    @pytest.mark.parametrize("quantization", [1, 10, 100])
    @pytest.mark.parametrize("flavor", ["glyf", "cff"])
    def test_computeClipBoxes(self, flavor, quantization):
        font = TTFont()
        font.importXML(TEST_DATA_DIR / f"COLRv1-clip-boxes-{flavor}.ttx")
        assert font["COLR"].table.ClipList is None

        font["COLR"].table.computeClipBoxes(font.getGlyphSet(), quantization)

        clipList = font["COLR"].table.ClipList
        assert len(clipList.clips) > 0

        expected = TTFont()
        expected.importXML(
            TEST_DATA_DIR / f"COLRv1-clip-boxes-q{quantization}-expected.ttx"
        )
        expectedClipList = expected["COLR"].table.ClipList

        assert getXML(clipList.toXML) == getXML(expectedClipList.toXML)


class COLR_V1_Variable_Test(object):
    def test_round_trip_xml(self, font):
        colr = table_C_O_L_R_()
        xml = COLR_V1_XML + COLR_V1_VAR_XML
        for name, attrs, content in parseXML(xml):
            colr.fromXML(name, attrs, content, font)
        compiled = colr.compile(font)

        colr = table_C_O_L_R_()
        colr.decompile(compiled, font)
        assert getXML(colr.toXML, font) == xml
