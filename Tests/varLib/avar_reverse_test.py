from pathlib import Path
import sys

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib import builder
from fontTools.varLib.avar.map import main, map as map_avar
from fontTools.varLib.avar.reverse import _AvarMapping, reverse


def make_font(tags=("aaaa", "bbbb", "cccc"), hidden=(), positive=()):
    font = TTFont()
    font["fvar"] = newTable("fvar")
    for tag in tags:
        axis = Axis()
        axis.axisTag = tag
        axis.minValue = 400 if tag in positive else 100
        axis.defaultValue = 400
        axis.maxValue = 900
        axis.flags = int(tag in hidden)
        axis.axisNameID = 256
        font["fvar"].axes.append(axis)
    return font


def add_avar2(font, supports, deltas):
    tags = [a.axisTag for a in font["fvar"].axes]
    avar = font["avar"] = newTable("avar")
    avar.majorVersion, avar.minorVersion = 2, 0
    avar.segments = {tag: {-1: -1, 0: 0, 1: 1} for tag in tags}
    avar.table = otTables.avar()
    avar.table.VarIdxMap = None
    region_list = builder.buildVarRegionList(supports, tags)
    data = builder.buildVarData(
        range(len(supports)),
        [
            [round(v * 16384) for v in deltas.get(tag, [0] * len(supports))]
            for tag in tags
        ],
    )
    avar.table.VarStore = builder.buildVarStore(region_list, [data])
    return avar


def forward(font, location):
    return map_avar(font, location, outputNormalized=True, dropZeroes=False)


def assert_target(font, result, target, atol=1 / 16384):
    actual = forward(font, result)
    assert np.linalg.norm([v - target.get(tag, 0) for tag, v in actual.items()]) <= atol


def test_identity_units_and_omitted_targets():
    font = make_font()
    result = reverse(font, {"aaaa": 0.4}, inputNormalized=True, dropZeroes=True)
    assert result == pytest.approx({"aaaa": 600})
    assert reverse(font, {"aaaa": 600}, outputNormalized=True) == pytest.approx(
        {"aaaa": 0.4, "bbbb": 0, "cccc": 0}
    )
    assert map_avar(
        font, {"aaaa": 0.4}, reverse=True, inputNormalized=True
    ) == pytest.approx({"aaaa": 600, "bbbb": 400, "cccc": 400})


@pytest.mark.parametrize(
    "segment,target,expected",
    [
        ({-1: -1, 0: 0, 0.5: 0.25, 1: 1}, 0.25, 650),
        # A plateau has infinitely many preimages. Prefer its nearest end.
        ({-1: -1, 0: 0, 0.25: 0.5, 0.75: 0.5, 1: 1}, 0.5, 525),
    ],
)
def test_avar1(segment, target, expected):
    font = make_font(("aaaa",))
    font["avar"] = newTable("avar")
    font["avar"].segments = {"aaaa": segment}
    result = reverse(font, {"aaaa": target}, inputNormalized=True)
    assert_target(font, result, {"aaaa": target})
    assert result["aaaa"] == pytest.approx(expected, abs=0.05)


def test_hidden_inputs_stay_default_but_outputs_can_change():
    font = make_font(("aaaa", "bbbb"), hidden=("bbbb",))
    add_avar2(font, [{"aaaa": (0, 1, 1)}], {"bbbb": [1]})
    target = {"aaaa": 0.5, "bbbb": 0.5}
    result = reverse(font, target, inputNormalized=True)
    assert result["bbbb"] == 400
    assert_target(font, result, target)


def test_pins_use_pre_fvar_units_with_normalized_flags():
    font = make_font(("aaaa", "bbbb"))
    result = reverse(
        font,
        {"aaaa": 0.25, "bbbb": 0.5},
        inputNormalized=True,
        outputNormalized=True,
        pinned={"aaaa": 525},
    )
    assert result == pytest.approx({"aaaa": 0.25, "bbbb": 0.5})
    result = reverse(font, {}, inputNormalized=True, pinned={"aaaa": 525, "bbbb": 400})
    assert result == {"aaaa": 525, "bbbb": 400}


def test_pin_none_means_default_including_hidden_axes():
    font = make_font(hidden=("cccc",))
    result = reverse(
        font,
        {"bbbb": 0.5},
        inputNormalized=True,
        pinned={"aaaa": None, "cccc": None},
    )
    assert result == pytest.approx({"aaaa": 400, "bbbb": 650, "cccc": 400})


def test_nearest_unreachable_target(caplog):
    # With the hidden input fixed, outputs lie on (x, x). The projection of
    # (1, 0) onto this line is (1/2, 1/2), not (1, 0) or the default.
    font = make_font(("aaaa", "bbbb"), hidden=("bbbb",))
    add_avar2(font, [{"aaaa": (0, 1, 1)}], {"bbbb": [1]})
    result = reverse(font, {"aaaa": 1}, inputNormalized=True)
    assert result == pytest.approx({"aaaa": 650, "bbbb": 400}, abs=0.04)
    assert "normalized residual" in caplog.text


