import fontTools.varLib.iup as iup
from fontTools.misc.roundTools import otRound
import sys
import random
import pytest


class IupTest:
    # -----
    # Tests
    # -----

    @pytest.mark.parametrize(
        "delta, coords, forced",
        [
            ([(0, 0)], [(1, 2)], set()),
            ([(0, 0), (0, 0), (0, 0)], [(1, 2), (3, 2), (2, 3)], set()),
            (
                [(1, 1), (-1, 1), (-1, -1), (1, -1)],
                [(0, 0), (2, 0), (2, 2), (0, 2)],
                set(),
            ),
            (
                [
                    (-1, 0),
                    (-1, 0),
                    (-1, 0),
                    (-1, 0),
                    (-1, 0),
                    (0, 0),
                    (0, 0),
                    (0, 0),
                    (0, 0),
                    (0, 0),
                    (0, 0),
                    (-1, 0),
                ],
                [
                    (-35, -152),
                    (-86, -101),
                    (-50, -65),
                    (0, -116),
                    (51, -65),
                    (86, -99),
                    (35, -151),
                    (87, -202),
                    (51, -238),
                    (-1, -187),
                    (-53, -239),
                    (-88, -205),
                ],
                {11},
            ),
            (
                [
                    (0, 0),
                    (1, 0),
                    (2, 0),
                    (2, 0),
                    (0, 0),
                    (1, 0),
                    (3, 0),
                    (3, 0),
                    (2, 0),
                    (2, 0),
                    (0, 0),
                    (0, 0),
                    (-1, 0),
                    (-1, 0),
                    (-1, 0),
                    (-3, 0),
                    (-1, 0),
                    (0, 0),
                    (0, 0),
                    (-2, 0),
                    (-2, 0),
                    (-1, 0),
                    (-1, 0),
                    (-1, 0),
                    (-4, 0),
                ],
                [
                    (330, 65),
                    (401, 65),
                    (499, 117),
                    (549, 225),
                    (549, 308),
                    (549, 422),
                    (549, 500),
                    (497, 600),
                    (397, 648),
                    (324, 648),
                    (271, 648),
                    (200, 620),
                    (165, 570),
                    (165, 536),
                    (165, 473),
                    (252, 407),
                    (355, 407),
                    (396, 407),
                    (396, 333),
                    (354, 333),
                    (249, 333),
                    (141, 268),
                    (141, 203),
                    (141, 131),
                    (247, 65),
                ],
                {5, 15, 24},
            ),
        ],
    )
    def test_forced_set(self, delta, coords, forced):
        f = iup._iup_contour_bound_forced_set(delta, coords)
        assert forced == f

        chain1, costs1 = iup._iup_contour_optimize_dp(delta, coords, f)
        chain2, costs2 = iup._iup_contour_optimize_dp(delta, coords, set())

        assert chain1 == chain2, f
        assert costs1 == costs2, f

    @pytest.mark.parametrize("delta", [1, -2])
    def test_optimize_preserves_rounded_deltas(self, delta):
        coords = [(0, 0), (0.125, 10), (0.25, 20)]
        deltas = [(delta, 0), (delta + 0.5, 0), (delta + 1, 0)]
        optimized = iup.iup_contour_optimize(deltas, coords)
        encoded = [
            None if d is None else (otRound(d[0]), otRound(d[1])) for d in optimized
        ]

        assert iup.iup_contour(encoded, [(0, 0), (0, 10), (0, 20)]) == [
            (delta, 0),
            (otRound(delta + 0.5), 0),
            (delta + 1, 0),
        ]

    @pytest.mark.parametrize("left, right", [(1.5, 2), (-1.5, -1)])
    def test_interpolate_fractional_reference_deltas(self, left, right):
        result = iup.iup_contour(
            [(left, 0), None, (right, 0)], [(0, 0), (0, 10), (0, 20)]
        )
        assert result == [(left, 0), (0, 0), (right, 0)]

    @pytest.mark.parametrize("rotation", range(3))
    def test_interpolate_fractional_coordinates(self, rotation):
        coords = [(0, 0), (0.125, 10), (0.25, 20)]
        deltas = [(1, 0), None, (2, 0)]
        expected = [(1, 0), (1.5, 0), (2, 0)]
        coords = coords[rotation:] + coords[:rotation]
        deltas = deltas[rotation:] + deltas[:rotation]
        expected = expected[rotation:] + expected[:rotation]

        assert iup.iup_contour(deltas, coords) == expected

    @pytest.mark.parametrize("tolerance", [0, 0.03])
    def test_optimize_equal_rounded_deltas(self, tolerance):
        coords = [(0, 0), (0, 10), (0, 20)]
        deltas = [(1.01, 0), (1.02, 0), (1.03, 0)]
        optimized = iup.iup_contour_optimize(deltas, coords, tolerance)
        inferred = iup.iup_contour(optimized, coords)
        assert all(
            abs(complex(x - p, y - q)) <= tolerance
            for (x, y), (p, q) in zip(deltas, inferred)
        )
        assert all(d is None or d == original for d, original in zip(optimized, deltas))
        encoded = [
            None if d is None else (otRound(d[0]), otRound(d[1])) for d in optimized
        ]
        assert iup.iup_contour(encoded, coords) == [(1, 0), (1, 0), (1, 0)]

    @pytest.mark.parametrize("rotation", range(4))
    @pytest.mark.parametrize("tolerance", [0, 0.25])
    def test_optimize_preserves_rounded_interpolation(self, rotation, tolerance):
        coords = [(-0.625, 0), (-0.25, 10), (0.5, 20), (-0.5, 70)]
        deltas = [(-0.375, 0), (-0.625, 0), (-1.125, 0), (-0.375, 0)]
        coords = coords[rotation:] + coords[:rotation]
        deltas = deltas[rotation:] + deltas[:rotation]
        optimized = iup.iup_contour_optimize(deltas, coords, tolerance)
        inferred = iup.iup_contour(optimized, coords)
        assert all(
            abs(complex(x - p, y - q)) <= tolerance
            for (x, y), (p, q) in zip(deltas, inferred)
        )
        encoded = [
            None if d is None else (otRound(d[0]), otRound(d[1])) for d in optimized
        ]
        rounded_coords = [(otRound(x), otRound(y)) for x, y in coords]
        inferred = iup.iup_contour(encoded, rounded_coords)
        assert all(
            abs(complex(otRound(x) - p, otRound(y) - q)) <= tolerance
            for (x, y), (p, q) in zip(deltas, inferred)
        )

    @pytest.mark.parametrize("delta", [(0.5, 0), (0, 0.5), (0.4, 0.4), (-0.5, 0)])
    def test_optimize_zero_checks_rounded_deltas(self, delta):
        coords = [(0, 0), (10, 10), (20, 0)]
        deltas = [delta] * len(coords)
        optimized = iup.iup_contour_optimize(deltas, coords, tolerance=0.5)
        inferred = iup.iup_contour(optimized, coords)
        assert all(
            abs(complex(x - p, y - q)) <= 0.5
            for (x, y), (p, q) in zip(deltas, inferred)
        )
        encoded = [
            None if d is None else (otRound(d[0]), otRound(d[1])) for d in optimized
        ]
        assert iup.iup_contour(encoded, coords) == [
            (otRound(delta[0]), otRound(delta[1]))
        ] * len(coords)

    @pytest.mark.parametrize("tolerance", [0, 0.5, 1])
    def test_optimize_fractional_contours(self, tolerance):
        randomizer = random.Random(3636)
        for index in range(200):
            count = randomizer.randrange(1, 10)
            coords = [
                (randomizer.randrange(-16, 17) / 8, randomizer.randrange(-16, 17) / 8)
                for _ in range(count)
            ]
            deltas = [
                (randomizer.randrange(-16, 17) / 8, randomizer.randrange(-16, 17) / 8)
                for _ in range(count)
            ]
            if index % 5 == 0:
                deltas = [deltas[0]] * count
            optimized = iup.iup_contour_optimize(deltas, coords, tolerance)
            assert all(
                d is None or d == original for d, original in zip(optimized, deltas)
            )
            inferred = iup.iup_contour(optimized, coords)
            assert all(
                abs(complex(x - p, y - q)) <= tolerance
                for (x, y), (p, q) in zip(deltas, inferred)
            )
            encoded = [
                None if d is None else (otRound(d[0]), otRound(d[1])) for d in optimized
            ]
            rounded_coords = [(otRound(x), otRound(y)) for x, y in coords]
            inferred = iup.iup_contour(encoded, rounded_coords)
            assert all(
                abs(complex(otRound(x) - p, otRound(y) - q)) <= tolerance
                for (x, y), (p, q) in zip(deltas, inferred)
            )


if __name__ == "__main__":
    sys.exit(pytest.main(sys.argv))
