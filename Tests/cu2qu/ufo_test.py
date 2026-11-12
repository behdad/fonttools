import os

from fontTools.misc.loggingTools import CapturingLogHandler
from fontTools.cu2qu.ufo import (
    fonts_to_quadratic,
    font_to_quadratic,
    glyphs_to_quadratic,
    glyph_to_quadratic,
    logger,
    CURVE_TYPE_LIB_KEY,
)
from fontTools.cu2qu.errors import (
    IncompatibleSegmentNumberError,
    IncompatibleSegmentTypesError,
    IncompatibleFontsError,
)

import pytest

ufoLib2 = pytest.importorskip("ufoLib2")

DATADIR = os.path.join(os.path.dirname(__file__), "data")

TEST_UFOS = [
    os.path.join(DATADIR, "RobotoSubset-Regular.ufo"),
    os.path.join(DATADIR, "RobotoSubset-Bold.ufo"),
]


@pytest.fixture
def fonts():
    return [ufoLib2.Font.open(ufo) for ufo in TEST_UFOS]


class FontsToQuadraticTest(object):
    def test_modified(self, fonts):
        # previously this method returned True/False, now it returns a set of modified
        # glyph names.
        modified = fonts_to_quadratic(fonts)
        # the first assertion continues to work whether the return value is a bool/set
        # so the change is backward compatible
        assert modified
        assert len(modified) > 0
        assert "B" in modified

    def test_stats(self, fonts):
        stats = {}
        fonts_to_quadratic(fonts, stats=stats)
        assert stats == {"1": 1, "2": 79, "3": 130, "4": 2}

    def test_dump_stats(self, fonts):
        with CapturingLogHandler(logger, "INFO") as captor:
            fonts_to_quadratic(fonts, dump_stats=True)
        assert captor.assertRegex("New spline lengths:")

    def test_remember_curve_type_quadratic(self, fonts):
        fonts_to_quadratic(fonts, remember_curve_type=True)
        assert fonts[0].lib[CURVE_TYPE_LIB_KEY] == "quadratic"
        with CapturingLogHandler(logger, "INFO") as captor:
            fonts_to_quadratic(fonts, remember_curve_type=True)
        assert captor.assertRegex("already converted")

    def test_remember_curve_type_mixed(self, fonts):
        fonts_to_quadratic(fonts, remember_curve_type=True, all_quadratic=False)
        assert fonts[0].lib[CURVE_TYPE_LIB_KEY] == "mixed"
        with CapturingLogHandler(logger, "INFO") as captor:
            fonts_to_quadratic(fonts, remember_curve_type=True)
        assert captor.assertRegex("already converted")

    def test_no_remember_curve_type(self, fonts):
        assert CURVE_TYPE_LIB_KEY not in fonts[0].lib
        fonts_to_quadratic(fonts, remember_curve_type=False)
        assert CURVE_TYPE_LIB_KEY not in fonts[0].lib

    def test_different_glyphsets(self, fonts):
        del fonts[0]["a"]
        assert "a" not in fonts[0]
        assert "a" in fonts[1]
        assert fonts_to_quadratic(fonts)

    def test_max_err_em_float(self, fonts):
        stats = {}
        fonts_to_quadratic(fonts, max_err_em=0.002, stats=stats)
        assert stats == {"1": 5, "2": 193, "3": 14}

    def test_max_err_em_list(self, fonts):
        stats = {}
        fonts_to_quadratic(fonts, max_err_em=[0.002, 0.002], stats=stats)
        assert stats == {"1": 5, "2": 193, "3": 14}

    def test_max_err_float(self, fonts):
        stats = {}
        fonts_to_quadratic(fonts, max_err=4.096, stats=stats)
        assert stats == {"1": 5, "2": 193, "3": 14}

    def test_max_err_list(self, fonts):
        stats = {}
        fonts_to_quadratic(fonts, max_err=[4.096, 4.096], stats=stats)
        assert stats == {"1": 5, "2": 193, "3": 14}

    @pytest.mark.parametrize("kwargs", [{"max_err": 0}, {"max_err_em": 0}])
    def test_reject_zero_tolerance(self, fonts, kwargs):
        with pytest.raises(ValueError, match="must be greater than zero"):
            fonts_to_quadratic(fonts, **kwargs)

    @pytest.mark.parametrize(
        "kwargs",
        [{"max_err": [1]}, {"max_err_em": [0.001]}],
    )
    def test_reject_mismatched_tolerance_list_lengths(self, fonts, kwargs):
        with pytest.raises(ValueError, match="must match the number of inputs"):
            fonts_to_quadratic(fonts, **kwargs)

    def test_both_max_err_and_max_err_em(self, fonts):
        with pytest.raises(TypeError, match="Only one .* can be specified"):
            fonts_to_quadratic(fonts, max_err=1.000, max_err_em=0.001)

    def test_single_font(self, fonts):
        assert font_to_quadratic(fonts[0], max_err_em=0.002, reverse_direction=True)
        assert font_to_quadratic(
            fonts[1], max_err_em=0.002, reverse_direction=True, all_quadratic=False
        )


