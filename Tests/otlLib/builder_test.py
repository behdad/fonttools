import io
import struct
from fontTools.misc.fixedTools import floatToFixed, fixedToFloat
from fontTools.misc.testTools import getXML
from fontTools.otlLib import builder, error
from fontTools import ttLib
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.otBase import OTTableReader, OTTableWriter
import pytest


class ExtendedGlyphMap(dict):
    def __len__(self):
        return 0x10001


class BuilderTest(object):
    GLYPHS = (
        ".notdef space zero one two three four five six "
        "A B C a b c grave acute cedilla f_f_i f_i c_t"
    ).split()
    GLYPHMAP = {name: num for num, name in enumerate(GLYPHS)}

    ANCHOR1 = builder.buildAnchor(11, -11)
    ANCHOR2 = builder.buildAnchor(22, -22)
    ANCHOR3 = builder.buildAnchor(33, -33)

    def test_buildAnchor_format1(self):
        anchor = builder.buildAnchor(23, 42)
        assert getXML(anchor.toXML) == [
            '<Anchor Format="1">',
            '  <XCoordinate value="23"/>',
            '  <YCoordinate value="42"/>',
            "</Anchor>",
        ]

    def test_buildAnchor_format2(self):
        anchor = builder.buildAnchor(23, 42, point=17)
        assert getXML(anchor.toXML) == [
            '<Anchor Format="2">',
            '  <XCoordinate value="23"/>',
            '  <YCoordinate value="42"/>',
            '  <AnchorPoint value="17"/>',
            "</Anchor>",
        ]

    def test_buildAnchor_format3(self):
        anchor = builder.buildAnchor(
            23,
            42,
            deviceX=builder.buildDevice({1: 1, 0: 0}),
            deviceY=builder.buildDevice({7: 7}),
        )
        assert getXML(anchor.toXML) == [
            '<Anchor Format="3">',
            '  <XCoordinate value="23"/>',
            '  <YCoordinate value="42"/>',
            "  <XDeviceTable>",
            '    <StartSize value="0"/>',
            '    <EndSize value="1"/>',
            '    <DeltaFormat value="1"/>',
            '    <DeltaValue value="[0, 1]"/>',
            "  </XDeviceTable>",
            "  <YDeviceTable>",
            '    <StartSize value="7"/>',
            '    <EndSize value="7"/>',
            '    <DeltaFormat value="2"/>',
            '    <DeltaValue value="[7]"/>',
            "  </YDeviceTable>",
            "</Anchor>",
        ]

    def test_buildAttachList(self):
        attachList = builder.buildAttachList(
            {"zero": [23, 7], "one": [1]}, self.GLYPHMAP
        )
        assert getXML(attachList.toXML) == [
            "<AttachList>",
            "  <Coverage>",
            '    <Glyph value="zero"/>',
            '    <Glyph value="one"/>',
            "  </Coverage>",
            "  <!-- GlyphCount=2 -->",
            '  <AttachPoint index="0">',
            "    <!-- PointCount=2 -->",
            '    <PointIndex index="0" value="7"/>',
            '    <PointIndex index="1" value="23"/>',
            "  </AttachPoint>",
            '  <AttachPoint index="1">',
            "    <!-- PointCount=1 -->",
            '    <PointIndex index="0" value="1"/>',
            "  </AttachPoint>",
            "</AttachList>",
        ]

    def test_buildAttachList_empty(self):
        assert builder.buildAttachList({}, self.GLYPHMAP) is None

    def test_buildAttachPoint(self):
        attachPoint = builder.buildAttachPoint([7, 3])
        assert getXML(attachPoint.toXML) == [
            "<AttachPoint>",
            "  <!-- PointCount=2 -->",
            '  <PointIndex index="0" value="3"/>',
            '  <PointIndex index="1" value="7"/>',
            "</AttachPoint>",
        ]

    def test_buildAttachPoint_empty(self):
        assert builder.buildAttachPoint([]) is None

    def test_buildAttachPoint_duplicate(self):
        attachPoint = builder.buildAttachPoint([7, 3, 7])
        assert getXML(attachPoint.toXML) == [
            "<AttachPoint>",
            "  <!-- PointCount=2 -->",
            '  <PointIndex index="0" value="3"/>',
            '  <PointIndex index="1" value="7"/>',
            "</AttachPoint>",
        ]

    def test_buildBaseArray(self):
        anchor = builder.buildAnchor
        baseArray = builder.buildBaseArray(
            {"a": {2: anchor(300, 80)}, "c": {1: anchor(300, 80), 2: anchor(300, -20)}},
            numMarkClasses=4,
            glyphMap=self.GLYPHMAP,
        )
        assert getXML(baseArray.toXML) == [
            "<BaseArray>",
            "  <!-- BaseCount=2 -->",
            '  <BaseRecord index="0">',
            '    <BaseAnchor index="0" empty="1"/>',
            '    <BaseAnchor index="1" empty="1"/>',
            '    <BaseAnchor index="2" Format="1">',
            '      <XCoordinate value="300"/>',
            '      <YCoordinate value="80"/>',
            "    </BaseAnchor>",
            '    <BaseAnchor index="3" empty="1"/>',
            "  </BaseRecord>",
            '  <BaseRecord index="1">',
            '    <BaseAnchor index="0" empty="1"/>',
            '    <BaseAnchor index="1" Format="1">',
            '      <XCoordinate value="300"/>',
            '      <YCoordinate value="80"/>',
            "    </BaseAnchor>",
            '    <BaseAnchor index="2" Format="1">',
            '      <XCoordinate value="300"/>',
            '      <YCoordinate value="-20"/>',
            "    </BaseAnchor>",
            '    <BaseAnchor index="3" empty="1"/>',
            "  </BaseRecord>",
            "</BaseArray>",
        ]

    def test_buildBaseRecord(self):
        a = builder.buildAnchor
        rec = builder.buildBaseRecord([a(500, -20), None, a(300, -15)])
        assert getXML(rec.toXML) == [
            "<BaseRecord>",
            '  <BaseAnchor index="0" Format="1">',
            '    <XCoordinate value="500"/>',
            '    <YCoordinate value="-20"/>',
            "  </BaseAnchor>",
            '  <BaseAnchor index="1" empty="1"/>',
            '  <BaseAnchor index="2" Format="1">',
            '    <XCoordinate value="300"/>',
            '    <YCoordinate value="-15"/>',
            "  </BaseAnchor>",
            "</BaseRecord>",
        ]

    def test_buildCaretValueForCoord(self):
        caret = builder.buildCaretValueForCoord(500)
        assert getXML(caret.toXML) == [
            '<CaretValue Format="1">',
            '  <Coordinate value="500"/>',
            "</CaretValue>",
        ]

    def test_buildCaretValueForPoint(self):
        caret = builder.buildCaretValueForPoint(23)
        assert getXML(caret.toXML) == [
            '<CaretValue Format="2">',
            '  <CaretValuePoint value="23"/>',
            "</CaretValue>",
        ]

    def test_buildComponentRecord(self):
        a = builder.buildAnchor
        rec = builder.buildComponentRecord([a(500, -20), None, a(300, -15)])
        assert getXML(rec.toXML) == [
            "<ComponentRecord>",
            '  <LigatureAnchor index="0" Format="1">',
            '    <XCoordinate value="500"/>',
            '    <YCoordinate value="-20"/>',
            "  </LigatureAnchor>",
            '  <LigatureAnchor index="1" empty="1"/>',
            '  <LigatureAnchor index="2" Format="1">',
            '    <XCoordinate value="300"/>',
            '    <YCoordinate value="-15"/>',
            "  </LigatureAnchor>",
            "</ComponentRecord>",
        ]

    def test_buildComponentRecord_empty(self):
        assert builder.buildComponentRecord([]) is None

    def test_buildComponentRecord_None(self):
        assert builder.buildComponentRecord(None) is None

    def test_buildCoverage(self):
        cov = builder.buildCoverage(("two", "four", "two"), {"two": 2, "four": 4})
        assert getXML(cov.toXML) == [
            "<Coverage>",
            '  <Glyph value="two"/>',
            '  <Glyph value="four"/>',
            "</Coverage>",
        ]

    def test_buildCoverage_empty(self):
        # Empty coverage should return an empty Coverage, not None.
        # https://github.com/fonttools/fonttools/issues/4003
        cov = builder.buildCoverage([], {"two": 2, "four": 4})
        assert cov is not None
        assert cov.glyphs == []
        assert getXML(cov.toXML) == [
            "<Coverage>",
            "</Coverage>",
        ]

    def test_buildCursivePos(self):
        pos = builder.buildCursivePosSubtable(
            {"two": (self.ANCHOR1, self.ANCHOR2), "four": (self.ANCHOR3, self.ANCHOR1)},
            self.GLYPHMAP,
        )
        assert getXML(pos.toXML) == [
            '<CursivePos Format="1">',
            "  <Coverage>",
            '    <Glyph value="two"/>',
            '    <Glyph value="four"/>',
            "  </Coverage>",
            "  <!-- EntryExitCount=2 -->",
            '  <EntryExitRecord index="0">',
            '    <EntryAnchor Format="1">',
            '      <XCoordinate value="11"/>',
            '      <YCoordinate value="-11"/>',
            "    </EntryAnchor>",
            '    <ExitAnchor Format="1">',
            '      <XCoordinate value="22"/>',
            '      <YCoordinate value="-22"/>',
            "    </ExitAnchor>",
            "  </EntryExitRecord>",
            '  <EntryExitRecord index="1">',
            '    <EntryAnchor Format="1">',
            '      <XCoordinate value="33"/>',
            '      <YCoordinate value="-33"/>',
            "    </EntryAnchor>",
            '    <ExitAnchor Format="1">',
            '      <XCoordinate value="11"/>',
            '      <YCoordinate value="-11"/>',
            "    </ExitAnchor>",
            "  </EntryExitRecord>",
            "</CursivePos>",
        ]

    def test_buildCursivePos_format2(self):
        pos = builder.buildCursivePosSubtable(
            {"two": (self.ANCHOR1, self.ANCHOR2)},
            ExtendedGlyphMap(self.GLYPHMAP),
        )
        assert pos.Format == 2
        assert isinstance(pos.EntryExitRecord[0], otTables.EntryExit2)

    def test_buildDevice_format1(self):
        device = builder.buildDevice({1: 1, 0: 0})
        assert getXML(device.toXML) == [
            "<Device>",
            '  <StartSize value="0"/>',
            '  <EndSize value="1"/>',
            '  <DeltaFormat value="1"/>',
            '  <DeltaValue value="[0, 1]"/>',
            "</Device>",
        ]

    def test_buildDevice_format2(self):
        device = builder.buildDevice({2: 2, 0: 1, 1: 0})
        assert getXML(device.toXML) == [
            "<Device>",
            '  <StartSize value="0"/>',
            '  <EndSize value="2"/>',
            '  <DeltaFormat value="2"/>',
            '  <DeltaValue value="[1, 0, 2]"/>',
            "</Device>",
        ]

    def test_buildDevice_format3(self):
        device = builder.buildDevice({5: 3, 1: 77})
        assert getXML(device.toXML) == [
            "<Device>",
            '  <StartSize value="1"/>',
            '  <EndSize value="5"/>',
            '  <DeltaFormat value="3"/>',
            '  <DeltaValue value="[77, 0, 0, 0, 3]"/>',
            "</Device>",
        ]

    def test_buildLigatureArray(self):
        anchor = builder.buildAnchor
        ligatureArray = builder.buildLigatureArray(
            {
                "f_i": [{2: anchor(300, -20)}, {}],
                "c_t": [{}, {1: anchor(500, 350), 2: anchor(1300, -20)}],
            },
            numMarkClasses=4,
            glyphMap=self.GLYPHMAP,
        )
        assert getXML(ligatureArray.toXML) == [
            "<LigatureArray>",
            "  <!-- LigatureCount=2 -->",
            '  <LigatureAttach index="0">',  # f_i
            "    <!-- ComponentCount=2 -->",
            '    <ComponentRecord index="0">',
            '      <LigatureAnchor index="0" empty="1"/>',
            '      <LigatureAnchor index="1" empty="1"/>',
            '      <LigatureAnchor index="2" Format="1">',
            '        <XCoordinate value="300"/>',
            '        <YCoordinate value="-20"/>',
            "      </LigatureAnchor>",
            '      <LigatureAnchor index="3" empty="1"/>',
            "    </ComponentRecord>",
            '    <ComponentRecord index="1">',
            '      <LigatureAnchor index="0" empty="1"/>',
            '      <LigatureAnchor index="1" empty="1"/>',
            '      <LigatureAnchor index="2" empty="1"/>',
            '      <LigatureAnchor index="3" empty="1"/>',
            "    </ComponentRecord>",
            "  </LigatureAttach>",
            '  <LigatureAttach index="1">',
            "    <!-- ComponentCount=2 -->",
            '    <ComponentRecord index="0">',
            '      <LigatureAnchor index="0" empty="1"/>',
            '      <LigatureAnchor index="1" empty="1"/>',
            '      <LigatureAnchor index="2" empty="1"/>',
            '      <LigatureAnchor index="3" empty="1"/>',
            "    </ComponentRecord>",
            '    <ComponentRecord index="1">',
            '      <LigatureAnchor index="0" empty="1"/>',
            '      <LigatureAnchor index="1" Format="1">',
            '        <XCoordinate value="500"/>',
            '        <YCoordinate value="350"/>',
            "      </LigatureAnchor>",
            '      <LigatureAnchor index="2" Format="1">',
            '        <XCoordinate value="1300"/>',
            '        <YCoordinate value="-20"/>',
            "      </LigatureAnchor>",
            '      <LigatureAnchor index="3" empty="1"/>',
            "    </ComponentRecord>",
            "  </LigatureAttach>",
            "</LigatureArray>",
        ]

    def test_buildLigatureAttach(self):
        anchor = builder.buildAnchor
        attach = builder.buildLigatureAttach(
            [[anchor(500, -10), None], [None, anchor(300, -20), None]]
        )
        assert getXML(attach.toXML) == [
            "<LigatureAttach>",
            "  <!-- ComponentCount=2 -->",
            '  <ComponentRecord index="0">',
            '    <LigatureAnchor index="0" Format="1">',
            '      <XCoordinate value="500"/>',
            '      <YCoordinate value="-10"/>',
            "    </LigatureAnchor>",
            '    <LigatureAnchor index="1" empty="1"/>',
            "  </ComponentRecord>",
            '  <ComponentRecord index="1">',
            '    <LigatureAnchor index="0" empty="1"/>',
            '    <LigatureAnchor index="1" Format="1">',
            '      <XCoordinate value="300"/>',
            '      <YCoordinate value="-20"/>',
            "    </LigatureAnchor>",
            '    <LigatureAnchor index="2" empty="1"/>',
            "  </ComponentRecord>",
            "</LigatureAttach>",
        ]

    def test_buildLigatureAttach_emptyComponents(self):
        attach = builder.buildLigatureAttach([[], None])
        assert getXML(attach.toXML) == [
            "<LigatureAttach>",
            "  <!-- ComponentCount=2 -->",
            '  <ComponentRecord index="0" empty="1"/>',
            '  <ComponentRecord index="1" empty="1"/>',
            "</LigatureAttach>",
        ]

    def test_buildLigatureAttach_noComponents(self):
        attach = builder.buildLigatureAttach([])
        assert getXML(attach.toXML) == [
            "<LigatureAttach>",
            "  <!-- ComponentCount=0 -->",
            "</LigatureAttach>",
        ]

    def test_buildLigCaretList(self):
        carets = builder.buildLigCaretList(
            {"f_f_i": [300, 600]}, {"c_t": [42]}, self.GLYPHMAP
        )
        assert getXML(carets.toXML) == [
            "<LigCaretList>",
            "  <Coverage>",
            '    <Glyph value="f_f_i"/>',
            '    <Glyph value="c_t"/>',
            "  </Coverage>",
            "  <!-- LigGlyphCount=2 -->",
            '  <LigGlyph index="0">',
            "    <!-- CaretCount=2 -->",
            '    <CaretValue index="0" Format="1">',
            '      <Coordinate value="300"/>',
            "    </CaretValue>",
            '    <CaretValue index="1" Format="1">',
            '      <Coordinate value="600"/>',
            "    </CaretValue>",
            "  </LigGlyph>",
            '  <LigGlyph index="1">',
            "    <!-- CaretCount=1 -->",
            '    <CaretValue index="0" Format="2">',
            '      <CaretValuePoint value="42"/>',
            "    </CaretValue>",
            "  </LigGlyph>",
            "</LigCaretList>",
        ]

    def test_buildLigCaretList_bothCoordsAndPointsForSameGlyph(self):
        carets = builder.buildLigCaretList(
            {"f_f_i": [300]}, {"f_f_i": [7]}, self.GLYPHMAP
        )
        assert getXML(carets.toXML) == [
            "<LigCaretList>",
            "  <Coverage>",
            '    <Glyph value="f_f_i"/>',
            "  </Coverage>",
            "  <!-- LigGlyphCount=1 -->",
            '  <LigGlyph index="0">',
            "    <!-- CaretCount=2 -->",
            '    <CaretValue index="0" Format="1">',
            '      <Coordinate value="300"/>',
            "    </CaretValue>",
            '    <CaretValue index="1" Format="2">',
            '      <CaretValuePoint value="7"/>',
            "    </CaretValue>",
            "  </LigGlyph>",
            "</LigCaretList>",
        ]

    def test_buildLigCaretList_extended(self):
        carets = builder.buildLigCaretList(
            {"f_f_i": [300]}, {}, ExtendedGlyphMap(self.GLYPHMAP)
        )
        assert isinstance(carets, otTables.LigCaretList2)

    def test_buildLigCaretList_empty(self):
        assert builder.buildLigCaretList({}, {}, self.GLYPHMAP) is None

    def test_buildLigCaretList_None(self):
        assert builder.buildLigCaretList(None, None, self.GLYPHMAP) is None

    def test_buildLigGlyph_coords(self):
        lig = builder.buildLigGlyph([500, 800], None)
        assert getXML(lig.toXML) == [
            "<LigGlyph>",
            "  <!-- CaretCount=2 -->",
            '  <CaretValue index="0" Format="1">',
            '    <Coordinate value="500"/>',
            "  </CaretValue>",
            '  <CaretValue index="1" Format="1">',
            '    <Coordinate value="800"/>',
            "  </CaretValue>",
            "</LigGlyph>",
        ]

    def test_buildLigGlyph_empty(self):
        assert builder.buildLigGlyph([], []) is None

    def test_buildLigGlyph_None(self):
        assert builder.buildLigGlyph(None, None) is None

    def test_buildLigGlyph_points(self):
        lig = builder.buildLigGlyph(None, [2])
        assert getXML(lig.toXML) == [
            "<LigGlyph>",
            "  <!-- CaretCount=1 -->",
            '  <CaretValue index="0" Format="2">',
            '    <CaretValuePoint value="2"/>',
            "  </CaretValue>",
            "</LigGlyph>",
        ]

    def test_buildLookup(self):
        s1 = builder.buildSingleSubstSubtable({"one": "two"})
        s2 = builder.buildSingleSubstSubtable({"three": "four"})
        lookup = builder.buildLookup([s1, s2], flags=7)
        assert getXML(lookup.toXML) == [
            "<Lookup>",
            '  <LookupType value="1"/>',
            '  <LookupFlag value="7"/><!-- rightToLeft ignoreBaseGlyphs ignoreLigatures -->',
            "  <!-- SubTableCount=2 -->",
            '  <SingleSubst index="0">',
            '    <Substitution in="one" out="two"/>',
            "  </SingleSubst>",
            '  <SingleSubst index="1">',
            '    <Substitution in="three" out="four"/>',
            "  </SingleSubst>",
            "</Lookup>",
        ]

    def test_buildLookup_badFlags(self):
        s = builder.buildSingleSubstSubtable({"one": "two"})
        with pytest.raises(
            AssertionError,
            match=(
                "if markFilterSet is None, flags must not set "
                "LOOKUP_FLAG_USE_MARK_FILTERING_SET; flags=0x0010"
            ),
        ) as excinfo:
            builder.buildLookup([s], builder.LOOKUP_FLAG_USE_MARK_FILTERING_SET, None)

    def test_buildLookup_conflictingSubtableTypes(self):
        s1 = builder.buildSingleSubstSubtable({"one": "two"})
        s2 = builder.buildAlternateSubstSubtable({"one": ["two", "three"]})
        with pytest.raises(
            AssertionError, match="all subtables must have the same LookupType"
        ) as excinfo:
            builder.buildLookup([s1, s2])

    def test_buildLookup_noSubtables(self):
        assert builder.buildLookup([]) is None
        assert builder.buildLookup(None) is None
        assert builder.buildLookup([None]) is None
        assert builder.buildLookup([None, None]) is None

    def test_buildLookup_markFilterSet(self):
        s = builder.buildSingleSubstSubtable({"one": "two"})
        flags = (
            builder.LOOKUP_FLAG_RIGHT_TO_LEFT
            | builder.LOOKUP_FLAG_USE_MARK_FILTERING_SET
        )
        lookup = builder.buildLookup([s], flags, markFilterSet=999)
        assert getXML(lookup.toXML) == [
            "<Lookup>",
            '  <LookupType value="1"/>',
            '  <LookupFlag value="17"/><!-- rightToLeft useMarkFilteringSet -->',
            "  <!-- SubTableCount=1 -->",
            '  <SingleSubst index="0">',
            '    <Substitution in="one" out="two"/>',
            "  </SingleSubst>",
            '  <MarkFilteringSet value="999"/>',
            "</Lookup>",
        ]

    def test_buildMarkArray(self):
        markArray = builder.buildMarkArray(
            {
                "acute": (7, builder.buildAnchor(300, 800)),
                "grave": (2, builder.buildAnchor(10, 80)),
            },
            self.GLYPHMAP,
        )
        assert self.GLYPHMAP["grave"] < self.GLYPHMAP["acute"]
        assert getXML(markArray.toXML) == [
            "<MarkArray>",
            "  <!-- MarkCount=2 -->",
            '  <MarkRecord index="0">',
            '    <Class value="2"/>',
            '    <MarkAnchor Format="1">',
            '      <XCoordinate value="10"/>',
            '      <YCoordinate value="80"/>',
            "    </MarkAnchor>",
            "  </MarkRecord>",
            '  <MarkRecord index="1">',
            '    <Class value="7"/>',
            '    <MarkAnchor Format="1">',
            '      <XCoordinate value="300"/>',
            '      <YCoordinate value="800"/>',
            "    </MarkAnchor>",
            "  </MarkRecord>",
            "</MarkArray>",
        ]

    def test_buildMarkBasePosSubtable(self):
        anchor = builder.buildAnchor
        marks = {
            "acute": (0, anchor(300, 700)),
            "cedilla": (1, anchor(300, -100)),
            "grave": (0, anchor(300, 700)),
        }
        bases = {
            # Make sure we can handle missing entries.
            "A": {},  # no entry for any markClass
            "B": {0: anchor(500, 900)},  # only markClass 0 specified
            "C": {1: anchor(500, -10)},  # only markClass 1 specified
            "a": {0: anchor(500, 400), 1: anchor(500, -20)},
            "b": {0: anchor(500, 800), 1: anchor(500, -20)},
        }
        table = builder.buildMarkBasePosSubtable(marks, bases, self.GLYPHMAP)
        assert getXML(table.toXML) == [
            '<MarkBasePos Format="1">',
            "  <MarkCoverage>",
            '    <Glyph value="grave"/>',
            '    <Glyph value="acute"/>',
            '    <Glyph value="cedilla"/>',
            "  </MarkCoverage>",
            "  <BaseCoverage>",
            '    <Glyph value="A"/>',
            '    <Glyph value="B"/>',
            '    <Glyph value="C"/>',
            '    <Glyph value="a"/>',
            '    <Glyph value="b"/>',
            "  </BaseCoverage>",
            "  <!-- ClassCount=2 -->",
            "  <MarkArray>",
            "    <!-- MarkCount=3 -->",
            '    <MarkRecord index="0">',  # grave
            '      <Class value="0"/>',
            '      <MarkAnchor Format="1">',
            '        <XCoordinate value="300"/>',
            '        <YCoordinate value="700"/>',
            "      </MarkAnchor>",
            "    </MarkRecord>",
            '    <MarkRecord index="1">',  # acute
            '      <Class value="0"/>',
            '      <MarkAnchor Format="1">',
            '        <XCoordinate value="300"/>',
            '        <YCoordinate value="700"/>',
            "      </MarkAnchor>",
            "    </MarkRecord>",
            '    <MarkRecord index="2">',  # cedilla
            '      <Class value="1"/>',
            '      <MarkAnchor Format="1">',
            '        <XCoordinate value="300"/>',
            '        <YCoordinate value="-100"/>',
            "      </MarkAnchor>",
            "    </MarkRecord>",
            "  </MarkArray>",
            "  <BaseArray>",
            "    <!-- BaseCount=5 -->",
            '    <BaseRecord index="0">',  # A
            '      <BaseAnchor index="0" empty="1"/>',
            '      <BaseAnchor index="1" empty="1"/>',
            "    </BaseRecord>",
            '    <BaseRecord index="1">',  # B
            '      <BaseAnchor index="0" Format="1">',
            '        <XCoordinate value="500"/>',
            '        <YCoordinate value="900"/>',
            "      </BaseAnchor>",
            '      <BaseAnchor index="1" empty="1"/>',
            "    </BaseRecord>",
            '    <BaseRecord index="2">',  # C
            '      <BaseAnchor index="0" empty="1"/>',
            '      <BaseAnchor index="1" Format="1">',
            '        <XCoordinate value="500"/>',
            '        <YCoordinate value="-10"/>',
            "      </BaseAnchor>",
            "    </BaseRecord>",
            '    <BaseRecord index="3">',  # a
            '      <BaseAnchor index="0" Format="1">',
            '        <XCoordinate value="500"/>',
            '        <YCoordinate value="400"/>',
            "      </BaseAnchor>",
            '      <BaseAnchor index="1" Format="1">',
            '        <XCoordinate value="500"/>',
            '        <YCoordinate value="-20"/>',
            "      </BaseAnchor>",
            "    </BaseRecord>",
            '    <BaseRecord index="4">',  # b
            '      <BaseAnchor index="0" Format="1">',
            '        <XCoordinate value="500"/>',
            '        <YCoordinate value="800"/>',
            "      </BaseAnchor>",
            '      <BaseAnchor index="1" Format="1">',
            '        <XCoordinate value="500"/>',
            '        <YCoordinate value="-20"/>',
            "      </BaseAnchor>",
            "    </BaseRecord>",
            "  </BaseArray>",
            "</MarkBasePos>",
        ]

    def test_buildMarkBasePosSubtable_format2(self):
        table = builder.buildMarkBasePosSubtable(
            {"acute": (0, self.ANCHOR1)},
            {"A": {0: self.ANCHOR2}},
            ExtendedGlyphMap(self.GLYPHMAP),
        )
        assert table.Format == 2
        assert isinstance(table.MarkArray, otTables.MarkArray2)
        assert isinstance(table.BaseArray, otTables.BaseArray2)

    def test_buildMarkGlyphSetsDef(self):
        marksets = builder.buildMarkGlyphSetsDef(
            [{"acute", "grave"}, {"cedilla", "grave"}], self.GLYPHMAP
        )
        assert getXML(marksets.toXML) == [
            "<MarkGlyphSetsDef>",
            '  <MarkSetTableFormat value="1"/>',
            "  <!-- MarkSetCount=2 -->",
            '  <Coverage index="0">',
            '    <Glyph value="grave"/>',
            '    <Glyph value="acute"/>',
            "  </Coverage>",
            '  <Coverage index="1">',
            '    <Glyph value="grave"/>',
            '    <Glyph value="cedilla"/>',
            "  </Coverage>",
            "</MarkGlyphSetsDef>",
        ]

    def test_buildMarkGlyphSetsDef_empty(self):
        assert builder.buildMarkGlyphSetsDef([], self.GLYPHMAP) is None

    def test_buildMarkGlyphSetsDef_None(self):
        assert builder.buildMarkGlyphSetsDef(None, self.GLYPHMAP) is None

    def test_buildMarkGlyphSetsDef_emptyMarkSet(self):
        # Empty mark sets should produce an empty Coverage, not None/null offset.
        # https://github.com/fonttools/fonttools/issues/4003
        marksets = builder.buildMarkGlyphSetsDef(
            [{"acute", "grave"}, set()], self.GLYPHMAP
        )
        assert getXML(marksets.toXML) == [
            "<MarkGlyphSetsDef>",
            '  <MarkSetTableFormat value="1"/>',
            "  <!-- MarkSetCount=2 -->",
            '  <Coverage index="0">',
            '    <Glyph value="grave"/>',
            '    <Glyph value="acute"/>',
            "  </Coverage>",
            '  <Coverage index="1">',
            "  </Coverage>",
            "</MarkGlyphSetsDef>",
        ]

    def test_buildMarkLigPosSubtable(self):
        anchor = builder.buildAnchor
        marks = {
            "acute": (0, anchor(300, 700)),
            "cedilla": (1, anchor(300, -100)),
            "grave": (0, anchor(300, 700)),
        }
        bases = {
            "f_i": [{}, {0: anchor(200, 400)}],  # nothing on f; only 1 on i
            "c_t": [
                {0: anchor(500, 600), 1: anchor(500, -20)},  # c
                {0: anchor(1300, 800), 1: anchor(1300, -20)},  # t
            ],
        }
        table = builder.buildMarkLigPosSubtable(marks, bases, self.GLYPHMAP)
        assert getXML(table.toXML) == [
            '<MarkLigPos Format="1">',
            "  <MarkCoverage>",
            '    <Glyph value="grave"/>',
            '    <Glyph value="acute"/>',
            '    <Glyph value="cedilla"/>',
            "  </MarkCoverage>",
            "  <LigatureCoverage>",
            '    <Glyph value="f_i"/>',
            '    <Glyph value="c_t"/>',
            "  </LigatureCoverage>",
            "  <!-- ClassCount=2 -->",
            "  <MarkArray>",
            "    <!-- MarkCount=3 -->",
            '    <MarkRecord index="0">',
            '      <Class value="0"/>',
            '      <MarkAnchor Format="1">',
            '        <XCoordinate value="300"/>',
            '        <YCoordinate value="700"/>',
            "      </MarkAnchor>",
            "    </MarkRecord>",
            '    <MarkRecord index="1">',
            '      <Class value="0"/>',
            '      <MarkAnchor Format="1">',
            '        <XCoordinate value="300"/>',
            '        <YCoordinate value="700"/>',
            "      </MarkAnchor>",
            "    </MarkRecord>",
            '    <MarkRecord index="2">',
            '      <Class value="1"/>',
            '      <MarkAnchor Format="1">',
            '        <XCoordinate value="300"/>',
            '        <YCoordinate value="-100"/>',
            "      </MarkAnchor>",
            "    </MarkRecord>",
            "  </MarkArray>",
            "  <LigatureArray>",
            "    <!-- LigatureCount=2 -->",
            '    <LigatureAttach index="0">',
            "      <!-- ComponentCount=2 -->",
            '      <ComponentRecord index="0">',
            '        <LigatureAnchor index="0" empty="1"/>',
            '        <LigatureAnchor index="1" empty="1"/>',
            "      </ComponentRecord>",
            '      <ComponentRecord index="1">',
            '        <LigatureAnchor index="0" Format="1">',
            '          <XCoordinate value="200"/>',
            '          <YCoordinate value="400"/>',
            "        </LigatureAnchor>",
            '        <LigatureAnchor index="1" empty="1"/>',
            "      </ComponentRecord>",
            "    </LigatureAttach>",
            '    <LigatureAttach index="1">',
            "      <!-- ComponentCount=2 -->",
            '      <ComponentRecord index="0">',
            '        <LigatureAnchor index="0" Format="1">',
            '          <XCoordinate value="500"/>',
            '          <YCoordinate value="600"/>',
            "        </LigatureAnchor>",
            '        <LigatureAnchor index="1" Format="1">',
            '          <XCoordinate value="500"/>',
            '          <YCoordinate value="-20"/>',
            "        </LigatureAnchor>",
            "      </ComponentRecord>",
            '      <ComponentRecord index="1">',
            '        <LigatureAnchor index="0" Format="1">',
            '          <XCoordinate value="1300"/>',
            '          <YCoordinate value="800"/>',
            "        </LigatureAnchor>",
            '        <LigatureAnchor index="1" Format="1">',
            '          <XCoordinate value="1300"/>',
            '          <YCoordinate value="-20"/>',
            "        </LigatureAnchor>",
            "      </ComponentRecord>",
            "    </LigatureAttach>",
            "  </LigatureArray>",
            "</MarkLigPos>",
        ]

    def test_buildMarkLigPosSubtable_format2(self):
        table = builder.buildMarkLigPosSubtable(
            {"acute": (0, self.ANCHOR1)},
            {"f_i": [{0: self.ANCHOR2}]},
            ExtendedGlyphMap(self.GLYPHMAP),
        )
        assert table.Format == 2
        assert isinstance(table.MarkArray, otTables.MarkArray2)
        assert isinstance(table.LigatureArray, otTables.LigatureArray2)

    def test_MarkMarkPosBuilder_format2(self):
        font = ttLib.TTFont()
        font.getReverseGlyphMap = lambda: ExtendedGlyphMap(self.GLYPHMAP)
        lookupBuilder = builder.MarkMarkPosBuilder(font, None)
        lookupBuilder.marks = {"acute": ("top", self.ANCHOR1)}
        lookupBuilder.baseMarks = {"grave": {"top": self.ANCHOR2}}
        [subtable] = lookupBuilder.build().SubTable
        assert subtable.Format == 2
        assert isinstance(subtable.Mark1Array, otTables.MarkArray2)
        assert isinstance(subtable.Mark2Array, otTables.Mark2Array2)

    def test_buildMarkRecord(self):
        rec = builder.buildMarkRecord(17, builder.buildAnchor(500, -20))
        assert getXML(rec.toXML) == [
            "<MarkRecord>",
            '  <Class value="17"/>',
            '  <MarkAnchor Format="1">',
            '    <XCoordinate value="500"/>',
            '    <YCoordinate value="-20"/>',
            "  </MarkAnchor>",
            "</MarkRecord>",
        ]

    def test_buildMark2Record(self):
        a = builder.buildAnchor
        rec = builder.buildMark2Record([a(500, -20), None, a(300, -15)])
        assert getXML(rec.toXML) == [
            "<Mark2Record>",
            '  <Mark2Anchor index="0" Format="1">',
            '    <XCoordinate value="500"/>',
            '    <YCoordinate value="-20"/>',
            "  </Mark2Anchor>",
            '  <Mark2Anchor index="1" empty="1"/>',
            '  <Mark2Anchor index="2" Format="1">',
            '    <XCoordinate value="300"/>',
            '    <YCoordinate value="-15"/>',
            "  </Mark2Anchor>",
            "</Mark2Record>",
        ]

    def test_buildPairPosClassesSubtable(self):
        d20 = builder.buildValue({"XPlacement": -20})
        d50 = builder.buildValue({"XPlacement": -50})
        d0 = builder.buildValue({})
        d8020 = builder.buildValue({"XPlacement": -80, "YPlacement": -20})
        subtable = builder.buildPairPosClassesSubtable(
            {
                (tuple("A"), tuple(["zero"])): (d0, d50),
                (tuple("A"), tuple(["one", "two"])): (None, d20),
                (tuple(["B", "C"]), tuple(["zero"])): (d8020, d50),
            },
            self.GLYPHMAP,
        )
        assert getXML(subtable.toXML) == [
            '<PairPos Format="2">',
            "  <Coverage>",
            '    <Glyph value="A"/>',
            '    <Glyph value="B"/>',
            '    <Glyph value="C"/>',
            "  </Coverage>",
            '  <ValueFormat1 value="3"/>',
            '  <ValueFormat2 value="1"/>',
            "  <ClassDef1>",
            '    <ClassDef glyph="A" class="1"/>',
            "  </ClassDef1>",
            "  <ClassDef2>",
            '    <ClassDef glyph="one" class="1"/>',
            '    <ClassDef glyph="two" class="1"/>',
            '    <ClassDef glyph="zero" class="2"/>',
            "  </ClassDef2>",
            "  <!-- Class1Count=2 -->",
            "  <!-- Class2Count=3 -->",
            '  <Class1Record index="0">',
            '    <Class2Record index="0">',
            '      <Value1 XPlacement="0" YPlacement="0"/>',
            '      <Value2 XPlacement="0"/>',
            "    </Class2Record>",
            '    <Class2Record index="1">',
            '      <Value1 XPlacement="0" YPlacement="0"/>',
            '      <Value2 XPlacement="0"/>',
            "    </Class2Record>",
            '    <Class2Record index="2">',
            '      <Value1 XPlacement="-80" YPlacement="-20"/>',
            '      <Value2 XPlacement="-50"/>',
            "    </Class2Record>",
            "  </Class1Record>",
            '  <Class1Record index="1">',
            '    <Class2Record index="0">',
            '      <Value1 XPlacement="0" YPlacement="0"/>',
            '      <Value2 XPlacement="0"/>',
            "    </Class2Record>",
            '    <Class2Record index="1">',
            '      <Value1 XPlacement="0" YPlacement="0"/>',
            '      <Value2 XPlacement="-20"/>',
            "    </Class2Record>",
            '    <Class2Record index="2">',
            '      <Value1 XPlacement="0" YPlacement="0"/>',
            '      <Value2 XPlacement="-50"/>',
            "    </Class2Record>",
            "  </Class1Record>",
            "</PairPos>",
        ]

    def test_buildPairPosClassesSubtable_format4(self):
        subtable = builder.buildPairPosClassesSubtable(
            {(("one",), ("two",)): (builder.buildValue({}), None)},
            ExtendedGlyphMap(self.GLYPHMAP),
        )
        assert subtable.Format == 4

    @pytest.mark.parametrize("wide", [False, True])
    @pytest.mark.parametrize("extension", [False, True])
    @pytest.mark.parametrize(
        "rules,expected",
        [
            (
                [(("a",), ("b",), -50), (("a", "aacute"), ("c",), -100)],
                {
                    ("a", "b"): -50,
                    ("a", "c"): -100,
                    ("aacute", "c"): -100,
                    ("aacute", "b"): 0,
                },
            ),
            (
                [(("a",), ("b", "c"), -50), (("a",), ("c", "d"), -100)],
                {("a", "b"): -50, ("a", "c"): -50, ("a", "d"): -100},
            ),
            (
                [(("a", "aacute"), ("b", "c"), -50), (("a", "x"), ("c", "d"), -100)],
                {("a", "c"): -50, ("a", "d"): -100, ("x", "c"): -100, ("x", "b"): 0},
            ),
            (
                [(("a",), ("b",), -50), (("a",), ("b",), -100)],
                {("a", "b"): -100},
            ),
            (
                [
                    (("a",), ("b",), -50),
                    (("a", "aacute"), ("b", "c"), -100),
                    (("a",), ("b",), -150),
                ],
                {("a", "b"): -50, ("a", "c"): -100, ("aacute", "b"): -100},
            ),
            (
                [(("a",), ("b",), -50), None, (("a", "aacute"), ("c",), -100)],
                {("a", "b"): -50, ("a", "c"): 0, ("aacute", "c"): -100},
            ),
            (
                [
                    (("a",), ("b", "c"), -30),
                    (("d",), ("c", "x"), -60),
                    (("a", "aacute"), ("x",), -90),
                ],
                {
                    ("a", "c"): -30,
                    ("a", "x"): -90,
                    ("d", "c"): -60,
                    ("d", "x"): -60,
                    ("aacute", "x"): -90,
                },
            ),
        ],
    )
    def test_class_pair_overlap_roundtrip(self, rules, expected, extension, wide):
        font = ttLib.TTFont()
        glyphs = [".notdef"]
        if wide:
            glyphs.extend(f"padding{i}" for i in range(0x10000))
        glyphs.extend(["a", "aacute", "b", "c", "d", "x"])
        font.setGlyphOrder(glyphs)
        lookup_builder = builder.PairPosBuilder(font, None)
        subtable_builder = builder.ClassPairPosSubtableBuilder(lookup_builder)
        for rule in rules:
            if rule is None:
                subtable_builder.addSubtableBreak()
                continue
            left, right, advance = rule
            subtable_builder.addPair(
                left, builder.buildValue({"XAdvance": advance}), right, None
            )
        lookup = builder.buildLookup(
            subtable_builder.subtables(), table="GPOS", extension=extension
        )
        writer = OTTableWriter(tableTag="GPOS")
        lookup.compile(writer, font)
        reloaded = otTables.Lookup()
        reloaded.decompile(OTTableReader(writer.getAllData(), tableTag="GPOS"), font)
        for (left, right), advance in expected.items():
            actual = 0
            for subtable in reloaded.SubTable:
                if extension:
                    subtable = subtable.ExtSubTable
                if left not in subtable.Coverage.glyphs:
                    continue
                row = subtable.ClassDef1.classDefs.get(left, 0)
                column = subtable.ClassDef2.classDefs.get(right, 0)
                value = subtable.Class1Record[row].Class2Record[column].Value1
                actual = getattr(value, "XAdvance", 0)
                break
            assert actual == advance, (left, right)

    def test_buildPairPosGlyphs(self):
        d50 = builder.buildValue({"XPlacement": -50})
        d8020 = builder.buildValue({"XPlacement": -80, "YPlacement": -20})
        subtables = builder.buildPairPosGlyphs(
            {("A", "zero"): (None, d50), ("A", "one"): (d8020, d50)}, self.GLYPHMAP
        )
        assert sum([getXML(t.toXML) for t in subtables], []) == [
            '<PairPos Format="1">',
            "  <Coverage>",
            '    <Glyph value="A"/>',
            "  </Coverage>",
            '  <ValueFormat1 value="0"/>',
            '  <ValueFormat2 value="1"/>',
            "  <!-- PairSetCount=1 -->",
            '  <PairSet index="0">',
            "    <!-- PairValueCount=1 -->",
            '    <PairValueRecord index="0">',
            '      <SecondGlyph value="zero"/>',
            '      <Value2 XPlacement="-50"/>',
            "    </PairValueRecord>",
            "  </PairSet>",
            "</PairPos>",
            '<PairPos Format="1">',
            "  <Coverage>",
            '    <Glyph value="A"/>',
            "  </Coverage>",
            '  <ValueFormat1 value="3"/>',
            '  <ValueFormat2 value="1"/>',
            "  <!-- PairSetCount=1 -->",
            '  <PairSet index="0">',
            "    <!-- PairValueCount=1 -->",
            '    <PairValueRecord index="0">',
            '      <SecondGlyph value="one"/>',
            '      <Value1 XPlacement="-80" YPlacement="-20"/>',
            '      <Value2 XPlacement="-50"/>',
            "    </PairValueRecord>",
            "  </PairSet>",
            "</PairPos>",
        ]

    def test_buildPairPosGlyphsSubtable(self):
        d20 = builder.buildValue({"XPlacement": -20})
        d50 = builder.buildValue({"XPlacement": -50})
        d0 = builder.buildValue({})
        d8020 = builder.buildValue({"XPlacement": -80, "YPlacement": -20})
        subtable = builder.buildPairPosGlyphsSubtable(
            {
                ("A", "zero"): (d0, d50),
                ("A", "one"): (None, d20),
                ("B", "five"): (d8020, d50),
            },
            self.GLYPHMAP,
        )

        assert getXML(subtable.toXML) == [
            '<PairPos Format="1">',
            "  <Coverage>",
            '    <Glyph value="A"/>',
            '    <Glyph value="B"/>',
            "  </Coverage>",
            '  <ValueFormat1 value="3"/>',
            '  <ValueFormat2 value="1"/>',
            "  <!-- PairSetCount=2 -->",
            '  <PairSet index="0">',
            "    <!-- PairValueCount=2 -->",
            '    <PairValueRecord index="0">',
            '      <SecondGlyph value="zero"/>',
            '      <Value1 XPlacement="0" YPlacement="0"/>',
            '      <Value2 XPlacement="-50"/>',
            "    </PairValueRecord>",
            '    <PairValueRecord index="1">',
            '      <SecondGlyph value="one"/>',
            '      <Value1 XPlacement="0" YPlacement="0"/>',
            '      <Value2 XPlacement="-20"/>',
            "    </PairValueRecord>",
            "  </PairSet>",
            '  <PairSet index="1">',
            "    <!-- PairValueCount=1 -->",
            '    <PairValueRecord index="0">',
            '      <SecondGlyph value="five"/>',
            '      <Value1 XPlacement="-80" YPlacement="-20"/>',
            '      <Value2 XPlacement="-50"/>',
            "    </PairValueRecord>",
            "  </PairSet>",
            "</PairPos>",
        ]

    def test_buildPairPosGlyphsSubtable_format3(self):
        subtable = builder.buildPairPosGlyphsSubtable(
            {("one", "two"): (builder.buildValue({}), None)},
            ExtendedGlyphMap(self.GLYPHMAP),
        )
        assert subtable.Format == 3
        assert isinstance(subtable.PairSet[0], otTables.PairSet2)
        assert isinstance(subtable.PairSet[0].PairValueRecord[0], otTables.PairValue2)

    def test_buildSinglePos(self):
        subtables = builder.buildSinglePos(
            {
                "one": builder.buildValue({"XPlacement": 500}),
                "two": builder.buildValue({"XPlacement": 500}),
                "three": builder.buildValue({"XPlacement": 200}),
                "four": builder.buildValue({"XPlacement": 400}),
                "five": builder.buildValue({"XPlacement": 500}),
                "six": builder.buildValue({"YPlacement": -6}),
            },
            self.GLYPHMAP,
        )
        assert sum([getXML(t.toXML) for t in subtables], []) == [
            '<SinglePos Format="2">',
            "  <Coverage>",
            '    <Glyph value="one"/>',
            '    <Glyph value="two"/>',
            '    <Glyph value="three"/>',
            '    <Glyph value="four"/>',
            '    <Glyph value="five"/>',
            "  </Coverage>",
            '  <ValueFormat value="1"/>',
            "  <!-- ValueCount=5 -->",
            '  <Value index="0" XPlacement="500"/>',
            '  <Value index="1" XPlacement="500"/>',
            '  <Value index="2" XPlacement="200"/>',
            '  <Value index="3" XPlacement="400"/>',
            '  <Value index="4" XPlacement="500"/>',
            "</SinglePos>",
            '<SinglePos Format="1">',
            "  <Coverage>",
            '    <Glyph value="six"/>',
            "  </Coverage>",
            '  <ValueFormat value="2"/>',
            '  <Value YPlacement="-6"/>',
            "</SinglePos>",
        ]

    def test_buildSinglePos_ValueFormat0(self):
        subtables = builder.buildSinglePos(
            {"zero": builder.buildValue({})}, self.GLYPHMAP
        )
        assert sum([getXML(t.toXML) for t in subtables], []) == [
            '<SinglePos Format="1">',
            "  <Coverage>",
            '    <Glyph value="zero"/>',
            "  </Coverage>",
            '  <ValueFormat value="0"/>',
            "</SinglePos>",
        ]

    def test_buildSinglePosSubtable_format1(self):
        subtable = builder.buildSinglePosSubtable(
            {
                "one": builder.buildValue({"XPlacement": 777}),
                "two": builder.buildValue({"XPlacement": 777}),
            },
            self.GLYPHMAP,
        )
        assert getXML(subtable.toXML) == [
            '<SinglePos Format="1">',
            "  <Coverage>",
            '    <Glyph value="one"/>',
            '    <Glyph value="two"/>',
            "  </Coverage>",
            '  <ValueFormat value="1"/>',
            '  <Value XPlacement="777"/>',
            "</SinglePos>",
        ]

    def test_buildSinglePosSubtable_format2(self):
        subtable = builder.buildSinglePosSubtable(
            {
                "one": builder.buildValue({"XPlacement": 777}),
                "two": builder.buildValue({"YPlacement": -888}),
            },
            self.GLYPHMAP,
        )
        assert getXML(subtable.toXML) == [
            '<SinglePos Format="2">',
            "  <Coverage>",
            '    <Glyph value="one"/>',
            '    <Glyph value="two"/>',
            "  </Coverage>",
            '  <ValueFormat value="3"/>',
            "  <!-- ValueCount=2 -->",
            '  <Value index="0" XPlacement="777" YPlacement="0"/>',
            '  <Value index="1" XPlacement="0" YPlacement="-888"/>',
            "</SinglePos>",
        ]

    def test_buildSinglePosSubtable_format3(self):
        subtable = builder.buildSinglePosSubtable(
            {"one": builder.buildValue({"XPlacement": 777})},
            ExtendedGlyphMap(self.GLYPHMAP),
        )
        assert subtable.Format == 3

    def test_buildSinglePosSubtable_format4(self):
        subtable = builder.buildSinglePosSubtable(
            {
                "one": builder.buildValue({"XPlacement": 777}),
                "two": builder.buildValue({"YPlacement": -888}),
            },
            ExtendedGlyphMap(self.GLYPHMAP),
        )
        assert subtable.Format == 4

    def test_buildValue(self):
        value = builder.buildValue({"XPlacement": 7, "YPlacement": 23})
        func = lambda writer, font: value.toXML(writer, font, valueName="Val")
        assert getXML(func) == ['<Val XPlacement="7" YPlacement="23"/>']

    def test_getLigatureSortKey(self):
        components = lambda s: [tuple(word) for word in s.split()]
        c = components("fi fl ff ffi fff")
        c.sort(key=otTables.LigatureSubst._getLigatureSortKey)
        assert c == components("ffi fff fi fl ff")

    def test_getSinglePosValueKey(self):
        device = builder.buildDevice({10: 1, 11: 3})
        a1 = builder.buildValue({"XPlacement": 500, "XPlaDevice": device})
        a2 = builder.buildValue({"XPlacement": 500, "XPlaDevice": device})
        b = builder.buildValue({"XPlacement": 500})
        keyA1 = builder._getSinglePosValueKey(a1)
        keyA2 = builder._getSinglePosValueKey(a1)
        keyB = builder._getSinglePosValueKey(b)
        assert keyA1 == keyA2
        assert hash(keyA1) == hash(keyA2)
        assert keyA1 != keyB
        assert hash(keyA1) != hash(keyB)


