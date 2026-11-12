import pytest

from io import BytesIO
from pathlib import Path
from fontTools import subset
from fontTools.cffLib import FDSelect, SubrsIndex
from fontTools.cffLib.CFF2ToCFF import convertCFF2ToCFF
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.misc.psCharStrings import T2CharString
from fontTools.otlLib.builder import buildMathTable
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.reorderGlyphs import reorderGlyphs

DATA_DIR = Path(__file__).parent / "data"


@pytest.mark.parametrize("lazy", [True, False, None])
def test_reorder_lazy_ligatures(lazy):
    fb = FontBuilder(1000)
    fb.setupGlyphOrder([".notdef", "a", "b", "a_b", "unused"])
    fb.setupPost()
    addOpenTypeFeaturesFromString(fb.font, "feature liga { sub a b by a_b; } liga;")
    data = BytesIO()
    fb.font.save(data)
    font = TTFont(BytesIO(data.getvalue()), lazy=lazy)
    order = font.getGlyphOrder()
    reorderGlyphs(font, order[:1] + list(reversed(order[1:])))
    output = BytesIO()
    font.save(output)
    font = TTFont(BytesIO(output.getvalue()))
    ligature = font["GSUB"].table.LookupList.Lookup[0].SubTable[0].ligatures["a"][0]
    assert ligature.Component == ["b"]
    assert ligature.LigGlyph == "a_b"


def test_ensure_decompiled_high_level_ligatures():
    from fontTools.ttLib.tables import otTables

    subtable = otTables.LigatureSubst()
    subtable.ensureDecompiled(recurse=True)
    subtable.ligatures = {("a", "b"): "a_b"}
    subtable.ensureDecompiled(recurse=True)
    assert subtable.ligatures == {("a", "b"): "a_b"}


@pytest.mark.parametrize("lazy", [True, False, None])
def test_reorder_glyphs(lazy):
    font_path = DATA_DIR / "Test-Regular.ttf"
    font = TTFont(str(font_path), lazy=lazy)
    old_coverage1 = list(
        font["GSUB"].table.LookupList.Lookup[0].SubTable[0].Coverage[0].glyphs
    )
    old_coverage2 = list(
        font["GPOS"].table.LookupList.Lookup[0].SubTable[0].Coverage.glyphs
    )

    ga = font.getGlyphOrder()
    ga = [ga[0]] + list(reversed(ga[1:]))
    reorderGlyphs(font, ga)

    new_coverage1 = list(
        font["GSUB"].table.LookupList.Lookup[0].SubTable[0].Coverage[0].glyphs
    )
    new_coverage2 = list(
        font["GPOS"].table.LookupList.Lookup[0].SubTable[0].Coverage.glyphs
    )

    assert list(reversed(old_coverage1)) == new_coverage1
    assert list(reversed(old_coverage2)) == new_coverage2


def test_ttfont_reorder_glyphs():
    font_path = DATA_DIR / "Test-Regular.ttf"
    font = TTFont(str(font_path))
    ga = font.getGlyphOrder()
    ga = [ga[0]] + list(reversed(ga[1:]))

    old_coverage1 = list(
        font["GSUB"].table.LookupList.Lookup[0].SubTable[0].Coverage[0].glyphs
    )
    old_coverage2 = list(
        font["GPOS"].table.LookupList.Lookup[0].SubTable[0].Coverage.glyphs
    )

    font.reorderGlyphs(ga)

    new_coverage1 = list(
        font["GSUB"].table.LookupList.Lookup[0].SubTable[0].Coverage[0].glyphs
    )
    new_coverage2 = list(
        font["GPOS"].table.LookupList.Lookup[0].SubTable[0].Coverage.glyphs
    )

    assert list(reversed(old_coverage1)) == new_coverage1
    assert list(reversed(old_coverage2)) == new_coverage2


def test_reorder_glyphs_cff():
    font_path = DATA_DIR / "TestVGID-Regular.otf"
    font = TTFont(str(font_path))
    ga = font.getGlyphOrder()
    ga = list(reversed(ga))
    reorderGlyphs(font, ga)

    assert list(font["CFF "].cff.topDictIndex[0].CharStrings.charStrings.keys()) == ga
    assert font["CFF "].cff.topDictIndex[0].charset == ga


