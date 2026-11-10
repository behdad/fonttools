from fontTools.misc.testTools import parseXML
from fontTools.misc.textTools import deHexStr
from fontTools.misc.xmlWriter import XMLWriter
from fontTools.ttLib import TTLibError, TTFont
from fontTools.ttLib.tables._f_v_a_r import table__f_v_a_r, Axis, NamedInstance
from fontTools.ttLib.tables._n_a_m_e import table__n_a_m_e, NameRecord
from io import BytesIO
import unittest

FVAR_DATA = deHexStr(
    "00 01 00 00 00 10 00 02 00 02 00 14 00 02 00 0C "
    "77 67 68 74 00 64 00 00 01 90 00 00 03 84 00 00 00 00 01 01 "
    "77 64 74 68 00 32 00 00 00 64 00 00 00 c8 00 00 00 00 01 02 "
    "01 03 00 00 01 2c 00 00 00 64 00 00 "
    "01 04 00 00 01 2c 00 00 00 4b 00 00"
)

FVAR_AXIS_DATA = deHexStr("6F 70 73 7a ff ff 80 00 00 01 4c cd 00 01 80 00 00 00 01 59")

FVAR_INSTANCE_DATA_WITHOUT_PSNAME = deHexStr("01 59 00 00 00 00 b3 33 00 00 80 00")

FVAR_INSTANCE_DATA_WITH_PSNAME = FVAR_INSTANCE_DATA_WITHOUT_PSNAME + deHexStr("02 34")


def xml_lines(writer):
    content = writer.file.getvalue().decode("utf-8")
    return [line.strip() for line in content.splitlines()][1:]


def AddName(font, name):
    nameTable = font.get("name")
    if nameTable is None:
        nameTable = font["name"] = table__n_a_m_e()
        nameTable.names = []
    namerec = NameRecord()
    namerec.nameID = 1 + max([n.nameID for n in nameTable.names] + [256])
    namerec.string = name.encode("mac_roman")
    namerec.platformID, namerec.platEncID, namerec.langID = (1, 0, 0)
    nameTable.names.append(namerec)
    return namerec


def MakeFont():
    axes = [("wght", "Weight", 100, 400, 900), ("wdth", "Width", 50, 100, 200)]
    instances = [("Light", 300, 100), ("Light Condensed", 300, 75)]
    fvarTable = table__f_v_a_r()
    font = {"fvar": fvarTable}
    for tag, name, minValue, defaultValue, maxValue in axes:
        axis = Axis()
        axis.axisTag = tag
        axis.defaultValue = defaultValue
        axis.minValue, axis.maxValue = minValue, maxValue
        axis.axisNameID = AddName(font, name).nameID
        fvarTable.axes.append(axis)
    for name, weight, width in instances:
        inst = NamedInstance()
        inst.subfamilyNameID = AddName(font, name).nameID
        inst.coordinates = {"wght": weight, "wdth": width}
        fvarTable.instances.append(inst)
    return font


class FontVariationTableTest(unittest.TestCase):
    def test_name_with_hyphens_XML_roundtrip(self):
        font = TTFont()
        for tag, table in MakeFont().items():
            font[tag] = table
        name_id = font["fvar"].axes[0].axisNameID
        font["name"].setName("Weight---Light", name_id, 1, 0, 0)
        output = BytesIO()
        font.saveXML(output, tables=["name", "fvar"])
        restored = TTFont()
        restored.importXML(BytesIO(output.getvalue()))
        self.assertEqual("Weight---Light", restored["name"].getDebugName(name_id))
        self.assertEqual(name_id, restored["fvar"].axes[0].axisNameID)

    def test_compile(self):
        font = MakeFont()
        h = font["fvar"].compile(font)
        self.assertEqual(FVAR_DATA, font["fvar"].compile(font))

    def test_decompile(self):
        fvar = table__f_v_a_r()
        fvar.decompile(FVAR_DATA, ttFont={"fvar": fvar})
        self.assertEqual(["wght", "wdth"], [a.axisTag for a in fvar.axes])
        self.assertEqual([259, 260], [i.subfamilyNameID for i in fvar.instances])

    def test_toXML(self):
        font = MakeFont()
        writer = XMLWriter(BytesIO())
        font["fvar"].toXML(writer, font)
        xml = writer.file.getvalue().decode("utf-8")
        self.assertEqual(2, xml.count("<Axis>"))
        self.assertTrue("<AxisTag>wght</AxisTag>" in xml)
        self.assertTrue("<AxisTag>wdth</AxisTag>" in xml)
        self.assertEqual(2, xml.count("<NamedInstance "))
        self.assertTrue("<!-- Light -->" in xml)
        self.assertTrue("<!-- Light Condensed -->" in xml)

    def test_fromXML(self):
        fvar = table__f_v_a_r()
        for name, attrs, content in parseXML(
            "<Axis>"
            "    <AxisTag>opsz</AxisTag>"
            "</Axis>"
            "<Axis>"
            "    <AxisTag>slnt</AxisTag>"
            "    <Flags>0x123</Flags>"
            "</Axis>"
            '<NamedInstance subfamilyNameID="765"/>'
            '<NamedInstance subfamilyNameID="234"/>'
        ):
            fvar.fromXML(name, attrs, content, ttFont=None)
        self.assertEqual(["opsz", "slnt"], [a.axisTag for a in fvar.axes])
        self.assertEqual([0, 0x123], [a.flags for a in fvar.axes])
        self.assertEqual([765, 234], [i.subfamilyNameID for i in fvar.instances])


