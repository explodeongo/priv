"""
Knowledge Engine V2 — authority model + availability + resolution (Phase 7E)
════════════════════════════════════════════════════════════════════════════
The Phase 7D audit proved SynaptDI had NO representation of *which source has the right
to define an answer*: an Open API spec was silently promoted to SID authority, per-API
implementations were generalized into normative TM-Forum-wide rules, and confidence was
pure retrieval distance. This module introduces the missing concept — an explicit, CLOSED
set of authority classes, the semantics of what each class may and may NOT define, a
DETERMINISTIC availability inventory (never inferred from embedding distance), and a
resolver that decides which authority a question requires and whether it is present.

Pure & offline: reads only the canonical corpus inventory (knowledge_link) and the data/
filesystem once (cached). No Ollama, no ChromaDB, no network. An LLM never decides whether
an authoritative deterministic source exists — this module does, from corpus facts.
"""
from __future__ import annotations
import enum
import os
import re
from functools import lru_cache

import knowledge_link as L

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_ODA_COMPONENTS = os.path.join(_HERE, "oda_components.json")


# ── Closed authority set ───────────────────────────────────────────────────────────────
class Authority(enum.Enum):
    OPENAPI_SCHEMA = "OPENAPI_SCHEMA"                       # a resource schema's fields/constraints
    OPENAPI_OPERATION = "OPENAPI_OPERATION"                 # a spec's paths/operations
    OPENAPI_SPEC = "OPENAPI_SPEC"                           # a spec's identity/scope
    ODA_COMPONENT_CONTRACT = "ODA_COMPONENT_CONTRACT"       # component exposed/mandatory/dependent/events
    TMF_DESIGN_GUIDANCE = "TMF_DESIGN_GUIDANCE"             # normative cross-API REST design rules
    SID_INFORMATION_FRAMEWORK = "SID_INFORMATION_FRAMEWORK" # SID ABEs / information-model hierarchy
    ETOM_BUSINESS_PROCESS_FRAMEWORK = "ETOM_BUSINESS_PROCESS_FRAMEWORK"  # eTOM processes
    EXPLICIT_INTEGRATION_EVIDENCE = "EXPLICIT_INTEGRATION_EVIDENCE"      # documented API↔API interaction
    GENERAL_TMF_GUIDANCE = "GENERAL_TMF_GUIDANCE"          # ODA-Canvas / general guidance prose
    UNKNOWN_AUTHORITY = "UNKNOWN_AUTHORITY"


class Scope(enum.Enum):
    GLOBAL = "GLOBAL"            # a TM-Forum-wide normative claim
    FRAMEWORK = "FRAMEWORK"      # a whole framework (SID / eTOM)
    SPEC = "SPEC"               # one named Open API spec
    VERSION = "VERSION"         # one major version of a spec
    SCHEMA = "SCHEMA"           # one resource schema
    PROPERTY = "PROPERTY"       # one property of a schema
    COMPONENT = "COMPONENT"     # one ODA component
    RELATIONSHIP = "RELATIONSHIP"  # a relationship between entities


class Availability(enum.Enum):
    AVAILABLE = "AVAILABLE"        # authority class present in the indexed corpus / resolver
    UNAVAILABLE = "UNAVAILABLE"    # not present — must abstain, never substitute a lower class
    CONDITIONAL = "CONDITIONAL"    # present only when a specific question yields explicit evidence


# ── What each authority class MAY and MAY NOT define (documented + testable) ────────────
AUTHORITATIVE_FOR = {
    Authority.OPENAPI_SCHEMA: (
        "property type", "property format", "property pattern", "property enum",
        "requiredness within that exact schema", "array/item shape", "schema references"),
    Authority.OPENAPI_OPERATION: ("operations", "paths", "HTTP methods", "query parameters of a spec"),
    Authority.OPENAPI_SPEC: ("spec identity", "spec domain/scope", "spec version set"),
    Authority.ODA_COMPONENT_CONTRACT: (
        "component identity", "component version", "functional block", "exposed APIs",
        "mandatory APIs", "dependent APIs", "published events", "subscribed events"),
    Authority.TMF_DESIGN_GUIDANCE: ("normative cross-API design rules",),
    Authority.SID_INFORMATION_FRAMEWORK: ("SID concepts", "ABEs", "information-model hierarchy"),
    Authority.ETOM_BUSINESS_PROCESS_FRAMEWORK: ("business process framework facts",),
    Authority.EXPLICIT_INTEGRATION_EVIDENCE: (
        "documented API-to-API interaction patterns",
        "runtime integration claims only when explicitly stated"),
    Authority.GENERAL_TMF_GUIDANCE: ("general ODA-Canvas / guidance narrative",),
    Authority.UNKNOWN_AUTHORITY: (),
}

