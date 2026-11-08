from fontTools.misc.loggingTools import CapturingLogHandler
from fontTools.misc.testTools import parseXML, getXML
from fontTools.misc.textTools import deHexStr
from fontTools.ttLib import TTFont, newTable
from fontTools.misc.fixedTools import log
import os
import unittest

CURR_DIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
DATA_DIR = os.path.join(CURR_DIR, "data")

HHEA_DATA = deHexStr(
    "0001 0000 "  # 1.0   version
    "02EE "  # 750   ascent
    "FF06 "  # -250  descent
    "00C8 "  # 200   lineGap
    "03E8 "  # 1000  advanceWidthMax
    "FFE7 "  # -25   minLeftSideBearing
    "FFEC "  # -20   minRightSideBearing
    "03D1 "  # 977   xMaxExtent
    "0000 "  # 0     caretSlopeRise
    "0001 "  # 1     caretSlopeRun
    "0010 "  # 16    caretOffset
    "0000 "  # 0     reserved0
    "0000 "  # 0     reserved1
    "0000 "  # 0     reserved2
    "0000 "  # 0     reserved3
    "0000 "  # 0     metricDataFormat
    "002A "  # 42    numberOfHMetrics
)

HHEA_AS_DICT = {
    "tableTag": "hhea",
    "tableVersion": 0x00010000,
    "ascent": 750,
    "descent": -250,
    "lineGap": 200,
    "advanceWidthMax": 1000,
    "minLeftSideBearing": -25,
    "minRightSideBearing": -20,
    "xMaxExtent": 977,
    "caretSlopeRise": 0,
    "caretSlopeRun": 1,
    "caretOffset": 16,
    "reserved0": 0,
    "reserved1": 0,
    "reserved2": 0,
    "reserved3": 0,
    "metricDataFormat": 0,
    "numberOfHMetrics": 42,
}

HHEA_XML = [
    '<tableVersion value="0x00010000"/>',
    '<ascent value="750"/>',
    '<descent value="-250"/>',
    '<lineGap value="200"/>',
    '<advanceWidthMax value="1000"/>',
    '<minLeftSideBearing value="-25"/>',
    '<minRightSideBearing value="-20"/>',
    '<xMaxExtent value="977"/>',
    '<caretSlopeRise value="0"/>',
    '<caretSlopeRun value="1"/>',
    '<caretOffset value="16"/>',
    '<reserved0 value="0"/>',
    '<reserved1 value="0"/>',
    '<reserved2 value="0"/>',
    '<reserved3 value="0"/>',
    '<metricDataFormat value="0"/>',
    '<numberOfHMetrics value="42"/>',
]

HHEA_XML_VERSION_AS_FLOAT = [
    '<tableVersion value="1.0"/>',
] + HHEA_XML[1:]


class HheaCompileOrToXMLTest(unittest.TestCase):
    def setUp(self):
        hhea = newTable("hhea")
        hhea.tableVersion = 0x00010000
        hhea.ascent = 750
        hhea.descent = -250
        hhea.lineGap = 200
        hhea.advanceWidthMax = 1000
        hhea.minLeftSideBearing = -25
        hhea.minRightSideBearing = -20
        hhea.xMaxExtent = 977
        hhea.caretSlopeRise = 0
        hhea.caretSlopeRun = 1
        hhea.caretOffset = 16
        hhea.metricDataFormat = 0
        hhea.numberOfHMetrics = 42
        hhea.reserved0 = hhea.reserved1 = hhea.reserved2 = hhea.reserved3 = 0
        self.font = TTFont(sfntVersion="OTTO")
        self.font["hhea"] = hhea

    def test_compile(self):
        hhea = self.font["hhea"]
        hhea.tableVersion = 0x00010000
        self.assertEqual(HHEA_DATA, hhea.compile(self.font))

    def test_compile_version_10_as_float(self):
        hhea = self.font["hhea"]
        hhea.tableVersion = 1.0
        with CapturingLogHandler(log, "WARNING") as captor:
            self.assertEqual(HHEA_DATA, hhea.compile(self.font))
        self.assertTrue(
            len(
                [r for r in captor.records if "Table version value is a float" in r.msg]
            )
            == 1
        )

    def test_toXML(self):
        hhea = self.font["hhea"]
        self.font["hhea"].tableVersion = 0x00010000
        self.assertEqual(getXML(hhea.toXML), HHEA_XML)

    def test_toXML_version_as_float(self):
        hhea = self.font["hhea"]
        hhea.tableVersion = 1.0
        with CapturingLogHandler(log, "WARNING") as captor:
            self.assertEqual(getXML(hhea.toXML), HHEA_XML)
        self.assertTrue(
            len(
                [r for r in captor.records if "Table version value is a float" in r.msg]
            )
            == 1
        )

    def test_aliases(self):
        hhea = self.font["hhea"]
        self.assertEqual(hhea.ascent, hhea.ascender)
        self.assertEqual(hhea.descent, hhea.descender)
        hhea.ascender = 800
        self.assertEqual(hhea.ascent, 800)
        hhea.ascent = 750
        self.assertEqual(hhea.ascender, 750)
        hhea.descender = -300
        self.assertEqual(hhea.descent, -300)
        hhea.descent = -299
        self.assertEqual(hhea.descender, -299)


