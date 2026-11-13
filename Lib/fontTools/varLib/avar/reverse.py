"""Find pre-fvar coordinates that approximate a post-avar location.

The numerical solver uses an unrounded forward map and its analytic Jacobian.
Candidates are ranked using the actual forward map, including avar2 rounding
and clipping. SciPy is optional and is imported only when reverse() is called.
"""

from bisect import bisect_right
import logging
import math

from fontTools.varLib.models import normalizeValue, piecewiseLinearMap
from fontTools.varLib.varStore import NO_VARIATION_INDEX
from .map import _denormalize, map as map_forward

log = logging.getLogger(__name__)


def _segment(value, items):
    """Piecewise-linear segment value and a one-sided derivative."""
    if not items:
        return value, 1.0
    keys = [k for k, _ in items]
    i = bisect_right(keys, value)
    if value < keys[0] or value > keys[-1] or len(items) == 1:
        k, v = items[0 if value < keys[0] else -1]
        return value + v - k, 1.0
    i = min(max(i, 1), len(items) - 1)
    a, va = items[i - 1]
    b, vb = items[i]
    slope = (vb - va) / (b - a)
    return va + (value - a) * slope, slope


def _tent(value, start, peak, end):
    """Tent value and right derivative (inward at a one-sided peak)."""
    if value < start or value > end:
        return 0.0, 0.0
    if value == peak:
        if peak < end:
            return 1.0, -1 / (end - peak)
        return 1.0, 1 / (peak - start) if start < peak else 0.0
    if value == end and end < 1:
        return 0.0, 0.0
    if value < peak:
        slope = 1 / (peak - start)
        return (value - start) * slope, slope
    slope = -1 / (end - peak)
    return (value - end) * slope, slope


def _inverseSegment(value, items, lo, hi):
    """Choose a segment preimage nearest default, including flat intervals."""
    mapping = dict(items)
    points = sorted({lo, hi, *[k for k in mapping if lo <= k <= hi]})
    preimages = []
    for a, b in zip(points, points[1:]):
        va, vb = piecewiseLinearMap(a, mapping), piecewiseLinearMap(b, mapping)
        if min(va, vb) <= value <= max(va, vb):
            preimages.append(
                min(max(0, a), b)
                if va == vb
                else a + (value - va) * (b - a) / (vb - va)
            )
    if preimages:
        return min(preimages, key=abs)
    return min(points, key=lambda v: abs(piecewiseLinearMap(v, mapping) - value))


