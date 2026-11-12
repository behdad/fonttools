from pathlib import Path

from fontTools.diff import run
from fontTools.ttLib import TTCollection, TTFont

import pytest

TEST_DATA = Path(__file__).parent.parent / "ttLib" / "data"


def _load_font():
    font = TTFont()
    font.importXML(TEST_DATA / "TestTTF-Regular.ttx")
    return font


@pytest.fixture
def font_paths(tmp_path):
    """Two fonts that only differ in the 'head' table."""
    path1 = tmp_path / "font1.ttf"
    path2 = tmp_path / "font2.ttf"
    font = _load_font()
    font.save(path1)
    font = _load_font()
    font["head"].fontRevision = 2.0
    font.save(path2)
    return str(path1), str(path2)


@pytest.fixture
def collection_path(tmp_path):
    path = tmp_path / "collection.ttc"
    coll = TTCollection()
    coll.fonts = [_load_font(), _load_font()]
    coll.save(path)
    return str(path)


def test_diff(font_paths, capsys):
    assert run(["--diff", "", *font_paths]) == 1
    out = capsys.readouterr().out
    assert "fontRevision" in out


def test_diff_color_auto_not_a_tty(font_paths, capsys):
    # stdout is captured by pytest and is not a TTY
    assert run(["--diff", "", "--color", "auto", *font_paths]) == 1
    out = capsys.readouterr().out
    assert "fontRevision" in out
    assert "\x1b[" not in out


def test_diff_color_always(font_paths, capsys):
    assert run(["--diff", "", "--color", "always", *font_paths]) == 1
    out = capsys.readouterr().out
    assert "\x1b[" in out


def test_diff_include_only_identical_tables(font_paths, capsys):
    assert run(["--diff", "", "-t", "OS/2", "cmap", "--", *font_paths]) == 0
    assert capsys.readouterr().out == ""


def test_diff_include_some_identical_tables(font_paths, capsys):
    assert run(["--diff", "", "-t", "OS/2", "head", "--", *font_paths]) == 1
    out = capsys.readouterr().out
    assert "fontRevision" in out
    assert "<OS_2>" not in out


@pytest.mark.parametrize("summary", [False, True])
def test_diff_collection_without_font_number(collection_path, summary, capsys):
    args = ["-l"] if summary else []
    assert run([*args, collection_path, collection_path]) == 2
    err = capsys.readouterr().err
    assert err.startswith("[*] ERROR: specify a font number")
    assert run([*args, "--y1", "0", "--y2", "1", collection_path, collection_path]) == 0
