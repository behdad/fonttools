from fontTools.ttLib import TTFont
from fontTools.ttLib import ttGlyphSet
from fontTools.ttLib.beyond64k import upper_tables
from fontTools.ttLib.ttGlyphSet import LerpGlyphSet
from fontTools.ttLib.tables.otTables import (
    ConditionTable,
    NO_VARIATION_INDEX,
    VarComponentFlags,
)
from fontTools.pens.recordingPen import (
    RecordingPen,
    RecordingPointPen,
    DecomposingRecordingPen,
)
from fontTools.misc.roundTools import otRound
from fontTools.misc.transform import DecomposedTransform
from io import BytesIO, StringIO
import os
import pytest


class TTGlyphSetTest(object):
    @staticmethod
    def getpath(testfile):
        path = os.path.dirname(__file__)
        return os.path.join(path, "data", testfile)

    @pytest.mark.parametrize("initial", [{}, {"wght": 0.75}])
    @pytest.mark.parametrize("reset", [False, True])
    @pytest.mark.parametrize("nested", [False, True])
    @pytest.mark.parametrize("points", [False, True])
    def test_varc_reset_pen_location(self, initial, reset, nested, points):
        from contextlib import ExitStack
        from fontTools.ttLib import newTable
        from fontTools.ttLib.tables import otTables as ot
        from fontTools.pens.recordingPen import DecomposingRecordingPointPen
        from fontTools.pens.transformPen import TransformPen, TransformPointPen

        class OutlinePointPen(DecomposingRecordingPointPen):
            def addVarComponent(self, *args, **kwargs):
                raise AttributeError

        font = TTFont(self.getpath("I.ttf"))
        varc = font["VARC"] = newTable("VARC")
        table = varc.table = ot.VARC()
        table.Version = 0x00010000
        table.Coverage = ot.Coverage()
        table.Coverage.glyphs = [".notdef"]
        table.MultiVarStore = table.ConditionList = None
        table.AxisIndicesList = ot.AxisIndicesList()
        table.AxisIndicesList.Item = [[1]]
        component = ot.VarComponent()
        component.glyphName = "I"
        component.axisIndicesIndex = 0
        component.axisValues = (0.25,)
        if reset:
            component.flags = ot.VarComponentFlags.RESET_UNSPECIFIED_AXES
        table.VarCompositeGlyphs = ot.VarCompositeGlyphs()
        table.VarCompositeGlyphs.VarCompositeGlyph = [ot.VarCompositeGlyph([component])]

        glyphset = font.getGlyphSet(location=initial, normalized=True)
        pen_type = RecordingPointPen if points else RecordingPen
        decomposing_pen_type = OutlinePointPen if points else DecomposingRecordingPen
        transform_pen_type = TransformPointPen if points else TransformPen
        draw = "drawPoints" if points else "draw"
        with ExitStack() as stack:
            if nested:
                stack.enter_context(
                    glyphset.glyphSet.pushLocation({"wght": 0.25}, False)
                )
                stack.enter_context(glyphset.pushLocation({"wght": 0.25}, False))
            expected = decomposing_pen_type(glyphset)
            getattr(glyphset[".notdef"], draw)(expected)
            recording = pen_type()
            getattr(glyphset[".notdef"], draw)(recording)
            assert len(recording.value) == 1
            operator, operands = recording.value[0][:2]
            kwargs = recording.value[0][2] if len(recording.value[0]) == 3 else {}
            assert operator == "addVarComponent"
            name, transform, location = operands
            assert location == {"wdth": 0.25}
            assert kwargs == ({"resetUnspecifiedAxes": True} if reset else {})

            actual = decomposing_pen_type(glyphset)
            reset = kwargs.get("resetUnspecifiedAxes", False)
            with glyphset.glyphSet.pushLocation(location, reset):
                with glyphset.pushLocation(location, reset):
                    getattr(glyphset[name], draw)(
                        transform_pen_type(actual, transform.toTransform())
                    )
            assert actual.value == expected.value

    @pytest.mark.parametrize(
        "fontfile, location, expected",
        [
            (
                "I.ttf",
                None,
                [
                    ("moveTo", ((175, 0),)),
                    ("lineTo", ((367, 0),)),
                    ("lineTo", ((367, 1456),)),
                    ("lineTo", ((175, 1456),)),
                    ("closePath", ()),
                ],
            ),
            (
                "I.ttf",
                {},
                [
                    ("moveTo", ((175, 0),)),
                    ("lineTo", ((367, 0),)),
                    ("lineTo", ((367, 1456),)),
                    ("lineTo", ((175, 1456),)),
                    ("closePath", ()),
                ],
            ),
            (
                "I.ttf",
                {"wght": 100},
                [
                    ("moveTo", ((175, 0),)),
                    ("lineTo", ((271, 0),)),
                    ("lineTo", ((271, 1456),)),
                    ("lineTo", ((175, 1456),)),
                    ("closePath", ()),
                ],
            ),
            (
                "I.ttf",
                {"wght": 1000},
                [
                    ("moveTo", ((128, 0),)),
                    ("lineTo", ((550, 0),)),
                    ("lineTo", ((550, 1456),)),
                    ("lineTo", ((128, 1456),)),
                    ("closePath", ()),
                ],
            ),
            (
                "I.ttf",
                {"wght": 1000, "wdth": 25},
                [
                    ("moveTo", ((140, 0),)),
                    ("lineTo", ((553, 0),)),
                    ("lineTo", ((553, 1456),)),
                    ("lineTo", ((140, 1456),)),
                    ("closePath", ()),
                ],
            ),
            (
                "I.ttf",
                {"wght": 1000, "wdth": 50},
                [
                    ("moveTo", ((136, 0),)),
                    ("lineTo", ((552, 0),)),
                    ("lineTo", ((552, 1456),)),
                    ("lineTo", ((136, 1456),)),
                    ("closePath", ()),
                ],
            ),
            (
                "I.otf",
                {"wght": 1000},
                [
                    ("moveTo", ((179, 74),)),
                    ("lineTo", ((28, 59),)),
                    ("lineTo", ((28, 0),)),
                    ("lineTo", ((367, 0),)),
                    ("lineTo", ((367, 59),)),
                    ("lineTo", ((212, 74),)),
                    ("lineTo", ((179, 74),)),
                    ("closePath", ()),
                    ("moveTo", ((179, 578),)),
                    ("lineTo", ((212, 578),)),
                    ("lineTo", ((367, 593),)),
                    ("lineTo", ((367, 652),)),
                    ("lineTo", ((28, 652),)),
                    ("lineTo", ((28, 593),)),
                    ("lineTo", ((179, 578),)),
                    ("closePath", ()),
                    ("moveTo", ((98, 310),)),
                    ("curveTo", ((98, 205), (98, 101), (95, 0))),
                    ("lineTo", ((299, 0),)),
                    ("curveTo", ((296, 103), (296, 207), (296, 311))),
                    ("lineTo", ((296, 342),)),
                    ("curveTo", ((296, 447), (296, 551), (299, 652))),
                    ("lineTo", ((95, 652),)),
                    ("curveTo", ((98, 549), (98, 445), (98, 342))),
                    ("lineTo", ((98, 310),)),
                    ("closePath", ()),
                ],
            ),
            (
                # In this font, /I has an lsb of 30, but an xMin of 25, so an
                # offset of 5 units needs to be applied when drawing the outline.
                # See https://github.com/fonttools/fonttools/issues/2824
                "issue2824.ttf",
                None,
                [
                    ("moveTo", ((309, 180),)),
                    ("qCurveTo", ((274, 151), (187, 136), (104, 166), (74, 201))),
                    ("qCurveTo", ((45, 236), (30, 323), (59, 407), (95, 436))),
                    ("qCurveTo", ((130, 466), (217, 480), (301, 451), (330, 415))),
                    ("qCurveTo", ((360, 380), (374, 293), (345, 210), (309, 180))),
                    ("closePath", ()),
                ],
            ),
        ],
    )
    def test_glyphset(self, fontfile, location, expected):
        font = TTFont(self.getpath(fontfile))
        glyphset = font.getGlyphSet(location=location)

        assert isinstance(glyphset, ttGlyphSet._TTGlyphSet)

        assert list(glyphset.keys()) == [".notdef", "I"]

        assert "I" in glyphset
        with pytest.deprecated_call():
            assert glyphset.has_key("I")  # we should really get rid of this...

        assert len(glyphset) == 2

        pen = RecordingPen()
        glyph = glyphset["I"]

        assert glyphset.get("foobar") is None

        assert isinstance(glyph, ttGlyphSet._TTGlyph)
        is_glyf = fontfile.endswith(".ttf")
        glyphType = ttGlyphSet._TTGlyphGlyf if is_glyf else ttGlyphSet._TTGlyphCFF
        assert isinstance(glyph, glyphType)

        glyph.draw(pen)
        actual = pen.value

        assert actual == expected, (location, actual, expected)

    @pytest.mark.parametrize("location", [{}, {"wght": 1000}])
    def test_cff2_glyphset_from_xml(self, location):
        font = TTFont(self.getpath("I.otf"))
        expected = RecordingPen()
        font.getGlyphSet(location=location)["I"].draw(expected)

        xml = BytesIO()
        font.saveXML(xml)
        xml.seek(0)
        from_xml = TTFont()
        from_xml.importXML(xml)

        actual = RecordingPen()
        from_xml.getGlyphSet(location=location)["I"].draw(actual)
        assert actual.value == expected.value

    @pytest.mark.parametrize("initial", [{}, {"wght": 0.75, "CNTR": 0.5}])
    @pytest.mark.parametrize("reset", [False, True])
    def test_cff2_push_location_inherits_and_restores(self, initial, reset):
        font = TTFont(self.getpath("I.otf"))
        glyphset = font.getGlyphSet(location=initial, normalized=True)

        def outline(glyphset):
            pen = RecordingPen()
            glyphset["I"].draw(pen)
            return pen.value

        def check(location):
            assert glyphset.location == location
            expected = font.getGlyphSet(location=location, normalized=True)
            assert outline(glyphset) == outline(expected)

        with glyphset.pushLocation({"wght": 0.25}, False):
            parent = {**initial, "wght": 0.25}
            check(parent)
            with glyphset.pushLocation({"CNTR": 0.25}, reset):
                check({**(initial if reset else parent), "CNTR": 0.25})
            check(parent)
            with glyphset.pushLocation({}, False):
                check(parent)
            check(parent)
        check(initial)

    def test_cff2_push_location_restores_after_exception(self):
        font = TTFont(self.getpath("I.otf"))
        location = {"wght": 0.75, "CNTR": 0.5}
        glyphset = font.getGlyphSet(location=location, normalized=True)
        expected = RecordingPen()
        glyphset["I"].draw(expected)

        with pytest.raises(ValueError, match="drawing failed"):
            with glyphset.pushLocation({"wght": 0.25}, False):
                raise ValueError("drawing failed")

        assert glyphset.location == location
        actual = RecordingPen()
        glyphset["I"].draw(actual)
        assert actual.value == expected.value

    @pytest.mark.parametrize("reset", [False, True])
    def test_varc_cff2_nested_locations(self, reset):
        from fontTools.ttLib import newTable
        from fontTools.ttLib.tables import otTables as ot

        font = TTFont(self.getpath("I.otf"))
        location = {"wght": 0.75, "CNTR": 0.5}
        expected = []
        for weight in (0.75 if reset else 0.25, 0.75):
            pen = RecordingPen()
            font.getGlyphSet(location={"wght": weight, "CNTR": 0.25}, normalized=True)[
                "I"
            ].draw(pen)
            expected.extend(pen.value)

        varc = font["VARC"] = newTable("VARC")
        varc.table = ot.VARC()
        varc.table.Version = 0x00010000
        varc.table.Coverage = ot.Coverage()
        varc.table.Coverage.glyphs = [".notdef", "I"]
        varc.table.MultiVarStore = None
        varc.table.ConditionList = None
        varc.table.AxisIndicesList = ot.AxisIndicesList()
        varc.table.AxisIndicesList.Item = [[0], [1]]
        varc.table.VarCompositeGlyphs = ot.VarCompositeGlyphs()
        parent, child = ot.VarCompositeGlyph(), ot.VarCompositeGlyph()
        first, second, leaf = ot.VarComponent(), ot.VarComponent(), ot.VarComponent()
        first.glyphName = second.glyphName = leaf.glyphName = "I"
        first.axisIndicesIndex = 0
        first.axisValues = (0.25,)
        leaf.axisIndicesIndex = 1
        leaf.axisValues = (0.25,)
        if reset:
            leaf.flags = ot.VarComponentFlags.RESET_UNSPECIFIED_AXES
        parent.components = [first, second]
        child.components = [leaf]
        varc.table.VarCompositeGlyphs.VarCompositeGlyph = [parent, child]

        def check(font):
            glyphset = font.getGlyphSet(location=location, normalized=True)
            pen = DecomposingRecordingPen(glyphset)
            glyphset[".notdef"].draw(pen)
            assert pen.value == expected
            # Repeated drawing must not depend on a previous component's axes.
            pen = DecomposingRecordingPen(glyphset)
            glyphset[".notdef"].draw(pen)
            assert pen.value == expected

        check(font)
        stream = BytesIO()
        font.save(stream)
        check(TTFont(BytesIO(stream.getvalue())))

    @pytest.mark.parametrize(
        "fontfile, locations, factor, expected",
        [
            (
                "I.ttf",
                ({"wght": 400}, {"wght": 1000}),
                0.5,
                [
                    ("moveTo", ((151.5, 0.0),)),
                    ("lineTo", ((458.5, 0.0),)),
                    ("lineTo", ((458.5, 1456.0),)),
                    ("lineTo", ((151.5, 1456.0),)),
                    ("closePath", ()),
                ],
            ),
            (
                "I.ttf",
                ({"wght": 400}, {"wght": 1000}),
                0.25,
                [
                    ("moveTo", ((163.25, 0.0),)),
                    ("lineTo", ((412.75, 0.0),)),
                    ("lineTo", ((412.75, 1456.0),)),
                    ("lineTo", ((163.25, 1456.0),)),
                    ("closePath", ()),
                ],
            ),
        ],
    )
    def test_lerp_glyphset(self, fontfile, locations, factor, expected):
        font = TTFont(self.getpath(fontfile))
        glyphset1 = font.getGlyphSet(location=locations[0])
        glyphset2 = font.getGlyphSet(location=locations[1])
        glyphset = LerpGlyphSet(glyphset1, glyphset2, factor)

        assert "I" in glyphset

        pen = RecordingPen()
        glyph = glyphset["I"]

        assert glyphset.get("foobar") is None

        glyph.draw(pen)
        actual = pen.value

        assert actual == expected, (locations, actual, expected)

    def test_glyphset_varComposite_components(self):
        font = TTFont(self.getpath("varc-ac00-ac01.ttf"))
        glyphset = font.getGlyphSet()

        pen = RecordingPen()
        glyph = glyphset["uniAC00"]

        glyph.draw(pen)
        actual = pen.value

        expected = [
            (
                "addVarComponent",
                (
                    "glyph00003",
                    DecomposedTransform(
                        translateX=0,
                        translateY=0,
                        rotation=0,
                        scaleX=1,
                        scaleY=1,
                        skewX=0,
                        skewY=0,
                        tCenterX=0,
                        tCenterY=0,
                    ),
                    {},
                ),
            ),
            (
                "addVarComponent",
                (
                    "glyph00005",
                    DecomposedTransform(
                        translateX=0,
                        translateY=0,
                        rotation=0,
                        scaleX=1,
                        scaleY=1,
                        skewX=0,
                        skewY=0,
                        tCenterX=0,
                        tCenterY=0,
                    ),
                    {},
                ),
            ),
        ]

        assert actual == expected, (actual, expected)

    def test_glyphset_varComposite_conditional(self):
        font = TTFont(self.getpath("varc-ac01-conditional.ttf"))

        glyphset = font.getGlyphSet()
        pen = RecordingPen()
        glyph = glyphset["uniAC01"]
        glyph.draw(pen)
        assert len(pen.value) == 2

        glyphset = font.getGlyphSet(location={"wght": 800})
        pen = RecordingPen()
        glyph = glyphset["uniAC01"]
        glyph.draw(pen)
        assert len(pen.value) == 3

    @pytest.mark.parametrize("location", [None, {"wght": 800}])
    def test_glyphset_varComposite_uppercase_metrics(self, location):
        from fontTools.fontBuilder import FontBuilder

        font = TTFont(self.getpath("varc-ac01-conditional.ttf"))
        builder = FontBuilder(font=font)
        builder.setupVerticalMetrics(
            {name: (1024, 30) for name in font.getGlyphOrder()}
        )
        builder.setupVerticalHeader()
        glyphset = font.getGlyphSet(location=location)
        pen = DecomposingRecordingPen(glyphset)
        glyphset["uniAC01"].draw(pen)
        expected = pen.value
        expected_metrics = (
            glyphset["uniAC01"].width,
            glyphset["uniAC01"].lsb,
            glyphset["uniAC01"].height,
            glyphset["uniAC01"].tsb,
        )

        upper_tables(font)
        stream = BytesIO()
        font.save(stream)
        font = TTFont(BytesIO(stream.getvalue()))
        glyphset = font.getGlyphSet(location=location)
        pen = DecomposingRecordingPen(glyphset)
        glyphset["uniAC01"].draw(pen)
        assert pen.value == expected
        assert (
            glyphset["uniAC01"].width,
            glyphset["uniAC01"].lsb,
            glyphset["uniAC01"].height,
            glyphset["uniAC01"].tsb,
        ) == expected_metrics
        assert glyphset.hMetrics is font["HMTX"].metrics
        assert glyphset.vMetrics is font["VMTX"].metrics

    @pytest.mark.parametrize("draw_points", [False, True])
    def test_glyphset_varComposite_uppercase_static_axes(self, draw_points):
        from fontTools.pens.recordingPen import DecomposingRecordingPointPen

        font = TTFont(self.getpath("varc-static-gvar.ttf"))
        glyph_name = font["VARC"].table.Coverage.glyphs[0]
        pen_type = (
            DecomposingRecordingPointPen if draw_points else DecomposingRecordingPen
        )
        draw = "drawPoints" if draw_points else "draw"
        glyphset = font.getGlyphSet()
        pen = pen_type(glyphset)
        getattr(glyphset[glyph_name], draw)(pen)
        expected = pen.value

        upper_tables(font)
        stream = BytesIO()
        font.save(stream)
        font = TTFont(BytesIO(stream.getvalue()))
        assert "fvar" not in font
        assert "gvar" not in font
        glyphset = font.getGlyphSet()
        assert len(glyphset.axes) == font["GVAR"].axisCount == 1
        pen = pen_type(glyphset)
        getattr(glyphset[glyph_name], draw)(pen)
        assert pen.value == expected

    @pytest.mark.parametrize(
        "fontfile", ["I.otf", "../../cffLib/data/varc-short-cff2.otf"]
    )
    @pytest.mark.parametrize("vertical", [False, True])
    def test_glyphset_cff2_uppercase_metrics(self, fontfile, vertical):
        from fontTools.fontBuilder import FontBuilder

        font = TTFont(self.getpath(fontfile))
        if vertical:
            builder = FontBuilder(font=font)
            builder.setupVerticalMetrics(
                {name: (1024, 30) for name in font.getGlyphOrder()}
            )
            builder.setupVerticalHeader()
        else:
            for tag in ("vhea", "vmtx"):
                if tag in font:
                    del font[tag]

        def outlines_and_metrics(font):
            glyphset = font.getGlyphSet()
            result = {}
            for name in font.getGlyphOrder():
                glyph = glyphset[name]
                pen = DecomposingRecordingPen(glyphset)
                glyph.draw(pen)
                result[name] = (
                    pen.value,
                    glyph.width,
                    glyph.lsb,
                    glyph.height,
                    glyph.tsb,
                )
            return result

        expected = outlines_and_metrics(font)
        upper_tables(font)
        assert outlines_and_metrics(font) == expected
        stream = BytesIO()
        font.save(stream)
        reloaded = TTFont(BytesIO(stream.getvalue()))
        assert outlines_and_metrics(reloaded) == expected

    @pytest.mark.parametrize(
        "fontfile",
        [
            "I.ttf",
            "I.otf",
            "varc-ac01-conditional.ttf",
            "../../cffLib/data/varc-short-cff2.otf",
        ],
    )
    @pytest.mark.parametrize("uppercase", [False, True])
    @pytest.mark.parametrize("mapped", [False, True])
    @pytest.mark.parametrize("hvar", [False, True])
    def test_glyphset_vvar_height(self, fontfile, uppercase, mapped, hvar):
        from fontTools.fontBuilder import FontBuilder
        from fontTools.ttLib import newTable
        from fontTools.ttLib.tables import otTables as ot
        from fontTools.varLib.builder import (
            buildVarData,
            buildVarIdxMap,
            buildVarRegionList,
            buildVarStore,
        )

        font = TTFont(self.getpath(fontfile))
        builder = FontBuilder(font=font)
        if "fvar" not in font:
            builder.setupFvar([("TEST", 0, 0, 1, "Test")], [])
        order = font.getGlyphOrder()
        builder.setupVerticalMetrics({name: (1000, 20) for name in order})
        builder.setupVerticalHeader()
        axes = [axis.axisTag for axis in font["fvar"].axes]
        deltas = [100 + gid * 20 for gid in range(len(order))]
        regions = buildVarRegionList([{axes[0]: (0, 1, 1)}], axes)
        font["VVAR"] = newTable("VVAR")
        vvar = font["VVAR"].table = ot.VVAR()
        vvar.Version = 0x00010000
        vvar.VarStore = buildVarStore(
            regions, [buildVarData([0], [[d] for d in deltas])]
        )
        indices = (
            list(reversed(range(len(order)))) if mapped else list(range(len(order)))
        )
        vvar.AdvHeightMap = buildVarIdxMap(indices, order) if mapped else None
        vvar.TsbMap = vvar.BsbMap = vvar.VOrgMap = None
        if hvar and "HVAR" not in font:
            font["HVAR"] = newTable("HVAR")
            table = font["HVAR"].table = ot.HVAR()
            table.Version = 0x00010000
            table.VarStore = buildVarStore(
                regions, [buildVarData([0], [[0]] * len(order))]
            )
            table.AdvWidthMap = table.LsbMap = table.RsbMap = None
        elif not hvar and "HVAR" in font:
            del font["HVAR"]
        if uppercase:
            upper_tables(font)
        stream = BytesIO()
        font.save(stream)
        font = TTFont(BytesIO(stream.getvalue()))
        glyphset = font.getGlyphSet(location={axes[0]: 0.5}, normalized=True)
        for gid, name in enumerate(order):
            glyph = glyphset[name]
            expected = 1000 + deltas[indices[gid]] / 2
            assert glyph.height == expected
            glyph.draw(DecomposingRecordingPen(glyphset))
            assert glyph.height == expected

    @pytest.mark.parametrize("gid", [0, 0xFFFF, 0x10000, 0x10001])
    @pytest.mark.parametrize("mapped", [False, True])
    @pytest.mark.parametrize("uppercase", [False, True])
    def test_advance_mapping_high_glyph_id(self, gid, mapped, uppercase, monkeypatch):
        from fontTools.fontBuilder import FontBuilder
        from fontTools.ttLib import newTable
        from fontTools.ttLib.tables import otTables as ot
        from fontTools.varLib.builder import (
            buildVarData,
            buildVarIdxMap,
            buildVarRegionList,
            buildVarStore,
        )

        font = TTFont(self.getpath("I.otf"))
        builder = FontBuilder(font=font)
        order = font.getGlyphOrder()
        builder.setupVerticalMetrics({name: (800, 20) for name in order})
        builder.setupVerticalHeader()
        axes = [axis.axisTag for axis in font["fvar"].axes]
        regions = buildVarRegionList([{axes[0]: (0, 1, 1)}], axes)
        store = buildVarStore(
            regions, [buildVarData([0], [[10]]), buildVarData([0], [[100], [200]])]
        )
        for tag, map_name in [("HVAR", "AdvWidthMap"), ("VVAR", "AdvHeightMap")]:
            font[tag] = newTable(tag)
            table = font[tag].table = getattr(ot, tag)()
            table.Version = 0x00010000
            table.VarStore = store
            mapping = buildVarIdxMap([0x10000] * len(order), order) if mapped else None
            setattr(table, map_name, mapping)
        if uppercase:
            upper_tables(font)
        # Simulate a high glyph ID without constructing a 65K-glyph fixture.
        monkeypatch.setattr(font, "getGlyphID", lambda name: gid)
        glyphset = font.getGlyphSet(location={axes[0]: 0.5}, normalized=True)
        glyph = glyphset[order[0]]
        delta = 50 if mapped else 5 if gid == 0 else 0
        assert glyph.width == glyphset.hMetrics[order[0]][0] + delta
        assert glyph.height == 800 + delta

    @pytest.mark.parametrize(
        "format, expected_components", [(None, 3), (3, 3), (4, 3), (5, 2)]
    )
    def test_glyphset_varComposite_null_condition(self, format, expected_components):
        font = TTFont(self.getpath("varc-ac01-conditional.ttf"))
        condition = None
        if format is not None:
            condition = ConditionTable()
            condition.Format = format
            condition.ConditionTable = None if format == 5 else [None]
        font["VARC"].table.ConditionList.ConditionTable[0] = condition

        stream = BytesIO()
        font.save(stream)
        stream.seek(0)
        font = TTFont(stream)
        pen = RecordingPen()
        font.getGlyphSet()["uniAC01"].draw(pen)
        assert len(pen.value) == expected_components

    @pytest.mark.parametrize(
        "default_value, expected_components", [(-1, 2), (0, 2), (1, 3)]
    )
    @pytest.mark.parametrize("with_store", [False, True])
    def test_glyphset_varComposite_static_value_condition(
        self, default_value, expected_components, with_store
    ):
        font = TTFont(self.getpath("varc-ac01-conditional.ttf"))
        varc = font["VARC"].table
        condition = ConditionTable()
        condition.Format = 2
        condition.DefaultValue = default_value
        condition.VarIdx = NO_VARIATION_INDEX
        varc.ConditionList.ConditionTable[0] = condition
        if not with_store:
            varc.MultiVarStore = None
            for glyph in varc.VarCompositeGlyphs.VarCompositeGlyph:
                for component in glyph.components:
                    component.axisValuesVarIndex = NO_VARIATION_INDEX
                    component.transformVarIndex = NO_VARIATION_INDEX

        stream = BytesIO()
        font.save(stream)
        stream.seek(0)
        font = TTFont(stream)
        pen = RecordingPen()
        font.getGlyphSet()["uniAC01"].draw(pen)
        assert len(pen.value) == expected_components

    @pytest.mark.parametrize("scale", [-0.5, 0.5])
    def test_varc_xml_implicit_scale_y(self, scale):
        from fontTools.ttLib.tables.otTables import VarComponentFlags

        font = TTFont(self.getpath("varc-ac00-ac01.ttf"))
        component = (
            font["VARC"].table.VarCompositeGlyphs.VarCompositeGlyph[0].components[0]
        )
        component.transform.scaleX = component.transform.scaleY = scale
        component.flags |= VarComponentFlags.HAVE_SCALE_X
        component.flags &= ~VarComponentFlags.HAVE_SCALE_Y

        def draw(font):
            glyphset = font.getGlyphSet()
            pen = DecomposingRecordingPen(glyphset)
            glyphset["uniAC00"].draw(pen)
            return pen.value

        expected = draw(font)
        xml = StringIO()
        font.saveXML(xml)
        xml.seek(0)
        font = TTFont()
        font.importXML(xml)
        assert draw(font) == expected

        stream = BytesIO()
        font.save(stream)
        assert draw(TTFont(BytesIO(stream.getvalue()))) == expected

    @pytest.mark.parametrize(
        "location, negations, expected_components",
        [({}, 1, 3), ({"wght": 800}, 1, 2), ({}, 2, 2), ({"wght": 800}, 2, 3)],
    )
    def test_glyphset_varComposite_negated_condition(
        self, location, negations, expected_components
    ):
        font = TTFont(self.getpath("varc-ac01-conditional.ttf"))
        conditions = font["VARC"].table.ConditionList.ConditionTable
        for _ in range(negations):
            negated = ConditionTable()
            negated.Format = 5
            negated.ConditionTable = conditions[0]
            conditions[0] = negated

        stream = BytesIO()
        font.save(stream)
        stream.seek(0)
        font = TTFont(stream)
        glyphset = font.getGlyphSet(location=location)
        pen = RecordingPen()
        glyphset["uniAC01"].draw(pen)
        assert len(pen.value) == expected_components

    def test_glyphset_varComposite1(self):
        font = TTFont(self.getpath("varc-ac00-ac01.ttf"))
        glyphset = font.getGlyphSet(location={"wght": 600})

        pen = DecomposingRecordingPen(glyphset)
        glyph = glyphset["uniAC00"]

        glyph.draw(pen)
        actual = pen.value

        expected = [
            ("moveTo", ((82, 108),)),
            ("qCurveTo", ((188, 138), (350, 240), (461, 384), (518, 567), (518, 678))),
            ("lineTo", ((518, 732),)),
            ("lineTo", ((74, 732),)),
            ("lineTo", ((74, 630),)),
            ("lineTo", ((456, 630),)),
            ("lineTo", ((403, 660),)),
            ("qCurveTo", ((403, 575), (358, 431), (267, 314), (128, 225), (34, 194))),
            ("closePath", ()),
            ("moveTo", ((702, 385),)),
            ("lineTo", ((897, 385),)),
            ("lineTo", ((897, 485),)),
            ("lineTo", ((702, 485),)),
            ("closePath", ()),
            ("moveTo", ((641, -92),)),
            ("lineTo", ((752, -92),)),
            ("lineTo", ((752, 813),)),
            ("lineTo", ((641, 813),)),
            ("closePath", ()),
        ]

        actual = [
            (op, tuple((otRound(pt[0]), otRound(pt[1])) for pt in args))
            for op, args in actual
        ]

        assert actual == expected, (actual, expected)

        # Test that drawing twice works, we accidentally don't change the component
        pen = DecomposingRecordingPen(glyphset)
        glyph.draw(pen)
        actual = pen.value
        actual = [
            (op, tuple((otRound(pt[0]), otRound(pt[1])) for pt in args))
            for op, args in actual
        ]
        assert actual == expected, (actual, expected)

        pen = RecordingPointPen()
        glyph.drawPoints(pen)
        assert pen.value

    def test_glyphset_varComposite2(self):
        # This test font has axis variations

        font = TTFont(self.getpath("varc-6868.ttf"))
        glyphset = font.getGlyphSet(location={"wght": 600})

        pen = DecomposingRecordingPen(glyphset)
        glyph = glyphset["uni6868"]

        glyph.draw(pen)
        actual = pen.value

        expected = [
            ("moveTo", ((460, 565),)),
            (
                "qCurveTo",
                (
                    (482, 577),
                    (526, 603),
                    (568, 632),
                    (607, 663),
                    (644, 698),
                    (678, 735),
                    (708, 775),
                    (721, 796),
                ),
            ),
            ("lineTo", ((632, 835),)),
            (
                "qCurveTo",
                (
                    (621, 817),
                    (595, 784),
                    (566, 753),
                    (534, 724),
                    (499, 698),
                    (462, 675),
                    (423, 653),
                    (403, 644),
                ),
            ),
            ("closePath", ()),
            ("moveTo", ((616, 765),)),
            ("lineTo", ((590, 682),)),
            ("lineTo", ((830, 682),)),
            ("lineTo", ((833, 682),)),
            ("lineTo", ((828, 693),)),
            (
                "qCurveTo",
                (
                    (817, 671),
                    (775, 620),
                    (709, 571),
                    (615, 525),
                    (492, 490),
                    (413, 480),
                ),
            ),
            ("lineTo", ((454, 386),)),
            (
                "qCurveTo",
                (
                    (544, 403),
                    (687, 455),
                    (798, 519),
                    (877, 590),
                    (926, 655),
                    (937, 684),
                ),
            ),
            ("lineTo", ((937, 765),)),
            ("closePath", ()),
            ("moveTo", ((723, 555),)),
            (
                "qCurveTo",
                (
                    (713, 563),
                    (693, 579),
                    (672, 595),
                    (651, 610),
                    (629, 625),
                    (606, 638),
                    (583, 651),
                    (572, 657),
                ),
            ),
            ("lineTo", ((514, 590),)),
            (
                "qCurveTo",
                (
                    (525, 584),
                    (547, 572),
                    (568, 559),
                    (589, 545),
                    (609, 531),
                    (629, 516),
                    (648, 500),
                    (657, 492),
                ),
            ),
            ("closePath", ()),
            ("moveTo", ((387, 375),)),
            ("lineTo", ((387, 830),)),
            ("lineTo", ((289, 830),)),
            ("lineTo", ((289, 375),)),
            ("closePath", ()),
            ("moveTo", ((96, 383),)),
            (
                "qCurveTo",
                (
                    (116, 390),
                    (156, 408),
                    (194, 427),
                    (231, 449),
                    (268, 472),
                    (302, 497),
                    (335, 525),
                    (351, 539),
                ),
            ),
            ("lineTo", ((307, 610),)),
            (
                "qCurveTo",
                (
                    (291, 597),
                    (257, 572),
                    (221, 549),
                    (185, 528),
                    (147, 509),
                    (108, 492),
                    (69, 476),
                    (48, 469),
                ),
            ),
            ("closePath", ()),
            ("moveTo", ((290, 653),)),
            (
                "qCurveTo",
                (
                    (281, 664),
                    (261, 687),
                    (240, 708),
                    (219, 729),
                    (196, 749),
                    (173, 768),
                    (148, 786),
                    (136, 794),
                ),
            ),
            ("lineTo", ((69, 727),)),
            (
                "qCurveTo",
                (
                    (81, 719),
                    (105, 702),
                    (129, 684),
                    (151, 665),
                    (173, 645),
                    (193, 625),
                    (213, 604),
                    (222, 593),
                ),
            ),
            ("closePath", ()),
            ("moveTo", ((913, -57),)),
            ("lineTo", ((953, 30),)),
            (
                "qCurveTo",
                (
                    (919, 41),
                    (854, 68),
                    (790, 98),
                    (729, 134),
                    (671, 173),
                    (616, 217),
                    (564, 264),
                    (540, 290),
                ),
            ),
            ("lineTo", ((522, 286),)),
            ("qCurveTo", ((511, 267), (498, 235), (493, 213), (492, 206))),
            ("lineTo", ((515, 209),)),
            ("qCurveTo", ((569, 146), (695, 45), (835, -32), (913, -57))),
            ("closePath", ()),
            ("moveTo", ((474, 274),)),
            ("lineTo", ((452, 284),)),
            (
                "qCurveTo",
                (
                    (428, 260),
                    (377, 214),
                    (323, 172),
                    (266, 135),
                    (206, 101),
                    (144, 71),
                    (80, 46),
                    (47, 36),
                ),
            ),
            ("lineTo", ((89, -53),)),
            ("qCurveTo", ((163, -29), (299, 46), (423, 142), (476, 201))),
            ("lineTo", ((498, 196),)),
            ("qCurveTo", ((498, 203), (494, 225), (482, 255), (474, 274))),
            ("closePath", ()),
            ("moveTo", ((450, 250),)),
            ("lineTo", ((550, 250),)),
            ("lineTo", ((550, 379),)),
            ("lineTo", ((450, 379),)),
            ("closePath", ()),
            ("moveTo", ((68, 215),)),
            ("lineTo", ((932, 215),)),
            ("lineTo", ((932, 305),)),
            ("lineTo", ((68, 305),)),
            ("closePath", ()),
            ("moveTo", ((450, -71),)),
            ("lineTo", ((550, -71),)),
            ("lineTo", ((550, -71),)),
            ("lineTo", ((550, 267),)),
            ("lineTo", ((450, 267),)),
            ("lineTo", ((450, -71),)),
            ("closePath", ()),
        ]

        actual = [
            (op, tuple((otRound(pt[0]), otRound(pt[1])) for pt in args))
            for op, args in actual
        ]

        assert actual == expected, (actual, expected)

        pen = RecordingPointPen()
        glyph.drawPoints(pen)
        assert pen.value

    def test_cubic_glyf(self):
        font = TTFont(self.getpath("dot-cubic.ttf"))
        upper_tables(font, tables={"glyf", "loca", "maxp", "hhea", "hmtx"})
        glyphset = font.getGlyphSet()

        expected = [
            ("moveTo", ((76, 181),)),
            ("curveTo", ((103, 181), (125, 158), (125, 131))),
            ("curveTo", ((125, 104), (103, 82), (76, 82))),
            ("curveTo", ((48, 82), (26, 104), (26, 131))),
            ("curveTo", ((26, 158), (48, 181), (76, 181))),
            ("closePath", ()),
        ]

        pen = RecordingPen()
        glyphset["one"].draw(pen)
        assert pen.value == expected

        expectedPoints = [
            ("beginPath", (), {}),
            ("addPoint", ((76, 181), "curve", False, None), {}),
            ("addPoint", ((103, 181), None, False, None), {}),
            ("addPoint", ((125, 158), None, False, None), {}),
            ("addPoint", ((125, 104), None, False, None), {}),
            ("addPoint", ((103, 82), None, False, None), {}),
            ("addPoint", ((76, 82), "curve", False, None), {}),
            ("addPoint", ((48, 82), None, False, None), {}),
            ("addPoint", ((26, 104), None, False, None), {}),
            ("addPoint", ((26, 158), None, False, None), {}),
            ("addPoint", ((48, 181), None, False, None), {}),
            ("endPath", (), {}),
        ]
        pen = RecordingPointPen()
        glyphset["one"].drawPoints(pen)
        assert pen.value == expectedPoints

        pen = RecordingPen()
        glyphset["two"].draw(pen)
        assert pen.value == expected

        expectedPoints = [
            ("beginPath", (), {}),
            ("addPoint", ((26, 158), None, False, None), {}),
            ("addPoint", ((48, 181), None, False, None), {}),
            ("addPoint", ((76, 181), "curve", False, None), {}),
            ("addPoint", ((103, 181), None, False, None), {}),
            ("addPoint", ((125, 158), None, False, None), {}),
            ("addPoint", ((125, 104), None, False, None), {}),
            ("addPoint", ((103, 82), None, False, None), {}),
            ("addPoint", ((76, 82), "curve", False, None), {}),
            ("addPoint", ((48, 82), None, False, None), {}),
            ("addPoint", ((26, 104), None, False, None), {}),
            ("endPath", (), {}),
        ]
        pen = RecordingPointPen()
        glyphset["two"].drawPoints(pen)
        assert pen.value == expectedPoints

        pen = RecordingPen()
        glyphset["three"].draw(pen)
        assert pen.value == expected

        expectedPoints = [
            ("beginPath", (), {}),
            ("addPoint", ((48, 82), None, False, None), {}),
            ("addPoint", ((26, 104), None, False, None), {}),
            ("addPoint", ((26, 158), None, False, None), {}),
            ("addPoint", ((48, 181), None, False, None), {}),
            ("addPoint", ((76, 181), "curve", False, None), {}),
            ("addPoint", ((103, 181), None, False, None), {}),
            ("addPoint", ((125, 158), None, False, None), {}),
            ("addPoint", ((125, 104), None, False, None), {}),
            ("addPoint", ((103, 82), None, False, None), {}),
            ("addPoint", ((76, 82), "curve", False, None), {}),
            ("endPath", (), {}),
        ]
        pen = RecordingPointPen()
        glyphset["three"].drawPoints(pen)
        assert pen.value == expectedPoints

        pen = RecordingPen()
        glyphset["four"].draw(pen)
        assert pen.value == [
            ("moveTo", ((75.5, 181),)),
            ("curveTo", ((103, 181), (125, 158), (125, 131))),
            ("curveTo", ((125, 104), (103, 82), (75.5, 82))),
            ("curveTo", ((48, 82), (26, 104), (26, 131))),
            ("curveTo", ((26, 158), (48, 181), (75.5, 181))),
            ("closePath", ()),
        ]

        # The point protocol cannot distinguish these from quadratic controls.
        # https://github.com/fonttools/fonttools/issues/3191
        pen = RecordingPointPen()
        with pytest.raises(NotImplementedError, match="All-off-curve cubic"):
            glyphset["four"].drawPoints(pen)
        assert pen.value == []

    @pytest.mark.parametrize("location", [{}, {"wght": 800}])
    @pytest.mark.parametrize("from_xml", [False, True])
    @pytest.mark.parametrize(
        "pen_type, draw", [(RecordingPen, "draw"), (RecordingPointPen, "drawPoints")]
    )
    def test_varc_in_memory_component_conditions(
        self, location, from_xml, pen_type, draw
    ):
        from fontTools.ttLib.tables.otTables import VarComponentFlags

        font = TTFont(self.getpath("varc-ac01-conditional.ttf"))
        expected = pen_type()
        getattr(font.getGlyphSet(location=location)["uniAC01"], draw)(expected)

        if from_xml:
            xml = StringIO()
            font.saveXML(xml)
            xml.seek(0)
            font = TTFont()
            font.importXML(xml)
        else:
            # Constructors and XML import need not set derived binary flags.
            for glyph in font["VARC"].table.VarCompositeGlyphs.VarCompositeGlyph:
                for component in glyph.components:
                    component.flags &= ~VarComponentFlags.HAVE_CONDITION

        actual = pen_type()
        getattr(font.getGlyphSet(location=location)["uniAC01"], draw)(actual)
        assert actual.value == expected.value

        stream = BytesIO()
        font.save(stream)
        font = TTFont(BytesIO(stream.getvalue()))
        actual = pen_type()
        getattr(font.getGlyphSet(location=location)["uniAC01"], draw)(actual)
        assert actual.value == expected.value

    @pytest.mark.parametrize("location", [{}, {"wght": 800}])
    @pytest.mark.parametrize("roundtrip", [False, True])
    def test_varc_remove_component_condition(self, location, roundtrip):
        font = TTFont(self.getpath("varc-ac01-conditional.ttf"))
        removed = 0
        for glyph in font["VARC"].table.VarCompositeGlyphs.VarCompositeGlyph:
            for component in glyph.components:
                if component.conditionIndex is not None:
                    component.conditionIndex = None
                    removed += 1
        assert removed == 1

        if roundtrip:
            stream = BytesIO()
            font.save(stream)
            font = TTFont(BytesIO(stream.getvalue()))

        pen = RecordingPen()
        font.getGlyphSet(location=location)["uniAC01"].draw(pen)
        assert len(pen.value) == 3

    def test_glyf_width_without_hvar(self):
        # #3964: for a glyf-based variable font without an HVAR table, the
        # advance width at a non-default location used to be reported as the
        # stale default from hmtx until the glyph was drawn. ``width`` is
        # now a lazy property on _TTGlyphGlyf that computes the right value
        # from the gvar phantom points on first access when there is no HVAR
        # to interpolate from.
        from fontTools.pens.basePen import NullPen

        font = TTFont()
        font.importXML(self.getpath("I-512upem.ttx"))

        # With HVAR, the width is populated at construction time.
        glyph = font.getGlyphSet(location={"wght": 1000})["I"]
        assert glyph.width == 170

        # Default location is the hmtx value regardless of HVAR.
        glyph = font.getGlyphSet()["I"]
        assert glyph.width == 136

        del font["HVAR"]

        # No HVAR + default location: hmtx value is correct.
        glyph = font.getGlyphSet()["I"]
        assert glyph.width == 136

        # No HVAR + non-default: the lazy property returns the correct
        # phantom-point-derived width on first read, without the caller
        # having to draw first.
        glyph = font.getGlyphSet(location={"wght": 1000})["I"]
        assert glyph.width == 170

        # An explicit default-location dict ({"wght": 400} normalizes to
        # {"wght": 0.0}) is still the hmtx value, not an unknown.
        glyph = font.getGlyphSet(location={"wght": 400})["I"]
        assert glyph.width == 136

        # No HVAR + non-default + no gvar entry: ``.notdef`` doesn't vary,
        # so the fallback branch returns the hmtx advance directly without
        # going through the phantom-point computation.
        glyph = font.getGlyphSet(location={"wght": 1000})[".notdef"]
        assert glyph.width == 227

        # draw() still populates and returns consistent widths.
        glyph = font.getGlyphSet(location={"wght": 1000})["I"]
        glyph.draw(NullPen())
        assert glyph.width == 170

        # drawPoints() goes through draw() and does the same.
        glyph = font.getGlyphSet(location={"wght": 1000})["I"]
        glyph.drawPoints(RecordingPointPen())
        assert glyph.width == 170

    def test_varc_gvar_axes_without_fvar(self, tmp_path):
        font = TTFont(self.getpath("varc-static-gvar.ttf"))
        assert "fvar" not in font

        expected = [
            ("moveTo", ((50, 0),)),
            ("lineTo", ((450, 0),)),
            ("lineTo", ((250, 500),)),
            ("closePath", ()),
        ]

        def check_outline(font):
            pen = RecordingPen()
            font.getGlyphSet()["a"].draw(pen)
            assert pen.value == expected

        check_outline(font)

        # The hidden numeric axes also survive binary round-tripping.
        output = tmp_path / "varc-static-gvar.ttf"
        font.save(output)
        check_outline(TTFont(output))

        xml = StringIO()
        font.saveXML(xml)
        xml.seek(0)
        roundtripped = TTFont()
        roundtripped.importXML(xml)
        data = BytesIO()
        roundtripped.save(data)
        data.seek(0)
        check_outline(TTFont(data))