class _AvarMapping:
    """Continuous forward mapping in pre-avar normalized coordinates."""

    def __init__(self, font):
        import numpy as np

        self.np = np
        self.axes = font["fvar"].axes
        self.tags = [a.axisTag for a in self.axes]
        avar = font.get("avar")
        version = getattr(avar, "majorVersion", 1)
        if version not in (1, 2):
            raise NotImplementedError("Unknown avar table version")
        self.segments = [
            sorted(avar.segments.get(tag, {}).items()) if avar else []
            for tag in self.tags
        ]
        store = avar.table.VarStore if avar and version == 2 else None
        self.supports = []
        self.deltas = np.zeros((len(self.axes), 0))
        if store is not None:
            indexMap = avar.table.VarIdxMap
            # Assemble D[output axis, region] in normalized-coordinate units.
            # Resolving VarIdxMap here also handles axes that share delta rows.
            # Missing/out-of-range rows contribute zero, as in VarStoreInstancer.
            deltas = np.zeros((len(self.axes), len(store.VarRegionList.Region)))
            for i in range(len(self.axes)):
                index = indexMap[i] if indexMap is not None else i
                outer, inner = index >> 16, index & 0xFFFF
                if index == NO_VARIATION_INDEX or outer >= len(store.VarData):
                    continue
                data = store.VarData[outer]
                if inner >= len(data.Item):
                    continue
                for region, delta in zip(data.VarRegionIndex, data.Item[inner]):
                    deltas[i, region] += delta / 16384
            # Ignore unused regions and axes ignored by OpenType supportScalar.
            for r in np.flatnonzero(np.any(deltas, axis=0)):
                self.supports.append(
                    [
                        (i, a.StartCoord, a.PeakCoord, a.EndCoord)
                        for i, a in enumerate(
                            store.VarRegionList.Region[r].VarRegionAxis
                        )
                        if a.PeakCoord != 0
                        and a.StartCoord <= a.PeakCoord <= a.EndCoord
                        and not (a.StartCoord < 0 < a.EndCoord)
                    ]
                )
            self.deltas = deltas[:, np.any(deltas, axis=0)]

    def __call__(self, x):
        np = self.np
        # x is normalized BEFORE avar1; z = A(x) is the intermediate location.
        # Before clipping/rounding, the full map is H(x) = z + D * s(z), where
        # s contains the products of per-axis tents for each region. Within a
        # region cell this is multilinear, not generally one affine transform.
        values, slopes = zip(*(_segment(v, s) for v, s in zip(x, self.segments)))
        z = np.array(values)
        jac = np.eye(len(x))
        for deltas, support in zip(self.deltas.T, self.supports):
            factors = [_tent(z[i], a, p, b) for i, a, p, b in support]
            scalar = math.prod(v for v, _ in factors)
            gradient = np.zeros(len(x))
            for j, (i, _, _, _) in enumerate(support):
                # Do not divide by a factor: zero factors can have nonzero
                # derivatives at a region boundary.
                gradient[i] = factors[j][1] * math.prod(
                    v for k, (v, _) in enumerate(factors) if k != j
                )
            jac += np.outer(deltas, gradient)
            # All regions see the same intermediate coordinates.
            values = np.asarray(values) + deltas * scalar
        # Chain rule: J_H = (I + D * J_s) * diag(A'). Multiplying columns by
        # the avar1 slopes differentiates with respect to our input x, not z.
        return np.asarray(values), jac * slopes


