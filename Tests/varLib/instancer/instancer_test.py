from fontTools.misc.fixedTools import floatToFixedToFloat
from fontTools.misc.roundTools import noRound, otRound
from fontTools.misc.testTools import stripVariableItemsFromTTX
from fontTools.misc.textTools import Tag
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.fontBuilder import FontBuilder
from fontTools import ttLib
from fontTools import designspaceLib
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib.tables import _f_v_a_r, _g_l_y_f
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools import varLib
from fontTools.varLib import instancer
from fontTools.varLib.mvar import MVAR_ENTRIES
from fontTools.varLib import builder
from fontTools.varLib import featureVars
from fontTools.varLib import models
from fontTools.varLib import varStore
import collections
import itertools
from copy import deepcopy
from io import BytesIO, StringIO
import logging
import os
import re
from types import SimpleNamespace
import pytest

# see Tests/varLib/instancer/conftest.py for "varfont" fixture definition

TESTDATA = os.path.join(os.path.dirname(__file__), "data")
TTLIB_TABLES_DATA = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "ttLib", "tables", "data")
)
AVAR2_SUBSET_PATH = os.path.join(TTLIB_TABLES_DATA, "Amstelvar-avar2.subset.ttf")
AVAR2_FULL_INSTANCE_LOCATION = {
    "GRAD": 0,
    "XTRA": 562,
    "XOPQ": 176,
    "YOPQ": 124,
    "YTLC": 500,
    "YTUC": 750,
    "YTAS": 767,
    "YTDE": -240,
    "YTFI": 760,
    "wght": 650,
    "wdth": 90,
    "opsz": 32,
}


@pytest.fixture(params=[True, False], ids=["optimize", "no-optimize"])
def optimize(request):
    return request.param


@pytest.fixture
def fvarAxes():
    wght = _f_v_a_r.Axis()
    wght.axisTag = Tag("wght")
    wght.minValue = 100
    wght.defaultValue = 400
    wght.maxValue = 900
    wdth = _f_v_a_r.Axis()
    wdth.axisTag = Tag("wdth")
    wdth.minValue = 70
    wdth.defaultValue = 100
    wdth.maxValue = 100
    return [wght, wdth]


def _get_coordinates(varfont, glyphname):
    # converts GlyphCoordinates to a list of (x, y) tuples, so that pytest's
    # assert will give us a nicer diff
    return list(
        varfont["glyf"]._getCoordinatesAndControls(
            glyphname,
            varfont["hmtx"].metrics,
            varfont["vmtx"].metrics,
            # the tests expect float coordinates
            round=noRound,
        )[0]
    )


class InstantiateCFF2Test(object):
    @pytest.mark.parametrize(
        "location, expected",
        [
            (
                {},
                [
                    44,
                    256,
                    6,
                    -29,
                    2,
                    "blend",
                    "rmoveto",
                    239,
                    35,
                    -239,
                    44,
                    90,
                    -44,
                    3,
                    "blend",
                    "hlineto",
                ],
            ),
            ({"wght": 0}, [44, 256, "rmoveto", 239, 35, -239, "hlineto"]),
            ({"wght": 0.5}, [47, 242, "rmoveto", 261, 80, -261, "hlineto"]),
            ({"wght": 1}, [50, 227, "rmoveto", 283, 125, -283, "hlineto"]),
        ],
    )
    def test_pin_and_drop_axis(self, varfont, location, expected):

        varfont = ttLib.TTFont()
        varfont.importXML(os.path.join(TESTDATA, "CFF2Instancer-VF-1.ttx"))

        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateCFF2(varfont, location)
        instancer.instantiateHVAR(varfont, location)

        program = varfont["CFF2"].cff.topDictIndex[0].CharStrings.values()[1].program
        assert program == expected

    def test_no_varstore(self, varfont):
        varfont = ttLib.TTFont()
        varfont.importXML(os.path.join(TESTDATA, "CFF2Instancer-VF-1.ttx"))

        # Fully instancing empties the VarStore and removes it from the table.
        instancer.instantiateCFF2(varfont, instancer.NormalizedAxisLimits({"wght": 0}))
        assert not hasattr(varfont["CFF2"].cff.topDictIndex[0], "VarStore")

        # A CFF2 table without a VariationStore must survive instancing.
        # https://github.com/fonttools/fonttools/issues/4130
        instancer.instantiateCFF2(varfont, instancer.NormalizedAxisLimits({"wght": 0}))

    def test_private_dict_vsindex(self):
        # https://github.com/fonttools/fonttools/issues/4129
        from fontTools.cffLib import FontDict, PrivateDict
        from fontTools.varLib.varStore import VarStoreInstancer

        varfont = ttLib.TTFont()
        varfont.importXML(os.path.join(TESTDATA, "CFF2Instancer-VF-2.ttx"))
        topDict = varfont["CFF2"].cff.topDictIndex[0]

        # Add a Private dict with a non-zero vsindex and blended values;
        # its blends reference VarData 1, not VarData 0.
        fontDict = FontDict()
        fontDict.setCFF2(True)
        private = PrivateDict()
        private.vstore = topDict.VarStore
        private.vsindex = 1
        private.BlueValues = [[-12, 10, 20, 40], [0, 5, -5, 15]]
        fontDict.Private = private
        topDict.FDArray.append(fontDict)

        pinned = {"wght": 1.0, "wdth": 1.0}
        vsi = VarStoreInstancer(
            topDict.VarStore.otVarStore, varfont["fvar"].axes, pinned
        )
        expected = []
        delta = 0
        for value in private.BlueValues:
            # Defaults are absolute; the encoded region deltas are relative.
            delta += vsi.interpolateFromDeltas(1, value[1:])
            expected.append(value[0] + round(delta))

        instancer.instantiateCFF2(varfont, instancer.NormalizedAxisLimits(pinned))

        assert private.BlueValues == expected
        # The store emptied; the dict's vsindex must be gone with it.
        assert not hasattr(private, "vsindex")

    def test_charstring_inherits_private_dict_vsindex(self):
        from fontTools.cffLib.specializer import commandsToProgram, programToCommands

        varfont = ttLib.TTFont()
        varfont.importXML(os.path.join(TESTDATA, "CFF2Instancer-VF-2.ttx"))
        topDict = varfont["CFF2"].cff.topDictIndex[0]
        charString = topDict.CharStrings["A"]
        charString.decompile()

        # VarData 1 has three regions, unlike VarData 0, and is selected by the
        # Private DICT without an explicit vsindex operator in the charstring.
        charString.private.vsindex = 1
        charString.program = commandsToProgram([("rmoveto", [50, [100, 1, 2, 3, 1]])])

        instancer.instantiateCFF2(varfont, instancer.NormalizedAxisLimits({}))

        commands = programToCommands(
            charString.program,
            getNumRegions=charString.private.getNumRegions,
            vsIndex=charString.private.vsindex,
        )
        assert commands == [("rmoveto", [50, [100, 1, 2, 3, 1]])]

    def test_instance_of_saved_font(self):
        # Saving before instancing used to leave a compiled VarStore behind
        # that the second save then wrote out in place of the pruned one.
        varfont = ttLib.TTFont()
        varfont.importXML(os.path.join(TESTDATA, "CFF2Instancer-VF-2.ttx"))
        varfont.save(BytesIO())

        instancer.instantiateVariableFont(varfont, {"wdth": 100}, inplace=True)

        s = BytesIO()
        varfont.save(s)
        s.seek(0)
        instance = ttLib.TTFont(s)

        topDict = instance["CFF2"].cff.topDictIndex[0]
        regionList = topDict.VarStore.otVarStore.VarRegionList
        assert regionList.RegionAxisCount == len(instance["fvar"].axes) == 1

        pen = RecordingPen()
        instance.getGlyphSet()["A"].draw(pen)
        assert pen.value

    @pytest.mark.parametrize(
        "source_ttx, expected_ttx",
        [
            ("CFF2Instancer-VF-1.ttx", "CFF2Instancer-VF-1-instance-400.ttx"),
            ("CFF2Instancer-VF-2.ttx", "CFF2Instancer-VF-2-instance-400.ttx"),
            ("CFF2Instancer-VF-3.ttx", "CFF2Instancer-VF-3-instance-400.ttx"),
        ],
    )
    def test_full_instance(self, varfont, source_ttx, expected_ttx):
        varfont = ttLib.TTFont()
        varfont.importXML(os.path.join(TESTDATA, source_ttx))
        s = BytesIO()
        varfont.save(s)
        s.seek(0)
        varfont = ttLib.TTFont(s)

        instance = instancer.instantiateVariableFont(varfont, {"wght": 400})
        s = BytesIO()
        instance.save(s)
        s.seek(0)
        instance = ttLib.TTFont(s)

        s = StringIO()
        instance.saveXML(s)
        actual = stripVariableItemsFromTTX(s.getvalue())

        expected = ttLib.TTFont()
        expected.importXML(os.path.join(TESTDATA, "test_results", expected_ttx))
        s = BytesIO()
        expected.save(s)
        s.seek(0)
        expected = ttLib.TTFont(s)
        s = StringIO()
        expected.saveXML(s)
        expected = stripVariableItemsFromTTX(s.getvalue())

        assert actual == expected


class InstantiateGvarTest(object):
    @pytest.mark.parametrize("glyph_name", ["hyphen"])
    @pytest.mark.parametrize(
        "location, expected",
        [
            pytest.param(
                {"wdth": -1.0},
                {
                    "hyphen": [
                        (27, 229),
                        (27, 310),
                        (247, 310),
                        (247, 229),
                        (0, 0),
                        (274, 0),
                        (0, 536),
                        (0, 0),
                    ]
                },
                id="wdth=-1.0",
            ),
            pytest.param(
                {"wdth": -0.5},
                {
                    "hyphen": [
                        (33.5, 229),
                        (33.5, 308.5),
                        (264.5, 308.5),
                        (264.5, 229),
                        (0, 0),
                        (298, 0),
                        (0, 536),
                        (0, 0),
                    ]
                },
                id="wdth=-0.5",
            ),
            # an axis pinned at the default normalized location (0.0) means
            # the default glyf outline stays the same
            pytest.param(
                {"wdth": 0.0},
                {
                    "hyphen": [
                        (40, 229),
                        (40, 307),
                        (282, 307),
                        (282, 229),
                        (0, 0),
                        (322, 0),
                        (0, 536),
                        (0, 0),
                    ]
                },
                id="wdth=0.0",
            ),
        ],
    )
    def test_pin_and_drop_axis(self, varfont, glyph_name, location, expected, optimize):
        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateGvar(varfont, location, optimize=optimize)

        assert _get_coordinates(varfont, glyph_name) == expected[glyph_name]

        # check that the pinned axis has been dropped from gvar
        assert not any(
            "wdth" in t.axes
            for tuples in varfont["gvar"].variations.values()
            for t in tuples
        )

    def test_full_instance(self, varfont, optimize):
        location = instancer.NormalizedAxisLimits(wght=0.0, wdth=-0.5)

        instancer.instantiateGvar(varfont, location, optimize=optimize)

        assert _get_coordinates(varfont, "hyphen") == [
            (33.5, 229),
            (33.5, 308.5),
            (264.5, 308.5),
            (264.5, 229),
            (0, 0),
            (298, 0),
            (0, 536),
            (0, 0),
        ]

        assert "gvar" not in varfont

    @pytest.mark.parametrize("location", [400, 600, 700, 900, (400, 700, 900)])
    def test_nested_composite_bounds_roundtrip(self, varfont, location):
        glyf = varfont["glyf"]
        pen = TTGlyphPen(glyf)
        pen.addComponent("minus", (1.5, 0, 0, 1.5, 0, 0))
        glyf["nested"] = pen.glyph()
        varfont["hmtx"].metrics["nested"] = (500, 0)
        varfont["vmtx"].metrics["nested"] = (1000, 0)
        varfont["HVAR"].table.AdvWidthMap.mapping["nested"] = 0xFFFFFFFF
        varfont["gvar"].variations["minus"] = [
            TupleVariation({"wght": (0, 1, 1)}, [(1, -1)] + [(0, 0)] * 4)
        ]

        instance = instancer.instantiateVariableFont(
            varfont, {"wght": location, "wdth": 100}
        )
        output = BytesIO()
        instance.save(output)
        output.seek(0)
        saved = ttLib.TTFont(output)
        glyph = saved["glyf"]["nested"]
        stored_bounds = glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax
        component = saved["glyf"]["minus"].components[0]
        points = [
            (1.5 * (x + component.x), 1.5 * (y + component.y))
            for x, y in saved["glyf"]["hyphen"].coordinates
        ]
        xs, ys = zip(*points)
        assert stored_bounds == tuple(
            otRound(value) for value in (min(xs), min(ys), max(xs), max(ys))
        )
        glyph.recalcBounds(saved["glyf"])
        assert stored_bounds == (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax)

    def test_composite_glyph_not_in_gvar(self, varfont):
        """The 'minus' glyph is a composite glyph, which references 'hyphen' as a
        component, but has no tuple variations in gvar table, so the component offset
        and the phantom points do not change; however the sidebearings and bounding box
        do change as a result of the parent glyph 'hyphen' changing.
        """
        hmtx = varfont["hmtx"]
        vmtx = varfont["vmtx"]

        hyphenCoords = _get_coordinates(varfont, "hyphen")
        assert hyphenCoords == [
            (40, 229),
            (40, 307),
            (282, 307),
            (282, 229),
            (0, 0),
            (322, 0),
            (0, 536),
            (0, 0),
        ]
        assert hmtx["hyphen"] == (322, 40)
        assert vmtx["hyphen"] == (536, 229)

        minusCoords = _get_coordinates(varfont, "minus")
        assert minusCoords == [(0, 0), (0, 0), (422, 0), (0, 536), (0, 0)]
        assert hmtx["minus"] == (422, 40)
        assert vmtx["minus"] == (536, 229)

        location = instancer.NormalizedAxisLimits(wght=-1.0, wdth=-1.0)

        instancer.instantiateGvar(varfont, location)

        # check 'hyphen' coordinates changed
        assert _get_coordinates(varfont, "hyphen") == [
            (26, 259),
            (26, 286),
            (237, 286),
            (237, 259),
            (0, 0),
            (263, 0),
            (0, 536),
            (0, 0),
        ]
        # check 'minus' coordinates (i.e. component offset and phantom points)
        # did _not_ change
        assert _get_coordinates(varfont, "minus") == minusCoords

        assert hmtx["hyphen"] == (263, 26)
        assert vmtx["hyphen"] == (536, 250)

        assert hmtx["minus"] == (422, 26)  # 'minus' left sidebearing changed
        assert vmtx["minus"] == (536, 250)  # 'minus' top sidebearing too


class InstantiateCvarTest(object):
    @pytest.mark.parametrize(
        "location, expected",
        [
            pytest.param({"wght": -1.0}, [500, -400, 150, 250], id="wght=-1.0"),
            pytest.param({"wdth": -1.0}, [500, -400, 180, 200], id="wdth=-1.0"),
            pytest.param({"wght": -0.5}, [500, -400, 165, 250], id="wght=-0.5"),
            pytest.param({"wdth": -0.3}, [500, -400, 180, 235], id="wdth=-0.3"),
        ],
    )
    def test_pin_and_drop_axis(self, varfont, location, expected):
        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateCvar(varfont, location)

        assert list(varfont["cvt "].values) == expected

        # check that the pinned axis has been dropped from cvar
        pinned_axes = location.keys()
        assert not any(
            axis in t.axes for t in varfont["cvar"].variations for axis in pinned_axes
        )

    def test_full_instance(self, varfont):
        location = instancer.NormalizedAxisLimits(wght=-0.5, wdth=-0.5)

        instancer.instantiateCvar(varfont, location)

        assert list(varfont["cvt "].values) == [500, -400, 165, 225]

        assert "cvar" not in varfont


class InstantiateMVARTest(object):
    @pytest.mark.parametrize("fullyInstanced", [False, True])
    @pytest.mark.parametrize("uppercase", [False, True])
    @pytest.mark.parametrize(
        "valueTag",
        ["hcrs", "hcrn", "hcof", "vasc", "vdsc", "vlgp", "vcrs", "vcrn", "vcof"],
    )
    def test_metric_header_companions(
        self, varfont, valueTag, uppercase, fullyInstanced
    ):
        from fontTools.ttLib.beyond64k import upper_tables
        from fontTools.varLib.mvar import getMVARTableTag

        if uppercase:
            upper_tables(varfont)
        tableTag, itemName = MVAR_ENTRIES[valueTag]
        tableTag = getMVARTableTag(varfont, tableTag)
        original = getattr(varfont[tableTag], itemName)
        mvar = varfont["MVAR"].table
        record = otTables.MetricsValueRecord()
        record.ValueTag = valueTag
        record.VarIdx = 0
        mvar.ValueRecord = [record]
        mvar.ValueRecordCount = 1
        mvar.VarStore = builder.buildVarStore(
            builder.buildVarRegionList([{"wght": (0, 1, 1)}], ["wght", "wdth"]),
            [builder.buildVarData([0], [[20]])],
        )
        location = {"wght": 900}
        if fullyInstanced:
            location["wdth"] = 100
        instance = instancer.instantiateVariableFont(varfont, location)
        assert getattr(instance[tableTag], itemName) == original + 20
        output = BytesIO()
        instance.save(output)
        output.seek(0)
        assert getattr(ttLib.TTFont(output)[tableTag], itemName) == original + 20

    @pytest.mark.parametrize(
        "location, expected",
        [
            pytest.param(
                {"wght": 1.0},
                {"strs": 100, "undo": -200, "unds": 150, "xhgt": 530},
                id="wght=1.0",
            ),
            pytest.param(
                {"wght": 0.5},
                {"strs": 75, "undo": -150, "unds": 100, "xhgt": 515},
                id="wght=0.5",
            ),
            pytest.param(
                {"wght": 0.0},
                {"strs": 50, "undo": -100, "unds": 50, "xhgt": 500},
                id="wght=0.0",
            ),
            pytest.param(
                {"wdth": -1.0},
                {"strs": 20, "undo": -100, "unds": 50, "xhgt": 500},
                id="wdth=-1.0",
            ),
            pytest.param(
                {"wdth": -0.5},
                {"strs": 35, "undo": -100, "unds": 50, "xhgt": 500},
                id="wdth=-0.5",
            ),
            pytest.param(
                {"wdth": 0.0},
                {"strs": 50, "undo": -100, "unds": 50, "xhgt": 500},
                id="wdth=0.0",
            ),
        ],
    )
    def test_pin_and_drop_axis(self, varfont, location, expected):
        mvar = varfont["MVAR"].table
        # initially we have two VarData: the first contains deltas associated with 3
        # regions: 1 with only wght, 1 with only wdth, and 1 with both wght and wdth
        assert len(mvar.VarStore.VarData) == 2
        assert mvar.VarStore.VarRegionList.RegionCount == 3
        assert mvar.VarStore.VarData[0].VarRegionCount == 3
        assert all(len(item) == 3 for item in mvar.VarStore.VarData[0].Item)
        # The second VarData has deltas associated only with 1 region (wght only).
        assert mvar.VarStore.VarData[1].VarRegionCount == 1
        assert all(len(item) == 1 for item in mvar.VarStore.VarData[1].Item)

        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateMVAR(varfont, location)

        for mvar_tag, expected_value in expected.items():
            table_tag, item_name = MVAR_ENTRIES[mvar_tag]
            assert getattr(varfont[table_tag], item_name) == expected_value

        # check that regions and accompanying deltas have been dropped
        num_regions_left = len(mvar.VarStore.VarRegionList.Region)
        assert num_regions_left < 3
        assert mvar.VarStore.VarRegionList.RegionCount == num_regions_left
        assert mvar.VarStore.VarData[0].VarRegionCount == num_regions_left
        # VarData subtables have been merged
        assert len(mvar.VarStore.VarData) == 1

    @pytest.mark.parametrize(
        "location, expected, sync_vmetrics",
        [
            pytest.param(
                {"wght": 1.0, "wdth": 0.0},
                {"strs": 100, "undo": -200, "unds": 150, "hasc": 1100},
                True,
                id="wght=1.0,wdth=0.0",
            ),
            pytest.param(
                {"wght": 0.0, "wdth": -1.0},
                {"strs": 20, "undo": -100, "unds": 50, "hasc": 1000},
                True,
                id="wght=0.0,wdth=-1.0",
            ),
            pytest.param(
                {"wght": 0.5, "wdth": -0.5},
                {"strs": 55, "undo": -145, "unds": 95, "hasc": 1050},
                True,
                id="wght=0.5,wdth=-0.5",
            ),
            pytest.param(
                {"wght": 1.0, "wdth": -1.0},
                {"strs": 50, "undo": -180, "unds": 130, "hasc": 1100},
                True,
                id="wght=0.5,wdth=-0.5",
            ),
            pytest.param(
                {"wght": 1.0, "wdth": 0.0},
                {"strs": 100, "undo": -200, "unds": 150, "hasc": 1100},
                False,
                id="wght=1.0,wdth=0.0,no_sync_vmetrics",
            ),
        ],
    )
    def test_full_instance(self, varfont, location, sync_vmetrics, expected):
        location = instancer.NormalizedAxisLimits(location)

        # check vertical metrics are in sync before...
        if sync_vmetrics:
            assert varfont["OS/2"].sTypoAscender == varfont["hhea"].ascender
            assert varfont["OS/2"].sTypoDescender == varfont["hhea"].descender
            assert varfont["OS/2"].sTypoLineGap == varfont["hhea"].lineGap
        else:
            # force them not to be in sync
            varfont["OS/2"].sTypoDescender -= 100
            varfont["OS/2"].sTypoLineGap += 200

        instancer.instantiateMVAR(varfont, location)

        for mvar_tag, expected_value in expected.items():
            table_tag, item_name = MVAR_ENTRIES[mvar_tag]
            assert getattr(varfont[table_tag], item_name) == expected_value

        # ... as well as after instancing, but only if they were already
        # https://github.com/fonttools/fonttools/issues/3297
        if sync_vmetrics:
            assert varfont["OS/2"].sTypoAscender == varfont["hhea"].ascender
            assert varfont["OS/2"].sTypoDescender == varfont["hhea"].descender
            assert varfont["OS/2"].sTypoLineGap == varfont["hhea"].lineGap
        else:
            assert varfont["OS/2"].sTypoDescender != varfont["hhea"].descender
            assert varfont["OS/2"].sTypoLineGap != varfont["hhea"].lineGap

        assert "MVAR" not in varfont


