import logging
import shutil

import pytest

from fontTools.misc import plistlib
from fontTools.ufoLib import UFOFormatVersion, UFOReader, UFOWriter
from fontTools.ufoLib.errors import UFOLibError, UnsupportedUFOFormat


@pytest.fixture
def ufo_path(tmp_path):
    ufodir = tmp_path / "TestFont.ufo"
    ufodir.mkdir()
    with (ufodir / "metainfo.plist").open("wb") as f:
        plistlib.dump({"creator": "pytest", "formatVersion": 3}, f)
    (ufodir / "glyphs").mkdir()
    with (ufodir / "layercontents.plist").open("wb") as f:
        plistlib.dump([("public.default", "glyphs")], f)
    return ufodir


@pytest.mark.parametrize(
    "pair",
    [("public.kern2.V", "A"), ("V", "public.kern1.A")],
)
def test_readKerning_group_on_wrong_side(ufo_path, pair):
    with (ufo_path / "kerning.plist").open("wb") as file:
        plistlib.dump({pair[0]: {pair[1]: -80}}, file)

    with UFOReader(ufo_path) as reader:
        with pytest.raises(UFOLibError):
            reader.readKerning()
        assert reader.readKerning(validate=False) == {pair: -80}


@pytest.mark.parametrize(
    "pair",
    [("public.kern2.V", "A"), ("V", "public.kern1.A")],
)
def test_writeKerning_group_on_wrong_side(ufo_path, pair):
    with UFOWriter(ufo_path) as writer:
        writer.writeKerning({("A", "V"): -40})
        with pytest.raises(UFOLibError):
            writer.writeKerning({pair: -80})
        assert writer.readKerning() == {("A", "V"): -40}
        writer.writeKerning({pair: -80}, validate=False)

    with UFOReader(ufo_path) as reader:
        assert reader.readKerning(validate=False) == {pair: -80}


@pytest.mark.parametrize(
    "pair",
    [
        ("A", "V"),
        ("public.kern1.A", "public.kern2.V"),
        ("public.kern2x.A", "public.kern1x.V"),
        ("public.kern1.MissingA", "public.kern2.MissingV"),
    ],
)
def test_kerning_group_sides_roundtrip(ufo_path, pair):
    with UFOWriter(ufo_path) as writer:
        writer.writeGroups({"public.kern1.A": ["A"], "public.kern2.V": ["V"]})
        writer.writeKerning({pair: -80})

    with UFOReader(ufo_path) as reader:
        assert reader.readKerning() == {pair: -80}


@pytest.mark.parametrize("format_version", [1, 2])
def test_kerning_legacy_group_names(tmp_path, format_version):
    ufo_path = tmp_path / "LegacyFont.ufo"
    with UFOWriter(ufo_path, formatVersion=format_version) as writer:
        glyphs = writer.getGlyphSet()
        for name in ("A", "V"):
            glyphs.writeGlyph(name)
        glyphs.writeContents()
        writer.writeGroups({"public.kern2.V": ["V"]})
        writer.writeKerning({("public.kern2.V", "A"): -80})

    with UFOReader(ufo_path) as reader:
        first_group = next(
            name
            for name, members in reader.readGroups().items()
            if name.startswith("public.kern1.") and members == ["V"]
        )
        assert reader.readKerning() == {(first_group, "A"): -80}


def test_formatVersion_deprecated(ufo_path):
    reader = UFOReader(ufo_path)

    with pytest.warns(DeprecationWarning) as warnings:
        assert reader.formatVersion == 3

    assert len(warnings) == 1


def test_formatVersionTuple(ufo_path):
    reader = UFOReader(ufo_path)

    assert reader.formatVersionTuple == (3, 0)
    assert reader.formatVersionTuple.major == 3
    assert reader.formatVersionTuple.minor == 0
    assert str(reader.formatVersionTuple) == "3.0"


def test_readMetaInfo_errors(ufo_path):
    (ufo_path / "metainfo.plist").unlink()
    with pytest.raises(UFOLibError, match="'metainfo.plist' is missing"):
        UFOReader(ufo_path)

    (ufo_path / "metainfo.plist").write_bytes(plistlib.dumps({}))
    with pytest.raises(UFOLibError, match="Missing required formatVersion"):
        UFOReader(ufo_path)

    (ufo_path / "metainfo.plist").write_bytes(plistlib.dumps([]))
    with pytest.raises(UFOLibError, match="metainfo.plist is not properly formatted"):
        UFOReader(ufo_path)


def test_readMetaInfo_unsupported_format_version(ufo_path, caplog):
    metainfo = {"formatVersion": 10, "formatVersionMinor": 15}
    (ufo_path / "metainfo.plist").write_bytes(plistlib.dumps(metainfo))

    with pytest.raises(UnsupportedUFOFormat):
        UFOReader(ufo_path)  # validate=True by default

    with pytest.raises(UnsupportedUFOFormat):
        UFOReader(ufo_path, validate=True)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="fontTools.ufoLib"):
        UFOReader(ufo_path, validate=False)

    assert len(caplog.records) == 1
    assert "Unsupported UFO format" in caplog.text
    assert "Assuming the latest supported version" in caplog.text


def test_UFOWriter_formatVersion(tmp_path):
    ufo_path = tmp_path / "TestFont.ufo"
    with UFOWriter(ufo_path, formatVersion=3) as writer:
        assert writer.formatVersionTuple == (3, 0)

    shutil.rmtree(str(ufo_path))
    with UFOWriter(ufo_path, formatVersion=(2, 0)) as writer:
        assert writer.formatVersionTuple == (2, 0)


def test_UFOWriter_formatVersion_default_latest(tmp_path):
    writer = UFOWriter(tmp_path / "TestFont.ufo")
    assert writer.formatVersionTuple == UFOFormatVersion.default()


def test_UFOWriter_unsupported_format_version(tmp_path):
    with pytest.raises(UnsupportedUFOFormat):
        UFOWriter(tmp_path, formatVersion=(123, 456))


def test_UFOWriter_previous_higher_format_version(ufo_path):
    with pytest.raises(
        UnsupportedUFOFormat, match="UFO located at this path is a higher version"
    ):
        UFOWriter(ufo_path, formatVersion=(2, 0))


def test_getFileModificationTime(ufo_path):
    import time

    with UFOWriter(ufo_path) as writer:
        raw_metainfo = writer.readBytesFromPath("metainfo.plist")
        modified = writer.getFileModificationTime("metainfo.plist")
        assert isinstance(modified, float)
        # writeBytesToPath only modifies a file if the content to be written is not the same
        writer.writeBytesToPath("metainfo.plist", raw_metainfo)
        assert writer.getFileModificationTime("metainfo.plist") == modified
        time.sleep(0.1)
        writer.writeBytesToPath("metainfo.plist", raw_metainfo + b"\n")
        assert writer.getFileModificationTime("metainfo.plist") != modified
