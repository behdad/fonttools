"""Choose SingleSubst partitions using a size/subtable-count tradeoff."""

from collections import defaultdict
from functools import cached_property
from itertools import chain

from fontTools.ttLib import OPTIMIZE_FONT_SPEED
from fontTools.ttLib.tables import otTables


def _suffix_sizes(groups, extended, slot_size):
    """Estimate each suffix's size, including its lookup slot and wrapper.

    Adding glyphs in reverse group order tracks Coverage ranges without
    repeatedly sorting or scanning all the remaining substitutions.
    """
    covered = set()
    deltas16, deltas24 = set(), set()
    count = ranges = max_source = max_glyph = 0
    sizes = [0]
    for group in reversed(groups):
        for source, target, _, _ in group:
            ranges += 1 - (source - 1 in covered) - (source + 1 in covered)
            covered.add(source)
            count += 1
            max_source = max(max_source, source)
            max_glyph = max(max_glyph, source, target)
            deltas16.add((target - source) % 0x10000)
            deltas24.add((target - source) % 0x1000000)
        wide_count = count > 0xFFFF
        width = 3 if extended and (wide_count or max_glyph > 0xFFFF) else 2
        coverage_width = 3 if extended and (wide_count or max_source > 0xFFFF) else 2
        coverage_size = 2 + coverage_width * (1 + min(count, 3 * ranges))
        constant = len(deltas24 if width == 3 else deltas16) == 1
        # Format, Coverage offset, and either delta or substitute count.
        header_size = 9 if width == 3 else 6
        substitutes_size = 0 if constant else width * count
        sizes.append(slot_size + header_size + coverage_size + substitutes_size)
    return sizes[::-1]


class _SingleSubstPlan:
    def __init__(self, subtable, font, slot_size):
        self.original = subtable
        get_id = font.getGlyphID
        rows = [(get_id(a), get_id(b), a, b) for a, b in subtable.mapping.items()]
        extended = font.hasExtendedGlyphIDs()
        wide = extended and (
            len(rows) > 0xFFFF or any(a > 0xFFFF or b > 0xFFFF for a, b, _, _ in rows)
        )
        modulus = 0x1000000 if wide else 0x10000
        by_delta = defaultdict(list)
        for row in rows:
            by_delta[(row[1] - row[0]) % modulus].append(row)
        groups = sorted(
            by_delta.values(), key=lambda group: (-len(group), min(r[0] for r in group))
        )
        if len(groups[0]) == 1:
            # Distinct deltas cannot benefit from separate delta subtables.
            groups = [rows]
        self.groups = groups
        self.extended = extended
        self.slot_size = slot_size

    @cached_property
    def suffix_sizes(self):
        return _suffix_sizes(self.groups, self.extended, self.slot_size)

    @cached_property
    def group_sizes(self):
        return (
            [self.suffix_sizes[0]]
            if len(self.groups) == 1
            else [
                _suffix_sizes([group], self.extended, self.slot_size)[0]
                for group in self.groups
            ]
        )

    def subtables(self, extracted):
        if not extracted:
            return [self.original]
        from fontTools.otlLib.builder import buildSingleSubstSubtable

        groups = self.groups[:extracted] + [
            list(chain.from_iterable(self.groups[extracted:]))
        ]
        return [
            buildSingleSubstSubtable({a: b for _, _, a, b in group}) for group in groups
        ]


def compact_single_subst(font, lookup):
    """Minimize estimated lookup bytes times subtable count over split candidates.

    Candidates extract delta groups largest first and retain a residual
    subtable for each original explicit block. Every prefix is considered:
    an intermediate split can lose even when a later batch wins.
    """
    if lookup is None or font.cfg[OPTIMIZE_FONT_SPEED]:
        return lookup

    extension = lookup.LookupType == 7
    subtables = (
        [st.ExtSubTable for st in lookup.SubTable] if extension else lookup.SubTable
    )
    slot_size = 10 if extension else 2
    plans = [_SingleSubstPlan(st, font, slot_size) for st in subtables]
    events = sorted(
        (
            (-len(group), min(row[0] for row in group), index, position)
            for index, plan in enumerate(plans)
            for position, group in enumerate(plan.groups[:-1])
        )
    )
    if not events:
        return lookup

    # Include the complete lookup header, offsets, and extension wrappers.
    header_size = 8 if lookup.LookupFlag & 0x0010 else 6  # UseMarkFilteringSet
    size = header_size + sum(plan.suffix_sizes[0] for plan in plans)
    count = len(subtables)
    best_size, best_score, best_prefix = size, size * count, 0
    for prefix, (_, _, index, position) in enumerate(events, 1):
        plan = plans[index]
        size += (
            plan.group_sizes[position]
            + plan.suffix_sizes[position + 1]
            - plan.suffix_sizes[position]
        )
        count += 1
        score = size * count
        # Conservatively leave oversized lookups to overflow repair.
        if size <= 0xFFFF and (
            score < best_score or (score == best_score and size < best_size)
        ):
            best_size, best_score, best_prefix = size, score, prefix

    if not best_prefix:
        return lookup
    selected = [0] * len(plans)
    for _, _, index, _ in events[:best_prefix]:
        selected[index] += 1
    result = [
        st for plan, count in zip(plans, selected) for st in plan.subtables(count)
    ]
    if extension:
        wrapped = []
        for subtable in result:
            wrapper = otTables.ExtensionSubst()
            wrapper.Format = 1
            wrapper.ExtensionLookupType = 1
            wrapper.ExtSubTable = subtable
            wrapped.append(wrapper)
        result = wrapped
    lookup.SubTable = result
    lookup.SubTableCount = len(result)
    return lookup