class InstantiateHVARTest(object):
    # the 'expectedDeltas' below refer to the VarData item deltas for the "hyphen"
    # glyph in the PartialInstancerTest-VF.ttx test font, that are left after
    # partial instancing
    @pytest.mark.parametrize(
        "location, expectedRegions, expectedDeltas",
        [
            ({"wght": -1.0}, [{"wdth": (-1.0, -1.0, 0)}], [-59]),
            ({"wght": 0}, [{"wdth": (-1.0, -1.0, 0)}], [-48]),
            ({"wght": 1.0}, [{"wdth": (-1.0, -1.0, 0)}], [7]),
            (
                {"wdth": -1.0},
                [
                    {"wght": (-1.0, -1.0, 0.0)},
                    {"wght": (0.0, 0.6099854, 1.0)},
                    {"wght": (0.6099854, 1.0, 1.0)},
                ],
                [-11, 31, 51],
            ),
            ({"wdth": 0}, [{"wght": (0.6099854, 1.0, 1.0)}], [-4]),
        ],
    )
    def test_partial_instance(self, varfont, location, expectedRegions, expectedDeltas):
        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateHVAR(varfont, location)

        assert "HVAR" in varfont
        hvar = varfont["HVAR"].table
        varStore = hvar.VarStore

        regions = varStore.VarRegionList.Region
        fvarAxes = [a for a in varfont["fvar"].axes if a.axisTag not in location]
        regionDicts = [reg.get_support(fvarAxes) for reg in regions]
        assert len(regionDicts) == len(expectedRegions)
        for region, expectedRegion in zip(regionDicts, expectedRegions):
            assert region.keys() == expectedRegion.keys()
            for axisTag, support in region.items():
                assert support == pytest.approx(expectedRegion[axisTag])

        assert len(varStore.VarData) == 1
        assert varStore.VarData[0].ItemCount == 2

        assert hvar.AdvWidthMap is not None
        advWithMap = hvar.AdvWidthMap.mapping

        assert advWithMap[".notdef"] == advWithMap["space"]
        varIdx = advWithMap[".notdef"]
        # these glyphs have no metrics variations in the test font
        assert varStore.VarData[varIdx >> 16].Item[varIdx & 0xFFFF] == (
            [0] * varStore.VarData[0].VarRegionCount
        )

        varIdx = advWithMap["hyphen"]
        assert varStore.VarData[varIdx >> 16].Item[varIdx & 0xFFFF] == expectedDeltas

    def test_full_instance(self, varfont):
        location = instancer.NormalizedAxisLimits(wght=0, wdth=0)

        instancer.instantiateHVAR(varfont, location)

        assert "HVAR" not in varfont

    def test_partial_instance_keep_empty_table(self, varfont):
        # Append an additional dummy axis to fvar, for which the current HVAR table
        # in our test 'varfont' contains no variation data.
        # Instancing the other two wght and wdth axes should leave HVAR table empty,
        # to signal there are variations to the glyph's advance widths.
        fvar = varfont["fvar"]
        axis = _f_v_a_r.Axis()
        axis.axisTag = "TEST"
        fvar.axes.append(axis)

        location = instancer.NormalizedAxisLimits(wght=0, wdth=0)

        instancer.instantiateHVAR(varfont, location)

        assert "HVAR" in varfont

        varStore = varfont["HVAR"].table.VarStore

        assert varStore.VarRegionList.RegionCount == 0
        assert not varStore.VarRegionList.Region
        assert varStore.VarRegionList.RegionAxisCount == 1


class InstantiateVVARTest:
    @pytest.fixture(params=[1, 2], ids=["VORG-v1", "VORG-v2"])
    def varfont(self, fvarAxes, request):
        font = ttLib.TTFont()
        glyphOrder = [".notdef", "a", "b", "c"]
        font.setGlyphOrder(glyphOrder)
        font["fvar"] = ttLib.newTable("fvar")
        font["fvar"].axes = deepcopy(fvarAxes)
        font["vmtx"] = ttLib.newTable("vmtx")
        font["vmtx"].metrics = {glyph: (1000, 100) for glyph in glyphOrder}
        font["VORG"] = ttLib.newTable("VORG")
        font["VORG"].majorVersion = request.param
        font["VORG"].minorVersion = 0
        font["VORG"].defaultVertOriginY = 800
        font["VORG"].VOriginRecords = {"b": 850}

        vvar = otTables.VVAR()
        vvar.Version = 0x10000
        vvar.VarStore = builder.buildVarStore(
            builder.buildVarRegionList(
                [{"wght": (0, 1, 1)}, {"wdth": (-1, -1, 0)}],
                ["wght", "wdth"],
            ),
            [builder.buildVarData([0, 1], [[0, 0], [10, 0], [100, 30], [-50, 0]])],
        )
        vvar.AdvHeightMap = builder.buildVarIdxMap([0] * 4, glyphOrder)
        vvar.TsbMap = vvar.BsbMap = None
        vvar.VOrgMap = builder.buildVarIdxMap(
            [1, 2, 3, otTables.NO_VARIATION_INDEX], glyphOrder
        )
        font["VVAR"] = ttLib.newTable("VVAR")
        font["VVAR"].table = vvar
        return font

    @pytest.mark.parametrize(
        "limits, expected, remainingLocation, remainingOrigins",
        [
            ({"wght": 1, "wdth": 0}, [810, 900, 800, 800], None, None),
            (
                {"wght": 1},
                [810, 900, 800, 800],
                {"wdth": -1},
                [810, 930, 800, 800],
            ),
            (
                {"wght": (0.5, 0.5, 1), "wdth": 0},
                [805, 850, 825, 800],
                {"wght": 1},
                [810, 900, 800, 800],
            ),
        ],
    )
    def test_vertical_origins(
        self, varfont, limits, expected, remainingLocation, remainingOrigins
    ):
        limits = instancer.NormalizedAxisLimits(limits)
        instancer.instantiateVVAR(varfont, limits)

        glyphOrder = varfont.getGlyphOrder()
        vorg = varfont["VORG"]
        assert [vorg[glyph] for glyph in glyphOrder] == expected
        assert vorg.defaultVertOriginY == 800
        assert all(value != 800 for value in vorg.VOriginRecords.values())
        assert varfont["vmtx"].metrics == {glyph: (1000, 100) for glyph in glyphOrder}

        reloaded = ttLib.newTable("VORG")
        reloaded.decompile(vorg.compile(varfont), varfont)
        assert [reloaded[glyph] for glyph in glyphOrder] == expected

        if remainingLocation is None:
            assert "VVAR" not in varfont
        else:
            vvar = varfont["VVAR"].table
            remainingAxes = [
                axis
                for axis in varfont["fvar"].axes
                if axis.axisTag not in limits.pinnedLocation()
            ]
            evaluator = varStore.VarStoreInstancer(
                vvar.VarStore, remainingAxes, remainingLocation
            )
            assert [
                vorg[glyph] + evaluator[vvar.VOrgMap.mapping[glyph]]
                for glyph in glyphOrder
            ] == remainingOrigins

    @pytest.mark.parametrize("delta, rounded", [(37, 19), (-37, -18)])
    def test_uniform_origins_and_half_unit_rounding(self, varfont, delta, rounded):
        glyphOrder = varfont.getGlyphOrder()
        varfont["VORG"].VOriginRecords = {}
        vvar = varfont["VVAR"].table
        vvar.VarStore.VarData[0].Item[1] = [delta, 0]
        vvar.VOrgMap = builder.buildVarIdxMap([1] * len(glyphOrder), glyphOrder)
        vvar.AdvHeightMap = builder.buildVarIdxMap([1] * len(glyphOrder), glyphOrder)
        instancer.instantiateVVAR(
            varfont, instancer.NormalizedAxisLimits(wght=0.5, wdth=0)
        )
        vorg = varfont["VORG"]
        assert vorg.defaultVertOriginY == 800 + rounded
        assert vorg.VOriginRecords == {}
        assert [vorg[glyph] for glyph in glyphOrder] == [800 + rounded] * len(
            glyphOrder
        )
        assert varfont["vmtx"].metrics == {
            glyph: (1000 + rounded, 100) for glyph in glyphOrder
        }
        reloaded = ttLib.newTable("VORG")
        reloaded.decompile(vorg.compile(varfont), varfont)
        assert reloaded.defaultVertOriginY == 800 + rounded
        assert reloaded.VOriginRecords == {}

    @pytest.mark.parametrize("delta, rounded", [(37, 19), (-37, -18)])
    def test_hvar_half_unit_rounding(self, varfont, delta, rounded):
        glyphOrder = varfont.getGlyphOrder()
        varfont["hmtx"] = ttLib.newTable("hmtx")
        varfont["hmtx"].metrics = {glyph: (1000, 100) for glyph in glyphOrder}
        hvar = otTables.HVAR()
        hvar.Version = 0x10000
        hvar.VarStore = deepcopy(varfont["VVAR"].table.VarStore)
        hvar.VarStore.VarData[0].Item[1] = [delta, 0]
        hvar.AdvWidthMap = builder.buildVarIdxMap([1] * len(glyphOrder), glyphOrder)
        hvar.LsbMap = hvar.RsbMap = None
        varfont["HVAR"] = ttLib.newTable("HVAR")
        varfont["HVAR"].table = hvar
        instancer.instantiateHVAR(
            varfont, instancer.NormalizedAxisLimits(wght=0.5, wdth=0)
        )
        assert varfont["hmtx"].metrics == {
            glyph: (1000 + rounded, 100) for glyph in glyphOrder
        }

    def test_no_origin_mapping(self, varfont):
        varfont["VVAR"].table.VOrgMap = None
        instancer.instantiateVVAR(
            varfont, instancer.NormalizedAxisLimits(wght=1, wdth=0)
        )
        assert varfont["VORG"].defaultVertOriginY == 800
        assert varfont["VORG"].VOriginRecords == {"b": 850}


class InstantiateItemVariationStoreTest(object):
    def test_VarRegion_get_support(self):
        axisOrder = ["wght", "wdth", "opsz"]
        regionAxes = {"wdth": (-1.0, -1.0, 0.0), "wght": (0.0, 1.0, 1.0)}
        region = builder.buildVarRegion(regionAxes, axisOrder)

        assert len(region.VarRegionAxis) == 3
        assert region.VarRegionAxis[2].PeakCoord == 0

        fvarAxes = [SimpleNamespace(axisTag=axisTag) for axisTag in axisOrder]

        assert region.get_support(fvarAxes) == regionAxes

    @pytest.fixture
    def varStore(self):
        return builder.buildVarStore(
            builder.buildVarRegionList(
                [
                    {"wght": (-1.0, -1.0, 0)},
                    {"wght": (0, 0.5, 1.0)},
                    {"wght": (0.5, 1.0, 1.0)},
                    {"wdth": (-1.0, -1.0, 0)},
                    {"wght": (-1.0, -1.0, 0), "wdth": (-1.0, -1.0, 0)},
                    {"wght": (0, 0.5, 1.0), "wdth": (-1.0, -1.0, 0)},
                    {"wght": (0.5, 1.0, 1.0), "wdth": (-1.0, -1.0, 0)},
                ],
                ["wght", "wdth"],
            ),
            [
                builder.buildVarData([0, 1, 2], [[100, 100, 100], [100, 100, 100]]),
                builder.buildVarData(
                    [3, 4, 5, 6], [[100, 100, 100, 100], [100, 100, 100, 100]]
                ),
            ],
        )

    @pytest.mark.parametrize(
        "location, expected_deltas, num_regions",
        [
            ({"wght": 0}, [[0, 0], [0, 0]], 1),
            ({"wght": 0.25}, [[50, 50], [0, 0]], 1),
            ({"wdth": 0}, [[0, 0], [0, 0]], 3),
            ({"wdth": -0.75}, [[0, 0], [75, 75]], 3),
            ({"wght": 0, "wdth": 0}, [[0, 0], [0, 0]], 0),
            ({"wght": 0.25, "wdth": 0}, [[50, 50], [0, 0]], 0),
            ({"wght": 0, "wdth": -0.75}, [[0, 0], [75, 75]], 0),
        ],
    )
    def test_instantiate_default_deltas(
        self, varStore, fvarAxes, location, expected_deltas, num_regions
    ):
        location = instancer.NormalizedAxisLimits(location)

        defaultDeltas = instancer.instantiateItemVariationStore(
            varStore, fvarAxes, location
        )

        defaultDeltaArray = []
        for varidx, delta in sorted(defaultDeltas.items()):
            if varidx == varStore.NO_VARIATION_INDEX:
                continue
            major, minor = varidx >> 16, varidx & 0xFFFF
            if major == len(defaultDeltaArray):
                defaultDeltaArray.append([])
            assert len(defaultDeltaArray[major]) == minor
            defaultDeltaArray[major].append(delta)

        assert defaultDeltaArray == expected_deltas
        assert varStore.VarRegionList.RegionCount == num_regions


class TupleVarStoreAdapterTest(object):
    def test_instantiate(self):
        regions = [
            {"wght": (-1.0, -1.0, 0)},
            {"wght": (0.0, 1.0, 1.0)},
            {"wdth": (-1.0, -1.0, 0)},
            {"wght": (-1.0, -1.0, 0), "wdth": (-1.0, -1.0, 0)},
            {"wght": (0, 1.0, 1.0), "wdth": (-1.0, -1.0, 0)},
        ]
        axisOrder = ["wght", "wdth"]
        tupleVarData = [
            [
                TupleVariation({"wght": (-1.0, -1.0, 0)}, [10, 70]),
                TupleVariation({"wght": (0.0, 1.0, 1.0)}, [30, 90]),
                TupleVariation(
                    {"wght": (-1.0, -1.0, 0), "wdth": (-1.0, -1.0, 0)}, [-40, -100]
                ),
                TupleVariation(
                    {"wght": (0, 1.0, 1.0), "wdth": (-1.0, -1.0, 0)}, [-60, -120]
                ),
            ],
            [
                TupleVariation({"wdth": (-1.0, -1.0, 0)}, [5, 45]),
                TupleVariation(
                    {"wght": (-1.0, -1.0, 0), "wdth": (-1.0, -1.0, 0)}, [-15, -55]
                ),
                TupleVariation(
                    {"wght": (0, 1.0, 1.0), "wdth": (-1.0, -1.0, 0)}, [-35, -75]
                ),
            ],
        ]
        adapter = instancer._TupleVarStoreAdapter(
            regions, axisOrder, tupleVarData, itemCounts=[2, 2]
        )
        location = instancer.NormalizedAxisLimits(wght=0.5)

        defaultDeltaArray = adapter.instantiate(location)

        assert defaultDeltaArray == [[15, 45], [0, 0]]
        assert adapter.regions == [{"wdth": (-1.0, -1.0, 0)}]
        assert adapter.tupleVarData == [
            [TupleVariation({"wdth": (-1.0, -1.0, 0)}, [-30, -60])],
            [TupleVariation({"wdth": (-1.0, -1.0, 0)}, [-12, 8])],
        ]

    def test_rebuildRegions(self):
        regions = [
            {"wght": (-1.0, -1.0, 0)},
            {"wght": (0.0, 1.0, 1.0)},
            {"wdth": (-1.0, -1.0, 0)},
            {"wght": (-1.0, -1.0, 0), "wdth": (-1.0, -1.0, 0)},
            {"wght": (0, 1.0, 1.0), "wdth": (-1.0, -1.0, 0)},
        ]
        axisOrder = ["wght", "wdth"]
        variations = []
        for region in regions:
            variations.append(TupleVariation(region, [100]))
        tupleVarData = [variations[:3], variations[3:]]
        adapter = instancer._TupleVarStoreAdapter(
            regions, axisOrder, tupleVarData, itemCounts=[1, 1]
        )

        adapter.rebuildRegions()

        assert adapter.regions == regions

        del tupleVarData[0][2]
        tupleVarData[1][0].axes = {"wght": (-1.0, -0.5, 0)}
        tupleVarData[1][1].axes = {"wght": (0, 0.5, 1.0)}

        adapter.rebuildRegions()

        assert adapter.regions == [
            {"wght": (-1.0, -1.0, 0)},
            {"wght": (0.0, 1.0, 1.0)},
            {"wght": (-1.0, -0.5, 0)},
            {"wght": (0, 0.5, 1.0)},
        ]

    def test_roundtrip(self, fvarAxes):
        regions = [
            {"wght": (-1.0, -1.0, 0)},
            {"wght": (0, 0.5, 1.0)},
            {"wght": (0.5, 1.0, 1.0)},
            {"wdth": (-1.0, -1.0, 0)},
            {"wght": (-1.0, -1.0, 0), "wdth": (-1.0, -1.0, 0)},
            {"wght": (0, 0.5, 1.0), "wdth": (-1.0, -1.0, 0)},
            {"wght": (0.5, 1.0, 1.0), "wdth": (-1.0, -1.0, 0)},
        ]
        axisOrder = [axis.axisTag for axis in fvarAxes]

        itemVarStore = builder.buildVarStore(
            builder.buildVarRegionList(regions, axisOrder),
            [
                builder.buildVarData(
                    [0, 1, 2, 4, 5, 6],
                    [[10, -20, 30, -40, 50, -60], [70, -80, 90, -100, 110, -120]],
                ),
                builder.buildVarData(
                    [3, 4, 5, 6], [[5, -15, 25, -35], [45, -55, 65, -75]]
                ),
            ],
        )

        adapter = instancer._TupleVarStoreAdapter.fromItemVarStore(
            itemVarStore, fvarAxes
        )

        assert adapter.tupleVarData == [
            [
                TupleVariation({"wght": (-1.0, -1.0, 0)}, [10, 70]),
                TupleVariation({"wght": (0, 0.5, 1.0)}, [-20, -80]),
                TupleVariation({"wght": (0.5, 1.0, 1.0)}, [30, 90]),
                TupleVariation(
                    {"wght": (-1.0, -1.0, 0), "wdth": (-1.0, -1.0, 0)}, [-40, -100]
                ),
                TupleVariation(
                    {"wght": (0, 0.5, 1.0), "wdth": (-1.0, -1.0, 0)}, [50, 110]
                ),
                TupleVariation(
                    {"wght": (0.5, 1.0, 1.0), "wdth": (-1.0, -1.0, 0)}, [-60, -120]
                ),
            ],
            [
                TupleVariation({"wdth": (-1.0, -1.0, 0)}, [5, 45]),
                TupleVariation(
                    {"wght": (-1.0, -1.0, 0), "wdth": (-1.0, -1.0, 0)}, [-15, -55]
                ),
                TupleVariation(
                    {"wght": (0, 0.5, 1.0), "wdth": (-1.0, -1.0, 0)}, [25, 65]
                ),
                TupleVariation(
                    {"wght": (0.5, 1.0, 1.0), "wdth": (-1.0, -1.0, 0)}, [-35, -75]
                ),
            ],
        ]
        assert adapter.itemCounts == [data.ItemCount for data in itemVarStore.VarData]
        assert adapter.regions == regions
        assert adapter.axisOrder == axisOrder

        itemVarStore2 = adapter.asItemVarStore()

        assert [
            reg.get_support(fvarAxes) for reg in itemVarStore2.VarRegionList.Region
        ] == regions

        assert itemVarStore2.VarDataCount == 2
        assert itemVarStore2.VarData[0].VarRegionIndex == [0, 1, 2, 4, 5, 6]
        assert itemVarStore2.VarData[0].Item == [
            [10, -20, 30, -40, 50, -60],
            [70, -80, 90, -100, 110, -120],
        ]
        assert itemVarStore2.VarData[1].VarRegionIndex == [3, 4, 5, 6]
        assert itemVarStore2.VarData[1].Item == [[5, -15, 25, -35], [45, -55, 65, -75]]


def makeTTFont(glyphOrder, features):
    font = ttLib.TTFont()
    font.setGlyphOrder(glyphOrder)
    addOpenTypeFeaturesFromString(font, features)
    font["name"] = ttLib.newTable("name")
    return font


def _makeDSAxesDict(axes):
    dsAxes = collections.OrderedDict()
    for axisTag, axisValues in axes:
        axis = designspaceLib.AxisDescriptor()
        axis.name = axis.tag = axis.labelNames["en"] = axisTag
        axis.minimum, axis.default, axis.maximum = axisValues
        dsAxes[axis.tag] = axis
    return dsAxes


def makeVariableFont(masters, baseIndex, axes, masterLocations):
    vf = deepcopy(masters[baseIndex])
    dsAxes = _makeDSAxesDict(axes)
    fvar = varLib._add_fvar(vf, dsAxes, instances=())
    axisTags = [axis.axisTag for axis in fvar.axes]
    normalizedLocs = [models.normalizeLocation(m, dict(axes)) for m in masterLocations]
    model = models.VariationModel(normalizedLocs, axisOrder=axisTags)
    varLib._merge_OTL(vf, model, masters, axisTags)
    return vf


def makeParametrizedVF(glyphOrder, features, values, increments):
    # Create a test VF with given glyphs and parametrized OTL features.
    # The VF is built from 9 masters (3 x 3 along wght and wdth), with
    # locations hard-coded and base master at wght=400 and wdth=100.
    # 'values' is a list of initial values that are interpolated in the
    # 'features' string, and incremented for each subsequent master by the
    # given 'increments' (list of 2-tuple) along the two axes.
    assert values and len(values) == len(increments)
    assert all(len(i) == 2 for i in increments)
    masterLocations = [
        {"wght": 100, "wdth": 50},
        {"wght": 100, "wdth": 100},
        {"wght": 100, "wdth": 150},
        {"wght": 400, "wdth": 50},
        {"wght": 400, "wdth": 100},  # base master
        {"wght": 400, "wdth": 150},
        {"wght": 700, "wdth": 50},
        {"wght": 700, "wdth": 100},
        {"wght": 700, "wdth": 150},
    ]
    n = len(values)
    values = list(values)
    masters = []
    for _ in range(3):
        for _ in range(3):
            master = makeTTFont(glyphOrder, features=features % tuple(values))
            masters.append(master)
            for i in range(n):
                values[i] += increments[i][1]
        for i in range(n):
            values[i] += increments[i][0]
    baseIndex = 4
    axes = [("wght", (100, 400, 700)), ("wdth", (50, 100, 150))]
    vf = makeVariableFont(masters, baseIndex, axes, masterLocations)
    return vf


@pytest.fixture
def varfontGDEF():
    glyphOrder = [".notdef", "f", "i", "f_i"]
    features = (
        "feature liga { sub f i by f_i;} liga;"
        "table GDEF { LigatureCaretByPos f_i %d; } GDEF;"
    )
    values = [100]
    increments = [(+30, +10)]
    return makeParametrizedVF(glyphOrder, features, values, increments)


@pytest.fixture
def varfontGPOS():
    glyphOrder = [".notdef", "V", "A"]
    features = "feature kern { pos V A %d; } kern;"
    values = [-80]
    increments = [(-10, -5)]
    return makeParametrizedVF(glyphOrder, features, values, increments)


