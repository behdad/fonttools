from fontTools.ttLib.tables import otTables
from fontTools.otlLib.builder import buildStatTable
from fontTools.varLib import instancer

import pytest


def test_pruningUnusedNames(varfont):
    varNameIDs = instancer.names.getVariationNameIDs(varfont)

    assert varNameIDs == set(range(256, 297 + 1))

    fvar = varfont["fvar"]
    stat = varfont["STAT"].table

    with instancer.names.pruningUnusedNames(varfont):
        del fvar.axes[0]  # Weight (nameID=256)
        del fvar.instances[0]  # Thin (nameID=258)
        del stat.DesignAxisRecord.Axis[0]  # Weight (nameID=256)
        del stat.AxisValueArray.AxisValue[0]  # Thin (nameID=258)

    assert not any(n for n in varfont["name"].names if n.nameID in {256, 258})

    with instancer.names.pruningUnusedNames(varfont):
        del varfont["fvar"]
        del varfont["STAT"]

    assert not any(n for n in varfont["name"].names if n.nameID in varNameIDs)
    assert "ltag" not in varfont


def _test_name_records(varfont, expected, isNonRIBBI, platforms=[0x409]):
    nametable = varfont["name"]
    font_names = {
        (r.nameID, r.platformID, r.platEncID, r.langID): r.toUnicode()
        for r in nametable.names
    }
    for k in expected:
        if k[-1] not in platforms:
            continue
        assert font_names[k] == expected[k]

    font_nameids = set(i[0] for i in font_names)
    if isNonRIBBI:
        assert 16 in font_nameids
        assert 17 in font_nameids

    if "fvar" not in varfont:
        assert 25 not in font_nameids


@pytest.mark.parametrize(
    "limits, expected, isNonRIBBI",
    [
        # Regular
        (
            {"wght": 400},
            {
                (1, 3, 1, 0x409): "Test Variable Font",
                (2, 3, 1, 0x409): "Regular",
                (3, 3, 1, 0x409): "2.001;GOOG;TestVariableFont-Regular",
                (6, 3, 1, 0x409): "TestVariableFont-Regular",
            },
            False,
        ),
        # Regular Normal (width axis Normal isn't included since it is elided)
        (
            {"wght": 400, "wdth": 100},
            {
                (1, 3, 1, 0x409): "Test Variable Font",
                (2, 3, 1, 0x409): "Regular",
                (3, 3, 1, 0x409): "2.001;GOOG;TestVariableFont-Regular",
                (6, 3, 1, 0x409): "TestVariableFont-Regular",
            },
            False,
        ),
        # Black
        (
            {"wght": 900},
            {
                (1, 3, 1, 0x409): "Test Variable Font Black",
                (2, 3, 1, 0x409): "Regular",
                (3, 3, 1, 0x409): "2.001;GOOG;TestVariableFont-Black",
                (6, 3, 1, 0x409): "TestVariableFont-Black",
                (16, 3, 1, 0x409): "Test Variable Font",
                (17, 3, 1, 0x409): "Black",
            },
            True,
        ),
        # Thin
        (
            {"wght": 100},
            {
                (1, 3, 1, 0x409): "Test Variable Font Thin",
                (2, 3, 1, 0x409): "Regular",
                (3, 3, 1, 0x409): "2.001;GOOG;TestVariableFont-Thin",
                (6, 3, 1, 0x409): "TestVariableFont-Thin",
                (16, 3, 1, 0x409): "Test Variable Font",
                (17, 3, 1, 0x409): "Thin",
            },
            True,
        ),
        # Thin Condensed
        (
            {"wght": 100, "wdth": 79},
            {
                (1, 3, 1, 0x409): "Test Variable Font Thin Condensed",
                (2, 3, 1, 0x409): "Regular",
                (3, 3, 1, 0x409): "2.001;GOOG;TestVariableFont-ThinCondensed",
                (6, 3, 1, 0x409): "TestVariableFont-ThinCondensed",
                (16, 3, 1, 0x409): "Test Variable Font",
                (17, 3, 1, 0x409): "Thin Condensed",
            },
            True,
        ),
        # Condensed with unpinned weights
        (
            {"wdth": 79, "wght": (400, 900)},
            {
                (1, 3, 1, 0x409): "Test Variable Font Condensed",
                (2, 3, 1, 0x409): "Regular",
                (3, 3, 1, 0x409): "2.001;GOOG;TestVariableFont-Condensed",
                (6, 3, 1, 0x409): "TestVariableFont-Condensed",
                (16, 3, 1, 0x409): "Test Variable Font",
                (17, 3, 1, 0x409): "Condensed",
            },
            True,
        ),
        # Restrict weight and move default, new minimum (500) > old default (400)
        (
            {"wght": (500, 900)},
            {
                (1, 3, 1, 0x409): "Test Variable Font Medium",
                (2, 3, 1, 0x409): "Regular",
                (3, 3, 1, 0x409): "2.001;GOOG;TestVariableFont-Medium",
                (6, 3, 1, 0x409): "TestVariableFont-Medium",
                (16, 3, 1, 0x409): "Test Variable Font",
                (17, 3, 1, 0x409): "Medium",
            },
            True,
        ),
    ],
)
def test_updateNameTable_with_registered_axes_ribbi(
    varfont, limits, expected, isNonRIBBI
):
    instancer.names.updateNameTable(varfont, limits)
    _test_name_records(varfont, expected, isNonRIBBI)