class ClassDefBuilderTest(object):
    def test_build_usingClass0(self):
        b = builder.ClassDefBuilder(useClass0=True)
        b.add({"aa", "bb"})
        b.add({"a", "b"})
        b.add({"c"})
        b.add({"e", "f", "g", "h"})
        cdef = b.build()
        assert isinstance(cdef, otTables.ClassDef)
        assert cdef.classDefs == {"a": 1, "b": 1, "c": 3, "aa": 2, "bb": 2}

    def test_build_notUsingClass0(self):
        b = builder.ClassDefBuilder(useClass0=False)
        b.add({"a", "b"})
        b.add({"c"})
        b.add({"e", "f", "g", "h"})
        cdef = b.build()
        assert isinstance(cdef, otTables.ClassDef)
        assert cdef.classDefs == {
            "a": 2,
            "b": 2,
            "c": 3,
            "e": 1,
            "f": 1,
            "g": 1,
            "h": 1,
        }

    def test_canAdd(self):
        b = builder.ClassDefBuilder(useClass0=True)
        b.add({"a", "b", "c", "d"})
        b.add({"e", "f"})
        assert b.canAdd({"a", "b", "c", "d"})
        assert b.canAdd({"e", "f"})
        assert b.canAdd({"g", "h", "i"})
        assert not b.canAdd({"b", "c", "d"})
        assert not b.canAdd({"a", "b", "c", "d", "e", "f"})
        assert not b.canAdd({"d", "e", "f"})
        assert not b.canAdd({"f"})

    def test_add_exception(self):
        b = builder.ClassDefBuilder(useClass0=True)
        b.add({"a", "b", "c"})
        with pytest.raises(error.OpenTypeLibError):
            b.add({"a", "d"})