@pytest.fixture
def varfontGPOS2():
    glyphOrder = [".notdef", "V", "A", "acutecomb"]
    features = (
        "markClass [acutecomb] <anchor 150 -10> @TOP_MARKS;"
        "feature mark {"
        "  pos base A <anchor %d 450> mark @TOP_MARKS;"
        "} mark;"
        "feature kern {"
        "  pos V A %d;"
        "} kern;"
    )
    values = [200, -80]
    increments = [(+30, +10), (-10, -5)]
    return makeParametrizedVF(glyphOrder, features, values, increments)


@pytest.fixture
def varfontBASE():
    # The feature file syntax has no way to express variable baseline
    # coordinates, so the BASE table is built here: a single 'romn' baseline
    # for 'latn' at -120 by default, -100 at wght=1.0 and -110 at wdth=1.0.
    vf = makeParametrizedVF(
        [".notdef", "A"], "feature kern { pos A A %d; } kern;", [-80], [(-10, -5)]
    )
    axisTags = [axis.axisTag for axis in vf["fvar"].axes]
    storeBuilder = varStore.OnlineVarStoreBuilder(axisTags)
    storeBuilder.setModel(
        models.VariationModel([{}, {"wght": 1.0}, {"wdth": 1.0}], axisOrder=axisTags)
    )
    default, varIdx = storeBuilder.storeMasters([-120, -100, -110])

    coord = otTables.BaseCoord()
    coord.Format = 3
    coord.Coordinate = default
    coord.DeviceTable = builder.buildVarDevTable(varIdx)

    baseValues = otTables.BaseValues()
    baseValues.DefaultIndex = 0
    baseValues.BaseCoord = [coord]
    baseValues.BaseCoordCount = 1

    baseScript = otTables.BaseScript()
    baseScript.BaseValues = baseValues
    baseScript.DefaultMinMax = None
    baseScript.BaseLangSysRecord = []
    baseScript.BaseLangSysCount = 0

    scriptRecord = otTables.BaseScriptRecord()
    scriptRecord.BaseScriptTag = "latn"
    scriptRecord.BaseScript = baseScript

    axis = otTables.Axis()
    axis.BaseTagList = otTables.BaseTagList()
    axis.BaseTagList.BaselineTag = ["romn"]
    axis.BaseTagList.BaseTagCount = 1
    axis.BaseScriptList = otTables.BaseScriptList()
    axis.BaseScriptList.BaseScriptRecord = [scriptRecord]
    axis.BaseScriptList.BaseScriptCount = 1

    base = otTables.BASE()
    base.Version = 0x00010001
    base.HorizAxis = axis
    base.VertAxis = None
    base.VarStore = storeBuilder.finish()

    vf["BASE"] = ttLib.newTable("BASE")
    vf["BASE"].table = base
    return vf


def getBaseCoord(varfont):
    axis = varfont["BASE"].table.HorizAxis
    return axis.BaseScriptList.BaseScriptRecord[0].BaseScript.BaseValues.BaseCoord[0]


class InstantiateOTLTest(object):
    @pytest.mark.parametrize("full", [False, True])
    @pytest.mark.parametrize("delta", [1, 3, 7])
    @pytest.mark.parametrize("kind", ["GDEF", "BASE", "GPOS"])
    def test_preserves_ppem_devices(self, request, full, delta, kind):
        from fontTools.otlLib.builder import buildDevice

        vf = request.getfixturevalue("varfont" + kind)
        hint = buildDevice({10: delta})
        if kind == "GDEF":
            record = vf["GDEF"].table.LigCaretList.LigGlyph[0].CaretValue[0]
            record.DeviceTable = hint
            original = record.Coordinate
        elif kind == "BASE":
            record = getBaseCoord(vf)
            record.DeviceTable = hint
            original = record.Coordinate
        else:
            subtable = vf["GPOS"].table.LookupList.Lookup[0].SubTable[0]
            record = subtable.PairSet[0].PairValueRecord[0].Value1
            record.XAdvDevice = hint
            original = record.XAdvance
        limits = {"wght": 1.0}
        if full:
            limits["wdth"] = 0.0
        instancer.instantiateOTL(vf, instancer.NormalizedAxisLimits(limits))
        if kind == "GDEF":
            record = vf["GDEF"].table.LigCaretList.LigGlyph[0].CaretValue[0]
        elif kind == "BASE":
            record = getBaseCoord(vf)
        else:
            subtable = vf["GPOS"].table.LookupList.Lookup[0].SubTable[0]
            record = subtable.PairSet[0].PairValueRecord[0].Value1
        if kind in ("GDEF", "BASE"):
            assert record.Format == 3
            assert record.Coordinate == original
            device = record.DeviceTable
        else:
            assert record.XAdvance == original
            assert subtable.ValueFormat1 == 0x44
            device = record.XAdvDevice
        assert device.DeltaFormat == hint.DeltaFormat
        assert device.DeltaValue == [delta]

    @pytest.mark.parametrize("full", [False, True])
    @pytest.mark.parametrize("delta", [1, 3, 7])
    @pytest.mark.parametrize("hint_axis", ["X", "Y"])
    def test_preserves_mixed_anchor_devices(self, varfontGPOS2, full, delta, hint_axis):
        from fontTools.otlLib.builder import buildDevice

        vf = varfontGPOS2
        anchor = (
            vf["GPOS"]
            .table.LookupList.Lookup[0]
            .SubTable[0]
            .BaseArray.BaseRecord[0]
            .BaseAnchor[0]
        )
        hint = buildDevice({10: delta})
        setattr(anchor, hint_axis + "DeviceTable", hint)
        limits = {"wght": 1.0}
        if full:
            limits["wdth"] = 0.0
        instancer.instantiateOTL(vf, instancer.NormalizedAxisLimits(limits))
        anchor = (
            vf["GPOS"]
            .table.LookupList.Lookup[0]
            .SubTable[0]
            .BaseArray.BaseRecord[0]
            .BaseAnchor[0]
        )
        assert anchor.Format == 3
        assert anchor.XCoordinate == (270 if hint_axis == "X" else 330)
        assert anchor.YCoordinate == 450
        assert getattr(anchor, hint_axis + "DeviceTable").DeltaValue == [delta]
        if full and hint_axis == "Y":
            assert getattr(anchor, "XDeviceTable", None) is None

    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": -1.0}, 110),  # -60
            ({"wght": 0}, 170),
            ({"wght": 0.5}, 200),  # +30
            ({"wght": 1.0}, 230),  # +60
            ({"wdth": -1.0}, 160),  # -10
            ({"wdth": -0.3}, 167),  # -3
            ({"wdth": 0}, 170),
            ({"wdth": 1.0}, 180),  # +10
        ],
    )
    def test_pin_and_drop_axis_GDEF(self, varfontGDEF, location, expected):
        vf = varfontGDEF
        assert "GDEF" in vf

        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateOTL(vf, location)

        assert "GDEF" in vf
        gdef = vf["GDEF"].table
        assert gdef.Version == 0x00010003
        assert gdef.VarStore
        assert gdef.LigCaretList
        caretValue = gdef.LigCaretList.LigGlyph[0].CaretValue[0]
        assert caretValue.Format == 3
        assert hasattr(caretValue, "DeviceTable")
        assert caretValue.DeviceTable.DeltaFormat == 0x8000
        assert caretValue.Coordinate == expected

    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": -1.0, "wdth": -1.0}, 100),  # -60 - 10
            ({"wght": -1.0, "wdth": 0.0}, 110),  # -60
            ({"wght": -1.0, "wdth": 1.0}, 120),  # -60 + 10
            ({"wght": 0.0, "wdth": -1.0}, 160),  # -10
            ({"wght": 0.0, "wdth": 0.0}, 170),
            ({"wght": 0.0, "wdth": 1.0}, 180),  # +10
            ({"wght": 1.0, "wdth": -1.0}, 220),  # +60 - 10
            ({"wght": 1.0, "wdth": 0.0}, 230),  # +60
            ({"wght": 1.0, "wdth": 1.0}, 240),  # +60 + 10
        ],
    )
    def test_full_instance_GDEF(self, varfontGDEF, location, expected):
        vf = varfontGDEF
        assert "GDEF" in vf

        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateOTL(vf, location)

        assert "GDEF" in vf
        gdef = vf["GDEF"].table
        assert gdef.Version == 0x00010000
        assert not hasattr(gdef, "VarStore")
        assert gdef.LigCaretList
        caretValue = gdef.LigCaretList.LigGlyph[0].CaretValue[0]
        assert caretValue.Format == 1
        assert not hasattr(caretValue, "DeviceTable")
        assert caretValue.Coordinate == expected

    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": -1.0}, -85),  # +25
            ({"wght": 0}, -110),
            ({"wght": 1.0}, -135),  # -25
            ({"wdth": -1.0}, -105),  # +5
            ({"wdth": 0}, -110),
            ({"wdth": 1.0}, -115),  # -5
        ],
    )
    def test_pin_and_drop_axis_GPOS_kern(self, varfontGPOS, location, expected):
        vf = varfontGPOS
        assert "GDEF" in vf
        assert "GPOS" in vf

        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateOTL(vf, location)

        gdef = vf["GDEF"].table
        gpos = vf["GPOS"].table
        assert gdef.Version == 0x00010003
        assert gdef.VarStore

        assert gpos.LookupList.Lookup[0].LookupType == 2  # PairPos
        pairPos = gpos.LookupList.Lookup[0].SubTable[0]
        valueRec1 = pairPos.PairSet[0].PairValueRecord[0].Value1
        assert valueRec1.XAdvDevice
        assert valueRec1.XAdvDevice.DeltaFormat == 0x8000
        assert valueRec1.XAdvance == expected

    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": -1.0, "wdth": -1.0}, -80),  # +25 + 5
            ({"wght": -1.0, "wdth": 0.0}, -85),  # +25
            ({"wght": -1.0, "wdth": 1.0}, -90),  # +25 - 5
            ({"wght": 0.0, "wdth": -1.0}, -105),  # +5
            ({"wght": 0.0, "wdth": 0.0}, -110),
            ({"wght": 0.0, "wdth": 1.0}, -115),  # -5
            ({"wght": 1.0, "wdth": -1.0}, -130),  # -25 + 5
            ({"wght": 1.0, "wdth": 0.0}, -135),  # -25
            ({"wght": 1.0, "wdth": 1.0}, -140),  # -25 - 5
        ],
    )
    def test_full_instance_GPOS_kern(self, varfontGPOS, location, expected):
        vf = varfontGPOS
        assert "GDEF" in vf
        assert "GPOS" in vf

        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateOTL(vf, location)

        assert "GDEF" not in vf
        gpos = vf["GPOS"].table

        assert gpos.LookupList.Lookup[0].LookupType == 2  # PairPos
        pairPos = gpos.LookupList.Lookup[0].SubTable[0]
        valueRec1 = pairPos.PairSet[0].PairValueRecord[0].Value1
        assert not hasattr(valueRec1, "XAdvDevice")
        assert valueRec1.XAdvance == expected

    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": -1.0}, (210, -85)),  # -60, +25
            ({"wght": 0}, (270, -110)),
            ({"wght": 0.5}, (300, -122)),  # +30, -12
            ({"wght": 1.0}, (330, -135)),  # +60, -25
            ({"wdth": -1.0}, (260, -105)),  # -10, +5
            ({"wdth": -0.3}, (267, -108)),  # -3, +2
            ({"wdth": 0}, (270, -110)),
            ({"wdth": 1.0}, (280, -115)),  # +10, -5
        ],
    )
    def test_pin_and_drop_axis_GPOS_mark_and_kern(
        self, varfontGPOS2, location, expected
    ):
        vf = varfontGPOS2
        assert "GDEF" in vf
        assert "GPOS" in vf

        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateOTL(vf, location)

        v1, v2 = expected
        gdef = vf["GDEF"].table
        gpos = vf["GPOS"].table
        assert gdef.Version == 0x00010003
        assert gdef.VarStore
        assert gdef.GlyphClassDef

        assert gpos.LookupList.Lookup[0].LookupType == 4  # MarkBasePos
        markBasePos = gpos.LookupList.Lookup[0].SubTable[0]
        baseAnchor = markBasePos.BaseArray.BaseRecord[0].BaseAnchor[0]
        assert baseAnchor.Format == 3
        assert baseAnchor.XDeviceTable
        assert baseAnchor.XDeviceTable.DeltaFormat == 0x8000
        assert not baseAnchor.YDeviceTable
        assert baseAnchor.XCoordinate == v1
        assert baseAnchor.YCoordinate == 450

        assert gpos.LookupList.Lookup[1].LookupType == 2  # PairPos
        pairPos = gpos.LookupList.Lookup[1].SubTable[0]
        valueRec1 = pairPos.PairSet[0].PairValueRecord[0].Value1
        assert valueRec1.XAdvDevice
        assert valueRec1.XAdvDevice.DeltaFormat == 0x8000
        assert valueRec1.XAdvance == v2

    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": -1.0, "wdth": -1.0}, (200, -80)),  # -60 - 10, +25 + 5
            ({"wght": -1.0, "wdth": 0.0}, (210, -85)),  # -60, +25
            ({"wght": -1.0, "wdth": 1.0}, (220, -90)),  # -60 + 10, +25 - 5
            ({"wght": 0.0, "wdth": -1.0}, (260, -105)),  # -10, +5
            ({"wght": 0.0, "wdth": 0.0}, (270, -110)),
            ({"wght": 0.0, "wdth": 1.0}, (280, -115)),  # +10, -5
            ({"wght": 1.0, "wdth": -1.0}, (320, -130)),  # +60 - 10, -25 + 5
            ({"wght": 1.0, "wdth": 0.0}, (330, -135)),  # +60, -25
            ({"wght": 1.0, "wdth": 1.0}, (340, -140)),  # +60 + 10, -25 - 5
        ],
    )
    def test_full_instance_GPOS_mark_and_kern(self, varfontGPOS2, location, expected):
        vf = varfontGPOS2
        assert "GDEF" in vf
        assert "GPOS" in vf

        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateOTL(vf, location)

        v1, v2 = expected
        gdef = vf["GDEF"].table
        gpos = vf["GPOS"].table
        assert gdef.Version == 0x00010000
        assert not hasattr(gdef, "VarStore")
        assert gdef.GlyphClassDef

        assert gpos.LookupList.Lookup[0].LookupType == 4  # MarkBasePos
        markBasePos = gpos.LookupList.Lookup[0].SubTable[0]
        baseAnchor = markBasePos.BaseArray.BaseRecord[0].BaseAnchor[0]
        assert baseAnchor.Format == 1
        assert not hasattr(baseAnchor, "XDeviceTable")
        assert not hasattr(baseAnchor, "YDeviceTable")
        assert baseAnchor.XCoordinate == v1
        assert baseAnchor.YCoordinate == 450

        assert gpos.LookupList.Lookup[1].LookupType == 2  # PairPos
        pairPos = gpos.LookupList.Lookup[1].SubTable[0]
        valueRec1 = pairPos.PairSet[0].PairValueRecord[0].Value1
        assert not hasattr(valueRec1, "XAdvDevice")
        assert valueRec1.XAdvance == v2

    def test_GPOS_ValueRecord_XAdvDevice_wtihout_XAdvance(self):
        # Test VF contains a PairPos adjustment in which the default instance
        # has no XAdvance but there are deltas in XAdvDevice (VariationIndex).
        vf = ttLib.TTFont()
        vf.importXML(os.path.join(TESTDATA, "PartialInstancerTest4-VF.ttx"))
        pairPos = vf["GPOS"].table.LookupList.Lookup[0].SubTable[0]
        assert pairPos.ValueFormat1 == 0x40
        valueRec1 = pairPos.PairSet[0].PairValueRecord[0].Value1
        assert not hasattr(valueRec1, "XAdvance")
        assert valueRec1.XAdvDevice.DeltaFormat == 0x8000
        outer = valueRec1.XAdvDevice.StartSize
        inner = valueRec1.XAdvDevice.EndSize
        assert vf["GDEF"].table.VarStore.VarData[outer].Item[inner] == [-50]

        # check that MutatorMerger for ValueRecord doesn't raise AttributeError
        # when XAdvDevice is present but there's no corresponding XAdvance.
        instancer.instantiateOTL(vf, instancer.NormalizedAxisLimits(wght=0.5))

        pairPos = vf["GPOS"].table.LookupList.Lookup[0].SubTable[0]
        assert pairPos.ValueFormat1 == 0x4
        valueRec1 = pairPos.PairSet[0].PairValueRecord[0].Value1
        assert not hasattr(valueRec1, "XAdvDevice")
        assert valueRec1.XAdvance == -25

    def test_full_instance_save_beyond64k(self):
        """A fully-instanced beyond-64k VF can be saved and reloaded.

        The variation tables use the uppercase companion spelling (GVAR, GLYF,
        HMTX, ...). Full instancing must instance and drop GVAR/HVAR -- which it
        only does once it resolves their uppercase tags -- and keep the extended
        GDEF at v1.4, NULLing its VarStore once the instance consumes it rather
        than downgrading the table and dropping the extended *2 fields like
        GlyphClassDef2.
        """
        from fontTools.fontBuilder import FontBuilder
        from fontTools.pens.ttGlyphPen import TTGlyphPen
        from fontTools.ttLib.beyond64k import upper_tables

        order = [".notdef"] + ["g%05d" % i for i in range(1, 0x10001)]  # 65537
        HI = "g65536"  # glyph id > 0xFFFF, the point of beyond-64k
        ACUTE = "g65530"

        def make_hi(scale):
            # a triangle that scales with the master, so gvar carries a real
            # delta for this beyond-64k glyph id
            pen = TTGlyphPen(None)
            pen.moveTo((100 * scale, 0))
            pen.lineTo((100 * scale, 100 * scale))
            pen.lineTo((0, 100 * scale))
            pen.closePath()
            return pen.glyph()

        def make_master(scale):
            fb = FontBuilder(unitsPerEm=1000)
            fb.setupGlyphOrder(order)
            glyphs = {g: _g_l_y_f.Glyph() for g in order}
            glyphs[HI] = make_hi(scale)
            fb.setupGlyf(glyphs)
            fb.setupHorizontalMetrics({g: (500, 0) for g in order})
            fb.setupHorizontalHeader(ascent=800, descent=-200)
            fb.setupNameTable({"familyName": "TestBeyond64k", "styleName": "R"})
            fb.setupPost(keepGlyphNames=False)
            addOpenTypeFeaturesFromString(
                fb.font,
                "markClass %(ACUTE)s <anchor %(a)d %(a)d> @TOP;\n"
                "feature mark { pos base %(HI)s <anchor %(a)d %(a)d> mark @TOP; } mark;\n"
                "table GDEF { GlyphClassDef ,,[%(ACUTE)s],; } GDEF;\n"
                % dict(ACUTE=ACUTE, HI=HI, a=10 * scale),
            )
            return fb.font

        doc = designspaceLib.DesignSpaceDocument()
        doc.addAxis(
            designspaceLib.AxisDescriptor(
                tag="wght", name="Weight", minimum=0, default=0, maximum=1000
            )
        )
        for loc, scale in [(0, 1), (1000, 2)]:
            doc.addSource(
                designspaceLib.SourceDescriptor(
                    font=make_master(scale), location={"Weight": loc}
                )
            )
        vf, _, _ = varLib.build(doc)
        assert vf.hasExtendedGlyphIDs()
        # ufo2ft uppercases the companion tables on the final VF, not the masters
        upper_tables(vf)
        assert "GVAR" in vf and "gvar" not in vf
        assert vf["GVAR"].variations[HI]  # the beyond-64k glyph carries a delta
        assert vf["GDEF"].table.Version == 0x00010004
        assert vf["GDEF"].table.VarStore is not None  # consumed by the full instance

        # the single axis -> pinning it is a full instance
        instancer.instantiateVariableFont(vf, {"wght": 500}, inplace=True)

        # GVAR/HVAR instanced then dropped; GDEF stays extended (v1.4)
        assert "GVAR" not in vf and "gvar" not in vf
        assert "HVAR" not in vf
        assert vf["GDEF"].table.Version == 0x00010004

        # the step that used to crash: save the fully-instanced font
        data = BytesIO()
        vf.save(data)
        data.seek(0)
        reloaded = ttLib.TTFont(data)
        reloaded.ensureDecompiled()

        assert reloaded.getGlyphCount() == 65537
        assert "GLYF" in reloaded and "LOCA" in reloaded
        assert reloaded["GDEF"].table.Version == 0x00010004
        assert reloaded["GDEF"].table.VarStore is None  # NULLed, not removed
        assert reloaded["GDEF"].table.GlyphClassDef2 is not None  # extended field kept
        # the beyond-64k mark-class value (3) survives at v1.4; resolve the acute
        # glyph by id since keepGlyphNames=False drops the names on reload
        acuteName = reloaded.getGlyphName(65530)
        assert reloaded["GDEF"].table.GlyphClassDef2.classDefs[acuteName] == 3

        # the gvar delta for the beyond-64k glyph was applied to its outline at
        # the pinned location: each master triangle scales 1x <-> 2x, so 500
        # (normalized 0.5) interpolates the coordinates halfway
        glyf = reloaded["GLYF"]
        hiGlyph = glyf[reloaded.getGlyphName(65536)]
        assert [tuple(pt) for pt in hiGlyph.coordinates] == [
            (150, 0),
            (150, 150),
            (0, 150),
        ]

        # the GPOS mark anchor interpolated at the pinned location: 10 <-> 20 -> 15
        gpos = reloaded["GPOS"].table
        markBasePos = gpos.LookupList2.Lookup[0].SubTable[0]
        assert markBasePos.Format == 2  # extended MarkBasePos
        anchor = markBasePos.BaseArray.BaseRecord[0].BaseAnchor[0]
        assert (anchor.XCoordinate, anchor.YCoordinate) == (15, 15)

    def test_partial_instance_save_beyond64k(self):
        """Partially instancing a beyond-64k VF retains and rewrites GVAR.

        Pinning one of two axes leaves residual variations, so the uppercase
        GVAR (and the companion metric tables) must be instanced in place and
        the font must still save and reload.
        """
        from fontTools.ttLib.beyond64k import upper_tables

        vf = ttLib.TTFont()
        vf.importXML(os.path.join(TESTDATA, "PartialInstancerTest-VF.ttx"))
        upper_tables(vf)
        assert "GVAR" in vf and "GLYF" in vf and "HMTX" in vf

        axes = {a.axisTag: a for a in vf["fvar"].axes}
        instancer.instantiateVariableFont(
            vf, {"wght": axes["wght"].defaultValue}, inplace=True
        )

        # the wdth axis survives, so GVAR keeps residual variations
        assert [a.axisTag for a in vf["fvar"].axes] == ["wdth"]
        assert "GVAR" in vf

        data = BytesIO()
        vf.save(data)
        data.seek(0)
        reloaded = ttLib.TTFont(data)
        reloaded.ensureDecompiled()
        assert "GVAR" in reloaded and "GLYF" in reloaded
        assert reloaded.getGlyphOrder() == vf.getGlyphOrder()

    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": 0.0}, -120),
            ({"wght": 0.5}, -110),
            ({"wght": 1.0}, -100),
            ({"wdth": 1.0}, -110),
            ({"wdth": 0.5}, -115),
        ],
    )
    def test_pin_and_drop_axis_BASE(self, varfontBASE, location, expected):
        vf = varfontBASE

        instancer.instantiateOTL(vf, instancer.NormalizedAxisLimits(location))

        base = vf["BASE"].table
        assert base.Version == 0x00010001
        assert base.VarStore
        coord = getBaseCoord(vf)
        assert coord.Format == 3
        assert coord.DeviceTable.DeltaFormat == 0x8000
        assert coord.Coordinate == expected

    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": 0.0, "wdth": 0.0}, -120),
            ({"wght": 1.0, "wdth": 0.0}, -100),
            ({"wght": 0.0, "wdth": 1.0}, -110),
            ({"wght": 1.0, "wdth": 1.0}, -90),
        ],
    )
    def test_full_instance_BASE(self, varfontBASE, location, expected):
        vf = varfontBASE

        instancer.instantiateOTL(vf, instancer.NormalizedAxisLimits(location))

        base = vf["BASE"].table
        assert base.Version == 0x00010000
        assert not hasattr(base, "VarStore")
        coord = getBaseCoord(vf)
        assert coord.Format == 1
        assert not hasattr(coord, "DeviceTable")
        assert coord.Coordinate == expected


