from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._f_v_a_r import Axis
from fontTools.varLib.avar.build import build
from fontTools.varLib.avar.map import map as map_avar, main as map_main
from fontTools.varLib.models import VariationModel
from fontTools.varLib.avar.unbuild import _pruneLocations, mappings_from_avar, unbuild
from io import StringIO
from pathlib import Path
import os
import unittest
import pytest

TESTS = [
    (
        [
            {"wght": 1},
            {"wght": 0.5},
        ],
        [
            {"wght": 0.5},
        ],
        [
            {"wght": 0.5},
        ],
    ),
    (
        [
            {"wght": 1, "wdth": 1},
            {"wght": 0.5, "wdth": 1},
        ],
        [
            {"wght": 1, "wdth": 1},
        ],
        [
            {"wght": 1, "wdth": 1},
            {"wght": 0.5, "wdth": 1},
        ],
    ),
    (
        [
            {"wght": 1},
            {"wdth": 1},
            {"wght": 0.5, "wdth": 0.5},
        ],
        [
            {"wght": 0.5, "wdth": 0.5},
        ],
        [
            {"wght": 0.5, "wdth": 0.5},
        ],
    ),
]


@pytest.mark.parametrize("locations, poles, expected", TESTS)
def test_pruneLocations(locations, poles, expected):
    axisTags = set()
    for location in locations:
        axisTags.update(location.keys())
    axisTags = sorted(axisTags)

    locations = [{}] + locations

    pruned = _pruneLocations(locations, poles, axisTags)

    assert pruned == expected, (pruned, expected)


@pytest.mark.parametrize("locations, poles, expected", TESTS)
def test_roundtrip(locations, poles, expected):
    axisTags = set()
    for location in locations:
        axisTags.update(location.keys())
    axisTags = sorted(axisTags)

    locations = [{}] + locations
    expected = [{}] + expected

    model1 = VariationModel(locations, axisTags)
    model2 = VariationModel(expected, axisTags)

    for location in poles:
        i = model1.locations.index(location)
        support1 = model1.supports[i]

        i = model2.locations.index(location)
        support2 = model2.supports[i]

        assert support1 == support2, (support1, support2)


def test_mappings_from_avar():
    CWD = os.path.abspath(os.path.dirname(__file__))
    DATADIR = os.path.join(CWD, "..", "ttLib", "tables", "data")
    varfont_path = os.path.join(DATADIR, "Amstelvar-avar2.subset.ttf")
    font = TTFont(varfont_path)
    mappings = mappings_from_avar(font)

    assert len(mappings) == 2, mappings


def test_mappings_from_avar_without_avar_table():
    font = TTFont()
    font["fvar"] = newTable("fvar")
    font["fvar"].axes = []

    axis_maps, mappings = mappings_from_avar(font)

    assert axis_maps == {}
    assert mappings == []


def test_unbuild_falls_back_to_axis_tag_when_name_missing():
    font = TTFont()
    font["fvar"] = newTable("fvar")
    axis = Axis()
    axis.axisTag = "wght"
    axis.axisNameID = 999
    axis.minValue = 100
    axis.defaultValue = 400
    axis.maxValue = 900
    font["fvar"].axes = [axis]
    font["name"] = newTable("name")

    output = StringIO()
    unbuild(font, output)

    assert 'name="wght"' in output.getvalue()


def test_map_rejects_unknown_axis():
    font = TTFont()
    font["fvar"] = newTable("fvar")
    axis = Axis()
    axis.axisTag = "wght"
    axis.axisNameID = 256
    axis.minValue = 100
    axis.defaultValue = 400
    axis.maxValue = 900
    font["fvar"].axes = [axis]

    with pytest.raises(ValueError, match="Unknown axis tag"):
        map_avar(font, {"wdth": 100})


def test_map_main_rejects_malformed_coordinate(tmp_path):
    designspace = Path(tmp_path) / "Test.designspace"
    designspace.write_text(
        """\
<?xml version='1.0' encoding='UTF-8'?>
<designspace format="5.0">
  <axes>
    <axis tag="wght" name="Weight" minimum="100" maximum="900" default="400"/>
  </axes>
</designspace>
""",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="2"):
        map_main([str(designspace), "wght"])


def test_build_preserves_existing_name_table(tmp_path):
    designspace = Path(tmp_path) / "Test.designspace"
    designspace.write_text(
        """\
<?xml version='1.0' encoding='UTF-8'?>
<designspace format="5.0">
  <axes>
    <axis tag="wght" name="Weight" minimum="100" maximum="900" default="400"/>
  </axes>
</designspace>
""",
        encoding="utf-8",
    )

    font = TTFont()
    font["name"] = newTable("name")
    font["name"].setName("Existing Name", 320, 3, 1, 0x409)

    build(font, designspace)

    assert font["name"].getDebugName(320) == "Existing Name"


def test_unbuild_escapes_axis_name_in_designspace():
    # Axis names come from the font's 'name' table (untrusted); unbuild writes
    # them into XML attribute values. A name containing markup must not be able
    # to break out of the attribute and inject elements into the designspace.
    from xml.etree import ElementTree

    font = TTFont()
    name = newTable("name")
    name.names = []
    hostile = 'W" /><!DOCTYPE x><axis tag="z'
    name.setName(hostile, 256, 3, 1, 0x409)
    font["name"] = name

    fvar = newTable("fvar")
    axis = Axis()
    axis.axisTag = "wght"
    axis.minValue, axis.defaultValue, axis.maxValue = 100, 400, 900
    axis.axisNameID = 256
    fvar.axes = [axis]
    font["fvar"] = fvar

    buf = StringIO()
    unbuild(font, f=buf)
    out = buf.getvalue()

    # No unescaped markup leaked through
    assert "<!DOCTYPE" not in out
    # Output is well-formed and the hostile string survives as a plain
    # attribute value on the single <axis> element
    root = ElementTree.fromstring(out)
    axes = root.findall(".//axis")
    assert len(axes) == 1
    assert axes[0].get("name") == hostile


def test_avarPlanner_main_returns_plan_exit_code(tmp_path):
    import subprocess
    import sys
    from fontTools.fontBuilder import FontBuilder
    from fontTools.varLib.avarPlanner import main as avarPlanner_main

    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef"])
    fontfile = str(tmp_path / "Static.ttf")
    fb.font.save(fontfile)

    # "Not a variable font."
    assert avarPlanner_main([fontfile]) == 1

    result = subprocess.run(
        [sys.executable, "-m", "fontTools", "varLib.avarPlanner", fontfile]
    )
    assert result.returncode == 1
