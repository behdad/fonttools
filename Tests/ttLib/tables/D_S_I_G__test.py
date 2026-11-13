import struct

from fontTools.ttLib import TTLibError
from fontTools.ttLib.tables.D_S_I_G_ import table_D_S_I_G_

import pytest


def make_header(version=1, num_sigs=0, flag=0):
    return struct.pack(">LHH", version, num_sigs, flag)


def test_decompile_empty_header():
    dsig = table_D_S_I_G_()
    dsig.decompile(make_header(), ttFont=None)
    assert dsig.ulVersion == 1
    assert dsig.usNumSigs == 0
    assert dsig.usFlag == 0
    assert dsig.signatureRecords == []


def test_decompile_bad_version():
    dsig = table_D_S_I_G_()
    with pytest.raises(TTLibError, match="invalid DSIG ulVersion: 0"):
        dsig.decompile(make_header(version=0), ttFont=None)


def test_decompile_bad_usFlag():
    dsig = table_D_S_I_G_()
    with pytest.raises(TTLibError, match="invalid DSIG usFlag"):
        dsig.decompile(make_header(flag=2), ttFont=None)


def test_decompile_bad_record_format():
    dsig = table_D_S_I_G_()
    # one signature record with ulFormat=0
    data = make_header(num_sigs=1) + struct.pack(">LLL", 0, 0, 0)
    with pytest.raises(TTLibError, match="invalid DSIG signature record #0 ulFormat"):
        dsig.decompile(data, ttFont=None)


def test_decompile_out_of_range_offset():
    dsig = table_D_S_I_G_()
    # one signature record pointing past the table
    data = make_header(num_sigs=1) + struct.pack(">LLL", 1, 20, 100)
    with pytest.raises(TTLibError, match="invalid DSIG signature record #0 ulOffset"):
        dsig.decompile(data, ttFont=None)


def test_decompile_bad_reserved():
    dsig = table_D_S_I_G_()
    # header (8 bytes) + record (12 bytes) + block at offset 20 with usReserved1=1
    data = (
        make_header(num_sigs=1)
        + struct.pack(">LLL", 1, 10, 20)
        + struct.pack(">HHl", 1, 0, 0)
    )
    with pytest.raises(TTLibError, match="usReserved1"):
        dsig.decompile(data, ttFont=None)


def test_compile_roundtrip():
    dsig = table_D_S_I_G_()
    # 4-byte pkcs7 keeps the table length even, so compile() adds no pad byte
    pkcs7 = b"\x01\x02\x03\x04"
    block_size = struct.calcsize(">HHl")  # DSIG_SignatureBlockFormat is 8 bytes
    data = (
        make_header(num_sigs=1, flag=1)
        + struct.pack(">LLL", 1, block_size + len(pkcs7), 20)
        + struct.pack(">HHl", 0, 0, len(pkcs7))
        + pkcs7
    )
    dsig.decompile(data, ttFont=None)
    assert dsig.signatureRecords[0].pkcs7 == pkcs7
    assert dsig.compile(ttFont=None) == data