class InstantiateAvarTest(object):
    @pytest.mark.parametrize("location", [{"wght": 0.0}, {"wdth": 0.0}])
    def test_pin_and_drop_axis(self, varfont, location):
        location = instancer.AxisLimits(location)
        normalized = location.normalize(varfont)

        instancer.instantiateAvar(varfont, location, normalized)

        assert set(varfont["avar"].segments).isdisjoint(location)

    def test_full_instance(self, varfont):
        location = instancer.AxisLimits(wght=0.0, wdth=0.0)
        normalized = location.normalize(varfont)

        instancer.instantiateAvar(varfont, location, normalized)

        assert "avar" not in varfont

    @staticmethod
    def quantizeF2Dot14Floats(mapping):
        return {
            floatToFixedToFloat(k, 14): floatToFixedToFloat(v, 14)
            for k, v in mapping.items()
        }

    # the following values come from NotoSans-VF.ttf
    DFLT_WGHT_MAPPING = {
        -1.0: -1.0,
        -0.6667: -0.7969,
        -0.3333: -0.5,
        0: 0,
        0.2: 0.18,
        0.4: 0.38,
        0.6: 0.61,
        0.8: 0.79,
        1.0: 1.0,
    }

    DFLT_WDTH_MAPPING = {-1.0: -1.0, -0.6667: -0.7, -0.3333: -0.36664, 0: 0, 1.0: 1.0}

    @pytest.fixture
    def varfont(self):
        fvarAxes = ("wght", (100, 400, 900)), ("wdth", (62.5, 100, 100))
        avarSegments = {
            "wght": self.quantizeF2Dot14Floats(self.DFLT_WGHT_MAPPING),
            "wdth": self.quantizeF2Dot14Floats(self.DFLT_WDTH_MAPPING),
        }
        varfont = ttLib.TTFont()
        varfont["name"] = ttLib.newTable("name")
        varLib._add_fvar(varfont, _makeDSAxesDict(fvarAxes), instances=())
        avar = varfont["avar"] = ttLib.newTable("avar")
        avar.segments = avarSegments
        return varfont

    @pytest.mark.parametrize(
        "axisLimits, expectedSegments",
        [
            pytest.param(
                {"wght": (100, 900)},
                {"wght": DFLT_WGHT_MAPPING, "wdth": DFLT_WDTH_MAPPING},
                id="wght=100:900",
            ),
            pytest.param(
                {"wght": (400, 900)},
                {
                    "wght": {
                        -1.0: -1.0,
                        0: 0,
                        0.2: 0.18,
                        0.4: 0.38,
                        0.6: 0.61,
                        0.8: 0.79,
                        1.0: 1.0,
                    },
                    "wdth": DFLT_WDTH_MAPPING,
                },
                id="wght=400:900",
            ),
            pytest.param(
                {"wght": (100, 400)},
                {
                    "wght": {
                        -1.0: -1.0,
                        -0.6667: -0.7969,
                        -0.3333: -0.5,
                        0: 0,
                        1.0: 1.0,
                    },
                    "wdth": DFLT_WDTH_MAPPING,
                },
                id="wght=100:400",
            ),
            pytest.param(
                {"wght": (400, 800)},
                {
                    "wght": {
                        -1.0: -1.0,
                        0: 0,
                        0.25: 0.22784,
                        0.50006: 0.48103,
                        0.75: 0.77214,
                        1.0: 1.0,
                    },
                    "wdth": DFLT_WDTH_MAPPING,
                },
                id="wght=400:800",
            ),
            pytest.param(
                {"wght": (400, 700)},
                {
                    "wght": {
                        -1.0: -1.0,
                        0: 0,
                        0.3334: 0.2951,
                        0.66675: 0.623,
                        1.0: 1.0,
                    },
                    "wdth": DFLT_WDTH_MAPPING,
                },
                id="wght=400:700",
            ),
            pytest.param(
                {"wght": (400, 600)},
                {
                    "wght": {-1.0: -1.0, 0: 0, 0.5: 0.47363, 1.0: 1.0},
                    "wdth": DFLT_WDTH_MAPPING,
                },
                id="wght=400:600",
            ),
            pytest.param(
                {"wdth": (62.5, 100)},
                {
                    "wght": DFLT_WGHT_MAPPING,
                    "wdth": {
                        -1.0: -1.0,
                        -0.6667: -0.7,
                        -0.3333: -0.36664,
                        0: 0,
                        1.0: 1.0,
                    },
                },
                id="wdth=62.5:100",
            ),
            pytest.param(
                {"wdth": (70, 100)},
                {
                    "wght": DFLT_WGHT_MAPPING,
                    "wdth": {
                        -1.0: -1.0,
                        -0.8334: -0.85364,
                        -0.4166: -0.44714,
                        0: 0,
                        1.0: 1.0,
                    },
                },
                id="wdth=70:100",
            ),
            pytest.param(
                {"wdth": (75, 100)},
                {
                    "wght": DFLT_WGHT_MAPPING,
                    "wdth": {-1.0: -1.0, -0.49994: -0.52374, 0: 0, 1.0: 1.0},
                },
                id="wdth=75:100",
            ),
            pytest.param(
                {"wdth": (77, 100)},
                {
                    "wght": DFLT_WGHT_MAPPING,
                    "wdth": {-1.0: -1.0, -0.54346: -0.56696, 0: 0, 1.0: 1.0},
                },
                id="wdth=77:100",
            ),
            pytest.param(
                {"wdth": (87.5, 100)},
                {"wght": DFLT_WGHT_MAPPING, "wdth": {-1.0: -1.0, 0: 0, 1.0: 1.0}},
                id="wdth=87.5:100",
            ),
        ],
    )
    def test_limit_axes(self, varfont, axisLimits, expectedSegments):
        axisLimits = instancer.AxisLimits(axisLimits)
        normalized = axisLimits.normalize(varfont)

        instancer.instantiateAvar(varfont, axisLimits, normalized)

        newSegments = varfont["avar"].segments
        expectedSegments = {
            axisTag: self.quantizeF2Dot14Floats(mapping)
            for axisTag, mapping in expectedSegments.items()
        }
        assert newSegments == expectedSegments

    @pytest.mark.parametrize(
        "invalidSegmentMap",
        [
            pytest.param({0.5: 0.5}, id="missing-required-maps-1"),
            pytest.param({-1.0: -1.0, 1.0: 1.0}, id="missing-required-maps-2"),
            pytest.param(
                {-1.0: -1.0, 0: 0, 0.5: 0.5, 0.6: 0.4, 1.0: 1.0},
                id="retrograde-value-maps",
            ),
        ],
    )
    def test_drop_invalid_segment_map(self, varfont, invalidSegmentMap, caplog):
        varfont["avar"].segments["wght"] = invalidSegmentMap

        axisLimits = instancer.AxisLimits(wght=(100, 400))
        normalized = axisLimits.normalize(varfont)

        with caplog.at_level(logging.WARNING, logger="fontTools.varLib.instancer"):
            instancer.instantiateAvar(varfont, axisLimits, normalized)

        assert "Invalid avar" in caplog.text
        assert "wght" not in varfont["avar"].segments

    def test_isValidAvarSegmentMap(self):
        assert instancer._isValidAvarSegmentMap("FOOO", {})
        assert instancer._isValidAvarSegmentMap("FOOO", {-1.0: -1.0, 0: 0, 1.0: 1.0})
        assert instancer._isValidAvarSegmentMap(
            "FOOO", {-1.0: -1.0, 0: 0, 0.5: 0.5, 1.0: 1.0}
        )
        assert instancer._isValidAvarSegmentMap(
            "FOOO", {-1.0: -1.0, 0: 0, 0.5: 0.5, 0.7: 0.5, 1.0: 1.0}
        )


class InstantiateFvarTest(object):
    @pytest.mark.parametrize(
        "location, instancesLeft",
        [
            (
                {"wght": 400.0},
                ["Regular", "SemiCondensed", "Condensed", "ExtraCondensed"],
            ),
            (
                {"wght": 100.0},
                ["Thin", "SemiCondensed Thin", "Condensed Thin", "ExtraCondensed Thin"],
            ),
            (
                {"wdth": 100.0},
                [
                    "Thin",
                    "ExtraLight",
                    "Light",
                    "Regular",
                    "Medium",
                    "SemiBold",
                    "Bold",
                    "ExtraBold",
                    "Black",
                ],
            ),
            # no named instance at pinned location
            ({"wdth": 90.0}, []),
        ],
    )
    def test_pin_and_drop_axis(self, varfont, location, instancesLeft):
        location = instancer.AxisLimits(location)

        instancer.instantiateFvar(varfont, location)

        fvar = varfont["fvar"]
        assert {a.axisTag for a in fvar.axes}.isdisjoint(location)

        for instance in fvar.instances:
            assert set(instance.coordinates).isdisjoint(location)

        name = varfont["name"]
        assert [
            name.getDebugName(instance.subfamilyNameID) for instance in fvar.instances
        ] == instancesLeft

    def test_full_instance(self, varfont):
        location = instancer.AxisLimits({"wght": 0.0, "wdth": 0.0})

        instancer.instantiateFvar(varfont, location)

        assert "fvar" not in varfont

    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": (30, 40, 700)}, (100, 100, 700)),
            ({"wght": (30, 40, None)}, (100, 100, 900)),
            ({"wght": (30, None, 700)}, (100, 400, 700)),
            ({"wght": (None, 200, 700)}, (100, 200, 700)),
            ({"wght": (40, None, None)}, (100, 400, 900)),
            ({"wght": (None, 40, None)}, (100, 100, 900)),
            ({"wght": (None, None, 700)}, (100, 400, 700)),
            ({"wght": (None, None, None)}, (100, 400, 900)),
        ],
    )
    def test_axis_limits(self, varfont, location, expected):
        location = instancer.AxisLimits(location)

        varfont = instancer.instantiateVariableFont(varfont, location)

        fvar = varfont["fvar"]
        axes = {a.axisTag: a for a in fvar.axes}
        assert axes["wght"].minValue == expected[0]
        assert axes["wght"].defaultValue == expected[1]
        assert axes["wght"].maxValue == expected[2]


class InstantiateSTATTest(object):
    @pytest.mark.parametrize(
        "location, expected",
        [
            ({"wght": 400}, ["Regular", "Condensed", "Upright", "Normal"]),
            (
                {"wdth": 100},
                ["Thin", "Regular", "Medium", "Black", "Upright", "Normal"],
            ),
        ],
    )
    def test_pin_and_drop_axis(self, varfont, location, expected):
        location = instancer.AxisLimits(location)

        instancer.instantiateSTAT(varfont, location)

        stat = varfont["STAT"].table
        designAxes = {a.AxisTag for a in stat.DesignAxisRecord.Axis}

        assert designAxes == {"wght", "wdth", "ital"}

        name = varfont["name"]
        valueNames = []
        for axisValueTable in stat.AxisValueArray.AxisValue:
            valueName = name.getDebugName(axisValueTable.ValueNameID)
            valueNames.append(valueName)

        assert valueNames == expected

    def test_skip_table_no_axis_value_array(self, varfont):
        varfont["STAT"].table.AxisValueArray = None

        instancer.instantiateSTAT(varfont, instancer.AxisLimits(wght=100))

        assert len(varfont["STAT"].table.DesignAxisRecord.Axis) == 3
        assert varfont["STAT"].table.AxisValueArray is None

    def test_skip_table_axis_value_array_empty(self, varfont):
        varfont["STAT"].table.AxisValueArray.AxisValue = []

        instancer.instantiateSTAT(varfont, {"wght": 100})

        assert len(varfont["STAT"].table.DesignAxisRecord.Axis) == 3
        assert not varfont["STAT"].table.AxisValueArray.AxisValue

    def test_skip_table_no_design_axes(self, varfont):
        stat = otTables.STAT()
        stat.Version = 0x00010001
        stat.populateDefaults()
        assert not stat.DesignAxisRecord
        assert not stat.AxisValueArray
        varfont["STAT"].table = stat

        instancer.instantiateSTAT(varfont, {"wght": 100})

        assert not varfont["STAT"].table.DesignAxisRecord

    @staticmethod
    def get_STAT_axis_values(stat):
        axes = stat.DesignAxisRecord.Axis
        result = []
        for axisValue in stat.AxisValueArray.AxisValue:
            if axisValue.Format == 1:
                result.append((axes[axisValue.AxisIndex].AxisTag, axisValue.Value))
            elif axisValue.Format == 3:
                result.append(
                    (
                        axes[axisValue.AxisIndex].AxisTag,
                        (axisValue.Value, axisValue.LinkedValue),
                    )
                )
            elif axisValue.Format == 2:
                result.append(
                    (
                        axes[axisValue.AxisIndex].AxisTag,
                        (
                            axisValue.RangeMinValue,
                            axisValue.NominalValue,
                            axisValue.RangeMaxValue,
                        ),
                    )
                )
            elif axisValue.Format == 4:
                result.append(
                    tuple(
                        (axes[rec.AxisIndex].AxisTag, rec.Value)
                        for rec in axisValue.AxisValueRecord
                    )
                )
            else:
                raise AssertionError(axisValue.Format)
        return result

    def test_limit_axes(self, varfont2):
        axisLimits = instancer.AxisLimits({"wght": (400, 500), "wdth": (75, 100)})

        instancer.instantiateSTAT(varfont2, axisLimits)

        assert len(varfont2["STAT"].table.AxisValueArray.AxisValue) == 5
        assert self.get_STAT_axis_values(varfont2["STAT"].table) == [
            ("wght", (400.0, 700.0)),
            ("wght", 500.0),
            ("wdth", (93.75, 100.0, 100.0)),
            ("wdth", (81.25, 87.5, 93.75)),
            ("wdth", (68.75, 75.0, 81.25)),
        ]

    def test_limit_axis_value_format_4(self, varfont2):
        stat = varfont2["STAT"].table

        axisValue = otTables.AxisValue()
        axisValue.Format = 4
        axisValue.AxisValueRecord = []
        for tag, value in (("wght", 575), ("wdth", 90)):
            rec = otTables.AxisValueRecord()
            rec.AxisIndex = next(
                i for i, a in enumerate(stat.DesignAxisRecord.Axis) if a.AxisTag == tag
            )
            rec.Value = value
            axisValue.AxisValueRecord.append(rec)
        stat.AxisValueArray.AxisValue.append(axisValue)

        instancer.instantiateSTAT(varfont2, instancer.AxisLimits(wght=(100, 600)))

        assert axisValue in varfont2["STAT"].table.AxisValueArray.AxisValue

        instancer.instantiateSTAT(varfont2, instancer.AxisLimits(wdth=(62.5, 87.5)))

        assert axisValue not in varfont2["STAT"].table.AxisValueArray.AxisValue

    def test_unknown_axis_value_format(self, varfont2, caplog):
        stat = varfont2["STAT"].table
        axisValue = otTables.AxisValue()
        axisValue.Format = 5
        stat.AxisValueArray.AxisValue.append(axisValue)

        with caplog.at_level(logging.WARNING, logger="fontTools.varLib.instancer"):
            instancer.instantiateSTAT(varfont2, instancer.AxisLimits(wght=400))

        assert "Unknown AxisValue table format (5)" in caplog.text
        assert axisValue in varfont2["STAT"].table.AxisValueArray.AxisValue


def test_setMacOverlapFlags():
    flagOverlapCompound = _g_l_y_f.OVERLAP_COMPOUND
    flagOverlapSimple = _g_l_y_f.flagOverlapSimple

    glyf = ttLib.newTable("glyf")
    glyf.glyphOrder = ["a", "b", "c"]
    a = _g_l_y_f.Glyph()
    a.numberOfContours = 1
    a.flags = [0]
    b = _g_l_y_f.Glyph()
    b.numberOfContours = -1
    comp = _g_l_y_f.GlyphComponent()
    comp.flags = 0
    b.components = [comp]
    c = _g_l_y_f.Glyph()
    c.numberOfContours = 0
    glyf.glyphs = {"a": a, "b": b, "c": c}

    instancer.setMacOverlapFlags(glyf)

    assert a.flags[0] & flagOverlapSimple != 0
    assert b.components[0].flags & flagOverlapCompound != 0


@pytest.fixture
def varfont2():
    f = ttLib.TTFont(recalcTimestamp=False)
    f.importXML(os.path.join(TESTDATA, "PartialInstancerTest2-VF.ttx"))
    return f


@pytest.fixture
def varfont3():
    f = ttLib.TTFont(recalcTimestamp=False)
    f.importXML(os.path.join(TESTDATA, "PartialInstancerTest3-VF.ttx"))
    return f


@pytest.fixture
def avar2_varfont():
    return ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False)


def _dump_ttx(ttFont):
    # compile to temporary bytes stream, reload and dump to XML
    tmp = BytesIO()
    ttFont.save(tmp)
    tmp.seek(0)
    ttFont2 = ttLib.TTFont(tmp, recalcBBoxes=False, recalcTimestamp=False)
    s = StringIO()
    ttFont2.saveXML(s)
    return stripVariableItemsFromTTX(s.getvalue())


def _get_expected_instance_ttx(
    name, *locations, overlap=instancer.OverlapMode.KEEP_AND_SET_FLAGS
):
    filename = f"{name}-VF-instance-{','.join(str(loc) for loc in locations)}"
    if overlap == instancer.OverlapMode.KEEP_AND_DONT_SET_FLAGS:
        filename += "-no-overlap-flags"
    elif overlap == instancer.OverlapMode.REMOVE:
        filename += "-no-overlaps"
    with open(
        os.path.join(TESTDATA, "test_results", f"{filename}.ttx"),
        "r",
        encoding="utf-8",
    ) as fp:
        return stripVariableItemsFromTTX(fp.read())


def _avar2_final_coords(font, user_loc):
    """Final normalized coordinates per the avar2 spec pipeline.

    Applies fvar normalization then the avar v1 + v2 mapping
    (table__a_v_a_r.renormalizeLocation), i.e. the exact algorithm a shaping
    engine runs. Used as an independent oracle: a correctly partial-instanced
    font must produce the same final coordinates as the original font at the
    same user-space location, for every axis that survives in the instance.
    """
    fvar = font["fvar"]
    norm = {
        axis.axisTag: models.normalizeValue(
            user_loc.get(axis.axisTag, axis.defaultValue),
            (axis.minValue, axis.defaultValue, axis.maxValue),
        )
        for axis in fvar.axes
    }
    avar = font.get("avar")
    if avar is None:
        return norm
    return avar.renormalizeLocation(norm, font, dropZeroes=False)


def _set_private_avar2_axis_deltas(font, outputTag, regions, deltas):
    """Replace avar2 deltas for an axis treated as private by the instancer.

    The partial-instancing design uses HIDDEN_AXIS as its private-axis marker:
    an unrestricted private axis has intermediate coordinate zero, so its
    final coordinate is determined by the avar2 delta alone.
    """
    axes = font["fvar"].axes
    axisTags = [axis.axisTag for axis in axes]
    outputIndex = axisTags.index(outputTag)
    regionList = builder.buildVarRegionList(regions, axisTags)
    varData = builder.buildVarData(list(range(len(regions))), [deltas], optimize=False)
    font["avar"].table.VarStore = builder.buildVarStore(regionList, [varData])
    mapping = [varStore.NO_VARIATION_INDEX] * len(axes)
    mapping[outputIndex] = 0
    font["avar"].table.VarIdxMap = builder.buildDeltaSetIndexMap(mapping)
    axes[outputIndex].flags |= 0x0001


def _add_gvar_sentinel(font, axisTag, support, sentinel):
    coordinateCount = len(font["gvar"].variations["T"][0].coordinates)
    font["gvar"].variations["T"].append(
        TupleVariation({axisTag: support}, [sentinel] * coordinateCount)
    )


def _has_gvar_sentinel(font, axisTag, support, sentinel):
    return any(
        variation.axes == {axisTag: support}
        and variation.coordinates
        and variation.coordinates[0] == sentinel
        for variation in font["gvar"].variations["T"]
    )


