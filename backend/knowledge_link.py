"""
Knowledge Engine V2 — corpus-derived entity linking + spec inventory (Phase 7B)
═══════════════════════════════════════════════════════════════════════════════
Derives, from the CANONICAL specification corpus (never hand-maintained):
  • SPEC_PRESENT  — which TMF spec_ids actually have canonical evidence indexed
                    (the authority for honest abstention: a named TMF id absent here
                    must NOT be answered from semantically-near unrelated specs).
  • SPEC_MAJORS   — {spec_id → {major → [canonical files]}} for version-aware retrieval.
  • SCHEMA_MAP    — {schema_name(lower) → {spec_id}} so a bare entity ("Alarm") links to
                    its owning spec(s) (TMF642). Derived from each spec's declared schemas.

Content classification (canonical_spec / tmf_guidance / oda_canvas / test_collection /
non_tmf_external) is filename-deterministic and shared with ingestion (content_class()).

Built once and cached to storage/knowledge_index.json; rebuilt if absent. Pure aside from
the one-time filesystem scan; no Ollama, no network.
"""
from __future__ import annotations
import glob
import json
import os
import re
from functools import lru_cache

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_INDEX_PATH = os.path.join(_HERE, "storage", "knowledge_index.json")

_SPEC_ID = re.compile(r"(TMF)(\d{3})", re.I)
_MAJOR_RE = re.compile(r"v?(\d+)(?:\.\d+){0,3}", re.I)


# ── Deterministic content classification (filename-based; shared with ingest V2) ──────────
_MEF_MARKERS = ("carrierethernet", "ipcommon", "iproutingprotocols", "ovc", "mplify",
                "lso ", "lso-", "bitstreamaccess", "accesseline", "circuitimpairment",
                "servicelevelspecification", "uni", "enni", "sonata", "cantata")
_CANVAS_MARKERS = ("canvas", "componentoperator", "component-operator", "exposedapi",
                   "dependentapi", "oda-component-design", "odacomponentdesign",
                   "manage-component", "deploy-component", "configure-exposed", "about-oda")


def content_class(file_name: str) -> str:
    """canonical_spec | tmf_guidance | oda_canvas | test_collection | non_tmf_external."""
    f = (file_name or "").lower()
    if "postman" in f or ".postman_collection" in f:
        return "test_collection"
    if any(m in f for m in _MEF_MARKERS):
        return "non_tmf_external"
    if f.endswith((".md",)):
        return "oda_canvas" if any(m in f for m in _CANVAS_MARKERS) else "tmf_guidance"
    if f.endswith(".docx"):
        return "tmf_guidance"
    if any(m in f for m in _CANVAS_MARKERS):
        return "oda_canvas"
    if f.endswith((".json", ".yaml", ".yml")) and _SPEC_ID.search(f):
        return "canonical_spec"
    if f.endswith((".json", ".yaml", ".yml")):
        return "non_tmf_external"    # a spec-shaped file with no TMFxxx id is not canonical TMF
    return "tmf_guidance"


def spec_id_of(file_name: str) -> str:
    m = _SPEC_ID.search(file_name or "")
    return (m.group(1) + m.group(2)).upper() if m else ""


def major_of(file_name: str) -> str:
    """Major version parsed from a canonical filename ('...-v4.0.0.swagger.json' → '4')."""
    m = re.search(r"[-_]v(\d+)(?:\.\d+){0,3}", file_name or "", re.I)
    if m:
        return m.group(1)
    m = re.search(r"[_-](\d+)\.\d+\.\d+", file_name or "")
    return m.group(1) if m else ""


