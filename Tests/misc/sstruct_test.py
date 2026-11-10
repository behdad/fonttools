from fontTools.misc import sstruct
import pytest


@pytest.fixture(autouse=True)
def clear_format_cache():
    sstruct._formatcache.clear()
    yield
    sstruct._formatcache.clear()


@pytest.mark.parametrize("warmup", [None, "pack", "unpack", "calcsize", "keep_padding"])
def test_named_padding_roundtrip(warmup):
    fmt = ">; first:B; padding:x; last:H"
    values = {"first": 1, "last": 0x0203}
    encoded = b"\x01\x00\x02\x03"
    if warmup == "pack":
        sstruct.pack(fmt, values)
    elif warmup == "unpack":
        sstruct.unpack(fmt, encoded)
    elif warmup == "calcsize":
        sstruct.calcsize(fmt)
    elif warmup == "keep_padding":
        sstruct.getformat(fmt, keep_pad_byte=True)

    assert sstruct.pack(fmt, values) == encoded
    assert sstruct.unpack(fmt, encoded) == values
    assert sstruct.calcsize(fmt) == 4
    assert sstruct.unpack2(fmt, encoded + b"rest") == (values, b"rest")


@pytest.mark.parametrize("keep_first", [False, True])
def test_padding_format_cache_respects_flag(keep_first):
    fmt = ">; first:B; padding:x; last:H"
    for keep in [keep_first, not keep_first, keep_first]:
        formatstring, names, fixes = sstruct.getformat(fmt, keep_pad_byte=keep)
        assert formatstring == ">BxH"
        assert list(names) == (
            ["first", "padding", "last"] if keep else ["first", "last"]
        )
        assert fixes == {}


def test_unnamed_padding_and_fixed_point_roundtrip():
    fmt = ">; x; first:8.8F; padding:x; last:B; x"
    values = {"first": 1.5, "last": 2}
    assert sstruct.pack(fmt, values) == b"\x00\x01\x80\x00\x02\x00"
    assert sstruct.unpack(fmt, sstruct.pack(fmt, values)) == values