def test_cross_axis_product_roundtrip():
    font = make_font(hidden=("cccc",))
    add_avar2(
        font,
        [{"aaaa": (0, 1, 1), "bbbb": (0, 1, 1)}],
        {"cccc": [0.5]},
    )
    source = {"aaaa": 600, "bbbb": 700, "cccc": 400}
    target = forward(font, source)
    result = reverse(font, target, inputNormalized=True)
    assert result["cccc"] == 400
    assert_target(font, result, target)


def test_multistart_escapes_zero_product_gradient():
    font = make_font(hidden=("cccc",))
    add_avar2(
        font,
        [{"aaaa": (0, 1, 1), "bbbb": (0, 1, 1)}],
        {"cccc": [1.5]},
    )
    result = reverse(font, {"cccc": 1}, inputNormalized=True)
    # min 2*x^2 + (1.5*x^2 - 1)^2 occurs at x = sqrt(2)/3.
    expected = 400 + 500 * np.sqrt(2) / 3
    assert result["aaaa"] == pytest.approx(expected, abs=0.1)
    assert result["bbbb"] == pytest.approx(expected, abs=0.1)
    actual = forward(font, result)
    assert sum((actual[tag] - (tag == "cccc")) ** 2 for tag in actual) < 0.9


def test_prefers_one_nondefault_axis_over_two():
    font = make_font(hidden=("cccc",), positive=("aaaa", "bbbb"))
    add_avar2(
        font,
        [{"aaaa": (0, 1, 1)}, {"bbbb": (0, 1, 1)}],
        {"aaaa": [-1, 0], "bbbb": [0, -1], "cccc": [1, 1]},
    )
    target = {"cccc": 0.75}
    result = reverse(font, target, inputNormalized=True)
    assert sum(value != 400 for value in result.values()) == 1
    assert_target(font, result, target)
    pinned = reverse(font, target, inputNormalized=True, pinned={"aaaa": 400})
    assert pinned == pytest.approx({"aaaa": 400, "bbbb": 775, "cccc": 400}, abs=0.04)


@pytest.mark.parametrize("target", [0.5, 1.0, -1.0])
def test_clipping_and_saturation(target):
    font = make_font(("aaaa",))
    add_avar2(
        font,
        [{"aaaa": (-1, -1, 0)}, {"aaaa": (0, 1, 1)}],
        {"aaaa": [-1, 1]},
    )
    result = reverse(font, {"aaaa": target}, inputNormalized=True)
    assert_target(font, result, {"aaaa": target})


def test_jacobian_matches_unrounded_finite_differences():
    font = make_font()
    avar = add_avar2(
        font,
        [
            {},
            {"aaaa": (0, 0.8, 1), "bbbb": (0, 0.7, 1)},
            {"aaaa": (-1, -0.8, 0), "cccc": (0, 1, 1)},
        ],
        {"aaaa": [0.125, 0.5, 0], "bbbb": [0, 0, -0.25], "cccc": [0, 0.5, 0.25]},
    )
    avar.segments["aaaa"] = {-1: -1, 0: 0, 0.5: 0.7, 1: 1}
    mapping = _AvarMapping(font)
    for x in (np.array([0.3, 0.4, 0.2]), np.array([-0.4, 0.3, 0.7])):
        _, jac = mapping(x)
        numerical = np.column_stack(
            [(mapping(x + d)[0] - mapping(x - d)[0]) / 2e-6 for d in np.eye(3) * 1e-6]
        )
        assert jac == pytest.approx(numerical, abs=1e-8)


def test_jacobian_at_shared_tent_boundary():
    # The individual tents kink at zero, but their sum is linear there.
    font = make_font(("aaaa",))
    add_avar2(
        font,
        [{"aaaa": (-1, -1, 0)}, {"aaaa": (0, 1, 1)}],
        {"aaaa": [-0.25, 0.25]},
    )
    _, jac = _AvarMapping(font)(np.array([0.0]))
    assert jac == pytest.approx(np.array([[1.25]]))


def test_degenerate_and_one_sided_axes():
    font = make_font(("aaaa", "bbbb"), positive=("aaaa",))
    font["fvar"].axes[1].minValue = font["fvar"].axes[1].maxValue = 400
    result = reverse(font, {"aaaa": -0.5, "bbbb": 1}, inputNormalized=True)
    assert result == {"aaaa": 400, "bbbb": 400}


