import unittest
from fontTools.ufoLib.filenames import userNameToFileName, handleClash1, handleClash2


class TestFilenames(unittest.TestCase):
    def test_userNameToFileName_existing_iterator(self):
        first = "a" + "1".zfill(15) + ".glif"
        second = "a" + "2".zfill(15) + ".glif"
        existing = [second, first, "a.glif"]
        expected = userNameToFileName("a", existing=existing, suffix=".glif")
        actual = userNameToFileName("a", existing=iter(existing), suffix=".glif")
        self.assertEqual(actual, expected)
        self.assertNotIn(actual, existing)

    def test_handleClash1_existing_iterator(self):
        existing = ["a" + "2".zfill(15), "a" + "1".zfill(15)]
        expected = handleClash1("a", existing=existing)
        actual = handleClash1("a", existing=iter(existing))
        self.assertEqual(actual, expected)
        self.assertNotIn(actual, existing)

    def test_handleClash2_existing_iterator(self):
        existing = ["2", "1"]
        expected = handleClash2(existing=existing)
        actual = handleClash2(existing=iter(existing))
        self.assertEqual(actual, expected)
        self.assertNotIn(actual, existing)

    def test_userNameToFileName(self):
        self.assertEqual(userNameToFileName("a"), "a")
        self.assertEqual(userNameToFileName("A"), "A_")
        self.assertEqual(userNameToFileName("AE"), "A_E_")
        self.assertEqual(userNameToFileName("Ae"), "A_e")
        self.assertEqual(userNameToFileName("ae"), "ae")
        self.assertEqual(userNameToFileName("aE"), "aE_")
        self.assertEqual(userNameToFileName("a.alt"), "a.alt")
        self.assertEqual(userNameToFileName("A.alt"), "A_.alt")
        self.assertEqual(userNameToFileName("A.Alt"), "A_.A_lt")
        self.assertEqual(userNameToFileName("A.aLt"), "A_.aL_t")
        self.assertEqual(userNameToFileName("A.alT"), "A_.alT_")
        self.assertEqual(userNameToFileName("T_H"), "T__H_")
        self.assertEqual(userNameToFileName("T_h"), "T__h")
        self.assertEqual(userNameToFileName("t_h"), "t_h")
        self.assertEqual(userNameToFileName("F_F_I"), "F__F__I_")
        self.assertEqual(userNameToFileName("f_f_i"), "f_f_i")
        self.assertEqual(userNameToFileName("Aacute_V.swash"), "A_acute_V_.swash")
        self.assertEqual(userNameToFileName(".notdef"), "_notdef")
        self.assertEqual(userNameToFileName("con"), "_con")
        self.assertEqual(userNameToFileName("CON"), "C_O_N_")
        self.assertEqual(userNameToFileName("con.alt"), "_con.alt")
        self.assertEqual(userNameToFileName("alt.con"), "alt._con")

        self.assertEqual(
            # Test output for ASCII range (up until 0x7F), except for illegal
            # characters.
            userNameToFileName("".join([chr(i) for i in range(0, 0x80)])),
            "________________________________"
            " !_#$%&'____,-._0123456789_;_=__"
            "@A_B_C_D_E_F_G_H_I_J_K_L_M_N_O_P_Q_R_S_T_U_V_W_X_Y_Z_"
            "___^_`abcdefghijklmnopqrstuvwxyz{_}~_",
        )

    def test_userNameToFileName_ValueError(self):
        with self.assertRaises(ValueError):
            userNameToFileName(b"a")
        with self.assertRaises(ValueError):
            userNameToFileName({"a"})
        with self.assertRaises(ValueError):
            userNameToFileName(("a",))
        with self.assertRaises(ValueError):
            userNameToFileName(["a"])
        with self.assertRaises(ValueError):
            userNameToFileName(["a"])
        with self.assertRaises(ValueError):
            userNameToFileName(b"\xd8\x00")

    def test_handleClash1(self):
        prefix = ("0" * 5) + "."
        suffix = "." + ("0" * 10)
        existing = ["a" * 5]

        e = list(existing)
        self.assertEqual(
            handleClash1(userName="A" * 5, existing=e, prefix=prefix, suffix=suffix),
            "00000.AAAAA000000000000001.0000000000",
        )

        e = list(existing)
        e.append(prefix + "aaaaa" + "1".zfill(15) + suffix)
        self.assertEqual(
            handleClash1(userName="A" * 5, existing=e, prefix=prefix, suffix=suffix),
            "00000.AAAAA000000000000002.0000000000",
        )

        e = list(existing)
        e.append(prefix + "AAAAA" + "2".zfill(15) + suffix)
        self.assertEqual(
            handleClash1(userName="A" * 5, existing=e, prefix=prefix, suffix=suffix),
            "00000.AAAAA000000000000001.0000000000",
        )

    def test_handleClash2(self):
        prefix = ("0" * 5) + "."
        suffix = "." + ("0" * 10)
        existing = [prefix + str(i) + suffix for i in range(100)]

        e = list(existing)
        self.assertEqual(
            handleClash2(existing=e, prefix=prefix, suffix=suffix),
            "00000.100.0000000000",
        )

        e = list(existing)
        e.remove(prefix + "1" + suffix)
        self.assertEqual(
            handleClash2(existing=e, prefix=prefix, suffix=suffix), "00000.1.0000000000"
        )

        e = list(existing)
        e.remove(prefix + "2" + suffix)
        self.assertEqual(
            handleClash2(existing=e, prefix=prefix, suffix=suffix), "00000.2.0000000000"
        )
