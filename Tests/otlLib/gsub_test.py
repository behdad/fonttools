import random

import pytest

from fontTools.otlLib import builder
from fontTools.otlLib.optimize.gsub import _SingleSubstPlan, compact_single_subst
from fontTools.ttLib import OPTIMIZE_FONT_SPEED, TTFont
from fontTools.ttLib.tables import otTables
from fontTools.ttLib.tables.otBase import OTTableReader, OTTableWriter


def make_font(pairs):
    font = TTFont()
    last = max(max(pair) for pair in pairs)
    font.setGlyphOrder([f"g{i}" for i in range(last + 1)])
    return font


def mapping(pairs):
    return {f"g{a}": f"g{b}" for a, b in pairs}


def compile_lookup(lookup, font):
    writer = OTTableWriter(tableTag="GSUB")
    lookup.compile(writer, font)
    return writer.getAllData()


def roundtrip(lookup, font):
    data = compile_lookup(lookup, font)
    decoded = otTables.Lookup()
    decoded.decompile(OTTableReader(data, tableTag="GSUB"), font)
    actual = {}
    for subtable in decoded.SubTable:
        if decoded.LookupType == 7:
            subtable = subtable.ExtSubTable
        for source, target in subtable.mapping.items():
            actual.setdefault(source, target)
    return actual


def make_lookup(font, blocks, extension=False, mark_filter=False):
    tables = [builder.buildSingleSubstSubtable(mapping(pairs)) for pairs in blocks]
    return builder.buildLookup(
        tables,
        table="GSUB",
        extension=extension,
        markFilterSet=0 if mark_filter else None,
    )


