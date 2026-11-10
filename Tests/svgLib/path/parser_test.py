from fontTools.pens.recordingPen import RecordingPen
from fontTools.svgLib import parse_path

import pytest


@pytest.mark.parametrize(
    "pathdef, start, end",
    [
        ("M 01 02 L 003 004", (1.0, 2.0), (3.0, 4.0)),
        ("M 000.5 000.7 L 01e2 02e1", (0.5, 0.7), (100.0, 20.0)),
        ("M 1.e2 2.E1 L -3.e1 +4.e0", (100.0, 20.0), (-30.0, 4.0)),
        ("M .1.2 L .3.4", (0.1, 0.2), (0.3, 0.4)),
    ],
)
def test_svg_number_grammar(pathdef, start, end):
    pen = RecordingPen()
    parse_path(pathdef, pen)
    assert pen.value == [
        ("moveTo", (start,)),
        ("lineTo", (end,)),
        ("endPath", ()),
    ]


@pytest.mark.parametrize(
    "pathdef, expected",
    [
        # Examples from the SVG spec
        (
            "M 100 100 L 300 100 L 200 300 z",
            [
                ("moveTo", ((100.0, 100.0),)),
                ("lineTo", ((300.0, 100.0),)),
                ("lineTo", ((200.0, 300.0),)),
                ("lineTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        # for Z command behavior when there is multiple subpaths
        (
            "M 0 0 L 50 20 M 100 100 L 300 100 L 200 300 z",
            [
                ("moveTo", ((0.0, 0.0),)),
                ("lineTo", ((50.0, 20.0),)),
                ("endPath", ()),
                ("moveTo", ((100.0, 100.0),)),
                ("lineTo", ((300.0, 100.0),)),
                ("lineTo", ((200.0, 300.0),)),
                ("lineTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        # a redundant Z after a subpath is already closed is a no-op
        # (valid per the SVG path grammar); it must not crash nor emit
        # a second closePath.
        (
            "M 100 100 L 300 100 L 200 300 z z",
            [
                ("moveTo", ((100.0, 100.0),)),
                ("lineTo", ((300.0, 100.0),)),
                ("lineTo", ((200.0, 300.0),)),
                ("lineTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        # a redundant Z following an empty (moveto-only) closed subpath
        (
            "M 100 100 Z Z",
            [
                ("moveTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        (
            "M100,200 C100,100 250,100 250,200 S400,300 400,200",
            [
                ("moveTo", ((100.0, 200.0),)),
                ("curveTo", ((100.0, 100.0), (250.0, 100.0), (250.0, 200.0))),
                ("curveTo", ((250.0, 300.0), (400.0, 300.0), (400.0, 200.0))),
                ("endPath", ()),
            ],
        ),
        (
            "M100,200 C100,100 400,100 400,200",
            [
                ("moveTo", ((100.0, 200.0),)),
                ("curveTo", ((100.0, 100.0), (400.0, 100.0), (400.0, 200.0))),
                ("endPath", ()),
            ],
        ),
        (
            "M100,500 C25,400 475,400 400,500",
            [
                ("moveTo", ((100.0, 500.0),)),
                ("curveTo", ((25.0, 400.0), (475.0, 400.0), (400.0, 500.0))),
                ("endPath", ()),
            ],
        ),
        (
            "M100,800 C175,700 325,700 400,800",
            [
                ("moveTo", ((100.0, 800.0),)),
                ("curveTo", ((175.0, 700.0), (325.0, 700.0), (400.0, 800.0))),
                ("endPath", ()),
            ],
        ),
        (
            "M600,200 C675,100 975,100 900,200",
            [
                ("moveTo", ((600.0, 200.0),)),
                ("curveTo", ((675.0, 100.0), (975.0, 100.0), (900.0, 200.0))),
                ("endPath", ()),
            ],
        ),
        (
            "M600,500 C600,350 900,650 900,500",
            [
                ("moveTo", ((600.0, 500.0),)),
                ("curveTo", ((600.0, 350.0), (900.0, 650.0), (900.0, 500.0))),
                ("endPath", ()),
            ],
        ),
        (
            "M600,800 C625,700 725,700 750,800 S875,900 900,800",
            [
                ("moveTo", ((600.0, 800.0),)),
                ("curveTo", ((625.0, 700.0), (725.0, 700.0), (750.0, 800.0))),
                ("curveTo", ((775.0, 900.0), (875.0, 900.0), (900.0, 800.0))),
                ("endPath", ()),
            ],
        ),
        (
            "M200,300 Q400,50 600,300 T1000,300",
            [
                ("moveTo", ((200.0, 300.0),)),
                ("qCurveTo", ((400.0, 50.0), (600.0, 300.0))),
                ("qCurveTo", ((800.0, 550.0), (1000.0, 300.0))),
                ("endPath", ()),
            ],
        ),
        # End examples from SVG spec
        # Relative moveto
        (
            "M 0 0 L 50 20 m 50 80 L 300 100 L 200 300 z",
            [
                ("moveTo", ((0.0, 0.0),)),
                ("lineTo", ((50.0, 20.0),)),
                ("endPath", ()),
                ("moveTo", ((100.0, 100.0),)),
                ("lineTo", ((300.0, 100.0),)),
                ("lineTo", ((200.0, 300.0),)),
                ("lineTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        # Initial smooth and relative curveTo
        (
            "M100,200 s 150,-100 150,0",
            [
                ("moveTo", ((100.0, 200.0),)),
                ("curveTo", ((100.0, 200.0), (250.0, 100.0), (250.0, 200.0))),
                ("endPath", ()),
            ],
        ),
        # Initial smooth and relative qCurveTo
        (
            "M100,200 t 150,0",
            [
                ("moveTo", ((100.0, 200.0),)),
                ("qCurveTo", ((100.0, 200.0), (250.0, 200.0))),
                ("endPath", ()),
            ],
        ),
        # relative l command
        (
            "M 100 100 L 300 100 l -100 200 z",
            [
                ("moveTo", ((100.0, 100.0),)),
                ("lineTo", ((300.0, 100.0),)),
                ("lineTo", ((200.0, 300.0),)),
                ("lineTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        # relative q command
        (
            "M200,300 q200,-250 400,0",
            [
                ("moveTo", ((200.0, 300.0),)),
                ("qCurveTo", ((400.0, 50.0), (600.0, 300.0))),
                ("endPath", ()),
            ],
        ),
        # absolute H command
        (
            "M 100 100 H 300 L 200 300 z",
            [
                ("moveTo", ((100.0, 100.0),)),
                ("lineTo", ((300.0, 100.0),)),
                ("lineTo", ((200.0, 300.0),)),
                ("lineTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        # relative h command
        (
            "M 100 100 h 200 L 200 300 z",
            [
                ("moveTo", ((100.0, 100.0),)),
                ("lineTo", ((300.0, 100.0),)),
                ("lineTo", ((200.0, 300.0),)),
                ("lineTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        # absolute V command
        (
            "M 100 100 V 300 L 200 300 z",
            [
                ("moveTo", ((100.0, 100.0),)),
                ("lineTo", ((100.0, 300.0),)),
                ("lineTo", ((200.0, 300.0),)),
                ("lineTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        # relative v command
        (
            "M 100 100 v 200 L 200 300 z",
            [
                ("moveTo", ((100.0, 100.0),)),
                ("lineTo", ((100.0, 300.0),)),
                ("lineTo", ((200.0, 300.0),)),
                ("lineTo", ((100.0, 100.0),)),
                ("closePath", ()),
            ],
        ),
        # a drawto command following a closepath starts a new subpath at the
        # initial point of the just-closed subpath, i.e. there is an implicit
        # moveto (SVG 1.1 sec 8.3.3); the new subpath is open, hence endPath
        # https://github.com/fonttools/fonttools/issues/4154
        (
            "M0,0 L10,10 Z L5,5",
            [
                ("moveTo", ((0.0, 0.0),)),
                ("lineTo", ((10.0, 10.0),)),
                ("lineTo", ((0.0, 0.0),)),
                ("closePath", ()),
                ("moveTo", ((0.0, 0.0),)),
                ("lineTo", ((5.0, 5.0),)),
                ("endPath", ()),
            ],
        ),
        # a redundant Z before the drawto must not emit a second closePath
        # nor a spurious moveTo
        (
            "M0,0 L10,10 Z Z L5,5",
            [
                ("moveTo", ((0.0, 0.0),)),
                ("lineTo", ((10.0, 10.0),)),
                ("lineTo", ((0.0, 0.0),)),
                ("closePath", ()),
                ("moveTo", ((0.0, 0.0),)),
                ("lineTo", ((5.0, 5.0),)),
                ("endPath", ()),
            ],
        ),
        # a relative drawto after closepath is relative to the initial point
        # of the just-closed subpath
        (
            "M10,10 L20,20 Z l5,5",
            [
                ("moveTo", ((10.0, 10.0),)),
                ("lineTo", ((20.0, 20.0),)),
                ("lineTo", ((10.0, 10.0),)),
                ("closePath", ()),
                ("moveTo", ((10.0, 10.0),)),
                ("lineTo", ((15.0, 15.0),)),
                ("endPath", ()),
            ],
        ),
        # the implicitly-opened subpath can itself be closed, back to the
        # same initial point
        (
            "M0,0 L10,0 L10,10 Z L5,5 Z",
            [
                ("moveTo", ((0.0, 0.0),)),
                ("lineTo", ((10.0, 0.0),)),
                ("lineTo", ((10.0, 10.0),)),
                ("lineTo", ((0.0, 0.0),)),
                ("closePath", ()),
                ("moveTo", ((0.0, 0.0),)),
                ("lineTo", ((5.0, 5.0),)),
                ("lineTo", ((0.0, 0.0),)),
                ("closePath", ()),
            ],
        ),
        # S/T immediately after a closepath: the previous command (Z) is
        # not a C/S or Q/T, so the reflected first control point falls
        # back to the current point, i.e. the initial point of the
        # just-closed subpath
        (
            "M0,0 C0,5 5,5 5,0 Z S10,5 10,0",
            [
                ("moveTo", ((0.0, 0.0),)),
                ("curveTo", ((0.0, 5.0), (5.0, 5.0), (5.0, 0.0))),
                ("lineTo", ((0.0, 0.0),)),
                ("closePath", ()),
                ("moveTo", ((0.0, 0.0),)),
                ("curveTo", ((0.0, 0.0), (10.0, 5.0), (10.0, 0.0))),
                ("endPath", ()),
            ],
        ),
        (
            "M0,0 Q2.5,5 5,0 Z T10,0",
            [
                ("moveTo", ((0.0, 0.0),)),
                ("qCurveTo", ((2.5, 5.0), (5.0, 0.0))),
                ("lineTo", ((0.0, 0.0),)),
                ("closePath", ()),
                ("moveTo", ((0.0, 0.0),)),
                ("qCurveTo", ((0.0, 0.0), (10.0, 0.0))),
                ("endPath", ()),
            ],
        ),
    ],
)
def test_parse_path(pathdef, expected):
    pen = RecordingPen()
    parse_path(pathdef, pen)

    assert pen.value == expected


@pytest.mark.parametrize(
    "pathdef1, pathdef2",
    [
        # don't need spaces between numbers and commands
        (
            "M 100 100 L 200 200",
            "M100 100L200 200",
        ),
        # repeated implicit command
        ("M 100 200 L 200 100 L -100 -200", "M 100 200 L 200 100 -100 -200"),
        # don't need spaces before a minus-sign
        ("M100,200c10-5,20-10,30-20", "M 100 200 c 10 -5 20 -10 30 -20"),
        # closed paths have an implicit lineTo if they don't
        # end on the same point as the initial moveTo
        (
            "M 100 100 L 300 100 L 200 300 z",
            "M 100 100 L 300 100 L 200 300 L 100 100 z",
        ),
    ],
)
def test_equivalent_paths(pathdef1, pathdef2):
    pen1 = RecordingPen()
    parse_path(pathdef1, pen1)

    pen2 = RecordingPen()
    parse_path(pathdef2, pen2)

    assert pen1.value == pen2.value


def test_closepath_ignores_floating_point_rounding():
    pen = RecordingPen()
    parse_path("M 0.1 0 l 0.2 0 l -0.2 0 z", pen)

    assert [command for command, _ in pen.value] == [
        "moveTo",
        "lineTo",
        "lineTo",
        "closePath",
    ]


def test_implicit_moveto_after_drift_suppressed_closepath():
    # a closepath returning to its start with floating-point drift emits no
    # closing lineTo (see test above), but must still reset the current
    # position to the exact initial point, so that the implicit moveto of a
    # following drawto lands on it rather than on the drifted position
    assert 0.1 + 0.2 - 0.2 != 0.1  # the drift this test relies on
    pen = RecordingPen()
    parse_path("M 0.1 0 l 0.2 0 l -0.2 0 z l 0.1 0.1", pen)

    assert pen.value[3] == ("closePath", ())
    assert pen.value[4] == ("moveTo", ((0.1, 0.0),))
    # the relative lineTo resolves against the exact initial point too
    assert pen.value[5] == ("lineTo", ((0.1 + 0.1, 0.1),))
    assert pen.value[6] == ("endPath", ())


def test_exponents():
    # It can be e or E, the plus is optional, and a minimum of +/-3.4e38 must be supported.
    pen = RecordingPen()
    parse_path("M-3.4e38 3.4E+38L-3.4E-38,3.4e-38", pen)
    expected = [
        ("moveTo", ((-3.4e38, 3.4e38),)),
        ("lineTo", ((-3.4e-38, 3.4e-38),)),
        ("endPath", ()),
    ]

    assert pen.value == expected

    pen = RecordingPen()
    parse_path("M-3e38 3E+38L-3E-38,3e-38", pen)
    expected = [
        ("moveTo", ((-3e38, 3e38),)),
        ("lineTo", ((-3e-38, 3e-38),)),
        ("endPath", ()),
    ]

    assert pen.value == expected


def test_invalid_implicit_command():
    with pytest.raises(ValueError) as exc_info:
        parse_path("M 100 100 L 200 200 Z 100 200", RecordingPen())
    assert exc_info.match("Unallowed implicit command")


@pytest.mark.parametrize(
    "pathdef",
    [
        "M",  # moveto with no coordinates
        "M0,0 L5",  # lineto missing its y
        "M0,0 L1,1 2",  # trailing implicit lineto missing its y
        "M0,0 H",  # horizontal lineto with no coordinate
        "M0,0 V",  # vertical lineto with no coordinate
        "M0,0 C1,1 2,2",  # curveto missing its end point
        "M0,0 S1,1",  # smooth curveto missing its end point
        "M0,0 Q1,1",  # quadratic curveto missing its end point
        "M0,0 T",  # smooth quadratic with no end point
    ],
)
def test_too_few_coordinates(pathdef):
    # A drawto command with fewer numbers than it needs should raise a clear
    # ValueError, like the parser's other errors, instead of a bare IndexError
    # from popping an empty token list.
    with pytest.raises(ValueError, match="Not enough coordinates"):
        parse_path(pathdef, RecordingPen())


@pytest.mark.parametrize(
    "pathdef",
    [
        "L 5 5",
        "Z",
        # bare coordinates aren't a moveto either
        "5 5",
        # a later moveto doesn't repair a bad start
        "L 5 5 M 0 0",
    ],
)
def test_path_must_start_with_moveto(pathdef):
    # A path data segment must begin with a moveto command (SVG 1.1
    # sec 8.3.2); raise before any pen call instead of inventing a
    # start point for the malformed path.
    # https://github.com/fonttools/fonttools/issues/4154
    pen = RecordingPen()
    with pytest.raises(ValueError, match="must start with a moveto"):
        parse_path(pathdef, pen)
    assert pen.value == []


def test_initial_relative_moveto_with_current_pos():
    # a caller-supplied current_pos affects an initial relative moveto...
    pen = RecordingPen()
    parse_path("m 5 5", pen, current_pos=(10, 20))
    assert pen.value == [("moveTo", ((15.0, 25.0),)), ("endPath", ())]

    # ...but does not legalize a leading drawto
    pen = RecordingPen()
    with pytest.raises(ValueError, match="must start with a moveto"):
        parse_path("l 5 5", pen, current_pos=(10, 20))
    assert pen.value == []


def test_empty_path_is_noop():
    pen = RecordingPen()
    parse_path("", pen)
    parse_path("   ", pen)
    assert pen.value == []


def test_arc_to_cubic_bezier():
    pen = RecordingPen()
    parse_path("M300,200 h-150 a150,150 0 1,0 150,-150 z", pen)
    expected = [
        ("moveTo", ((300.0, 200.0),)),
        ("lineTo", ((150.0, 200.0),)),
        ("curveTo", ((150.0, 282.842), (217.157, 350.0), (300.0, 350.0))),
        ("curveTo", ((382.842, 350.0), (450.0, 282.842), (450.0, 200.0))),
        ("curveTo", ((450.0, 117.157), (382.842, 50.0), (300.0, 50.0))),
        ("lineTo", ((300.0, 200.0),)),
        ("closePath", ()),
    ]

    result = list(pen.value)
    assert len(result) == len(expected)
    for (cmd1, points1), (cmd2, points2) in zip(result, expected):
        assert cmd1 == cmd2
        assert len(points1) == len(points2)
        for pt1, pt2 in zip(points1, points2):
            assert pt1 == pytest.approx(pt2, rel=1e-5)


class ArcRecordingPen(RecordingPen):
    def arcTo(self, rx, ry, rotation, arc_large, arc_sweep, end_point):
        self.value.append(
            ("arcTo", (rx, ry, rotation, arc_large, arc_sweep, end_point))
        )


@pytest.mark.parametrize(
    "pathdef",
    [
        "M0 0 A01 02 03 0 1 04 05",
        "M0 0 A1. 2. 3.e0 0 1 4. 5.",
        "M0 0 A1 2 3\n0\n1\n4\n5",
        "M0 0 A1 2 3\r0\r1\r4\r5",
    ],
)
def test_arc_number_grammar_and_whitespace(pathdef):
    pen = ArcRecordingPen()
    parse_path(pathdef, pen)
    assert pen.value == [
        ("moveTo", ((0.0, 0.0),)),
        ("arcTo", (1.0, 2.0, 3.0, False, True, (4.0, 5.0))),
        ("endPath", ()),
    ]


def test_arc_pen_with_arcTo():
    pen = ArcRecordingPen()
    parse_path("M300,200 h-150 a150,150 0 1,0 150,-150 z", pen)
    expected = [
        ("moveTo", ((300.0, 200.0),)),
        ("lineTo", ((150.0, 200.0),)),
        ("arcTo", (150.0, 150.0, 0.0, True, False, (300.0, 50.0))),
        ("lineTo", ((300.0, 200.0),)),
        ("closePath", ()),
    ]

    assert pen.value == expected


@pytest.mark.parametrize(
    "path, expected",
    [
        (
            "M1-2A3-4-1.0 01.5.7",
            [
                ("moveTo", ((1.0, -2.0),)),
                ("arcTo", (3.0, 4.0, -1.0, False, True, (0.5, 0.7))),
                ("endPath", ()),
            ],
        ),
        (
            "M21.58 7.19a2.51 2.51 0 10-1.77-1.77",
            [
                ("moveTo", ((21.58, 7.19),)),
                ("arcTo", (2.51, 2.51, 0.0, True, False, (19.81, 5.42))),
                ("endPath", ()),
            ],
        ),
        (
            "M22 12a25.87 25.87 0 00-.42-4.81",
            [
                ("moveTo", ((22.0, 12.0),)),
                ("arcTo", (25.87, 25.87, 0.0, False, False, (21.58, 7.19))),
                ("endPath", ()),
            ],
        ),
        (
            "M0,0 A1.2 1.2 0 012 15.8",
            [
                ("moveTo", ((0.0, 0.0),)),
                ("arcTo", (1.2, 1.2, 0.0, False, True, (2.0, 15.8))),
                ("endPath", ()),
            ],
        ),
        (
            "M12 7a5 5 0 105 5 5 5 0 00-5-5",
            [
                ("moveTo", ((12.0, 7.0),)),
                ("arcTo", (5.0, 5.0, 0.0, True, False, (17.0, 12.0))),
                ("arcTo", (5.0, 5.0, 0.0, False, False, (12.0, 7.0))),
                ("endPath", ()),
            ],
        ),
    ],
)
def test_arc_flags_without_spaces(path, expected):
    pen = ArcRecordingPen()
    parse_path(path, pen)
    assert pen.value == expected


@pytest.mark.parametrize("path", ["A", "A0,0,0,0,0,0", "A 0 0 0 0 0 0 0 0 0 0 0 0 0"])
def test_invalid_arc_not_enough_args(path):
    pen = ArcRecordingPen()
    with pytest.raises(ValueError, match="Invalid arc command") as e:
        parse_path(path, pen)

    assert isinstance(e.value.__cause__, ValueError)
    assert "Not enough arguments" in str(e.value.__cause__)


def test_invalid_arc_argument_value():
    pen = ArcRecordingPen()
    with pytest.raises(ValueError, match="Invalid arc command") as e:
        parse_path("M0,0 A0,0,0,2,0,0,0", pen)

    cause = e.value.__cause__
    assert isinstance(cause, ValueError)
    assert "Invalid argument for 'large-arc-flag' parameter: '2'" in str(cause)

    pen = ArcRecordingPen()
    with pytest.raises(ValueError, match="Invalid arc command") as e:
        parse_path("M0,0 A0,0,0,0,-2.0,0,0", pen)

    cause = e.value.__cause__
    assert isinstance(cause, ValueError)
    assert "Invalid argument for 'sweep-flag' parameter: '-2.0'" in str(cause)
