from fontTools.misc.fixedTools import (
    fixedToFloat,
    floatToFixed,
    floatToFixedToStr,
    fixedToStr,
    strToFixed,
    strToFixedToFloat,
)
import unittest


class FixedToolsTest(unittest.TestCase):
    def test_roundtrip(self):
        for bits in range(0, 15):
            for value in range(-(2 ** (bits + 1)), 2 ** (bits + 1)):
                self.assertEqual(value, floatToFixed(fixedToFloat(value, bits), bits))

    def test_fixedToFloat_precision14(self):
        self.assertAlmostEqual(0.7999878, fixedToFloat(13107, 14))
        self.assertEqual(0.0, fixedToFloat(0, 14))
        self.assertEqual(1.0, fixedToFloat(16384, 14))
        self.assertEqual(-1.0, fixedToFloat(-16384, 14))
        self.assertAlmostEqual(0.999939, fixedToFloat(16383, 14))
        self.assertAlmostEqual(-0.999939, fixedToFloat(-16383, 14))

    def test_fixedToFloat_precision6(self):
        self.assertAlmostEqual(-9.984375, fixedToFloat(-639, 6))
        self.assertAlmostEqual(-10.0, fixedToFloat(-640, 6))
        self.assertAlmostEqual(9.984375, fixedToFloat(639, 6))
        self.assertAlmostEqual(10.0, fixedToFloat(640, 6))

    def test_fixedToStr_precision14(self):
        self.assertEqual("0.8", fixedToStr(13107, 14))
        self.assertEqual("0.0", fixedToStr(0, 14))
        self.assertEqual("1.0", fixedToStr(16384, 14))
        self.assertEqual("-1.0", fixedToStr(-16384, 14))
        self.assertEqual("0.99994", fixedToStr(16383, 14))
        self.assertEqual("-0.99994", fixedToStr(-16383, 14))

    def test_fixedToStr_precision6(self):
        self.assertAlmostEqual("-9.98", fixedToStr(-639, 6))
        self.assertAlmostEqual("-10.0", fixedToStr(-640, 6))
        self.assertAlmostEqual("9.98", fixedToStr(639, 6))
        self.assertAlmostEqual("10.0", fixedToStr(640, 6))

    def test_floatToFixed_precision14(self):
        self.assertEqual(13107, floatToFixed(0.8, 14))
        self.assertEqual(16384, floatToFixed(1.0, 14))
        self.assertEqual(16384, floatToFixed(1, 14))
        self.assertEqual(-16384, floatToFixed(-1.0, 14))
        self.assertEqual(-16384, floatToFixed(-1, 14))
        self.assertEqual(0, floatToFixed(0, 14))

    def test_strToFixed_precision14(self):
        self.assertEqual(13107, strToFixed("0.8", 14))
        self.assertEqual(16384, strToFixed("1.0", 14))
        self.assertEqual(16384, strToFixed("1", 14))
        self.assertEqual(-16384, strToFixed("-1.0", 14))
        self.assertEqual(-16384, strToFixed("-1", 14))
        self.assertEqual(0, strToFixed("0", 14))

    def test_strToFixedToFloat_precision14(self):
        self.assertAlmostEqual(0.7999878, strToFixedToFloat("0.8", 14))
        self.assertEqual(0.0, strToFixedToFloat("0", 14))
        self.assertEqual(1.0, strToFixedToFloat("1.0", 14))
        self.assertEqual(-1.0, strToFixedToFloat("-1.0", 14))
        self.assertAlmostEqual(0.999939, strToFixedToFloat("0.99994", 14))
        self.assertAlmostEqual(-0.999939, strToFixedToFloat("-0.99994", 14))

    def test_floatToFixedToStr_precision14(self):
        self.assertEqual("0.8", floatToFixedToStr(0.7999878, 14))
        self.assertEqual("1.0", floatToFixedToStr(1.0, 14))
        self.assertEqual("1.0", floatToFixedToStr(1, 14))
        self.assertEqual("-1.0", floatToFixedToStr(-1.0, 14))
        self.assertEqual("-1.0", floatToFixedToStr(-1, 14))
        self.assertEqual("0.0", floatToFixedToStr(0, 14))

    def test_floatToFixedToStr_rounds_to_zero(self):
        # non-zero values whose fixed-point representation is zero
        self.assertEqual("0.0", floatToFixedToStr(1e-5, 14))
        self.assertEqual("0.0", floatToFixedToStr(-1e-5, 14))
        self.assertEqual("0.0", floatToFixedToStr(1e-6, 16))
        self.assertEqual("0.0", floatToFixedToStr(0.4 / (1 << 14), 14))

    def test_fixedToFloat_return_float(self):
        value = fixedToFloat(16384, 14)
        self.assertIsInstance(value, float)


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
