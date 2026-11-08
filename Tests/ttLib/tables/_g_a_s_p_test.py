import io

from fontTools.misc.testTools import getXML, parseXML
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_a_s_p import table__g_a_s_p
import pytest

GASP_DATA = bytes.fromhex("0001 0002 0008 0002 ffff 000f")

GASP_XML = [
    '<gaspRange rangeMaxPPEM="8" rangeGaspBehavior="2"/>',
    '<gaspRange rangeMaxPPEM="65535" rangeGaspBehavior="15"/>',
]


@pytest.fixture
def font():
    return TTFont()


def test_decompile_and_compile(font):
    table = table__g_a_s_p()
    table.decompile(GASP_DATA, font)
    assert table.gaspRange == {8: 2, 65535: 15}
    assert table.compile(font) == GASP_DATA


def test_round_trip_xml(font):
    table = table__g_a_s_p()
    table.decompile(GASP_DATA, font)
    assert getXML(table.toXML, font) == GASP_XML

    table = table__g_a_s_p()
    for name, attrs, content in parseXML(GASP_XML):
        table.fromXML(name, attrs, content, font)
    assert table.compile(font) == GASP_DATA


def test_round_trip_ttx_empty(font):
    font["gasp"] = table = table__g_a_s_p()
    table.decompile(b"\x00\x01\x00\x00", font)
    assert table.gaspRange == {}

    # the empty table is dumped without any child elements
    buf = io.StringIO()
    font.saveXML(buf, tables=["gasp"])
    font = TTFont()
    font.importXML(io.StringIO(buf.getvalue()))

    assert font["gasp"].gaspRange == {}
    assert font["gasp"].compile(font) == b"\x00\x00\x00\x00"