def test_updateNameTable_stat_version_1_0(varfont):
    stat = varfont["STAT"]
    stat.table.Version = 0x00010000
    stat.decompile(stat.compile(varfont), varfont)

    instancer.names.updateNameTable(varfont, {"wght": 100})

    expected = {
        (1, 3, 1, 0x409): "Test Variable Font Thin",
        (2, 3, 1, 0x409): "Regular",
        (6, 3, 1, 0x409): "TestVariableFont-Thin",
        (16, 3, 1, 0x409): "Test Variable Font",
        (17, 3, 1, 0x409): "Thin",
    }
    _test_name_records(varfont, expected, isNonRIBBI=True)


def test_updatetNameTable_axis_order(varfont):
    axes = [
        dict(
            tag="wght",
            name="Weight",
            values=[
                dict(value=400, name="Regular"),
            ],
        ),
        dict(
            tag="wdth",
            name="Width",
            values=[
                dict(value=75, name="Condensed"),
            ],
        ),
    ]
    nametable = varfont["name"]
    buildStatTable(varfont, axes)
    instancer.names.updateNameTable(varfont, {"wdth": 75, "wght": 400})
    assert nametable.getName(17, 3, 1, 0x409).toUnicode() == "Regular Condensed"

    # Swap the axes so the names get swapped
    axes[0], axes[1] = axes[1], axes[0]

    buildStatTable(varfont, axes)
    instancer.names.updateNameTable(varfont, {"wdth": 75, "wght": 400})
    assert nametable.getName(17, 3, 1, 0x409).toUnicode() == "Condensed Regular"


@pytest.mark.parametrize(
    "limits, expected, isNonRIBBI",
    [
        # Regular | Normal
        (
            {"wght": 400},
            {
                (1, 3, 1, 0x409): "Test Variable Font",
                (2, 3, 1, 0x409): "Normal",
            },
            False,
        ),
        # Black | Negreta
        (
            {"wght": 900},
            {
                (1, 3, 1, 0x409): "Test Variable Font Negreta",
                (2, 3, 1, 0x409): "Normal",
                (16, 3, 1, 0x409): "Test Variable Font",
                (17, 3, 1, 0x409): "Negreta",
            },
            True,
        ),
        # Black Condensed | Negreta Zhuštěné
        (
            {"wght": 900, "wdth": 79},
            {
                (1, 3, 1, 0x409): "Test Variable Font Negreta Zhuštěné",
                (2, 3, 1, 0x409): "Normal",
                (16, 3, 1, 0x409): "Test Variable Font",
                (17, 3, 1, 0x409): "Negreta Zhuštěné",
            },
            True,
        ),
    ],
)
def test_updateNameTable_with_multilingual_names(varfont, limits, expected, isNonRIBBI):
    name = varfont["name"]
    # langID 0x405 is the Czech Windows langID
    name.setName("Test Variable Font", 1, 3, 1, 0x405)
    name.setName("Normal", 2, 3, 1, 0x405)
    name.setName("Normal", 261, 3, 1, 0x405)  # nameID 261=Regular STAT entry
    name.setName("Negreta", 266, 3, 1, 0x405)  # nameID 266=Black STAT entry
    name.setName("Zhuštěné", 279, 3, 1, 0x405)  # nameID 279=Condensed STAT entry

    instancer.names.updateNameTable(varfont, limits)
    _test_name_records(varfont, expected, isNonRIBBI, platforms=[0x405])