class InstantiateAvar2Test(object):
    def test_partial_limit_axis_roundtrip_matches_direct_instance(self, avar2_varfont):
        partial = instancer.instantiateVariableFont(
            avar2_varfont, {"wght": (300, 400, 700)}
        )

        wght = next(axis for axis in partial["fvar"].axes if axis.axisTag == "wght")
        assert (wght.minValue, wght.defaultValue, wght.maxValue) == (300, 400, 700)
        assert partial["avar"].majorVersion == 2
        assert getattr(partial["avar"].table, "VarStore", None) is not None
        assert getattr(partial["avar"].table, "VarIdxMap", None) is not None
        assert all(tag in partial for tag in ("gvar", "HVAR", "MVAR"))

        bytes_out = BytesIO()
        partial.save(bytes_out)
        bytes_out.seek(0)
        partial = ttLib.TTFont(bytes_out, recalcTimestamp=False)

        staged = instancer.instantiateVariableFont(
            partial, AVAR2_FULL_INSTANCE_LOCATION
        )
        direct = instancer.instantiateVariableFont(
            ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False),
            AVAR2_FULL_INSTANCE_LOCATION,
        )

        assert _dump_ttx(staged) == _dump_ttx(direct)

    def test_partial_pin_self_contained_axis_preserves_avar2(self, avar2_varfont):
        partial = instancer.instantiateVariableFont(avar2_varfont, {"wght": 650})

        assert all(axis.axisTag != "wght" for axis in partial["fvar"].axes)
        assert "wght" not in partial["avar"].segments
        assert partial["avar"].majorVersion == 2
        assert getattr(partial["avar"].table, "VarStore", None) is not None
        assert getattr(partial["avar"].table, "VarIdxMap", None) is not None
        assert all(tag in partial for tag in ("gvar", "HVAR", "MVAR"))

        bytes_out = BytesIO()
        partial.save(bytes_out)
        bytes_out.seek(0)
        partial = ttLib.TTFont(bytes_out, recalcTimestamp=False)

        assert all(axis.axisTag != "wght" for axis in partial["fvar"].axes)
        assert "wght" not in partial["avar"].segments
        assert partial["avar"].majorVersion == 2
        assert getattr(partial["avar"].table, "VarStore", None) is not None

    # In Amstelvar-avar2.subset several fvar axes share a single avar2 varIdx
    # (GRAD & XOPQ, YOPQ & YTLC & YTUC, ...). Offset compensation must not leak
    # between axes that share a delta row. Each case below restricts/pins one or
    # more shared-varIdx axes and checks that the final normalized coordinates
    # of every surviving axis still match the original font at the same user
    # location (the spec-pipeline oracle above). Before the fix these diverged
    # by up to ~1.0 (full scale) on the untouched partner axes.
    @pytest.mark.parametrize(
        "limits, samples",
        [
            # two axes sharing a varIdx, both restricted
            (
                {"GRAD": (-100, 0, 300), "XOPQ": (50, 176, 220)},
                [
                    {"GRAD": -100, "XOPQ": 220},
                    {"GRAD": 300, "XOPQ": 50},
                    {"GRAD": 150, "XOPQ": 176},
                ],
            ),
            # three axes sharing a varIdx, all restricted
            (
                {
                    "YOPQ": (30, 124, 130),
                    "YTLC": (450, 500, 560),
                    "YTUC": (600, 750, 900),
                },
                [
                    {"YOPQ": 30, "YTLC": 560, "YTUC": 600},
                    {"YOPQ": 130, "YTLC": 450, "YTUC": 900},
                ],
            ),
            # restrict one axis of a shared pair; the free partner (GRAD) must
            # stay uncorrupted even when the restricted axis is off its default
            (
                {"XOPQ": (100, 176, 250)},
                [{"XOPQ": 250, "GRAD": g} for g in (-300, 0, 300, 500)],
            ),
            # restricted axis whose default MOVES: exercises the empty-region
            # bias, which contaminated the free partner unconditionally
            (
                {"XOPQ": (100, 220, 250)},
                [{"XOPQ": 220, "GRAD": g} for g in (-300, 0, 500)],
            ),
            # moved default sampled at INTERIOR points (unique varIdx axis):
            # the inverse renormalization kinks where the old default lands in
            # the new space, so a plain two-tent offset is wrong between the
            # anchors even though it is exact at min/default/max.
            (
                {"XTRA": (421, 586, 617)},
                [{"XTRA": x} for x in (450, 470, 519, 560, 600)],
            ),
            # moved default on a shared-varIdx axis, sampled at interior points
            (
                {"XOPQ": (100, 220, 250)},
                [{"XOPQ": x, "GRAD": g} for x in (130, 176, 210) for g in (-200, 300)],
            ),
            # pin one axis of a shared pair (kept hidden as it is not
            # self-contained); its free partner must be unaffected
            (
                {"XOPQ": 200},
                [{"XOPQ": 200, "GRAD": g} for g in (-300, 0, 500)],
            ),
        ],
    )
    def test_partial_instance_final_coords_match_original(self, limits, samples):
        original = ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False)
        partial = instancer.instantiateVariableFont(
            ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False), dict(limits)
        )
        bytes_out = BytesIO()
        partial.save(bytes_out)
        bytes_out.seek(0)
        partial = ttLib.TTFont(bytes_out, recalcTimestamp=False)

        partial_axes = {axis.axisTag for axis in partial["fvar"].axes}
        for user_loc in samples:
            orig_final = _avar2_final_coords(original, user_loc)
            part_loc = {k: v for k, v in user_loc.items() if k in partial_axes}
            part_final = _avar2_final_coords(partial, part_loc)
            for tag in partial_axes:
                o = round(orig_final.get(tag, 0) * 16384)
                p = round(part_final.get(tag, 0) * 16384)
                # tolerance: a couple of F2Dot14 units of rounding noise
                assert abs(o - p) <= 2, (
                    f"axis {tag} at {user_loc}: original final {o} "
                    f"!= partial {p} (diff {o - p})"
                )

    def test_offset_compensation_exhaustive(self):
        # Exhaustive offset-compensation check: every single-axis and pairwise
        # restriction (with a MOVED default, the hardest case) must reproduce
        # the original font's final normalized coordinates at interior user
        # locations for every surviving axis. Also doubles as an integration
        # smoke test that the full partial-instancing path (including region
        # culling / getExtremes) runs cleanly across many axis combinations.
        original = ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False)
        axes = {
            a.axisTag: (a.minValue, a.defaultValue, a.maxValue)
            for a in original["fvar"].axes
        }

        def moved(tag):
            lo, d, hi = axes[tag]
            return (round(lo + (d - lo) * 0.3), round(d + (hi - d) * 0.3), round(hi))

        tags = list(axes)
        combos = list(itertools.combinations(tags, 1)) + list(
            itertools.combinations(tags, 2)
        )
        for combo in combos:
            limits = {t: moved(t) for t in combo}
            partial = instancer.instantiateVariableFont(
                ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False), dict(limits)
            )
            partial_axes = {axis.axisTag for axis in partial["fvar"].axes}
            for i in range(5):
                user_loc = {
                    t: moved(t)[0] + (moved(t)[2] - moved(t)[0]) * i / 4 for t in combo
                }
                orig_final = _avar2_final_coords(original, user_loc)
                part_loc = {k: v for k, v in user_loc.items() if k in partial_axes}
                part_final = _avar2_final_coords(partial, part_loc)
                for tag in partial_axes:
                    o = round(orig_final.get(tag, 0) * 16384)
                    p = round(part_final.get(tag, 0) * 16384)
                    assert abs(o - p) <= 2, (
                        f"{combo} axis {tag} at {user_loc}: "
                        f"original final {o} != partial {p} (diff {o - p})"
                    )

    def test_offset_compensation_interior_avar1_breakpoints(self):
        # An avar v1 map with a breakpoint strictly inside the retained range
        # adds a kink to the offset function that the {-1, 0, +1, z_old} anchors
        # alone miss, so partial instancing was approximate there (worst under a
        # moved default). _instantiateAvarV2 now also collects each retained
        # avar v1 breakpoint, removing that structural error. A smaller residual
        # from F2Dot14 requantization of the retained (steep, near-edge) segment
        # map can remain, so tolerances are per-case rather than the 2-unit
        # quantization floor used elsewhere. Every case below FAILS without the
        # breakpoint collection (worst 4 and 14 respectively).
        cases = [
            # gentle map, moderate moved default: structural error fully removed.
            (
                {"opsz": {-1: -1, -0.5: -0.35, 0: 0, 0.5: 0.65, 1: 1}},
                {"opsz": (8, 40, 120)},
                2,
            ),
            # moved default near the fvar edge + interior breakpoint: the regime
            # that exposed the bug. Structural error removed (was 14); the ~3
            # residual is retained-map requantization, not the offset math.
            ({"opsz": {-1: -1, 0: 0, 1: 1, -0.45: -0.27}}, {"opsz": (8, 89.6, 144)}, 6),
        ]
        for segments, limits, tol in cases:

            def make():
                f = ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False)
                for tag, seg in segments.items():
                    f["avar"].segments[tag] = dict(seg)
                return f

            original = make()
            partial = instancer.instantiateVariableFont(make(), dict(limits))
            partial_axes = {axis.axisTag for axis in partial["fvar"].axes}
            tag = next(iter(limits))
            assert tag in partial_axes
            lo, _, hi = limits[tag]
            worst = 0
            for i in range(401):
                u = lo + (hi - lo) * i / 400
                o = round(_avar2_final_coords(original, {tag: u}).get(tag, 0) * 16384)
                p = round(_avar2_final_coords(partial, {tag: u}).get(tag, 0) * 16384)
                worst = max(worst, abs(o - p))
            assert worst <= tol, f"{segments} {limits}: worst {worst} > tolerance {tol}"

    def test_truncated_varIdxMap(self, avar2_varfont):
        # A compiled DeltaSetIndexMap may be stored truncated (trailing
        # duplicates trimmed; reads clamp to the last entry). The fixture's
        # mapping ends in NO_VARIATION_INDEX entries for wght/wdth/opsz, like
        # fontations' Amstelvar-avar2.A.ttf; truncating it must not break the
        # offset-compensation write path (which used to IndexError when
        # writing at an axis index beyond the stored length).
        mapping = avar2_varfont["avar"].table.VarIdxMap.mapping
        assert mapping[-3:] == [varStore.NO_VARIATION_INDEX] * 3
        avar2_varfont["avar"].table.VarIdxMap.mapping = mapping[:10]

        reference = instancer.instantiateVariableFont(
            ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False),
            {"opsz": (8, 14, 30)},
        )
        partial = instancer.instantiateVariableFont(
            avar2_varfont, {"opsz": (8, 14, 30)}
        )

        # Same final coordinates as instancing the untruncated font.
        for user_loc in ({"opsz": 8}, {"opsz": 14}, {"opsz": 22}, {"opsz": 30}):
            assert _avar2_final_coords(partial, user_loc) == pytest.approx(
                _avar2_final_coords(reference, user_loc), abs=2 / 16384
            )

    def test_empty_v1_segments_keeps_avar2(self, avar2_varfont):
        # avar2 fonts need no v1 segment maps (design doc §9.6). An empty (or
        # partial) segments dict must not trigger the "all axes pinned" early
        # drop of the table on a pure range restriction — that would delete
        # the entire avar2 VarStore while gvar stays in old-space coordinates.
        original = ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False)
        original["avar"].segments = {}
        avar2_varfont["avar"].segments = {}

        partial = instancer.instantiateVariableFont(
            avar2_varfont, {"wght": (300, 400, 700)}
        )

        assert "avar" in partial
        assert getattr(partial["avar"].table, "VarStore", None) is not None

        for wght in (300, 400, 550, 700):
            assert _avar2_final_coords(partial, {"wght": wght}) == pytest.approx(
                _avar2_final_coords(original, {"wght": wght}), abs=2 / 16384
            )

    def test_avar2_null_varstore_never_downgraded(self, avar2_varfont):
        # An avar 2.0 table with a NULL VarStore is legal and behaves as
        # plain v1 (it used to crash normalize() by entering the v2 path).
        # It is never downgraded to v1: partial instancing takes the avar2
        # path, creating offset-compensation delta rows on demand so the
        # instance stays bit-exact against the original.
        original = ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False)
        original["avar"].table.VarStore = None
        original["avar"].table.VarIdxMap = None
        avar2_varfont["avar"].table.VarStore = None
        avar2_varfont["avar"].table.VarIdxMap = None

        partial = instancer.instantiateVariableFont(
            avar2_varfont, {"wght": (300, 400, 700)}
        )
        wght = next(axis for axis in partial["fvar"].axes if axis.axisTag == "wght")
        assert (wght.minValue, wght.defaultValue, wght.maxValue) == (300, 400, 700)
        assert partial["avar"].majorVersion == 2
        assert getattr(partial["avar"].table, "VarStore", None) is not None

        # Survives compile+decompile, and the final normalized coordinates
        # match the original (v1-behaving) font at the same user locations.
        bytes_out = BytesIO()
        partial.save(bytes_out)
        bytes_out.seek(0)
        partial = ttLib.TTFont(bytes_out, recalcTimestamp=False)
        assert partial["avar"].majorVersion == 2

        for wght in (300, 350, 400, 550, 700):
            assert _avar2_final_coords(partial, {"wght": wght}) == pytest.approx(
                _avar2_final_coords(original, {"wght": wght}), abs=2 / 16384
            )

    def test_unpopulated_default_2_tuple_limits(self, avar2_varfont):
        # AxisLimits({"wght": (300, 700)}) leaves default=None; the avar2
        # offset-compensation path must fall back to the fvar default instead
        # of crashing. Also exercises instantiateAvar's optional
        # normalizedLimits (back-compat with the (varfont, axisLimits) form).
        axisLimits = instancer.AxisLimits({"wght": (300, 700)})
        instancer.instantiateAvar(avar2_varfont, axisLimits)

        assert "avar" in avar2_varfont
        assert getattr(avar2_varfont["avar"].table, "VarStore", None) is not None

    def test_isTupleVariationDead_boundary_peak(self):
        # supportScalar returns 1 (not 0) at v == peak, so a tent whose peak
        # sits exactly on the reachable boundary is still live there.
        live = TupleVariation({"wght": (0.5, 0.5, 1.0)}, [10] * 4)
        assert not instancer._isTupleVariationDead(live, {"wght": (0.0, 0.5)})
        live = TupleVariation({"wght": (-1.0, -0.5, -0.5)}, [10] * 4)
        assert not instancer._isTupleVariationDead(live, {"wght": (-0.5, 0.0)})
        dead = TupleVariation({"wght": (0.5, 0.75, 1.0)}, [10] * 4)
        assert instancer._isTupleVariationDead(dead, {"wght": (0.0, 0.25)})

    @pytest.mark.parametrize("gvarTag", ["gvar", "GVAR"])
    def test_cull_glyph_variations(self, gvarTag):
        font = ttLib.TTFont()
        font["fvar"] = ttLib.newTable("fvar")
        axis = _f_v_a_r.Axis()
        axis.axisTag = "wght"
        font["fvar"].axes = [axis]
        font[gvarTag] = ttLib.newTable(gvarTag)
        live = TupleVariation({"wght": (0, 0.25, 0.5)}, [(10, 20)] * 4)
        dead = TupleVariation({"wght": (0.5, 0.75, 1)}, [(30, 40)] * 4)
        font[gvarTag].variations = {"A": [live, dead]}

        instancer._cullVariationsForAvar2(font, {"wght": (0, 0.25)})

        assert font[gvarTag].variations == {"A": [live]}

    def test_avar2_culling_preserves_live_gvar_regions(self, avar2_varfont):
        # Region culling may only delete TupleVariations whose support scalar
        # is zero at EVERY reachable final coordinate. Sample a grid of user
        # locations, map each through the spec pipeline of the ORIGINAL font,
        # and require every culled gvar variation to be dead at all of them.
        original = ttLib.TTFont(AVAR2_SUBSET_PATH, recalcTimestamp=False)
        limits = {"wght": (300, 400, 700), "opsz": (10, 14, 20)}
        partial = instancer.instantiateVariableFont(avar2_varfont, dict(limits))

        def freeze(tv):
            return (
                tuple(sorted(tv.axes.items())),
                tuple(tuple(c) if c is not None else None for c in tv.coordinates),
            )

        grid = [
            {"wght": w, "opsz": o, "GRAD": g}
            for w in (300, 400, 550, 700)
            for o in (10, 14, 20)
            for g in (-300, 0, 500)
        ]
        finals = [_avar2_final_coords(original, loc) for loc in grid]

        gvarOld = original["gvar"].variations
        gvarNew = partial["gvar"].variations
        for glyphName in gvarOld:
            kept = collections.Counter(freeze(tv) for tv in gvarNew[glyphName])
            for tv in gvarOld[glyphName]:
                if kept[freeze(tv)]:
                    kept[freeze(tv)] -= 1
                    continue
                # culled: must be unreachable at every sampled location
                for loc, final in zip(grid, finals):
                    scalar = models.supportScalar(final, tv.axes)
                    assert scalar == 0, (
                        f"culled variation {tv.axes} of {glyphName!r} is live "
                        f"(scalar {scalar}) at {loc} -> {final}"
                    )

    def test_culling_preserves_one_sided_support_sentinel(self, avar2_varfont):
        outputTag = "XOPQ"
        inputTag = "wght"
        support = (0.5, 1.0, 1.0)
        sentinel = (12345, -6789)
        _set_private_avar2_axis_deltas(
            avar2_varfont,
            outputTag,
            [
                {inputTag: (0.0, 0.25, 0.25)},
                {inputTag: (0.0, 0.25, 0.5)},
            ],
            [-16384, 16384],
        )
        _add_gvar_sentinel(avar2_varfont, outputTag, support, sentinel)

        inputAxis = next(
            axis for axis in avar2_varfont["fvar"].axes if axis.axisTag == inputTag
        )
        normalizedInput = 4097 / 16384
        userInput = inputAxis.defaultValue + normalizedInput * (
            inputAxis.maxValue - inputAxis.defaultValue
        )
        location = {inputTag: userInput}
        before = _avar2_final_coords(avar2_varfont, location)
        assert before[outputTag] == 16380 / 16384
        assert models.supportScalar(before, {outputTag: support}) > 0.99

        partial = instancer.instantiateVariableFont(
            avar2_varfont,
            {
                inputTag: (
                    inputAxis.minValue,
                    inputAxis.defaultValue,
                    inputAxis.maxValue,
                )
            },
        )

        assert _avar2_final_coords(partial, location)[outputTag] == before[outputTag]
        assert _has_gvar_sentinel(partial, outputTag, support, sentinel)

    def test_culling_bounds_runtime_rounded_avar2_delta(self, avar2_varfont):
        outputTag = "XOPQ"
        inputTag = "wght"
        unit = 1 / 16384
        support = (unit, unit, 1.0)
        sentinel = (22222, -3333)
        _set_private_avar2_axis_deltas(
            avar2_varfont,
            outputTag,
            [
                {inputTag: (0.0, 0.125, 0.25)},
                {inputTag: (0.0, 0.125, 0.375)},
            ],
            [-8, 1],
        )
        _add_gvar_sentinel(avar2_varfont, outputTag, support, sentinel)

        inputAxis = next(
            axis for axis in avar2_varfont["fvar"].axes if axis.axisTag == inputTag
        )
        userInput = inputAxis.defaultValue + 0.25 * (
            inputAxis.maxValue - inputAxis.defaultValue
        )
        location = {inputTag: userInput}
        before = _avar2_final_coords(avar2_varfont, location)
        assert before[outputTag] == unit
        assert models.supportScalar(before, {outputTag: support}) == 1.0

        partial = instancer.instantiateVariableFont(
            avar2_varfont,
            {
                inputTag: (
                    inputAxis.minValue,
                    inputAxis.defaultValue,
                    inputAxis.maxValue,
                )
            },
        )

        assert _avar2_final_coords(partial, location)[outputTag] == unit
        assert _has_gvar_sentinel(partial, outputTag, support, sentinel)

    @pytest.mark.parametrize(
        "delta,support,expected,sentinel",
        [
            pytest.param(32767, (0.5, 1.0, 1.0), 1.0, (30001, -30001), id="upper"),
            pytest.param(-32768, (-1.0, -1.0, -0.5), -1.0, (-30001, 30001), id="lower"),
        ],
    )
    def test_culling_clamps_overshooting_range_on_both_sides(
        self, avar2_varfont, delta, support, expected, sentinel
    ):
        outputTag = "XOPQ"
        inputTag = "wght"
        _set_private_avar2_axis_deltas(avar2_varfont, outputTag, [{}], [delta])
        _add_gvar_sentinel(avar2_varfont, outputTag, support, sentinel)

        before = _avar2_final_coords(avar2_varfont, {})
        assert before[outputTag] == expected
        assert models.supportScalar(before, {outputTag: support}) == 1.0

        inputAxis = next(
            axis for axis in avar2_varfont["fvar"].axes if axis.axisTag == inputTag
        )
        partial = instancer.instantiateVariableFont(
            avar2_varfont,
            {
                inputTag: (
                    inputAxis.minValue,
                    inputAxis.defaultValue,
                    inputAxis.maxValue,
                )
            },
        )

        assert _avar2_final_coords(partial, {})[outputTag] == expected
        assert _has_gvar_sentinel(partial, outputTag, support, sentinel)

    def test_full_instance_avar2_malformed_empty_varstore(self, avar2_varfont):
        # With no VarIdxMap, an empty non-NULL VarStore produces implicit
        # indices outside the store. The partial avar2 path treats them as zero
        # deltas, so full instancing should do the same. HarfBuzz corroborates
        # that defensive policy:
        # https://github.com/harfbuzz/harfbuzz/blob/d2df3cdcc0836299a163dc0399a6b047d19ac56c/src/hb-ot-layout-common.hh#L3354-L3363
        axisTags = [axis.axisTag for axis in avar2_varfont["fvar"].axes]
        avar2_varfont["avar"].table.VarStore = builder.buildVarStore(
            builder.buildVarRegionList([], axisTags), []
        )
        avar2_varfont["avar"].table.VarIdxMap = None
        defaults = {
            axis.axisTag: axis.defaultValue for axis in avar2_varfont["fvar"].axes
        }

        static = instancer.instantiateVariableFont(avar2_varfont, defaults)

        assert "fvar" not in static
        assert "avar" not in static


class InstantiateVariableFontTest(object):
    @pytest.mark.parametrize(
        "wght, wdth",
        [(100, 100), (400, 100), (900, 100), (100, 62.5), (400, 62.5), (900, 62.5)],
    )
    def test_multiple_instancing(self, varfont2, wght, wdth):
        partial = instancer.instantiateVariableFont(varfont2, {"wght": wght})
        instance = instancer.instantiateVariableFont(partial, {"wdth": wdth})

        expected = _get_expected_instance_ttx("PartialInstancerTest2", wght, wdth)

        assert _dump_ttx(instance) == expected

    def test_default_instance(self, varfont2):
        instance = instancer.instantiateVariableFont(
            varfont2, {"wght": None, "wdth": None}
        )

        expected = _get_expected_instance_ttx("PartialInstancerTest2", 400, 100)

        assert _dump_ttx(instance) == expected

    def test_move_weight_width_axis_default(self, varfont2):
        # https://github.com/fonttools/fonttools/issues/2885
        assert varfont2["OS/2"].usWeightClass == 400
        assert varfont2["OS/2"].usWidthClass == 5

        varfont = instancer.instantiateVariableFont(
            varfont2, {"wght": (100, 500, 900), "wdth": 87.5}
        )

        assert varfont["OS/2"].usWeightClass == 500
        assert varfont["OS/2"].usWidthClass == 4

    @pytest.mark.parametrize(
        "overlap, wght",
        [
            (instancer.OverlapMode.KEEP_AND_DONT_SET_FLAGS, 400),
            (instancer.OverlapMode.REMOVE, 400),
            (instancer.OverlapMode.REMOVE, 700),
        ],
    )
    def test_overlap(self, varfont3, wght, overlap):
        pytest.importorskip("pathops")

        location = {"wght": wght}

        instance = instancer.instantiateVariableFont(
            varfont3, location, overlap=overlap
        )

        expected = _get_expected_instance_ttx(
            "PartialInstancerTest3", wght, overlap=overlap
        )

        assert _dump_ttx(instance) == expected

    def test_singlepos(self):
        varfont = ttLib.TTFont(recalcTimestamp=False)
        varfont.importXML(os.path.join(TESTDATA, "SinglePos.ttx"))

        location = {"wght": 280, "opsz": 18}

        instance = instancer.instantiateVariableFont(
            varfont,
            location,
        )

        expected = _get_expected_instance_ttx("SinglePos", *location.values())

        assert _dump_ttx(instance) == expected

    def test_varComposite(self):
        input_path = os.path.join(
            TESTDATA, "..", "..", "..", "ttLib", "data", "varc-6868.ttf"
        )
        varfont = ttLib.TTFont(input_path)

        location = {"wght": 600}

        # We currently do not allow this either; although in theory
        # it should be possible.
        with pytest.raises(
            NotImplementedError,
            match="is not supported.",
        ):
            instance = instancer.instantiateVariableFont(
                varfont,
                location,
            )

        location = {"0000": 0.5}

        with pytest.raises(
            NotImplementedError,
            match="is not supported.",
        ):
            instance = instancer.instantiateVariableFont(
                varfont,
                location,
            )