buildStatTable_test_data = [
    (
        [
            dict(
                tag="wght",
                name="Weight",
                values=[
                    dict(value=100, name="Thin"),
                    dict(value=400, name="Regular", flags=0x2),
                    dict(value=900, name="Black"),
                ],
            )
        ],
        None,
        "Regular",
        [
            "  <STAT>",
            '    <Version value="0x00010001"/>',
            '    <DesignAxisRecordSize value="8"/>',
            "    <!-- DesignAxisCount=1 -->",
            "    <DesignAxisRecord>",
            '      <Axis index="0">',
            '        <AxisTag value="wght"/>',
            '        <AxisNameID value="257"/>  <!-- Weight -->',
            '        <AxisOrdering value="0"/>',
            "      </Axis>",
            "    </DesignAxisRecord>",
            "    <!-- AxisValueCount=3 -->",
            "    <AxisValueArray>",
            '      <AxisValue index="0" Format="1">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="0"/>',
            '        <ValueNameID value="258"/>  <!-- Thin -->',
            '        <Value value="100.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="1" Format="1">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="2"/>  <!-- ElidableAxisValueName -->',
            '        <ValueNameID value="256"/>  <!-- Regular -->',
            '        <Value value="400.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="2" Format="1">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="0"/>',
            '        <ValueNameID value="259"/>  <!-- Black -->',
            '        <Value value="900.0"/>',
            "      </AxisValue>",
            "    </AxisValueArray>",
            '    <ElidedFallbackNameID value="256"/>  <!-- Regular -->',
            "  </STAT>",
        ],
    ),
    (
        [
            dict(
                tag="wght",
                name=dict(en="Weight", nl="Gewicht"),
                values=[
                    dict(value=100, name=dict(en="Thin", nl="Dun")),
                    dict(value=400, name="Regular", flags=0x2),
                    dict(value=900, name="Black"),
                ],
            ),
            dict(
                tag="wdth",
                name="Width",
                values=[
                    dict(value=50, name="Condensed"),
                    dict(value=100, name="Regular", flags=0x2),
                    dict(value=200, name="Extended"),
                ],
            ),
        ],
        None,
        2,
        [
            "  <STAT>",
            '    <Version value="0x00010001"/>',
            '    <DesignAxisRecordSize value="8"/>',
            "    <!-- DesignAxisCount=2 -->",
            "    <DesignAxisRecord>",
            '      <Axis index="0">',
            '        <AxisTag value="wght"/>',
            '        <AxisNameID value="256"/>  <!-- Weight -->',
            '        <AxisOrdering value="0"/>',
            "      </Axis>",
            '      <Axis index="1">',
            '        <AxisTag value="wdth"/>',
            '        <AxisNameID value="260"/>  <!-- Width -->',
            '        <AxisOrdering value="1"/>',
            "      </Axis>",
            "    </DesignAxisRecord>",
            "    <!-- AxisValueCount=6 -->",
            "    <AxisValueArray>",
            '      <AxisValue index="0" Format="1">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="0"/>',
            '        <ValueNameID value="257"/>  <!-- Thin -->',
            '        <Value value="100.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="1" Format="1">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="2"/>  <!-- ElidableAxisValueName -->',
            '        <ValueNameID value="258"/>  <!-- Regular -->',
            '        <Value value="400.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="2" Format="1">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="0"/>',
            '        <ValueNameID value="259"/>  <!-- Black -->',
            '        <Value value="900.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="3" Format="1">',
            '        <AxisIndex value="1"/>',
            '        <Flags value="0"/>',
            '        <ValueNameID value="261"/>  <!-- Condensed -->',
            '        <Value value="50.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="4" Format="1">',
            '        <AxisIndex value="1"/>',
            '        <Flags value="2"/>  <!-- ElidableAxisValueName -->',
            '        <ValueNameID value="258"/>  <!-- Regular -->',
            '        <Value value="100.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="5" Format="1">',
            '        <AxisIndex value="1"/>',
            '        <Flags value="0"/>',
            '        <ValueNameID value="262"/>  <!-- Extended -->',
            '        <Value value="200.0"/>',
            "      </AxisValue>",
            "    </AxisValueArray>",
            '    <ElidedFallbackNameID value="2"/>  <!-- missing from name table -->',
            "  </STAT>",
        ],
    ),
    (
        [
            dict(
                tag="wght",
                name="Weight",
                values=[
                    dict(value=400, name="Regular", flags=0x2),
                    dict(value=600, linkedValue=650, name="Bold"),
                ],
            )
        ],
        None,
        18,
        [
            "  <STAT>",
            '    <Version value="0x00010001"/>',
            '    <DesignAxisRecordSize value="8"/>',
            "    <!-- DesignAxisCount=1 -->",
            "    <DesignAxisRecord>",
            '      <Axis index="0">',
            '        <AxisTag value="wght"/>',
            '        <AxisNameID value="256"/>  <!-- Weight -->',
            '        <AxisOrdering value="0"/>',
            "      </Axis>",
            "    </DesignAxisRecord>",
            "    <!-- AxisValueCount=2 -->",
            "    <AxisValueArray>",
            '      <AxisValue index="0" Format="1">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="2"/>  <!-- ElidableAxisValueName -->',
            '        <ValueNameID value="257"/>  <!-- Regular -->',
            '        <Value value="400.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="1" Format="3">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="0"/>',
            '        <ValueNameID value="258"/>  <!-- Bold -->',
            '        <Value value="600.0"/>',
            '        <LinkedValue value="650.0"/>',
            "      </AxisValue>",
            "    </AxisValueArray>",
            '    <ElidedFallbackNameID value="18"/>  <!-- missing from name table -->',
            "  </STAT>",
        ],
    ),
    (
        [
            dict(
                tag="opsz",
                name="Optical Size",
                values=[
                    dict(nominalValue=6, rangeMaxValue=10, name="Small"),
                    dict(
                        rangeMinValue=10,
                        nominalValue=14,
                        rangeMaxValue=24,
                        name="Text",
                        flags=0x2,
                    ),
                    dict(rangeMinValue=24, nominalValue=600, name="Display"),
                ],
            )
        ],
        None,
        2,
        [
            "  <STAT>",
            '    <Version value="0x00010001"/>',
            '    <DesignAxisRecordSize value="8"/>',
            "    <!-- DesignAxisCount=1 -->",
            "    <DesignAxisRecord>",
            '      <Axis index="0">',
            '        <AxisTag value="opsz"/>',
            '        <AxisNameID value="256"/>  <!-- Optical Size -->',
            '        <AxisOrdering value="0"/>',
            "      </Axis>",
            "    </DesignAxisRecord>",
            "    <!-- AxisValueCount=3 -->",
            "    <AxisValueArray>",
            '      <AxisValue index="0" Format="2">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="0"/>',
            '        <ValueNameID value="257"/>  <!-- Small -->',
            '        <NominalValue value="6.0"/>',
            '        <RangeMinValue value="-32768.0"/>',
            '        <RangeMaxValue value="10.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="1" Format="2">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="2"/>  <!-- ElidableAxisValueName -->',
            '        <ValueNameID value="258"/>  <!-- Text -->',
            '        <NominalValue value="14.0"/>',
            '        <RangeMinValue value="10.0"/>',
            '        <RangeMaxValue value="24.0"/>',
            "      </AxisValue>",
            '      <AxisValue index="2" Format="2">',
            '        <AxisIndex value="0"/>',
            '        <Flags value="0"/>',
            '        <ValueNameID value="259"/>  <!-- Display -->',
            '        <NominalValue value="600.0"/>',
            '        <RangeMinValue value="24.0"/>',
            '        <RangeMaxValue value="32767.99998"/>',
            "      </AxisValue>",
            "    </AxisValueArray>",
            '    <ElidedFallbackNameID value="2"/>  <!-- missing from name table -->',
            "  </STAT>",
        ],
    ),
    (
        [
            dict(tag="wght", name="Weight", ordering=1, values=[]),
            dict(
                tag="ABCD",
                name="ABCDTest",
                ordering=0,
                values=[dict(value=100, name="Regular", flags=0x2)],
            ),
        ],
        [dict(location=dict(wght=300, ABCD=100), name="Regular ABCD")],
        18,
        [
            "  <STAT>",
            '    <Version value="0x00010002"/>',
            '    <DesignAxisRecordSize value="8"/>',
            "    <!-- DesignAxisCount=2 -->",
            "    <DesignAxisRecord>",
            '      <Axis index="0">',
            '        <AxisTag value="wght"/>',
            '        <AxisNameID value="256"/>  <!-- Weight -->',
            '        <AxisOrdering value="1"/>',
            "      </Axis>",
            '      <Axis index="1">',
            '        <AxisTag value="ABCD"/>',
            '        <AxisNameID value="257"/>  <!-- ABCDTest -->',
            '        <AxisOrdering value="0"/>',
            "      </Axis>",
            "    </DesignAxisRecord>",
            "    <!-- AxisValueCount=2 -->",
            "    <AxisValueArray>",
            '      <AxisValue index="0" Format="4">',
            "        <!-- AxisCount=2 -->",
            '        <Flags value="0"/>',
            '        <ValueNameID value="259"/>  <!-- Regular ABCD -->',
            '        <AxisValueRecord index="0">',
            '          <AxisIndex value="0"/>',
            '          <Value value="300.0"/>',
            "        </AxisValueRecord>",
            '        <AxisValueRecord index="1">',
            '          <AxisIndex value="1"/>',
            '          <Value value="100.0"/>',
            "        </AxisValueRecord>",
            "      </AxisValue>",
            '      <AxisValue index="1" Format="1">',
            '        <AxisIndex value="1"/>',
            '        <Flags value="2"/>  <!-- ElidableAxisValueName -->',
            '        <ValueNameID value="258"/>  <!-- Regular -->',
            '        <Value value="100.0"/>',
            "      </AxisValue>",
            "    </AxisValueArray>",
            '    <ElidedFallbackNameID value="18"/>  <!-- missing from name table -->',
            "  </STAT>",
        ],
    ),
]