def test_updateNameTable_missing_axisValues(varfont):
    with pytest.raises(ValueError, match="Cannot find Axis Values {'wght': 200}"):
        instancer.names.updateNameTable(varfont, {"wght": 200})


def test_updateNameTable_missing_stat_no_fvar_instance(varfont):
    del varfont["STAT"]
    # no fvar instance at wght=450
    with pytest.raises(ValueError, match="no fvar instance at"):
        instancer.names.updateNameTable(varfont, {"wght": 450})


@pytest.mark.parametrize("emptyStat", [False, True])
@pytest.mark.parametrize(
    "limits, expected, isNonRIBBI",
    [
        (
            {"wght": 400, "wdth": 100},
            {
                (1, 3, 1, 0x409): "Test Variable Font",
                (2, 3, 1, 0x409): "Regular",
                (6, 3, 1, 0x409): "TestVariableFont-Regular",
            },
            False,
        ),
        (
            {"wght": 700, "wdth": 100},
            {
                (1, 3, 1, 0x409): "Test Variable Font",
                (2, 3, 1, 0x409): "Bold",
                (6, 3, 1, 0x409): "TestVariableFont-Bold",
            },
            False,
        ),
        (
            {"wght": 900, "wdth": 79},
            {
                (1, 3, 1, 0x409): "Test Variable Font Condensed Black",
                (2, 3, 1, 0x409): "Regular",
                (6, 3, 1, 0x409): "TestVariableFont-CondensedBlack",
                (16, 3, 1, 0x409): "Test Variable Font",
                (17, 3, 1, 0x409): "Condensed Black",
            },
            True,
        ),
    ],
)
def test_updateNameTable_fvar_fallback(
    varfont, limits, expected, isNonRIBBI, emptyStat
):
    if emptyStat:
        varfont["STAT"].table.AxisValueArray = None
    else:
        del varfont["STAT"]
    instancer.names.updateNameTable(varfont, limits)
    _test_name_records(varfont, expected, isNonRIBBI)


def test_updateNameTable_fvar_fallback_partial_instancing(varfont):
    del varfont["STAT"]
    instancer.names.updateNameTable(varfont, {"wght": 900})
    name = varfont["name"]
    assert name.getName(1, 3, 1, 0x409).toUnicode() == "Test Variable Font Black"
    assert name.getName(17, 3, 1, 0x409).toUnicode() == "Black"


@pytest.mark.parametrize("modifier", ["Extra", "Semi", "Demi", "Ultra"])
def test_updateNameTable_fvar_fallback_weight_modifier_not_ribbi(varfont, modifier):
    del varfont["STAT"]
    instance = next(
        i
        for i in varfont["fvar"].instances
        if i.coordinates == {"wght": 900, "wdth": 100}
    )
    fullName = f"{modifier} Bold"
    varfont["name"].setName(fullName, instance.subfamilyNameID, 3, 1, 0x409)
    instancer.names.updateNameTable(varfont, {"wght": 900, "wdth": 100})
    name = varfont["name"]
    assert name.getName(1, 3, 1, 0x409).toUnicode() == f"Test Variable Font {fullName}"
    assert name.getName(2, 3, 1, 0x409).toUnicode() == "Regular"
    assert name.getName(17, 3, 1, 0x409).toUnicode() == fullName