@pytest.mark.parametrize("variant", ["null", "invalid", "shared"])
def test_varstore_index_variants(variant):
    font = make_font(("aaaa", "bbbb"))
    avar = add_avar2(font, [{"aaaa": (0, 1, 1)}], {"aaaa": [0.25], "bbbb": [0.5]})
    if variant == "null":
        avar.table.VarStore = None
    elif variant == "invalid":
        avar.table.VarIdxMap = builder.buildDeltaSetIndexMap([0xFFFFFFFF, 0x12345678])
    else:
        avar.table.VarIdxMap = builder.buildDeltaSetIndexMap([0, 0])
    target = forward(font, {"aaaa": 550, "bbbb": 650})
    result = reverse(font, target, inputNormalized=True)
    assert_target(font, result, target)


def test_real_avar2_roundtrip():
    path = Path(__file__).parent.parent / "ttLib/tables/data/Amstelvar-avar2.subset.ttf"
    font = TTFont(path)
    source = {"wght": 650, "wdth": 85, "opsz": 24}
    target = forward(font, source)
    before = {tag: dict(seg) for tag, seg in font["avar"].segments.items()}
    result = reverse(font, target, inputNormalized=True, dropZeroes=True)
    assert_target(font, result, target, atol=2 / 16384)
    assert len(result) <= len(source)
    assert font["avar"].segments == before


@pytest.mark.parametrize(
    "location,kwargs,message",
    [
        ({"XXXX": 0}, {}, "Unknown axis"),
        ({}, {"pinned": {"XXXX": 400}}, "Unknown axis"),
        ({"aaaa": float("nan")}, {}, "Invalid target"),
        ({"aaaa": 2}, {"inputNormalized": True}, "Invalid target"),
        ({}, {"pinned": {"aaaa": 1000}}, "Pinned coordinate"),
        ({}, {"pinned": {"bbbb": 500}}, "Hidden axis"),
        ({}, {"tolerance": -1}, "tolerance"),
    ],
)
def test_invalid_arguments(location, kwargs, message):
    font = make_font(("aaaa", "bbbb"), hidden=("bbbb",))
    with pytest.raises(ValueError, match=message):
        reverse(font, location, **kwargs)


def test_no_fvar():
    assert reverse(TTFont(), {}) is None


def test_scipy_is_optional_for_forward_mapping(monkeypatch):
    monkeypatch.setitem(sys.modules, "scipy.optimize", None)
    font = make_font(("aaaa",))
    assert forward(font, {"aaaa": 650}) == {"aaaa": 0.5}
    with pytest.raises(ImportError, match=r"install fonttools\[avar\]"):
        reverse(font, {"aaaa": 0.5}, inputNormalized=True)


@pytest.mark.parametrize("pin", ["bbbb=400", "bbbb"])
def test_cli_reverse_and_pins(tmp_path, capsys, pin):
    font = make_font(("aaaa", "bbbb"))
    path = tmp_path / "test.ttf"
    font.save(path)
    main(["--reverse", "-i", "--pin", pin, str(path), "aaaa=0.3333333333333333"])
    result = {
        k: float(v)
        for k, v in (line.split("=") for line in capsys.readouterr().out.splitlines())
    }
    assert set(result) == {"aaaa"}
    assert_target(font, result, {"aaaa": 1 / 3}, atol=1e-14)


def test_cli_pins_require_reverse():
    with pytest.raises(SystemExit, match="2"):
        main(["--pin", "aaaa=400", "font.ttf", "aaaa=0"])


@pytest.mark.parametrize("input_normalized", [False, True])
@pytest.mark.parametrize("output_normalized", [False, True])
@pytest.mark.parametrize("drop_zeroes", [False, True])
def test_cli_reverse_empty_location(
    tmp_path, capsys, input_normalized, output_normalized, drop_zeroes
):
    font = make_font(("aaaa", "bbbb"))
    add_avar2(font, [{"aaaa": (0, 1, 1)}], {"bbbb": [0.5]})
    path = tmp_path / "test.ttf"
    font.save(path)
    flags = ["--reverse"]
    if input_normalized:
        flags.append("-i")
    if output_normalized:
        flags.append("-o")
    if not drop_zeroes:
        flags.append("-f")
    main([*flags, str(path)])
    result = {
        tag: float(value)
        for tag, value in (
            line.split("=") for line in capsys.readouterr().out.splitlines()
        )
    }
    expected = (
        {"aaaa": 0, "bbbb": 0} if output_normalized else {"aaaa": 400, "bbbb": 400}
    )
    assert result == ({} if drop_zeroes else expected)


@pytest.mark.parametrize("pin", ["XXXX", "aaaa=", "aaaa=nan", "aaaa=1000"])
def test_cli_invalid_pin(tmp_path, pin):
    font = make_font(("aaaa",))
    path = tmp_path / "test.ttf"
    font.save(path)
    with pytest.raises(SystemExit, match="2"):
        main(["--reverse", "-i", "--pin", pin, str(path), "aaaa=0"])
