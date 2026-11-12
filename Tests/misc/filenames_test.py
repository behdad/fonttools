import unittest
from fontTools.misc.filenames import userNameToFileName, handleClash1, handleClash2


class UserNameToFilenameTest(unittest.TestCase):
    def test_names(self):
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

    def test_nul_character(self):
        self.assertEqual(userNameToFileName("a\0b", suffix=".ttx"), "a_b.ttx")

    def test_reserved_device_names(self):
        for prefix in ("com", "lpt"):
            for number in range(1, 10):
                name = f"{prefix}{number}"
                with self.subTest(name=name):
                    self.assertEqual(userNameToFileName(name), "_" + name)
                    self.assertEqual(
                        userNameToFileName(name + ".alt", suffix=".ttx"),
                        "_" + name + ".alt.ttx",
                    )

    def test_reserved_device_name_collision(self):
        self.assertEqual(
            userNameToFileName("com5", existing=["_com5.ttx"], suffix=".ttx"),
            "_com5000000000000001.ttx",
        )

    def test_prefix_suffix(self):
        prefix = "TEST_PREFIX"
        suffix = "TEST_SUFFIX"
        name = "NAME"
        name_file = "N_A_M_E_"
        self.assertEqual(
            userNameToFileName(name, prefix=prefix, suffix=suffix),
            prefix + name_file + suffix,
        )

    def test_collide(self):
        prefix = "TEST_PREFIX"
        suffix = "TEST_SUFFIX"
        name = "NAME"
        name_file = "N_A_M_E_"
        collision_avoidance1 = "000000000000001"
        collision_avoidance2 = "000000000000002"
        exist = set()
        generated = userNameToFileName(name, exist, prefix=prefix, suffix=suffix)
        exist.add(generated.lower())
        self.assertEqual(generated, prefix + name_file + suffix)
        generated = userNameToFileName(name, exist, prefix=prefix, suffix=suffix)
        exist.add(generated.lower())
        self.assertEqual(generated, prefix + name_file + collision_avoidance1 + suffix)
        generated = userNameToFileName(name, exist, prefix=prefix, suffix=suffix)
        self.assertEqual(generated, prefix + name_file + collision_avoidance2 + suffix)

    def test_ValueError(self):
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


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
