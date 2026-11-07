from copy import deepcopy
from io import BytesIO

import pytest

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import otTables as ot
from fontTools.varLib import featureVars
from fontTools.varLib.instancer import instantiateVariableFont, main


def makeFont(features="", languages="languagesystem DFLT dflt;"):
    builder = FontBuilder(1000, isTTF=True)
    names = [".notdef", "A", "A.alt", "A.done", "B"]
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({65: "A", 66: "B"})
    builder.setupGlyf({name: TTGlyphPen(None).glyph() for name in names})
    builder.setupHorizontalMetrics({name: (500, 0) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "Static rvrn", "styleName": "Regular"})
    builder.setupOS2(
        sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200
    )
    builder.setupPost()
    builder.setupFvar([("wght", 0, 0, 1, "Weight"), ("wdth", 0, 0, 1, "Width")], [])
    if features:
        addOpenTypeFeaturesFromString(builder.font, languages + features)
    return builder.font


def roundtrip(font):
    stream = BytesIO()
    font.save(stream)
    stream.seek(0)
    return TTFont(stream)


def instance(font):
    return roundtrip(instantiateVariableFont(font, {"wght": 1, "wdth": 0}))


def shape(font, *, features=None, language="en"):
    hb = pytest.importorskip("uharfbuzz")
    stream = BytesIO()
    font.save(stream)
    hbFont = hb.Font(hb.Face(stream.getvalue()))
    buffer = hb.Buffer()
    buffer.add_str("A")
    buffer.direction = "ltr"
    buffer.script = "Latn"
    buffer.language = language
    hb.shape(hbFont, buffer, features)
    return [font.getGlyphName(info.codepoint) for info in buffer.glyph_infos]


def assertStatic(font):
    assert "fvar" not in font
    if "GSUB" not in font:
        return
    table = font["GSUB"].table
    assert not getattr(table, "FeatureVariations", None)
    tags = [record.FeatureTag for record in table.FeatureList.FeatureRecord]
    assert "rvrn" not in tags
    assert tags == sorted(tags)


@pytest.mark.parametrize("inplace", [False, True])
def test_axis_selected_rvrn_activates_without_variable_shaping(inplace):
    font = makeFont()
    featureVars.addFeatureVariations(font, [([{"wght": (0.5, 1)}], {"A": "A.alt"})])
    before = font["GSUB"].compile(font)
    result = instantiateVariableFont(font, {"wght": 1, "wdth": 0}, inplace=inplace)
    assert (result is font) == inplace
    if not inplace:
        assert font["GSUB"].compile(font) == before
    result = roundtrip(result)
    assertStatic(result)
    assert shape(result, features={"rvrn": False}) == ["A.alt"]


@pytest.mark.parametrize("rvrn_first", [False, True])
def test_existing_ccmp_lookup_order(rvrn_first):
    ccmp = "feature ccmp { sub A.alt by A.done; } ccmp;"
    rvrn = "feature rvrn { sub A by A.alt; } rvrn;"
    font = makeFont(rvrn + ccmp if rvrn_first else ccmp + rvrn)
    assert shape(font) == ["A.done"]
    result = instance(font)
    assertStatic(result)
    assert shape(result, features={"rvrn": False}) == ["A.done"]


def test_shared_lookup_keeps_two_executions():
    font = makeFont("""
        lookup Shared { sub A by A.alt; sub A.alt by A.done; } Shared;
        feature ccmp { lookup Shared; } ccmp;
        feature rvrn { lookup Shared; } rvrn;
        """)
    assert shape(font) == ["A.done"]
    result = instance(font)
    assertStatic(result)
    assert shape(result, features={"rvrn": False}) == ["A.done"]


@pytest.mark.parametrize("extension", [False, True])
def test_contextual_lookup_indices_follow_reordering(extension):
    font = makeFont("""
        lookup Finish { sub A.alt by A.done; } Finish;
        lookup Context %s { sub A.alt' lookup Finish; } Context;
        feature ccmp { lookup Context; } ccmp;
        feature rvrn { sub A by A.alt; } rvrn;
        """ % ("useExtension" if extension else ""))
    assert shape(font) == ["A.done"]
    result = instance(font)
    assertStatic(result)
    assert shape(result, features={"rvrn": False}) == ["A.done"]
    lookups = result["GSUB"].table.LookupList.Lookup
    context = next(lookup for lookup in lookups if lookup.LookupType in (5, 7))
    subtable = context.SubTable[0]
    if context.LookupType == 7:
        subtable = subtable.ExtSubTable
    target = lookups[subtable.SubstLookupRecord[0].LookupListIndex]
    assert target.SubTable[0].mapping == {"A.alt": "A.done"}


