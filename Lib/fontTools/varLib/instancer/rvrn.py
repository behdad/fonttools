"""Make instanced required variation alternates available to static shapers."""

from copy import deepcopy

from fontTools.ttLib.beyond64k import _compact_layout_tables
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.ttVisitor import TTVisitor


class _LookupRemapper(TTVisitor):
    def __init__(self, lookupMap, replacements):
        self.lookupMap = lookupMap
        self.replacements = replacements
        self.seen = set()

    def visit(self, obj, *args, **kwargs):
        # JSTF maximum tables contain GPOS lookups, not GSUB references.
        if isinstance(obj, ot.JstfMax):
            return
        # Layout tables may share subobjects. Remap each reference only once.
        if hasattr(obj, "__dict__") or isinstance(obj, (list, dict)):
            if id(obj) in self.seen:
                return
            self.seen.add(id(obj))
        super().visit(obj, *args, **kwargs)


@_LookupRemapper.register_attr((ot.SubstLookupRecord, ot.SeqLookup), "LookupListIndex")
def visit(visitor, obj, attr, value):
    setattr(obj, attr, visitor.lookupMap[value])


@_LookupRemapper.register_attr(ot.JstfGSUBModList, "GSUBLookupIndex")
def visit(visitor, obj, attr, value):
    indices = sorted({j for i in value for j in visitor.replacements[i]})
    obj.GSUBLookupIndex = indices
    obj.LookupCount = len(indices)


def _instantiateRvrn(font):
    """Move static GSUB rvrn substitutions to ccmp, preserving language scope."""
    if "GSUB" not in font:
        return
    with _compact_layout_tables(font):
        _moveRvrnToCcmp(font)


def _moveRvrnToCcmp(font):
    table = font["GSUB"].table
    if not table.FeatureList or not table.ScriptList:
        return
    # Valid, fully instanced variation records have already been baked. Do not
    # rewrite feature indices in any unsupported records that were retained.
    if getattr(table, "FeatureVariations", None):
        return

    features = table.FeatureList.FeatureRecord
    languages = {}
    for record in table.ScriptList.ScriptRecord:
        script = record.Script
        for lang in [script.DefaultLangSys] + [
            rec.LangSys for rec in script.LangSysRecord
        ]:
            if lang is not None:
                languages[id(lang)] = lang
    referenced = {
        i
        for lang in languages.values()
        for i in [lang.ReqFeatureIndex, *lang.FeatureIndex]
        if i != 0xFFFF
    }
    rvrnFeatures = {i for i in referenced if features[i].FeatureTag == "rvrn"}
    if not rvrnFeatures:
        return

    early = sorted(
        {lookup for i in rvrnFeatures for lookup in features[i].Feature.LookupListIndex}
    )
    other = {
        lookup
        for record in features
        if record.FeatureTag != "rvrn"
        for lookup in record.Feature.LookupListIndex
    }
    exclusive = set(early) - other
    lookups = table.LookupList.Lookup
    remaining = [i for i in range(len(lookups)) if i not in exclusive]
    earlyMap = {old: new for new, old in enumerate(early)}
    lookupMap = {old: new + len(early) for new, old in enumerate(remaining)}
    lookupMap.update({old: earlyMap[old] for old in exclusive})

    # Shapers sort lookups by their global index within a stage. rvrn runs in
    # an earlier stage than ccmp, so concatenating feature indices is not enough.
    # A lookup shared with another feature must still execute in both stages:
    # give its early invocation a separate lookup index.
    table.LookupList.Lookup = [
        deepcopy(lookups[i]) if i in other else lookups[i] for i in early
    ] + [lookups[i] for i in remaining]
    table.LookupList.LookupCount = len(table.LookupList.Lookup)
    replacements = {
        i: {lookupMap[i], earlyMap[i]} if i in earlyMap else {lookupMap[i]}
        for i in range(len(lookups))
    }
    remapper = _LookupRemapper(lookupMap, replacements)
    remapper.visit(table.LookupList)
    if "JSTF" in font:
        remapper.visit(font["JSTF"].table)

    for i, record in enumerate(features):
        mapping = earlyMap if i in rvrnFeatures else lookupMap
        record.Feature = deepcopy(record.Feature)
        record.Feature.LookupListIndex = [
            mapping[index] for index in record.Feature.LookupListIndex
        ]

    combinations = {}

    def combinedFeature(indices, template):
        lookups = tuple(
            sorted(
                {
                    index
                    for i in indices
                    for index in features[i].Feature.LookupListIndex
                }
            )
        )
        key = (lookups, template)
        if key not in combinations:
            record = ot.FeatureRecord()
            record.FeatureTag = "ccmp"
            record.Feature = deepcopy(features[template].Feature)
            record.Feature.LookupListIndex = list(lookups)
            record.Feature.LookupCount = len(lookups)
            combinations[key] = len(features)
            features.append(record)
        return combinations[key]

    for lang in languages.values():
        required = lang.ReqFeatureIndex
        indices = set(lang.FeatureIndex)
        if required != 0xFFFF:
            indices.add(required)
        rvrn = indices & rvrnFeatures
        if not rvrn:
            continue
        ccmp = {i for i in indices if features[i].FeatureTag == "ccmp"}
        if required in rvrn:
            # Keep optional ccmp lookups optional when rvrn was required.
            lang.ReqFeatureIndex = combinedFeature(rvrn, required)
            removed = rvrn
        else:
            template = min(ccmp) if ccmp else min(rvrn)
            combined = combinedFeature(rvrn | ccmp, template)
            removed = rvrn | ccmp
            if required in ccmp:
                lang.ReqFeatureIndex = combined
            else:
                lang.FeatureIndex = [*lang.FeatureIndex, combined]
        lang.FeatureIndex = [i for i in lang.FeatureIndex if i not in removed]
        lang.FeatureCount = len(lang.FeatureIndex)

    # Remove the old tags and sort the FeatureList while remapping both ordinary
    # and required references. Leave unrelated, unused features alone.
    retained = sorted(
        (i for i, rec in enumerate(features) if rec.FeatureTag != "rvrn"),
        key=lambda i: features[i].FeatureTag,
    )
    featureMap = {old: new for new, old in enumerate(retained)}
    table.FeatureList.FeatureRecord = [features[i] for i in retained]
    table.FeatureList.FeatureCount = len(retained)
    for lang in languages.values():
        lang.FeatureIndex = sorted({featureMap[i] for i in lang.FeatureIndex})
        lang.FeatureCount = len(lang.FeatureIndex)
        if lang.ReqFeatureIndex != 0xFFFF:
            lang.ReqFeatureIndex = featureMap[lang.ReqFeatureIndex]
