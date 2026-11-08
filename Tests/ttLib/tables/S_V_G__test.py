import gzip
import io
import struct

from fontTools.misc import etree
from fontTools.misc.testTools import getXML, parseXML
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.S_V_G_ import table_S_V_G_

import pytest


def dump(table, ttFont=None):
    print("\n".join(getXML(table.toXML, ttFont)))


def compress(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(None, "w", fileobj=buf, mtime=0) as gz:
        gz.write(data)
    return buf.getvalue()


def strip_xml_whitespace(xml_string):
    def strip_or_none(text):
        text = text.strip() if text else None
        return text if text else None

    tree = etree.fromstring(xml_string)
    for e in tree.iter("*"):
        e.text = strip_or_none(e.text)
        e.tail = strip_or_none(e.tail)
    return etree.tostring(tree, encoding="utf-8")


SVG_DOCS = [
    strip_xml_whitespace(svg)
    for svg in (
        b"""\
        <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1">
          <defs>
            <rect x="100" y="-200" width="300" height="400" id="p1"/>
          </defs>
          <g id="glyph1">
            <use xlink:href="#p1" fill="#red"/>
          </g>
          <g id="glyph2">
            <use xlink:href="#p1" fill="#blue"/>
          </g>
          <g id="glyph4">
            <use xlink:href="#p1" fill="#green"/>
          </g>
        </svg>""",
        b"""\
        <svg xmlns="http://www.w3.org/2000/svg" version="1.1">
          <g id="glyph3">
            <path d="M0,0 L100,0 L50,100 Z" fill="#red"/>
            <path d="M10,10 L110,10 L60,110 Z" fill="#blue"/>
            <path d="M20,20 L120,20 L70,120 Z" fill="#green"/>
          </g>
        </svg>""",
    )
]


OTSVG_DATA = b"".join(
    [
        # SVG table header
        b"\x00\x00"  # version (0)
        b"\x00\x00\x00\x0a"  # offset to SVGDocumentList (10)
        b"\x00\x00\x00\x00"  # reserved (0)
        #  SVGDocumentList
        b"\x00\x03"  # number of SVGDocumentRecords (3)
        # SVGDocumentRecord[0]
        b"\x00\x01"  # startGlyphID (1)
        b"\x00\x02"  # endGlyphID (2)
        b"\x00\x00\x00\x26"  # svgDocOffset (2 + 12*3 == 38 == 0x26)
        + struct.pack(">L", len(SVG_DOCS[0]))  # svgDocLength
        # SVGDocumentRecord[1] (compressed)
        + b"\x00\x03"  # startGlyphID (3)
        b"\x00\x03"  # endGlyphID (3)
        + struct.pack(">L", 0x26 + len(SVG_DOCS[0]))  # svgDocOffset
        + struct.pack(">L", len(compress(SVG_DOCS[1])))  # svgDocLength
        # SVGDocumentRecord[2]
        + b"\x00\x04"  # startGlyphID (4)
        b"\x00\x04"  # endGlyphID (4)
        b"\x00\x00\x00\x26"  # svgDocOffset (38); records 0 and 2 point to same SVG doc
        + struct.pack(">L", len(SVG_DOCS[0]))  # svgDocLength
    ]
    + [SVG_DOCS[0], compress(SVG_DOCS[1])]
)

OTSVG_TTX = [
    '<svgDoc endGlyphID="2" startGlyphID="1">',
    f"  <![CDATA[{SVG_DOCS[0].decode()}]]>",
    "</svgDoc>",
    '<svgDoc compressed="1" endGlyphID="3" startGlyphID="3">',
    f"  <![CDATA[{SVG_DOCS[1].decode()}]]>",
    "</svgDoc>",
    '<svgDoc endGlyphID="4" startGlyphID="4">',
    f"  <![CDATA[{SVG_DOCS[0].decode()}]]>",
    "</svgDoc>",
]


@pytest.fixture
def font():
    font = TTFont()
    font.setGlyphOrder([".notdef"] + ["glyph%05d" % i for i in range(1, 30)])
    return font


def test_decompile_and_compile(font):
    table = table_S_V_G_()
    table.decompile(OTSVG_DATA, font)
    assert table.compile(font) == OTSVG_DATA


def test_decompile_and_dump_ttx(font):
    table = table_S_V_G_()
    table.decompile(OTSVG_DATA, font)

    dump(table, font)
    assert getXML(table.toXML, font) == OTSVG_TTX


def test_load_from_ttx_and_compile(font):
    table = table_S_V_G_()
    for name, attrs, content in parseXML(OTSVG_TTX):
        table.fromXML(name, attrs, content, font)
    assert table.compile(font) == OTSVG_DATA


def test_round_trip_ttx(font):
    table = table_S_V_G_()
    for name, attrs, content in parseXML(OTSVG_TTX):
        table.fromXML(name, attrs, content, font)
    compiled = table.compile(font)

    table = table_S_V_G_()
    table.decompile(compiled, font)
    assert getXML(table.toXML, font) == OTSVG_TTX


def test_round_trip_ttx_empty(font):
    font["SVG "] = table = table_S_V_G_()
    table.decompile(struct.pack(">HLLH", 0, 10, 0, 0), font)
    assert table.docList == []

    # the empty table is dumped without any child elements
    buf = io.StringIO()
    font.saveXML(buf, tables=["SVG "])
    font = TTFont()
    font.importXML(io.StringIO(buf.getvalue()))

    assert font["SVG "].docList == []
    table = table_S_V_G_()
    table.decompile(font["SVG "].compile(font), font)
    assert table.docList == []


def test_round_trip_ttx_doc_containing_cdata_end(font):
    # a document containing "]]>" must not escape the CDATA section it is
    # written into, or the dump reads back as different tables
    doc = (
        ']]></svgDoc></SVG><name><namerecord nameID="6" platformID="3" '
        'platEncID="1" langID="0x409">x</namerecord></name>'
        '<SVG><svgDoc startGlyphID="1" endGlyphID="1"><![CDATA[y'
    )
    table = table_S_V_G_()
    table.docList = [(doc, 1, 1)]
    xml = getXML(table.toXML, font)

    table = table_S_V_G_()
    for name, attrs, content in parseXML(xml):
        table.fromXML(name, attrs, content, font)

    assert len(table.docList) == 1
    assert table.docList[0].data == doc


def test_unpack_svg_doc_as_3_tuple():
    # test that the legacy docList as list of 3-tuples interface still works
    # even after the new SVGDocument class with extra `compressed` attribute
    # was added
    table = table_S_V_G_()
    table.decompile(OTSVG_DATA, font)

    for doc, compressed in zip(table.docList, (False, True, False)):
        assert len(doc) == 3
        data, startGID, endGID = doc
        assert doc.data == data
        assert doc.startGlyphID == startGID
        assert doc.endGlyphID == endGID
        assert doc.compressed == compressed