@pytest.mark.parametrize(
    "axes, axisValues, elidedFallbackName, expected_ttx", buildStatTable_test_data
)
def test_buildStatTable(axes, axisValues, elidedFallbackName, expected_ttx):
    font = ttLib.TTFont()
    font["name"] = ttLib.newTable("name")
    font["name"].names = []
    # https://github.com/fonttools/fonttools/issues/1985
    # Add nameID < 256 that matches a test axis name, to test whether
    # the nameID is not reused: AxisNameIDs must be > 255 according
    # to the spec.
    font["name"].addMultilingualName(dict(en="ABCDTest"), nameID=6)
    builder.buildStatTable(font, axes, axisValues, elidedFallbackName)
    f = io.StringIO()
    font.saveXML(f, tables=["STAT"])
    ttx = f.getvalue().splitlines()
    ttx = ttx[3:-2]  # strip XML header and <ttFont> element
    assert expected_ttx == ttx
    # Compile and round-trip
    f = io.BytesIO()
    font.save(f)
    font = ttLib.TTFont(f)
    f = io.StringIO()
    font.saveXML(f, tables=["STAT"])
    ttx = f.getvalue().splitlines()
    ttx = ttx[3:-2]  # strip XML header and <ttFont> element
    assert expected_ttx == ttx


