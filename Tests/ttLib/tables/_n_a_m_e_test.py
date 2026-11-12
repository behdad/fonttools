from fontTools.misc import sstruct
from fontTools.misc.loggingTools import CapturingLogHandler
from fontTools.misc.testTools import FakeFont
from fontTools.misc.textTools import bytesjoin, tostr, Tag
from fontTools.misc.xmlWriter import XMLWriter
from io import BytesIO
import struct
import unittest
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._n_a_m_e import (
    table__n_a_m_e,
    NameRecord,
    nameRecordFormat,
    nameRecordSize,
    makeName,
    log,
)


def names(nameTable):
    result = [
        (n.nameID, n.platformID, n.platEncID, n.langID, n.string)
        for n in nameTable.names
    ]
    result.sort()
    return result


class NameTableTest(unittest.TestCase):
    def test_init(self):
        table = table__n_a_m_e()
        self.assertEqual(table.names, [])
        self.assertTrue(type(table.tableTag) is Tag)

    def test_getDebugName(self):
        table = table__n_a_m_e()
        table.names = [
            makeName("Bold", 258, 1, 0, 0),  # Mac, MacRoman, English
            makeName("Gras", 258, 1, 0, 1),  # Mac, MacRoman, French
            makeName("Fett", 258, 1, 0, 2),  # Mac, MacRoman, German
            makeName("Sem Fracções", 292, 1, 0, 8),  # Mac, MacRoman, Portuguese
        ]
        self.assertEqual("Bold", table.getDebugName(258))
        self.assertEqual("Sem Fracções", table.getDebugName(292))
        self.assertEqual(None, table.getDebugName(999))

    def test_getDebugName_prefers_windows_english(self):
        table = table__n_a_m_e()
        table.names = [
            makeName("Mac Bold", 258, 1, 0, 0),  # Mac, MacRoman, English
            makeName("Mac Gras", 258, 1, 0, 1),  # Mac, MacRoman, French
            makeName("Windows Gras", 258, 3, 1, 0x40C),  # Windows, French
            makeName("Windows Bold", 258, 3, 1, 0x409),  # Windows, English
            makeName("Mac Regular", 259, 1, 0, 0),  # Mac, MacRoman, English
            makeName("Windows Normal", 259, 3, 1, 0x40C),  # Windows, French
        ]
        self.assertEqual("Windows Bold", table.getDebugName(258))
        # falls back to the Mac English name if there's no Windows English one
        self.assertEqual("Mac Regular", table.getDebugName(259))

    def test_setName(self):
        table = table__n_a_m_e()
        table.setName("Regular", 2, 1, 0, 0)
        table.setName("Version 1.000", 5, 3, 1, 0x409)
        table.setName("寬鬆", 276, 1, 2, 0x13)
        self.assertEqual("Regular", table.getName(2, 1, 0, 0).toUnicode())
        self.assertEqual("Version 1.000", table.getName(5, 3, 1, 0x409).toUnicode())
        self.assertEqual("寬鬆", table.getName(276, 1, 2, 0x13).toUnicode())
        self.assertTrue(len(table.names) == 3)
        table.setName("緊縮", 276, 1, 2, 0x13)
        self.assertEqual("緊縮", table.getName(276, 1, 2, 0x13).toUnicode())
        self.assertTrue(len(table.names) == 3)
        # passing bytes issues a warning
        with CapturingLogHandler(log, "WARNING") as captor:
            table.setName(b"abc", 0, 1, 0, 0)
        self.assertTrue(
            len([r for r in captor.records if "string is bytes" in r.msg]) == 1
        )
        # anything other than unicode or bytes raises an error
        with self.assertRaises(TypeError):
            table.setName(1.000, 5, 1, 0, 0)

    def test_names_sort_bytes_str(self):
        # Corner case: If a user appends a name record directly to `names`, the
        # `__lt__` method on NameRecord may run into duplicate name records where
        # one `string` is a str and the other one bytes, leading to an exception.
        table = table__n_a_m_e()
        table.names = [
            makeName("Test", 25, 3, 1, 0x409),
            makeName("Test".encode("utf-16be"), 25, 3, 1, 0x409),
        ]
        table.compile(None)

    def test_names_sort_attributes(self):
        table = table__n_a_m_e()
        # Create an actual invalid NameRecord object
        broken = makeName("Test", 25, 3, 1, 0x409)
        delattr(broken, "platformID")
        table.names = [
            makeName("Test", 25, 3, 1, 0x409),
            broken,
        ]
        # Sorting these two is impossible, expect an error to be raised
        with self.assertRaises(TypeError):
            table.names.sort()

    def test_names_sort_encoding(self):
        """
        Confirm that encoding errors in name table strings do not prevent at
        least sorting by other IDs
        """
        table = table__n_a_m_e()
        table.names = [
            makeName("Mac Unicode 寬 encodes ok", 25, 3, 0, 0x409),
            makeName("Win Latin 寬 fails to encode", 25, 1, 0, 0),
        ]
        table.names.sort()
        # Encoding errors or not, sort based on other IDs nonetheless
        self.assertEqual(table.names[0].platformID, 1)
        self.assertEqual(table.names[1].platformID, 3)

    def test_addName(self):
        table = table__n_a_m_e()
        nameIDs = []
        for string in ("Width", "Weight", "Custom"):
            nameIDs.append(table.addName(string))

        self.assertEqual(nameIDs[0], 256)
        self.assertEqual(nameIDs[1], 257)
        self.assertEqual(nameIDs[2], 258)
        self.assertEqual(len(table.names), 6)
        self.assertEqual(table.names[0].string, "Width")
        self.assertEqual(table.names[1].string, "Width")
        self.assertEqual(table.names[2].string, "Weight")
        self.assertEqual(table.names[3].string, "Weight")
        self.assertEqual(table.names[4].string, "Custom")
        self.assertEqual(table.names[5].string, "Custom")

        with self.assertRaises(ValueError):
            table.addName("Invalid nameID", minNameID=32767)
        with self.assertRaises(TypeError):
            table.addName(b"abc")  # must be unicode string

    def test_removeNames(self):
        table = table__n_a_m_e()
        table.setName("Regular", 2, 1, 0, 0)
        table.setName("Regular", 2, 3, 1, 0x409)
        table.removeNames(nameID=2)
        self.assertEqual(table.names, [])

        table = table__n_a_m_e()
        table.setName("FamilyName", 1, 1, 0, 0)
        table.setName("Regular", 2, 1, 0, 0)
        table.setName("FamilyName", 1, 3, 1, 0x409)
        table.setName("Regular", 2, 3, 1, 0x409)
        table.removeNames(platformID=1)
        self.assertEqual(len(table.names), 2)
        self.assertIsNone(table.getName(1, 1, 0, 0))
        self.assertIsNone(table.getName(2, 1, 0, 0))
        rec1 = table.getName(1, 3, 1, 0x409)
        self.assertEqual(str(rec1), "FamilyName")
        rec2 = table.getName(2, 3, 1, 0x409)
        self.assertEqual(str(rec2), "Regular")

        table = table__n_a_m_e()
        table.setName("FamilyName", 1, 1, 0, 0)
        table.setName("Regular", 2, 1, 0, 0)
        table.removeNames(nameID=1)
        self.assertEqual(len(table.names), 1)
        self.assertIsNone(table.getName(1, 1, 0, 0))
        rec = table.getName(2, 1, 0, 0)
        self.assertEqual(str(rec), "Regular")

        table = table__n_a_m_e()
        table.setName("FamilyName", 1, 1, 0, 0)
        table.setName("Regular", 2, 1, 0, 0)
        table.removeNames(2, 1, 0, 0)
        self.assertEqual(len(table.names), 1)
        self.assertIsNone(table.getName(2, 1, 0, 0))
        rec = table.getName(1, 1, 0, 0)
        self.assertEqual(str(rec), "FamilyName")

        table = table__n_a_m_e()
        table.setName("FamilyName", 1, 1, 0, 0)
        table.setName("Regular", 2, 1, 0, 0)
        table.removeNames()
        self.assertEqual(len(table.names), 2)
        rec1 = table.getName(1, 1, 0, 0)
        self.assertEqual(str(rec1), "FamilyName")
        rec2 = table.getName(2, 1, 0, 0)
        self.assertEqual(str(rec2), "Regular")

    @staticmethod
    def _get_test_names():
        names = {
            "en": "Width",
            "de-CH": "Breite",
            "gsw-LI": "Bräiti",
        }
        namesSubSet = names.copy()
        del namesSubSet["gsw-LI"]
        namesSuperSet = names.copy()
        namesSuperSet["nl"] = "Breedte"
        return names, namesSubSet, namesSuperSet

    def test_findMultilingualName(self):
        table = table__n_a_m_e()
        names, namesSubSet, namesSuperSet = self._get_test_names()
        nameID = table.addMultilingualName(names)
        assert nameID is not None
        self.assertEqual(nameID, table.findMultilingualName(names))
        self.assertEqual(nameID, table.findMultilingualName(namesSubSet))
        self.assertEqual(None, table.findMultilingualName(namesSuperSet))

    def test_findMultilingualName_compiled(self):
        table = table__n_a_m_e()
        names, namesSubSet, namesSuperSet = self._get_test_names()
        nameID = table.addMultilingualName(names)
        assert nameID is not None
        # After compile/decompile, name.string is a bytes sequence, which
        # findMultilingualName() should also handle
        data = table.compile(None)
        table = table__n_a_m_e()
        table.decompile(data, None)
        self.assertEqual(nameID, table.findMultilingualName(names))
        self.assertEqual(nameID, table.findMultilingualName(namesSubSet))
        self.assertEqual(None, table.findMultilingualName(namesSuperSet))

    def test_addMultilingualNameReuse(self):
        table = table__n_a_m_e()
        names, namesSubSet, namesSuperSet = self._get_test_names()
        nameID = table.addMultilingualName(names)
        assert nameID is not None
        self.assertEqual(nameID, table.addMultilingualName(names))
        self.assertEqual(nameID, table.addMultilingualName(namesSubSet))
        self.assertNotEqual(None, table.addMultilingualName(namesSuperSet))

    def test_findMultilingualNameNoMac(self):
        table = table__n_a_m_e()
        names, namesSubSet, namesSuperSet = self._get_test_names()
        nameID = table.addMultilingualName(names, mac=False)
        assert nameID is not None
        self.assertEqual(nameID, table.findMultilingualName(names, mac=False))
        self.assertEqual(None, table.findMultilingualName(names))
        self.assertEqual(nameID, table.findMultilingualName(namesSubSet, mac=False))
        self.assertEqual(None, table.findMultilingualName(namesSubSet))
        self.assertEqual(None, table.findMultilingualName(namesSuperSet))

    def test_addMultilingualName(self):
        # Microsoft Windows has language codes for “English” (en)
        # and for “Standard German as used in Switzerland” (de-CH).
        # In this case, we expect that the implementation just
        # encodes the name for the Windows platform; Apple platforms
        # have been able to decode Windows names since the early days
        # of OSX (~2001). However, Windows has no language code for
        # “Swiss German as used in Liechtenstein” (gsw-LI), so we
        # expect that the implementation populates the 'ltag' table
        # to represent that particular, rather exotic BCP47 code.
        font = FakeFont(glyphs=[".notdef", "A"])
        nameTable = font.tables["name"] = newTable("name")
        with CapturingLogHandler(log, "WARNING") as captor:
            widthID = nameTable.addMultilingualName(
                {
                    "en": "Width",
                    "de-CH": "Breite",
                    "gsw-LI": "Bräiti",
                },
                ttFont=font,
                mac=False,
            )
            self.assertEqual(widthID, 256)
            xHeightID = nameTable.addMultilingualName(
                {"en": "X-Height", "gsw-LI": "X-Hööchi"}, ttFont=font, mac=False
            )
            self.assertEqual(xHeightID, 257)
        captor.assertRegex("cannot add Windows name in language gsw-LI")
        self.assertEqual(
            names(nameTable),
            [
                (256, 0, 4, 0, "Bräiti"),
                (256, 3, 1, 0x0409, "Width"),
                (256, 3, 1, 0x0807, "Breite"),
                (257, 0, 4, 0, "X-Hööchi"),
                (257, 3, 1, 0x0409, "X-Height"),
            ],
        )
        self.assertEqual(set(font.tables.keys()), {"ltag", "name"})
        self.assertEqual(font["ltag"].tags, ["gsw-LI"])

    def test_addMultilingualName_legacyMacEncoding(self):
        # Windows has no language code for Latin; MacOS has a code;
        # and we actually can convert the name to the legacy MacRoman
        # encoding. In this case, we expect that the name gets encoded
        # as Macintosh name (platformID 1) with the corresponding Mac
        # language code (133); the 'ltag' table should not be used.
        font = FakeFont(glyphs=[".notdef", "A"])
        nameTable = font.tables["name"] = newTable("name")
        with CapturingLogHandler(log, "WARNING") as captor:
            nameTable.addMultilingualName({"la": "SPQR"}, ttFont=font)
        captor.assertRegex("cannot add Windows name in language la")
        self.assertEqual(names(nameTable), [(256, 1, 0, 131, "SPQR")])
        self.assertNotIn("ltag", font.tables.keys())

    def test_addMultilingualName_legacyMacEncodingButUnencodableName(self):
        # Windows has no language code for Latin; MacOS has a code;
        # but we cannot encode the name into this encoding because
        # it contains characters that are not representable.
        # In this case, we expect that the name gets encoded as
        # Unicode name (platformID 0) with the language tag being
        # added to the 'ltag' table.
        font = FakeFont(glyphs=[".notdef", "A"])
        nameTable = font.tables["name"] = newTable("name")
        with CapturingLogHandler(log, "WARNING") as captor:
            nameTable.addMultilingualName({"la": "ⱾƤℚⱤ"}, ttFont=font)
        captor.assertRegex("cannot add Windows name in language la")
        self.assertEqual(names(nameTable), [(256, 0, 4, 0, "ⱾƤℚⱤ")])
        self.assertIn("ltag", font.tables)
        self.assertEqual(font["ltag"].tags, ["la"])

    def test_addMultilingualName_legacyMacEncodingButNoCodec(self):
        # Windows has no language code for “Azeri written in the
        # Arabic script” (az-Arab); MacOS would have a code (50);
        # but we cannot encode the name into the legacy encoding
        # because we have no codec for MacArabic in fonttools.
        # In this case, we expect that the name gets encoded as
        # Unicode name (platformID 0) with the language tag being
        # added to the 'ltag' table.
        font = FakeFont(glyphs=[".notdef", "A"])
        nameTable = font.tables["name"] = newTable("name")
        with CapturingLogHandler(log, "WARNING") as captor:
            nameTable.addMultilingualName({"az-Arab": "آذربايجان ديلی"}, ttFont=font)
        captor.assertRegex("cannot add Windows name in language az-Arab")
        self.assertEqual(names(nameTable), [(256, 0, 4, 0, "آذربايجان ديلی")])
        self.assertIn("ltag", font.tables)
        self.assertEqual(font["ltag"].tags, ["az-Arab"])

    def test_addMultilingualName_macLanguageCodes(self):
        # https://github.com/fonttools/fonttools/issues/3733
        # Spanish must not end up as Macintosh langEstonian (27), and
        # Irish must use langIrishGaelic (35), not langIrishGaelicScript.
        font = FakeFont(glyphs=[".notdef", "A"])
        nameTable = font.tables["name"] = newTable("name")
        nameTable.addMultilingualName(
            {"es": "Ancho", "et": "Laius", "ga": "Leithead", "ga-Latg": "Leithead"},
            ttFont=font,
            windows=False,
        )
        self.assertEqual(
            names(nameTable),
            [
                (256, 1, 0, 6, "Ancho"),
                (256, 1, 0, 35, "Leithead"),
                (256, 1, 0, 146, "Leithead"),
                (256, 1, 29, 27, "Laius"),
            ],
        )
        self.assertNotIn("ltag", font.tables)

    def test_addMultilingualName_windowsSamiLanguageCodes(self):
        # https://github.com/fonttools/fonttools/issues/3733
        # 0x1C3B is Southern Sami (Sweden), not Skolt Sami.
        nameTable = newTable("name")
        nameTable.addMultilingualName({"sms": "Skolt", "sma": "Southern"}, mac=False)
        self.assertEqual(
            names(nameTable),
            [
                (256, 3, 1, 0x1C3B, "Southern"),
                (256, 3, 1, 0x203B, "Skolt"),
            ],
        )

    def test_addMultilingualName_noTTFont(self):
        # If the ttFont argument is not passed, the implementation
        # should add whatever names it can, but it should not crash
        # just because it cannot build an ltag table.
        nameTable = newTable("name")
        with CapturingLogHandler(log, "WARNING") as captor:
            nameTable.addMultilingualName({"en": "A", "la": "ⱾƤℚⱤ"})
        captor.assertRegex("cannot store language la into 'ltag' table")

    def test_addMultilingualName_TTFont(self):
        # if ttFont argument is passed, it should not WARN about not being able
        # to create ltag table.
        font = FakeFont(glyphs=[".notdef", "A"])
        nameTable = newTable("name")
        with CapturingLogHandler(log, "WARNING") as captor:
            nameTable.addMultilingualName({"en": "A", "ar": "ع"}, ttFont=font)
        self.assertFalse(captor.records)

    def test_addMultilingualName_minNameID(self):
        table = table__n_a_m_e()
        names, namesSubSet, namesSuperSet = self._get_test_names()
        nameID = table.addMultilingualName(names, nameID=2)
        self.assertEqual(nameID, 2)
        nameID = table.addMultilingualName(names)
        self.assertEqual(nameID, 2)
        nameID = table.addMultilingualName(names, minNameID=256)
        self.assertGreaterEqual(nameID, 256)
        self.assertEqual(nameID, table.findMultilingualName(names, minNameID=256))

    def test_addMultilingualName_name_inconsistencies(self):
        # Check what happens, when there are
        # inconsistencies in the name table
        table = table__n_a_m_e()
        table.setName("Weight", 270, 3, 1, 0x409)
        names = {
            "en": "Weight",
        }
        nameID = table.addMultilingualName(names, minNameID=256)
        # Because there is an inconsistency in the names,
        # addMultilingualName adds a new name ID
        self.assertEqual(271, nameID)

    def test_decompile_badOffset(self):
        # https://github.com/fonttools/fonttools/issues/525
        table = table__n_a_m_e()
        badRecord = {
            "platformID": 1,
            "platEncID": 3,
            "langID": 7,
            "nameID": 1,
            "length": 3,
            "offset": 8765,  # out of range
        }
        data = bytesjoin(
            [
                struct.pack(tostr(">HHH"), 1, 1, 6 + nameRecordSize),
                sstruct.pack(nameRecordFormat, badRecord),
            ]
        )
        table.decompile(data, ttFont=None)
        self.assertEqual(table.names, [])


