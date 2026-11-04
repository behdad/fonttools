import pytest
from pathlib import Path

pathops = pytest.importorskip("pathops")

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.removeOverlaps import removeOverlaps, _simplify, _round_path

DATA_DIR = Path(__file__).parent / "data"


def test_pathops_simplify_bug_workaround():
    # Paths extracted from Noto Sans Ethiopic instance that fails skia-pathops
    # https://github.com/google/fonts/issues/3365
    # https://bugs.chromium.org/p/skia/issues/detail?id=11958
    path = pathops.Path()
    path.moveTo(550.461, 0)
    path.lineTo(550.461, 366.308)
    path.lineTo(713.229, 366.308)
    path.lineTo(713.229, 0)
    path.close()
    path.moveTo(574.46, 0)
    path.lineTo(574.46, 276.231)
    path.lineTo(737.768, 276.231)
    path.quadTo(820.075, 276.231, 859.806, 242.654)
    path.quadTo(899.537, 209.077, 899.537, 144.154)
    path.quadTo(899.537, 79, 853.46, 39.5)
    path.quadTo(807.383, 0, 712.383, 0)
    path.close()

    # check that it fails without workaround
    with pytest.raises(pathops.PathOpsError):
        pathops.simplify(path)

    result = _simplify(path, debugGlyphName="a")

    expected = pathops.Path()
    expected.moveTo(550, 0)
    expected.lineTo(550, 366)
    expected.lineTo(713, 366)
    expected.lineTo(713, 276)
    expected.lineTo(738, 276)
    expected.quadTo(820, 276, 860, 243)
    expected.quadTo(900, 209, 900, 144)
    expected.quadTo(900, 79, 853, 40)
    expected.quadTo(807.242, 0.211, 713, 0.001)
    expected.lineTo(713, 0)
    expected.close()

    assert expected == _round_path(result, round=lambda v: round(v, 3))

    reversed_result = _simplify(path, debugGlyphName="a", clockwise=False)
    assert not reversed_result.clockwise
    assert abs(reversed_result.area) == pytest.approx(abs(result.area))
    assert reversed_result.bounds == pytest.approx(result.bounds)


def test_CFF_CharString_width_nominalWidthX():
    font_path = DATA_DIR / "IBMPlexSans-Bold.subset.otf"
    font = TTFont(str(font_path))

    assert font["hmtx"]["OE"][0] == 998

    # calcBounds() has the side effect of setting the width attribute
    font["CFF "].cff[0].CharStrings["OE"].calcBounds({})
    assert font["CFF "].cff[0].CharStrings["OE"].width == font["hmtx"]["OE"][0]

    removeOverlaps(font)

    assert font["hmtx"]["OE"][0] == 998

    font["CFF "].cff[0].CharStrings["OE"].calcBounds({})
    assert font["CFF "].cff[0].CharStrings["OE"].width == font["hmtx"]["OE"][0]


def test_remove_overlaps_beyond64k_glyf():
    fb = FontBuilder(1024, isTTF=True, beyond64k=True)
    fb.setupGlyphOrder([".notdef", "A"])

    pen = TTGlyphPen(None)
    emptyGlyph = pen.glyph()

    pen = TTGlyphPen(None)
    pen.moveTo((0, 0))
    pen.lineTo((100, 0))
    pen.lineTo((100, 100))
    pen.lineTo((0, 100))
    pen.closePath()
    pen.moveTo((50, 0))
    pen.lineTo((150, 0))
    pen.lineTo((150, 100))
    pen.lineTo((50, 100))
    pen.closePath()
    glyph = pen.glyph()

    fb.setupGlyf({".notdef": emptyGlyph, "A": glyph})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (500, 10)})

    removeOverlaps(fb.font)

    assert "GLYF" in fb.font
    assert "HMTX" in fb.font
    assert fb.font["GLYF"]["A"].numberOfContours == 1
    assert fb.font["HMTX"]["A"] == (500, 10)


def _winding_font(outline_tag):
    is_ttf = outline_tag in {"glyf", "GLYF"}
    fb = FontBuilder(1000, isTTF=is_ttf, beyond64k=outline_tag == "GLYF")
    fb.setupGlyphOrder([".notdef", "A"])
    glyphs = {}
    for name in fb.font.getGlyphOrder():
        if is_ttf:
            pen = TTGlyphPen(None)
        else:
            pen = T2CharStringPen(
                None if outline_tag == "CFF2" else 800,
                None,
                CFF2=outline_tag == "CFF2",
            )
        if name == "A":
            for points in (
                [(100, 0), (700, 0), (700, 700), (100, 700)],
                [(300, 200), (300, 500), (500, 500), (500, 200)],
            ):
                if not is_ttf:
                    points.reverse()
                pen.moveTo(points[0])
                for point in points[1:]:
                    pen.lineTo(point)
                pen.closePath()
        glyphs[name] = pen.glyph() if is_ttf else pen.getCharString()
    if is_ttf:
        fb.setupGlyf(glyphs)
    elif outline_tag == "CFF2":
        fb.setupCFF2(glyphs)
    else:
        fb.setupCFF("Winding", {}, glyphs, {})
    fb.setupHorizontalMetrics({".notdef": (800, 0), "A": (800, 100)})
    return fb.font


def _glyph_path(font, name):
    glyph_set = font.getGlyphSet()
    path = pathops.Path()
    glyph_set[name].draw(path.getPen(glyphSet=glyph_set))
    return path


@pytest.mark.parametrize("outline_tag", ["glyf", "GLYF", "CFF ", "CFF2"])
@pytest.mark.parametrize("fix_winding", [False, True])
def test_remove_overlaps_winding(outline_tag, fix_winding):
    font = _winding_font(outline_tag)
    is_ttf = outline_tag in {"glyf", "GLYF"}
    original = _glyph_path(font, "A")
    assert original.clockwise != is_ttf

    if fix_winding:
        removeOverlaps(font, fixWinding=True)
    else:
        removeOverlaps(font)

    result = _glyph_path(font, "A")
    assert result.clockwise == (is_ttf if fix_winding else not is_ttf)
    assert abs(result.area) == pytest.approx(abs(original.area))
    assert result.bounds == original.bounds
    hmtx_tag = "HMTX" if outline_tag == "GLYF" else "hmtx"
    assert font[hmtx_tag]["A"] == (800, 100)


@pytest.mark.parametrize("outline_tag", ["glyf", "GLYF"])
def test_fix_winding_selected_composite(outline_tag):
    font = _winding_font(outline_tag)
    pen = TTGlyphPen(font.getGlyphSet())
    pen.addComponent("A", (1, 0, 0, 1, 0, 0))
    font[outline_tag]["C"] = pen.glyph()
    hmtx_tag = "HMTX" if outline_tag == "GLYF" else "hmtx"
    font[hmtx_tag]["C"] = (800, 100)
    font.setGlyphOrder([".notdef", "A", "C"])
    original = _glyph_path(font, "C")
    assert not original.clockwise

    removeOverlaps(font, ["C"], fixWinding=True)

    result = _glyph_path(font, "C")
    assert result.clockwise
    assert abs(result.area) == pytest.approx(abs(original.area))
    assert result.bounds == original.bounds
    assert not _glyph_path(font, "A").clockwise
    assert font[hmtx_tag]["C"] == (800, 100)