def test_buildStatTable_platform_specific_names():
    # PR: https://github.com/fonttools/fonttools/pull/2528
    # Introduce new 'platform' feature for creating a STAT table.
    # Set windowsNames and or macNames to create name table entries
    # in the specified platforms
    font_obj = ttLib.TTFont()
    font_obj["name"] = ttLib.newTable("name")
    font_obj["name"].names = []

    wght_values = [
        dict(nominalValue=200, rangeMinValue=200, rangeMaxValue=250, name="ExtraLight"),
        dict(nominalValue=300, rangeMinValue=250, rangeMaxValue=350, name="Light"),
        dict(
            nominalValue=400,
            rangeMinValue=350,
            rangeMaxValue=450,
            name="Regular",
            flags=0x2,
        ),
        dict(nominalValue=500, rangeMinValue=450, rangeMaxValue=650, name="Medium"),
        dict(nominalValue=700, rangeMinValue=650, rangeMaxValue=750, name="Bold"),
        dict(nominalValue=800, rangeMinValue=750, rangeMaxValue=850, name="ExtraBold"),
        dict(nominalValue=900, rangeMinValue=850, rangeMaxValue=900, name="Black"),
    ]

    AXES = [
        dict(
            tag="wght",
            name="Weight",
            ordering=1,
            values=wght_values,
        ),
    ]

    font_obj["name"].setName("ExtraLight", 260, 3, 1, 0x409)
    font_obj["name"].setName("Light", 261, 3, 1, 0x409)
    font_obj["name"].setName("Regular", 262, 3, 1, 0x409)
    font_obj["name"].setName("Medium", 263, 3, 1, 0x409)
    font_obj["name"].setName("Bold", 264, 3, 1, 0x409)
    font_obj["name"].setName("ExtraBold", 265, 3, 1, 0x409)
    font_obj["name"].setName("Black", 266, 3, 1, 0x409)

    font_obj["name"].setName("Weight", 270, 3, 1, 0x409)

    expected_names = [x.string for x in font_obj["name"].names]

    builder.buildStatTable(font_obj, AXES, windowsNames=True, macNames=False)
    actual_names = [x.string for x in font_obj["name"].names]

    # no new name records were added by buildStatTable
    # because windows-only names with the same strings were already present
    assert expected_names == actual_names

    font_obj["name"].removeNames(nameID=270)
    expected_names = [x.string for x in font_obj["name"].names] + ["Weight"]

    builder.buildStatTable(font_obj, AXES, windowsNames=True, macNames=False)
    actual_names = [x.string for x in font_obj["name"].names]
    # One new name records 'Weight' were added by buildStatTable
    assert expected_names == actual_names

    builder.buildStatTable(font_obj, AXES, windowsNames=True, macNames=True)
    actual_names = [x.string for x in font_obj["name"].names]
    expected_names = [
        "Weight",
        "Weight",
        "Weight",
        "ExtraLight",
        "ExtraLight",
        "ExtraLight",
        "Light",
        "Light",
        "Light",
        "Regular",
        "Regular",
        "Regular",
        "Medium",
        "Medium",
        "Medium",
        "Bold",
        "Bold",
        "Bold",
        "ExtraBold",
        "ExtraBold",
        "ExtraBold",
        "Black",
        "Black",
        "Black",
    ]
    # Because there is an inconsistency in the names add new name IDs
    # for each platform -> windowsNames=True, macNames=True
    assert sorted(expected_names) == sorted(actual_names)


