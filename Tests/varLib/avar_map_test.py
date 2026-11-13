from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib import builder
from fontTools.varLib.avar.map import main, map as map_avar
import pytest


@pytest.fixture(params=[None, 1, 2], ids=["no-avar", "avar1", "avar2"])
def font(request):
    font = TTFont()
    font["fvar"] = newTable("fvar")
    for tag, triple in (("wght", (100, 400, 900)), ("wdth", (50, 100, 125))):
        axis = Axis()
        axis.axisTag = tag
        axis.minValue, axis.defaultValue, axis.maxValue = triple
        axis.axisNameID = 256
        font["fvar"].axes.append(axis)
    if request.param is not None:
        avar = font["avar"] = newTable("avar")
        avar.majorVersion = request.param
        avar.segments = {
            "wght": {-1: -1, 0: 0, 0.5: 0.75, 1: 1},
            "wdth": {-1: -1, 0: 0, 1: 1},
        }
        if request.param == 2:
            avar.table = otTables.avar()
            avar.table.VarIdxMap = None
            avar.table.VarStore = builder.buildVarStore(
                builder.buildVarRegionList([{"wght": (0, 1, 1)}], ["wght", "wdth"]),
                [builder.buildVarData([0], [[0], [4096]])],
            )
    return font


@pytest.mark.parametrize("input_normalized", [False, True])
@pytest.mark.parametrize("output_normalized", [False, True])
@pytest.mark.parametrize("drop_zeroes", [False, True])
def test_empty_location_uses_defaults(
    font, input_normalized, output_normalized, drop_zeroes
):
    expected = (
        {}
        if drop_zeroes
        else (
            {"wght": 0, "wdth": 0} if output_normalized else {"wght": 400, "wdth": 100}
        )
    )
    result = map_avar(
        font,
        {},
        inputNormalized=input_normalized,
        outputNormalized=output_normalized,
        dropZeroes=drop_zeroes,
    )
    assert result == expected


@pytest.mark.parametrize("input_normalized", [False, True])
@pytest.mark.parametrize("drop_zeroes", [False, True])
def test_sparse_location_uses_defaults(font, input_normalized, drop_zeroes):
    has_avar = "avar" in font
    avar2 = has_avar and font["avar"].majorVersion == 2
    expected = {"wght": 0.75 if has_avar else 0.5, "wdth": 0.1875 if avar2 else 0}
    if drop_zeroes:
        expected = {tag: v for tag, v in expected.items() if v != 0}
    assert (
        map_avar(
            font,
            {"wght": 0.5 if input_normalized else 650},
            inputNormalized=input_normalized,
            outputNormalized=True,
            dropZeroes=drop_zeroes,
        )
        == expected
    )


@pytest.mark.parametrize("input_normalized", [False, True])
def test_explicit_defaults_are_omitted(font, input_normalized):
    location = (
        {"wght": 0, "wdth": 0} if input_normalized else {"wght": 400, "wdth": 100}
    )
    assert (
        map_avar(font, location, inputNormalized=input_normalized, dropZeroes=True)
        == {}
    )


@pytest.mark.parametrize("input_normalized", [False, True])
@pytest.mark.parametrize(
    "flags,expected",
    [
        ([], {}),
        (["-f"], {"wght": 400, "wdth": 100}),
        (["-f", "-o"], {"wght": 0, "wdth": 0}),
    ],
)
def test_cli_accepts_empty_location(
    font, tmp_path, capsys, input_normalized, flags, expected
):
    path = tmp_path / "test.ttf"
    font.save(path)
    main([*flags, *(["-i"] if input_normalized else []), str(path)])
    output = capsys.readouterr()
    actual = {
        tag: float(value)
        for tag, value in (line.split("=") for line in output.out.splitlines())
    }
    assert actual == expected
    assert output.err == ""


def test_default_location_applies_avar2_bias():
    font = TTFont()
    font["fvar"] = newTable("fvar")
    axis = Axis()
    axis.axisTag = "wght"
    axis.minValue, axis.defaultValue, axis.maxValue = 100, 400, 900
    font["fvar"].axes = [axis]
    avar = font["avar"] = newTable("avar")
    avar.majorVersion = 2
    avar.segments = {"wght": {-1: -1, 0: 0, 1: 1}}
    avar.table = otTables.avar()
    avar.table.VarIdxMap = None
    avar.table.VarStore = builder.buildVarStore(
        builder.buildVarRegionList([{}], ["wght"]),
        [builder.buildVarData([0], [[4096]])],
    )
    # A constant avar2 bias can move the default. Empty input must still go
    # through avar instead of returning early or unconditionally dropping axes.
    for normalized in (False, True):
        assert map_avar(
            font, {}, inputNormalized=normalized, outputNormalized=True, dropZeroes=True
        ) == {"wght": 0.25}