NOT_AUTHORITATIVE_FOR = {
    Authority.OPENAPI_SCHEMA: (
        "global TM Forum design rules", "SID ABE definitions", "eTOM processes",
        "runtime API dependencies", "constraints the schema does not explicitly declare"),
    Authority.OPENAPI_OPERATION: ("global design rules", "runtime dependencies on other APIs"),
    Authority.OPENAPI_SPEC: ("SID authority", "eTOM authority", "normative cross-API rules"),
    Authority.ODA_COMPONENT_CONTRACT: (
        "OpenAPI property constraints", "runtime invocation by every operation",
        "SID entity hierarchy"),
    Authority.TMF_DESIGN_GUIDANCE: ("per-schema field constraints", "component contracts"),
    Authority.SID_INFORMATION_FRAMEWORK: ("REST operations", "OpenAPI field constraints"),
    Authority.ETOM_BUSINESS_PROCESS_FRAMEWORK: ("REST API operations", "OpenAPI field constraints"),
    Authority.EXPLICIT_INTEGRATION_EVIDENCE: ("dependencies inferred from schema references alone",),
    Authority.GENERAL_TMF_GUIDANCE: (
        "normative design rules", "SID authority", "eTOM authority", "schema constraints"),
    Authority.UNKNOWN_AUTHORITY: (),
}


# ── Deterministic availability inventory ────────────────────────────────────────────────
# A framework/design AUTHORITY is present ONLY when there is a genuine authority asset for it:
#   • DESIGN  — the normative REST guideline is indexed as a canonical spec (spec_present TMF630).
#   • SID/eTOM — an EXPLICIT provenance registration (data/authority_sources.json), because
#     those frameworks have no TMFxxx id to detect and Phase 7D proved the markdown corpus is
#     ODA-Canvas ADR material, NOT SID/eTOM authority. Fuzzy filename matching is deliberately
#     rejected — it would re-commit the exact 7D error (treating "…design…"/"…sid…" prose as an
#     authority). Drop a real source in the registry (or vendor TMF630) and availability flips.
_REGISTRY = os.path.join(_DATA, "authority_sources.json")


@lru_cache(maxsize=1)
def _registered_authorities() -> set:
    """Authority classes explicitly registered as having a genuine indexed source. Empty now
    (no registry file) → SID/eTOM absent, matching Phase 7D. Future-proof, deterministic."""
    import json
    try:
        data = json.load(open(_REGISTRY, encoding="utf-8"))
        return {k for k, v in data.items() if v}
    except Exception:
        return set()


@lru_cache(maxsize=1)
def authority_inventory() -> dict:
    """Deterministic map {Authority: Availability}, derived once from actual corpus/runtime
    capabilities. This is the single source of truth for 'does the required authority exist?'."""
    reg = _registered_authorities()
    openapi = Availability.AVAILABLE if L.all_present_specs() else Availability.UNAVAILABLE
    oda = Availability.AVAILABLE if os.path.exists(_ODA_COMPONENTS) else Availability.UNAVAILABLE
    design = (Availability.AVAILABLE
              if (L.spec_present("TMF630") or Authority.TMF_DESIGN_GUIDANCE.value in reg)
              else Availability.UNAVAILABLE)
    sid = (Availability.AVAILABLE if Authority.SID_INFORMATION_FRAMEWORK.value in reg
           else Availability.UNAVAILABLE)
    etom = (Availability.AVAILABLE if Authority.ETOM_BUSINESS_PROCESS_FRAMEWORK.value in reg
            else Availability.UNAVAILABLE)
    return {
        Authority.OPENAPI_SCHEMA: openapi,
        Authority.OPENAPI_OPERATION: openapi,
        Authority.OPENAPI_SPEC: openapi,
        Authority.ODA_COMPONENT_CONTRACT: oda,
        Authority.TMF_DESIGN_GUIDANCE: design,
        Authority.SID_INFORMATION_FRAMEWORK: sid,
        Authority.ETOM_BUSINESS_PROCESS_FRAMEWORK: etom,
        # Explicit interaction evidence is only ever proven per-question, never statically.
        Authority.EXPLICIT_INTEGRATION_EVIDENCE: Availability.CONDITIONAL,
        Authority.GENERAL_TMF_GUIDANCE: Availability.AVAILABLE,
        Authority.UNKNOWN_AUTHORITY: Availability.UNAVAILABLE,
    }