class HheaDecompileOrFromXMLTest(unittest.TestCase):
    def setUp(self):
        hhea = newTable("hhea")
        self.font = TTFont(sfntVersion="OTTO")
        self.font["hhea"] = hhea

    def test_decompile(self):
        hhea = self.font["hhea"]
        hhea.decompile(HHEA_DATA, self.font)
        for key in hhea.__dict__:
            self.assertEqual(getattr(hhea, key), HHEA_AS_DICT[key])

    def test_fromXML(self):
        hhea = self.font["hhea"]
        for name, attrs, content in parseXML(HHEA_XML):
            hhea.fromXML(name, attrs, content, self.font)
        for key in hhea.__dict__:
            self.assertEqual(getattr(hhea, key), HHEA_AS_DICT[key])

    def test_fromXML_version_as_float(self):
        hhea = self.font["hhea"]
        with CapturingLogHandler(log, "WARNING") as captor:
            for name, attrs, content in parseXML(HHEA_XML_VERSION_AS_FLOAT):
                hhea.fromXML(name, attrs, content, self.font)
        self.assertTrue(
            len(
                [r for r in captor.records if "Table version value is a float" in r.msg]
            )
            == 1
        )
        for key in hhea.__dict__:
            self.assertEqual(getattr(hhea, key), HHEA_AS_DICT[key])


class HheaRecalcTest(unittest.TestCase):
    def test_recalc_TTF(self):
        font = TTFont()
        font.importXML(os.path.join(DATA_DIR, "_h_h_e_a_recalc_TTF.ttx"))
        hhea = font["hhea"]
        hhea.recalc(font)
        self.assertEqual(hhea.advanceWidthMax, 600)
        self.assertEqual(hhea.minLeftSideBearing, -56)
        self.assertEqual(hhea.minRightSideBearing, 100)
        self.assertEqual(hhea.xMaxExtent, 400)

    def test_recalc_OTF(self):
        font = TTFont()
        font.importXML(os.path.join(DATA_DIR, "_h_h_e_a_recalc_OTF.ttx"))
        hhea = font["hhea"]
        hhea.recalc(font)
        self.assertEqual(hhea.advanceWidthMax, 600)
        self.assertEqual(hhea.minLeftSideBearing, -56)
        self.assertEqual(hhea.minRightSideBearing, 100)
        self.assertEqual(hhea.xMaxExtent, 400)

    def test_recalc_empty(self):
        font = TTFont()
        font.importXML(os.path.join(DATA_DIR, "_h_h_e_a_recalc_empty.ttx"))
        hhea = font["hhea"]
        hhea.recalc(font)
        self.assertEqual(hhea.advanceWidthMax, 600)
        self.assertEqual(hhea.minLeftSideBearing, 0)
        self.assertEqual(hhea.minRightSideBearing, 0)
        self.assertEqual(hhea.xMaxExtent, 0)

    def test_recalc_empty_glyf_shell(self):
        font = TTFont()
        font.importXML(os.path.join(DATA_DIR, "_h_h_e_a_recalc_empty.ttx"))
        font["glyf"] = newTable("glyf")
        hhea = font["hhea"]
        hhea.recalc(font)
        self.assertEqual(hhea.advanceWidthMax, 600)
        self.assertEqual(hhea.minLeftSideBearing, 0)
        self.assertEqual(hhea.minRightSideBearing, 0)
        self.assertEqual(hhea.xMaxExtent, 0)


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
