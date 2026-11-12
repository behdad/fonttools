from fontTools.misc.xmlWriter import XMLWriter
from fontTools.ttLib import TTFont
from fontTools.feaLib.lookupDebugInfo import LOOKUP_DEBUG_ENV_VAR
from fontTools import mtiLib
import difflib
from io import StringIO
import os
import sys
import threading
import pytest


@pytest.fixture(autouse=True)
def set_lookup_debug_env_var(monkeypatch):
    monkeypatch.setenv(LOOKUP_DEBUG_ENV_VAR, "1")


class MtiTest:
    GLYPH_ORDER = [
        ".notdef",
        "a",
        "b",
        "pakannada",
        "phakannada",
        "vakannada",
        "pevowelkannada",
        "phevowelkannada",
        "vevowelkannada",
        "uvowelsignkannada",
        "uuvowelsignkannada",
        "uvowelsignaltkannada",
        "uuvowelsignaltkannada",
        "uuvowelsignsinh",
        "uvowelsignsinh",
        "rakarsinh",
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "slash",
        "fraction",
        "A",
        "B",
        "C",
        "fi",
        "fl",
        "breve",
        "acute",
        "uniFB01",
        "ffi",
        "grave",
        "commaacent",
        "dotbelow",
        "dotabove",
        "cedilla",
        "commaaccent",
        "Acircumflex",
        "V",
        "T",
        "acircumflex",
        "Aacute",
        "Agrave",
        "O",
        "Oacute",
        "Ograve",
        "Ocircumflex",
        "aacute",
        "agrave",
        "aimatrabindigurmukhi",
        "aimatragurmukhi",
        "aimatratippigurmukhi",
        "aumatrabindigurmukhi",
        "aumatragurmukhi",
        "bindigurmukhi",
        "eematrabindigurmukhi",
        "eematragurmukhi",
        "eematratippigurmukhi",
        "oomatrabindigurmukhi",
        "oomatragurmukhi",
        "oomatratippigurmukhi",
        "lagurmukhi",
        "lanuktagurmukhi",
        "nagurmukhi",
        "nanuktagurmukhi",
        "ngagurmukhi",
        "nganuktagurmukhi",
        "nnagurmukhi",
        "nnanuktagurmukhi",
        "tthagurmukhi",
        "tthanuktagurmukhi",
        "bsuperior",
        "isuperior",
        "vsuperior",
        "wsuperior",
        "periodsuperior",
        "osuperior",
        "tsuperior",
        "dollarsuperior",
        "fsuperior",
        "gsuperior",
        "zsuperior",
        "dsuperior",
        "psuperior",
        "hsuperior",
        "oesuperior",
        "aesuperior",
        "centsuperior",
        "esuperior",
        "lsuperior",
        "qsuperior",
        "csuperior",
        "asuperior",
        "commasuperior",
        "xsuperior",
        "egravesuperior",
        "usuperior",
        "rsuperior",
        "nsuperior",
        "ssuperior",
        "msuperior",
        "jsuperior",
        "ysuperior",
        "ksuperior",
        "guilsinglright",
        "guilsinglleft",
        "uniF737",
        "uniE11C",
        "uniE11D",
        "uniE11A",
        "uni2077",
        "uni2087",
        "uniE11B",
        "uniE119",
        "uniE0DD",
        "uniE0DE",
        "uniF736",
        "uniE121",
        "uniE122",
        "uniE11F",
        "uni2076",
        "uni2086",
        "uniE120",
        "uniE11E",
        "uniE0DB",
        "uniE0DC",
        "uniF733",
        "uniE12B",
        "uniE12C",
        "uniE129",
        "uni00B3",
        "uni2083",
        "uniE12A",
        "uniE128",
        "uniF732",
        "uniE133",
        "uniE134",
        "uniE131",
        "uni00B2",
        "uni2082",
        "uniE132",
        "uniE130",
        "uniE0F9",
        "uniF734",
        "uniE0D4",
        "uniE0D5",
        "uniE0D2",
        "uni2074",
        "uni2084",
        "uniE0D3",
        "uniE0D1",
        "uniF730",
        "uniE13D",
        "uniE13E",
        "uniE13A",
        "uni2070",
        "uni2080",
        "uniE13B",
        "uniE139",
        "uniE13C",
        "uniF739",
        "uniE0EC",
        "uniE0ED",
        "uniE0EA",
        "uni2079",
        "uni2089",
        "uniE0EB",
        "uniE0E9",
        "uniF735",
        "uniE0CD",
        "uniE0CE",
        "uniE0CB",
        "uni2075",
        "uni2085",
        "uniE0CC",
        "uniE0CA",
        "uniF731",
        "uniE0F3",
        "uniE0F4",
        "uniE0F1",
        "uni00B9",
        "uni2081",
        "uniE0F2",
        "uniE0F0",
        "uniE0F8",
        "uniF738",
        "uniE0C0",
        "uniE0C1",
        "uniE0BE",
        "uni2078",
        "uni2088",
        "uniE0BF",
        "uniE0BD",
        "I",
        "Ismall",
        "t",
        "i",
        "f",
        "IJ",
        "J",
        "IJsmall",
        "Jsmall",
        "tt",
        "ij",
        "j",
        "ffb",
        "ffh",
        "h",
        "ffk",
        "k",
        "ffl",
        "l",
        "fft",
        "fb",
        "ff",
        "fh",
        "fj",
        "fk",
        "ft",
        "janyevoweltelugu",
        "kassevoweltelugu",
        "jaivoweltelugu",
        "nyasubscripttelugu",
        "kaivoweltelugu",
        "ssasubscripttelugu",
        "bayi1",
        "jeemi1",
        "kafi1",
        "ghafi1",
        "laami1",
        "kafm1",
        "ghafm1",
        "laamm1",
        "rayf2",
        "reyf2",
        "yayf2",
        "zayf2",
        "fayi1",
        "ayehf2",
        "hamzayeharabf2",
        "hamzayehf2",
        "yehf2",
        "ray",
        "rey",
        "zay",
        "yay",
        "dal",
        "del",
        "zal",
        "rayf1",
        "reyf1",
        "yayf1",
        "zayf1",
        "ayehf1",
        "hamzayeharabf1",
        "hamzayehf1",
        "yehf1",
        "dal1",
        "del1",
        "zal1",
        "onehalf",
        "onehalf.alt",
        "onequarter",
        "onequarter.alt",
        "threequarters",
        "threequarters.alt",
        "AlefSuperiorNS",
        "DammaNS",
        "DammaRflxNS",
        "DammatanNS",
        "Fatha2dotsNS",
        "FathaNS",
        "FathatanNS",
        "FourDotsAboveNS",
        "HamzaAboveNS",
        "MaddaNS",
        "OneDotAbove2NS",
        "OneDotAboveNS",
        "ShaddaAlefNS",
        "ShaddaDammaNS",
        "ShaddaDammatanNS",
        "ShaddaFathatanNS",
        "ShaddaKasraNS",
        "ShaddaKasratanNS",
        "ShaddaNS",
        "SharetKafNS",
        "SukunNS",
        "ThreeDotsDownAboveNS",
        "ThreeDotsUpAboveNS",
        "TwoDotsAboveNS",
        "TwoDotsVerticalAboveNS",
        "UltapeshNS",
        "WaslaNS",
        "AinIni.12m_MeemFin.02",
        "AinIni_YehBarreeFin",
        "AinMed_YehBarreeFin",
        "BehxIni_MeemFin",
        "BehxIni_NoonGhunnaFin",
        "BehxIni_RehFin",
        "BehxIni_RehFin.b",
        "BehxMed_MeemFin.py",
        "BehxMed_NoonGhunnaFin",
        "BehxMed_NoonGhunnaFin.cup",
        "BehxMed_RehFin",
        "BehxMed_RehFin.cup",
        "BehxMed_YehxFin",
        "FehxMed_YehBarreeFin",
        "HahIni_YehBarreeFin",
        "KafIni_YehBarreeFin",
        "KafMed.12_YehxFin.01",
        "KafMed_MeemFin",
        "KafMed_YehBarreeFin",
        "LamAlefFin",
        "LamAlefFin.cup",
        "LamAlefFin.cut",
        "LamAlefFin.short",
        "LamAlefSep",
        "LamIni_MeemFin",
        "LamIni_YehBarreeFin",
        "LamMed_MeemFin",
        "LamMed_MeemFin.b",
        "LamMed_YehxFin",
        "LamMed_YehxFin.cup",
        "TahIni_YehBarreeFin",
        "null",
        "CR",
        "space",
        "exclam",
        "quotedbl",
        "numbersign",
    ]

    # Feature files in data/*.txt; output gets compared to data/*.ttx.
    TESTS = {
        None: ("mti/cmap",),
        "cmap": ("mti/cmap",),
        "GSUB": (
            "featurename-backward",
            "featurename-forward",
            "lookupnames-backward",
            "lookupnames-forward",
            "mixed-toplevels",
            "mti/scripttable",
            "mti/chainedclass",
            "mti/chainedcoverage",
            "mti/chained-glyph",
            "mti/gsubalternate",
            "mti/gsubligature",
            "mti/gsubmultiple",
            "mti/gsubreversechanined",
            "mti/gsubsingle",
        ),
        "GPOS": (
            "mti/scripttable",
            "mti/chained-glyph",
            "mti/gposcursive",
            "mti/gposkernset",
            "mti/gposmarktobase",
            "mti/gpospairclass",
            "mti/gpospairglyph",
            "mti/gpossingle",
            "mti/mark-to-ligature",
        ),
        "GDEF": (
            "mti/gdefattach",
            "mti/gdefclasses",
            "mti/gdefligcaret",
            "mti/gdefmarkattach",
            "mti/gdefmarkfilter",
        ),
    }
    # TODO:
    # https://github.com/Monotype/OpenType_Table_Source/issues/12
    #
    #        'mti/featuretable'
    #        'mti/contextclass'
    #        'mti/contextcoverage'
    #        'mti/context-glyph'

    @staticmethod
    def getpath(testfile):
        path, _ = os.path.split(__file__)
        return os.path.join(path, "data", testfile)

    def expect_ttx(self, expected_ttx, actual_ttx, fromfile=None, tofile=None):
        expected = [l + "\n" for l in expected_ttx.split("\n")]
        actual = [l + "\n" for l in actual_ttx.split("\n")]
        if actual != expected:
            sys.stderr.write("\n")
            for line in difflib.unified_diff(
                expected, actual, fromfile=fromfile, tofile=tofile
            ):
                sys.stderr.write(line)
            pytest.fail("TTX output is different from expected")

    @classmethod
    def create_font(celf):
        font = TTFont()
        font.setGlyphOrder(celf.GLYPH_ORDER)
        return font

    def test_subtable_end_case_insensitive(self):
        with open(self.getpath("mti/gposkernset.txt"), "rt", encoding="utf-8") as f:
            text = f.read().replace("subtable end", "Subtable End")
        font = self.create_font()
        result = []

        # Parse in a daemon thread, so that the test fails instead of hanging
        # if parsing never terminates.
        thread = threading.Thread(
            target=lambda: result.append(
                mtiLib.build(StringIO(text), font, tableTag="GPOS")
            ),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=10)
        assert not thread.is_alive(), "parsing did not terminate"

        (table,) = result
        assert [l.SubTableCount for l in table.table.LookupList.Lookup] == [2]

    def check_mti_file(self, name, tableTag=None):
        xml_expected_path = self.getpath(
            "%s.ttx" % name + ("." + tableTag if tableTag is not None else "")
        )
        with open(xml_expected_path, "rt", encoding="utf-8") as xml_expected_file:
            xml_expected = xml_expected_file.read()

        font = self.create_font()

        with open(self.getpath("%s.txt" % name), "rt", encoding="utf-8") as f:
            table = mtiLib.build(f, font, tableTag=tableTag)

        if tableTag is not None:
            assert tableTag == table.tableTag
        tableTag = table.tableTag

        # Make sure it compiles.
        blob = table.compile(font)

        # Make sure it decompiles.
        decompiled = table.__class__()
        decompiled.decompile(blob, font)

        # XML from built object.
        writer = XMLWriter(StringIO())
        writer.begintag(tableTag)
        writer.newline()
        table.toXML(writer, font)
        writer.endtag(tableTag)
        writer.newline()
        xml_built = writer.file.getvalue()

        # XML from decompiled object.
        writer = XMLWriter(StringIO())
        writer.begintag(tableTag)
        writer.newline()
        decompiled.toXML(writer, font)
        writer.endtag(tableTag)
        writer.newline()
        xml_binary = writer.file.getvalue()

        self.expect_ttx(xml_binary, xml_built, fromfile="decompiled", tofile="built")
        self.expect_ttx(
            xml_expected, xml_built, fromfile=xml_expected_path, tofile="built"
        )

        from fontTools.misc import xmlReader

        f = StringIO()
        f.write(xml_expected)
        f.seek(0)
        font2 = TTFont()
        font2.setGlyphOrder(font.getGlyphOrder())
        reader = xmlReader.XMLReader(f, font2)
        reader.read(rootless=True)

        # XML from object read from XML.
        writer = XMLWriter(StringIO())
        writer.begintag(tableTag)
        writer.newline()
        font2[tableTag].toXML(writer, font)
        writer.endtag(tableTag)
        writer.newline()
        xml_fromxml = writer.file.getvalue()

        self.expect_ttx(
            xml_expected, xml_fromxml, fromfile=xml_expected_path, tofile="fromxml"
        )


def generate_mti_file_test(name, tableTag=None):
    return lambda self: self.check_mti_file(
        os.path.join(*name.split("/")), tableTag=tableTag
    )


for tableTag, tests in MtiTest.TESTS.items():
    for name in tests:
        setattr(
            MtiTest,
            "test_MtiFile_%s%s" % (name, "_" + tableTag if tableTag else ""),
            generate_mti_file_test(name, tableTag=tableTag),
        )


if __name__ == "__main__":
    if len(sys.argv) > 1:
        from fontTools.mtiLib import main

        font = MtiTest.create_font()
        sys.exit(main(sys.argv[1:], font))
    sys.exit(pytest.main(sys.argv))
