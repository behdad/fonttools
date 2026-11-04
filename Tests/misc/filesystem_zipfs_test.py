import zipfile

import pytest

from fontTools.misc.filesystem._zipfs import ReadZipFS, WriteZipFS


@pytest.mark.parametrize("suffix", [".zip", ".ufoz"])
def test_writezipfs_repeated_close(tmp_path, suffix):
    path = tmp_path / f"archive{suffix}"
    fs = WriteZipFS(path)
    fs.writebytes("hello.txt", b"hello")
    fs.close()
    archive = path.read_bytes()

    fs.close()

    assert fs.isclosed()
    assert path.read_bytes() == archive
    with zipfile.ZipFile(path) as zf:
        assert zf.read("hello.txt") == b"hello"


@pytest.mark.parametrize("suffix", [".zip", ".ufoz"])
def test_writezipfs_explicit_close_in_context_manager(tmp_path, suffix):
    path = tmp_path / f"archive{suffix}"
    with WriteZipFS(path) as fs:
        fs.writebytes("hello.txt", b"hello")
        fs.close()

    assert fs.isclosed()
    with zipfile.ZipFile(path) as zf:
        assert zf.read("hello.txt") == b"hello"


@pytest.mark.parametrize("suffix", [".ufoz", ".ZIP", ""])
def test_writezipfs_preserves_sibling_archive(tmp_path, suffix):
    path = tmp_path / f"archive{suffix}"
    sibling = tmp_path / "archive.zip"
    with zipfile.ZipFile(sibling, "w") as zf:
        zf.writestr("original.txt", b"keep this archive")
    original = sibling.read_bytes()
    if path.exists():
        pytest.skip("Output and sibling names alias on this filesystem")

    with WriteZipFS(path) as fs:
        fs.writebytes("hello.txt", b"hello")

    assert sibling.exists()
    assert sibling.read_bytes() == original
    with zipfile.ZipFile(path) as zf:
        assert zf.namelist() == ["hello.txt"]
        assert zf.read("hello.txt") == b"hello"


@pytest.mark.parametrize("suffix", [".zip", ".ufoz", ".ZIP", ""])
def test_writezipfs_creates_output_parent(tmp_path, suffix):
    path = tmp_path / "new" / f"archive{suffix}"
    with WriteZipFS(path) as fs:
        fs.writebytes("hello.txt", b"hello")
    with zipfile.ZipFile(path) as zf:
        assert zf.read("hello.txt") == b"hello"


@pytest.mark.parametrize("suffix", [".zip", ".ufoz", ".ZIP", ""])
def test_writezipfs_stages_beside_destination(tmp_path, monkeypatch, suffix):
    from pathlib import Path
    from fontTools.misc.filesystem import _zipfs

    path = tmp_path / "new" / f"archive{suffix}"
    replace = _zipfs.os.replace
    replacements = []

    def checked_replace(source, destination):
        source = Path(source)
        assert source.parent.parent == path.parent
        assert Path(destination) == path
        replacements.append(source)
        return replace(source, destination)

    monkeypatch.setattr(_zipfs.os, "replace", checked_replace)
    with WriteZipFS(path) as fs:
        fs.writebytes("hello.txt", b"hello")

    assert len(replacements) == 1
    assert not replacements[0].parent.exists()
    with zipfile.ZipFile(path) as zf:
        assert zf.read("hello.txt") == b"hello"


@pytest.mark.parametrize("suffix", [".zip", ".ufoz", ".ZIP", ""])
def test_writezipfs_archive_failure_preserves_destination(
    tmp_path, monkeypatch, suffix
):
    from pathlib import Path
    from fontTools.misc.filesystem import _zipfs

    path = tmp_path / f"archive{suffix}"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("original.txt", b"keep this archive")
    original = path.read_bytes()
    staged = []

    def fail_archive(base_name, **kwargs):
        partial = Path(base_name + ".zip")
        partial.write_bytes(b"partial archive")
        staged.append(partial)
        raise OSError("archive creation failed")

    fs = WriteZipFS(path)
    fs.writebytes("hello.txt", b"hello")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(_zipfs.shutil, "make_archive", fail_archive)
            with pytest.raises(OSError, match="archive creation failed"):
                fs.close()
        assert path.read_bytes() == original
        assert not fs.isclosed()
        assert not staged[0].exists()
    finally:
        fs.clean()


@pytest.mark.parametrize("suffix", [".zip", ".ufoz"])
def test_writezipfs_overwrites_open_archive(tmp_path, suffix):
    path = tmp_path / f"archive{suffix}"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("original.txt", b"original")

    with ReadZipFS(path) as reader:
        assert reader.readbytes("original.txt") == b"original"
        with WriteZipFS(path) as writer:
            writer.writebytes("updated.txt", b"updated")

    assert [p.name for p in tmp_path.iterdir()] == [path.name]
    with ReadZipFS(path) as reader:
        assert reader.listdir("/") == ["updated.txt"]
        assert reader.readbytes("updated.txt") == b"updated"
