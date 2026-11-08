from fontTools.misc.loggingTools import CapturingLogHandler
from fontTools.misc.testTools import parseXML, getXML
from fontTools.misc.textTools import deHexStr
from fontTools.ttLib import TTFont, newTable
from fontTools.misc.fixedTools import log
import os
import unittest

CURR_DIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
DATA_DIR = os.path.join(CURR_DIR, "data")

VHEA_DATA_VERSION_11 = deHexStr(
    "0001 1000 "  # 1.1   version
    "01F4 "  # 500   ascent
    "FE0C "  # -500  descent
    "0000 "  # 0     lineGap
    "0BB8 "  # 3000  advanceHeightMax
    "FC16 "  # -1002 minTopSideBearing
    "FD5B "  # -677  minBottomSideBearing
    "0B70 "  # 2928  yMaxExtent
    "0000 "  # 0     caretSlopeRise
    "0001 "  # 1     caretSlopeRun
    "0000 "  # 0     caretOffset
    "0000 "  # 0     reserved1
    "0000 "  # 0     reserved2
    "0000 "  # 0     reserved3
    "0000 "  # 0     reserved4
    "0000 "  # 0     metricDataFormat
    "000C "  # 12    numberOfVMetrics
)

VHEA_DATA_VERSION_10 = deHexStr("00010000") + VHEA_DATA_VERSION_11[4:]

VHEA_VERSION_11_AS_DICT = {
    "tableTag": "vhea",
    "tableVersion": 0x00011000,
    "ascent": 500,
    "descent": -500,
    "lineGap": 0,
    "advanceHeightMax": 3000,
    "minTopSideBearing": -1002,
    "minBottomSideBearing": -677,
    "yMaxExtent": 2928,
    "caretSlopeRise": 0,
    "caretSlopeRun": 1,
    "caretOffset": 0,
    "reserved1": 0,
    "reserved2": 0,
    "reserved3": 0,
    "reserved4": 0,
    "metricDataFormat": 0,
    "numberOfVMetrics": 12,
}

VHEA_VERSION_10_AS_DICT = dict(VHEA_VERSION_11_AS_DICT)
VHEA_VERSION_10_AS_DICT["tableVersion"] = 0x00010000

VHEA_XML_VERSION_11 = [
    '<tableVersion value="0x00011000"/>',
    '<ascent value="500"/>',
    '<descent value="-500"/>',
    '<lineGap value="0"/>',
    '<advanceHeightMax value="3000"/>',
    '<minTopSideBearing value="-1002"/>',
    '<minBottomSideBearing value="-677"/>',
    '<yMaxExtent value="2928"/>',
    '<caretSlopeRise value="0"/>',
    '<caretSlopeRun value="1"/>',
    '<caretOffset value="0"/>',
    '<reserved1 value="0"/>',
    '<reserved2 value="0"/>',
    '<reserved3 value="0"/>',
    '<reserved4 value="0"/>',
    '<metricDataFormat value="0"/>',
    '<numberOfVMetrics value="12"/>',
]

VHEA_XML_VERSION_11_AS_FLOAT = [
    '<tableVersion value="1.0625"/>',
] + VHEA_XML_VERSION_11[1:]

VHEA_XML_VERSION_10 = [
    '<tableVersion value="0x00010000"/>',
] + VHEA_XML_VERSION_11[1:]

VHEA_XML_VERSION_10_AS_FLOAT = [
    '<tableVersion value="1.0"/>',
] + VHEA_XML_VERSION_11[1:]