@pytest.mark.parametrize("cff2", [False, True])
@pytest.mark.parametrize("source", ["binary", "xml", "compiled_xml"])
def test_reorder_glyphs_fdselect(cff2, source):
    order = [".notdef", "a", "b"]
    fb = FontBuilder(1000, isTTF=False)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x61: "a", 0x62: "b"})
    fb.setupHorizontalMetrics({name: (500, 0) for name in order})
    fb.setupHorizontalHeader()
    fb.setupPost()
    fb.setupCFF2(
        {
            name: T2CharString(program=[0, 0, "rmoveto", -107, "callsubr"])
            for name in order
        },
        fdArrayList=[{}, {}],
    )
    top = fb.font["CFF2"].cff[0]
    top.FDSelect = FDSelect(format=3)
    top.CharStrings.fdSelect = top.FDSelect
    for i, fd in enumerate(top.FDArray):
        private = fd.Private
        private.Subrs = SubrsIndex()
        private.Subrs.append(
            T2CharString(
                program=[100 * (i + 1), 0, "rlineto"],
                private=private,
                globalSubrs=top.GlobalSubrs,
            )
        )
    for name, selector in zip(order, [0, 0, 1]):
        charstring = top.CharStrings[name]
        charstring.fdSelectIndex = selector
        charstring.private = top.FDArray[selector].Private

    data = BytesIO()
    fb.font.save(data)
    font = TTFont(BytesIO(data.getvalue()), recalcBBoxes=False)
    if not cff2:
        convertCFF2ToCFF(font)
        data = BytesIO()
        font.save(data)
        font = TTFont(BytesIO(data.getvalue()))
    tag = "CFF2" if cff2 else "CFF "

    def outlines(font):
        glyph_set = font.getGlyphSet()
        result = {}
        for name in font.getGlyphOrder():
            pen = RecordingPen()
            glyph_set[name].draw(pen)
            result[name] = pen.value
        return result

    expected = outlines(font)
    data = BytesIO()
    font.save(data)
    font = TTFont(BytesIO(data.getvalue()))
    if source != "binary":
        xml = BytesIO()
        font.saveXML(xml)
        font = TTFont()
        font.importXML(BytesIO(xml.getvalue()))
        if source == "compiled_xml":
            font.save(BytesIO())

    # Load only the name-to-index mapping, leaving the individual charstrings
    # lazy. This isolates FDSelect reordering from the CFF2 naming bug in #4411.
    font[tag].cff[0].CharStrings
    order = font.getGlyphOrder()
    new_order = order[:1] + list(reversed(order[1:]))
    for glyph_order in [new_order, order, new_order]:
        reorderGlyphs(font, glyph_order)
        top = font[tag].cff[0]
        assert {
            name: top.CharStrings.getItemAndSelector(name)[1] for name in order
        } == dict(zip(order, [0, 0, 1]))
        assert outlines(font) == expected
        data = BytesIO()
        font.save(data)
        reopened = TTFont(BytesIO(data.getvalue()))
        assert outlines(reopened) == expected
        top = reopened[tag].cff[0]
        assert {
            name: top.CharStrings.getItemAndSelector(name)[1] for name in order
        } == dict(zip(order, [0, 0, 1]))

    if source == "binary":
        # Subsequent edits must see the same order in the INDEX and FDSelect.
        options = subset.Options()
        options.notdef_outline = True
        subsetter = subset.Subsetter(options=options)
        subsetter.populate(glyphs=order[-1:])
        subsetter.subset(font)
        expected = {name: expected[name] for name in font.getGlyphOrder()}
        assert outlines(font) == expected
        data = BytesIO()
        font.save(data)
        assert outlines(TTFont(BytesIO(data.getvalue()))) == expected