def _conditionSetAsDict(conditionSet, axisOrder):
    result = {}
    conditionSets = conditionSet.ConditionTable if conditionSet is not None else []
    for cond in conditionSets:
        assert cond.Format == 1
        axisTag = axisOrder[cond.AxisIndex]
        result[axisTag] = (cond.FilterRangeMinValue, cond.FilterRangeMaxValue)
    return result


def _getSubstitutions(gsub, lookupIndices):
    subs = {}
    for index, lookup in enumerate(gsub.LookupList.Lookup):
        if index in lookupIndices:
            for subtable in lookup.SubTable:
                subs.update(subtable.mapping)
    return subs


def makeFeatureVarsFont(conditionalSubstitutions):
    axes = set()
    glyphs = set()
    for region, substitutions in conditionalSubstitutions:
        for box in region:
            axes.update(box.keys())
        glyphs.update(*substitutions.items())

    varfont = ttLib.TTFont()
    varfont.setGlyphOrder(sorted(glyphs))

    fvar = varfont["fvar"] = ttLib.newTable("fvar")
    fvar.axes = []
    for axisTag in sorted(axes):
        axis = _f_v_a_r.Axis()
        axis.axisTag = Tag(axisTag)
        fvar.axes.append(axis)

    featureVars.addFeatureVariations(varfont, conditionalSubstitutions)

    return varfont


def _lookupVariationCondition(minimum, maximum, axisIndex=0):
    condition = otTables.ConditionTable()
    condition.Format = 1
    condition.AxisIndex = axisIndex
    condition.FilterRangeMinValue = minimum
    condition.FilterRangeMaxValue = maximum
    return condition


def _lookupVariationValueCondition(defaultValue, varIdx=otTables.NO_VARIATION_INDEX):
    condition = otTables.ConditionTable()
    condition.Format = 2
    condition.DefaultValue = defaultValue
    condition.VarIdx = varIdx
    return condition


def _lookupVariationCompoundCondition(format, conditions):
    condition = otTables.ConditionTable()
    condition.Format = format
    condition.ConditionTable = conditions
    condition.ConditionCount = len(conditions)
    return condition


def _lookupVariationRecord(condition, lookupIndices):
    lookupIndexList = otTables.LookupIndexList()
    lookupIndexList.LookupIndex = lookupIndices
    lookupIndexList.LookupIndexCount = len(lookupIndices)

    record = otTables.LookupConditionRecord()
    record.ConditionTable = condition
    record.LookupIndexList = lookupIndexList
    return record


def makeLookupVariationsFont(withVarStore=False):
    glyphOrder = [
        ".notdef",
        "A",
        "A.alt",
        "B",
        "B.alt",
        "C",
        "C.alt",
        "D",
        "D.alt",
    ]
    font = ttLib.TTFont()
    font.setGlyphOrder(glyphOrder)
    font["name"] = ttLib.newTable("name")
    font["name"].names = []

    fvar = font["fvar"] = ttLib.newTable("fvar")
    fvar.axes = []
    for tag in ("wght", "wdth"):
        axis = _f_v_a_r.Axis()
        axis.axisTag = Tag(tag)
        axis.minValue = -1
        axis.defaultValue = 0
        axis.maxValue = 1
        axis.axisNameID = 256 + len(fvar.axes)
        axis.flags = 0
        fvar.axes.append(axis)
    fvar.instances = []

    addOpenTypeFeaturesFromString(
        font,
        """
        languagesystem DFLT dflt;
        lookup DefaultLiga { sub A by A.alt; } DefaultLiga;
        lookup ConditionalB { sub B by B.alt; } ConditionalB;
        lookup ConditionalC { sub C by C.alt; } ConditionalC;
        lookup ConditionalD { sub D by D.alt; } ConditionalD;
        feature liga { lookup DefaultLiga; } liga;
        feature zzzz {
          lookup ConditionalB;
          lookup ConditionalC;
          lookup ConditionalD;
        } zzzz;
        """,
    )

    gsub = font["GSUB"].table
    featureIndices = {
        record.FeatureTag: index
        for index, record in enumerate(gsub.FeatureList.FeatureRecord)
    }
    conditionalLookups = list(
        gsub.FeatureList.FeatureRecord[featureIndices["zzzz"]].Feature.LookupListIndex
    )

    removedFeatureIndex = featureIndices["zzzz"]
    gsub.FeatureList.FeatureRecord.pop(removedFeatureIndex)
    gsub.FeatureList.FeatureCount -= 1
    for scriptRecord in gsub.ScriptList.ScriptRecord:
        langSystems = [scriptRecord.Script.DefaultLangSys]
        langSystems.extend(
            record.LangSys for record in scriptRecord.Script.LangSysRecord
        )
        for langSystem in filter(None, langSystems):
            langSystem.FeatureIndex = [
                index - (index > removedFeatureIndex)
                for index in langSystem.FeatureIndex
                if index != removedFeatureIndex
            ]
            langSystem.FeatureCount = len(langSystem.FeatureIndex)

    featureIndices = {
        record.FeatureTag: index
        for index, record in enumerate(gsub.FeatureList.FeatureRecord)
    }
    conditionB = _lookupVariationCompoundCondition(
        3,
        [
            _lookupVariationCondition(0.25, 1.0),
            _lookupVariationCondition(-0.5, 0.5, 1),
            _lookupVariationValueCondition(1),
        ],
    )
    conditionC = _lookupVariationCompoundCondition(
        4,
        [
            _lookupVariationCondition(0.5, 1.0),
            (
                _lookupVariationValueCondition(-1, 0)
                if withVarStore
                else _lookupVariationCondition(0.75, 1.0, 1)
            ),
            _lookupVariationValueCondition(0),
        ],
    )
    conditionD = otTables.ConditionTable()
    conditionD.Format = 5
    conditionD.ConditionTable = _lookupVariationCondition(-1.0, 0.24)

    featureLookups = otTables.FeatureLookupsTable()
    featureLookups.Version = 0x00010000
    featureLookups.Flags = 1
    featureLookups.LookupConditionRecord = [
        _lookupVariationRecord(conditionB, [conditionalLookups[0]]),
        _lookupVariationRecord(conditionC, [conditionalLookups[1]]),
        _lookupVariationRecord(conditionD, [conditionalLookups[2]]),
    ]
    featureLookups.LookupConditionCount = len(featureLookups.LookupConditionRecord)

    lookupVariation = otTables.LookupVariationRecord()
    lookupVariation.FeatureIndex = featureIndices["liga"]
    lookupVariation.FeatureLookupsTable = featureLookups

    variations = otTables.FeatureVariations()
    variations.Version = 0x00010001
    variations.FeatureVariationRecord = []
    variations.FeatureVariationCount = 0
    variations.LookupVariationRecord = [lookupVariation]
    variations.LookupVariationCount = 1
    gsub.FeatureVariations = variations
    gsub.Version = 0x00010001

    if withVarStore:
        gdef = font["GDEF"] = ttLib.newTable("GDEF")
        gdef.table = otTables.GDEF()
        gdef.table.Version = 0x00010003
        gdef.table.GlyphClassDef = None
        gdef.table.AttachList = None
        gdef.table.LigCaretList = None
        gdef.table.MarkAttachClassDef = None
        gdef.table.MarkGlyphSetsDef = None
        regionList = builder.buildVarRegionList([{"wdth": (0, 1, 1)}], ["wght", "wdth"])
        gdef.table.VarStore = builder.buildVarStore(
            regionList, [builder.buildVarData([0], [[2]])]
        )

    return font


def makeFeatureVariationConditionsFont(format):
    font = makeLookupVariationsFont(withVarStore=True)
    variations = font["GSUB"].table.FeatureVariations
    records = variations.LookupVariationRecord[
        0
    ].FeatureLookupsTable.LookupConditionRecord
    lookupRecord = records[max(format - 3, 0)]
    condition = (
        _lookupVariationValueCondition(-1, 0)
        if format == 2
        else lookupRecord.ConditionTable
    )
    substitution = featureVars.buildFeatureTableSubstitutionRecord(
        0, lookupRecord.LookupIndexList.LookupIndex
    )
    variations.FeatureVariationRecord = [
        featureVars.buildFeatureVariationRecord([condition], [substitution])
    ]
    variations.FeatureVariationCount = 1
    variations.Version = 0x00010000
    del variations.LookupVariationRecord
    del variations.LookupVariationCount
    return font


def _getFeatureVariationSubstitutions(font, location):
    from fontTools.ttLib.ttGlyphSet import _evaluateCondition

    gsub = font["GSUB"].table
    axes = font["fvar"].axes if "fvar" in font else []
    store = getattr(font["GDEF"].table, "VarStore", None) if "GDEF" in font else None
    evaluator = varStore.VarStoreInstancer(store, axes, location)
    indices = set()
    gsub.collect_device_varidxes(indices)
    values = {index: [evaluator[index]] for index in indices}
    feature = gsub.FeatureList.FeatureRecord[0].Feature
    variations = getattr(gsub, "FeatureVariations", None)
    for record in getattr(variations, "FeatureVariationRecord", []):
        conditions = (
            record.ConditionSet.ConditionTable
            if record.ConditionSet is not None
            else []
        )
        if all(_evaluateCondition(c, axes, location, values) for c in conditions):
            feature = record.FeatureTableSubstitution.SubstitutionRecord[0].Feature
            break
    return _getSubstitutions(gsub, feature.LookupListIndex)


