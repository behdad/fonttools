import io
import os
import re
import struct
from fontTools import ttLib
from fontTools.ttLib import TTLibError
from fontTools.fontBuilder import FontBuilder
import unittest
from fontTools.ttLib.tables._c_m_a_p import (
    CmapSubtable,
    cmap_format_unknown,
    table__c_m_a_p,
)
from fontTools.ttLib.tables._g_l_y_f import Glyph

CURR_DIR = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
DATA_DIR = os.path.join(CURR_DIR, "data")
CMAP_FORMAT_14_TTX = os.path.join(DATA_DIR, "_c_m_a_p_format_14.ttx")
CMAP_FORMAT_14_BW_COMPAT_TTX = os.path.join(
    DATA_DIR, "_c_m_a_p_format_14_bw_compat.ttx"
)


def strip_VariableItems(string):
    # ttlib changes with the fontTools version
    string = re.sub(' ttLibVersion=".*"', "", string)
    return string


class CmapSubtableTest(unittest.TestCase):
    def makeSubtable(self, cmapFormat, platformID, platEncID, langID):
        subtable = CmapSubtable.newSubtable(cmapFormat)
        subtable.platformID, subtable.platEncID, subtable.language = (
            platformID,
            platEncID,
            langID,
        )
        return subtable

    def test_toUnicode_utf16be(self):
        subtable = self.makeSubtable(4, 0, 2, 7)
        self.assertEqual("utf_16_be", subtable.getEncoding())
        self.assertEqual(True, subtable.isUnicode())

    def test_compact_glyph_id_limits(self):
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef"] + [f"g{i}" for i in range(1, 0x10002)])
        for format in (2, 4):
            for virtual in (False, True):
                for companion in (False, True):
                    for gid in (0xFFFF, 0x10000, 0x10001):
                        with self.subTest(
                            format=format, virtual=virtual, companion=companion, gid=gid
                        ):
                            subtable = self.makeSubtable(format, 3, 1, 0)
                            subtable.cmap = {
                                65: f"gid{gid}" if virtual else font.getGlyphName(gid)
                            }
                            if companion:
                                subtable.cmap[66] = "g2"
                            if gid > 0xFFFF:
                                with self.assertRaisesRegex(struct.error, "glyph ID"):
                                    subtable.compile(font)
                            else:
                                data = subtable.compile(font)
                                reloaded = CmapSubtable.newSubtable(format)
                                reloaded.decompile(data, font)
                                expected = {65: font.getGlyphName(gid)}
                                if companion:
                                    expected[66] = "g2"
                                self.assertEqual(reloaded.cmap, expected)

    def test_toUnicode_macroman(self):
        subtable = self.makeSubtable(4, 1, 0, 7)  # MacRoman
        self.assertEqual("mac_roman", subtable.getEncoding())
        self.assertEqual(False, subtable.isUnicode())

    def test_toUnicode_macromanian(self):
        subtable = self.makeSubtable(4, 1, 0, 37)  # Mac Romanian
        self.assertNotEqual(None, subtable.getEncoding())
        self.assertEqual(False, subtable.isUnicode())

    def test_extended_mac_encodings(self):
        subtable = self.makeSubtable(4, 1, 1, 0)  # Mac Japanese
        self.assertNotEqual(None, subtable.getEncoding())
        self.assertEqual(False, subtable.isUnicode())

    def test_extended_unknown(self):
        subtable = self.makeSubtable(4, 10, 11, 12)
        self.assertEqual(subtable.getEncoding(), None)
        self.assertEqual(subtable.getEncoding("ascii"), "ascii")
        self.assertEqual(subtable.getEncoding(default="xyz"), "xyz")

    def test_decompile_truncated(self):
        # A truncated cmap table, an out-of-bounds subtable offset, or a
        # subtable whose length does not match the data used to raise a bare
        # struct.error or AssertionError instead of TTLibError.
        font = ttLib.TTFont()

        def cmap(numTables, *entries, body=b""):
            data = struct.pack(">HH", 0, numTables)
            for platformID, platEncID, offset in entries:
                data += struct.pack(">HHL", platformID, platEncID, offset)
            return data + body

        # A subtable directory with one entry pointing at `offset`; the subtable
        # header itself starts right after the 12-byte directory (offset 12).
        def one_subtable(header):
            return cmap(1, (3, 1, 12), body=header)

        cases = {
            "table shorter than the 4-byte header": (
                b"\x00\x00",
                "too short",
            ),
            "subtable directory truncated": (
                struct.pack(">HH", 0, 3) + b"ab",
                "directory is truncated",
            ),
            "offset past the end of the data": (
                cmap(1, (3, 1, 9999)),
                "out of bounds",
            ),
            # 0xFFFFFFFF pins the offset as an unsigned Offset32: read signed it
            # would be -1 and slip through as an in-range negative index.
            "offset 0xFFFFFFFF is unsigned and out of bounds": (
                cmap(1, (3, 1, 0xFFFFFFFF)),
                "out of bounds",
            ),
            # format 4 header is ">HHH" (6 bytes); a length of 4 is too small.
            "length smaller than the format header": (
                one_subtable(struct.pack(">HH", 4, 4)),
                "header is truncated",
            ),
            # length claims 20 bytes but only 6 are present after the offset.
            "length longer than the available data": (
                one_subtable(struct.pack(">HHH", 4, 20, 0)),
                "subtable is truncated",
            ),
        }
        for label, (data, pattern) in cases.items():
            with self.subTest(label):
                table = table__c_m_a_p("cmap")
                with self.assertRaisesRegex(ttLib.TTLibError, pattern):
                    table.decompile(data, font)

    def test_decompile_unknown_format_no_header_minimum(self):
        # Formats 8 and 10, and any unrecognised format, are handled by
        # cmap_format_unknown, which keeps the body verbatim instead of
        # unpacking a fixed header, so a body too short for one is fine.
        font = ttLib.TTFont()

        for format, header in [
            # 8 and 10 read a ">HHL" header off the subtable offset, so the
            # body must be 8 bytes even though the length field says 4.
            (8, struct.pack(">HHL", 8, 0, 4)),
            (10, struct.pack(">HHL", 10, 0, 4)),
            (99, struct.pack(">HH", 99, 4)),
        ]:
            with self.subTest(format=format):
                data = struct.pack(">HH", 0, 1) + struct.pack(">HHL", 3, 1, 12) + header
                table = table__c_m_a_p("cmap")
                table.decompile(data, font)
                subtable = table.tables[0]
                self.assertIsInstance(subtable, cmap_format_unknown)
                self.assertEqual(subtable.format, format)
                self.assertEqual(subtable.data, header[:4])

    def test_decompile_format_12_inconsistent_nGroups(self):
        # nGroups and length disagree: the header check used to be an assert,
        # which python -O drops, leaving a subtable claiming groups that are
        # not there.
        font = ttLib.TTFont()
        # length says 28 bytes, but nGroups == 0 accounts for the 16-byte
        # header alone.
        body = struct.pack(">HHLLL", 12, 0, 28, 0, 0) + b"\0" * 12
        data = struct.pack(">HH", 0, 1) + struct.pack(">HHL", 3, 10, 12) + body
        table = table__c_m_a_p("cmap")
        with self.assertRaisesRegex(ttLib.TTLibError, "inconsistent group count"):
            table.decompile(data, font)

    def test_decompile_subtable_format_12_truncated(self):
        # a subtable decompiled on its own does not go through the length
        # checks table__c_m_a_p.decompile does up front.
        subtable = CmapSubtable.newSubtable(12)
        data = struct.pack(">HHLLL", 12, 0, 28, 0, 1)
        with self.assertRaisesRegex(ttLib.TTLibError, "is truncated"):
            subtable.decompile(data, ttLib.TTFont())

    def test_compile_2(self):
        subtable = self.makeSubtable(2, 1, 2, 0)
        subtable.cmap = {c: "cid%05d" % c for c in range(32, 8192)}
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef"] + list(subtable.cmap.values()))
        data = subtable.compile(font)

        subtable2 = CmapSubtable.newSubtable(2)
        subtable2.decompile(data, font)
        self.assertEqual(subtable2.cmap, subtable.cmap)

    def test_compile_2_rebuild_rev_glyph_order(self):
        for fmt in [2, 4, 12]:
            subtable = self.makeSubtable(fmt, 1, 2, 0)
            subtable.cmap = {c: "cid%05d" % c for c in range(32, 8192)}
            font = ttLib.TTFont()
            font.setGlyphOrder([".notdef"] + list(subtable.cmap.values()))
            font._reverseGlyphOrderDict = (
                {}
            )  # force first KeyError branch in subtable.compile()
            data = subtable.compile(font)
            subtable2 = CmapSubtable.newSubtable(fmt)
            subtable2.decompile(data, font)
            self.assertEqual(subtable2.cmap, subtable.cmap, str(fmt))

    def test_compile_2_gids(self):
        for fmt in [2, 4, 12]:
            subtable = self.makeSubtable(fmt, 1, 3, 0)
            subtable.cmap = {0x0041: "gid001", 0x0042: "gid002"}
            font = ttLib.TTFont()
            font.setGlyphOrder([".notdef"])
            data = subtable.compile(font)

    def test_compile_2_high_gids(self):
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef"] + ["glyph%05d" % i for i in range(1, 65536)])
        for gids in [(32767,), (32768,), (32769,), (40000, 40001), (65535,)]:
            with self.subTest(gids=gids):
                subtable = self.makeSubtable(2, 1, 1, 0)
                subtable.cmap = {
                    0x8140 + i: "glyph%05d" % gid for i, gid in enumerate(gids)
                }
                data = subtable.compile(font)
                subtable2 = CmapSubtable.newSubtable(2)
                subtable2.decompile(data, font)
                self.assertEqual(subtable2.cmap, subtable.cmap)

    def test_compile_2_single_byte_only(self):
        # https://github.com/fonttools/fonttools/issues/1524
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef", "a", "b"])
        for cmap in [{0x20: "a"}, {0x41: "a", 0x42: "b"}, {0xFF: "b"}]:
            with self.subTest(cmap=cmap):
                subtable = self.makeSubtable(2, 1, 1, 0)
                subtable.cmap = cmap
                data = subtable.compile(font)
                subtable2 = CmapSubtable.newSubtable(2)
                subtable2.decompile(data, font)
                self.assertEqual(subtable2.cmap, subtable.cmap)

    def test_compile_2_lead_byte_conflict(self):
        # https://github.com/fonttools/fonttools/issues/1524
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef", "a", "b"])
        for cmap in [{0x20: "a", 0x2000: "b"}, {0x81: "a", 0x8140: "b"}]:
            with self.subTest(cmap=cmap):
                subtable = self.makeSubtable(2, 1, 1, 0)
                subtable.cmap = cmap
                with self.assertRaisesRegex(struct.error, "single-byte code"):
                    subtable.compile(font)
        # a .notdef single-byte code is left unencoded, so it does not conflict
        subtable = self.makeSubtable(2, 1, 1, 0)
        subtable.cmap = {0x20: ".notdef", 0x2000: "b"}
        data = subtable.compile(font)
        subtable2 = CmapSubtable.newSubtable(2)
        subtable2.decompile(data, font)
        self.assertEqual(subtable2.cmap, {0x2000: "b"})

    def test_compile_2_single_byte_notdef(self):
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef", "a", "b"])
        for cmap, expected in [
            ({0x41: ".notdef"}, {}),
            ({0x41: ".notdef", 0x8140: "a"}, {0x8140: "a"}),
            ({0x00: "a", 0x41: ".notdef", 0x8140: "b"}, {0x00: "a", 0x8140: "b"}),
        ]:
            with self.subTest(cmap=cmap):
                subtable = self.makeSubtable(2, 1, 1, 0)
                subtable.cmap = cmap
                data = subtable.compile(font)
                subtable2 = CmapSubtable.newSubtable(2)
                subtable2.decompile(data, font)
                self.assertEqual(subtable2.cmap, expected)

    def test_compile_decompile_4_empty(self):
        subtable = self.makeSubtable(4, 3, 1, 0)
        subtable.cmap = {}
        font = ttLib.TTFont()
        font.setGlyphOrder([])
        data = subtable.compile(font)
        subtable2 = CmapSubtable.newSubtable(4)
        subtable2.decompile(data, font)
        self.assertEqual(subtable2.cmap, {})

    def test_compile_decompile_12_13_empty(self):
        font = ttLib.TTFont()
        font.setGlyphOrder([])
        for format in (12, 13):
            with self.subTest(format=format):
                subtable = self.makeSubtable(format, 3, 10, 0)
                subtable.cmap = {}
                data = subtable.compile(font)
                self.assertEqual(len(data), 16)
                subtable2 = CmapSubtable.newSubtable(format)
                subtable2.decompile(data, font)
                self.assertEqual(subtable2.cmap, {})
                self.assertEqual(subtable2.compile(font), data)

    def test_compile_decompile_2_empty(self):
        # An all-.notdef (empty) Macintosh format 2 cmap must round-trip
        # instead of crashing on compile, just like format 4 above.
        # https://github.com/fonttools/fonttools/issues/3663
        subtable = self.makeSubtable(2, 1, 3, 0)
        subtable.cmap = {}
        font = ttLib.TTFont()
        font.setGlyphOrder([])
        data = subtable.compile(font)
        subtable2 = CmapSubtable.newSubtable(2)
        subtable2.decompile(data, font)
        self.assertEqual(subtable2.cmap, {})

    def test_decompile_compile_2_all_notdef(self):
        # A binary format 2 subtable whose only subheader maps its whole range
        # to .notdef (entryCount 0, the spec's way of encoding a notdef range)
        # decompiles to an empty cmap; recompiling it must not raise.
        # https://github.com/fonttools/fonttools/issues/3663
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef", "A", "B"])
        subHeaderKeys = b"\x00\x00" * 256  # every first byte -> subHeader 0
        # subHeader 0: firstCode, entryCount, idDelta, idRangeOffset all zero
        subHeader0 = struct.pack(">HHhH", 0, 0, 0, 0)
        body = subHeaderKeys + subHeader0
        data = struct.pack(">HHH", 2, 6 + len(body), 0) + body

        subtable = CmapSubtable.newSubtable(2)
        subtable.platformID, subtable.platEncID = 1, 3
        subtable.decompile(data, font)
        self.assertEqual(subtable.cmap, {})

        # recompiling and decompiling again must still give the empty cmap
        subtable2 = CmapSubtable.newSubtable(2)
        subtable2.decompile(subtable.compile(font), font)
        self.assertEqual(subtable2.cmap, {})

    def test_decompile_4(self):
        subtable = CmapSubtable.newSubtable(4)
        font = ttLib.TTFont()
        font.setGlyphOrder([])
        subtable.decompile(b"\0" * 3 + b"\x10" + b"\0" * 12, font)

    def test_decompile_12(self):
        subtable = CmapSubtable.newSubtable(12)
        font = ttLib.TTFont()
        font.setGlyphOrder([])
        subtable.decompile(b"\0" * 7 + b"\x10" + b"\0" * 8, font)

    @staticmethod
    def _decompile_12_or_13(format, groups):
        subtable = CmapSubtable.newSubtable(format)
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef", "a", "b", "c"])
        body = b"".join(struct.pack(">LLL", *group) for group in groups)
        header = struct.pack(">HHLLL", format, 0, 16 + len(body), 0, len(groups))
        subtable.decompile(header + body, font)
        return subtable.cmap

    def test_decompile_12_or_13_clamps_to_max_unicode(self):
        # a single group claiming the whole 32-bit range used to be expanded
        # into a list of 2**32 code points.
        for format in (12, 13):
            with self.subTest(format=format):
                with self.assertLogs(
                    "fontTools.ttLib.tables._c_m_a_p", "WARNING"
                ) as logs:
                    cmap = self._decompile_12_or_13(format, [(0x10FFFE, 0xFFFFFFFF, 1)])
                self.assertEqual(
                    cmap,
                    {
                        0x10FFFE: "a",
                        0x10FFFF: "b" if format == 12 else "a",
                    },
                )
                self.assertIn("beyond U+10FFFF", logs.output[0])

    def test_decompile_12_or_13_many_overlapping_groups(self):
        # clamping alone is not enough: repeated full-range groups would
        # still add up to far more code points than exist.
        for format in (12, 13):
            with self.subTest(format=format):
                with self.assertLogs("fontTools.ttLib.tables._c_m_a_p", "WARNING"):
                    cmap = self._decompile_12_or_13(format, [(0, 0xFFFFFFFF, 1)] * 1000)
                self.assertEqual(len(cmap), 0x110000)

    def test_decompile_12_or_13_bad_groups_skipped(self):
        # like HarfBuzz, a group that is inverted or starts before the
        # previous one ends is dropped whole, so the first group in subtable
        # order wins.
        cases = [
            (12, [(0x41, 0x43, 1), (0x42, 0x44, 2)], {0x41: "a", 0x42: "b", 0x43: "c"}),
            (12, [(0x43, 0x43, 3), (0x41, 0x42, 1)], {0x43: "c"}),
            (12, [(0x42, 0x41, 1), (0x200000, 0x200001, 1)], {}),
            (13, [(0x42, 0x41, 1), (0x200000, 0x200001, 1)], {}),
        ]
        for format, groups, expected in cases:
            with self.subTest(format=format, groups=groups):
                with self.assertLogs(
                    "fontTools.ttLib.tables._c_m_a_p", "WARNING"
                ) as logs:
                    cmap = self._decompile_12_or_13(format, groups)
                self.assertEqual(cmap, expected)
                self.assertTrue(
                    any("unsorted or overlapping" in m for m in logs.output)
                )

    def test_decompile_12_or_13_shared_endpoint(self):
        # like HarfBuzz, a group may start on the previous group's last code
        # point; the later nonzero mapping wins there, the missing glyph
        # erases nothing.
        cases = [
            (12, [(0x41, 0x42, 2), (0x42, 0x43, 1)], {0x41: "b", 0x42: "a", 0x43: "b"}),
            (13, [(0x41, 0x42, 1), (0x42, 0x43, 2)], {0x41: "a", 0x42: "b", 0x43: "b"}),
            (12, [(0x41, 0x42, 1), (0x42, 0x43, 0)], {0x41: "a", 0x42: "b", 0x43: "a"}),
            (13, [(0x41, 0x42, 1), (0x42, 0x43, 0)], {0x41: "a", 0x42: "a"}),
        ]
        for format, groups, expected in cases:
            with self.subTest(format=format, groups=groups):
                with self.assertNoLogs("fontTools.ttLib.tables._c_m_a_p", "WARNING"):
                    cmap = self._decompile_12_or_13(format, groups)
                self.assertEqual(cmap, expected)

    def test_decompile_13_full_range_missing_glyph(self):
        # maps nothing, so it is not expanded either
        cmap = self._decompile_12_or_13(13, [(0, 0x10FFFF, 0)])
        self.assertEqual(cmap, {})

    def test_decompile_12_starting_missing_glyph(self):
        cmap = self._decompile_12_or_13(12, [(0x41, 0x43, 0)])
        self.assertEqual(cmap, {0x42: "a", 0x43: "b"})

    def test_decompile_12_sorted_groups_no_warning(self):
        # adjacent groups, ending exactly at U+10FFFF
        with self.assertNoLogs("fontTools.ttLib.tables._c_m_a_p", "WARNING"):
            cmap = self._decompile_12_or_13(
                12, [(0x41, 0x42, 1), (0x43, 0x43, 3), (0x10FFFF, 0x10FFFF, 1)]
            )
        self.assertEqual(cmap, {0x41: "a", 0x42: "b", 0x43: "c", 0x10FFFF: "a"})

    @staticmethod
    def _decompile_4(segments, glyphIndexArray=()):
        # segments: (start, end, delta, rangeOffset); the 0xFFFF sentinel
        # segment is appended here.
        segments = list(segments) + [(0xFFFF, 0xFFFF, 1, 0)]
        n = len(segments)
        starts, ends, deltas, offsets = zip(*segments)
        body = (
            struct.pack(">4H", n * 2, 0, 0, 0)
            + struct.pack(f">{n}H", *ends)
            + struct.pack(">H", 0)
            + struct.pack(f">{n}H", *starts)
            + struct.pack(f">{n}H", *(d & 0xFFFF for d in deltas))
            + struct.pack(f">{n}H", *offsets)
            + struct.pack(f">{len(glyphIndexArray)}H", *glyphIndexArray)
        )
        subtable = CmapSubtable.newSubtable(4)
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef", "a", "b", "c", "d"])
        subtable.decompile(struct.pack(">3H", 4, 6 + len(body), 0) + body, font)
        return subtable.cmap

    def test_decompile_4_overlapping_segments(self):
        # every segment covers the whole BMP: each one used to be expanded
        # in full before deduplication
        cmap = self._decompile_4([(0, 0xFFFE, 1, 0)] * 8)
        self.assertEqual(len(cmap), 0xFFFF)

    def test_decompile_4_later_segment_wins(self):
        # overlapping segments keep the previous behavior (and HarfBuzz's):
        # the last nonzero mapping wins, a missing glyph erases nothing.
        # rangeOffset is in bytes from the segment's own idRangeOffset entry:
        # with 3 segments, segment 0 is 6 bytes before glyphIndexArray[0],
        # and segment 1 is 4 bytes before it, plus 6 to start at [3].
        cmap = self._decompile_4(
            [(0x41, 0x43, 0, 6), (0x42, 0x43, 0, 4 + 6)],
            glyphIndexArray=[1, 2, 3, 4, 0],
        )
        self.assertEqual(cmap, {0x41: "a", 0x42: "d", 0x43: "c"})

    def test_decompile_4_idRangeOffset_out_of_bounds(self):
        # rangeOffset is in bytes from the segment's own idRangeOffset entry:
        # 2 lands before glyphIndexArray, 0xFFF0 lands past its end.
        for rangeOffset in (2, 0xFFF0):
            with self.subTest(rangeOffset=rangeOffset):
                with self.assertRaises(TTLibError):
                    self._decompile_4(
                        [(0x41, 0x41, 0, rangeOffset)],
                        glyphIndexArray=[1, 2, 3],
                    )

    def test_buildReversed(self):
        c4 = self.makeSubtable(4, 3, 1, 0)
        c4.cmap = {0x0041: "A", 0x0391: "A"}
        c12 = self.makeSubtable(12, 3, 10, 0)
        c12.cmap = {0x10314: "u10314"}
        cmap = table__c_m_a_p()
        cmap.tables = [c4, c12]
        self.assertEqual(
            cmap.buildReversed(), {"A": {0x0041, 0x0391}, "u10314": {0x10314}}
        )

    def test_getBestCmap(self):
        c4 = self.makeSubtable(4, 3, 1, 0)
        c4.cmap = {0x0041: "A", 0x0391: "A"}
        c12 = self.makeSubtable(12, 3, 10, 0)
        c12.cmap = {0x10314: "u10314"}
        cmap = table__c_m_a_p()
        cmap.tables = [c4, c12]
        self.assertEqual(cmap.getBestCmap(), {0x10314: "u10314"})
        self.assertEqual(
            cmap.getBestCmap(cmapPreferences=[(3, 1)]), {0x0041: "A", 0x0391: "A"}
        )
        self.assertEqual(cmap.getBestCmap(cmapPreferences=[(0, 4)]), None)

    def test_font_getBestCmap(self):
        c4 = self.makeSubtable(4, 3, 1, 0)
        c4.cmap = {0x0041: "A", 0x0391: "A"}
        c12 = self.makeSubtable(12, 3, 10, 0)
        c12.cmap = {0x10314: "u10314"}
        cmap = table__c_m_a_p()
        cmap.tables = [c4, c12]
        font = ttLib.TTFont()
        font["cmap"] = cmap
        self.assertEqual(font.getBestCmap(), {0x10314: "u10314"})
        self.assertEqual(
            font.getBestCmap(cmapPreferences=[(3, 1)]), {0x0041: "A", 0x0391: "A"}
        )
        self.assertEqual(font.getBestCmap(cmapPreferences=[(0, 4)]), None)

    def test_font_getBestCmap_applies_DMAP_first(self):
        cmap4 = self.makeSubtable(4, 3, 1, 0)
        cmap4.cmap = {0x0041: "A", 0x0042: "B"}
        dmap4 = self.makeSubtable(4, 3, 1, 0)
        dmap4.cmap = {0x0041: "A.alt", 0x0043: "C"}

        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef", "A", "A.alt", "B", "C"])
        font["cmap"] = table__c_m_a_p("cmap")
        font["cmap"].tableVersion = 0
        font["cmap"].tables = [cmap4]
        font["DMAP"] = ttLib.newTable("DMAP")
        font["DMAP"].tableVersion = 0
        font["DMAP"].tables = [dmap4]

        self.assertIsInstance(font["DMAP"], table__c_m_a_p)
        self.assertEqual(
            font.getBestCmap(), {0x0041: "A.alt", 0x0042: "B", 0x0043: "C"}
        )

        data = font["DMAP"].compile(font)
        dmap = ttLib.newTable("DMAP")
        dmap.decompile(data, font)
        self.assertEqual(dmap.getBestCmap(), dmap4.cmap)

    def test_glyph_order_applies_DMAP_first(self):
        glyphOrder = [".notdef", "cmapA", "dmapA", "cmapB", "dmapC"]
        fb = FontBuilder(1024, isTTF=True)
        fb.setupGlyphOrder(glyphOrder)
        fb.setupCharacterMap({0x0041: "cmapA", 0x0042: "cmapB"})
        fb.setupGlyf({name: Glyph() for name in glyphOrder})
        fb.setupHorizontalMetrics({name: (500, 0) for name in glyphOrder})
        fb.setupHorizontalHeader()
        fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
        fb.setupOS2()
        fb.setupPost(keepGlyphNames=False)

        dmap4 = self.makeSubtable(4, 3, 1, 0)
        dmap4.cmap = {0x0041: "dmapA", 0x0043: "dmapC"}
        fb.font["DMAP"] = ttLib.newTable("DMAP")
        fb.font["DMAP"].tableVersion = 0
        fb.font["DMAP"].tables = [dmap4]

        data = io.BytesIO()
        fb.font.save(data)
        data.seek(0)
        font = ttLib.TTFont(data)

        self.assertEqual(font.getGlyphOrder(), [".notdef", "glyph00001", "A", "B", "C"])

    def test_format_14(self):
        subtable = self.makeSubtable(14, 0, 5, 0)
        subtable.cmap = {}  # dummy
        subtable.uvsDict = {
            0xFE00: [(0x0030, "zero.slash")],
            0xFE01: [(0x0030, None)],
        }
        fb = FontBuilder(1024, isTTF=True)
        font = fb.font
        fb.setupGlyphOrder([".notdef", "zero.slash"])
        fb.setupMaxp()
        fb.setupPost()
        cmap = table__c_m_a_p()
        cmap.tableVersion = 0
        cmap.tables = [subtable]
        font["cmap"] = cmap
        f = io.BytesIO()
        font.save(f)
        f.seek(0)
        font = ttLib.TTFont(f)
        self.assertEqual(font["cmap"].getcmap(0, 5).uvsDict, subtable.uvsDict)
        f = io.StringIO(newline=None)
        font.saveXML(f, tables=["cmap"])
        ttx = strip_VariableItems(f.getvalue())
        with open(CMAP_FORMAT_14_TTX) as f:
            expected = strip_VariableItems(f.read())
        self.assertEqual(ttx, expected)
        with open(CMAP_FORMAT_14_BW_COMPAT_TTX) as f:
            font.importXML(f)
        self.assertEqual(font["cmap"].getcmap(0, 5).uvsDict, subtable.uvsDict)

    def test_default_uvs_range_limit(self):
        font = ttLib.TTFont()
        font.setGlyphOrder([".notdef", "a"])
        for count in (255, 256, 257, 512, 513, 768):
            for gaps in (False, True):
                with self.subTest(count=count, gaps=gaps):
                    points = list(range(0x1000, 0x1000 + count))
                    if gaps:
                        points.extend(range(0x2000, 0x2000 + count))
                    table = self.makeSubtable(14, 0, 5, 0)
                    table.cmap = {}
                    table.uvsDict = {
                        0xFE00: [(cp, None) for cp in reversed(points)]
                        + [(0x3000, "a")]
                    }
                    data = table.compile(font)
                    # The selector record starts after the 10-byte header.
                    default_offset = struct.unpack_from(">L", data, 13)[0]
                    num_ranges = struct.unpack_from(">L", data, default_offset)[0]
                    expected_ranges = [
                        (start + offset, min(256, count - offset) - 1)
                        for start in ([0x1000, 0x2000] if gaps else [0x1000])
                        for offset in range(0, count, 256)
                    ]
                    self.assertEqual(num_ranges, len(expected_ranges))
                    actual_ranges = [
                        (
                            int.from_bytes(data[offset : offset + 3]),
                            data[offset + 3],
                        )
                        for offset in range(
                            default_offset + 4, default_offset + 4 + 4 * num_ranges, 4
                        )
                    ]
                    self.assertEqual(actual_ranges, expected_ranges)
                    reloaded = self.makeSubtable(14, 0, 5, 0)
                    reloaded.decompile(data, font)
                    self.assertEqual(
                        reloaded.uvsDict,
                        {0xFE00: [(cp, None) for cp in points] + [(0x3000, "a")]},
                    )
                    self.assertEqual(reloaded.compile(font), data)

    def test_sort_subtables_with_duplicate_keys(self):
        # https://github.com/fonttools/fonttools/issues/4035
        # Sorting subtables that share (platformID, platEncID, language) but
        # differ in format should not raise TypeError from comparing dicts.
        subtable4 = self.makeSubtable(4, 3, 1, 0)
        subtable4.cmap = {0x41: "A"}
        subtable12 = self.makeSubtable(12, 3, 1, 0)
        subtable12.cmap = {0x41: "A"}
        # This used to raise: TypeError: '<' not supported between
        # instances of 'dict' and 'dict'
        tables = sorted([subtable12, subtable4])
        # Both have the same key, so stable sort preserves original order
        self.assertEqual(len(tables), 2)

    def test_compile_raises_on_duplicate_subtable_keys(self):
        # https://github.com/fonttools/fonttools/issues/4035
        # The OpenType spec requires each (platformID, platEncID, language)
        # combination to be unique; compile should raise a clear error.
        cmap = table__c_m_a_p()
        cmap.tableVersion = 0
        subtable4 = self.makeSubtable(4, 3, 1, 0)
        subtable4.cmap = {0x41: "A"}
        subtable12 = self.makeSubtable(12, 3, 1, 0)
        subtable12.cmap = {0x41: "A"}
        cmap.tables = [subtable4, subtable12]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            cmap.compile(ttFont=None)

    def test_unsupported_format_is_preserved(self):
        # A subtable in a format we can't read is kept as raw data and written
        # back out unchanged.
        path = os.path.join(DATA_DIR, "aots", "cmap10_font1.otf")
        for lazy in (True, False):
            with self.subTest(lazy=lazy):
                font = ttLib.TTFont(path, lazy=lazy)
                data = font["cmap"].tables[0].data

                font.saveXML(io.StringIO(), tables=["cmap"])
                buf = io.BytesIO()
                font.save(buf)
                buf.seek(0)

                subtable = ttLib.TTFont(buf)["cmap"].tables[0]
                self.assertEqual(subtable.format, 10)
                self.assertEqual(subtable.data, data)

    def test_unsupported_format_missing_attribute(self):
        # Retaining self.data must not make __getattr__ recurse forever.
        path = os.path.join(DATA_DIR, "aots", "cmap10_font1.otf")
        subtable = ttLib.TTFont(path)["cmap"].tables[0]
        self.assertFalse(hasattr(subtable, "length"))
        with self.assertRaises(AttributeError):
            subtable.nosuchattribute


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