def test_reorder_glyphs_math_null_coverage():
    # buildMathTable leaves ExtendedShapeCoverage and HorizGlyphCoverage as null
    # offsets when there are no extended shapes or horizontal variants.
    fb = FontBuilder(1000, isTTF=True)
    glyph_order = [".notdef", "a", "b", "c", "parenleft", "parenleft.size1"]
    fb.setupGlyphOrder(glyph_order)
    fb.setupGlyf({g: TTGlyphPen(None).glyph() for g in glyph_order})
    fb.setupHorizontalMetrics({g: (500, 0) for g in glyph_order})
    fb.setupHorizontalHeader()
    fb.setupPost()
    buildMathTable(
        fb.font,
        italicsCorrections={"a": 10, "c": 30, "b": 20},
        vertGlyphVariants={
            "parenleft": [("parenleft", 1000), ("parenleft.size1", 1500)]
        },
    )
    buf = BytesIO()
    fb.save(buf)
    buf.seek(0)
    font = TTFont(buf)
    math = font["MATH"].table
    assert math.MathGlyphInfo.ExtendedShapeCoverage is None
    assert math.MathVariants.HorizGlyphCoverage is None

    ga = font.getGlyphOrder()
    ga = [ga[0]] + list(reversed(ga[1:]))
    reorderGlyphs(font, ga)

    italics = math.MathGlyphInfo.MathItalicsCorrectionInfo
    assert italics.Coverage.glyphs == ["c", "b", "a"]
    assert [v.Value for v in italics.ItalicsCorrection] == [30, 20, 10]
    assert math.MathVariants.VertGlyphCoverage.glyphs == ["parenleft"]


def test_reorder_glyphs_bad_length(caplog):
    font_path = DATA_DIR / "Test-Regular.ttf"
    font = TTFont(str(font_path))
    with pytest.raises(ValueError) as ex:
        reorderGlyphs(font, ["A"])
    assert "New glyph order contains 1 glyphs" in str(ex.value)


def test_reorder_glyphs_bad_set(caplog):
    font_path = DATA_DIR / "Test-Regular.ttf"
    font = TTFont(str(font_path))
    ga = list(font.getGlyphOrder()) + ["AA"]
    ga.pop(1)
    with pytest.raises(ValueError) as ex:
        reorderGlyphs(font, ga)
    assert "New glyph order does not contain the same set of glyphs" in str(ex.value)


@pytest.mark.parametrize("lazy", [True, False, None])
@pytest.mark.parametrize("pairpos", [False, True])
def test_reorder_lazy_arrays(lazy, pairpos):
    from fontTools.misc.lazyTools import LazyList

    fb = FontBuilder(1000)
    order = [".notdef"] + [f"g{i}" for i in range(10)]
    fb.setupGlyphOrder(order)
    fb.setupPost()
    if pairpos:
        statements = [f"pos g0 g{i} {i + 1};" for i in range(10)]
    else:
        statements = [f"pos g{i} {i + 1};" for i in range(10)]
    addOpenTypeFeaturesFromString(
        fb.font, "feature kern { " + " ".join(statements) + " } kern;"
    )
    data = BytesIO()
    fb.font.save(data)
    font = TTFont(BytesIO(data.getvalue()), lazy=lazy)
    subtable = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    records = subtable.PairSet[0].PairValueRecord if pairpos else subtable.Value
    assert isinstance(records, LazyList) == bool(lazy)
    reorderGlyphs(font, order[:1] + list(reversed(order[1:])))
    output = BytesIO()
    font.save(output)
    font = TTFont(BytesIO(output.getvalue()))
    subtable = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    if pairpos:
        assert subtable.Coverage.glyphs == ["g0"]
        pairs = subtable.PairSet[0].PairValueRecord
        assert [record.SecondGlyph for record in pairs] == list(reversed(order[1:]))
        assert {
            (first, record.SecondGlyph): record.Value1.XAdvance
            for first, pair_set in zip(subtable.Coverage.glyphs, subtable.PairSet)
            for record in pair_set.PairValueRecord
        } == {("g0", f"g{i}"): i + 1 for i in range(10)}
    else:
        assert subtable.Coverage.glyphs == list(reversed(order[1:]))
        assert [v.XAdvance for v in subtable.Value] == list(reversed(range(1, 11)))