class VheaCompileOrToXMLTest(unittest.TestCase):
    def setUp(self):
        vhea = newTable("vhea")
        vhea.tableVersion = 0x00010000
        vhea.ascent = 500
        vhea.descent = -500
        vhea.lineGap = 0
        vhea.advanceHeightMax = 3000
        vhea.minTopSideBearing = -1002
        vhea.minBottomSideBearing = -677
        vhea.yMaxExtent = 2928
        vhea.caretSlopeRise = 0
        vhea.caretSlopeRun = 1
        vhea.caretOffset = 0
        vhea.metricDataFormat = 0
        vhea.numberOfVMetrics = 12
        vhea.reserved1 = vhea.reserved2 = vhea.reserved3 = vhea.reserved4 = 0
        self.font = TTFont(sfntVersion="OTTO")
        self.font["vhea"] = vhea

    def test_compile_caretOffset_as_reserved0(self):
        vhea = self.font["vhea"]
        del vhea.caretOffset
        vhea.reserved0 = 0
        self.assertEqual(VHEA_DATA_VERSION_10, vhea.compile(self.font))

    def test_compile_version_10(self):
        vhea = self.font["vhea"]
        vhea.tableVersion = 0x00010000
        self.assertEqual(VHEA_DATA_VERSION_10, vhea.compile(self.font))

    def test_compile_version_10_as_float(self):
        vhea = self.font["vhea"]
        vhea.tableVersion = 1.0
        with CapturingLogHandler(log, "WARNING") as captor:
            self.assertEqual(VHEA_DATA_VERSION_10, vhea.compile(self.font))
        self.assertTrue(
            len(
                [r for r in captor.records if "Table version value is a float" in r.msg]
            )
            == 1
        )

    def test_compile_version_11(self):
        vhea = self.font["vhea"]
        vhea.tableVersion = 0x00011000
        self.assertEqual(VHEA_DATA_VERSION_11, vhea.compile(self.font))

    def test_compile_version_11_as_float(self):
        vhea = self.font["vhea"]
        vhea.tableVersion = 1.0625
        with CapturingLogHandler(log, "WARNING") as captor:
            self.assertEqual(VHEA_DATA_VERSION_11, vhea.compile(self.font))
        self.assertTrue(
            len(
                [r for r in captor.records if "Table version value is a float" in r.msg]
            )
            == 1
        )

    def test_toXML_caretOffset_as_reserved0(self):
        vhea = self.font["vhea"]
        del vhea.caretOffset
        vhea.reserved0 = 0
        self.assertEqual(getXML(vhea.toXML), VHEA_XML_VERSION_10)

    def test_toXML_version_10(self):
        vhea = self.font["vhea"]
        self.font["vhea"].tableVersion = 0x00010000
        self.assertEqual(getXML(vhea.toXML), VHEA_XML_VERSION_10)

    def test_toXML_version_10_as_float(self):
        vhea = self.font["vhea"]
        vhea.tableVersion = 1.0
        with CapturingLogHandler(log, "WARNING") as captor:
            self.assertEqual(getXML(vhea.toXML), VHEA_XML_VERSION_10)
        self.assertTrue(
            len(
                [r for r in captor.records if "Table version value is a float" in r.msg]
            )
            == 1
        )

    def test_toXML_version_11(self):
        vhea = self.font["vhea"]
        self.font["vhea"].tableVersion = 0x00011000
        self.assertEqual(getXML(vhea.toXML), VHEA_XML_VERSION_11)

    def test_toXML_version_11_as_float(self):
        vhea = self.font["vhea"]
        vhea.tableVersion = 1.0625
        with CapturingLogHandler(log, "WARNING") as captor:
            self.assertEqual(getXML(vhea.toXML), VHEA_XML_VERSION_11)
        self.assertTrue(
            len(
                [r for r in captor.records if "Table version value is a float" in r.msg]
            )
            == 1
        )