class AxisTest(unittest.TestCase):
    def test_compile(self):
        axis = Axis()
        axis.axisTag, axis.axisNameID = ("opsz", 345)
        axis.minValue, axis.defaultValue, axis.maxValue = (-0.5, 1.3, 1.5)
        self.assertEqual(FVAR_AXIS_DATA, axis.compile())

    def test_decompile(self):
        axis = Axis()
        axis.decompile(FVAR_AXIS_DATA)
        self.assertEqual("opsz", axis.axisTag)
        self.assertEqual(345, axis.axisNameID)
        self.assertEqual(-0.5, axis.minValue)
        self.assertAlmostEqual(1.3000031, axis.defaultValue)
        self.assertEqual(1.5, axis.maxValue)

    def test_toXML(self):
        font = MakeFont()
        axis = Axis()
        axis.decompile(FVAR_AXIS_DATA)
        AddName(font, "Optical Size").nameID = 256
        axis.axisNameID = 256
        axis.flags = 0xABC
        writer = XMLWriter(BytesIO())
        axis.toXML(writer, font)
        self.assertEqual(
            [
                "",
                "<!-- Optical Size -->",
                "<Axis>",
                "<AxisTag>opsz</AxisTag>",
                "<Flags>0xABC</Flags>",
                "<MinValue>-0.5</MinValue>",
                "<DefaultValue>1.3</DefaultValue>",
                "<MaxValue>1.5</MaxValue>",
                "<AxisNameID>256</AxisNameID>",
                "</Axis>",
            ],
            xml_lines(writer),
        )

    def test_fromXML(self):
        axis = Axis()
        for name, attrs, content in parseXML(
            "<Axis>"
            "    <AxisTag>wght</AxisTag>"
            "    <Flags>0x123ABC</Flags>"
            "    <MinValue>100</MinValue>"
            "    <DefaultValue>400</DefaultValue>"
            "    <MaxValue>900</MaxValue>"
            "    <AxisNameID>256</AxisNameID>"
            "</Axis>"
        ):
            axis.fromXML(name, attrs, content, ttFont=None)
        self.assertEqual("wght", axis.axisTag)
        self.assertEqual(0x123ABC, axis.flags)
        self.assertEqual(100, axis.minValue)
        self.assertEqual(400, axis.defaultValue)
        self.assertEqual(900, axis.maxValue)
        self.assertEqual(256, axis.axisNameID)


