from fontTools.misc.textTools import safeEval
from fontTools.ttLib import TTLibError
from . import DefaultTable
import struct

GASP_SYMMETRIC_GRIDFIT = 0x0004
GASP_SYMMETRIC_SMOOTHING = 0x0008
GASP_DOGRAY = 0x0002
GASP_GRIDFIT = 0x0001


class table__g_a_s_p(DefaultTable.DefaultTable):
    """Grid-fitting and Scan-conversion Procedure table

    The ``gasp`` table defines the preferred rasterization settings for
    the font when rendered on monochrome and greyscale output devices.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/gasp
    """

    def decompile(self, data, ttFont):
        if len(data) < 4:
            raise TTLibError("Not enough 'gasp' table data")
        self.version, numRanges = struct.unpack(">HH", data[:4])
        if not 0 <= self.version <= 1:
            raise TTLibError("unknown 'gasp' format: %d" % self.version)
        data = data[4:]
        self.gaspRange = {}
        for i in range(numRanges):
            if len(data) < 4:
                raise TTLibError("Not enough 'gasp' table data")
            rangeMaxPPEM, rangeGaspBehavior = struct.unpack(">HH", data[:4])
            self.gaspRange[int(rangeMaxPPEM)] = int(rangeGaspBehavior)
            data = data[4:]
        if data:
            raise TTLibError("too much 'gasp' table data")

    def compile(self, ttFont):
        version = 0  # ignore self.version
        numRanges = len(self.gaspRange)
        data = b""
        items = sorted(self.gaspRange.items())
        for rangeMaxPPEM, rangeGaspBehavior in items:
            data = data + struct.pack(">HH", rangeMaxPPEM, rangeGaspBehavior)
            if rangeGaspBehavior & ~(GASP_GRIDFIT | GASP_DOGRAY):
                version = 1
        data = struct.pack(">HH", version, numRanges) + data
        return data

    def toXML(self, writer, ttFont):
        items = sorted(self.gaspRange.items())
        for rangeMaxPPEM, rangeGaspBehavior in items:
            writer.simpletag(
                "gaspRange",
                [
                    ("rangeMaxPPEM", rangeMaxPPEM),
                    ("rangeGaspBehavior", rangeGaspBehavior),
                ],
            )
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name != "gaspRange":
            return
        if not hasattr(self, "gaspRange"):
            self.gaspRange = {}
        self.gaspRange[safeEval(attrs["rangeMaxPPEM"])] = safeEval(
            attrs["rangeGaspBehavior"]
        )
