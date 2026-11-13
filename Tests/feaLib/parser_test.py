# -*- coding: utf-8 -*-
from fontTools.misc.loggingTools import CapturingLogHandler
from fontTools.feaLib.error import FeatureLibError
from fontTools.feaLib.parser import Parser, SymbolTable
from io import StringIO
import warnings
import fontTools.feaLib.ast as ast
import ast as pyast
import inspect
import os
import textwrap
import unittest


def glyphstr(glyphs):
    def f(x):
        if len(x) == 1:
            return list(x)[0]
        else:
            return "[%s]" % " ".join(sorted(list(x)))

    return " ".join(f(g.glyphSet()) for g in glyphs)


def mapping(s):
    b = []
    for a in s.glyphs:
        b.extend(a.glyphSet())
    c = []
    for a in s.replacements:
        c.extend(a.glyphSet())
    if len(c) == 1:
        c = c * len(b)
    return dict(zip(b, c))


GLYPHNAMES = ("""
    .notdef space A B C D E F G H I J K L M N O P Q R S T U V W X Y Z
    A.sc B.sc C.sc D.sc E.sc F.sc G.sc H.sc I.sc J.sc K.sc L.sc M.sc
    N.sc O.sc P.sc Q.sc R.sc S.sc T.sc U.sc V.sc W.sc X.sc Y.sc Z.sc
    A.swash B.swash X.swash Y.swash Z.swash
    a b c d e f g h i j k l m n o p q r s t u v w x y z
    a.sc b.sc c.sc d.sc e.sc f.sc g.sc h.sc i.sc j.sc k.sc l.sc m.sc
    n.sc o.sc p.sc q.sc r.sc s.sc t.sc u.sc v.sc w.sc x.sc y.sc z.sc
    a.swash b.swash x.swash y.swash z.swash
    foobar foo.09 foo.1234 foo.9876
    one two five six acute grave dieresis umlaut cedilla ogonek macron
    a_f_f_i o_f_f_i f_i f_l f_f_i one.fitted one.oldstyle a.1 a.2 a.3 c_t
    PRE SUF FIX BACK TRACK LOOK AHEAD ampersand ampersand.1 ampersand.2
    cid00001 cid00002 cid00003 cid00004 cid00005 cid00006 cid00007
    cid12345 cid78987 cid00999 cid01000 cid01001 cid00998 cid00995
    cid00111 cid00222
    comma endash emdash figuredash damma hamza
    c_d d.alt n.end s.end f_f
""").split() + ["foo.%d" % i for i in range(1, 200)] + ["G" * 600]