def test_stat_infinities():
    negInf = floatToFixed(builder.AXIS_VALUE_NEGATIVE_INFINITY, 16)
    assert struct.pack(">l", negInf) == b"\x80\x00\x00\x00"
    posInf = floatToFixed(builder.AXIS_VALUE_POSITIVE_INFINITY, 16)
    assert struct.pack(">l", posInf) == b"\x7f\xff\xff\xff"


def test_buildMathTable_empty():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder([])
    builder.buildMathTable(ttFont)

    assert "MATH" in ttFont
    mathTable = ttFont["MATH"].table
    assert mathTable.Version == 0x00010000

    assert mathTable.MathConstants is None
    assert mathTable.MathGlyphInfo is None
    assert mathTable.MathVariants is None


def test_buildMathTable_constants():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder([])
    constants = {
        "AccentBaseHeight": 516,
        "AxisHeight": 262,
        "DelimitedSubFormulaMinHeight": 1500,
        "DisplayOperatorMinHeight": 2339,
        "FlattenedAccentBaseHeight": 698,
        "FractionDenomDisplayStyleGapMin": 198,
        "FractionDenominatorDisplayStyleShiftDown": 698,
        "FractionDenominatorGapMin": 66,
        "FractionDenominatorShiftDown": 465,
        "FractionNumDisplayStyleGapMin": 198,
        "FractionNumeratorDisplayStyleShiftUp": 774,
        "FractionNumeratorGapMin": 66,
        "FractionNumeratorShiftUp": 516,
        "FractionRuleThickness": 66,
        "LowerLimitBaselineDropMin": 585,
        "LowerLimitGapMin": 132,
        "MathLeading": 300,
        "OverbarExtraAscender": 66,
        "OverbarRuleThickness": 66,
        "OverbarVerticalGap": 198,
        "RadicalDegreeBottomRaisePercent": 75,
        "RadicalDisplayStyleVerticalGap": 195,
        "RadicalExtraAscender": 66,
        "RadicalKernAfterDegree": -556,
        "RadicalKernBeforeDegree": 278,
        "RadicalRuleThickness": 66,
        "RadicalVerticalGap": 82,
        "ScriptPercentScaleDown": 70,
        "ScriptScriptPercentScaleDown": 55,
        "SkewedFractionHorizontalGap": 66,
        "SkewedFractionVerticalGap": 77,
        "SpaceAfterScript": 42,
        "StackBottomDisplayStyleShiftDown": 698,
        "StackBottomShiftDown": 465,
        "StackDisplayStyleGapMin": 462,
        "StackGapMin": 198,
        "StackTopDisplayStyleShiftUp": 774,
        "StackTopShiftUp": 516,
        "StretchStackBottomShiftDown": 585,
        "StretchStackGapAboveMin": 132,
        "StretchStackGapBelowMin": 132,
        "StretchStackTopShiftUp": 165,
        "SubSuperscriptGapMin": 264,
        "SubscriptBaselineDropMin": 105,
        "SubscriptShiftDown": 140,
        "SubscriptTopMax": 413,
        "SuperscriptBaselineDropMax": 221,
        "SuperscriptBottomMaxWithSubscript": 413,
        "SuperscriptBottomMin": 129,
        "SuperscriptShiftUp": 477,
        "SuperscriptShiftUpCramped": 358,
        "UnderbarExtraDescender": 66,
        "UnderbarRuleThickness": 66,
        "UnderbarVerticalGap": 198,
        "UpperLimitBaselineRiseMin": 165,
        "UpperLimitGapMin": 132,
    }
    builder.buildMathTable(ttFont, constants=constants)
    mathTable = ttFont["MATH"].table
    assert mathTable.MathConstants
    assert mathTable.MathGlyphInfo is None
    assert mathTable.MathVariants is None
    for k, v in constants.items():
        r = getattr(mathTable.MathConstants, k)
        try:
            r = r.Value
        except AttributeError:
            pass
        assert r == v


