"""
Knowledge Engine V2 — claim/evidence contracts + constraint precision (Phase 7E)
════════════════════════════════════════════════════════════════════════════════
Phase 7D proved the evidence gate only checked spec_id/version/concept-presence — it never
asked "does this evidence actually PROVE the KIND of claim being made?". So `type: string`
became "UUID/URI", a description became an enum, per-API examples became a normative rule,
and TMF629 (an Open API) became the SID authority.

This module names the CLAIM a question makes, states the evidence CONTRACT that claim
requires (which authority, and what specifically counts), and — for property-constraint
claims — reads the EXACT canonical property definition to report only what is genuinely
present, refusing to invent a format/pattern/enum the schema does not declare.

Pure & offline: canonical schema reading is delegated to spec_facts' deterministic resolver
(the same one behind required-fields facts). No Ollama, no network.
"""
from __future__ import annotations
import enum
import re

import knowledge_authority as A


class ClaimType(enum.Enum):
    PROPERTY_TYPE_CLAIM = "PROPERTY_TYPE_CLAIM"
    PROPERTY_FORMAT_CLAIM = "PROPERTY_FORMAT_CLAIM"
    PROPERTY_PATTERN_CLAIM = "PROPERTY_PATTERN_CLAIM"
    PROPERTY_ENUM_CLAIM = "PROPERTY_ENUM_CLAIM"
    PROPERTY_REQUIREDNESS_CLAIM = "PROPERTY_REQUIREDNESS_CLAIM"
    GLOBAL_DESIGN_RULE_CLAIM = "GLOBAL_DESIGN_RULE_CLAIM"
    SID_FRAMEWORK_CLAIM = "SID_FRAMEWORK_CLAIM"
    ETOM_FRAMEWORK_CLAIM = "ETOM_FRAMEWORK_CLAIM"
    API_DEPENDENCY_CLAIM = "API_DEPENDENCY_CLAIM"
    RUNTIME_CALL_CLAIM = "RUNTIME_CALL_CLAIM"
    COMPONENT_EXPOSURE_CLAIM = "COMPONENT_EXPOSURE_CLAIM"
    SCHEMA_REFERENCE_CLAIM = "SCHEMA_REFERENCE_CLAIM"
    ENTITY_ASSOCIATION_CLAIM = "ENTITY_ASSOCIATION_CLAIM"
    GENERAL_EXPLANATION_CLAIM = "GENERAL_EXPLANATION_CLAIM"


# ── Constraint-keyword detectors (what specific constraint the user is asking about) ────
_CONSTRAINT_KIND = [
    ("format", re.compile(r"\b(format|uuid|guid|uri|url|iso\s*8601|date-?time|email|ipv?[46])\b", re.I)),
    ("pattern", re.compile(r"\b(pattern|regex|regular\s+expression)\b", re.I)),
    ("enum", re.compile(r"\b(enum|enumerat\w+|valid\s+values|allowed\s+values|permitted\s+values|"
                        r"possible\s+values|list\s+of\s+values)\b", re.I)),
    ("length", re.compile(r"\b(minlength|maxlength|max\s*length|min\s*length|length|characters?\s+(max|limit))\b", re.I)),
    ("range", re.compile(r"\b(minimum|maximum|min\s*value|max\s*value|positive|negative|greater\s+than|"
                         r"less\s+than|numeric\s+range)\b", re.I)),
    ("nullable", re.compile(r"\bnullable\b", re.I)),
]
_CONSTRAINT_GENERIC = re.compile(r"\b(constraints?|validation|specific\s+format)\b", re.I)
# Schema keys we treat as genuine validation constraints (a `description` is NOT one).
_CONSTRAINT_KEYS = {"format": ["format"], "pattern": ["pattern"], "enum": ["enum"],
                    "length": ["minLength", "maxLength"],
                    "range": ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"],
                    "nullable": ["nullable"]}
_REQUIREDNESS = re.compile(r"\b(required|mandatory|optional)\b", re.I)