class VheaDecompileOrFromXMLTest(unittest.TestCase):
    def setUp(self):
        vhea = newTable("vhea")
        self.font = TTFont(sfntVersion="OTTO")
        self.font["vhea"] = vhea

    def test_decompile_version_10(self):
        vhea = self.font["vhea"]
        vhea.decompile(VHEA_DATA_VERSION_10, self.font)
        for key in vhea.__dict__:
            self.assertEqual(getattr(vhea, key), VHEA_VERSION_10_AS_DICT[key])

    def test_decompile_version_11(self):
        vhea = self.font["vhea"]
        vhea.decompile(VHEA_DATA_VERSION_11, self.font)
        for key in vhea.__dict__:
            self.assertEqual(getattr(vhea, key), VHEA_VERSION_11_AS_DICT[key])

    def test_fromXML_version_10(self):
        vhea = self.font["vhea"]
        for name, attrs, content in parseXML(VHEA_XML_VERSION_10):
            vhea.fromXML(name, attrs, content, self.font)
        for key in vhea.__dict__:
            self.assertEqual(getattr(vhea, key), VHEA_VERSION_10_AS_DICT[key])

    def test_fromXML_version_10_as_float(self):
        vhea = self.font["vhea"]
        with CapturingLogHandler(log, "WARNING") as captor:
            for name, attrs, content in parseXML(VHEA_XML_VERSION_10_AS_FLOAT):
                vhea.fromXML(name, attrs, content, self.font)
        self.assertTrue(
            len(
                [r for r in captor.records if "Table version value is a float" in r.msg]
            )
            == 1
        )
        for key in vhea.__dict__:
            self.assertEqual(getattr(vhea, key), VHEA_VERSION_10_AS_DICT[key])

    def test_fromXML_version_11(self):
        vhea = self.font["vhea"]
        for name, attrs, content in parseXML(VHEA_XML_VERSION_11):
            vhea.fromXML(name, attrs, content, self.font)
        for key in vhea.__dict__:
            self.assertEqual(getattr(vhea, key), VHEA_VERSION_11_AS_DICT[key])

    def test_fromXML_version_11_as_float(self):
        vhea = self.font["vhea"]
        with CapturingLogHandler(log, "WARNING") as captor:
            for name, attrs, content in parseXML(VHEA_XML_VERSION_11_AS_FLOAT):
                vhea.fromXML(name, attrs, content, self.font)
        self.assertTrue(
            len(
                [r for r in captor.records if "Table version value is a float" in r.msg]
            )
            == 1
        )
        for key in vhea.__dict__:
            self.assertEqual(getattr(vhea, key), VHEA_VERSION_11_AS_DICT[key])


class VheaRecalcTest(unittest.TestCase):
    def test_recalc_TTF(self):
        font = TTFont()
        font.importXML(os.path.join(DATA_DIR, "_v_h_e_a_recalc_TTF.ttx"))
        vhea = font["vhea"]
        vhea.recalc(font)
        self.assertEqual(vhea.advanceHeightMax, 900)
        self.assertEqual(vhea.minTopSideBearing, 200)
        self.assertEqual(vhea.minBottomSideBearing, 377)
        self.assertEqual(vhea.yMaxExtent, 312)

    def test_recalc_OTF(self):
        font = TTFont()
        font.importXML(os.path.join(DATA_DIR, "_v_h_e_a_recalc_OTF.ttx"))
        vhea = font["vhea"]
        vhea.recalc(font)
        self.assertEqual(vhea.advanceHeightMax, 900)
        self.assertEqual(vhea.minTopSideBearing, 200)
        self.assertEqual(vhea.minBottomSideBearing, 377)
        self.assertEqual(vhea.yMaxExtent, 312)

    def test_recalc_empty(self):
        font = TTFont()
        font.importXML(os.path.join(DATA_DIR, "_v_h_e_a_recalc_empty.ttx"))
        vhea = font["vhea"]
        vhea.recalc(font)
        self.assertEqual(vhea.advanceHeightMax, 900)
        self.assertEqual(vhea.minTopSideBearing, 0)
        self.assertEqual(vhea.minBottomSideBearing, 0)
        self.assertEqual(vhea.yMaxExtent, 0)

    def test_recalc_empty_glyf_shell(self):
        font = TTFont()
        font.importXML(os.path.join(DATA_DIR, "_v_h_e_a_recalc_empty.ttx"))
        font["glyf"] = newTable("glyf")
        vhea = font["vhea"]
        vhea.recalc(font)
        self.assertEqual(vhea.advanceHeightMax, 900)
        self.assertEqual(vhea.minTopSideBearing, 0)
        self.assertEqual(vhea.minBottomSideBearing, 0)
        self.assertEqual(vhea.yMaxExtent, 0)


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