def test_buildMathTable_italicsCorrection():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    italicsCorrections = {"A": 100, "C": 300, "D": 400, "E": 500}
    builder.buildMathTable(ttFont, italicsCorrections=italicsCorrections)
    mathTable = ttFont["MATH"].table
    assert mathTable.MathConstants is None
    assert mathTable.MathGlyphInfo
    assert mathTable.MathVariants is None
    assert set(
        mathTable.MathGlyphInfo.MathItalicsCorrectionInfo.Coverage.glyphs
    ) == set(italicsCorrections.keys())
    for glyph, correction in zip(
        mathTable.MathGlyphInfo.MathItalicsCorrectionInfo.Coverage.glyphs,
        mathTable.MathGlyphInfo.MathItalicsCorrectionInfo.ItalicsCorrection,
    ):
        assert correction.Value == italicsCorrections[glyph]


def test_buildMathTable_topAccentAttachment():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    topAccentAttachments = {"A": 10, "B": 20, "C": 30, "E": 50}
    builder.buildMathTable(ttFont, topAccentAttachments=topAccentAttachments)
    mathTable = ttFont["MATH"].table
    assert mathTable.MathConstants is None
    assert mathTable.MathGlyphInfo
    assert mathTable.MathVariants is None
    assert set(
        mathTable.MathGlyphInfo.MathTopAccentAttachment.TopAccentCoverage.glyphs
    ) == set(topAccentAttachments.keys())
    for glyph, attachment in zip(
        mathTable.MathGlyphInfo.MathTopAccentAttachment.TopAccentCoverage.glyphs,
        mathTable.MathGlyphInfo.MathTopAccentAttachment.TopAccentAttachment,
    ):
        assert attachment.Value == topAccentAttachments[glyph]


def test_buildMathTable_extendedShape():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    extendedShapes = {"A", "C", "E", "F"}
    builder.buildMathTable(ttFont, extendedShapes=extendedShapes)
    mathTable = ttFont["MATH"].table
    assert mathTable.MathConstants is None
    assert mathTable.MathGlyphInfo
    assert mathTable.MathVariants is None
    assert set(mathTable.MathGlyphInfo.ExtendedShapeCoverage.glyphs) == extendedShapes


def test_buildMathTable_mathKern():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder(["A", "B"])
    mathKerns = {
        "A": {
            "TopRight": ([10, 20], [10, 20, 30]),
            "BottomRight": ([], [10]),
            "TopLeft": ([10], [0, 20]),
            "BottomLeft": ([-10, 0], [0, 10, 20]),
        },
    }
    builder.buildMathTable(ttFont, mathKerns=mathKerns)
    mathTable = ttFont["MATH"].table
    assert mathTable.MathConstants is None
    assert mathTable.MathGlyphInfo
    assert mathTable.MathVariants is None
    assert set(mathTable.MathGlyphInfo.MathKernInfo.MathKernCoverage.glyphs) == set(
        mathKerns.keys()
    )
    for glyph, record in zip(
        mathTable.MathGlyphInfo.MathKernInfo.MathKernCoverage.glyphs,
        mathTable.MathGlyphInfo.MathKernInfo.MathKernInfoRecords,
    ):
        h, k = mathKerns[glyph]["TopRight"]
        assert [v.Value for v in record.TopRightMathKern.CorrectionHeight] == h
        assert [v.Value for v in record.TopRightMathKern.KernValue] == k
        h, k = mathKerns[glyph]["BottomRight"]
        assert [v.Value for v in record.BottomRightMathKern.CorrectionHeight] == h
        assert [v.Value for v in record.BottomRightMathKern.KernValue] == k
        h, k = mathKerns[glyph]["TopLeft"]
        assert [v.Value for v in record.TopLeftMathKern.CorrectionHeight] == h
        assert [v.Value for v in record.TopLeftMathKern.KernValue] == k
        h, k = mathKerns[glyph]["BottomLeft"]
        assert [v.Value for v in record.BottomLeftMathKern.CorrectionHeight] == h
        assert [v.Value for v in record.BottomLeftMathKern.KernValue] == k


def test_buildMathTable_vertVariants():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder(["A", "A.size1", "A.size2"])
    vertGlyphVariants = {"A": [("A.size1", 100), ("A.size2", 200)]}
    builder.buildMathTable(ttFont, vertGlyphVariants=vertGlyphVariants)
    mathTable = ttFont["MATH"].table
    assert mathTable.MathConstants is None
    assert mathTable.MathGlyphInfo is None
    assert mathTable.MathVariants
    assert set(mathTable.MathVariants.VertGlyphCoverage.glyphs) == set(
        vertGlyphVariants.keys()
    )
    for glyph, construction in zip(
        mathTable.MathVariants.VertGlyphCoverage.glyphs,
        mathTable.MathVariants.VertGlyphConstruction,
    ):
        assert [
            (r.VariantGlyph, r.AdvanceMeasurement)
            for r in construction.MathGlyphVariantRecord
        ] == vertGlyphVariants[glyph]


