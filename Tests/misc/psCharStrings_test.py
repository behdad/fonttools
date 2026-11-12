from fontTools.cffLib import PrivateDict
from fontTools.cffLib.specializer import stringToProgram
from fontTools.misc.testTools import getXML, parseXML
from fontTools.misc.psCharStrings import (
    CharStringDecompileError,
    T1CharString,
    T2CharString,
    encodeFloat,
    encodeFixed,
    read_fixed1616,
    read_realNumber,
)
from fontTools.pens.recordingPen import RecordingPen
import unittest
import pytest


def hexenc(s):
    return " ".join("%02x" % x for x in s)


class T2CharStringTest(unittest.TestCase):
    @classmethod
    def stringToT2CharString(cls, string):
        return T2CharString(program=stringToProgram(string), private=PrivateDict())

    def test_calcBounds_empty(self):
        cs = self.stringToT2CharString("endchar")
        bounds = cs.calcBounds(None)
        self.assertEqual(bounds, None)

    def test_calcBounds_line(self):
        cs = self.stringToT2CharString(
            "100 100 rmoveto 40 10 rlineto -20 50 rlineto endchar"
        )
        bounds = cs.calcBounds(None)
        self.assertEqual(bounds, (100, 100, 140, 160))

    def test_calcBounds_curve(self):
        cs = self.stringToT2CharString(
            "100 100 rmoveto -50 -150 200 0 -50 150 rrcurveto endchar"
        )
        bounds = cs.calcBounds(None)
        self.assertEqual(bounds, (91.90524980688875, -12.5, 208.09475019311125, 100))

    def test_charstring_bytecode_optimization(self):
        cs = self.stringToT2CharString(
            "100.0 100 rmoveto -50.0 -150 200.5 0.0 -50 150 rrcurveto endchar"
        )
        cs.isCFF2 = False
        cs.private._isCFF2 = False
        cs.compile()
        cs.decompile()
        self.assertEqual(
            cs.program,
            [
                100,
                100,
                "rmoveto",
                -50,
                -150,
                200.5,
                0,
                -50,
                150,
                "rrcurveto",
                "endchar",
            ],
        )

        cs2 = self.stringToT2CharString(
            "100.0 rmoveto -50.0 -150 200.5 0.0 -50 150 rrcurveto"
        )
        cs2.isCFF2 = True
        cs2.private._isCFF2 = True
        cs2.compile(isCFF2=True)
        cs2.decompile()
        self.assertEqual(
            cs2.program, [100, "rmoveto", -50, -150, 200.5, 0, -50, 150, "rrcurveto"]
        )

    def test_encodeFloat(self):
        testNums = [
            # value                expected result
            (-9.399999999999999, "1e e9 a4 ff"),  # -9.4
            (9.399999999999999999, "1e 9a 4f"),  # 9.4
            (456.8, "1e 45 6a 8f"),  # 456.8
            (0.0, "1e 0f"),  # 0
            (-0.0, "1e 0f"),  # 0
            (1.0, "1e 1f"),  # 1
            (-1.0, "1e e1 ff"),  # -1
            (98765.37e2, "1e 98 76 53 7f"),  # 9876537
            (1234567890.0, "1e 12 34 56 79 b2 ff"),  # 12345679E2
            (9.876537e-4, "1e 98 76 53 7c 10 ff"),  # 9876537E-10
            (9.876537e4, "1e 98 76 5a 37 ff"),  # 98765.37
            (1000.0, "1e 1b 3f"),  # 1E3
            (-1000.0, "1e e1 b3 ff"),  # -1E3
            (1e8, "1e 1b 8f"),  # 1E8
            (1e-5, "1e 1c 5f"),  # 1E-5
            (1.2e8, "1e 12 b7 ff"),  # 12E7
            (1.2345e-5, "1e 12 34 5c 9f"),  # 12345E-9
            (9.0987654e8, "1e 90 98 76 54 0f"),  # 909876540
            (0.1, "1e a1 ff"),  # .1
            (-0.1, "1e ea 1f"),  # -.1
            (0.01, "1e 1c 2f"),  # 1e-2
            (-0.01, "1e e1 c2 ff"),  # -1e-2
            (0.0123, "1e 12 3c 4f"),  # 123e-4
            (-0.0123, "1e e1 23 c4 ff"),  # -123e-4
        ]

        for sample in testNums:
            encoded_result = encodeFloat(sample[0])

            # check to see if we got the expected bytes
            self.assertEqual(hexenc(encoded_result), sample[1])

            # check to see if we get the same value by decoding the data
            decoded_result = read_realNumber(
                None,
                None,
                encoded_result,
                1,
            )
            self.assertEqual(decoded_result[0], float("%.8g" % sample[0]))
            # We limit to 8 digits of precision to match the implementation
            # of encodeFloat.

    def test_encode_decode_fixed(self):
        testNums = [
            # value                expected hex      expected float
            (-9.399999999999999, "ff ff f6 99 9a", -9.3999939),
            (-9.4, "ff ff f6 99 9a", -9.3999939),
            (9.399999999999999999, "ff 00 09 66 66", 9.3999939),
            (9.4, "ff 00 09 66 66", 9.3999939),
            (456.8, "ff 01 c8 cc cd", 456.8000031),
            (-456.8, "ff fe 37 33 33", -456.8000031),
        ]

        for value, expected_hex, expected_float in testNums:
            encoded_result = encodeFixed(value)

            # check to see if we got the expected bytes
            self.assertEqual(hexenc(encoded_result), expected_hex)

            # check to see if we get the same value by decoding the data
            decoded_result = read_fixed1616(
                None,
                None,
                encoded_result,
                1,
            )
            self.assertAlmostEqual(decoded_result[0], expected_float)

    def test_toXML(self):
        program = [
            "107 53.4004 166.199 hstem",
            "174.6 163.801 vstem",
            "338.4 142.8 rmoveto",
            "28 0 21.9 9 15.8 18 15.8 18 7.9 20.79959 0 23.6 rrcurveto",
            "endchar",
        ]
        cs = self.stringToT2CharString(" ".join(program))

        self.assertEqual(getXML(cs.toXML), program)

    def test_fromXML(self):
        cs = T2CharString()
        for name, attrs, content in parseXML(
            [
                '<CharString name="period">' "  338.4 142.8 rmoveto",
                "  28 0 21.9 9 15.8 18 15.8 18 7.9 20.79959 0 23.6 rrcurveto",
                "  endchar" "</CharString>",
            ]
        ):
            cs.fromXML(name, attrs, content)

        expected_program = [
            338.3999939,
            142.8000031,
            "rmoveto",
            28,
            0,
            21.8999939,
            9,
            15.8000031,
            18,
            15.8000031,
            18,
            7.8999939,
            20.7995911,
            0,
            23.6000061,
            "rrcurveto",
            "endchar",
        ]

        self.assertEqual(len(cs.program), len(expected_program))
        for arg, expected_arg in zip(cs.program, expected_program):
            if isinstance(arg, str):
                self.assertIsInstance(expected_arg, str)
                self.assertEqual(arg, expected_arg)
            else:
                self.assertNotIsInstance(expected_arg, str)
                self.assertAlmostEqual(arg, expected_arg)

    def test_pen_closePath(self):
        # Test CFF2/T2 charstring: it does NOT end in "endchar"
        # https://github.com/fonttools/fonttools/issues/2455
        cs = self.stringToT2CharString(
            "100 100 rmoveto -50 -150 200 0 -50 150 rrcurveto"
        )
        pen = RecordingPen()
        cs.draw(pen)
        self.assertEqual(pen.value[-1], ("closePath", ()))