class NamedInstanceTest(unittest.TestCase):
    def assertDictAlmostEqual(self, dict1, dict2):
        self.assertEqual(set(dict1.keys()), set(dict2.keys()))
        for key in dict1:
            self.assertAlmostEqual(dict1[key], dict2[key])

    def test_compile_withPostScriptName(self):
        inst = NamedInstance()
        inst.subfamilyNameID = 345
        inst.postscriptNameID = 564
        inst.coordinates = {"wght": 0.7, "wdth": 0.5}
        self.assertEqual(
            FVAR_INSTANCE_DATA_WITH_PSNAME, inst.compile(["wght", "wdth"], True)
        )

    def test_compile_withoutPostScriptName(self):
        inst = NamedInstance()
        inst.subfamilyNameID = 345
        inst.postscriptNameID = 564
        inst.coordinates = {"wght": 0.7, "wdth": 0.5}
        self.assertEqual(
            FVAR_INSTANCE_DATA_WITHOUT_PSNAME, inst.compile(["wght", "wdth"], False)
        )

    def test_decompile_withPostScriptName(self):
        inst = NamedInstance()
        inst.decompile(FVAR_INSTANCE_DATA_WITH_PSNAME, ["wght", "wdth"])
        self.assertEqual(564, inst.postscriptNameID)
        self.assertEqual(345, inst.subfamilyNameID)
        self.assertDictAlmostEqual({"wght": 0.6999969, "wdth": 0.5}, inst.coordinates)

    def test_decompile_withoutPostScriptName(self):
        inst = NamedInstance()
        inst.decompile(FVAR_INSTANCE_DATA_WITHOUT_PSNAME, ["wght", "wdth"])
        self.assertEqual(0xFFFF, inst.postscriptNameID)
        self.assertEqual(345, inst.subfamilyNameID)
        self.assertDictAlmostEqual({"wght": 0.6999969, "wdth": 0.5}, inst.coordinates)

    def test_toXML_withPostScriptName(self):
        font = MakeFont()
        inst = NamedInstance()
        inst.flags = 0xE9
        inst.subfamilyNameID = AddName(font, "Light Condensed").nameID
        inst.postscriptNameID = AddName(font, "Test-LightCondensed").nameID
        inst.coordinates = {"wght": 0.7, "wdth": 0.5}
        writer = XMLWriter(BytesIO())
        inst.toXML(writer, font)
        self.assertEqual(
            [
                "",
                "<!-- Light Condensed -->",
                "<!-- PostScript: Test-LightCondensed -->",
                '<NamedInstance flags="0xE9" postscriptNameID="%s" subfamilyNameID="%s">'
                % (inst.postscriptNameID, inst.subfamilyNameID),
                '<coord axis="wght" value="0.7"/>',
                '<coord axis="wdth" value="0.5"/>',
                "</NamedInstance>",
            ],
            xml_lines(writer),
        )

    def test_toXML_withoutPostScriptName(self):
        font = MakeFont()
        inst = NamedInstance()
        inst.flags = 0xABC
        inst.subfamilyNameID = AddName(font, "Light Condensed").nameID
        inst.coordinates = {"wght": 0.7, "wdth": 0.5}
        writer = XMLWriter(BytesIO())
        inst.toXML(writer, font)
        self.assertEqual(
            [
                "",
                "<!-- Light Condensed -->",
                '<NamedInstance flags="0xABC" subfamilyNameID="%s">'
                % inst.subfamilyNameID,
                '<coord axis="wght" value="0.7"/>',
                '<coord axis="wdth" value="0.5"/>',
                "</NamedInstance>",
            ],
            xml_lines(writer),
        )

    def test_fromXML_withPostScriptName(self):
        inst = NamedInstance()
        for name, attrs, content in parseXML(
            '<NamedInstance flags="0x0" postscriptNameID="257" subfamilyNameID="345">'
            '    <coord axis="wght" value="0.7"/>'
            '    <coord axis="wdth" value="0.5"/>'
            "</NamedInstance>"
        ):
            inst.fromXML(name, attrs, content, ttFont=MakeFont())
        self.assertEqual(257, inst.postscriptNameID)
        self.assertEqual(345, inst.subfamilyNameID)
        self.assertDictAlmostEqual({"wght": 0.6999969, "wdth": 0.5}, inst.coordinates)

    def test_fromXML_withoutPostScriptName(self):
        inst = NamedInstance()
        for name, attrs, content in parseXML(
            '<NamedInstance flags="0x123ABC" subfamilyNameID="345">'
            '    <coord axis="wght" value="0.7"/>'
            '    <coord axis="wdth" value="0.5"/>'
            "</NamedInstance>"
        ):
            inst.fromXML(name, attrs, content, ttFont=MakeFont())
        self.assertEqual(0x123ABC, inst.flags)
        self.assertEqual(345, inst.subfamilyNameID)
        self.assertDictAlmostEqual({"wght": 0.6999969, "wdth": 0.5}, inst.coordinates)


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