@pytest.mark.parametrize(
    "limits, expected, isNonRIBBI",
    [
        # Regular | Normal
        (
            {"wght": 400},
            {
                (1, 3, 1, 0x409): "Test Variable Font",
                (2, 3, 1, 0x409): "Italic",
                (6, 3, 1, 0x409): "TestVariableFont-Italic",
            },
            False,
        ),
        # Black Condensed Italic
        (
            {"wght": 900, "wdth": 79},
            {
                (1, 3, 1, 0x409): "Test Variable Font Black Condensed",
                (2, 3, 1, 0x409): "Italic",
                (6, 3, 1, 0x409): "TestVariableFont-BlackCondensedItalic",
                (16, 3, 1, 0x409): "Test Variable Font",
                (17, 3, 1, 0x409): "Black Condensed Italic",
            },
            True,
        ),
    ],
)
def test_updateNameTable_vf_with_italic_attribute(
    varfont, limits, expected, isNonRIBBI
):
    font_link_axisValue = varfont["STAT"].table.AxisValueArray.AxisValue[5]
    # Unset ELIDABLE_AXIS_VALUE_NAME flag
    font_link_axisValue.Flags &= ~instancer.names.ELIDABLE_AXIS_VALUE_NAME
    font_link_axisValue.ValueNameID = 294  # Roman --> Italic

    instancer.names.updateNameTable(varfont, limits)
    _test_name_records(varfont, expected, isNonRIBBI)


def test_updateNameTable_format4_axisValues(varfont):
    # format 4 axisValues should dominate the other axisValues
    stat = varfont["STAT"].table

    axisValue = otTables.AxisValue()
    axisValue.Format = 4
    axisValue.Flags = 0
    varfont["name"].setName("Dominant Value", 297, 3, 1, 0x409)
    axisValue.ValueNameID = 297
    axisValue.AxisValueRecord = []
    for tag, value in (("wght", 900), ("wdth", 79)):
        rec = otTables.AxisValueRecord()
        rec.AxisIndex = next(
            i for i, a in enumerate(stat.DesignAxisRecord.Axis) if a.AxisTag == tag
        )
        rec.Value = value
        axisValue.AxisValueRecord.append(rec)
    stat.AxisValueArray.AxisValue.append(axisValue)

    instancer.names.updateNameTable(varfont, {"wdth": 79, "wght": 900})
    expected = {
        (1, 3, 1, 0x409): "Test Variable Font Dominant Value",
        (2, 3, 1, 0x409): "Regular",
        (16, 3, 1, 0x409): "Test Variable Font",
        (17, 3, 1, 0x409): "Dominant Value",
    }
    _test_name_records(varfont, expected, isNonRIBBI=True)


def test_updateNameTable_elided_axisValues(varfont):
    stat = varfont["STAT"].table
    # set ELIDABLE_AXIS_VALUE_NAME flag for all axisValues
    for axisValue in stat.AxisValueArray.AxisValue:
        axisValue.Flags |= instancer.names.ELIDABLE_AXIS_VALUE_NAME

    stat.ElidedFallbackNameID = 266  # Regular --> Black
    instancer.names.updateNameTable(varfont, {"wght": 400})
    # Since all axis values are elided, the elided fallback name
    # must be used to construct the style names. Since we
    # changed it to Black, we need both a typoSubFamilyName and
    # the subFamilyName set so it conforms to the RIBBI model.
    expected = {(2, 3, 1, 0x409): "Regular", (17, 3, 1, 0x409): "Black"}
    _test_name_records(varfont, expected, isNonRIBBI=True)


def test_updateNameTable_existing_subfamily_name_is_not_regular(varfont):
    # Check the subFamily name will be set to Regular when we update a name
    # table to a non-RIBBI style and the current subFamily name is a RIBBI
    # style which isn't Regular.
    varfont["name"].setName("Bold", 2, 3, 1, 0x409)  # subFamily Regular --> Bold

    instancer.names.updateNameTable(varfont, {"wght": 100})
    expected = {(2, 3, 1, 0x409): "Regular", (17, 3, 1, 0x409): "Thin"}
    _test_name_records(varfont, expected, isNonRIBBI=True)


def test_name_irrelevant_axes(varfont):
    # Cannot update name table if not on a named axis value location
    with pytest.raises(ValueError) as excinfo:
        location = {"wght": 400, "wdth": 90}
        instance = instancer.instantiateVariableFont(
            varfont, location, updateFontNames=True
        )
    assert "Cannot find Axis Values" in str(excinfo.value)

    # Now let's make the wdth axis "irrelevant" to naming (no axis values)
    varfont["STAT"].table.AxisValueArray.AxisValue.pop(6)
    varfont["STAT"].table.AxisValueArray.AxisValue.pop(4)
    location = {"wght": 400, "wdth": 90}
    instance = instancer.instantiateVariableFont(
        varfont, location, updateFontNames=True
    )