class InstantiateFeatureVariationsTest(object):
    @pytest.mark.parametrize("lookup_variations", [False, True])
    @pytest.mark.parametrize("table_tag", ["GSUB", "GPOS"])
    @pytest.mark.parametrize("partial", [False, True])
    def test_extended_layout_header(self, lookup_variations, table_tag, partial):
        from fontTools.ttLib.beyond64k import lower_tables, upper_tables
        from fontTools.misc.testTools import getXML

        if lookup_variations:
            font = makeLookupVariationsFont()
            location = {"wght": 0.3, "wdth": 0.8}
        else:
            font = makeFeatureVarsFont([([{"wght": (0.5, 1.0)}], {"a": "a.alt"})])
            location = {"wght": 0.75}
        if partial:
            location["wght"] = (0.25, 0.3, 0.75)
        if table_tag == "GPOS":
            variations = font["GSUB"].table.FeatureVariations
            base, conditional = ("A", "B") if lookup_variations else ("a", "a.alt")
            addOpenTypeFeaturesFromString(
                font,
                f"""
                lookup Default {{ pos {base} 10; }} Default;
                lookup Conditional {{ pos {conditional} 20; }} Conditional;
                feature kern {{ lookup Default; }} kern;
                feature zzzz {{ lookup Conditional; }} zzzz;
                """,
                tables=["GPOS"],
            )
            del font["GSUB"]
            font["GPOS"].table.FeatureVariations = variations
            font["GPOS"].table.Version = 0x00010001
            if lookup_variations:
                lookups = variations.LookupVariationRecord[0].FeatureLookupsTable
                lookups.LookupConditionRecord = [
                    _lookupVariationRecord(_lookupVariationCondition(0.25, 0.5), [1])
                ]
                lookups.LookupConditionCount = 1
            else:
                for record in variations.FeatureVariationRecord:
                    for (
                        substitution
                    ) in record.FeatureTableSubstitution.SubstitutionRecord:
                        substitution.Feature.LookupListIndex = [1]
                        substitution.Feature.LookupCount = 1
        reference = deepcopy(font)
        upper_tables(font, tables=[table_tag])

        for target in (reference, font):
            instancer.instantiateFeatureVariations(
                target, instancer.NormalizedAxisLimits(location)
            )
        assert font[table_tag].table.Version == 0x00010002
        assert (
            bool(getattr(font[table_tag].table, "FeatureVariations", None)) == partial
        )
        lower_tables(font, tables=[table_tag])
        assert getXML(font[table_tag].table.toXML, font) == getXML(
            reference[table_tag].table.toXML, reference
        )

    @pytest.mark.parametrize("tableTag", ["GSUB", "GPOS"])
    @pytest.mark.parametrize("legacy", [False, True])
    @pytest.mark.parametrize("wrapper", ["value", "and", "or", "not"])
    @pytest.mark.parametrize(
        "default,deltas,pinned,peak,tensor",
        [
            (0, [1, -1], 0.25, 1, False),
            (1, [-1, -1], 0.75, 1, False),
            (0, [1, -1], 0.25, 1, True),
            (32767, [1, -32768], 0.25, 1, False),
            (0, [1, -1], 0.25, 0.75, False),
        ],
    )
    def test_fractional_condition_remaining_variable(
        self, tableTag, legacy, wrapper, default, deltas, pinned, peak, tensor
    ):
        from fontTools.ttLib.ttGlyphSet import _evaluateCondition

        font = makeLookupVariationsFont(withVarStore=True)
        variations = font["GSUB"].table.FeatureVariations
        addOpenTypeFeaturesFromString(
            font,
            """
            lookup Default { pos A 10; } Default;
            lookup Conditional { pos B 20; } Conditional;
            feature kern { lookup Default; } kern;
            feature zzzz { lookup Conditional; } zzzz;
            """,
            tables=["GPOS"],
        )
        # A positioning value shares the condition's source variation row.
        position = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
        position.Value.XAdvDevice = builder.buildVarDevTable(0)
        position.ValueFormat |= 0x40
        if tableTag == "GPOS":
            del font["GSUB"]
            font["GPOS"].table.FeatureVariations = variations
            font["GPOS"].table.Version = 0x00010001
        region = {"wdth": (0, 1, 1)}
        if tensor:
            region["wght"] = (0, peak, 1)
        font["GDEF"].table.VarStore = builder.buildVarStore(
            builder.buildVarRegionList(
                [{"wght": (0, peak, 1)}, region], ["wght", "wdth"]
            ),
            [builder.buildVarData([0, 1], [deltas])],
        )
        value = _lookupVariationValueCondition(default, 0)
        if wrapper in ("and", "or"):
            condition = _lookupVariationCompoundCondition(
                3 if wrapper == "and" else 4, [value, value]
            )
        elif wrapper == "not":
            condition = otTables.ConditionTable()
            condition.Format = 5
            condition.ConditionTable = value
        else:
            condition = value
        if legacy:
            variations.Version = 0x00010000
            variations.FeatureVariationRecord = [
                featureVars.buildFeatureVariationRecord(
                    [condition],
                    [featureVars.buildFeatureTableSubstitutionRecord(0, [1])],
                )
            ]
            variations.FeatureVariationCount = 1
            del variations.LookupVariationRecord
            del variations.LookupVariationCount
        else:
            lookups = variations.LookupVariationRecord[0].FeatureLookupsTable
            lookups.LookupConditionRecord = [_lookupVariationRecord(condition, [1])]
            lookups.LookupConditionCount = 1

        original = deepcopy(font)
        instancer.instantiateVariableFont(font, {"wght": pinned}, inplace=True)
        # Exercise the serialized integer fields, not just the Python objects.
        for tag in ("GDEF", tableTag, "GPOS"):
            data = font[tag].compile(font)
            table = ttLib.newTable(tag)
            table.decompile(data, font)
            font[tag] = table

        variations = font[tableTag].table.FeatureVariations
        if legacy:
            condition = variations.FeatureVariationRecord[
                0
            ].ConditionSet.ConditionTable[0]
        else:
            condition = (
                variations.LookupVariationRecord[0]
                .FeatureLookupsTable.LookupConditionRecord[0]
                .ConditionTable
            )
        for coordinate in (
            0,
            0.125,
            0.25,
            0.33331298828125,
            0.3333740234375,
            0.5,
            16383 / 16384,
            1,
        ):
            sourceEvaluator = varStore.VarStoreInstancer(
                original["GDEF"].table.VarStore,
                original["fvar"].axes,
                {"wght": pinned, "wdth": coordinate},
            )
            evaluator = varStore.VarStoreInstancer(
                font["GDEF"].table.VarStore, font["fvar"].axes, {"wdth": coordinate}
            )
            indices = set()
            font[tableTag].table.collect_device_varidxes(indices)
            values = {index: [evaluator[index]] for index in indices}
            positive = default + sourceEvaluator[0] > 0
            expected = not positive if wrapper == "not" else positive
            assert (
                _evaluateCondition(
                    condition, font["fvar"].axes, {"wdth": coordinate}, values
                )
                == expected
            )
            if not tensor:
                position = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
                device = position.Value.XAdvDevice
                varIdx = (device.StartSize << 16) | device.EndSize
                assert evaluator[varIdx] == deltas[1] * coordinate
            if legacy and tableTag == "GSUB":
                full = instancer.instantiateVariableFont(font, {"wdth": coordinate})
                assert _getFeatureVariationSubstitutions(
                    full, {}
                ) == _getFeatureVariationSubstitutions(
                    original, {"wght": pinned, "wdth": coordinate}
                )

    @pytest.mark.parametrize("tableTag", ["GSUB", "GPOS"])
    @pytest.mark.parametrize("legacy", [False, True])
    @pytest.mark.parametrize("partial", [False, True])
    @pytest.mark.parametrize("wrapper", ["value", "and", "or", "not"])
    @pytest.mark.parametrize(
        "default,delta,coordinate",
        [
            (0, 1, 0.25),
            (1, -1, 0.75),
            (-1, 2, 0.51),
            (1, -2, 0.49),
            (0, 1, 0),
            (1, -1, 1),
            (-1, 2, 0.49),
            (0, -1, 0.25),
        ],
    )
    def test_fractional_condition_becoming_constant(
        self, tableTag, legacy, partial, wrapper, default, delta, coordinate
    ):
        from fontTools.ttLib.ttGlyphSet import _evaluateCondition

        font = makeLookupVariationsFont(withVarStore=True)
        variations = font["GSUB"].table.FeatureVariations
        if tableTag == "GPOS":
            addOpenTypeFeaturesFromString(
                font,
                """
                lookup Default { pos A 10; } Default;
                lookup Conditional { pos B 20; } Conditional;
                feature kern { lookup Default; } kern;
                feature zzzz { lookup Conditional; } zzzz;
                """,
                tables=["GPOS"],
            )
            del font["GSUB"]
            font["GPOS"].table.FeatureVariations = variations
            font["GPOS"].table.Version = 0x00010001
        font["GDEF"].table.VarStore.VarData[0].Item = [[delta]]
        value = _lookupVariationValueCondition(default, 0)
        if wrapper == "and":
            condition = _lookupVariationCompoundCondition(3, [value, value])
        elif wrapper == "or":
            condition = _lookupVariationCompoundCondition(
                4, [value, _lookupVariationValueCondition(0)]
            )
        elif wrapper == "not":
            condition = otTables.ConditionTable()
            condition.Format = 5
            condition.ConditionTable = value
        else:
            condition = value
        if legacy:
            variations.Version = 0x00010000
            variations.FeatureVariationRecord = [
                featureVars.buildFeatureVariationRecord(
                    [condition],
                    [featureVars.buildFeatureTableSubstitutionRecord(0, [1])],
                )
            ]
            variations.FeatureVariationCount = 1
            del variations.LookupVariationRecord
            del variations.LookupVariationCount
        else:
            featureLookups = variations.LookupVariationRecord[0].FeatureLookupsTable
            featureLookups.LookupConditionRecord = [
                _lookupVariationRecord(condition, [1])
            ]
            featureLookups.LookupConditionCount = 1

        limits = {"wdth": coordinate}
        if not partial:
            limits["wght"] = 0
        instancer.instantiateVariableFont(font, limits, inplace=True)
        table = font[tableTag].table
        font[tableTag].compile(font)
        axes = font["fvar"].axes if "fvar" in font else []
        active = list(table.FeatureList.FeatureRecord[0].Feature.LookupListIndex)
        variations = getattr(table, "FeatureVariations", None)
        for record in getattr(variations, "FeatureVariationRecord", []):
            conditions = (
                record.ConditionSet.ConditionTable
                if record.ConditionSet is not None
                else []
            )
            if all(_evaluateCondition(c, axes, {}, {}) for c in conditions):
                active = record.FeatureTableSubstitution.SubstitutionRecord[
                    0
                ].Feature.LookupListIndex
                break
        for record in getattr(variations, "LookupVariationRecord", []):
            for lookupCondition in record.FeatureLookupsTable.LookupConditionRecord:
                if _evaluateCondition(lookupCondition.ConditionTable, axes, {}, {}):
                    active.extend(lookupCondition.LookupIndexList.LookupIndex)

        positive = default + delta * coordinate > 0
        applies = not positive if wrapper == "not" else positive
        expected = {"B"} if legacy and applies else {"A", "B"} if applies else {"A"}
        affected = (
            set(_getSubstitutions(table, active))
            if tableTag == "GSUB"
            else {
                name
                for index in active
                for subtable in table.LookupList.Lookup[index].SubTable
                for name in subtable.Coverage.glyphs
            }
        )
        assert affected == expected

    @pytest.mark.parametrize("legacy", [False, True])
    @pytest.mark.parametrize("limits", [{"wght": 0.3}, {"wdth": (-0.5, 0.25, 1)}])
    def test_shared_conditions_remapped_once(self, legacy, limits):
        from fontTools.ttLib.ttGlyphSet import _evaluateCondition

        font = makeLookupVariationsFont()
        variations = font["GSUB"].table.FeatureVariations
        shared = _lookupVariationCondition(0.5, 1, 1)
        conditions = [
            _lookupVariationCompoundCondition(3, [shared, shared]),
            _lookupVariationCompoundCondition(4, [shared]),
        ]
        if legacy:
            variations.FeatureVariationRecord = [
                featureVars.buildFeatureVariationRecord(
                    [condition],
                    [featureVars.buildFeatureTableSubstitutionRecord(0, [index])],
                )
                for condition, index in zip(conditions, (1, 2))
            ]
            variations.FeatureVariationCount = 2
            variations.LookupVariationRecord = []
            variations.LookupVariationCount = 0
        else:
            lookups = variations.LookupVariationRecord[0].FeatureLookupsTable
            lookups.LookupConditionRecord = [
                _lookupVariationRecord(condition, [index])
                for condition, index in zip(conditions, (1, 2))
            ]
            lookups.LookupConditionCount = 2

        # Share a root across GSUB and GPOS, which are instanced in sequence.
        other = ttLib.TTFont()
        other.setGlyphOrder(font.getGlyphOrder())
        addOpenTypeFeaturesFromString(other, "feature kern { pos B 10; } kern;")
        font["GPOS"] = other["GPOS"]
        gpos = font["GPOS"].table
        gpos.Version = 0x00010001
        gpos.FeatureVariations = otTables.FeatureVariations()
        fv = gpos.FeatureVariations
        fv.Version = 0x00010000
        fv.FeatureVariationRecord = [
            featureVars.buildFeatureVariationRecord(
                [conditions[0]],
                [featureVars.buildFeatureTableSubstitutionRecord(0, [0])],
            )
        ]
        fv.FeatureVariationCount = 1
        original = deepcopy(font)

        instancer.instantiateVariableFont(font, limits, inplace=True)

        for tag in ("GSUB", "GPOS"):
            data = font[tag].compile(font)
            font[tag] = ttLib.newTable(tag)
            font[tag].decompile(data, font)
        if "wght" in limits:
            locations = [({"wdth": w}, {"wght": 0.3, "wdth": w}) for w in (0, 0.8)]
        else:
            locations = [({"wdth": w}, {"wdth": old}) for w, old in ((0, 0.25), (1, 1))]
        for location, oldLocation in locations:
            if legacy:
                assert _getFeatureVariationSubstitutions(font, location) == (
                    _getFeatureVariationSubstitutions(original, oldLocation)
                )
            else:
                records = (
                    font["GSUB"]
                    .table.FeatureVariations.LookupVariationRecord[0]
                    .FeatureLookupsTable.LookupConditionRecord
                )
                selected = [
                    r.LookupIndexList.LookupIndex[0]
                    for r in records
                    if _evaluateCondition(
                        r.ConditionTable, font["fvar"].axes, location, {}
                    )
                ]
                assert _getSubstitutions(font["GSUB"].table, selected) == (
                    {"B": "B.alt", "C": "C.alt"} if oldLocation["wdth"] >= 0.5 else {}
                )

    @pytest.mark.parametrize("earlierConditional", [False, True])
    @pytest.mark.parametrize("compound", [False, True])
    def test_partial_instance_preserves_universal_first_match(
        self, earlierConditional, compound
    ):
        font = makeLookupVariationsFont()
        variations = font["GSUB"].table.FeatureVariations
        variations.Version = 0x00010000
        del variations.LookupVariationRecord
        del variations.LookupVariationCount

        def record(condition, lookup):
            return featureVars.buildFeatureVariationRecord(
                [condition],
                [featureVars.buildFeatureTableSubstitutionRecord(0, [lookup])],
            )

        condition = _lookupVariationCondition(0.25, 1)
        if compound:
            condition = _lookupVariationCompoundCondition(3, [condition])
        records = [
            record(condition, 1),
            record(_lookupVariationCondition(0.5, 1, 1), 2),
        ]
        if earlierConditional:
            records.insert(0, record(_lookupVariationCondition(0.75, 1, 1), 3))
        variations.FeatureVariationRecord = records
        variations.FeatureVariationCount = len(records)
        original = deepcopy(font)

        instancer.instantiateVariableFont(font, {"wght": 0.3}, inplace=True)

        # A universal record must block later records, including after saving.
        compiled = font["GSUB"].compile(font)
        font["GSUB"] = ttLib.newTable("GSUB")
        font["GSUB"].decompile(compiled, font)
        for width in (-1, 0, 0.6, 0.8, 1):
            assert _getFeatureVariationSubstitutions(font, {"wdth": width}) == (
                _getFeatureVariationSubstitutions(
                    original, {"wght": 0.3, "wdth": width}
                )
            )

    @pytest.mark.parametrize("format", [2, 3, 4, 5])
    @pytest.mark.parametrize(
        "location", [(0, 0), (0.3, 0), (0.3, 0.8), (0.6, 0.8), (0, 0.8)]
    )
    def test_condition_formats_full_instance(self, format, location):
        font = makeFeatureVariationConditionsFont(format)
        location = dict(zip(("wght", "wdth"), location))
        expected = _getFeatureVariationSubstitutions(font, location)

        instancer.instantiateVariableFont(font, location, inplace=True)

        assert not hasattr(font["GSUB"].table, "FeatureVariations")
        assert _getFeatureVariationSubstitutions(font, {}) == expected
        font["GSUB"].compile(font)

    @pytest.mark.parametrize("format", [2, 3, 4, 5])
    @pytest.mark.parametrize(
        "pinned",
        [{"wght": 0}, {"wght": 0.3}, {"wght": 0.6}, {"wdth": 0}, {"wdth": 0.8}],
    )
    def test_condition_formats_partial_instance(self, format, pinned):
        font = makeFeatureVariationConditionsFont(format)
        original = deepcopy(font)
        remaining = "wdth" if "wght" in pinned else "wght"

        instancer.instantiateVariableFont(font, pinned, inplace=True)

        # Exercise serialization as well as the in-memory condition tree.
        compiled = font["GSUB"].compile(font)
        font["GSUB"] = ttLib.newTable("GSUB")
        font["GSUB"].decompile(compiled, font)
        for value in (-1, 0, 0.3, 0.6, 0.8, 1):
            assert _getFeatureVariationSubstitutions(font, {remaining: value}) == (
                _getFeatureVariationSubstitutions(
                    original, {**pinned, remaining: value}
                )
            )

    def test_condition_formats_first_matching_record(self):
        font = makeFeatureVariationConditionsFont(2)
        variations = font["GSUB"].table.FeatureVariations
        second = deepcopy(variations.FeatureVariationRecord[0])
        second.ConditionSet.ConditionTable[0].DefaultValue = 1
        # Use the other conditional substitution to distinguish the records.
        second.FeatureTableSubstitution.SubstitutionRecord[
            0
        ].Feature.LookupListIndex = [2]
        variations.FeatureVariationRecord.append(second)
        variations.FeatureVariationCount = 2
        original = deepcopy(font)

        instancer.instantiateVariableFont(font, {"wght": 0}, inplace=True)

        for width in (0, 0.3, 0.8, 1):
            assert _getFeatureVariationSubstitutions(font, {"wdth": width}) == (
                _getFeatureVariationSubstitutions(original, {"wght": 0, "wdth": width})
            )

    @pytest.mark.parametrize("format, expected", [(3, True), (4, True), (5, False)])
    def test_condition_formats_null_child(self, format, expected):
        font = makeFeatureVariationConditionsFont(3)
        condition = otTables.ConditionTable()
        condition.Format = format
        condition.ConditionTable = None if format == 5 else [None]
        if format != 5:
            condition.ConditionCount = 1
        font["GSUB"].table.FeatureVariations.FeatureVariationRecord[
            0
        ].ConditionSet.ConditionTable = [condition]

        instancer.instantiateVariableFont(font, {"wght": 0, "wdth": 0}, inplace=True)

        assert _getFeatureVariationSubstitutions(font, {}) == (
            {"B": "B.alt"} if expected else {"A": "A.alt"}
        )

    @pytest.mark.parametrize("format", [None, 3, 4, 5])
    def test_lookup_variations_null_condition(self, format):
        font = makeLookupVariationsFont(withVarStore=True)
        records = (
            font["GSUB"]
            .table.FeatureVariations.LookupVariationRecord[0]
            .FeatureLookupsTable.LookupConditionRecord
        )
        condition = None
        if format is not None:
            condition = otTables.ConditionTable()
            condition.Format = format
            condition.ConditionTable = None if format == 5 else [None]
        records[0].ConditionTable = condition
        instancer.instantiateLookupVariationConditionValues(font)
        instancer.instantiateVariableFont(font, {"wght": 0, "wdth": 0}, inplace=True)

        gsub = font["GSUB"].table
        assert not hasattr(gsub, "FeatureVariations")
        lookupIndices = gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex
        expected = {"A": "A.alt"}
        if format != 5:
            expected["B"] = "B.alt"
        assert _getSubstitutions(gsub, lookupIndices) == expected

    @pytest.mark.parametrize(
        "location, expected",
        [
            (
                {"wght": 0.3, "wdth": 0},
                {"A": "A.alt", "B": "B.alt", "D": "D.alt"},
            ),
            (
                {"wght": 0.3, "wdth": 0.8},
                {"A": "A.alt", "C": "C.alt", "D": "D.alt"},
            ),
        ],
    )
    def test_lookup_variations_full_instance(self, location, expected):
        font = makeLookupVariationsFont()

        instancer.instantiateFeatureVariations(
            font, instancer.NormalizedAxisLimits(location)
        )

        gsub = font["GSUB"].table
        assert not hasattr(gsub, "FeatureVariations")
        lookupIndices = gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex
        assert _getSubstitutions(gsub, lookupIndices) == expected

    def test_lookup_variations_partial_instance(self):
        font = makeLookupVariationsFont()

        instancer.instantiateFeatureVariations(
            font, instancer.NormalizedAxisLimits({"wght": 0.3})
        )

        variations = font["GSUB"].table.FeatureVariations
        assert variations.LookupVariationCount == 1
        conditionRecords = variations.LookupVariationRecord[
            0
        ].FeatureLookupsTable.LookupConditionRecord
        assert len(conditionRecords) == 3
        assert [record.ConditionTable.Format for record in conditionRecords] == [
            3,
            4,
            2,
        ]
        for record in conditionRecords[:2]:
            assert record.ConditionTable.ConditionCount == 1
            condition = record.ConditionTable.ConditionTable[0]
            assert condition.Format == 1
            assert condition.AxisIndex == 0

    def test_lookup_variations_full_instance_does_not_modify_shared_feature(self):
        font = makeLookupVariationsFont()
        featureList = font["GSUB"].table.FeatureList
        sharedFeature = featureList.FeatureRecord[0].Feature
        featureRecord = otTables.FeatureRecord()
        featureRecord.FeatureTag = "test"
        featureRecord.Feature = sharedFeature
        featureList.FeatureRecord.append(featureRecord)
        featureList.FeatureCount += 1

        instancer.instantiateFeatureVariations(
            font, instancer.NormalizedAxisLimits({"wght": 0.3, "wdth": 0})
        )

        assert featureList.FeatureRecord[0].Feature is not sharedFeature
        assert featureList.FeatureRecord[1].Feature is sharedFeature
        assert _getSubstitutions(font["GSUB"].table, sharedFeature.LookupListIndex) == {
            "A": "A.alt"
        }

    def test_lookup_variations_full_instance_replaces_default_lookups(self):
        font = makeLookupVariationsFont()
        featureLookups = (
            font["GSUB"]
            .table.FeatureVariations.LookupVariationRecord[0]
            .FeatureLookupsTable
        )
        featureLookups.Flags = 0

        instancer.instantiateFeatureVariations(
            font, instancer.NormalizedAxisLimits({"wght": 0.3, "wdth": 0})
        )

        gsub = font["GSUB"].table
        lookupIndices = gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex
        assert _getSubstitutions(gsub, lookupIndices) == {
            "B": "B.alt",
            "D": "D.alt",
        }

    def test_lookup_variations_use_current_feature_lookups(self):
        font = makeLookupVariationsFont()
        gsub = font["GSUB"].table
        variations = gsub.FeatureVariations
        lookupVariation = variations.LookupVariationRecord[0]
        conditionalC = lookupVariation.FeatureLookupsTable.LookupConditionRecord[
            1
        ].LookupIndexList.LookupIndex
        substitution = featureVars.buildFeatureTableSubstitutionRecord(
            lookupVariation.FeatureIndex, conditionalC
        )
        variations.FeatureVariationRecord = [
            featureVars.buildFeatureVariationRecord(
                [_lookupVariationCondition(0.25, 1.0)], [substitution]
            )
        ]
        variations.FeatureVariationCount = 1

        instancer.instantiateFeatureVariations(
            font, instancer.NormalizedAxisLimits({"wght": 0.3, "wdth": 0})
        )

        assert not hasattr(gsub, "FeatureVariations")
        lookupIndices = gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex
        assert _getSubstitutions(gsub, lookupIndices) == {
            "B": "B.alt",
            "C": "C.alt",
            "D": "D.alt",
        }

    def test_lookup_variations_condition_value_partial_instance(self):
        font = makeLookupVariationsFont(withVarStore=True)

        instancer.instantiateVariableFont(font, {"wght": 0.3}, inplace=True)

        variations = font["GSUB"].table.FeatureVariations
        conditionRecords = variations.LookupVariationRecord[
            0
        ].FeatureLookupsTable.LookupConditionRecord
        valueCondition = conditionRecords[1].ConditionTable.ConditionTable[0]
        assert valueCondition.Format == 2
        assert valueCondition.DefaultValue == -1
        assert valueCondition.VarIdx == 0
        font["GDEF"].compile(font)
        font["GSUB"].compile(font)

    def test_lookup_variations_condition_value_bakes_delta(self):
        font = makeLookupVariationsFont(withVarStore=True)

        instancer.instantiateVariableFont(font, {"wdth": 0.8}, inplace=True)

        variations = font["GSUB"].table.FeatureVariations
        featureLookups = variations.LookupVariationRecord[0].FeatureLookupsTable
        assert featureLookups.LookupConditionCount == 2
        condition = featureLookups.LookupConditionRecord[0].ConditionTable
        assert condition.Format == 2
        assert condition.DefaultValue == 1
        assert condition.VarIdx == otTables.NO_VARIATION_INDEX

    def test_lookup_variations_condition_value_full_instance(self):
        font = makeLookupVariationsFont(withVarStore=True)

        instancer.instantiateVariableFont(
            font, {"wght": 0.3, "wdth": 0.8}, inplace=True
        )

        gsub = font["GSUB"].table
        assert not hasattr(gsub, "FeatureVariations")
        lookupIndices = gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex
        assert _getSubstitutions(gsub, lookupIndices) == {
            "A": "A.alt",
            "C": "C.alt",
            "D": "D.alt",
        }

    @pytest.mark.parametrize("pinned_axis", ["wght", "wdth"])
    def test_partial_instance_preserves_rule_substitutions(self, pinned_axis):
        fb = FontBuilder(1000)
        order = [".notdef", "dollar", "dollar.nostroke", "A", "a"]
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap({0x24: "dollar", 0x41: "A", 0x61: "a"})
        fb.setupGlyf({name: TTGlyphPen(None).glyph() for name in order})
        fb.setupHorizontalMetrics({name: (500, 0) for name in order})
        fb.setupHorizontalHeader()
        fb.setupNameTable({"familyName": "Rules", "styleName": "Regular"})
        fb.setupOS2()
        fb.setupPost()
        fb.setupFvar(
            [
                ("wght", 100, 400, 900, "Weight"),
                ("wdth", 50, 100, 200, "Width"),
            ],
            [],
        )
        featureVars.addFeatureVariations(
            fb.font,
            [
                ([{"wght": (0.2, 1)}], {"dollar": "dollar.nostroke"}),
                ([{"wdth": (0.75, 1)}], {"A": "a"}),
            ],
        )

        def roundtrip(font):
            stream = BytesIO()
            font.save(stream)
            stream.seek(0)
            return ttLib.TTFont(stream)

        def substitutions(font, location):
            gsub = font["GSUB"].table
            feature = gsub.FeatureList.FeatureRecord[0].Feature
            axes = [axis.axisTag for axis in font["fvar"].axes]
            variations = getattr(gsub, "FeatureVariations", None)
            for record in variations.FeatureVariationRecord if variations else []:
                conditions = (
                    record.ConditionSet.ConditionTable if record.ConditionSet else []
                )
                if all(
                    condition.FilterRangeMinValue
                    <= location.get(axes[condition.AxisIndex], 0)
                    <= condition.FilterRangeMaxValue
                    for condition in conditions
                ):
                    feature = record.FeatureTableSubstitution.SubstitutionRecord[
                        0
                    ].Feature
                    break
            return _getSubstitutions(gsub, feature.LookupListIndex)

        original = roundtrip(fb.font)
        partial = roundtrip(
            instancer.instantiateVariableFont(
                original, {pinned_axis: 900 if pinned_axis == "wght" else 200}
            )
        )
        remaining_axis = "wdth" if pinned_axis == "wght" else "wght"
        for value in (-1, 0, 0.5, 0.8, 1):
            assert substitutions(partial, {remaining_axis: value}) == substitutions(
                original, {pinned_axis: 1, remaining_axis: value}
            )

    @pytest.mark.parametrize(
        "location, appliedSubs, expectedRecords",
        [
            ({"wght": 0}, {}, [({"cntr": (0.75, 1.0)}, {"uni0041": "uni0061"})]),
            (
                {"wght": -1.0},
                {"uni0061": "uni0041"},
                [
                    ({"cntr": (0, 0.25)}, {"uni0061": "uni0041"}),
                    ({"cntr": (0.75, 1.0)}, {"uni0041": "uni0061"}),
                    ({}, {}),
                ],
            ),
            (
                {"wght": 1.0},
                {"uni0024": "uni0024.nostroke"},
                [
                    (
                        {"cntr": (0.75, 1.0)},
                        {"uni0024": "uni0024.nostroke", "uni0041": "uni0061"},
                    ),
                    ({}, {"uni0024": "uni0024.nostroke"}),
                ],
            ),
            (
                {"cntr": 0},
                {},
                [
                    ({"wght": (-1.0, -0.45654)}, {"uni0061": "uni0041"}),
                    ({"wght": (0.20886, 1.0)}, {"uni0024": "uni0024.nostroke"}),
                ],
            ),
            (
                {"cntr": 1.0},
                {"uni0041": "uni0061"},
                [
                    (
                        {"wght": (0.20886, 1.0)},
                        {"uni0024": "uni0024.nostroke", "uni0041": "uni0061"},
                    ),
                    ({}, {"uni0041": "uni0061"}),
                ],
            ),
            (
                {"cntr": (-0.5, 0, 1.0)},
                {},
                [
                    (
                        {"wght": (0.20886, 1.0), "cntr": (0.75, 1)},
                        {"uni0024": "uni0024.nostroke", "uni0041": "uni0061"},
                    ),
                    (
                        {"wght": (-1.0, -0.45654), "cntr": (0, 0.25)},
                        {"uni0061": "uni0041"},
                    ),
                    (
                        {"cntr": (0.75, 1.0)},
                        {"uni0041": "uni0061"},
                    ),
                    (
                        {"wght": (0.20886, 1.0)},
                        {"uni0024": "uni0024.nostroke"},
                    ),
                ],
            ),
            (
                {"cntr": (0.8, 0.9, 1.0)},
                {"uni0041": "uni0061"},
                [
                    (
                        {"wght": (0.20886, 1.0)},
                        {"uni0024": "uni0024.nostroke", "uni0041": "uni0061"},
                    ),
                    (
                        {},
                        {"uni0041": "uni0061"},
                    ),
                ],
            ),
            (
                {"cntr": (0.7, 0.9, 1.0)},
                {"uni0041": "uni0061"},
                [
                    (
                        {"cntr": (-0.7499999999999999, 1.0), "wght": (0.20886, 1.0)},
                        {"uni0024": "uni0024.nostroke", "uni0041": "uni0061"},
                    ),
                    (
                        {"cntr": (-0.7499999999999999, 1.0)},
                        {"uni0041": "uni0061"},
                    ),
                    (
                        {"wght": (0.20886, 1.0)},
                        {"uni0024": "uni0024.nostroke"},
                    ),
                    (
                        {},
                        {},
                    ),
                ],
            ),
        ],
    )
    def test_partial_instance(self, location, appliedSubs, expectedRecords):
        font = makeFeatureVarsFont(
            [
                ([{"wght": (0.20886, 1.0)}], {"uni0024": "uni0024.nostroke"}),
                ([{"cntr": (0.75, 1.0)}], {"uni0041": "uni0061"}),
                (
                    [{"wght": (-1.0, -0.45654), "cntr": (0, 0.25)}],
                    {"uni0061": "uni0041"},
                ),
            ]
        )

        limits = instancer.NormalizedAxisLimits(location)
        instancer.instantiateFeatureVariations(font, limits)

        gsub = font["GSUB"].table
        featureVariations = gsub.FeatureVariations

        assert featureVariations.FeatureVariationCount == len(expectedRecords)

        axisOrder = [
            a.axisTag
            for a in font["fvar"].axes
            if a.axisTag not in location or isinstance(location[a.axisTag], tuple)
        ]
        for i, (expectedConditionSet, expectedSubs) in enumerate(expectedRecords):
            rec = featureVariations.FeatureVariationRecord[i]
            conditionSet = _conditionSetAsDict(rec.ConditionSet, axisOrder)

            assert conditionSet == expectedConditionSet, i

            subsRecord = rec.FeatureTableSubstitution.SubstitutionRecord[0]
            lookupIndices = subsRecord.Feature.LookupListIndex
            substitutions = _getSubstitutions(gsub, lookupIndices)

            assert substitutions == expectedSubs, i

        appliedLookupIndices = gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex

        assert _getSubstitutions(gsub, appliedLookupIndices) == appliedSubs

    @pytest.mark.parametrize(
        "location, appliedSubs",
        [
            ({"wght": 0, "cntr": 0}, None),
            ({"wght": -1.0, "cntr": 0}, {"uni0061": "uni0041"}),
            ({"wght": 1.0, "cntr": 0}, {"uni0024": "uni0024.nostroke"}),
            ({"wght": 0.0, "cntr": 1.0}, {"uni0041": "uni0061"}),
            (
                {"wght": 1.0, "cntr": 1.0},
                {"uni0041": "uni0061", "uni0024": "uni0024.nostroke"},
            ),
            ({"wght": -1.0, "cntr": 0.3}, None),
        ],
    )
    def test_full_instance(self, location, appliedSubs):
        font = makeFeatureVarsFont(
            [
                ([{"wght": (0.20886, 1.0)}], {"uni0024": "uni0024.nostroke"}),
                ([{"cntr": (0.75, 1.0)}], {"uni0041": "uni0061"}),
                (
                    [{"wght": (-1.0, -0.45654), "cntr": (0, 0.25)}],
                    {"uni0061": "uni0041"},
                ),
            ]
        )
        gsub = font["GSUB"].table
        assert gsub.FeatureVariations
        assert gsub.Version == 0x00010001

        location = instancer.NormalizedAxisLimits(location)

        instancer.instantiateFeatureVariations(font, location)

        assert not hasattr(gsub, "FeatureVariations")
        assert gsub.Version == 0x00010000

        if appliedSubs:
            lookupIndices = gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex
            assert _getSubstitutions(gsub, lookupIndices) == appliedSubs
        else:
            assert not gsub.FeatureList.FeatureRecord

    @pytest.mark.parametrize("null_conditionset", [False, True])
    def test_null_conditionset(self, null_conditionset):
        # A null ConditionSet offset should be treated like an empty ConditionTable, i.e.
        # all contexts are matched; see https://github.com/fonttools/fonttools/issues/3211
        font = makeFeatureVarsFont(
            [([{"wght": (-1.0, 1.0)}], {"uni0024": "uni0024.nostroke"})]
        )
        gsub = font["GSUB"].table
        record = gsub.FeatureVariations.FeatureVariationRecord[0]
        if null_conditionset:
            record.ConditionSet = None
        else:
            record.ConditionSet = otTables.ConditionSet()
            record.ConditionSet.ConditionTable = [None]
            record.ConditionSet.ConditionCount = 1

        location = instancer.NormalizedAxisLimits({"wght": 0.5})
        instancer.instantiateFeatureVariations(font, location)

        assert not hasattr(gsub, "FeatureVariations")
        assert gsub.Version == 0x00010000

        lookupIndices = gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex
        assert _getSubstitutions(gsub, lookupIndices) == {"uni0024": "uni0024.nostroke"}

    @pytest.mark.parametrize("explicit_empty", [False, True])
    @pytest.mark.parametrize("lazy", [False, True])
    @pytest.mark.parametrize(
        "partial, coordinate, expected",
        [
            (False, 0, {"A.alt": "A"}),
            (False, 0.375, {"A": "A.alt"}),
            (False, 0.75, {"A.alt": "A"}),
            (True, -0.5, {"A.alt": "A"}),
            (True, -0.25, {"A": "A.alt"}),
            (True, 0, {"A.alt": "A"}),
            (True, 0.5, {"A.alt": "A"}),
        ],
    )
    def test_null_substitution(
        self, explicit_empty, lazy, partial, coordinate, expected
    ):
        font = makeFeatureVarsFont([([{"wght": (0.25, 1.0)}], {"A": "A.alt"})])
        gsub = font["GSUB"].table
        featureVars.buildSubstitutionLookups(
            gsub, [(("A.alt", "A"),)], processLast=True
        )
        feature = gsub.FeatureList.FeatureRecord[0].Feature
        feature.LookupListIndex = [1]
        feature.LookupCount = 1
        first = deepcopy(gsub.FeatureVariations.FeatureVariationRecord[0])
        first.ConditionSet.ConditionTable[0].FilterRangeMinValue = 0.5
        if explicit_empty:
            first.FeatureTableSubstitution.SubstitutionRecord = []
            first.FeatureTableSubstitution.SubstitutionCount = 0
        else:
            first.FeatureTableSubstitution = None
        gsub.FeatureVariations.FeatureVariationRecord.insert(0, first)
        gsub.FeatureVariations.FeatureVariationCount = 2
        data = font["GSUB"].compile(font)
        font.lazy = lazy
        font["GSUB"] = ttLib.newTable("GSUB")
        font["GSUB"].decompile(data, font)

        if partial:
            instancer.instantiateFeatureVariations(
                font, instancer.NormalizedAxisLimits({"wght": (-1, 0.75, 1)})
            )
            gsub = font["GSUB"].table
            assert gsub.FeatureVariations.FeatureVariationCount == 2
            first = gsub.FeatureVariations.FeatureVariationRecord[0]
            if explicit_empty:
                assert first.FeatureTableSubstitution.SubstitutionCount == 0
            else:
                assert first.FeatureTableSubstitution is None
            data = font["GSUB"].compile(font)
            font["GSUB"] = ttLib.newTable("GSUB")
            font["GSUB"].decompile(data, font)

        instancer.instantiateFeatureVariations(
            font, instancer.NormalizedAxisLimits({"wght": coordinate})
        )
        gsub = font["GSUB"].table
        assert not hasattr(gsub, "FeatureVariations")
        indices = gsub.FeatureList.FeatureRecord[0].Feature.LookupListIndex
        assert _getSubstitutions(gsub, indices) == expected

    @pytest.mark.parametrize("full_font", [False, True])
    @pytest.mark.parametrize("partial", [False, True])
    def test_unsupported_condition_format(self, full_font, partial):
        fb = FontBuilder(1000)
        order = [".notdef", "dollar", "dollar.nostroke"]
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap({0x24: "dollar"})
        fb.setupGlyf({name: TTGlyphPen(None).glyph() for name in order})
        fb.setupHorizontalMetrics({name: (500, 0) for name in order})
        fb.setupHorizontalHeader()
        fb.setupNameTable({"familyName": "Conditions", "styleName": "Regular"})
        fb.setupOS2()
        fb.setupPost()
        fb.setupFvar(
            [("wght", 100, 400, 900, "Weight"), ("wdth", 50, 100, 200, "Width")],
            [],
        )
        font = fb.font
        featureVars.addFeatureVariations(
            font, [([{"wght": (0.5, 1.0)}], {"dollar": "dollar.nostroke"})]
        )
        record = font["GSUB"].table.FeatureVariations.FeatureVariationRecord[0]
        condition = record.ConditionSet.ConditionTable[0]
        condition.Format = 99

        with pytest.raises(
            NotImplementedError, match="GSUB FeatureVariations condition format 99"
        ):
            if full_font:
                location = {"wght": 900} if partial else {"wght": 900, "wdth": 70}
                instancer.instantiateVariableFont(font, location, inplace=True)
            else:
                location = {"wght": 1} if partial else {"wght": 1, "wdth": -1}
                instancer.instantiateFeatureVariations(
                    font, instancer.NormalizedAxisLimits(location)
                )

        # Rejection happens before either entry point starts mutating the font.
        assert font["GSUB"].table.FeatureVariations.FeatureVariationRecord[0] is record
        assert record.ConditionSet.ConditionTable == [condition]
        assert condition.Format == 99

    def test_GSUB_FeatureVariations_is_None(self, varfont2):
        varfont2["GSUB"].table.Version = 0x00010001
        varfont2["GSUB"].table.FeatureVariations = None
        tmp = BytesIO()
        varfont2.save(tmp)
        varfont = ttLib.TTFont(tmp)

        # DO NOT raise an exception when the optional 'FeatureVariations' attribute is
        # present but is set to None (e.g. with GSUB 1.1); skip and do nothing.
        assert varfont["GSUB"].table.FeatureVariations is None
        instancer.instantiateFeatureVariations(varfont, {"wght": 400, "wdth": 100})
        assert varfont["GSUB"].table.FeatureVariations is None