def requested_constraints(question: str) -> list:
    """Which constraint kinds the question asks about (e.g. ['format'] for 'is id a UUID')."""
    q = question or ""
    kinds = [k for k, rx in _CONSTRAINT_KIND if rx.search(q)]
    if not kinds and _CONSTRAINT_GENERIC.search(q):
        kinds = ["format", "pattern", "enum", "length", "range"]   # a generic 'constraints?' sweep
    return kinds


def is_constraint_question(question: str) -> bool:
    """A property-constraint question (format/pattern/enum/length/range/nullable), distinct
    from a plain requiredness/fields question (owned by spec_facts)."""
    return bool(requested_constraints(question))


def classify_claim(question: str, entities: dict = None, relationship_intent=None) -> ClaimType:
    """The KIND of claim `question` makes — governs which evidence contract applies."""
    q = question or ""
    entities = entities or {}
    if A.mentions_sid(q):
        return ClaimType.SID_FRAMEWORK_CLAIM
    if A.mentions_etom(q):
        return ClaimType.ETOM_FRAMEWORK_CLAIM
    if A.is_global_scope(q) or A.asks_design_authority(q):
        return ClaimType.GLOBAL_DESIGN_RULE_CLAIM
    if is_constraint_question(q):
        kinds = requested_constraints(q)
        if "format" in kinds:
            return ClaimType.PROPERTY_FORMAT_CLAIM
        if "pattern" in kinds:
            return ClaimType.PROPERTY_PATTERN_CLAIM
        if "enum" in kinds:
            return ClaimType.PROPERTY_ENUM_CLAIM
        return ClaimType.PROPERTY_FORMAT_CLAIM
    # Relationship claims (mapped from the relationship intent the caller already computed).
    import knowledge_relationships as Rl
    ri = relationship_intent
    if ri == Rl.RelationshipIntent.RUNTIME_CALL_INTENT:
        return ClaimType.RUNTIME_CALL_CLAIM
    if ri in (Rl.RelationshipIntent.DEPENDENCY_INTENT, Rl.RelationshipIntent.INTEGRATION_INTENT):
        return ClaimType.API_DEPENDENCY_CLAIM
    if ri == Rl.RelationshipIntent.EXPOSURE_INTENT:
        return ClaimType.COMPONENT_EXPOSURE_CLAIM
    if ri == Rl.RelationshipIntent.ENTITY_ASSOCIATION_INTENT:
        return ClaimType.ENTITY_ASSOCIATION_CLAIM
    if ri == Rl.RelationshipIntent.REFERENCE_INTENT:
        return ClaimType.SCHEMA_REFERENCE_CLAIM
    if _REQUIREDNESS.search(q):
        return ClaimType.PROPERTY_REQUIREDNESS_CLAIM
    return ClaimType.GENERAL_EXPLANATION_CLAIM


# The evidence contract for each claim: the authority that may prove it + what specifically
# counts (and what explicitly does NOT). Used to validate before generation and to abstain.
REQUIRED_AUTHORITY = {
    ClaimType.PROPERTY_TYPE_CLAIM: A.Authority.OPENAPI_SCHEMA,
    ClaimType.PROPERTY_FORMAT_CLAIM: A.Authority.OPENAPI_SCHEMA,
    ClaimType.PROPERTY_PATTERN_CLAIM: A.Authority.OPENAPI_SCHEMA,
    ClaimType.PROPERTY_ENUM_CLAIM: A.Authority.OPENAPI_SCHEMA,
    ClaimType.PROPERTY_REQUIREDNESS_CLAIM: A.Authority.OPENAPI_SCHEMA,
    ClaimType.GLOBAL_DESIGN_RULE_CLAIM: A.Authority.TMF_DESIGN_GUIDANCE,
    ClaimType.SID_FRAMEWORK_CLAIM: A.Authority.SID_INFORMATION_FRAMEWORK,
    ClaimType.ETOM_FRAMEWORK_CLAIM: A.Authority.ETOM_BUSINESS_PROCESS_FRAMEWORK,
    ClaimType.API_DEPENDENCY_CLAIM: A.Authority.ODA_COMPONENT_CONTRACT,
    ClaimType.RUNTIME_CALL_CLAIM: A.Authority.EXPLICIT_INTEGRATION_EVIDENCE,
    ClaimType.COMPONENT_EXPOSURE_CLAIM: A.Authority.ODA_COMPONENT_CONTRACT,
    ClaimType.SCHEMA_REFERENCE_CLAIM: A.Authority.OPENAPI_SCHEMA,
    ClaimType.ENTITY_ASSOCIATION_CLAIM: A.Authority.OPENAPI_SCHEMA,
    ClaimType.GENERAL_EXPLANATION_CLAIM: A.Authority.GENERAL_TMF_GUIDANCE,
}

