from fontTools.ttLib import TTLibError
from fontTools.ttLib.tables._g_a_s_p import table__g_a_s_p

import pytest


def test_decompile_valid_gasp():
    gasp = table__g_a_s_p()
    # version 1, 2 ranges
    data = b"\x00\x01\x00\x02" + b"\x00\x08\x00\x03" + b"\xff\xff\x00\x03"
    gasp.decompile(data, ttFont=None)
    assert gasp.version == 1
    assert gasp.gaspRange == {8: 3, 0xFFFF: 3}


def test_decompile_truncated_header():
    gasp = table__g_a_s_p()
    with pytest.raises(TTLibError, match="Not enough 'gasp' table data"):
        gasp.decompile(b"\x00\x01", ttFont=None)


def test_decompile_unknown_version():
    gasp = table__g_a_s_p()
    with pytest.raises(TTLibError, match="unknown 'gasp' format: 255"):
        # version 0x00ff == 255
        gasp.decompile(b"\x00\xff\x00\x00", ttFont=None)


def test_decompile_truncated_range():
    gasp = table__g_a_s_p()
    # claims 2 ranges but only 1 range of data
    data = b"\x00\x01\x00\x02" + b"\x00\x08\x00\x03"
    with pytest.raises(TTLibError, match="Not enough 'gasp' table data"):
        gasp.decompile(data, ttFont=None)


def test_decompile_excess_data():
    gasp = table__g_a_s_p()
    # 1 range plus 2 trailing bytes
    data = b"\x00\x01\x00\x01" + b"\x00\x08\x00\x03" + b"\x00\x00"
    with pytest.raises(TTLibError, match="too much 'gasp' table data"):
        gasp.decompile(data, ttFont=None)


def test_compile_roundtrip():
    gasp = table__g_a_s_p()
    # compile() recomputes the version from the behavior bits: 3 has no
    # symmetric-smoothing bits, so the round-tripped version is 0.
    data = b"\x00\x00\x00\x02" + b"\x00\x08\x00\x03" + b"\xff\xff\x00\x03"
    gasp.decompile(data, ttFont=None)
    assert gasp.compile(ttFont=None) == data