class GlyphsToQuadraticTest(object):
    @pytest.mark.parametrize(
        ["glyph", "expected"],
        [("A", False), ("a", True)],  # contains no curves, it is not modified
        ids=["lines-only", "has-curves"],
    )
    def test_modified(self, fonts, glyph, expected):
        glyphs = [f[glyph] for f in fonts]
        assert glyphs_to_quadratic(glyphs) == expected

    def test_stats(self, fonts):
        stats = {}
        glyphs_to_quadratic([f["a"] for f in fonts], stats=stats)
        assert stats == {"2": 1, "3": 7, "4": 3, "5": 1}

    def test_max_err_float(self, fonts):
        glyphs = [f["a"] for f in fonts]
        stats = {}
        glyphs_to_quadratic(glyphs, max_err=4.096, stats=stats)
        assert stats == {"2": 11, "3": 1}

    def test_max_err_list(self, fonts):
        glyphs = [f["a"] for f in fonts]
        stats = {}
        glyphs_to_quadratic(glyphs, max_err=[4.096, 4.096], stats=stats)
        assert stats == {"2": 11, "3": 1}

    def test_reject_zero_tolerance(self, fonts):
        glyphs = [f["a"] for f in fonts]
        with pytest.raises(ValueError, match="must be greater than zero"):
            glyphs_to_quadratic(glyphs, max_err=0)

    def test_reject_mismatched_tolerance_list_lengths(self, fonts):
        glyphs = [f["a"] for f in fonts]
        with pytest.raises(ValueError, match="must match the number of inputs"):
            glyphs_to_quadratic(glyphs, max_err=[4.096])

    def test_reverse_direction(self, fonts):
        glyphs = [f["A"] for f in fonts]
        assert glyphs_to_quadratic(glyphs, reverse_direction=True)

    def test_single_glyph(self, fonts):
        assert glyph_to_quadratic(fonts[0]["a"], max_err=4.096, reverse_direction=True)

    @pytest.mark.parametrize(
        ["outlines", "exception", "message"],
        [
            [
                [
                    [
                        ("moveTo", ((0, 0),)),
                        ("curveTo", ((1, 1), (2, 2), (3, 3))),
                        ("curveTo", ((4, 4), (5, 5), (6, 6))),
                        ("closePath", ()),
                    ],
                    [
                        ("moveTo", ((7, 7),)),
                        ("curveTo", ((8, 8), (9, 9), (10, 10))),
                        ("closePath", ()),
                    ],
                ],
                IncompatibleSegmentNumberError,
                "have different number of segments",
            ],
            [
                [
                    [
                        ("moveTo", ((0, 0),)),
                        ("curveTo", ((1, 1), (2, 2), (3, 3))),
                        ("closePath", ()),
                    ],
                    [
                        ("moveTo", ((4, 4),)),
                        ("lineTo", ((5, 5),)),
                        ("closePath", ()),
                    ],
                ],
                IncompatibleSegmentTypesError,
                "have incompatible segment types",
            ],
        ],
        ids=[
            "unequal-length",
            "different-segment-types",
        ],
    )
    def test_incompatible_glyphs(self, outlines, exception, message):
        glyphs = []
        for i, outline in enumerate(outlines):
            glyph = ufoLib2.objects.Glyph("glyph%d" % i)
            pen = glyph.getPen()
            for operator, args in outline:
                getattr(pen, operator)(*args)
            glyphs.append(glyph)
        with pytest.raises(exception) as excinfo:
            glyphs_to_quadratic(glyphs)
        assert excinfo.match(message)

    def test_incompatible_fonts(self):
        font1 = ufoLib2.Font()
        font1.info.unitsPerEm = 1000
        glyph1 = font1.newGlyph("a")
        pen1 = glyph1.getPen()
        for operator, args in [
            ("moveTo", ((0, 0),)),
            ("lineTo", ((1, 1),)),
            ("endPath", ()),
        ]:
            getattr(pen1, operator)(*args)

        font2 = ufoLib2.Font()
        font2.info.unitsPerEm = 1000
        glyph2 = font2.newGlyph("a")
        pen2 = glyph2.getPen()
        for operator, args in [
            ("moveTo", ((0, 0),)),
            ("curveTo", ((1, 1), (2, 2), (3, 3))),
            ("endPath", ()),
        ]:
            getattr(pen2, operator)(*args)

        with pytest.raises(IncompatibleFontsError) as excinfo:
            fonts_to_quadratic([font1, font2])
        assert excinfo.match("fonts contains incompatible glyphs: 'a'")

        assert hasattr(excinfo.value, "glyph_errors")
        error = excinfo.value.glyph_errors["a"]
        assert isinstance(error, IncompatibleSegmentTypesError)
        assert error.segments == {1: ["line", "curve"]}

    def test_already_quadratic(self):
        glyph = ufoLib2.objects.Glyph()
        pen = glyph.getPen()
        pen.moveTo((0, 0))
        pen.qCurveTo((1, 1), (2, 2))
        pen.closePath()
        assert not glyph_to_quadratic(glyph)

    def test_mixed_curves_kept_cubic_not_modified(self):
        glyph = ufoLib2.objects.Glyph()
        pen = glyph.getPen()
        pen.moveTo((0, 0))
        pen.curveTo((0, 100), (100, 0), (100, 100))
        pen.closePath()
        # an S-shaped cubic can't be approximated by a single quadratic, so
        # with all_quadratic=False it is kept as is
        assert not glyph_to_quadratic(glyph, all_quadratic=False)
        points = [(p.x, p.y, p.segmentType) for p in glyph[0]]
        assert points == [
            (0, 0, "line"),
            (0, 100, None),
            (100, 0, None),
            (100, 100, "curve"),
        ]
        assert all(isinstance(v, int) for x, y, _ in points for v in (x, y))

    def test_mixed_curves_converted_modified(self):
        glyph = ufoLib2.objects.Glyph()
        pen = glyph.getPen()
        pen.moveTo((0, 0))
        # a degree-elevated quadratic, converted back to one quadratic
        pen.curveTo((0, 60), (30, 90), (90, 90))
        pen.closePath()
        assert glyph_to_quadratic(glyph, all_quadratic=False)
        assert glyph[0][-1].segmentType == "qcurve"

    def test_open_paths(self):
        glyph = ufoLib2.objects.Glyph()
        pen = glyph.getPen()
        pen.moveTo((0, 0))
        pen.lineTo((1, 1))
        pen.curveTo((2, 2), (3, 3), (4, 4))
        pen.endPath()
        assert glyph_to_quadratic(glyph)
        # open contour is still open
        assert glyph[-1][0].segmentType == "move"

    def test_ignore_components(self):
        glyph = ufoLib2.objects.Glyph()
        pen = glyph.getPen()
        pen.addComponent("a", (1, 0, 0, 1, 0, 0))
        pen.moveTo((0, 0))
        pen.curveTo((1, 1), (2, 2), (3, 3))
        pen.closePath()
        assert glyph_to_quadratic(glyph)
        assert len(glyph.components) == 1

    def test_overlapping_start_end_points(self):
        # https://github.com/googlefonts/fontmake/issues/572
        glyph1 = ufoLib2.objects.Glyph()
        pen = glyph1.getPointPen()
        pen.beginPath()
        pen.addPoint((0, 651), segmentType="line")
        pen.addPoint((0, 101), segmentType="line")
        pen.addPoint((0, 101), segmentType="line")
        pen.addPoint((0, 651), segmentType="line")
        pen.endPath()

        glyph2 = ufoLib2.objects.Glyph()
        pen = glyph2.getPointPen()
        pen.beginPath()
        pen.addPoint((1, 651), segmentType="line")
        pen.addPoint((2, 101), segmentType="line")
        pen.addPoint((3, 101), segmentType="line")
        pen.addPoint((4, 651), segmentType="line")
        pen.endPath()

        glyphs = [glyph1, glyph2]

        assert glyphs_to_quadratic(glyphs, reverse_direction=True)

        assert [[(p.x, p.y) for p in glyph[0]] for glyph in glyphs] == [
            [
                (0, 651),
                (0, 651),
                (0, 101),
                (0, 101),
            ],
            [(1, 651), (4, 651), (3, 101), (2, 101)],
        ]

    def test_ignore_empty_glyphs(self):
        non_empty = ufoLib2.objects.Glyph(name="sparse")
        pen = non_empty.getPointPen()
        pen.beginPath()
        pen.addPoint((0, 0), segmentType="line")
        pen.addPoint((0, 2))
        pen.addPoint((1, 3))
        pen.addPoint((3, 3), segmentType="curve")
        pen.endPath()

        empty = ufoLib2.objects.Glyph(name="sparse")

        assert glyphs_to_quadratic([non_empty, empty])

        # Verify non-empty glyph was converted to quadratic
        assert [((p.x, p.y), p.segmentType) for p in non_empty[0]] == [
            ((0, 0), "line"),
            ((0.0, 3.0), None),
            ((3.0, 3.0), "qcurve"),
        ]

        # Verify empty glyph remains empty
        assert len(empty) == 0