@pytest.mark.parametrize("extension", [False, True])
@pytest.mark.parametrize("speed", [False, True])
@pytest.mark.parametrize("mark_filter", [False, True])
def test_best_score_keeps_residual(extension, speed, mark_filter):
    # Splitting every delta group is smallest in bytes, but extracting just
    # the dominant delta group has the best size/count product.
    pairs = [
        (i, i + 2000 + (0 if i <= 600 else 1 + (i - 601) // 10)) for i in range(1, 1001)
    ]
    font = make_font(pairs)
    font.cfg[OPTIMIZE_FONT_SPEED] = speed
    original = make_lookup(font, [pairs], extension, mark_filter)
    before = compile_lookup(original, font)
    result = compact_single_subst(font, original)
    assert result.SubTableCount == (1 if speed else 2)
    after = compile_lookup(result, font)
    assert len(after) * result.SubTableCount <= len(before)
    if speed:
        assert after == before
    if mark_filter:
        assert result.MarkFilteringSet == 0
        assert result.LookupFlag & 0x0010
    assert roundtrip(result, font) == mapping(pairs)


def test_builder_honors_speed_option():
    pairs = [(i, i + 2000 + (0 if i <= 900 else i)) for i in range(1, 1001)]
    font = make_font(pairs)
    for speed in (False, True):
        font.cfg[OPTIMIZE_FONT_SPEED] = speed
        lookup_builder = builder.SingleSubstBuilder(font, None)
        lookup_builder.mapping.update(mapping(pairs))
        result = lookup_builder.build()
        assert result.SubTableCount == (1 if speed else 2)
        assert roundtrip(result, font) == mapping(pairs)


def test_batch_can_win_after_intermediate_split_loses():
    pairs = [(i, i + 2000 + (i - 1) // 100) for i in range(1, 301)]
    font = make_font(pairs)
    original = make_lookup(font, [pairs])
    before = compile_lookup(original, font)
    result = compact_single_subst(font, original)
    assert result.SubTableCount == 3
    assert len(compile_lookup(result, font)) * 3 < len(before)
    assert roundtrip(result, font) == mapping(pairs)


def test_many_groups_do_not_justify_count_growth():
    pairs = [(i, i + 20000 + (i - 1) // 100) for i in range(1, 10001)]
    font = make_font(pairs)
    original = make_lookup(font, [pairs])
    before = compile_lookup(original, font)
    result = compact_single_subst(font, original)
    assert result.SubTableCount == 1
    assert compile_lookup(result, font) == before


def test_balanced_groups_can_pay_for_count_growth():
    pairs = [(i, i + 2000 + (i - 1) // 100) for i in range(1, 1001)]
    font = make_font(pairs)
    original = make_lookup(font, [pairs])
    before = compile_lookup(original, font)
    result = compact_single_subst(font, original)
    assert result.SubTableCount == 10
    assert len(compile_lookup(result, font)) * 10 < len(before)
    assert roundtrip(result, font) == mapping(pairs)


def test_whole_lookup_count_includes_explicit_blocks():
    common = [(i, i + (100 if i <= 10 else 200)) for i in range(1, 21)]
    extra = [[(i, i + 300)] for i in range(30, 34)]
    font = make_font(common + [pair for block in extra for pair in block])
    standalone = compact_single_subst(font, make_lookup(font, [common]))
    assert standalone.SubTableCount == 1
    lookup_builder = builder.SingleSubstBuilder(font, None)
    for index, block in enumerate([common, *extra]):
        if index:
            lookup_builder.add_subtable_break(index)
        lookup_builder.mapping.update(mapping(block))
    original = make_lookup(font, [common, *extra])
    before = compile_lookup(original, font)
    result = lookup_builder.build()
    assert result.SubTableCount == 6
    assert len(compile_lookup(result, font)) * 6 <= len(before) * 5
    assert roundtrip(result, font) == mapping(common + [p for b in extra for p in b])


def test_batch_spans_multiple_explicit_blocks():
    blocks = [
        [(start + i, start + i + 2000 + (0 if i < 300 else i)) for i in range(500)]
        for start in (1, 1001)
    ]
    font = make_font([p for block in blocks for p in block])
    original = make_lookup(font, blocks)
    before = compile_lookup(original, font)
    result = compact_single_subst(font, original)
    assert result.SubTableCount == 4
    assert len(compile_lookup(result, font)) * 4 <= len(before) * 2
    assert roundtrip(result, font) == mapping([p for block in blocks for p in block])


@pytest.mark.parametrize("extension", [False, True])
def test_suffix_estimates_match_serialization(extension):
    pairs = [(i, i + (70000 if i % 3 else 100)) for i in range(1, 40)] + [
        (70000 + i, i) for i in range(20)
    ]
    font = make_font(pairs)
    subtable = builder.buildSingleSubstSubtable(mapping(pairs))
    plan = _SingleSubstPlan(subtable, font, 10 if extension else 2)
    for index in range(len(plan.groups)):
        suffix = {a: b for group in plan.groups[index:] for _, _, a, b in group}
        lookup = builder.buildLookup(
            [builder.buildSingleSubstSubtable(suffix)],
            table="GSUB",
            extension=extension,
        )
        assert plan.suffix_sizes[index] == len(compile_lookup(lookup, font)) - 6


def test_count_boundary_can_use_narrow_subtables():
    font = TTFont()
    font.setGlyphOrder([f"g{i}" for i in range(0x10001)])
    pairs = [(i, (i + 1) % 0x10000) for i in range(0x10000)]
    result = compact_single_subst(font, make_lookup(font, [pairs]))
    assert result.SubTableCount == 2
    assert roundtrip(result, font) == mapping(pairs)


def test_deterministic_for_mapping_order():
    pairs = [(i, i + 2000 + (i - 1) // 100) for i in range(1, 301)]
    font = make_font(pairs)
    first = compact_single_subst(font, make_lookup(font, [pairs]))
    random.Random(3259).shuffle(pairs)
    second = compact_single_subst(font, make_lookup(font, [pairs]))
    assert compile_lookup(first, font) == compile_lookup(second, font)


def test_empty_lookup():
    font = TTFont()
    font.setGlyphOrder([".notdef"])
    assert builder.SingleSubstBuilder(font, None).build() is None
