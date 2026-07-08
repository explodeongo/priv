"""
Canonical ODA Component contract resolver (execution-backed conformance, layer A)
════════════════════════════════════════════════════════════════════════════════
Deterministically parses a canonical TM Forum ODA **Component** specification
(`kind: Component`, `apiVersion: oda.tmforum.org/v1`) into a normalized *contract*:
the exposed / dependent / security / management API requirements and their
MANDATORY / OPTIONAL / UNKNOWN status, plus declared events.

This is the ground truth for what a deployed component MUST expose — the input the
CTK result normalizer cross-checks against. It is a SEPARATE conformance mode from the
existing OpenAPI schema engine (conformance.py / tmf_profile.py / oda.py::check_component)
and must not be merged into it.

Pure & offline: no Chroma, no RAG, no LLM, and NOT the cached ODA catalog JSON — the
canonical Component YAML shipped under oda_ctk_assets/standard-components/ is the only
source of truth. Requirement status is read from the canonical `required:` field; it is
never inferred from absence, and template placeholders (dependentAPI_id, exposedAPI_id,
`<...>`, dependentAPI_apiType, …) are identified and excluded from real coverage.
"""
import os
import re

try:
    import yaml
except Exception:                                    # pragma: no cover - yaml is a hard dep in this repo
    yaml = None

_HERE = os.path.dirname(os.path.abspath(__file__))
# Fixed, version-pinned canonical asset directory (vendored from
# tmforum-rand/TMForum-ODA-Ready-for-publication @ v1.0.0). Deterministic + offline.
_CANONICAL_DIR = os.path.join(_HERE, "oda_ctk_assets", "standard-components")
_CANONICAL_SOURCE = ("tmforum-rand/TMForum-ODA-Ready-for-publication@v1.0.0 : "
                     "{component}/Specification/{component}.yaml")

_COMPONENT_ID = re.compile(r"^TMFC\d{3}$")
# Segment (spec.<key>) → normalized segment label.
_SEGMENTS = {"coreFunction": "CORE", "securityFunction": "SECURITY", "managementFunction": "MANAGEMENT"}
# A value is a template placeholder when it still carries the spec skeleton's blanks.
_PLACEHOLDER = re.compile(
    r"^<.*>$|"                                        # <RELEASE_NAME>, <COMPONENT_UNDER_TEST>
    r"(?:^|_)(?:dependent|exposed)api_(?:id|name|version|apitype)$|"  # dependentAPI_id, exposedAPI_id, …
    r"^dependentapi_name$|^exposedapi_id$",
    re.I,
)


def _is_placeholder(*values) -> bool:
    """True if ANY of the given field values is still a spec-skeleton placeholder."""
    for v in values:
        if isinstance(v, str) and _PLACEHOLDER.search(v.strip()):
            return True
    return False


def canonical_path(component_id: str):
    """Absolute path to the vendored canonical YAML for `component_id`, or None."""
    if not component_id:
        return None
    cid = component_id.upper()
    for fname in os.listdir(_CANONICAL_DIR) if os.path.isdir(_CANONICAL_DIR) else []:
        if fname.upper().startswith(cid) and fname.lower().endswith((".yaml", ".yml")):
            return os.path.join(_CANONICAL_DIR, fname)
    return None


def _requirement_status(required_raw):
    """Canonical `required:` → MANDATORY / OPTIONAL / UNKNOWN.
    MANDATORY iff required == true; OPTIONAL iff required == false; UNKNOWN when the
    canonical spec does not establish it (absent/null/unparseable). Never inferred."""
    if isinstance(required_raw, bool):
        return "MANDATORY" if required_raw else "OPTIONAL"
    if isinstance(required_raw, str):
        s = required_raw.strip().lower()
        if s == "true":
            return "MANDATORY"
        if s == "false":
            return "OPTIONAL"
    return "UNKNOWN"


def _declared_version(api: dict):
    """First declared specification version (e.g. 'v4.0.0'), or None."""
    for spec in (api.get("specification") or []):
        if isinstance(spec, dict) and spec.get("version"):
            return str(spec["version"])
    return None


def _spec_url(api: dict):
    for spec in (api.get("specification") or []):
        if isinstance(spec, dict) and spec.get("url"):
            return spec["url"]
    return None


def _api_row(seg_label: str, kind: str, api: dict) -> dict:
    """Normalize one exposed/dependent API entry into a contract requirement row.

    An entry is a *blank* template (`is_placeholder`, excluded from real coverage) when
    its NAME or apiType is still a skeleton placeholder — the whole entry was never
    filled in (e.g. the management dependentAPI: name=dependentAPI_name,
    apiType=dependentAPI_apiType). An entry with a real name+apiType but a placeholder
    ID (the management `metrics`: id=exposedAPI_id, name=metrics, apiType=prometheus) is
    a REAL requirement whose id happens to be templated — recorded via `id_is_placeholder`
    but NOT excluded, so it is still classified (here: OPTIONAL MANAGEMENT prometheus)."""
    api_id = api.get("id")
    name = api.get("name")
    api_type = api.get("apiType")
    version = _declared_version(api)
    blank = _is_placeholder(name) or _is_placeholder(api_type)
    return {
        "id": api_id,
        "name": name,
        "segment": seg_label,
        "kind": kind,                                 # "exposed" | "dependent"
        "api_type": api_type,
        "declared_version": version,
        "spec_url": _spec_url(api),
        "required_raw": api.get("required"),
        "requirement_status": _requirement_status(api.get("required")),
        "is_placeholder": blank,
        "id_is_placeholder": _is_placeholder(api_id),
    }