def languageSystems(font):
    for record in font["GSUB"].table.ScriptList.ScriptRecord:
        script = record.Script
        if script.DefaultLangSys is not None:
            yield record.ScriptTag, "dflt", script.DefaultLangSys
        for lang in script.LangSysRecord:
            yield record.ScriptTag, lang.LangSysTag, lang.LangSys


def test_shared_ccmp_does_not_leak_into_other_languages():
    font = makeFont(
        """
        feature ccmp { sub A.alt by A.done; } ccmp;
        feature rvrn { sub A by A.alt; } rvrn;
        """,
        "languagesystem latn dflt; languagesystem latn TRK; languagesystem cyrl dflt;",
    )
    records = font["GSUB"].table.FeatureList.FeatureRecord
    rvrn = next(i for i, rec in enumerate(records) if rec.FeatureTag == "rvrn")
    for script, language, lang in languageSystems(font):
        if language == "TRK " or script == "cyrl":
            lang.FeatureIndex.remove(rvrn)
            lang.FeatureCount -= 1
    result = instance(font)
    assertStatic(result)
    assert shape(result, features={"rvrn": False}, language="en") == ["A.done"]
    assert shape(result, features={"rvrn": False}, language="tr") == ["A"]
    features = result["GSUB"].table.FeatureList.FeatureRecord
    lookupSets = {}
    for script, language, lang in languageSystems(result):
        ccmp = [
            features[i].Feature.LookupListIndex
            for i in lang.FeatureIndex
            if features[i].FeatureTag == "ccmp"
        ]
        assert len(ccmp) == 1
        lookupSets[(script, language)] = ccmp[0]
    assert lookupSets[("latn", "TRK ")] == lookupSets[("cyrl", "dflt")]
    assert lookupSets[("latn", "dflt")] != lookupSets[("latn", "TRK ")]


@pytest.mark.parametrize("required", ["rvrn", "ccmp", "rlig"])
def test_required_feature_is_preserved(required):
    font = makeFont("""
        feature ccmp { sub A.alt by A.done; } ccmp;
        feature rvrn { sub A by A.alt; } rvrn;
        feature rlig { sub B by A; } rlig;
        """)
    table = font["GSUB"].table
    index = next(
        i
        for i, rec in enumerate(table.FeatureList.FeatureRecord)
        if rec.FeatureTag == required
    )
    lang = table.ScriptList.ScriptRecord[0].Script.DefaultLangSys
    lang.ReqFeatureIndex = index
    lang.FeatureIndex.remove(index)
    lang.FeatureCount -= 1
    result = instance(font)
    assertStatic(result)
    resultTable = result["GSUB"].table
    lang = resultTable.ScriptList.ScriptRecord[0].Script.DefaultLangSys
    expectedTag = "ccmp" if required in ("rvrn", "ccmp") else "rlig"
    assert (
        resultTable.FeatureList.FeatureRecord[lang.ReqFeatureIndex].FeatureTag
        == expectedTag
    )
    assert shape(result, features={"rvrn": False}) == ["A.done"]
    if required == "rvrn":
        assert shape(result, features={"ccmp": False}) == ["A.alt"]
    elif required == "ccmp":
        assert shape(result, features={"ccmp": False}) == ["A.done"]


@pytest.mark.parametrize("variations", [False, True])
def test_partial_then_full_instance(variations):
    font = makeFont("" if variations else "feature rvrn {sub A by A.alt;} rvrn;")
    if variations:
        featureVars.addFeatureVariations(font, [([{"wght": (0.5, 1)}], {"A": "A.alt"})])
    partial = roundtrip(instantiateVariableFont(font, {"wght": 1}))
    assert "fvar" in partial
    assert any(
        rec.FeatureTag == "rvrn"
        for rec in partial["GSUB"].table.FeatureList.FeatureRecord
    )
    # An ordinary rvrn feature also remains untouched while any axis survives.
    if not variations:
        assert not getattr(partial["GSUB"].table, "FeatureVariations", None)
    final = roundtrip(instantiateVariableFont(partial, {"wdth": 0}))
    assertStatic(final)
    assert shape(final, features={"rvrn": False}) == ["A.alt"]