class LimitTupleVariationAxisRangesTest:
    def check_limit_single_var_axis_range(self, var, axisTag, axisRange, expected):
        result = instancer.changeTupleVariationAxisLimit(var, axisTag, axisRange)
        print(result)

        assert len(result) == len(expected)
        for v1, v2 in zip(result, expected):
            assert v1.coordinates == pytest.approx(v2.coordinates)
            assert v1.axes.keys() == v2.axes.keys()
            for k in v1.axes:
                p, q = v1.axes[k], v2.axes[k]
                assert p == pytest.approx(q)

    @pytest.mark.parametrize(
        "var, axisTag, newMax, expected",
        [
            (
                TupleVariation({"wght": (0.0, 1.0, 1.0)}, [100, 100]),
                "wdth",
                0.5,
                [TupleVariation({"wght": (0.0, 1.0, 1.0)}, [100, 100])],
            ),
            (
                TupleVariation({"wght": (0.0, 1.0, 1.0)}, [100, 100]),
                "wght",
                0.5,
                [TupleVariation({"wght": (0.0, 1.0, 1.0)}, [50, 50])],
            ),
            (
                TupleVariation({"wght": (0.0, 1.0, 1.0)}, [100, 100]),
                "wght",
                0.8,
                [TupleVariation({"wght": (0.0, 1.0, 1.0)}, [80, 80])],
            ),
            (
                TupleVariation({"wght": (0.0, 1.0, 1.0)}, [100, 100]),
                "wght",
                1.0,
                [TupleVariation({"wght": (0.0, 1.0, 1.0)}, [100, 100])],
            ),
            (TupleVariation({"wght": (0.0, 1.0, 1.0)}, [100, 100]), "wght", 0.0, []),
            (TupleVariation({"wght": (0.5, 1.0, 1.0)}, [100, 100]), "wght", 0.4, []),
            (
                TupleVariation({"wght": (0.0, 0.5, 1.0)}, [100, 100]),
                "wght",
                0.5,
                [TupleVariation({"wght": (0.0, 1.0, 1.0)}, [100, 100])],
            ),
            (
                TupleVariation({"wght": (0.0, 0.5, 1.0)}, [100, 100]),
                "wght",
                0.4,
                [TupleVariation({"wght": (0.0, 1.0, 1.0)}, [80, 80])],
            ),
            (
                TupleVariation({"wght": (0.0, 0.5, 1.0)}, [100, 100]),
                "wght",
                0.6,
                [
                    TupleVariation({"wght": (0.0, 0.833334, 1.0)}, [100, 100]),
                    TupleVariation({"wght": (0.833334, 1.0, 1.0)}, [80, 80]),
                ],
            ),
            (
                TupleVariation({"wght": (0.0, 0.2, 1.0)}, [100, 100]),
                "wght",
                0.4,
                [
                    TupleVariation({"wght": (0.0, 0.5, 1.0)}, [100, 100]),
                    TupleVariation({"wght": (0.5, 1.0, 1.0)}, [75, 75]),
                ],
            ),
            (
                TupleVariation({"wght": (0.0, 0.2, 1.0)}, [100, 100]),
                "wght",
                0.5,
                [
                    TupleVariation({"wght": (0.0, 0.4, 1)}, [100, 100]),
                    TupleVariation({"wght": (0.4, 1, 1)}, [62.5, 62.5]),
                ],
            ),
            (
                TupleVariation({"wght": (0.5, 0.5, 1.0)}, [100, 100]),
                "wght",
                0.5,
                [TupleVariation({"wght": (1.0, 1.0, 1.0)}, [100, 100])],
            ),
            # test case from https://github.com/fonttools/fonttools/issues/3453
            (
                TupleVariation(
                    {
                        "wght": (0.0, 1.0, 1.0),
                        "ital": (0.0, 0.0, 1.0),  # no-op axis gets dropped
                    },
                    [100, 100],
                ),
                "ital",
                0.0,
                [TupleVariation({"wght": (0.0, 1.0, 1.0)}, [100, 100])],
            ),
        ],
    )
    def test_positive_var(self, var, axisTag, newMax, expected):
        axisRange = instancer.NormalizedAxisTripleAndDistances(0, 0, newMax)
        self.check_limit_single_var_axis_range(var, axisTag, axisRange, expected)

    @pytest.mark.parametrize(
        "var, axisTag, newMin, expected",
        [
            (
                TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [100, 100]),
                "wdth",
                -0.5,
                [TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [100, 100])],
            ),
            (
                TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [100, 100]),
                "wght",
                -0.5,
                [TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [50, 50])],
            ),
            (
                TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [100, 100]),
                "wght",
                -0.8,
                [TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [80, 80])],
            ),
            (
                TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [100, 100]),
                "wght",
                -1.0,
                [TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [100, 100])],
            ),
            (TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [100, 100]), "wght", 0.0, []),
            (
                TupleVariation({"wght": (-1.0, -1.0, -0.5)}, [100, 100]),
                "wght",
                -0.4,
                [],
            ),
            (
                TupleVariation({"wght": (-1.0, -0.5, 0.0)}, [100, 100]),
                "wght",
                -0.5,
                [TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [100, 100])],
            ),
            (
                TupleVariation({"wght": (-1.0, -0.5, 0.0)}, [100, 100]),
                "wght",
                -0.4,
                [TupleVariation({"wght": (-1.0, -1.0, 0.0)}, [80, 80])],
            ),
            (
                TupleVariation({"wght": (-1.0, -0.5, 0.0)}, [100, 100]),
                "wght",
                -0.6,
                [
                    TupleVariation({"wght": (-1.0, -0.833334, 0.0)}, [100, 100]),
                    TupleVariation({"wght": (-1.0, -1.0, -0.833334)}, [80, 80]),
                ],
            ),
            (
                TupleVariation({"wght": (-1.0, -0.2, 0.0)}, [100, 100]),
                "wght",
                -0.4,
                [
                    TupleVariation({"wght": (-1.0, -0.5, -0.0)}, [100, 100]),
                    TupleVariation({"wght": (-1.0, -1.0, -0.5)}, [75, 75]),
                ],
            ),
            (
                TupleVariation({"wght": (-1.0, -0.2, 0.0)}, [100, 100]),
                "wght",
                -0.5,
                [
                    TupleVariation({"wght": (-1.0, -0.4, 0.0)}, [100, 100]),
                    TupleVariation({"wght": (-1.0, -1.0, -0.4)}, [62.5, 62.5]),
                ],
            ),
            (
                TupleVariation({"wght": (-1.0, -0.5, -0.5)}, [100, 100]),
                "wght",
                -0.5,
                [TupleVariation({"wght": (-1.0, -1.0, -1.0)}, [100, 100])],
            ),
        ],
    )
    def test_negative_var(self, var, axisTag, newMin, expected):
        axisRange = instancer.NormalizedAxisTripleAndDistances(newMin, 0, 0, 1, 1)
        self.check_limit_single_var_axis_range(var, axisTag, axisRange, expected)


@pytest.mark.parametrize(
    "oldRange, newLimit, expected",
    [
        ((1.0, -1.0), (-1.0, 0, 1.0), None),  # invalid oldRange min > max
        ((0.6, 1.0), (0, 0, 0.5), None),
        ((-1.0, -0.6), (-0.5, 0, 0), None),
        ((0.4, 1.0), (0, 0, 0.5), (0.8, 1.0)),
        ((-1.0, -0.4), (-0.5, 0, 0), (-1.0, -0.8)),
        ((0.4, 1.0), (0, 0, 0.4), (1.0, 1.0)),
        ((-1.0, -0.4), (-0.4, 0, 0), (-1.0, -1.0)),
        ((-0.5, 0.5), (-0.4, 0, 0.4), (-1.0, 1.0)),
        ((0, 1.0), (-1.0, 0, 0), (0, 0)),  # or None?
        ((-1.0, 0), (0, 0, 1.0), (0, 0)),  # or None?
    ],
)
def test_limitFeatureVariationConditionRange(oldRange, newLimit, expected):
    condition = featureVars.buildConditionTable(0, *oldRange)

    result = instancer.featureVars._limitFeatureVariationConditionRange(
        condition, instancer.NormalizedAxisTripleAndDistances(*newLimit, 1, 1)
    )

    assert result == expected


@pytest.mark.parametrize(
    "limits, expected",
    [
        (["wght=400", "wdth=100"], {"wght": 400, "wdth": 100}),
        (["wght=400:900"], {"wght": (400, 900)}),
        (["wght=400:700:900"], {"wght": (400, 700, 900)}),
        (["slnt=11.4"], {"slnt": 11.399994}),
        (["ABCD=drop"], {"ABCD": None}),
        (["wght=:500:"], {"wght": (None, 500, None)}),
        (["wght=::700"], {"wght": (None, None, 700)}),
        (["wght=200::"], {"wght": (200, None, None)}),
        (["wght=200:300:"], {"wght": (200, 300, None)}),
        (["wght=:300:500"], {"wght": (None, 300, 500)}),
        (["wght=300::700"], {"wght": (300, None, 700)}),
        (["wght=300:700"], {"wght": (300, None, 700)}),
        (["wght=:700"], {"wght": (None, None, 700)}),
        (["wght=200:"], {"wght": (200, None, None)}),
    ],
)
def test_parseLimits(limits, expected):
    limits = instancer.parseLimits(limits)
    expected = instancer.AxisLimits(expected)

    assert limits.keys() == expected.keys()
    for axis, triple in limits.items():
        expected_triple = expected[axis]
        if expected_triple is None:
            assert triple is None
        else:
            assert isinstance(triple, instancer.AxisTriple)
            assert isinstance(expected_triple, instancer.AxisTriple)
            assert triple == pytest.approx(expected_triple)


@pytest.mark.parametrize(
    "limits", [["abcde=123", "=0", "wght=:", "wght=1:", "wght=abcd", "wght=x:y"]]
)
def test_parseLimits_invalid(limits):
    with pytest.raises(ValueError, match="invalid location format"):
        instancer.parseLimits(limits)


@pytest.mark.parametrize(
    "limits, expected",
    [
        # 300, 500 come from the font having 100,400,900 fvar axis limits.
        ({"wght": (100, 400)}, {"wght": (-1.0, 0, 0, 300, 500)}),
        ({"wght": (100, 400, 400)}, {"wght": (-1.0, 0, 0, 300, 500)}),
        ({"wght": (100, 300, 400)}, {"wght": (-1.0, -0.5, 0, 300, 500)}),
    ],
)
def test_normalizeAxisLimits(varfont, limits, expected):
    limits = instancer.AxisLimits(limits)

    normalized = limits.normalize(varfont)

    assert normalized == instancer.NormalizedAxisLimits(expected)


def test_normalizeAxisLimits_no_avar(varfont):
    del varfont["avar"]

    limits = instancer.AxisLimits(wght=(400, 400, 500))
    normalized = limits.normalize(varfont)

    assert normalized["wght"] == pytest.approx((0, 0, 0.2, 300, 500), 1e-4)


def test_normalizeAxisLimits_missing_from_fvar(varfont):
    with pytest.raises(ValueError, match="not present in fvar"):
        instancer.AxisLimits({"ZZZZ": 1000}).normalize(varfont)


def test_normalizeAxisLimits_quantizes_after_avar_map(varfont):
    # The F2Dot14 quantization must be applied AFTER the avar v1 mapping (and
    # only there), like a shaping engine does: normalize -> map -> quantize.
    # Pinning wght=650 on a 100/400/900 axis through this map yields
    # 5/7 * 0.2 = 0.142857..., which is not F2Dot14-representable; the
    # normalized location must land on the quantized 0.14288330078125.
    varfont["avar"].segments["wght"] = {-1.0: -1.0, 0.0: 0.0, 0.7: 0.2, 1.0: 1.0}

    normalized = instancer.AxisLimits({"wght": 650}).normalize(varfont)

    for v in tuple(normalized["wght"])[:3]:
        assert v == floatToFixedToFloat(v, 14)
    assert normalized["wght"].default == 0.14288330078125


def test_sanityCheckVariableTables(varfont):
    font = ttLib.TTFont()
    with pytest.raises(ValueError, match="Missing required table fvar"):
        instancer.sanityCheckVariableTables(font)

    del varfont["glyf"]

    with pytest.raises(ValueError, match="Can't have gvar without glyf"):
        instancer.sanityCheckVariableTables(varfont)


def test_main(varfont, tmpdir):
    fontfile = str(tmpdir / "PartialInstancerTest-VF.ttf")
    varfont.save(fontfile)
    args = [fontfile, "wght=400"]

    # exits without errors
    assert instancer.main(args) is None


def test_main_missing_fvar(tmpdir):
    font = ttLib.TTFont()
    font.importXML(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "ttLib",
            "data",
            "TestTTF-Regular.ttx",
        )
    )
    fontfile = str(tmpdir / "static.ttf")
    font.save(fontfile)

    with pytest.raises(ValueError, match="Missing required table fvar"):
        instancer.main([fontfile])


def test_main_exit_nonexistent_file(capsys):
    with pytest.raises(SystemExit):
        instancer.main([""])
    captured = capsys.readouterr()

    assert "No such file ''" in captured.err


def test_main_exit_invalid_location(varfont, tmpdir, capsys):
    fontfile = str(tmpdir / "PartialInstancerTest-VF.ttf")
    varfont.save(fontfile)

    with pytest.raises(SystemExit):
        instancer.main([fontfile, "wght:100"])
    captured = capsys.readouterr()

    assert "invalid location format" in captured.err


def test_main_exit_multiple_limits(varfont, tmpdir, capsys):
    fontfile = str(tmpdir / "PartialInstancerTest-VF.ttf")
    varfont.save(fontfile)

    with pytest.raises(SystemExit):
        instancer.main([fontfile, "wght=400", "wght=90"])
    captured = capsys.readouterr()

    assert "Specified multiple limits for the same axis" in captured.err


def test_set_ribbi_bits():
    varfont = ttLib.TTFont()
    varfont.importXML(os.path.join(TESTDATA, "STATInstancerTest.ttx"))

    for location in [instance.coordinates for instance in varfont["fvar"].instances]:
        instance = instancer.instantiateVariableFont(
            varfont, location, updateFontNames=True
        )
        name_id_2 = instance["name"].getDebugName(2)
        mac_style = instance["head"].macStyle
        fs_selection = instance["OS/2"].fsSelection & 0b1100001  # Just bits 0, 5, 6

        if location["ital"] == 0:
            if location["wght"] == 700:
                assert name_id_2 == "Bold", location
                assert mac_style == 0b01, location
                assert fs_selection == 0b0100000, location
            else:
                assert name_id_2 == "Regular", location
                assert mac_style == 0b00, location
                assert fs_selection == 0b1000000, location
        else:
            if location["wght"] == 700:
                assert name_id_2 == "Bold Italic", location
                assert mac_style == 0b11, location
                assert fs_selection == 0b0100001, location
            else:
                assert name_id_2 == "Italic", location
                assert mac_style == 0b10, location
                assert fs_selection == 0b0000001, location


def test_rounds_before_iup():
    """Regression test for fonttools/fonttools#3634, with TTX based on
    reproduction process there."""

    varfont = ttLib.TTFont()
    varfont.importXML(os.path.join(TESTDATA, "3634-VF.ttx"))

    # Instantiate at a new default position, sufficient to cause differences
    # when unrounded but not when rounded.
    partial = instancer.instantiateVariableFont(varfont, {"wght": (401, 401, 900)})

    # Save and reload actual result to recalculate bounding box values, etc.
    bytes_out = BytesIO()
    partial.save(bytes_out)
    bytes_out.seek(0)
    partial = ttLib.TTFont(bytes_out)

    # Load expected result, then save and reload to normalise TTX output.
    expected = ttLib.TTFont()
    expected.importXML(os.path.join(TESTDATA, "test_results", "3634-VF-partial.ttx"))

    bytes_out = BytesIO()
    expected.save(bytes_out)
    bytes_out.seek(0)
    expected = ttLib.TTFont(bytes_out)

    # Serialise actual and expected to TTX strings, and compare.
    string_out = StringIO()
    partial.saveXML(string_out)
    partial_ttx = stripVariableItemsFromTTX(string_out.getvalue())

    string_out = StringIO()
    expected.saveXML(string_out)
    expected_ttx = stripVariableItemsFromTTX(string_out.getvalue())

    assert partial_ttx == expected_ttx