def _events(spec: dict) -> dict:
    ev = spec.get("eventNotification") or {}
    if not isinstance(ev, dict):
        return {"published": [], "subscribed": []}

    def _norm(items):
        out = []
        for e in (items or []):
            if isinstance(e, dict):
                out.append({"name": e.get("name"), "resources": list(e.get("resources") or [])})
        return out
    return {"published": _norm(ev.get("publishedEvents")), "subscribed": _norm(ev.get("subscribedEvents"))}


def resolve_contract(component_id: str, requested_version: str = None) -> dict:
    """Deterministic normalized contract for `component_id` (canonical YAML is ground
    truth), or a status object explaining why it could not be resolved.

    `status`:
      RESOLVED            — parsed; contract populated.
      UNSUPPORTED         — component_id malformed or not vendored (Phase 1: TMFC043 only).
      VERSION_MISMATCH    — an explicit requested_version ≠ the canonical componentMetadata.version.
      PARSE_ERROR         — the canonical YAML could not be parsed as a Component.

    `exhaustive` is True only when every non-placeholder API requirement resolved to a
    concrete id + version; a genuinely incomplete parse sets it False and lists why in
    `unresolved_items`. (Known template placeholders are recorded in `unresolved_items`
    but do NOT flip exhaustive — they are deterministically identified as blanks, not
    unresolved requirements.)"""
    if not component_id or not _COMPONENT_ID.match(component_id.upper()):
        return {"status": "UNSUPPORTED", "component_id": component_id,
                "reason": "component_id must look like TMFCNNN"}
    cid = component_id.upper()
    path = canonical_path(cid)
    if not path or yaml is None:
        return {"status": "UNSUPPORTED", "component_id": cid,
                "reason": "no vendored canonical component specification for this id"}

    try:
        docs = list(yaml.safe_load_all(open(path, encoding="utf-8", errors="ignore").read()))
        comp = next((d for d in docs if isinstance(d, dict) and d.get("kind") == "Component"), None)
    except Exception as e:
        return {"status": "PARSE_ERROR", "component_id": cid, "reason": f"YAML parse failed: {e}"}
    if not comp:
        return {"status": "PARSE_ERROR", "component_id": cid, "reason": "no kind: Component document found"}

    spec = comp.get("spec") or {}
    meta = spec.get("componentMetadata") or {}
    resolved_version = str(meta.get("version") or "")
    if requested_version and resolved_version and str(requested_version) != resolved_version:
        return {"status": "VERSION_MISMATCH", "component_id": cid,
                "requested_version": requested_version, "resolved_version": resolved_version,
                "reason": "explicit version does not match the canonical component version"}

    exposed, dependent, unresolved = [], [], []
    for seg_key, seg_label in _SEGMENTS.items():
        seg = spec.get(seg_key)
        if not isinstance(seg, dict):
            continue
        for api in (seg.get("exposedAPIs") or []):
            row = _api_row(seg_label, "exposed", api)
            exposed.append(row)
        for api in (seg.get("dependentAPIs") or []):
            row = _api_row(seg_label, "dependent", api)
            dependent.append(row)

    # A non-placeholder API with no concrete id or version means the canonical parse is
    # genuinely incomplete for that requirement → not exhaustive. Blank templates and a
    # real-entry-with-templated-id are recorded but do NOT flip exhaustive.
    for row in exposed + dependent:
        if row["is_placeholder"]:
            unresolved.append({"kind": "placeholder", "segment": row["segment"],
                               "api_kind": row["kind"], "id": row["id"], "name": row["name"]})
        elif not row["id"] or not row["declared_version"]:
            unresolved.append({"kind": "incomplete", "segment": row["segment"],
                               "api_kind": row["kind"], "id": row["id"], "name": row["name"]})
        elif row.get("id_is_placeholder"):
            unresolved.append({"kind": "placeholder_id", "segment": row["segment"],
                               "api_kind": row["kind"], "id": row["id"], "name": row["name"]})

    exhaustive = not any(u["kind"] == "incomplete" for u in unresolved)

    real_dependent = [d for d in dependent if not d["is_placeholder"]]
    mandatory = [r for r in exposed if r["requirement_status"] == "MANDATORY" and not r["is_placeholder"]]
    optional = [r for r in exposed if r["requirement_status"] == "OPTIONAL" and not r["is_placeholder"]]

    return {
        "status": "RESOLVED",
        "source": _CANONICAL_SOURCE.format(component=os.path.basename(path).rsplit(".", 1)[0]),
        "component_id": cid,
        "requested_version": requested_version,
        "resolved_version": resolved_version,
        "exhaustive": exhaustive,
        "unresolved_items": unresolved,
        "component": {
            "id": meta.get("id") or cid,
            "name": meta.get("name"),
            "version": resolved_version,
            "status": meta.get("status"),
            "publicationDate": str(meta.get("publicationDate")) if meta.get("publicationDate") else None,
            "functionalBlock": meta.get("functionalBlock"),
            "format": comp.get("apiVersion"),
        },
        "requirements": {
            "exposed": exposed,
            "dependent": dependent,
            "mandatory_exposed": mandatory,
            "optional_exposed": optional,
            "real_dependent": real_dependent,
            "events": _events(spec),
        },
    }


def mandatory_api_coverage(contract: dict) -> list:
    """The mandatory API requirements the CTK framework can actually execute — i.e.
    mandatory EXPOSED APIs whose apiType is a TMF Open API ('openapi'). A Prometheus
    'metrics' management endpoint is NOT a TMF API CTK and is excluded from mandatory
    coverage even if it were marked required. Returns [{id, segment, declared_version}]."""
    out = []
    for r in contract.get("requirements", {}).get("mandatory_exposed", []):
        if (r.get("api_type") or "").lower() == "openapi":
            out.append({"id": r["id"], "segment": r["segment"], "declared_version": r["declared_version"]})
    return out
