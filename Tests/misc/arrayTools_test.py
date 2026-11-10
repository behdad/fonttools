from fontTools.misc.arrayTools import (
    calcBounds,
    calcIntBounds,
    updateBounds,
    pointInRect,
    pointsInRect,
    vectorLength,
    asInt16,
    normRect,
    scaleRect,
    offsetRect,
    insetRect,
    sectRect,
    unionRect,
    rectCenter,
    intRect,
    pairwise,
)
import math
import pytest


def test_calcBounds():
    assert calcBounds([]) == (0, 0, 0, 0)
    assert calcBounds([(0, 40), (0, 100), (50, 50), (80, 10)]) == (0, 10, 80, 100)


def test_calcIntBounds():
    assert calcIntBounds([(0.1, 40.1), (0.1, 100.1), (49.9, 49.9), (78.5, 9.5)]) == (
        0,
        10,
        79,
        100,
    )

    assert calcIntBounds(
        [(0.1, 40.1), (0.1, 100.1), (49.9, 49.9), (78.5, 9.5)], round=round
    ) == (0, 10, 78, 100)


def test_updateBounds():
    assert updateBounds((0, 0, 0, 0), (100, 100)) == (0, 0, 100, 100)


def test_pointInRect():
    assert pointInRect((50, 50), (0, 0, 100, 100))
    assert pointInRect((0, 0), (0, 0, 100, 100))
    assert pointInRect((100, 100), (0, 0, 100, 100))
    assert not pointInRect((101, 100), (0, 0, 100, 100))


def test_pointsInRect():
    assert pointsInRect([], (0, 0, 100, 100)) == []
    assert pointsInRect(
        [(50, 50), (0, 0), (100, 100), (101, 100)], (0, 0, 100, 100)
    ) == [True, True, True, False]


def test_vectorLength():
    assert vectorLength((1, 1)) == math.sqrt(2)


def test_asInt16():
    assert asInt16([0, 0.1, 0.5, 0.9]) == [0, 0, 1, 1]


def test_normRect():
    assert normRect((0, 10, 100, 200)) == (0, 10, 100, 200)
    assert normRect((100, 200, 0, 10)) == (0, 10, 100, 200)


def test_scaleRect():
    assert scaleRect((10, 20, 50, 150), 1.5, 2) == (15.0, 40, 75.0, 300)


def test_offsetRect():
    assert offsetRect((10, 20, 30, 40), 5, 6) == (15, 26, 35, 46)


def test_insetRect():
    assert insetRect((10, 20, 50, 60), 5, 10) == (15, 30, 45, 50)
    assert insetRect((10, 20, 50, 60), -5, -10) == (5, 10, 55, 70)


def test_sectRect():
    intersects, rect = sectRect((0, 10, 20, 30), (0, 40, 20, 50))
    assert not intersects

    intersects, rect = sectRect((0, 10, 20, 30), (5, 20, 35, 50))
    assert intersects
    assert rect == (5, 20, 20, 30)


def test_unionRect():
    assert unionRect((0, 10, 20, 30), (0, 40, 20, 50)) == (0, 10, 20, 50)


def test_rectCenter():
    assert rectCenter((0, 0, 100, 200)) == (50.0, 100.0)
    assert rectCenter((0, 0, 100, 199.0)) == (50.0, 99.5)


def test_intRect():
    assert intRect((0.9, 2.9, 3.1, 4.1)) == (0, 2, 4, 5)


@pytest.mark.parametrize(
    "factory",
    [list, tuple, iter, lambda items: (item for item in items)],
    ids=["list", "tuple", "iterator", "generator"],
)
@pytest.mark.parametrize(
    "items, expected",
    [
        ([], []),
        ([None], [(None, None)]),
        ([None, 1], [(None, 1), (1, None)]),
        ([0], [(0, 0)]),
        ([0, 1, 2], [(0, 1), (1, 2), (2, 0)]),
    ],
)
def test_pairwise_iterables(factory, items, expected):
    assert list(pairwise(factory(items))) == expected