def reverse(
    font,
    location,
    *,
    inputNormalized=False,
    outputNormalized=False,
    dropZeroes=False,
    pinned=None,
    tolerance=1 / 16384,
):
    """Approximately invert an avar (version 1 or 2) mapping.

    ``location`` specifies post-avar targets; omitted axes target normalized
    zero. Input and output units follow avar.map: by default both are in
    pre-fvar units, with ``inputNormalized`` and ``outputNormalized`` selecting
    normalized target and result coordinates, respectively.

    Hidden axes are held at their fvar defaults. ``pinned`` optionally maps
    other axis tags to fixed PRE-FVAR values, regardless of the unit flags.
    A pinned value of None means the axis's fvar default.
    Returned coordinates stay within the fvar ranges.

    Output error is Euclidean distance in normalized coordinates. Among
    candidates within ``tolerance`` of the smallest error found, prefer fewer
    non-default input axes, then smaller error and normalized distance from
    default.
    Sparsity is sought by greedy elimination, not exhaustive subset search.
    Multiple starts reduce local-minimum sensitivity but do not guarantee a
    global optimum. An unreachable target returns an approximation and logs
    its residual. Returns None for a font without fvar. Requires SciPy.
    """
    if "fvar" not in font:
        return None
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be finite and non-negative")
    axes = font["fvar"].axes
    triples = {a.axisTag: (a.minValue, a.defaultValue, a.maxValue) for a in axes}
    pinned = dict(pinned or {})
    unknown = sorted((location.keys() | pinned.keys()) - triples.keys())
    if unknown:
        raise ValueError(f"Unknown axis tag(s): {', '.join(unknown)}")
    pinned = {
        tag: triples[tag][1] if value is None else value
        for tag, value in pinned.items()
    }
    for tag, value in location.items():
        if not math.isfinite(value) or (inputNormalized and not -1 <= value <= 1):
            raise ValueError(f"Invalid target coordinate for {tag}: {value}")
    for axis in axes:
        tag = axis.axisTag
        if axis.flags & 1:
            if tag in pinned and pinned[tag] != axis.defaultValue:
                raise ValueError(f"Hidden axis {tag} must stay at its default")
            pinned[tag] = axis.defaultValue
    for tag, value in pinned.items():
        lo, _, hi = triples[tag]
        if not math.isfinite(value) or not lo <= value <= hi:
            raise ValueError(f"Pinned coordinate for {tag} must be in [{lo}, {hi}]")

    if not axes:
        return {}
    try:
        import numpy as np
        from scipy.optimize import least_squares
    except ImportError as e:
        raise ImportError(
            "Reverse avar mapping requires scipy; install fonttools[avar]"
        ) from e

    mapping = _AvarMapping(font)
    target = np.array(
        [
            (
                location.get(a.axisTag, 0)
                if inputNormalized
                else normalizeValue(
                    location.get(a.axisTag, a.defaultValue), triples[a.axisTag]
                )
            )
            for a in axes
        ]
    )
    # Optimize in normalized input space so weight, optical size, etc. have
    # comparable scales. A default at an endpoint makes its domain one-sided.
    # Hidden, pinned, and collapsed axes are eliminated from the optimization;
    # their OUTPUT coordinates still participate in the residual.
    lower = np.array([-1.0 if a.minValue < a.defaultValue else 0.0 for a in axes])
    upper = np.array([1.0 if a.defaultValue < a.maxValue else 0.0 for a in axes])
    fixed = np.array(
        [
            normalizeValue(pinned.get(a.axisTag, a.defaultValue), triples[a.axisTag])
            for a in axes
        ]
    )
    free = [
        i for i, a in enumerate(axes) if a.axisTag not in pinned and lower[i] < upper[i]
    ]
    candidates = {}

    def add(x):
        x = x.copy()
        x[free] = np.where(abs(x[free]) < 1e-10, 0, x[free])
        key = tuple(x)
        if key not in candidates:
            # Score through the public forward path, including the round trip
            # through pre-fvar coordinates that the caller will actually use.
            user = {
                a.axisTag: _denormalize(v, triples[a.axisTag]) for a, v in zip(axes, x)
            }
            user.update(pinned)
            actual = map_forward(font, user, outputNormalized=True, dropZeroes=False)
            error = np.linalg.norm(
                [actual[tag] - t for tag, t in zip(mapping.tags, target)]
            )
            candidates[key] = (error, x)

    def best():
        # Output accuracy comes first, up to the requested tolerance. Use the
        # smallest residual seen across ALL candidates as the error budget's
        # anchor, so successive axis removals cannot accumulate tolerance loss.
        # Within that budget prefer fewer non-default inputs, then accuracy,
        # then proximity to default. This is a preference, not an L0 penalty
        # added to the residual, which could trade away an otherwise good fit.
        error = min(e for e, _ in candidates.values())
        return min(
            (c for c in candidates.values() if c[0] <= error + tolerance),
            key=lambda c: (np.count_nonzero(c[1]), c[0], np.dot(c[1], c[1])),
        )

    def solve(seed, varying):
        x = seed.copy()
        add(x)
        if not varying:
            return
        # First seek an exact inverse without the flat plateaus introduced by
        # clipping. At +/-1 the target is an inequality on the unclipped map.
        # Then minimize the true clipped output error, also for unreachable
        # targets (the two objectives need not have the same nearest point).
        for clipped in (False, True):
            cached = None

            def evaluate(v):
                nonlocal cached
                if cached is not None and np.array_equal(v, cached[0]):
                    return cached[1:]
                x[varying] = v
                raw, jac = mapping(x)
                if clipped:
                    residual = np.clip(raw, -1, 1) - target
                    active = (raw >= -1) & (raw <= 1)
                else:
                    residual = raw - target
                    active = ~(
                        ((target == 1) & (raw > 1)) | ((target == -1) & (raw < -1))
                    )
                    residual = np.where(active, residual, 0)
                jac = jac[:, varying] * active[:, None]
                cached = (v.copy(), residual, jac)
                return residual, jac

            # Trust-region least squares repeatedly solves a bounded local
            # linear problem using this Jacobian, then checks the nonlinear
            # residual before accepting a step. Rank deficiency is expected:
            # multiple inputs can produce the same output, especially after
            # saturation. Avoid explicitly inverting J or forming J.T @ J.
            result = least_squares(
                lambda v: evaluate(v)[0],
                x[varying],
                jac=lambda v: evaluate(v)[1],
                bounds=(lower[varying], upper[varying]),
                ftol=1e-11,
                xtol=1e-11,
                gtol=1e-11,
                max_nfev=200,
            )
            x[varying] = result.x
            add(x)

    # The default promotes sparse solutions; inverting avar1 alone gives a
    # better guess when its segment maps depart substantially from identity.
    # Keep the target-as-input guess too, since avar2 can undo that remapping.
    seeds = [
        fixed.copy(),
        np.array(
            [
                _inverseSegment(t, s, lo, hi)
                for t, s, lo, hi in zip(target, mapping.segments, lower, upper)
            ]
        ),
        np.clip(target, lower, upper),
    ]
    # Region peaks escape zero-gradient points of multi-axis tent products.
    peaks = []
    for support in mapping.supports:
        x = fixed.copy()
        for i, _, peak, _ in support:
            if i in free:
                x[i] = _inverseSegment(peak, mapping.segments[i], lower[i], upper[i])
        peaks.append(x)
    peaks.sort(key=lambda x: np.linalg.norm(np.clip(mapping(x)[0], -1, 1) - target))
    seeds.extend(peaks[:8])
    # A few reproducible random starts explore other basins without enumerating
    # the exponentially many region cells. This is not a global-optimum proof.
    rng = np.random.default_rng(0)
    seeds.extend(rng.uniform(lower, upper) for _ in range(4))
    seen = set()
    for seed in seeds:
        seed = np.asarray(seed).copy()
        for i in range(len(axes)):
            if i not in free:
                seed[i] = fixed[i]
        if tuple(seed) in seen:
            continue
        seen.add(tuple(seed))
        solve(seed, free)

    # Try dropping each non-default axis, refitting the others. Accept only
    # candidates within the output-error budget, then repeat after a removal.
    # Refitting matters: simply zeroing a coordinate misses solutions where
    # another axis can take over its contribution. Backward elimination is
    # greedy; finding the sparsest possible subset would be combinatorial.
    while True:
        _, x = best()
        active = [i for i in free if x[i] != 0]
        for i in active:
            seed = x.copy()
            seed[i] = 0
            solve(seed, [j for j in active if j != i])
        if np.count_nonzero(best()[1]) >= np.count_nonzero(x):
            break

    # Refine against the rounded forward map on a small coordinate stencil.
    # One tick in intermediate space is scaled by the local avar1 slope.
    # Differentiating the rounded avar2 mapper mostly gives zero derivatives
    # because of quantization. Instead, use its exact residual only to rank
    # nearby candidates after the continuous solver has located a good basin.
    for _ in range(3):
        error, x = best()
        if error == 0:
            break
        for i in free:
            _, slope = _segment(x[i], mapping.segments[i])
            step = 1 / (16384 * max(abs(slope), 1))
            for offset in (-1, -0.5, 0.5, 1):
                trial = x.copy()
                trial[i] = np.clip(x[i] + offset * step, lower[i], upper[i])
                add(trial)
        if np.array_equal(best()[1], x):
            break

    error, x = best()
    if error > tolerance:
        log.warning(
            "Reverse avar mapping is approximate: normalized residual %g", error
        )
    result = {}
    for axis, value in zip(axes, x):
        if dropZeroes and value == 0:
            continue
        tag = axis.axisTag
        result[tag] = (
            float(value)
            if outputNormalized
            else pinned.get(tag, float(_denormalize(value, triples[tag])))
        )
    return result