ACCEPTABLE_EVIDENCE = {
    ClaimType.PROPERTY_FORMAT_CLAIM: "an explicit `format` on the exact property (`type: string` alone is NOT sufficient)",
    ClaimType.PROPERTY_PATTERN_CLAIM: "an explicit `pattern` on the exact property (a description is NOT sufficient)",
    ClaimType.PROPERTY_ENUM_CLAIM: "an explicit `enum` on the exact property (a description is NOT sufficient)",
    ClaimType.GLOBAL_DESIGN_RULE_CLAIM: "a normative TMF design guideline (multiple Open API specs are NOT sufficient to claim a TM-Forum-wide rule)",
    ClaimType.SID_FRAMEWORK_CLAIM: "a SID / Information-Framework source (an Open API spec such as TMF629 is NOT sufficient)",
    ClaimType.ETOM_FRAMEWORK_CLAIM: "an eTOM / Business Process Framework source",
    ClaimType.API_DEPENDENCY_CLAIM: "an ODA component contract dependentAPI (a schema $ref is NOT sufficient)",
    ClaimType.RUNTIME_CALL_CLAIM: "explicit integration evidence (a relatedEntity/relatedParty association is NOT sufficient)",
    ClaimType.COMPONENT_EXPOSURE_CLAIM: "an ODA component contract exposedAPI",
    ClaimType.SCHEMA_REFERENCE_CLAIM: "an explicit schema reference in the canonical spec",
}


def required_authority_for_claim(claim: ClaimType) -> A.Authority:
    return REQUIRED_AUTHORITY.get(claim, A.Authority.GENERAL_TMF_GUIDANCE)


# ── Generic constraint precision — read the EXACT canonical property, invent nothing ────
def constraint_precision(question: str, entities: dict = None) -> dict:
    """For a property-constraint question, resolve the exact canonical property and report
    only the constraints genuinely present. Returns a dict:
      { resolved: bool, api_id, version, schema, property, present: {constraint: value},
        requested: [kinds], satisfied: {kind: bool}, type, has_description }
    or {'resolved': False} when the spec/property can't be pinned down (caller proceeds to
    normal RAG under the generation guard rather than guessing)."""
    kinds = requested_constraints(question)
    if not kinds:
        return {"resolved": False}
    try:
        import spec_facts as SF
        meta, spec = SF._resolve_spec(question)
        if not spec:
            return {"resolved": False}
        name, sd = SF._match_resource(spec, question)
        if not sd:
            return {"resolved": False}
        props = SF._properties(spec, sd)
        prop, known = SF._extract_target_property(question, set(props), exclude={name, SF._base(name)})
        if not prop or not known:
            return {"resolved": False}
        node = SF._resolve(spec, props[prop]) if isinstance(props.get(prop), dict) else {}
        if not isinstance(node, dict):
            return {"resolved": False}
    except Exception:
        return {"resolved": False}

    present = {}
    for kind, keys in _CONSTRAINT_KEYS.items():
        for k in keys:
            if k in node and node[k] not in (None, "", [], {}):
                present[k] = node[k]
    satisfied = {}
    for kind in kinds:
        satisfied[kind] = any(k in present for k in _CONSTRAINT_KEYS.get(kind, []))
    ptype = node.get("type") or ("array" if "items" in node else "") or ""
    return {
        "resolved": True,
        "api_id": meta.get("tmf", ""), "version": meta.get("version", ""),
        "schema": re.sub(r"_(Create|FVO|MVO|Update)$", "", name), "property": prop,
        "type": ptype, "has_description": bool((node.get("description") or "").strip()),
        "present": present, "requested": kinds, "satisfied": satisfied,
        "source_file": meta.get("file", ""),
    }