class NameRecordTest(unittest.TestCase):
    def test_toUnicode_utf16be(self):
        name = makeName("Foo Bold", 111, 0, 2, 7)
        self.assertEqual("utf_16_be", name.getEncoding())
        self.assertEqual("Foo Bold", name.toUnicode())

    def test_toUnicode_macroman(self):
        name = makeName("Foo Italic", 222, 1, 0, 7)  # MacRoman
        self.assertEqual("mac_roman", name.getEncoding())
        self.assertEqual("Foo Italic", name.toUnicode())

    def test_toUnicode_macromanian(self):
        name = makeName(b"Foo Italic\xfb", 222, 1, 0, 37)  # Mac Romanian
        self.assertEqual("mac_romanian", name.getEncoding())
        self.assertEqual("Foo Italic" + chr(0x02DA), name.toUnicode())

    def test_toUnicode_UnicodeDecodeError(self):
        name = makeName(b"\1", 111, 0, 2, 7)
        self.assertEqual("utf_16_be", name.getEncoding())
        self.assertRaises(UnicodeDecodeError, name.toUnicode)

    def test_toUnicode_singleChar(self):
        # https://github.com/fonttools/fonttools/issues/1997
        name = makeName("A", 256, 3, 1, 0x409)
        self.assertEqual(name.toUnicode(), "A")

    def toXML(self, name):
        writer = XMLWriter(BytesIO())
        name.toXML(writer, ttFont=None)
        xml = writer.file.getvalue().decode("utf_8").strip()
        return xml.split(writer.newlinestr.decode("utf_8"))[1:]

    def test_xml_roundtrip_xml_unsafe_names(self):
        for payload, platformID, platEncID, langID in (
            (b"\x00A\xff\xff\x00B", 3, 1, 0x409),
            (b"A\x01B", 1, 0, 0),
            (b"\xd8\x00", 0, 4, 0),
        ):
            with self.subTest(payload=payload, platformID=platformID):
                font = TTFont()
                font["name"] = newTable("name")
                font["name"].names = [
                    makeName(payload, 5, platformID, platEncID, langID)
                ]
                original = names(font["name"])
                xml = BytesIO()
                font.saveXML(xml, tables=["name"])

                restored = TTFont()
                restored.importXML(BytesIO(xml.getvalue()))
                self.assertEqual(names(restored["name"]), original)

    def test_toXML_utf16be(self):
        name = makeName("Foo Bold", 111, 0, 2, 7)
        self.assertEqual(
            [
                '<namerecord nameID="111" platformID="0" platEncID="2" langID="0x7">',
                "  Foo Bold",
                "</namerecord>",
            ],
            self.toXML(name),
        )

    def test_toXML_utf16be_odd_length1(self):
        name = makeName(b"\0F\0o\0o\0", 111, 0, 2, 7)
        self.assertEqual(
            [
                '<namerecord nameID="111" platformID="0" platEncID="2" langID="0x7">',
                "  Foo",
                "</namerecord>",
            ],
            self.toXML(name),
        )

    def test_toXML_utf16be_odd_length2(self):
        name = makeName(b"\0Fooz", 111, 0, 2, 7)
        self.assertEqual(
            [
                '<namerecord nameID="111" platformID="0" platEncID="2" langID="0x7">',
                "  Fooz",
                "</namerecord>",
            ],
            self.toXML(name),
        )

    def test_toXML_utf16be_double_encoded(self):
        name = makeName(b"\0\0\0F\0\0\0o", 111, 0, 2, 7)
        self.assertEqual(
            [
                '<namerecord nameID="111" platformID="0" platEncID="2" langID="0x7">',
                "  Fo",
                "</namerecord>",
            ],
            self.toXML(name),
        )

    def test_toXML_macroman(self):
        name = makeName("Foo Italic", 222, 1, 0, 7)  # MacRoman
        self.assertEqual(
            [
                '<namerecord nameID="222" platformID="1" platEncID="0" langID="0x7" unicode="True">',
                "  Foo Italic",
                "</namerecord>",
            ],
            self.toXML(name),
        )

    def test_toXML_macroman_actual_utf16be(self):
        name = makeName("\0F\0o\0o", 222, 1, 0, 7)
        self.assertEqual(
            [
                '<namerecord nameID="222" platformID="1" platEncID="0" langID="0x7" unicode="True">',
                "  Foo",
                "</namerecord>",
            ],
            self.toXML(name),
        )

    def test_toXML_unknownPlatEncID_nonASCII(self):
        name = makeName(b"B\x8arli", 333, 1, 9876, 7)  # Unknown Mac encodingID
        self.assertEqual(
            [
                '<namerecord nameID="333" platformID="1" platEncID="9876" langID="0x7" unicode="False">',
                "  B&#138;rli",
                "</namerecord>",
            ],
            self.toXML(name),
        )

    def test_toXML_unknownPlatEncID_ASCII(self):
        name = makeName(b"Barli", 333, 1, 9876, 7)  # Unknown Mac encodingID
        self.assertEqual(
            [
                '<namerecord nameID="333" platformID="1" platEncID="9876" langID="0x7" unicode="True">',
                "  Barli",
                "</namerecord>",
            ],
            self.toXML(name),
        )

    def test_encoding_macroman_misc(self):
        name = makeName("", 123, 1, 0, 17)  # Mac Turkish
        self.assertEqual(name.getEncoding(), "mac_turkish")
        name.langID = 37
        self.assertEqual(name.getEncoding(), "mac_romanian")
        name.langID = 45  # Other
        self.assertEqual(name.getEncoding(), "mac_roman")

    def test_extended_mac_encodings(self):
        name = makeName(b"\xfe", 123, 1, 1, 0)  # Mac Japanese
        self.assertEqual(name.toUnicode(), chr(0x2122))

    def test_extended_mac_encodings_errors(self):
        s = "汉仪彩云体简"
        name = makeName(s.encode("x_mac_simp_chinese_ttx"), 123, 1, 25, 0)
        # first check we round-trip with 'strict'
        self.assertEqual(name.toUnicode(errors="strict"), s)

        # append an incomplete invalid sequence and check that we handle
        # errors with the requested error handler
        name.string += b"\xba"
        self.assertEqual(name.toUnicode(errors="backslashreplace"), s + "\\xba")
        self.assertEqual(name.toUnicode(errors="replace"), s + "�")

    def test_extended_unknown(self):
        name = makeName(b"\xfe", 123, 10, 11, 12)
        self.assertEqual(name.getEncoding(), "ascii")
        self.assertEqual(name.getEncoding(None), None)
        self.assertEqual(name.getEncoding(default=None), None)

    def test_get_family_name(self):
        name = table__n_a_m_e()
        name.names = [
            makeName("Copyright", 0, 1, 0, 0),
            makeName("Family Name ID 1", 1, 1, 0, 0),
            makeName("SubFamily Name ID 2", 2, 1, 0, 0),
            makeName("Unique Name ID 3", 3, 1, 0, 0),
            makeName("Full Name ID 4", 4, 1, 0, 0),
            makeName("PS Name ID 6", 6, 1, 0, 0),
            makeName("Version Name ID 5", 5, 1, 0, 0),
            makeName("Trademark Name ID 7", 7, 1, 0, 0),
        ]

        result_value = name.getBestFamilyName()
        self.assertEqual("Family Name ID 1", result_value)

        expected_value = "Family Name ID 16"
        name.setName(expected_value, 16, 1, 0, 0)
        result_value = name.getBestFamilyName()
        self.assertEqual(expected_value, result_value)

        expected_value = "Family Name ID 21"
        name.setName(expected_value, 21, 1, 0, 0)
        result_value = name.getBestFamilyName()
        self.assertEqual(expected_value, result_value)

    def test_get_subfamily_name(self):
        name = table__n_a_m_e()
        name.names = [
            makeName("Copyright", 0, 1, 0, 0),
            makeName("Family Name ID 1", 1, 1, 0, 0),
            makeName("SubFamily Name ID 2", 2, 1, 0, 0),
            makeName("Unique Name ID 3", 3, 1, 0, 0),
            makeName("Full Name ID 4", 4, 1, 0, 0),
            makeName("PS Name ID 6", 6, 1, 0, 0),
            makeName("Version Name ID 5", 5, 1, 0, 0),
            makeName("Trademark Name ID 7", 7, 1, 0, 0),
        ]

        result_value = name.getBestSubFamilyName()
        self.assertEqual("SubFamily Name ID 2", result_value)

        expected_value = "Family Name ID 17"
        name.setName(expected_value, 17, 1, 0, 0)
        result_value = name.getBestSubFamilyName()
        self.assertEqual(expected_value, result_value)

        expected_value = "Family Name ID 22"
        name.setName(expected_value, 22, 1, 0, 0)
        result_value = name.getBestSubFamilyName()
        self.assertEqual(expected_value, result_value)

    def test_get_nice_full_name(self):
        name = table__n_a_m_e()
        name.names = [
            makeName("NID 1", 1, 1, 0, 0),
            makeName("NID 2", 2, 1, 0, 0),
            makeName("NID 4", 4, 1, 0, 0),
            makeName("NID 6", 6, 1, 0, 0),
        ]

        result_value = name.getBestFullName()
        self.assertEqual("NID 1 NID 2", result_value)

        expected_value = "NID 1 NID 2"
        # expection is still NID 1 NID 2,
        # because name ID 17 is missing
        name.setName("NID 16", 16, 1, 0, 0)
        result_value = name.getBestFullName()
        self.assertEqual(expected_value, result_value)

        name.setName("NID 17", 17, 1, 0, 0)
        result_value = name.getBestFullName()
        self.assertEqual("NID 16 NID 17", result_value)

        expected_value = "NID 16 NID 17"
        # expection is still NID 16 NID 17,
        # because name ID 21 is missing
        name.setName("NID 21", 21, 1, 0, 0)
        result_value = name.getBestFullName()
        self.assertEqual(expected_value, result_value)

        name.setName("NID 22", 22, 1, 0, 0)
        result_value = name.getBestFullName()
        self.assertEqual("NID 21 NID 22", result_value)

        for NID in [2, 16, 17, 21, 22]:
            name.removeNames(NID)

        result_value = name.getBestFullName()
        self.assertEqual("NID 4", result_value)

        name.setName("Regular", 2, 1, 0, 0)
        result_value = name.getBestFullName()
        self.assertEqual("NID 1", result_value)


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