def authority_available(authority: Authority) -> Availability:
    return authority_inventory().get(authority, Availability.UNAVAILABLE)


def is_present(authority: Authority) -> bool:
    """True only when an answer may be grounded in this authority (AVAILABLE). CONDITIONAL
    and UNAVAILABLE both mean 'do not substitute this for a required higher authority'."""
    return authority_available(authority) is Availability.AVAILABLE


def inventory_report() -> dict:
    """JSON-serialisable inventory for /health · /stats (no frontend work)."""
    return {a.value: authority_available(a).value for a in Authority}


# ── Shared question-shape detectors (keyword-anchored; the LLM never classifies) ────────
# GLOBAL = a TM-Forum-wide generalization. Two independent signals:
#  • a QUANTIFIER over APIs/ids ("all/every ... APIs", "across ... APIs", "globally", "...
#    standard") — present regardless of named ids (Phase 7D D-bait), OR
#  • the COLLECTIVE phrase ("TM Forum Open APIs" / "TM Forum APIs" / "TM Forum API
#    collections/resources") — the APIs are the SCOPE of a rule.
# A single-API IDENTITY question ("which TM Forum API DEFINES/MANAGES X") is explicitly NOT
# global — the API is the answer being sought, not the scope of a rule.
_GLOBAL_QUANT = re.compile(
    r"\b(all|every|each)\b[^.?]{0,40}\bapis?\b"
    r"|\bacross\b[^.?]{0,40}\bapis?\b"
    r"|\bglobally\b|\btm\s*forum\s+standard\b"
    r"|\b(all|every)\b[^.?]{0,30}\bids?\b"
    r"|\ball\s+tm\s*forum\b", re.I)
_GLOBAL_COLLECTIVE = re.compile(
    r"\btm\s*forum\s+open\s+apis?\b|\btm\s*forum\s+apis\b"
    r"|\btm\s*forum\s+api\s+(collections?|resources?|responses?)\b", re.I)
_SINGLE_API_IDENTITY = re.compile(
    r"\bwhich\b[^?]{0,30}\bapis?\b\s+(define\w*|manage\w*|handle\w*|provide\w*|cover\w*|"
    r"own\w*|support\w*|is|are|do|does|has|have)\b", re.I)
# A request for the normative DESIGN AUTHORITY itself (guideline / rules / principles).
_DESIGN_AUTHORITY = re.compile(
    r"\bnormative\b|\bdesign\s+guidelines?\b|\bdesign\s+rules?\b|\brest\s+api\s+design\b|"
    r"\bdesign\s+principles?\b|\bwhich\s+document\s+defines\b", re.I)
# A design-rule TOPIC — the cross-API concerns that only a normative guideline can settle.
_DESIGN_TOPIC = re.compile(
    r"\b(paginat\w*|offset|limit|zero-?based|0-?based|href|hypermedia|patch|"
    r"field\s*select\w*|sort\w*|filter\w*|error\s*(format|represent\w*|handling)|"
    r"status\s*code|uniqueness|globally\s*unique|id\s*format)\b", re.I)
# SID / Information Framework.
_SID = re.compile(r"\bSID\b|\binformation\s+framework\b|\binformation\s+model\b|\bABE\b|"
                  r"\baggregate\s+business\s+entit\w+\b", re.I)