@pytest.mark.parametrize("num_regions", [0, 1, 2])
@pytest.mark.parametrize("num_blends", [1, 2])
@pytest.mark.parametrize("use_blender", [False, True])
@pytest.mark.parametrize("bytecode", [False, True])
def test_cff2_blend_stack(num_regions, num_blends, use_blender, bytecode):
    from fontTools.cffLib import VarStoreData
    from fontTools.varLib.builder import buildVarData, buildVarRegionList, buildVarStore

    store = buildVarStore(
        buildVarRegionList([{"TEST": (0, 1, 1)}] * num_regions, ["TEST"]),
        [buildVarData(list(range(num_regions)), [], optimize=False)],
    )
    private = PrivateDict(vstore=VarStoreData(otVarStore=store))
    private._isCFF2 = True
    private.nominalWidthX = private.defaultWidthX = None
    defaults = [100, 200] if num_blends == 2 else [200]
    deltas = [
        10 * (i + 1) * (j + 1) for j in range(num_blends) for i in range(num_regions)
    ]
    program = (
        ([] if num_blends == 2 else [100])
        + defaults
        + deltas
        + [num_blends, "blend", "rmoveto", 100, 0, "rlineto", -100, 100, "rlineto"]
    )
    charstring = T2CharString(program=program, private=private)
    if bytecode:
        charstring.compile(isCFF2=True)
        charstring = T2CharString(bytecode=charstring.bytecode, private=private)
    pen = RecordingPen()
    blender = (lambda index, deltas: sum(deltas)) if use_blender else None
    charstring.draw(pen, blender=blender)
    delta = 10 * sum(range(1, num_regions + 1)) if use_blender else 0
    x = 100 + (delta if num_blends == 2 else 0)
    y = 200 + delta * num_blends
    assert pen.value == [
        ("moveTo", ((x, y),)),
        ("lineTo", ((x + 100, y),)),
        ("lineTo", ((x, y + 100),)),
        ("closePath", ()),
    ]