def _build_index() -> dict:
    spec_present: set = set()
    spec_majors: dict = {}
    schema_refs: dict = {}     # base schema name → specs that declare it (incl. cross-refs)
    schema_owns: dict = {}     # base schema name → specs that declare {base}_Create (owner)
    files_seen = 0
    try:
        import yaml
    except Exception:
        yaml = None
    for path in glob.glob(os.path.join(_DATA, "**", "*"), recursive=True):
        if not path.lower().endswith((".json", ".yaml", ".yml")):
            continue
        fname = os.path.basename(path)
        if content_class(fname) != "canonical_spec":
            continue
        sid = spec_id_of(fname)
        if not sid:
            continue
        maj = major_of(fname) or "?"
        spec_present.add(sid)
        spec_majors.setdefault(sid, {}).setdefault(maj, []).append(fname)
        files_seen += 1
        try:
            raw = open(path, encoding="utf-8", errors="ignore").read()
            spec = yaml.safe_load(raw) if (yaml and path.lower().endswith((".yaml", ".yml"))) else json.loads(raw)
            if isinstance(spec, dict):
                schemas = (spec.get("components", {}) or {}).get("schemas", {}) or spec.get("definitions", {}) or {}
                names = {str(n).lower() for n in schemas}
                for name in names:
                    base = re.sub(r"_(create|update|mvo|fvo|ref)$", "", name)
                    schema_refs.setdefault(base, set()).add(sid)
                    # A spec OWNS a resource when it declares {resource}_Create — this is the
                    # authoring spec (TMF642 owns Alarm), not a spec that merely cross-refs it.
                    if name.endswith("_create"):
                        schema_owns.setdefault(re.sub(r"_create$", "", name), set()).add(sid)
        except Exception:
            pass
    return {
        "spec_present": sorted(spec_present),
        "spec_majors": {k: {mk: sorted(set(mv)) for mk, mv in v.items()} for k, v in spec_majors.items()},
        "schema_owns": {k: sorted(v) for k, v in schema_owns.items()},
        "schema_refs": {k: sorted(v) for k, v in schema_refs.items()},
        "canonical_files": files_seen,
    }


@lru_cache(maxsize=1)
def _index() -> dict:
    if os.path.exists(_INDEX_PATH):
        try:
            return json.load(open(_INDEX_PATH, encoding="utf-8"))
        except Exception:
            pass
    idx = _build_index()
    try:
        os.makedirs(os.path.dirname(_INDEX_PATH), exist_ok=True)
        json.dump(idx, open(_INDEX_PATH, "w", encoding="utf-8"), indent=1)
    except Exception:
        pass
    return idx


def spec_present(spec_id: str) -> bool:
    """True iff `spec_id` has canonical evidence indexed (authority for abstention)."""
    return (spec_id or "").upper() in set(_index().get("spec_present", []))


def majors_for(spec_id: str) -> list:
    return sorted(k for k in _index().get("spec_majors", {}).get((spec_id or "").upper(), {}) if k != "?")


def files_for(spec_id: str, major: str = None) -> list:
    m = _index().get("spec_majors", {}).get((spec_id or "").upper(), {})
    if major is None:
        return sorted({f for fs in m.values() for f in fs})
    return sorted(m.get(str(major), []))


# A SMALL set of domain aliases for terms that are not literal schema names but
# unambiguously denote a spec's domain (e.g. "fault"/"alarm" → the Alarm API). Kept
# deliberately tiny — the primary linker is the corpus-derived schema map above.
_ALIASES = {
    "fault": ["TMF642"], "alarm": ["TMF642"], "alarms": ["TMF642"],
    "ticket": ["TMF621"], "tickets": ["TMF621"], "troubleticket": ["TMF621"],
    "partyrole": ["TMF669"],
}


def link_schema(name: str) -> list:
    """Candidate spec_ids for a bare entity name. Prefers OWNING specs (those declaring
    {name}_Create — the authoring spec, e.g. Alarm→TMF642), then the broader 'declares the
    schema' set, then a tiny domain-alias fallback. Multiple candidates → genuine ambiguity,
    preserved (never silently collapsed to one)."""
    key = re.sub(r"_(create|update|mvo|fvo|ref)$", "", (name or "").strip().lower())
    idx = _index()
    owners = idx.get("schema_owns", {}).get(key, [])
    if owners:
        return list(owners)
    refs = idx.get("schema_refs", {}).get(key, [])
    if refs:
        return list(refs)
    return [s for s in _ALIASES.get(key, []) if s in set(idx.get("spec_present", []))]


def all_present_specs() -> list:
    return list(_index().get("spec_present", []))