class ParserTest(unittest.TestCase):
    def __init__(self, methodName):
        unittest.TestCase.__init__(self, methodName)
        # Python 3 renamed assertRaisesRegexp to assertRaisesRegex,
        # and fires deprecation warnings if a program uses the old name.
        if not hasattr(self, "assertRaisesRegex"):
            self.assertRaisesRegex = self.assertRaisesRegexp

    def test_glyphMap_deprecated(self):
        glyphMap = {"a": 0, "b": 1, "c": 2}
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            parser = Parser(StringIO(), glyphMap=glyphMap)

            self.assertEqual(len(w), 1)
            self.assertEqual(w[-1].category, UserWarning)
            self.assertIn("deprecated", str(w[-1].message))
            self.assertEqual(parser.glyphNames_, {"a", "b", "c"})

            self.assertRaisesRegex(
                TypeError,
                "mutually exclusive",
                Parser,
                StringIO(),
                ("a",),
                glyphMap={"a": 0},
            )

            self.assertRaisesRegex(
                TypeError, "unsupported keyword argument", Parser, StringIO(), foo="bar"
            )

    def test_comments(self):
        doc = self.parse(""" # Initial
                feature test {
                    sub A by B; # simple
                } test;""")
        c1 = doc.statements[0]
        c2 = doc.statements[1].statements[1]
        self.assertEqual(type(c1), ast.Comment)
        self.assertEqual(c1.text, "# Initial")
        self.assertEqual(str(c1), "# Initial")
        self.assertEqual(type(c2), ast.Comment)
        self.assertEqual(c2.text, "# simple")
        self.assertEqual(doc.statements[1].name, "test")

    def test_only_comments(self):
        doc = self.parse("""\
            # Initial
        """)
        c1 = doc.statements[0]
        self.assertEqual(type(c1), ast.Comment)
        self.assertEqual(c1.text, "# Initial")
        self.assertEqual(str(c1), "# Initial")

    def test_anchor_format_a(self):
        doc = self.parse(
            "feature test {"
            "    pos cursive A <anchor 120 -20> <anchor NULL>;"
            "} test;"
        )
        anchor = doc.statements[0].statements[0].entryAnchor
        self.assertEqual(type(anchor), ast.Anchor)
        self.assertEqual(anchor.x, 120)
        self.assertEqual(anchor.y, -20)
        self.assertIsNone(anchor.contourpoint)
        self.assertIsNone(anchor.xDeviceTable)
        self.assertIsNone(anchor.yDeviceTable)

    def test_anchor_format_b(self):
        doc = self.parse(
            "feature test {"
            "    pos cursive A <anchor 120 -20 contourpoint 5> <anchor NULL>;"
            "} test;"
        )
        anchor = doc.statements[0].statements[0].entryAnchor
        self.assertEqual(type(anchor), ast.Anchor)
        self.assertEqual(anchor.x, 120)
        self.assertEqual(anchor.y, -20)
        self.assertEqual(anchor.contourpoint, 5)
        self.assertIsNone(anchor.xDeviceTable)
        self.assertIsNone(anchor.yDeviceTable)

    def test_anchor_format_c(self):
        doc = self.parse(
            "feature test {"
            "    pos cursive A "
            "        <anchor 120 -20 <device 11 111, 12 112> <device NULL>>"
            "        <anchor NULL>;"
            "} test;"
        )
        anchor = doc.statements[0].statements[0].entryAnchor
        self.assertEqual(type(anchor), ast.Anchor)
        self.assertEqual(anchor.x, 120)
        self.assertEqual(anchor.y, -20)
        self.assertIsNone(anchor.contourpoint)
        self.assertEqual(anchor.xDeviceTable, ((11, 111), (12, 112)))
        self.assertIsNone(anchor.yDeviceTable)

    def test_anchor_format_d(self):
        doc = self.parse(
            "feature test {"
            "    pos cursive A <anchor 120 -20> <anchor NULL>;"
            "} test;"
        )
        anchor = doc.statements[0].statements[0].exitAnchor
        self.assertIsNone(anchor)

    def test_anchor_format_e(self):
        doc = self.parse(
            "feature test {"
            "    anchorDef 120 -20 contourpoint 7 Foo;"
            "    pos cursive A <anchor Foo> <anchor NULL>;"
            "} test;"
        )
        anchor = doc.statements[0].statements[1].entryAnchor
        self.assertEqual(type(anchor), ast.Anchor)
        self.assertEqual(anchor.x, 120)
        self.assertEqual(anchor.y, -20)
        self.assertEqual(anchor.contourpoint, 7)
        self.assertIsNone(anchor.xDeviceTable)
        self.assertIsNone(anchor.yDeviceTable)

    def test_anchor_format_e_undefined(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Unknown anchor "UnknownName"',
            self.parse,
            "feature test {"
            "    position cursive A <anchor UnknownName> <anchor NULL>;"
            "} test;",
        )

    def test_anchor_variable_scalar(self):
        doc = self.parse(
            "feature test {"
            "    pos cursive A <anchor (wght=200:-100 wght=900:-150 wdth=150.5,wght=900:-120) -20> <anchor NULL>;"
            "} test;"
        )
        anchor = doc.statements[0].statements[0].entryAnchor
        self.assertEqual(
            anchor.asFea(),
            "<anchor (wght=200:-100 wght=900:-150 wdth=150.5,wght=900:-120) -20>",
        )

    def test_anchordef(self):
        [foo] = self.parse("anchorDef 123 456 foo;").statements
        self.assertEqual(type(foo), ast.AnchorDefinition)
        self.assertEqual(foo.name, "foo")
        self.assertEqual(foo.x, 123)
        self.assertEqual(foo.y, 456)
        self.assertEqual(foo.contourpoint, None)

    def test_anchordef_contourpoint(self):
        [foo] = self.parse("anchorDef 123 456 contourpoint 5 foo;").statements
        self.assertEqual(type(foo), ast.AnchorDefinition)
        self.assertEqual(foo.name, "foo")
        self.assertEqual(foo.x, 123)
        self.assertEqual(foo.y, 456)
        self.assertEqual(foo.contourpoint, 5)

    def test_anon(self):
        anon = self.parse("anon TEST { # a\nfoo\n } TEST; # qux").statements[0]
        self.assertIsInstance(anon, ast.AnonymousBlock)
        self.assertEqual(anon.tag, "TEST")
        self.assertEqual(anon.content, "foo\n ")

    def test_anonymous(self):
        anon = self.parse("anonymous TEST {\nbar\n} TEST;").statements[0]
        self.assertIsInstance(anon, ast.AnonymousBlock)
        self.assertEqual(anon.tag, "TEST")
        # feature file spec requires passing the final end-of-line
        self.assertEqual(anon.content, "bar\n")

    def test_anon_missingBrace(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Expected '} TEST;' to terminate anonymous block",
            self.parse,
            "anon TEST { \n no end in sight",
        )

    def test_anon_regexMetacharacterTag(self):
        # the closing tag is matched literally: regex metacharacters in the tag
        # (all of ``. + * ^ ~ !`` are valid feature-file name characters) must
        # not move where the block ends, so the inner "} X;" does not terminate it
        anon = self.parse("anon .+.+ {\n} X;\n} .+.+;\n").statements[0]
        self.assertIsInstance(anon, ast.AnonymousBlock)
        self.assertEqual(anon.tag, ".+.+")
        self.assertEqual(anon.content, "} X;\n")

    def test_anon_invalidRegexTag(self):
        # a tag that is not a valid regular expression must raise a
        # FeatureLibError rather than leaking a re.error out of the parser
        self.assertRaisesRegex(
            FeatureLibError,
            r"Expected '} \*;' to terminate anonymous block",
            self.parse,
            "anon * {\n no end in sight",
        )

    def test_attach(self):
        doc = self.parse("table GDEF {Attach [a e] 2;} GDEF;")
        s = doc.statements[0].statements[0]
        self.assertIsInstance(s, ast.AttachStatement)
        self.assertEqual(glyphstr([s.glyphs]), "[a e]")
        self.assertEqual(s.contourPoints, {2})

    def test_feature_block(self):
        [liga] = self.parse("feature liga {} liga;").statements
        self.assertEqual(liga.name, "liga")
        self.assertFalse(liga.use_extension)

    def test_feature_block_useExtension(self):
        [liga] = self.parse("feature liga useExtension {} liga;").statements
        self.assertEqual(liga.name, "liga")
        self.assertTrue(liga.use_extension)
        self.assertEqual(liga.asFea(), "feature liga useExtension {\n    \n} liga;\n")

    def test_feature_comment(self):
        [liga] = self.parse("feature liga { # Comment\n } liga;").statements
        [comment] = liga.statements
        self.assertIsInstance(comment, ast.Comment)
        self.assertEqual(comment.text, "# Comment")

    def test_feature_reference(self):
        doc = self.parse("feature aalt { feature salt; } aalt;")
        ref = doc.statements[0].statements[0]
        self.assertIsInstance(ref, ast.FeatureReferenceStatement)
        self.assertEqual(ref.featureName, "salt")

    def test_FeatureNames_bad(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Expected "name"',
            self.parse,
            "feature ss01 { featureNames { feature test; } ss01;",
        )

    def test_FeatureNames_comment(self):
        [feature] = self.parse(
            "feature ss01 { featureNames { # Comment\n }; } ss01;"
        ).statements
        [featureNames] = feature.statements
        self.assertIsInstance(featureNames, ast.NestedBlock)
        [comment] = featureNames.statements
        self.assertIsInstance(comment, ast.Comment)
        self.assertEqual(comment.text, "# Comment")

    def test_FeatureNames_emptyStatements(self):
        [feature] = self.parse(
            "feature ss01 { featureNames { ;;; }; } ss01;"
        ).statements
        [featureNames] = feature.statements
        self.assertIsInstance(featureNames, ast.NestedBlock)
        self.assertEqual(featureNames.statements, [])

    def test_FontRevision(self):
        doc = self.parse("table head {FontRevision 2.5;} head;")
        s = doc.statements[0].statements[0]
        self.assertIsInstance(s, ast.FontRevisionStatement)
        self.assertEqual(s.revision, 2.5)

    def test_FontRevision_negative(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Font revision numbers must be positive",
            self.parse,
            "table head {FontRevision -17.2;} head;",
        )

    def test_strict_glyph_name_check(self):
        self.parse("@bad = [a b ccc];", glyphNames=("a", "b", "ccc"))

        with self.assertRaisesRegex(
            FeatureLibError, "(?s)missing from the glyph set:.*ccc"
        ):
            self.parse("@bad = [a b ccc];", glyphNames=("a", "b"))

    def test_glyphclass(self):
        [gc] = self.parse("@dash = [endash emdash figuredash];").statements
        self.assertEqual(gc.name, "dash")
        self.assertEqual(gc.glyphSet(), ("endash", "emdash", "figuredash"))

    def test_glyphclass_glyphNameTooLong(self):
        gname = "G" * 600
        [gc] = self.parse(f"@GlyphClass = [{gname}];").statements
        self.assertEqual(gc.name, "GlyphClass")
        self.assertEqual(gc.glyphSet(), (gname,))

    def test_glyphclass_bad(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Expected glyph name, glyph range, or glyph class reference",
            self.parse,
            "@bad = [a 123];",
        )

    def test_glyphclass_duplicate(self):
        # makeotf accepts this, so we should too
        ab, xy = self.parse("@dup = [a b]; @dup = [x y];").statements
        self.assertEqual(glyphstr([ab]), "[a b]")
        self.assertEqual(glyphstr([xy]), "[x y]")

    def test_glyphclass_empty(self):
        [gc] = self.parse("@empty_set = [];").statements
        self.assertEqual(gc.name, "empty_set")
        self.assertEqual(gc.glyphSet(), tuple())

    def test_glyphclass_equality(self):
        [foo, bar] = self.parse("@foo = [a b]; @bar = @foo;").statements
        self.assertEqual(foo.glyphSet(), ("a", "b"))
        self.assertEqual(bar.glyphSet(), ("a", "b"))

    def test_glyphclass_from_markClass(self):
        doc = self.parse(
            "markClass [acute grave] <anchor 500 800> @TOP_MARKS;"
            "markClass cedilla <anchor 500 -100> @BOTTOM_MARKS;"
            "@MARKS = [@TOP_MARKS @BOTTOM_MARKS ogonek];"
            "@ALL = @MARKS;"
        )
        self.assertEqual(
            doc.statements[-1].glyphSet(), ("acute", "grave", "cedilla", "ogonek")
        )

    def test_glyphclass_range_cid(self):
        [gc] = self.parse(r"@GlyphClass = [\999-\1001];").statements
        self.assertEqual(gc.name, "GlyphClass")
        self.assertEqual(gc.glyphSet(), ("cid00999", "cid01000", "cid01001"))

    def test_glyphclass_range_cid_bad(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Bad range: start should be less than limit",
            self.parse,
            r"@bad = [\998-\995];",
        )

    def test_glyphclass_range_uppercase(self):
        [gc] = self.parse("@swashes = [X.swash-Z.swash];").statements
        self.assertEqual(gc.name, "swashes")
        self.assertEqual(gc.glyphSet(), ("X.swash", "Y.swash", "Z.swash"))

    def test_glyphclass_range_lowercase(self):
        [gc] = self.parse("@defg.sc = [d.sc-g.sc];").statements
        self.assertEqual(gc.name, "defg.sc")
        self.assertEqual(gc.glyphSet(), ("d.sc", "e.sc", "f.sc", "g.sc"))

    def test_glyphclass_range_dash(self):
        glyphNames = "A-foo.sc B-foo.sc C-foo.sc".split()
        [gc] = self.parse("@range = [A-foo.sc-C-foo.sc];", glyphNames).statements
        self.assertEqual(gc.glyphSet(), ("A-foo.sc", "B-foo.sc", "C-foo.sc"))

    def test_glyphclass_range_dash_with_space(self):
        gn = "A-foo.sc B-foo.sc C-foo.sc".split()
        [gc] = self.parse("@range = [A-foo.sc - C-foo.sc];", gn).statements
        self.assertEqual(gc.glyphSet(), ("A-foo.sc", "B-foo.sc", "C-foo.sc"))

    def test_glyphclass_ambiguous_dash_no_glyph_names(self):
        # If Parser is initialized without a glyphNames parameter (or with empty one)
        # it cannot distinguish between a glyph name containing an hyphen, or a
        # range of glyph names; thus it will interpret them as literal glyph names
        # while also outputting a logging warning to alert user about the ambiguity.
        # https://github.com/fonttools/fonttools/issues/1768
        glyphNames = ()
        with CapturingLogHandler("fontTools.feaLib.parser", level="WARNING") as caplog:
            [gc] = self.parse(
                "@class = [A-foo.sc B-foo.sc C D];", glyphNames
            ).statements
        self.assertEqual(gc.glyphSet(), ("A-foo.sc", "B-foo.sc", "C", "D"))
        self.assertEqual(len(caplog.records), 2)
        caplog.assertRegex("Ambiguous glyph name that looks like a range:")

    def test_glyphclass_glyph_name_should_win_over_range(self):
        # The OpenType Feature File Specification v1.20 makes it clear
        # that if a dashed name could be interpreted either as a glyph name
        # or as a range, then the semantics should be the single dashed name.
        glyphNames = "A-foo.sc-C-foo.sc A-foo.sc B-foo.sc C-foo.sc".split()
        [gc] = self.parse("@range = [A-foo.sc-C-foo.sc];", glyphNames).statements
        self.assertEqual(gc.glyphSet(), ("A-foo.sc-C-foo.sc",))

    def test_glyphclass_range_dash_ambiguous(self):
        glyphNames = "A B C A-B B-C".split()
        self.assertRaisesRegex(
            FeatureLibError,
            'Ambiguous glyph range "A-B-C"; '
            'please use "A - B-C" or "A-B - C" to clarify what you mean',
            self.parse,
            r"@bad = [A-B-C];",
            glyphNames,
        )

    def test_glyphclass_range_digit1(self):
        [gc] = self.parse("@range = [foo.2-foo.5];").statements
        self.assertEqual(gc.glyphSet(), ("foo.2", "foo.3", "foo.4", "foo.5"))

    def test_glyphclass_range_digit2(self):
        [gc] = self.parse("@range = [foo.09-foo.11];").statements
        self.assertEqual(gc.glyphSet(), ("foo.09", "foo.10", "foo.11"))

    def test_glyphclass_range_digit3(self):
        [gc] = self.parse("@range = [foo.123-foo.125];").statements
        self.assertEqual(gc.glyphSet(), ("foo.123", "foo.124", "foo.125"))

    def test_glyphclass_range_bad(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Bad range: "a" and "foobar" should have the same length',
            self.parse,
            "@bad = [a-foobar];",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            'Bad range: "A.swash-z.swash"',
            self.parse,
            "@bad = [A.swash-z.swash];",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            "Start of range must be smaller than its end",
            self.parse,
            "@bad = [B.swash-A.swash];",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            'Bad range: "foo.1234-foo.9876"',
            self.parse,
            "@bad = [foo.1234-foo.9876];",
        )

    def test_glyphclass_range_mixed(self):
        [gc] = self.parse("@range = [a foo.09-foo.11 X.sc-Z.sc];").statements
        self.assertEqual(
            gc.glyphSet(), ("a", "foo.09", "foo.10", "foo.11", "X.sc", "Y.sc", "Z.sc")
        )

    def test_glyphclass_reference(self):
        [vowels_lc, vowels_uc, vowels] = self.parse(
            "@Vowels.lc = [a e i o u]; @Vowels.uc = [A E I O U];"
            "@Vowels = [@Vowels.lc @Vowels.uc y Y];"
        ).statements
        self.assertEqual(vowels_lc.glyphSet(), tuple("aeiou"))
        self.assertEqual(vowels_uc.glyphSet(), tuple("AEIOU"))
        self.assertEqual(vowels.glyphSet(), tuple("aeiouAEIOUyY"))
        self.assertEqual(vowels.asFea(), "@Vowels = [@Vowels.lc @Vowels.uc y Y];")
        self.assertRaisesRegex(
            FeatureLibError,
            "Unknown glyph class @unknown",
            self.parse,
            "@bad = [@unknown];",
        )

    def test_glyphclass_scoping(self):
        [foo, liga, smcp] = self.parse(
            "@foo = [a b];"
            "feature liga { @bar = [@foo l]; } liga;"
            "feature smcp { @bar = [@foo s]; } smcp;"
        ).statements
        self.assertEqual(foo.glyphSet(), ("a", "b"))
        self.assertEqual(liga.statements[0].glyphSet(), ("a", "b", "l"))
        self.assertEqual(smcp.statements[0].glyphSet(), ("a", "b", "s"))

    def test_glyphclass_scoping_bug496(self):
        # https://github.com/fonttools/fonttools/issues/496
        f1, f2 = self.parse(
            "feature F1 { lookup L { @GLYPHCLASS = [A B C];} L; } F1;"
            "feature F2 { sub @GLYPHCLASS by D; } F2;"
        ).statements
        self.assertEqual(list(f2.statements[0].glyphs[0].glyphSet()), ["A", "B", "C"])

    def test_GlyphClassDef(self):
        doc = self.parse("table GDEF {GlyphClassDef [b],[l],[m],[C c];} GDEF;")
        s = doc.statements[0].statements[0]
        self.assertIsInstance(s, ast.GlyphClassDefStatement)
        self.assertEqual(glyphstr([s.baseGlyphs]), "b")
        self.assertEqual(glyphstr([s.ligatureGlyphs]), "l")
        self.assertEqual(glyphstr([s.markGlyphs]), "m")
        self.assertEqual(glyphstr([s.componentGlyphs]), "[C c]")

    def test_GlyphClassDef_noCLassesSpecified(self):
        doc = self.parse("table GDEF {GlyphClassDef ,,,;} GDEF;")
        s = doc.statements[0].statements[0]
        self.assertIsNone(s.baseGlyphs)
        self.assertIsNone(s.ligatureGlyphs)
        self.assertIsNone(s.markGlyphs)
        self.assertIsNone(s.componentGlyphs)

    def test_ignore_pos(self):
        doc = self.parse("feature test {ignore pos e t' c, q u' u' x;} test;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.IgnorePosStatement)
        [(pref1, glyphs1, suff1), (pref2, glyphs2, suff2)] = sub.chainContexts
        self.assertEqual(glyphstr(pref1), "e")
        self.assertEqual(glyphstr(glyphs1), "t")
        self.assertEqual(glyphstr(suff1), "c")
        self.assertEqual(glyphstr(pref2), "q")
        self.assertEqual(glyphstr(glyphs2), "u u")
        self.assertEqual(glyphstr(suff2), "x")

    def test_ignore_position(self):
        doc = self.parse(
            "feature test {" "    ignore position f [a e] d' [a u]' [e y];" "} test;"
        )
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.IgnorePosStatement)
        [(prefix, glyphs, suffix)] = sub.chainContexts
        self.assertEqual(glyphstr(prefix), "f [a e]")
        self.assertEqual(glyphstr(glyphs), "d [a u]")
        self.assertEqual(glyphstr(suffix), "[e y]")

    def test_ignore_position_with_lookup(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'No lookups can be specified for "ignore pos"',
            self.parse,
            "lookup L { pos [A A.sc] -100; } L;"
            "feature test { ignore pos f' i', A' lookup L; } test;",
        )

    def test_ignore_sub(self):
        doc = self.parse("feature test {ignore sub e t' c, q u' u' x;} test;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.IgnoreSubstStatement)
        [(pref1, glyphs1, suff1), (pref2, glyphs2, suff2)] = sub.chainContexts
        self.assertEqual(glyphstr(pref1), "e")
        self.assertEqual(glyphstr(glyphs1), "t")
        self.assertEqual(glyphstr(suff1), "c")
        self.assertEqual(glyphstr(pref2), "q")
        self.assertEqual(glyphstr(glyphs2), "u u")
        self.assertEqual(glyphstr(suff2), "x")

    def test_ignore_substitute(self):
        doc = self.parse(
            "feature test {" "    ignore substitute f [a e] d' [a u]' [e y];" "} test;"
        )
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.IgnoreSubstStatement)
        [(prefix, glyphs, suffix)] = sub.chainContexts
        self.assertEqual(glyphstr(prefix), "f [a e]")
        self.assertEqual(glyphstr(glyphs), "d [a u]")
        self.assertEqual(glyphstr(suffix), "[e y]")

    def test_ignore_substitute_with_lookup(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'No lookups can be specified for "ignore sub"',
            self.parse,
            "lookup L { sub [A A.sc] by a; } L;"
            "feature test { ignore sub f' i', A' lookup L; } test;",
        )

    def test_include_statement(self):
        doc = self.parse(
            """\
            include(../family.fea);
            include # Comment
                (foo)
                  ;
            """,
            followIncludes=False,
        )
        s1, s2, s3 = doc.statements
        self.assertEqual(type(s1), ast.IncludeStatement)
        self.assertEqual(s1.filename, "../family.fea")
        self.assertEqual(s1.asFea(), "include(../family.fea);")
        self.assertEqual(type(s2), ast.IncludeStatement)
        self.assertEqual(s2.filename, "foo")
        self.assertEqual(s2.asFea(), "include(foo);")
        self.assertEqual(type(s3), ast.Comment)
        self.assertEqual(s3.text, "# Comment")

    def test_include_statement_no_semicolon(self):
        doc = self.parse(
            """\
            include(../family.fea)
            """,
            followIncludes=False,
        )
        s1 = doc.statements[0]
        self.assertEqual(type(s1), ast.IncludeStatement)
        self.assertEqual(s1.filename, "../family.fea")
        self.assertEqual(s1.asFea(), "include(../family.fea);")

    def test_language(self):
        doc = self.parse("feature test {language DEU;} test;")
        s = doc.statements[0].statements[0]
        self.assertEqual(type(s), ast.LanguageStatement)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertEqual(s.language, "DEU ")
        self.assertTrue(s.include_default)
        self.assertFalse(s.required)

    def test_language_multiple(self):
        doc = self.parse(
            "feature test {language AZE CRT KAZ TAT TRK exclude_dflt required;} test;"
        )
        s = doc.statements[0].statements[0]
        self.assertEqual(type(s), ast.LanguageStatement)
        self.assertEqual(s.languages, ["AZE ", "CRT ", "KAZ ", "TAT ", "TRK "])
        with self.assertWarnsRegex(UserWarning, "use .languages") as cm:
            self.assertEqual(s.language, "AZE ")
        self.assertEqual(cm.filename, __file__)
        self.assertFalse(s.include_default)
        self.assertTrue(s.required)
        self.assertEqual(
            s.asFea(),
            "language AZE CRT KAZ TAT TRK exclude_dflt required;",
        )

    def test_language_multiple_missing_semicolon(self):
        # The next statement must not be read as more language tags.
        self.assertRaisesRegex(
            FeatureLibError,
            "Expected ';'",
            self.parse,
            "feature test {language AZE CRT\n sub a by b;} test;",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            "Expected ';'",
            self.parse,
            "feature test {language AZE\n lookup foo;} test;",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            "Expected ';'",
            self.parse,
            "feature test {language AZE CRT\n @foo = [a b];} test;",
        )

    def test_language_statement_keywords_up_to_date(self):
        # parse_language_ ends a multi-tag statement at the keywords that
        # start a block statement; this fails when parse_block_ learns a new
        # one that _statement_keywords does not list.
        source = textwrap.dedent(inspect.getsource(Parser.parse_block_))
        keywords = set()
        for node in pyast.walk(pyast.parse(source)):
            if (
                isinstance(node, pyast.Call)
                and isinstance(node.func, pyast.Attribute)
                and node.func.attr == "is_cur_keyword_"
            ):
                for arg in pyast.walk(node.args[0]):
                    if isinstance(arg, pyast.Constant) and isinstance(arg.value, str):
                        keywords.add(arg.value)
        self.assertIn("sub", keywords)  # the walk found the calls
        self.assertEqual(keywords - Parser._statement_keywords, set())

    def test_language_multiple_dflt(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"dflt" must be the only tag in a language statement',
            self.parse,
            "feature test {language dflt AZE;} test;",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            '"dflt" must be the only tag in a language statement',
            self.parse,
            "feature test {language AZE dflt;} test;",
        )

    def test_language_exclude_dflt(self):
        doc = self.parse("feature test {language DEU exclude_dflt;} test;")
        s = doc.statements[0].statements[0]
        self.assertEqual(type(s), ast.LanguageStatement)
        self.assertEqual(s.language, "DEU ")
        self.assertFalse(s.include_default)
        self.assertFalse(s.required)

    def test_language_exclude_dflt_required(self):
        doc = self.parse(
            "feature test {" "  language DEU exclude_dflt required;" "} test;"
        )
        s = doc.statements[0].statements[0]
        self.assertEqual(type(s), ast.LanguageStatement)
        self.assertEqual(s.language, "DEU ")
        self.assertFalse(s.include_default)
        self.assertTrue(s.required)

    def test_language_include_dflt(self):
        doc = self.parse("feature test {language DEU include_dflt;} test;")
        s = doc.statements[0].statements[0]
        self.assertEqual(type(s), ast.LanguageStatement)
        self.assertEqual(s.language, "DEU ")
        self.assertTrue(s.include_default)
        self.assertFalse(s.required)

    def test_language_include_dflt_required(self):
        doc = self.parse(
            "feature test {" "  language DEU include_dflt required;" "} test;"
        )
        s = doc.statements[0].statements[0]
        self.assertEqual(type(s), ast.LanguageStatement)
        self.assertEqual(s.language, "DEU ")
        self.assertTrue(s.include_default)
        self.assertTrue(s.required)

    def test_language_DFLT(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"DFLT" is not a valid language tag; use "dflt" instead',
            self.parse,
            "feature test { language DFLT; } test;",
        )

    def test_ligatureCaretByIndex_glyphClass(self):
        doc = self.parse("table GDEF{LigatureCaretByIndex [c_t f_i] 2;}GDEF;")
        s = doc.statements[0].statements[0]
        self.assertIsInstance(s, ast.LigatureCaretByIndexStatement)
        self.assertEqual(glyphstr([s.glyphs]), "[c_t f_i]")
        self.assertEqual(s.carets, [2])

    def test_ligatureCaretByIndex_singleGlyph(self):
        doc = self.parse("table GDEF{LigatureCaretByIndex f_f_i 3 7;}GDEF;")
        s = doc.statements[0].statements[0]
        self.assertIsInstance(s, ast.LigatureCaretByIndexStatement)
        self.assertEqual(glyphstr([s.glyphs]), "f_f_i")
        self.assertEqual(s.carets, [3, 7])

    def test_ligatureCaretByPos_glyphClass(self):
        doc = self.parse("table GDEF {LigatureCaretByPos [c_t f_i] 7;} GDEF;")
        s = doc.statements[0].statements[0]
        self.assertIsInstance(s, ast.LigatureCaretByPosStatement)
        self.assertEqual(glyphstr([s.glyphs]), "[c_t f_i]")
        self.assertEqual(s.carets, [7])

    def test_ligatureCaretByPos_singleGlyph(self):
        doc = self.parse("table GDEF {LigatureCaretByPos f_i 400 380;} GDEF;")
        s = doc.statements[0].statements[0]
        self.assertIsInstance(s, ast.LigatureCaretByPosStatement)
        self.assertEqual(glyphstr([s.glyphs]), "f_i")
        self.assertEqual(s.carets, [400, 380])

    def test_ligatureCaretByPos_out_of_range(self):
        self.assertRaisesRegex(
            FeatureLibError,
            r"Caret position out of valid range \(-32768..32767\)",
            self.parse,
            "table GDEF {LigatureCaretByPos f_i 400 99999;} GDEF;",
        )

    def test_ligatureCaretByIndex_out_of_range(self):
        self.assertRaisesRegex(
            FeatureLibError,
            r"Caret contour point out of valid range \(0..65535\)",
            self.parse,
            "table GDEF {LigatureCaretByIndex f_i -1;} GDEF;",
        )

    def test_ligatureCaretByPos_variable_scalar(self):
        doc = self.parse(
            "table GDEF {LigatureCaretByPos f_i (wght=200:400 wght=900:1000) 380;} GDEF;"
        )
        s = doc.statements[0].statements[0]
        self.assertIsInstance(s, ast.LigatureCaretByPosStatement)
        self.assertEqual(glyphstr([s.glyphs]), "f_i")
        self.assertEqual(len(s.carets), 2)
        self.assertEqual(str(s.carets[0]), "(wght=200:400 wght=900:1000)")
        self.assertEqual(s.carets[1], 380)

    def test_lookup_block(self):
        [lookup] = self.parse("lookup Ligatures {} Ligatures;").statements
        self.assertEqual(lookup.name, "Ligatures")
        self.assertFalse(lookup.use_extension)

    def test_lookup_block_useExtension(self):
        [lookup] = self.parse("lookup Foo useExtension {} Foo;").statements
        self.assertEqual(lookup.name, "Foo")
        self.assertTrue(lookup.use_extension)
        self.assertEqual(lookup.asFea(), "lookup Foo useExtension {\n    \n} Foo;\n")

    def test_lookup_block_name_mismatch(self):
        self.assertRaisesRegex(
            FeatureLibError, 'Expected "Foo"', self.parse, "lookup Foo {} Bar;"
        )

    def test_lookup_block_with_horizontal_valueRecordDef(self):
        doc = self.parse(
            "feature liga {"
            "  lookup look {"
            "    valueRecordDef 123 foo;"
            "  } look;"
            "} liga;"
        )
        [liga] = doc.statements
        [look] = liga.statements
        [foo] = look.statements
        self.assertEqual(foo.value.xAdvance, 123)
        self.assertIsNone(foo.value.yAdvance)

    def test_lookup_block_with_vertical_valueRecordDef(self):
        doc = self.parse(
            "feature vkrn {"
            "  lookup look {"
            "    valueRecordDef 123 foo;"
            "  } look;"
            "} vkrn;"
        )
        [vkrn] = doc.statements
        [look] = vkrn.statements
        [foo] = look.statements
        self.assertIsNone(foo.value.xAdvance)
        self.assertEqual(foo.value.yAdvance, 123)

    def test_lookup_comment(self):
        [lookup] = self.parse("lookup L { # Comment\n } L;").statements
        [comment] = lookup.statements
        self.assertIsInstance(comment, ast.Comment)
        self.assertEqual(comment.text, "# Comment")

    def test_lookup_reference(self):
        [foo, bar] = self.parse(
            "lookup Foo {} Foo;" "feature Bar {lookup Foo;} Bar;"
        ).statements
        [ref] = bar.statements
        self.assertEqual(type(ref), ast.LookupReferenceStatement)
        self.assertEqual(ref.lookup, foo)

    def test_lookup_reference_to_lookup_inside_feature(self):
        [qux, bar] = self.parse(
            "feature Qux {lookup Foo {} Foo;} Qux;" "feature Bar {lookup Foo;} Bar;"
        ).statements
        [foo] = qux.statements
        [ref] = bar.statements
        self.assertIsInstance(ref, ast.LookupReferenceStatement)
        self.assertEqual(ref.lookup, foo)

    def test_lookup_reference_unknown(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Unknown lookup "Huh"',
            self.parse,
            "feature liga {lookup Huh;} liga;",
        )

    def parse_lookupflag_(self, s):
        return self.parse("lookup L {%s} L;" % s).statements[0].statements[-1]

    def test_lookupflag_format_A(self):
        flag = self.parse_lookupflag_("lookupflag RightToLeft IgnoreMarks;")
        self.assertIsInstance(flag, ast.LookupFlagStatement)
        self.assertEqual(flag.value, 9)
        self.assertIsNone(flag.markAttachment)
        self.assertIsNone(flag.markFilteringSet)
        self.assertEqual(flag.asFea(), "lookupflag RightToLeft IgnoreMarks;")

    def test_lookupflag_format_A_MarkAttachmentType(self):
        flag = self.parse_lookupflag_(
            "@TOP_MARKS = [acute grave macron];"
            "lookupflag RightToLeft MarkAttachmentType @TOP_MARKS;"
        )
        self.assertIsInstance(flag, ast.LookupFlagStatement)
        self.assertEqual(flag.value, 1)
        self.assertIsInstance(flag.markAttachment, ast.GlyphClassName)
        self.assertEqual(flag.markAttachment.glyphSet(), ("acute", "grave", "macron"))
        self.assertIsNone(flag.markFilteringSet)
        self.assertEqual(
            flag.asFea(), "lookupflag RightToLeft MarkAttachmentType @TOP_MARKS;"
        )

    def test_lookupflag_format_A_MarkAttachmentType_glyphClass(self):
        flag = self.parse_lookupflag_(
            "lookupflag RightToLeft MarkAttachmentType [acute grave macron];"
        )
        self.assertIsInstance(flag, ast.LookupFlagStatement)
        self.assertEqual(flag.value, 1)
        self.assertIsInstance(flag.markAttachment, ast.GlyphClass)
        self.assertEqual(flag.markAttachment.glyphSet(), ("acute", "grave", "macron"))
        self.assertIsNone(flag.markFilteringSet)
        self.assertEqual(
            flag.asFea(),
            "lookupflag RightToLeft MarkAttachmentType [acute grave macron];",
        )

    def test_lookupflag_format_A_UseMarkFilteringSet(self):
        flag = self.parse_lookupflag_(
            "@BOTTOM_MARKS = [cedilla ogonek];"
            "lookupflag UseMarkFilteringSet @BOTTOM_MARKS IgnoreLigatures;"
        )
        self.assertIsInstance(flag, ast.LookupFlagStatement)
        self.assertEqual(flag.value, 4)
        self.assertIsNone(flag.markAttachment)
        self.assertIsInstance(flag.markFilteringSet, ast.GlyphClassName)
        self.assertEqual(flag.markFilteringSet.glyphSet(), ("cedilla", "ogonek"))
        self.assertEqual(
            flag.asFea(),
            "lookupflag IgnoreLigatures UseMarkFilteringSet @BOTTOM_MARKS;",
        )

    def test_lookupflag_format_A_UseMarkFilteringSet_glyphClass(self):
        flag = self.parse_lookupflag_(
            "lookupflag UseMarkFilteringSet [cedilla ogonek] IgnoreLigatures;"
        )
        self.assertIsInstance(flag, ast.LookupFlagStatement)
        self.assertEqual(flag.value, 4)
        self.assertIsNone(flag.markAttachment)
        self.assertIsInstance(flag.markFilteringSet, ast.GlyphClass)
        self.assertEqual(flag.markFilteringSet.glyphSet(), ("cedilla", "ogonek"))
        self.assertEqual(
            flag.asFea(),
            "lookupflag IgnoreLigatures UseMarkFilteringSet [cedilla ogonek];",
        )

    def test_lookupflag_format_B(self):
        flag = self.parse_lookupflag_("lookupflag 7;")
        self.assertIsInstance(flag, ast.LookupFlagStatement)
        self.assertEqual(flag.value, 7)
        self.assertIsNone(flag.markAttachment)
        self.assertIsNone(flag.markFilteringSet)
        self.assertEqual(
            flag.asFea(), "lookupflag RightToLeft IgnoreBaseGlyphs IgnoreLigatures;"
        )

    def test_lookupflag_format_B_zero(self):
        flag = self.parse_lookupflag_("lookupflag 0;")
        self.assertIsInstance(flag, ast.LookupFlagStatement)
        self.assertEqual(flag.value, 0)
        self.assertIsNone(flag.markAttachment)
        self.assertIsNone(flag.markFilteringSet)
        self.assertEqual(flag.asFea(), "lookupflag 0;")

    def test_lookupflag_no_value(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "lookupflag must have a value",
            self.parse,
            "feature test {lookupflag;} test;",
        )

    def test_lookupflag_repeated(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "RightToLeft can be specified only once",
            self.parse,
            "feature test {lookupflag RightToLeft RightToLeft;} test;",
        )

    def test_lookupflag_unrecognized(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"IgnoreCookies" is not a recognized lookupflag',
            self.parse,
            "feature test {lookupflag IgnoreCookies;} test;",
        )

    def test_gpos_type_1_glyph(self):
        doc = self.parse("feature kern {pos one <1 2 3 4>;} kern;")
        pos = doc.statements[0].statements[0]
        self.assertIsInstance(pos, ast.SinglePosStatement)
        [(glyphs, value)] = pos.pos
        self.assertEqual(glyphstr([glyphs]), "one")
        self.assertEqual(value.asFea(), "<1 2 3 4>")

    def test_gpos_type_1_glyphclass_horizontal(self):
        doc = self.parse("feature kern {pos [one two] -300;} kern;")
        pos = doc.statements[0].statements[0]
        self.assertIsInstance(pos, ast.SinglePosStatement)
        [(glyphs, value)] = pos.pos
        self.assertEqual(glyphstr([glyphs]), "[one two]")
        self.assertEqual(value.asFea(), "-300")

    def test_gpos_type_1_glyphclass_vertical(self):
        doc = self.parse("feature vkrn {pos [one two] -300;} vkrn;")
        pos = doc.statements[0].statements[0]
        self.assertIsInstance(pos, ast.SinglePosStatement)
        [(glyphs, value)] = pos.pos
        self.assertEqual(glyphstr([glyphs]), "[one two]")
        self.assertEqual(value.asFea(), "-300")

    def test_gpos_type_1_multiple(self):
        doc = self.parse("feature f {pos one'1 two'2 [five six]'56;} f;")
        pos = doc.statements[0].statements[0]
        self.assertIsInstance(pos, ast.SinglePosStatement)
        [(glyphs1, val1), (glyphs2, val2), (glyphs3, val3)] = pos.pos
        self.assertEqual(glyphstr([glyphs1]), "one")
        self.assertEqual(val1.asFea(), "1")
        self.assertEqual(glyphstr([glyphs2]), "two")
        self.assertEqual(val2.asFea(), "2")
        self.assertEqual(glyphstr([glyphs3]), "[five six]")
        self.assertEqual(val3.asFea(), "56")
        self.assertEqual(pos.prefix, [])
        self.assertEqual(pos.suffix, [])

    def test_gpos_type_1_enumerated(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"enumerate" is only allowed with pair positionings',
            self.parse,
            "feature test {enum pos T 100;} test;",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            '"enumerate" is only allowed with pair positionings',
            self.parse,
            "feature test {enumerate pos T 100;} test;",
        )

    def test_gpos_type_1_chained(self):
        doc = self.parse("feature kern {pos [A B] [T Y]' 20 comma;} kern;")
        pos = doc.statements[0].statements[0]
        self.assertIsInstance(pos, ast.SinglePosStatement)
        [(glyphs, value)] = pos.pos
        self.assertEqual(glyphstr([glyphs]), "[T Y]")
        self.assertEqual(value.asFea(), "20")
        self.assertEqual(glyphstr(pos.prefix), "[A B]")
        self.assertEqual(glyphstr(pos.suffix), "comma")

    def test_gpos_type_1_chained_special_kern_format_valuerecord_format_a(self):
        doc = self.parse("feature kern {pos [A B] [T Y]' comma 20;} kern;")
        pos = doc.statements[0].statements[0]
        self.assertIsInstance(pos, ast.SinglePosStatement)
        [(glyphs, value)] = pos.pos
        self.assertEqual(glyphstr([glyphs]), "[T Y]")
        self.assertEqual(value.asFea(), "20")
        self.assertEqual(glyphstr(pos.prefix), "[A B]")
        self.assertEqual(glyphstr(pos.suffix), "comma")

    def test_gpos_type_1_chained_special_kern_format_valuerecord_format_b(self):
        doc = self.parse("feature kern {pos [A B] [T Y]' comma <0 0 0 0>;} kern;")
        pos = doc.statements[0].statements[0]
        self.assertIsInstance(pos, ast.SinglePosStatement)
        [(glyphs, value)] = pos.pos
        self.assertEqual(glyphstr([glyphs]), "[T Y]")
        self.assertEqual(value.asFea(), "<0 0 0 0>")
        self.assertEqual(glyphstr(pos.prefix), "[A B]")
        self.assertEqual(glyphstr(pos.suffix), "comma")

    def test_gpos_type_1_chained_special_kern_format_valuerecord_format_b_bug2293(self):
        # https://github.com/fonttools/fonttools/issues/2293
        doc = self.parse("feature kern {pos [A B] [T Y]' comma a <0 0 0 0>;} kern;")
        pos = doc.statements[0].statements[0]
        self.assertIsInstance(pos, ast.SinglePosStatement)
        [(glyphs, value)] = pos.pos
        self.assertEqual(glyphstr([glyphs]), "[T Y]")
        self.assertEqual(value.asFea(), "<0 0 0 0>")
        self.assertEqual(glyphstr(pos.prefix), "[A B]")
        self.assertEqual(glyphstr(pos.suffix), "comma a")

    def test_gpos_type_1_chained_exception1(self):
        with self.assertRaisesRegex(FeatureLibError, "Positioning values are allowed"):
            doc = self.parse(
                "feature kern {" "    pos [A B]' [T Y]' comma a <0 0 0 0>;" "} kern;"
            )

    def test_gpos_type_1_chained_exception2(self):
        with self.assertRaisesRegex(FeatureLibError, "Positioning values are allowed"):
            doc = self.parse(
                "feature kern {"
                "    pos [A B]' <0 0 0 0> [T Y]' comma a <0 0 0 0>;"
                "} kern;"
            )

    def test_gpos_type_1_chained_exception3(self):
        with self.assertRaisesRegex(FeatureLibError, "Positioning cannot be applied"):
            doc = self.parse(
                "feature kern {"
                "    pos [A B] <0 0 0 0> [T Y]' comma a <0 0 0 0>;"
                "} kern;"
            )

    def test_gpos_type_1_chained_exception4(self):
        with self.assertRaisesRegex(FeatureLibError, "Positioning values are allowed"):
            doc = self.parse("feature kern {" "    pos a' b c 123 d;" "} kern;")

    def test_gpos_type_1_null(self):
        doc = self.parse("feature test {pos a <NULL>;} test;")
        pos = doc.statements[0].statements[0]
        self.assertEqual(pos.asFea(), "pos a <NULL>;")

    def test_gpos_type_1_null_chained(self):
        doc = self.parse("feature test {pos a' <NULL>;} test;")
        pos = doc.statements[0].statements[0]
        self.assertEqual(pos.asFea(), "pos a' <NULL>;")

    def test_gpos_type_2_format_a(self):
        doc = self.parse(
            "feature kern {" "    pos [T V] -60 [a b c] <1 2 3 4>;" "} kern;"
        )
        pos = doc.statements[0].statements[0]
        self.assertEqual(type(pos), ast.PairPosStatement)
        self.assertFalse(pos.enumerated)
        self.assertEqual(glyphstr([pos.glyphs1]), "[T V]")
        self.assertEqual(pos.valuerecord1.asFea(), "-60")
        self.assertEqual(glyphstr([pos.glyphs2]), "[a b c]")
        self.assertEqual(pos.valuerecord2.asFea(), "<1 2 3 4>")

    def test_gpos_type_2_format_a_enumerated(self):
        doc = self.parse(
            "feature kern {" "    enum pos [T V] -60 [a b c] <1 2 3 4>;" "} kern;"
        )
        pos = doc.statements[0].statements[0]
        self.assertEqual(type(pos), ast.PairPosStatement)
        self.assertTrue(pos.enumerated)
        self.assertEqual(glyphstr([pos.glyphs1]), "[T V]")
        self.assertEqual(pos.valuerecord1.asFea(), "-60")
        self.assertEqual(glyphstr([pos.glyphs2]), "[a b c]")
        self.assertEqual(pos.valuerecord2.asFea(), "<1 2 3 4>")

    def test_gpos_type_2_format_a_with_null_first(self):
        doc = self.parse(
            "feature kern {" "    pos [T V] <NULL> [a b c] <1 2 3 4>;" "} kern;"
        )
        pos = doc.statements[0].statements[0]
        self.assertEqual(type(pos), ast.PairPosStatement)
        self.assertFalse(pos.enumerated)
        self.assertEqual(glyphstr([pos.glyphs1]), "[T V]")
        self.assertFalse(pos.valuerecord1)
        self.assertEqual(pos.valuerecord1.asFea(), "<NULL>")
        self.assertEqual(glyphstr([pos.glyphs2]), "[a b c]")
        self.assertEqual(pos.valuerecord2.asFea(), "<1 2 3 4>")
        self.assertEqual(pos.asFea(), "pos [T V] <NULL> [a b c] <1 2 3 4>;")

    def test_gpos_type_2_format_a_with_null_second(self):
        doc = self.parse(
            "feature kern {" "    pos [T V] <1 2 3 4> [a b c] <NULL>;" "} kern;"
        )
        pos = doc.statements[0].statements[0]
        self.assertEqual(type(pos), ast.PairPosStatement)
        self.assertFalse(pos.enumerated)
        self.assertEqual(glyphstr([pos.glyphs1]), "[T V]")
        self.assertEqual(pos.valuerecord1.asFea(), "<1 2 3 4>")
        self.assertEqual(glyphstr([pos.glyphs2]), "[a b c]")
        self.assertFalse(pos.valuerecord2)
        self.assertEqual(pos.asFea(), "pos [T V] [a b c] <1 2 3 4>;")

    def test_gpos_type_2_format_b(self):
        doc = self.parse("feature kern {" "    pos [T V] [a b c] <1 2 3 4>;" "} kern;")
        pos = doc.statements[0].statements[0]
        self.assertEqual(type(pos), ast.PairPosStatement)
        self.assertFalse(pos.enumerated)
        self.assertEqual(glyphstr([pos.glyphs1]), "[T V]")
        self.assertEqual(pos.valuerecord1.asFea(), "<1 2 3 4>")
        self.assertEqual(glyphstr([pos.glyphs2]), "[a b c]")
        self.assertIsNone(pos.valuerecord2)

    def test_gpos_type_2_format_b_enumerated(self):
        doc = self.parse(
            "feature kern {" "    enumerate position [T V] [a b c] <1 2 3 4>;" "} kern;"
        )
        pos = doc.statements[0].statements[0]
        self.assertEqual(type(pos), ast.PairPosStatement)
        self.assertTrue(pos.enumerated)
        self.assertEqual(glyphstr([pos.glyphs1]), "[T V]")
        self.assertEqual(pos.valuerecord1.asFea(), "<1 2 3 4>")
        self.assertEqual(glyphstr([pos.glyphs2]), "[a b c]")
        self.assertIsNone(pos.valuerecord2)

    def test_gpos_type_3(self):
        doc = self.parse(
            "feature kern {"
            "    position cursive A <anchor 12 -2> <anchor 2 3>;"
            "} kern;"
        )
        pos = doc.statements[0].statements[0]
        self.assertEqual(type(pos), ast.CursivePosStatement)
        self.assertEqual(pos.glyphclass.glyphSet(), ("A",))
        self.assertEqual((pos.entryAnchor.x, pos.entryAnchor.y), (12, -2))
        self.assertEqual((pos.exitAnchor.x, pos.exitAnchor.y), (2, 3))

    def test_gpos_type_3_enumerated(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"enumerate" is not allowed with cursive attachment positioning',
            self.parse,
            "feature kern {"
            "    enumerate position cursive A <anchor 12 -2> <anchor 2 3>;"
            "} kern;",
        )

    def test_gpos_type_4(self):
        doc = self.parse(
            "markClass [acute grave] <anchor 150 -10> @TOP_MARKS;"
            "markClass [dieresis umlaut] <anchor 300 -10> @TOP_MARKS;"
            "markClass [cedilla] <anchor 300 600> @BOTTOM_MARKS;"
            "feature test {"
            "    position base [a e o u] "
            "        <anchor 250 450> mark @TOP_MARKS "
            "        <anchor 210 -10> mark @BOTTOM_MARKS;"
            "} test;"
        )
        pos = doc.statements[-1].statements[0]
        self.assertEqual(type(pos), ast.MarkBasePosStatement)
        self.assertEqual(pos.base.glyphSet(), ("a", "e", "o", "u"))
        (a1, m1), (a2, m2) = pos.marks
        self.assertEqual((a1.x, a1.y, m1.name), (250, 450, "TOP_MARKS"))
        self.assertEqual((a2.x, a2.y, m2.name), (210, -10, "BOTTOM_MARKS"))

    def test_gpos_type_4_enumerated(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"enumerate" is not allowed with ' "mark-to-base attachment positioning",
            self.parse,
            "feature kern {"
            "    markClass cedilla <anchor 300 600> @BOTTOM_MARKS;"
            "    enumerate position base A <anchor 12 -2> mark @BOTTOM_MARKS;"
            "} kern;",
        )

    def test_gpos_type_4_not_markClass(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "@MARKS is not a markClass",
            self.parse,
            "@MARKS = [acute grave];"
            "feature test {"
            "    position base [a e o u] <anchor 250 450> mark @MARKS;"
            "} test;",
        )

    def test_gpos_type_5(self):
        doc = self.parse(
            "markClass [grave acute] <anchor 150 500> @TOP_MARKS;"
            "markClass [cedilla] <anchor 300 -100> @BOTTOM_MARKS;"
            "feature test {"
            "    position "
            "        ligature [a_f_f_i o_f_f_i] "
            "            <anchor 50 600> mark @TOP_MARKS "
            "            <anchor 50 -10> mark @BOTTOM_MARKS "
            "        ligComponent "
            "            <anchor 30 800> mark @TOP_MARKS "
            "        ligComponent "
            "            <anchor NULL> "
            "        ligComponent "
            "            <anchor 30 -10> mark @BOTTOM_MARKS;"
            "} test;"
        )
        pos = doc.statements[-1].statements[0]
        self.assertEqual(type(pos), ast.MarkLigPosStatement)
        self.assertEqual(pos.ligatures.glyphSet(), ("a_f_f_i", "o_f_f_i"))
        [(a11, m11), (a12, m12)], [(a2, m2)], [], [(a4, m4)] = pos.marks
        self.assertEqual((a11.x, a11.y, m11.name), (50, 600, "TOP_MARKS"))
        self.assertEqual((a12.x, a12.y, m12.name), (50, -10, "BOTTOM_MARKS"))
        self.assertEqual((a2.x, a2.y, m2.name), (30, 800, "TOP_MARKS"))
        self.assertEqual((a4.x, a4.y, m4.name), (30, -10, "BOTTOM_MARKS"))

    def test_gpos_type_5_enumerated(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"enumerate" is not allowed with '
            "mark-to-ligature attachment positioning",
            self.parse,
            "feature test {"
            "    markClass cedilla <anchor 300 600> @MARKS;"
            "    enumerate position "
            "        ligature f_i <anchor 100 0> mark @MARKS"
            "        ligComponent <anchor NULL>;"
            "} test;",
        )

    def test_gpos_type_5_not_markClass(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "@MARKS is not a markClass",
            self.parse,
            "@MARKS = [acute grave];"
            "feature test {"
            "    position ligature f_i <anchor 250 450> mark @MARKS;"
            "} test;",
        )

    def test_gpos_type_6(self):
        doc = self.parse(
            "markClass damma <anchor 189 -103> @MARK_CLASS_1;"
            "feature test {"
            "    position mark hamza <anchor 221 301> mark @MARK_CLASS_1;"
            "} test;"
        )
        pos = doc.statements[-1].statements[0]
        self.assertEqual(type(pos), ast.MarkMarkPosStatement)
        self.assertEqual(pos.baseMarks.glyphSet(), ("hamza",))
        [(a1, m1)] = pos.marks
        self.assertEqual((a1.x, a1.y, m1.name), (221, 301, "MARK_CLASS_1"))

    def test_gpos_type_6_enumerated(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"enumerate" is not allowed with ' "mark-to-mark attachment positioning",
            self.parse,
            "markClass damma <anchor 189 -103> @MARK_CLASS_1;"
            "feature test {"
            "    enum pos mark hamza <anchor 221 301> mark @MARK_CLASS_1;"
            "} test;",
        )

    def test_gpos_type_6_not_markClass(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "@MARKS is not a markClass",
            self.parse,
            "@MARKS = [acute grave];"
            "feature test {"
            "    position mark cedilla <anchor 250 450> mark @MARKS;"
            "} test;",
        )

    def test_gpos_type_8(self):
        doc = self.parse(
            "lookup L1 {pos one 100;} L1; lookup L2 {pos two 200;} L2;"
            "feature test {"
            "    pos [A a] [B b] I' lookup L1 [N n]' lookup L2 P' [Y y] [Z z];"
            "} test;"
        )
        lookup1, lookup2 = doc.statements[0:2]
        pos = doc.statements[-1].statements[0]
        self.assertEqual(type(pos), ast.ChainContextPosStatement)
        self.assertEqual(glyphstr(pos.prefix), "[A a] [B b]")
        self.assertEqual(glyphstr(pos.glyphs), "I [N n] P")
        self.assertEqual(glyphstr(pos.suffix), "[Y y] [Z z]")
        self.assertEqual(pos.lookups, [[lookup1], [lookup2], None])

    def test_gpos_type_8_lookup_with_values(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'If "lookup" is present, no values must be specified',
            self.parse,
            "lookup L1 {pos one 100;} L1;"
            "feature test {"
            "    pos A' lookup L1 B' 20;"
            "} test;",
        )

    def test_markClass(self):
        doc = self.parse("markClass [acute grave] <anchor 350 3> @MARKS;")
        mc = doc.statements[0]
        self.assertIsInstance(mc, ast.MarkClassDefinition)
        self.assertEqual(mc.markClass.name, "MARKS")
        self.assertEqual(mc.glyphSet(), ("acute", "grave"))
        self.assertEqual((mc.anchor.x, mc.anchor.y), (350, 3))

    def test_nameid_windows_unpaired_surrogate(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Name string is not valid utf_16_be",
            self.parse,
            r'table name { nameid 9 "Joachim \d800"; } name;',
        )

    def test_nameid_mac_unencodable_character(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Name string is not valid mac_roman",
            self.parse,
            'table name { nameid 9 1 "A\U0001f600"; } name;',
        )

    def test_stat_name_unpaired_surrogate(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Name string is not valid utf_16_be",
            self.parse,
            r'table STAT { ElidedFallbackName { name "\dc00"; }; } STAT;',
        )

    def test_nameid_windows_utf16(self):
        doc = self.parse(r'table name { nameid 9 "M\00fcller-Lanc\00e9"; } name;')
        name = doc.statements[0].statements[0]
        self.assertIsInstance(name, ast.NameRecord)
        self.assertEqual(name.nameID, 9)
        self.assertEqual(name.platformID, 3)
        self.assertEqual(name.platEncID, 1)
        self.assertEqual(name.langID, 0x0409)
        self.assertEqual(name.string, "Müller-Lancé")
        self.assertEqual(name.asFea(), r'nameid 9 "M\00fcller-Lanc\00e9";')

    def test_nameid_windows_utf16_backslash(self):
        doc = self.parse(r'table name { nameid 9 "Back\005cslash"; } name;')
        name = doc.statements[0].statements[0]
        self.assertEqual(name.string, r"Back\slash")
        self.assertEqual(name.asFea(), r'nameid 9 "Back\005cslash";')

    def test_nameid_windows_utf16_quotation_mark(self):
        doc = self.parse(r'table name { nameid 9 "Quotation \0022Mark\0022"; } name;')
        name = doc.statements[0].statements[0]
        self.assertEqual(name.string, 'Quotation "Mark"')
        self.assertEqual(name.asFea(), r'nameid 9 "Quotation \0022Mark\0022";')

    def test_nameid_windows_utf16_surroates(self):
        doc = self.parse(r'table name { nameid 9 "Carrot \D83E\DD55"; } name;')
        name = doc.statements[0].statements[0]
        self.assertEqual(name.string, r"Carrot 🥕")
        self.assertEqual(name.asFea(), r'nameid 9 "Carrot \d83e\dd55";')

    def test_nameid_mac_roman(self):
        doc = self.parse(r'table name { nameid 9 1 "Joachim M\9fller-Lanc\8e"; } name;')
        name = doc.statements[0].statements[0]
        self.assertIsInstance(name, ast.NameRecord)
        self.assertEqual(name.nameID, 9)
        self.assertEqual(name.platformID, 1)
        self.assertEqual(name.platEncID, 0)
        self.assertEqual(name.langID, 0)
        self.assertEqual(name.string, "Joachim Müller-Lancé")
        self.assertEqual(name.asFea(), r'nameid 9 1 "Joachim M\9fller-Lanc\8e";')

    def test_nameid_mac_croatian(self):
        doc = self.parse(r'table name { nameid 9 1 0 18 "Jovica Veljovi\e6"; } name;')
        name = doc.statements[0].statements[0]
        self.assertEqual(name.nameID, 9)
        self.assertEqual(name.platformID, 1)
        self.assertEqual(name.platEncID, 0)
        self.assertEqual(name.langID, 18)
        self.assertEqual(name.string, "Jovica Veljović")
        self.assertEqual(name.asFea(), r'nameid 9 1 0 18 "Jovica Veljovi\e6";')

    def test_nameid_mac_japanese(self):
        # Literal text and \XX escapes are combined into a single byte
        # sequence before decoding, so multibyte Shift-JIS chars work even
        # when one of the constituent bytes is a printable ASCII char (#1196).
        # Here \95F is the Shift-JIS byte pair 0x95 0x46 = 彦.
        doc = self.parse(
            r'table name { nameid 9 1 1 11 "Kozuka \8f\ac\92\cb\8f\b9\95F"; } name;'
        )
        name = doc.statements[0].statements[0]
        self.assertEqual(name.nameID, 9)
        self.assertEqual(name.platformID, 1)
        self.assertEqual(name.platEncID, 1)
        self.assertEqual(name.langID, 11)
        self.assertEqual(name.string, "Kozuka 小塚昌彦")
        self.assertEqual(
            name.asFea(),
            r'nameid 9 1 1 11 "Kozuka \8f\ac\92\cb\8f\b9\95F";',
        )

    def test_nameid_unsupported_platform(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Expected platform id 1 or 3",
            self.parse,
            'table name { nameid 9 666 "Foo"; } name;',
        )

    def test_nameid_hexadecimal(self):
        doc = self.parse(r'table name { nameid 0x9 0x3 0x1 0x0409 "Test"; } name;')
        name = doc.statements[0].statements[0]
        self.assertEqual(name.nameID, 9)
        self.assertEqual(name.platformID, 3)
        self.assertEqual(name.platEncID, 1)
        self.assertEqual(name.langID, 0x0409)

    def test_nameid_octal(self):
        doc = self.parse(r'table name { nameid 011 03 012 02011 "Test"; } name;')
        name = doc.statements[0].statements[0]
        self.assertEqual(name.nameID, 9)
        self.assertEqual(name.platformID, 3)
        self.assertEqual(name.platEncID, 10)
        self.assertEqual(name.langID, 0o2011)

    def test_cv_hexadecimal(self):
        doc = self.parse(r"feature cv01 { cvParameters { Character 0x5DDE; }; } cv01;")
        cv = doc.statements[0].statements[0].statements[0]
        self.assertEqual(cv.character, 0x5DDE)

    def test_cv_octal(self):
        doc = self.parse(r"feature cv01 { cvParameters { Character 056736; }; } cv01;")
        cv = doc.statements[0].statements[0].statements[0]
        self.assertEqual(cv.character, 0o56736)

    def test_rsub_format_a(self):
        doc = self.parse("feature test {rsub a [b B] c' d [e E] by C;} test;")
        rsub = doc.statements[0].statements[0]
        self.assertEqual(type(rsub), ast.ReverseChainSingleSubstStatement)
        self.assertEqual(glyphstr(rsub.old_prefix), "a [B b]")
        self.assertEqual(rsub.glyphs[0].glyphSet(), ("c",))
        self.assertEqual(rsub.replacements[0].glyphSet(), ("C",))
        self.assertEqual(glyphstr(rsub.old_suffix), "d [E e]")

    def test_rsub_format_a_cid(self):
        doc = self.parse(r"feature test {rsub \1 [\2 \3] \4' \5 by \6;} test;")
        rsub = doc.statements[0].statements[0]
        self.assertEqual(type(rsub), ast.ReverseChainSingleSubstStatement)
        self.assertEqual(glyphstr(rsub.old_prefix), "cid00001 [cid00002 cid00003]")
        self.assertEqual(rsub.glyphs[0].glyphSet(), ("cid00004",))
        self.assertEqual(rsub.replacements[0].glyphSet(), ("cid00006",))
        self.assertEqual(glyphstr(rsub.old_suffix), "cid00005")

    def test_rsub_format_b(self):
        doc = self.parse(
            "feature smcp {"
            "    reversesub A B [one.fitted one.oldstyle]' C [d D] by one;"
            "} smcp;"
        )
        rsub = doc.statements[0].statements[0]
        self.assertEqual(type(rsub), ast.ReverseChainSingleSubstStatement)
        self.assertEqual(glyphstr(rsub.old_prefix), "A B")
        self.assertEqual(glyphstr(rsub.old_suffix), "C [D d]")
        self.assertEqual(mapping(rsub), {"one.fitted": "one", "one.oldstyle": "one"})

    def test_rsub_format_c(self):
        doc = self.parse(
            "feature test {"
            "    reversesub BACK TRACK [a-d]' LOOK AHEAD by [A.sc-D.sc];"
            "} test;"
        )
        rsub = doc.statements[0].statements[0]
        self.assertEqual(type(rsub), ast.ReverseChainSingleSubstStatement)
        self.assertEqual(glyphstr(rsub.old_prefix), "BACK TRACK")
        self.assertEqual(glyphstr(rsub.old_suffix), "LOOK AHEAD")
        self.assertEqual(
            mapping(rsub), {"a": "A.sc", "b": "B.sc", "c": "C.sc", "d": "D.sc"}
        )

    def test_rsub_from(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Reverse chaining substitutions do not support "from"',
            self.parse,
            "feature test {rsub a from [a.1 a.2 a.3];} test;",
        )

    def test_rsub_nonsingle(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "In reverse chaining single substitutions, only a single glyph "
            "or glyph class can be replaced",
            self.parse,
            "feature test {rsub c d by c_d;} test;",
        )

    def test_rsub_multiple_replacement_glyphs(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "In reverse chaining single substitutions, the replacement "
            r'\(after "by"\) must be a single glyph or glyph class',
            self.parse,
            "feature test {rsub f_i by f i;} test;",
        )

    def test_rsub_deletion(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Reverse chaining substitutions do not support glyph deletion",
            self.parse,
            "lookup test { rsub a b c' e by NULL; } test;",
        )

    def test_script(self):
        doc = self.parse("feature test {script cyrl;} test;")
        s = doc.statements[0].statements[0]
        self.assertEqual(type(s), ast.ScriptStatement)
        self.assertEqual(s.script, "cyrl")

    def test_script_dflt(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"dflt" is not a valid script tag; use "DFLT" instead',
            self.parse,
            "feature test {script dflt;} test;",
        )

    def test_stat_design_axis(self):  # STAT DesignAxis
        doc = self.parse(
            "table STAT { DesignAxis opsz 0 " '{name "Optical Size";}; } STAT;'
        )
        da = doc.statements[0].statements[0]
        self.assertIsInstance(da, ast.STATDesignAxisStatement)
        self.assertEqual(da.tag, "opsz")
        self.assertEqual(da.axisOrder, 0)
        self.assertEqual(da.names[0].string, "Optical Size")

    def test_stat_axis_value_format1(self):  # STAT AxisValue
        doc = self.parse(
            "table STAT { DesignAxis opsz 0 "
            '{name "Optical Size";}; '
            'AxisValue {location opsz 8; name "Caption";}; } '
            "STAT;"
        )
        avr = doc.statements[0].statements[1]
        self.assertIsInstance(avr, ast.STATAxisValueStatement)
        self.assertEqual(avr.locations[0].tag, "opsz")
        self.assertEqual(avr.locations[0].values[0], 8)
        self.assertEqual(avr.names[0].string, "Caption")

    def test_stat_axis_value_format2(self):  # STAT AxisValue
        doc = self.parse(
            "table STAT { DesignAxis opsz 0 "
            '{name "Optical Size";}; '
            'AxisValue {location opsz 8 6 10; name "Caption";}; } '
            "STAT;"
        )
        avr = doc.statements[0].statements[1]
        self.assertIsInstance(avr, ast.STATAxisValueStatement)
        self.assertEqual(avr.locations[0].tag, "opsz")
        self.assertEqual(avr.locations[0].values, [8, 6, 10])
        self.assertEqual(avr.names[0].string, "Caption")

    def test_stat_axis_value_format2_bad_range(self):  # STAT AxisValue
        self.assertRaisesRegex(
            FeatureLibError,
            "Default value 5 is outside of specified range 6-10.",
            self.parse,
            "table STAT { DesignAxis opsz 0 "
            '{name "Optical Size";}; '
            'AxisValue {location opsz 5 6 10; name "Caption";}; } '
            "STAT;",
        )

    def test_stat_axis_value_too_many_values(self):  # STAT AxisValue
        self.assertRaisesRegex(
            FeatureLibError,
            "Expected 1, 2 or 3 values for axis opsz, but 4 were found.",
            self.parse,
            "table STAT { DesignAxis opsz 0 "
            '{name "Optical Size";}; '
            'AxisValue {location opsz 8 6 10 12; name "Caption";}; } '
            "STAT;",
        )

    def test_stat_axis_value_no_values(self):  # STAT AxisValue
        self.assertRaisesRegex(
            FeatureLibError,
            "Expected 1, 2 or 3 values for axis opsz, but 0 were found.",
            self.parse,
            "table STAT { DesignAxis opsz 0 "
            '{name "Optical Size";}; '
            'AxisValue {location opsz; name "Caption";}; } '
            "STAT;",
        )

    def test_stat_axis_value_format4(self):  # STAT AxisValue
        self.assertRaisesRegex(
            FeatureLibError,
            "Only one value is allowed in a Format 4 Axis Value Record, but 3 were found.",
            self.parse,
            "table STAT { "
            'DesignAxis opsz 0 {name "Optical Size";}; '
            'DesignAxis wdth 0 {name "Width";}; '
            "AxisValue {"
            "location opsz 8 6 10; "
            "location wdth 400; "
            'name "Caption";}; } '
            "STAT;",
        )

    def test_stat_elidedfallbackname(self):  # STAT ElidedFallbackName
        doc = self.parse(
            'table STAT { ElidedFallbackName {name "Roman"; '
            'name 3 1 0x0411 "ローマン"; }; '
            "} STAT;"
        )
        nameRecord = doc.statements[0].statements[0]
        self.assertIsInstance(nameRecord, ast.ElidedFallbackName)
        self.assertEqual(nameRecord.names[0].string, "Roman")
        self.assertEqual(nameRecord.names[1].string, "ローマン")

    def test_stat_elidedfallbacknameid(self):  # STAT ElidedFallbackNameID
        doc = self.parse(
            'table name { nameid 278 "Roman"; } name; '
            "table STAT { ElidedFallbackNameID 278; "
            "} STAT;"
        )
        nameRecord = doc.statements[0].statements[0]
        self.assertIsInstance(nameRecord, ast.NameRecord)
        self.assertEqual(nameRecord.string, "Roman")

    def test_sub_single_format_a(self):  # GSUB LookupType 1
        doc = self.parse("feature smcp {substitute a by a.sc;} smcp;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.SingleSubstStatement)
        self.assertEqual(glyphstr(sub.prefix), "")
        self.assertEqual(mapping(sub), {"a": "a.sc"})
        self.assertEqual(glyphstr(sub.suffix), "")

    def test_sub_single_format_a_chained(self):  # chain to GSUB LookupType 1
        doc = self.parse("feature test {sub [A a] d' [C] by d.alt;} test;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.SingleSubstStatement)
        self.assertEqual(mapping(sub), {"d": "d.alt"})
        self.assertEqual(glyphstr(sub.prefix), "[A a]")
        self.assertEqual(glyphstr(sub.suffix), "C")

    def test_sub_single_format_a_cid(self):  # GSUB LookupType 1
        doc = self.parse(r"feature smcp {substitute \12345 by \78987;} smcp;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.SingleSubstStatement)
        self.assertEqual(glyphstr(sub.prefix), "")
        self.assertEqual(mapping(sub), {"cid12345": "cid78987"})
        self.assertEqual(glyphstr(sub.suffix), "")

    def test_sub_single_format_b(self):  # GSUB LookupType 1
        doc = self.parse(
            "feature smcp {"
            "    substitute [one.fitted one.oldstyle] by one;"
            "} smcp;"
        )
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.SingleSubstStatement)
        self.assertEqual(mapping(sub), {"one.fitted": "one", "one.oldstyle": "one"})
        self.assertEqual(glyphstr(sub.prefix), "")
        self.assertEqual(glyphstr(sub.suffix), "")

    def test_sub_single_format_b_chained(self):  # chain to GSUB LookupType 1
        doc = self.parse(
            "feature smcp {"
            "    substitute PRE FIX [one.fitted one.oldstyle]' SUF FIX by one;"
            "} smcp;"
        )
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.SingleSubstStatement)
        self.assertEqual(mapping(sub), {"one.fitted": "one", "one.oldstyle": "one"})
        self.assertEqual(glyphstr(sub.prefix), "PRE FIX")
        self.assertEqual(glyphstr(sub.suffix), "SUF FIX")

    def test_sub_single_format_c(self):  # GSUB LookupType 1
        doc = self.parse(
            "feature smcp {" "    substitute [a-d] by [A.sc-D.sc];" "} smcp;"
        )
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.SingleSubstStatement)
        self.assertEqual(
            mapping(sub), {"a": "A.sc", "b": "B.sc", "c": "C.sc", "d": "D.sc"}
        )
        self.assertEqual(glyphstr(sub.prefix), "")
        self.assertEqual(glyphstr(sub.suffix), "")

    def test_sub_single_format_c_chained(self):  # chain to GSUB LookupType 1
        doc = self.parse(
            "feature smcp {" "    substitute [a-d]' X Y [Z z] by [A.sc-D.sc];" "} smcp;"
        )
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.SingleSubstStatement)
        self.assertEqual(
            mapping(sub), {"a": "A.sc", "b": "B.sc", "c": "C.sc", "d": "D.sc"}
        )
        self.assertEqual(glyphstr(sub.prefix), "")
        self.assertEqual(glyphstr(sub.suffix), "X Y [Z z]")

    def test_sub_single_format_c_different_num_elements(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Expected a glyph class with 4 elements after "by", '
            "but found a glyph class with 26 elements",
            self.parse,
            "feature smcp {sub [a-d] by [A.sc-Z.sc];} smcp;",
        )

    def test_sub_with_values(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Substitution statements cannot contain values",
            self.parse,
            "feature smcp {sub A' 20 by A.sc;} smcp;",
        )

    def test_substitute_multiple(self):  # GSUB LookupType 2
        doc = self.parse("lookup Look {substitute f_f_i by f f i;} Look;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.MultipleSubstStatement)
        self.assertEqual(glyphstr([sub.glyph]), "f_f_i")
        self.assertEqual(glyphstr(sub.replacement), "f f i")

    def test_substitute_multiple_chained(self):  # chain to GSUB LookupType 2
        doc = self.parse("lookup L {sub [A-C] f_f_i' [X-Z] by f f i;} L;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.MultipleSubstStatement)
        self.assertEqual(glyphstr([sub.glyph]), "f_f_i")
        self.assertEqual(glyphstr(sub.replacement), "f f i")

    def test_substitute_multiple_force_chained(self):
        doc = self.parse("lookup L {sub f_f_i' by f f i;} L;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.MultipleSubstStatement)
        self.assertEqual(glyphstr([sub.glyph]), "f_f_i")
        self.assertEqual(glyphstr(sub.replacement), "f f i")
        self.assertEqual(sub.asFea(), "sub f_f_i' by f f i;")

    def test_substitute_multiple_classes(self):
        doc = self.parse("lookup Look {substitute [f_i f_l] by [f f] [i l];} Look;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.MultipleSubstStatement)
        self.assertEqual(glyphstr([sub.glyph]), "[f_i f_l]")
        self.assertEqual(glyphstr(sub.replacement), "[f f] [i l]")

    def test_substitute_multiple_classes_mixed(self):
        doc = self.parse("lookup Look {substitute [f_i f_l] by f [i l];} Look;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.MultipleSubstStatement)
        self.assertEqual(glyphstr([sub.glyph]), "[f_i f_l]")
        self.assertEqual(glyphstr(sub.replacement), "f [i l]")

    def test_substitute_multiple_classes_mixed_singleton(self):
        doc = self.parse("lookup Look {substitute [f_i f_l] by [f] [i l];} Look;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.MultipleSubstStatement)
        self.assertEqual(glyphstr([sub.glyph]), "[f_i f_l]")
        self.assertEqual(glyphstr(sub.replacement), "f [i l]")

    def test_substitute_multiple_classes_mismatch(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Expected a glyph class with 1 or 3 elements after "by", '
            "but found a glyph class with 2 elements",
            self.parse,
            "lookup Look {substitute [f_i f_l f_f_i] by [f f_f] [i l i];} Look;",
        )

    def test_substitute_multiple_by_mutliple(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Direct substitution of multiple glyphs by multiple glyphs "
            "is not supported",
            self.parse,
            "lookup MxM {sub a b c by d e f;} MxM;",
        )

    def test_split_marked_glyphs_runs(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Unsupported contextual target sequence",
            self.parse,
            "feature test{" "    ignore pos a' x x A';" "} test;",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            "Unsupported contextual target sequence",
            self.parse,
            "lookup shift {"
            "    pos a <0 -10 0 0>;"
            "    pos A <0 10 0 0>;"
            "} shift;"
            "feature test {"
            "    sub a' lookup shift x x A' lookup shift;"
            "} test;",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            "Unsupported contextual target sequence",
            self.parse,
            "feature test {" "    ignore sub a' x x A';" "} test;",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            "Unsupported contextual target sequence",
            self.parse,
            "lookup upper {"
            "    sub a by A;"
            "} upper;"
            "lookup lower {"
            "    sub A by a;"
            "} lower;"
            "feature test {"
            "    sub a' lookup upper x x A' lookup lower;"
            "} test;",
        )

    def test_substitute_from(self):  # GSUB LookupType 3
        doc = self.parse(
            "feature test {" "  substitute a from [a.1 a.2 a.3];" "} test;"
        )
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.AlternateSubstStatement)
        self.assertEqual(glyphstr(sub.prefix), "")
        self.assertEqual(glyphstr([sub.glyph]), "a")
        self.assertEqual(glyphstr(sub.suffix), "")
        self.assertEqual(glyphstr([sub.replacement]), "[a.1 a.2 a.3]")

    def test_substitute_from_chained(self):  # chain to GSUB LookupType 3
        doc = self.parse(
            "feature test {" "  substitute A B a' [Y y] Z from [a.1 a.2 a.3];" "} test;"
        )
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.AlternateSubstStatement)
        self.assertEqual(glyphstr(sub.prefix), "A B")
        self.assertEqual(glyphstr([sub.glyph]), "a")
        self.assertEqual(glyphstr(sub.suffix), "[Y y] Z")
        self.assertEqual(glyphstr([sub.replacement]), "[a.1 a.2 a.3]")

    def test_substitute_from_cid(self):  # GSUB LookupType 3
        doc = self.parse(
            r"feature test {" r"  substitute \7 from [\111 \222];" r"} test;"
        )
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.AlternateSubstStatement)
        self.assertEqual(glyphstr(sub.prefix), "")
        self.assertEqual(glyphstr([sub.glyph]), "cid00007")
        self.assertEqual(glyphstr(sub.suffix), "")
        self.assertEqual(glyphstr([sub.replacement]), "[cid00111 cid00222]")

    def test_substitute_from_glyphclass(self):  # GSUB LookupType 3
        doc = self.parse(
            "feature test {"
            "  @Ampersands = [ampersand.1 ampersand.2];"
            "  substitute ampersand from @Ampersands;"
            "} test;"
        )
        [glyphclass, sub] = doc.statements[0].statements
        self.assertIsInstance(sub, ast.AlternateSubstStatement)
        self.assertEqual(glyphstr(sub.prefix), "")
        self.assertEqual(glyphstr([sub.glyph]), "ampersand")
        self.assertEqual(glyphstr(sub.suffix), "")
        self.assertEqual(glyphstr([sub.replacement]), "[ampersand.1 ampersand.2]")

    def test_substitute_ligature(self):  # GSUB LookupType 4
        doc = self.parse("feature liga {substitute f f i by f_f_i;} liga;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.LigatureSubstStatement)
        self.assertEqual(glyphstr(sub.glyphs), "f f i")
        self.assertEqual(sub.replacement, "f_f_i")
        self.assertEqual(glyphstr(sub.prefix), "")
        self.assertEqual(glyphstr(sub.suffix), "")

    def test_substitute_ligature_chained(self):  # chain to GSUB LookupType 4
        doc = self.parse("feature F {substitute A B f' i' Z by f_i;} F;")
        sub = doc.statements[0].statements[0]
        self.assertIsInstance(sub, ast.LigatureSubstStatement)
        self.assertEqual(glyphstr(sub.glyphs), "f i")
        self.assertEqual(sub.replacement, "f_i")
        self.assertEqual(glyphstr(sub.prefix), "A B")
        self.assertEqual(glyphstr(sub.suffix), "Z")

    def test_substitute_lookups(self):  # GSUB LookupType 6
        doc = Parser(self.getpath("spec5fi1.fea"), GLYPHNAMES).parse()
        [_, _, _, langsys, ligs, sub, feature] = doc.statements
        self.assertEqual(feature.statements[0].lookups, [[ligs], None, [sub]])
        self.assertEqual(feature.statements[1].lookups, [[ligs], None, [sub]])

    def test_substitute_missing_by(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Expected "by", "from" or explicit lookup references',
            self.parse,
            "feature liga {substitute f f i;} liga;",
        )

    def test_substitute_invalid_statement(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Invalid substitution statement",
            Parser(self.getpath("GSUB_error.fea"), GLYPHNAMES).parse,
        )

    def test_subtable(self):
        doc = self.parse("feature test {subtable;} test;")
        s = doc.statements[0].statements[0]
        self.assertIsInstance(s, ast.SubtableStatement)

    def test_table_BASE_script_list_without_tag_list(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "BaseScriptList must be preceded by BaseTagList",
            self.parse,
            "table BASE { HorizAxis.BaseScriptList latn romn 0; } BASE;",
        )

    def test_table_BASE_default_baseline_not_in_tag_list(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Default baseline "ideo" is not in BaseTagList',
            self.parse,
            "table BASE {"
            "    VertAxis.BaseTagList romn;"
            "    VertAxis.BaseScriptList latn ideo 0;"
            "} BASE;",
        )

    def test_table_unclosed(self):
        for table, statement in {
            "OS/2": "WeightClass 400;",
            "BASE": "HorizAxis.BaseTagList romn;",
            "STAT": "ElidedFallbackNameID 2;",
        }.items():
            for text in ("", statement, statement + " # comment"):
                with self.subTest(table=table, text=text):
                    self.assertRaisesRegex(
                        FeatureLibError,
                        "Expected '}'",
                        self.parse,
                        "table %s { %s" % (table, text),
                    )

    def test_table_OS_2_vendor_not_ascii(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Vendor ID must be ASCII",
            self.parse,
            'table OS/2 { Vendor "\u00e9\u00e9"; } OS/2;',
        )

    def test_table_OS_2_unicode_range_bit_out_of_range(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "UnicodeRange bits must be between 0 and 127",
            self.parse,
            "table OS/2 { UnicodeRange 0 200; } OS/2;",
        )

    def test_table_badEnd(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Expected "GDEF"',
            self.parse,
            "table GDEF {LigatureCaretByPos f_i 400;} ABCD;",
        )

    def test_table_comment(self):
        for table in "BASE GDEF OS/2 head hhea name vhea".split():
            doc = self.parse("table %s { # Comment\n } %s;" % (table, table))
            comment = doc.statements[0].statements[0]
            self.assertIsInstance(comment, ast.Comment)
            self.assertEqual(comment.text, "# Comment")

    def test_table_unsupported(self):
        self.assertRaisesRegex(
            FeatureLibError,
            '"table Foo" is not supported',
            self.parse,
            "table Foo {LigatureCaretByPos f_i 400;} Foo;",
        )

    def test_valuerecord_format_a_horizontal(self):
        doc = self.parse("feature liga {valueRecordDef 123 foo;} liga;")
        valuedef = doc.statements[0].statements[0]
        value = valuedef.value
        self.assertIsNone(value.xPlacement)
        self.assertIsNone(value.yPlacement)
        self.assertEqual(value.xAdvance, 123)
        self.assertIsNone(value.yAdvance)
        self.assertIsNone(value.xPlaDevice)
        self.assertIsNone(value.yPlaDevice)
        self.assertIsNone(value.xAdvDevice)
        self.assertIsNone(value.yAdvDevice)
        self.assertEqual(valuedef.asFea(), "valueRecordDef 123 foo;")
        self.assertEqual(value.asFea(), "123")

    def test_valuerecord_format_a_vertical(self):
        doc = self.parse("feature vkrn {valueRecordDef 123 foo;} vkrn;")
        valuedef = doc.statements[0].statements[0]
        value = valuedef.value
        self.assertIsNone(value.xPlacement)
        self.assertIsNone(value.yPlacement)
        self.assertIsNone(value.xAdvance)
        self.assertEqual(value.yAdvance, 123)
        self.assertIsNone(value.xPlaDevice)
        self.assertIsNone(value.yPlaDevice)
        self.assertIsNone(value.xAdvDevice)
        self.assertIsNone(value.yAdvDevice)
        self.assertEqual(valuedef.asFea(), "valueRecordDef 123 foo;")
        self.assertEqual(value.asFea(), "123")

    def test_valuerecord_format_a_zero_horizontal(self):
        doc = self.parse("feature liga {valueRecordDef 0 foo;} liga;")
        valuedef = doc.statements[0].statements[0]
        value = valuedef.value
        self.assertIsNone(value.xPlacement)
        self.assertIsNone(value.yPlacement)
        self.assertEqual(value.xAdvance, 0)
        self.assertIsNone(value.yAdvance)
        self.assertIsNone(value.xPlaDevice)
        self.assertIsNone(value.yPlaDevice)
        self.assertIsNone(value.xAdvDevice)
        self.assertIsNone(value.yAdvDevice)
        self.assertEqual(valuedef.asFea(), "valueRecordDef 0 foo;")
        self.assertEqual(value.asFea(), "0")

    def test_valuerecord_format_a_zero_vertical(self):
        doc = self.parse("feature vkrn {valueRecordDef 0 foo;} vkrn;")
        valuedef = doc.statements[0].statements[0]
        value = valuedef.value
        self.assertIsNone(value.xPlacement)
        self.assertIsNone(value.yPlacement)
        self.assertIsNone(value.xAdvance)
        self.assertEqual(value.yAdvance, 0)
        self.assertIsNone(value.xPlaDevice)
        self.assertIsNone(value.yPlaDevice)
        self.assertIsNone(value.xAdvDevice)
        self.assertIsNone(value.yAdvDevice)
        self.assertEqual(valuedef.asFea(), "valueRecordDef 0 foo;")
        self.assertEqual(value.asFea(), "0")

    def test_valuerecord_format_a_vertical_contexts_(self):
        for tag in "vkrn vpal vhal valt".split():
            doc = self.parse("feature %s {valueRecordDef 77 foo;} %s;" % (tag, tag))
            value = doc.statements[0].statements[0].value
            if value.yAdvance != 77:
                self.fail(
                    msg="feature %s should be a vertical context "
                    "for ValueRecord format A" % tag
                )

    def test_valuerecord_format_b(self):
        doc = self.parse("feature liga {valueRecordDef <1 2 3 4> foo;} liga;")
        valuedef = doc.statements[0].statements[0]
        value = valuedef.value
        self.assertEqual(value.xPlacement, 1)
        self.assertEqual(value.yPlacement, 2)
        self.assertEqual(value.xAdvance, 3)
        self.assertEqual(value.yAdvance, 4)
        self.assertIsNone(value.xPlaDevice)
        self.assertIsNone(value.yPlaDevice)
        self.assertIsNone(value.xAdvDevice)
        self.assertIsNone(value.yAdvDevice)
        self.assertEqual(valuedef.asFea(), "valueRecordDef <1 2 3 4> foo;")
        self.assertEqual(value.asFea(), "<1 2 3 4>")

    def test_valuerecord_format_b_zero(self):
        doc = self.parse("feature liga {valueRecordDef <0 0 0 0> foo;} liga;")
        valuedef = doc.statements[0].statements[0]
        value = valuedef.value
        self.assertEqual(value.xPlacement, 0)
        self.assertEqual(value.yPlacement, 0)
        self.assertEqual(value.xAdvance, 0)
        self.assertEqual(value.yAdvance, 0)
        self.assertIsNone(value.xPlaDevice)
        self.assertIsNone(value.yPlaDevice)
        self.assertIsNone(value.xAdvDevice)
        self.assertIsNone(value.yAdvDevice)
        self.assertEqual(valuedef.asFea(), "valueRecordDef <0 0 0 0> foo;")
        self.assertEqual(value.asFea(), "<0 0 0 0>")

    def test_valuerecord_format_c(self):
        doc = self.parse(
            "feature liga {"
            "    valueRecordDef <"
            "        1 2 3 4"
            "        <device 8 88>"
            "        <device 11 111, 12 112>"
            "        <device NULL>"
            "        <device 33 -113, 44 -114, 55 115>"
            "    > foo;"
            "} liga;"
        )
        value = doc.statements[0].statements[0].value
        self.assertEqual(value.xPlacement, 1)
        self.assertEqual(value.yPlacement, 2)
        self.assertEqual(value.xAdvance, 3)
        self.assertEqual(value.yAdvance, 4)
        self.assertEqual(value.xPlaDevice, ((8, 88),))
        self.assertEqual(value.yPlaDevice, ((11, 111), (12, 112)))
        self.assertIsNone(value.xAdvDevice)
        self.assertEqual(value.yAdvDevice, ((33, -113), (44, -114), (55, 115)))
        self.assertEqual(
            value.asFea(),
            "<1 2 3 4 <device 8 88> <device 11 111, 12 112>"
            " <device NULL> <device 33 -113, 44 -114, 55 115>>",
        )

    def test_valuerecord_format_c_all_devices_null(self):
        doc = self.parse(
            "feature test {"
            "    valueRecordDef <-80 0 -160 0"
            "        <device NULL> <device NULL> <device NULL> <device NULL>> foo;"
            "} test;"
        )
        value = doc.statements[0].statements[0].value
        self.assertEqual(value.xPlacement, -80)
        self.assertEqual(value.yPlacement, 0)
        self.assertEqual(value.xAdvance, -160)
        self.assertEqual(value.yAdvance, 0)
        self.assertIsNone(value.xPlaDevice)
        self.assertIsNone(value.yPlaDevice)
        self.assertIsNone(value.xAdvDevice)
        self.assertIsNone(value.yAdvDevice)
        self.assertEqual(value.asFea(), "<-80 0 -160 0>")

    def test_valuerecord_format_d(self):
        doc = self.parse("feature test {valueRecordDef <NULL> foo;} test;")
        value = doc.statements[0].statements[0].value
        self.assertFalse(value)
        self.assertEqual(value.asFea(), "<NULL>")

    def test_valuerecord_variable_scalar(self):
        doc = self.parse(
            "feature test {valueRecordDef <0 (wght=200:-100 wght=900:-150 wdth=150,wght=900:-120) 0 0> foo;} test;"
        )
        value = doc.statements[0].statements[0].value
        self.assertEqual(
            value.asFea(),
            "<0 (wght=200:-100 wght=900:-150 wdth=150,wght=900:-120) 0 0>",
        )

    def test_valuerecord_named(self):
        doc = self.parse(
            "valueRecordDef <1 2 3 4> foo;"
            "feature liga {valueRecordDef <foo> bar;} liga;"
        )
        value = doc.statements[1].statements[0].value
        self.assertEqual(value.xPlacement, 1)
        self.assertEqual(value.yPlacement, 2)
        self.assertEqual(value.xAdvance, 3)
        self.assertEqual(value.yAdvance, 4)

    def test_valuerecord_named_unknown(self):
        self.assertRaisesRegex(
            FeatureLibError,
            'Unknown valueRecordDef "unknown"',
            self.parse,
            "valueRecordDef <unknown> foo;",
        )

    def test_valuerecord_scoping(self):
        [foo, liga, smcp] = self.parse(
            "valueRecordDef 789 foo;"
            "feature liga {valueRecordDef <foo> bar;} liga;"
            "feature smcp {valueRecordDef <foo> bar;} smcp;"
        ).statements
        self.assertEqual(foo.value.xAdvance, 789)
        self.assertEqual(liga.statements[0].value.xAdvance, 789)
        self.assertEqual(smcp.statements[0].value.xAdvance, 789)

    def test_valuerecord_device_value_out_of_range(self):
        self.assertRaisesRegex(
            FeatureLibError,
            r"Device value out of valid range \(-128..127\)",
            self.parse,
            "valueRecordDef <1 2 3 4 <device NULL> <device NULL> "
            "<device NULL> <device 11 128>> foo;",
        )

    def test_conditionset(self):
        doc = self.parse("conditionset heavy { wght 700 900; } heavy;")
        value = doc.statements[0]
        self.assertEqual(value.conditions["wght"], (700, 900))
        self.assertEqual(
            value.asFea(), "conditionset heavy {\n    wght 700 900;\n} heavy;\n"
        )

        doc = self.parse("conditionset heavy { wght 700 900; opsz 17 18;} heavy;")
        value = doc.statements[0]
        self.assertEqual(value.conditions["wght"], (700, 900))
        self.assertEqual(value.conditions["opsz"], (17, 18))
        self.assertEqual(
            value.asFea(),
            "conditionset heavy {\n    wght 700 900;\n    opsz 17 18;\n} heavy;\n",
        )

    def test_conditionset_same_axis(self):
        self.assertRaisesRegex(
            FeatureLibError,
            r"Repeated condition for axis wght",
            self.parse,
            "conditionset heavy { wght 700 900; wght 100 200; } heavy;",
        )

    def test_conditionset_float(self):
        doc = self.parse("conditionset heavy { wght 700.0 900.0; } heavy;")
        value = doc.statements[0]
        self.assertEqual(value.conditions["wght"], (700.0, 900.0))
        self.assertEqual(
            value.asFea(), "conditionset heavy {\n    wght 700.0 900.0;\n} heavy;\n"
        )

    def test_variation(self):
        doc = self.parse("variation rvrn heavy { sub a by b; } rvrn;")
        value = doc.statements[0]

    def test_languagesystem(self):
        [langsys] = self.parse("languagesystem latn DEU;").statements
        self.assertEqual(langsys.script, "latn")
        self.assertEqual(langsys.language, "DEU ")
        [langsys] = self.parse("languagesystem DFLT DEU;").statements
        self.assertEqual(langsys.script, "DFLT")
        self.assertEqual(langsys.language, "DEU ")
        self.assertRaisesRegex(
            FeatureLibError,
            '"dflt" is not a valid script tag; use "DFLT" instead',
            self.parse,
            "languagesystem dflt dflt;",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            '"DFLT" is not a valid language tag; use "dflt" instead',
            self.parse,
            "languagesystem latn DFLT;",
        )
        self.assertRaisesRegex(
            FeatureLibError, "Expected ';'", self.parse, "languagesystem latn DEU"
        )
        self.assertRaisesRegex(
            FeatureLibError,
            "longer than 4 characters",
            self.parse,
            "languagesystem foobar DEU;",
        )
        self.assertRaisesRegex(
            FeatureLibError,
            "longer than 4 characters",
            self.parse,
            "languagesystem latn FOOBAR;",
        )

    def test_empty_statement_ignored(self):
        doc = self.parse("feature test {;} test;")
        self.assertFalse(doc.statements[0].statements)
        doc = self.parse(";;;")
        self.assertFalse(doc.statements)
        for table in "BASE GDEF OS/2 head hhea name vhea".split():
            doc = self.parse("table %s { ;;; } %s;" % (table, table))
            self.assertEqual(doc.statements[0].statements, [])

    def test_ufo_features_parse_include_dir(self):
        fea_path = self.getpath("include/test.ufo/features.fea")
        include_dir = os.path.dirname(os.path.dirname(fea_path))
        doc = Parser(fea_path, includeDir=include_dir).parse()
        assert len(doc.statements) == 1 and doc.statements[0].text == "# Nothing"

    def test_unmarked_ignore_statement(self):
        with CapturingLogHandler("fontTools.feaLib.parser", level="WARNING") as caplog:
            doc = self.parse("lookup foo { ignore sub A; } foo;")
        self.assertEqual(doc.statements[0].statements[0].asFea(), "ignore sub A';")
        self.assertEqual(len(caplog.records), 1)
        caplog.assertRegex(
            'Ambiguous "ignore sub", there should be least one marked glyph'
        )

    def test_variable_scalar_default(self):
        doc = self.parse(
            "feature test {valueRecordDef <0 (100 wght=200:-100 wght=900:-150 wdth=150,wght=900:-120) 0 0> foo;} test;"
        )
        value = doc.statements[0].statements[0].value
        self.assertEqual(
            value.asFea(),
            "<0 (100 wght=200:-100 wght=900:-150 wdth=150,wght=900:-120) 0 0>",
        )

    def test_variable_scalar_duplicate_bare_value(self):
        self.assertRaisesRegex(
            FeatureLibError,
            "Duplicate value for the default location",
            self.parse,
            "feature test {pos a (10 20 wght=900:30);} test",
        )

    def parse(self, text, glyphNames=GLYPHNAMES, followIncludes=True):
        featurefile = StringIO(text)
        p = Parser(featurefile, glyphNames, followIncludes=followIncludes)
        return p.parse()

    @staticmethod
    def getpath(testfile):
        path, _ = os.path.split(__file__)
        return os.path.join(path, "data", testfile)


class SymbolTableTest(unittest.TestCase):
    def test_scopes(self):
        symtab = SymbolTable()
        symtab.define("foo", 23)
        self.assertEqual(symtab.resolve("foo"), 23)
        symtab.enter_scope()
        self.assertEqual(symtab.resolve("foo"), 23)
        symtab.define("foo", 42)
        self.assertEqual(symtab.resolve("foo"), 42)
        symtab.exit_scope()
        self.assertEqual(symtab.resolve("foo"), 23)

    def test_resolve_undefined(self):
        self.assertEqual(SymbolTable().resolve("abc"), None)


if __name__ == "__main__":
    import sys

    sys.exit(unittest.main())