@pytest.mark.parametrize("features", ["", "feature ccmp {sub A by A.alt;} ccmp;"])
def test_no_rvrn_is_unchanged(features):
    font = makeFont(features)
    before = font["GSUB"].compile(font) if "GSUB" in font else None
    result = instance(font)
    assertStatic(result)
    after = result["GSUB"].compile(result) if "GSUB" in result else None
    assert before == after


def test_nonmatching_variation_is_harmless():
    font = makeFont()
    featureVars.addFeatureVariations(font, [([{"wght": (0.5, 1)}], {"A": "A.alt"})])
    result = roundtrip(instantiateVariableFont(font, {"wght": 0, "wdth": 0}))
    assertStatic(result)
    assert shape(result, features={"rvrn": False}) == ["A"]


def table(typ, **fields):
    obj = getattr(ot, typ)()
    obj.__dict__.update(fields)
    obj.populateDefaults()
    return obj


def test_jstf_gsub_references_preserve_split_lookup_roles():
    font = makeFont("""
        lookup Shared { sub A by A.alt; sub A.alt by A.done; } Shared;
        feature ccmp { lookup Shared; } ccmp;
        feature rvrn { lookup Shared; } rvrn;
        lookup Position { pos A 10; } Position;
        feature kern { pos A' lookup Position; } kern;
        """)
    mod = table("JstfGSUBModList", GSUBLookupIndex=[0])
    maximum = table("JstfMax", Lookup=deepcopy(font["GPOS"].table.LookupList.Lookup))
    # Extended positioning contexts also use SeqLookup records, but their
    # indices refer to GPOS and must not follow the GSUB permutation.
    maximum.Lookup[1].LookupType = 7
    maximum.Lookup[1].SubTable = [
        table(
            "ContextPos",
            Format=6,
            GlyphCount=1,
            SeqLookupCount=1,
            Coverage=[table("Coverage", glyphs=["A"])],
            SeqLookupRecord=[table("SeqLookup", SequenceIndex=0, LookupListIndex=0)],
        )
    ]
    priority = table(
        "JstfPriority",
        ShrinkageEnableGSUB=mod,
        ShrinkageDisableGSUB=mod,
        ExtensionEnableGSUB=mod,
        ExtensionDisableGSUB=mod,
        ShrinkageEnableGPOS=table("JstfGPOSModList", GPOSLookupIndex=[0]),
        ShrinkageJstfMax=maximum,
    )
    font["JSTF"] = newTable("JSTF")
    font["JSTF"].table = table(
        "JSTF",
        Version=0x00010000,
        JstfScriptRecord=[
            table(
                "JstfScriptRecord",
                JstfScriptTag="latn",
                JstfScript=table(
                    "JstfScript",
                    DefJstfLangSys=table("JstfLangSys", JstfPriority=[priority]),
                ),
            )
        ],
    )
    result = instance(font)
    assertStatic(result)
    priority = (
        result["JSTF"]
        .table.JstfScriptRecord[0]
        .JstfScript.DefJstfLangSys.JstfPriority[0]
    )
    for attr in (
        "ShrinkageEnableGSUB",
        "ShrinkageDisableGSUB",
        "ExtensionEnableGSUB",
        "ExtensionDisableGSUB",
    ):
        mod = getattr(priority, attr)
        assert mod.GSUBLookupIndex == [0, 1]
        assert mod.LookupCount == 2
    assert priority.ShrinkageEnableGPOS.GPOSLookupIndex == [0]
    context = priority.ShrinkageJstfMax.Lookup[1].SubTable[0]
    assert context.Format == 6
    assert context.SeqLookupRecord[0].LookupListIndex == 0


def test_cli_static_output(tmp_path):
    font = makeFont("feature rvrn {sub A by A.alt;} rvrn;")
    source = tmp_path / "variable.ttf"
    destination = tmp_path / "static.ttf"
    font.save(source)
    main([str(source), "wght=1", "wdth=0", "--output", str(destination)])
    result = TTFont(destination)
    assertStatic(result)
    assert shape(result, features={"rvrn": False}) == ["A.alt"]