# eTOM / Business Process Framework.
_ETOM = re.compile(r"\beTOM\b|\bbusiness\s+process\s+framework\b|\bbusiness\s+process\b", re.I)


def is_global_scope(question: str) -> bool:
    q = question or ""
    if _GLOBAL_QUANT.search(q):
        return True
    if _GLOBAL_COLLECTIVE.search(q) and not _SINGLE_API_IDENTITY.search(q):
        return True
    return False


def asks_design_authority(question: str) -> bool:
    """A request for the normative TM Forum design guideline/rules themselves (absent authority)."""
    return bool(_DESIGN_AUTHORITY.search(question or ""))


def is_design_topic(question: str) -> bool:
    return bool(_DESIGN_TOPIC.search(question or ""))


def mentions_sid(question: str) -> bool:
    return bool(_SID.search(question or ""))


def mentions_etom(question: str) -> bool:
    return bool(_ETOM.search(question or ""))


def resolve_required_authority(question: str, entities: dict = None,
                               router_intent: str = "", context: dict = None) -> dict:
    """Deterministically decide which authority class has the RIGHT to answer `question`,
    at what scope, and whether that authority is actually present.

    Returns { required_authority: Authority, scope: Scope, reason: str,
              allow_fallback: bool, authority_available: Availability }.
    `allow_fallback` is True only for ordinary entity-scoped facts, where general RAG over
    the named spec is the intended path; it is False whenever a specific higher authority is
    required, so the caller must abstain rather than substitute a lower-authority source."""
    q = question or ""
    entities = entities or {}
    tmf_ids = entities.get("tmf_ids") or []
    oda_ids = entities.get("oda_ids") or []

    def result(auth: Authority, scope: Scope, reason: str, allow_fallback: bool):
        return {"required_authority": auth, "scope": scope, "reason": reason,
                "allow_fallback": allow_fallback, "authority_available": authority_available(auth)}

    # 1. Framework authority (SID / eTOM) — highest-priority mis-attribution risk. A SID/ABE
    #    question is owned by the SID Information Framework even when an Open API id is named
    #    (that id is NOT automatically the SID authority — Phase 7D SID→TMF629 defect).
    if mentions_sid(q):
        return result(Authority.SID_INFORMATION_FRAMEWORK, Scope.FRAMEWORK,
                      "SID / Information-Framework concept (ABE, information model)", False)
    if mentions_etom(q):
        return result(Authority.ETOM_BUSINESS_PROCESS_FRAMEWORK, Scope.FRAMEWORK,
                      "eTOM / Business Process Framework concept", False)

    # 2. Global normative claim (or a request for the design authority itself) — only a TMF
    #    design guideline can settle a TM-Forum-wide rule; per-API specs cannot (Phase 7D
    #    global-rule / cross-spec-generalization / guideline-vs-impl defects).
    if is_global_scope(q) or asks_design_authority(q):
        return result(Authority.TMF_DESIGN_GUIDANCE, Scope.GLOBAL,
                      "TM-Forum-wide normative rule / normative design authority", False)

    # 3. ODA component contract facts (named component + contract intent) — deterministic
    #    resolver territory. The knowledge_router usually answers these before we get here.
    if oda_ids and router_intent in ("ODA_COMPONENT_CONTRACT", "ODA_API_RELATIONSHIP"):
        return result(Authority.ODA_COMPONENT_CONTRACT, Scope.COMPONENT,
                      "named ODA component contract fact", False)

    # 4. Otherwise an entity-scoped Open API question (schema / operation / spec). General
    #    RAG over the named spec is the intended, Phase-7C-correct path → allow_fallback.
    if tmf_ids:
        if router_intent == "SPEC_OPERATIONS":
            return result(Authority.OPENAPI_OPERATION, Scope.SPEC, "named-spec operations", True)
        return result(Authority.OPENAPI_SPEC, Scope.SPEC, "named-spec explanation/identity", True)

    return result(Authority.UNKNOWN_AUTHORITY, Scope.GLOBAL,
                  "no authoritative entity resolved", True)