@pytest.mark.parametrize("use_blender", [False, True])
@pytest.mark.parametrize("bytecode", [False, True])
def test_cff2_vsindex_zero_regions(use_blender, bytecode):
    from fontTools.cffLib import VarStoreData
    from fontTools.varLib.builder import buildVarData, buildVarRegionList, buildVarStore

    store = buildVarStore(
        buildVarRegionList([{"TEST": (0, 1, 1)}], ["TEST"]),
        [buildVarData([0], [], optimize=False), buildVarData([], [])],
    )
    private = PrivateDict(vstore=VarStoreData(otVarStore=store))
    private._isCFF2 = True
    private.nominalWidthX = private.defaultWidthX = None
    program = [1, "vsindex", 100, 200, 1, "blend", "rmoveto", 100, 0, "rlineto"]
    charstring = T2CharString(program=program, private=private)
    if bytecode:
        charstring.compile(isCFF2=True)
        charstring = T2CharString(bytecode=charstring.bytecode, private=private)
    pen = RecordingPen()
    charstring.draw(
        pen, blender=(lambda index, deltas: sum(deltas)) if use_blender else None
    )
    assert pen.value == [
        ("moveTo", ((100, 200),)),
        ("lineTo", ((200, 200),)),
        ("closePath", ()),
    ]


@pytest.mark.parametrize("private_vsindex", [None, 0, 1])
@pytest.mark.parametrize("charstring_vsindex", [None, 0, 1])
@pytest.mark.parametrize("location", [0, 0.5, 1])
@pytest.mark.parametrize("bytecode", [False, True])
def test_cff2_inherited_vsindex(
    private_vsindex, charstring_vsindex, location, bytecode
):
    from fontTools.cffLib import VarStoreData
    from fontTools.ttLib.tables._f_v_a_r import Axis
    from fontTools.varLib.builder import buildVarData, buildVarRegionList, buildVarStore
    from fontTools.varLib.varStore import VarStoreInstancer

    store = buildVarStore(
        buildVarRegionList([{"TEST": (-1, -1, 0)}, {"TEST": (0, 1, 1)}], ["TEST"]),
        [buildVarData([0], [], optimize=False), buildVarData([1], [], optimize=False)],
    )
    private = PrivateDict(vstore=VarStoreData(otVarStore=store))
    private._isCFF2 = True
    private.nominalWidthX = private.defaultWidthX = None
    if private_vsindex is not None:
        private.vsindex = private_vsindex
    program = [100, 100, "rmoveto", 100, 80, 1, "blend", "hlineto"]
    if charstring_vsindex is not None:
        program = [charstring_vsindex, "vsindex"] + program
    charstring = T2CharString(program=program, private=private)
    if bytecode:
        charstring.compile(isCFF2=True)
        charstring = T2CharString(bytecode=charstring.bytecode, private=private)
    axis = Axis()
    axis.axisTag = "TEST"
    instancer = VarStoreInstancer(store, [axis], {"TEST": location})
    pen = RecordingPen()
    charstring.draw(pen, blender=instancer.interpolateFromDeltas)
    vsindex = private_vsindex or 0
    if charstring_vsindex is not None:
        vsindex = charstring_vsindex
    delta = 80 * location if vsindex == 1 else 0
    assert pen.value == [
        ("moveTo", ((100, 100),)),
        ("lineTo", ((200 + delta, 100),)),
        ("closePath", ()),
    ]


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())


@pytest.mark.parametrize("operator", [b"", b"("])
def test_t2_unknown_operator(operator):
    # An undefined operator used to end the charstring silently, so that the
    # rest of the glyph was lost when the charstring was compiled again.
    head = T2CharString(program=stringToProgram("0 0 rmoveto 100 0 rlineto"))
    tail = T2CharString(program=stringToProgram("0 100 rlineto endchar"))
    head.compile()
    tail.compile()
    bytecode = head.bytecode + operator + tail.bytecode

    cs = T2CharString(bytecode=bytecode, private=PrivateDict())
    with pytest.raises(CharStringDecompileError, match="unknown operator"):
        cs.decompile()

    cs = T2CharString(bytecode=bytecode, private=PrivateDict())
    with pytest.raises(CharStringDecompileError, match="unknown operator"):
        cs.draw(RecordingPen())


def test_t1_unknown_operator():
    head = T1CharString(program=[0, 500, "hsbw", 0, 0, "rmoveto"])
    tail = T1CharString(program=[0, 100, "rlineto", "closepath", "endchar"])
    head.compile()
    tail.compile()
    cs = T1CharString(bytecode=head.bytecode + b"" + tail.bytecode)
    with pytest.raises(CharStringDecompileError, match="unknown operator: 2"):
        cs.decompile()