def test_buildMathTable_horizVariants():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder(["A", "A.size1", "A.size2"])
    horizGlyphVariants = {"A": [("A.size1", 100), ("A.size2", 200)]}
    builder.buildMathTable(ttFont, horizGlyphVariants=horizGlyphVariants)
    mathTable = ttFont["MATH"].table
    assert mathTable.MathConstants is None
    assert mathTable.MathGlyphInfo is None
    assert mathTable.MathVariants
    assert set(mathTable.MathVariants.HorizGlyphCoverage.glyphs) == set(
        horizGlyphVariants.keys()
    )
    for glyph, construction in zip(
        mathTable.MathVariants.HorizGlyphCoverage.glyphs,
        mathTable.MathVariants.HorizGlyphConstruction,
    ):
        assert [
            (r.VariantGlyph, r.AdvanceMeasurement)
            for r in construction.MathGlyphVariantRecord
        ] == horizGlyphVariants[glyph]


def test_buildMathTable_vertAssembly():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder(["A", "A.top", "A.middle", "A.bottom", "A.extender"])
    vertGlyphAssembly = {
        "A": [
            [
                ("A.bottom", 0, 0, 100, 200),
                ("A.extender", 1, 50, 50, 100),
                ("A.middle", 0, 100, 100, 200),
                ("A.extender", 1, 50, 50, 100),
                ("A.top", 0, 100, 0, 200),
            ],
            10,
        ],
    }
    builder.buildMathTable(ttFont, vertGlyphAssembly=vertGlyphAssembly)
    mathTable = ttFont["MATH"].table
    assert mathTable.MathConstants is None
    assert mathTable.MathGlyphInfo is None
    assert mathTable.MathVariants
    assert set(mathTable.MathVariants.VertGlyphCoverage.glyphs) == set(
        vertGlyphAssembly.keys()
    )
    for glyph, construction in zip(
        mathTable.MathVariants.VertGlyphCoverage.glyphs,
        mathTable.MathVariants.VertGlyphConstruction,
    ):
        assert [
            [
                (
                    r.glyph,
                    r.PartFlags,
                    r.StartConnectorLength,
                    r.EndConnectorLength,
                    r.FullAdvance,
                )
                for r in construction.GlyphAssembly.PartRecords
            ],
            construction.GlyphAssembly.ItalicsCorrection.Value,
        ] == vertGlyphAssembly[glyph]


def test_buildMathTable_horizAssembly():
    ttFont = ttLib.TTFont()
    ttFont.setGlyphOrder(["A", "A.top", "A.middle", "A.bottom", "A.extender"])
    horizGlyphAssembly = {
        "A": [
            [
                ("A.bottom", 0, 0, 100, 200),
                ("A.extender", 1, 50, 50, 100),
                ("A.middle", 0, 100, 100, 200),
                ("A.extender", 1, 50, 50, 100),
                ("A.top", 0, 100, 0, 200),
            ],
            10,
        ],
    }
    builder.buildMathTable(ttFont, horizGlyphAssembly=horizGlyphAssembly)
    mathTable = ttFont["MATH"].table
    assert mathTable.MathConstants is None
    assert mathTable.MathGlyphInfo is None
    assert mathTable.MathVariants
    assert set(mathTable.MathVariants.HorizGlyphCoverage.glyphs) == set(
        horizGlyphAssembly.keys()
    )
    for glyph, construction in zip(
        mathTable.MathVariants.HorizGlyphCoverage.glyphs,
        mathTable.MathVariants.HorizGlyphConstruction,
    ):
        assert [
            [
                (
                    r.glyph,
                    r.PartFlags,
                    r.StartConnectorLength,
                    r.EndConnectorLength,
                    r.FullAdvance,
                )
                for r in construction.GlyphAssembly.PartRecords
            ],
            construction.GlyphAssembly.ItalicsCorrection.Value,
        ] == horizGlyphAssembly[glyph]


class ChainContextualRulesetTest(object):
    @pytest.mark.parametrize(
        "builderClass",
        [builder.ChainContextSubstBuilder, builder.ChainContextPosBuilder],
    )
    @pytest.mark.parametrize("chaining", [False, True])
    def test_buildExtendedFormats(self, builderClass, chaining):
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef", "a", "b", "c", "d"])
        lookupBuilder = builderClass(font, None)
        lookupBuilder.glyphMap = ExtendedGlyphMap(font.getReverseGlyphMap())

        prefix = [["a"]] if chaining else []
        suffix = [["d"]] if chaining else []
        lookup = builder.SingleSubstBuilder(font, None)
        lookup.lookup_index = 3
        rule = builder.ChainContextualRule(
            prefix, [["b"], ["c"]], suffix, [[lookup], None]
        )
        ruleset = builder.ChainContextualRuleset()
        ruleset.addRule(rule)

        format1 = lookupBuilder.buildFormat1Subtable(ruleset, chaining)
        assert format1.Format == 4
        ruleSetAttr = "ChainedSeqRuleSet" if chaining else "SeqRuleSet"
        ruleAttr = "ChainedSeqRule" if chaining else "SeqRule"
        format1Rule = getattr(getattr(format1, ruleSetAttr)[0], ruleAttr)[0]
        assert format1Rule.InputSequence == ["c"]
        assert format1Rule.SeqLookupCount == 1
        assert format1Rule.SeqLookupRecord[0].LookupListIndex == 3
        if chaining:
            assert format1Rule.BacktrackSequence == ["a"]
            assert format1Rule.LookAheadSequence == ["d"]

        classdefs = ruleset.format2ClassDefs()
        format2 = lookupBuilder.buildFormat2Subtable(ruleset, classdefs, chaining)
        assert format2.Format == 5
        ruleSetAttr = "ChainedClassSeqRuleSet" if chaining else "ClassSeqRuleSet"
        ruleAttr = "ChainedClassSeqRule" if chaining else "ClassSeqRule"
        format2Rule = next(
            getattr(ruleSet, ruleAttr)[0]
            for ruleSet in getattr(format2, ruleSetAttr)
            if ruleSet is not None
        )
        assert len(format2Rule.InputSequence) == 1
        assert format2Rule.SeqLookupCount == 1

        if not chaining:
            format3 = lookupBuilder.buildFormat3Subtable(rule, chaining)
            assert format3.Format == 6
            assert format3.SeqLookupCount == 1
            assert format3.SeqLookupRecord[0].LookupListIndex == 3

    @pytest.mark.parametrize(
        "builder_class",
        [builder.ChainContextPosBuilder, builder.ChainContextSubstBuilder],
    )
    @pytest.mark.parametrize("extension", [False, True])
    def test_format2_overflow_falls_back_to_format3(self, builder_class, extension):
        font = ttLib.TTFont()
        glyphs = [f"g{i}" for i in range(44000)]
        font.setGlyphOrder(glyphs)
        lookup_builder = builder_class(font, None)
        lookup_builder.extension = extension
        # Alternating glyph IDs make the format-2 ClassDef too large, while
        # the equivalent format-3 Coverage fits in a single subtable.
        lookup_builder.rules.append(
            builder.ChainContextualRule([], [glyphs[::2]], [], [None])
        )
        lookup = lookup_builder.build()
        assert len(lookup.SubTable) == 1
        subtable = lookup.SubTable[0]
        if extension:
            subtable = subtable.ExtSubTable
        assert subtable.Format == 3

    def test_makeRulesets(self):
        font = ttLib.TTFont()
        font.setGlyphOrder(["a", "b", "c", "d", "A", "B", "C", "D", "E"])
        sb = builder.ChainContextSubstBuilder(font, None)
        prefix, input_, suffix, lookups = [["a"], ["b"]], [["c"]], [], [None]
        sb.rules.append(builder.ChainContextualRule(prefix, input_, suffix, lookups))

        prefix, input_, suffix, lookups = [["a"], ["d"]], [["c"]], [], [None]
        sb.rules.append(builder.ChainContextualRule(prefix, input_, suffix, lookups))

        sb.add_subtable_break(None)

        # Second subtable has some glyph classes
        prefix, input_, suffix, lookups = [["A"]], [["E"]], [], [None]
        sb.rules.append(builder.ChainContextualRule(prefix, input_, suffix, lookups))
        prefix, input_, suffix, lookups = [["A"]], [["C", "D"]], [], [None]
        sb.rules.append(builder.ChainContextualRule(prefix, input_, suffix, lookups))
        prefix, input_, suffix, lookups = [["A", "B"]], [["E"]], [], [None]
        sb.rules.append(builder.ChainContextualRule(prefix, input_, suffix, lookups))

        sb.add_subtable_break(None)

        # Third subtable has no pre/post context
        prefix, input_, suffix, lookups = [], [["E"]], [], [None]
        sb.rules.append(builder.ChainContextualRule(prefix, input_, suffix, lookups))
        prefix, input_, suffix, lookups = [], [["C", "D"]], [], [None]
        sb.rules.append(builder.ChainContextualRule(prefix, input_, suffix, lookups))

        rulesets = sb.rulesets()
        assert len(rulesets) == 3
        assert rulesets[0].hasPrefixOrSuffix
        assert not rulesets[0].hasAnyGlyphClasses
        cd = rulesets[0].format2ClassDefs()
        assert set(cd[0].classes()[1:]) == set([("d",), ("b",), ("a",)])
        assert set(cd[1].classes()[1:]) == set([("c",)])
        assert set(cd[2].classes()[1:]) == set()

        assert rulesets[1].hasPrefixOrSuffix
        assert rulesets[1].hasAnyGlyphClasses
        assert not rulesets[1].format2ClassDefs()

        assert not rulesets[2].hasPrefixOrSuffix
        assert rulesets[2].hasAnyGlyphClasses
        assert rulesets[2].format2ClassDefs()
        cd = rulesets[2].format2ClassDefs()
        assert set(cd[0].classes()[1:]) == set()
        assert set(cd[1].classes()[1:]) == set([("C", "D"), ("E",)])
        assert set(cd[2].classes()[1:]) == set()


def test_buildExtendedReverseChainSingleSubst():
    font = ttLib.TTFont()
    font.setGlyphOrder([".notdef", "a", "b", "c", "d"])
    lookupBuilder = builder.ReverseChainSingleSubstBuilder(font, None)
    lookupBuilder.glyphMap = ExtendedGlyphMap(font.getReverseGlyphMap())
    lookupBuilder.rules.append(([["a"]], [["d"]], {"c": "b"}))

    lookup = lookupBuilder.build()
    subtable = lookup.SubTable[0]
    assert subtable.Format == 2
    assert subtable.BacktrackCoverage[0].glyphs == ["a"]
    assert subtable.LookAheadCoverage[0].glyphs == ["d"]
    assert subtable.Coverage.glyphs == ["c"]
    assert subtable.Substitute == ["b"]


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main(sys.argv))
