"""
Profile-aware conformance
═════════════════════════
TMF630 (conformance.py) checks *generic* design rules. This goes deeper: it detects
which specific TM Forum API a spec is trying to be, then diffs it against the REAL
canonical spec shipped in backend/data/ — reporting the operations and resource
attributes the official API has that the user's spec is missing.

Pure & offline (no LLM): a structural diff between two specs. The corpus of 169+
official TMF specs is the ground truth — that's the part nobody else has.
"""
import glob
import json
import os
import re

from conformance import _iter_ops, _is_collection, _is_notification, _schemas, _schema_props

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_CACHE = os.path.join(_DATA, ".profile_index.json")
# Canonical, modern release files: "...-v4.0.0.swagger.json" / "...-v5.0.0.oas.yaml".
_CANON = re.compile(r"-v(\d+\.\d+\.\d+).*\.(swagger\.json|oas\.ya?ml)$", re.I)
_TMF = re.compile(r"TMF\d{3}", re.I)

_INDEX = None   # in-process cache: primary-resource → canonical metadata


def _load(path):
    try:
        text = open(path, encoding="utf-8", errors="ignore").read()
    except Exception:
        return None
    try:
        return json.loads(text)
    except Exception:
        try:
            import yaml
            return yaml.safe_load(text)
        except Exception:
            return None


def _norm(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{id}", path.lower())


def _ops(spec: dict) -> set:
    """(method, normalized-path) for every non-notification operation."""
    return {(m, _norm(p)) for p, it, m, op in _iter_ops(spec) if not _is_notification(p)}


def _collection_resources(spec: dict):
    """Collection resource names (last non-param segment of collection GET paths), in order."""
    seen, out = set(), []
    for p, it, m, op in _iter_ops(spec):
        if m == "get" and _is_collection(p) and not _is_notification(p):
            seg = [s for s in p.split("/") if s and not s.startswith("{")]
            if seg and seg[-1].lower() not in seen:
                seen.add(seg[-1].lower())
                out.append(seg[-1])
    return out


def _primary_schema(spec: dict, resource: str):
    """The resource's main schema, tolerating case and _Create/_Update/FVO/MVO/Ref suffixes."""
    if not resource:
        return None, None
    schemas = _schemas(spec)
    rl = resource.lower()
    exact = [n for n in schemas if n.lower() == rl]
    if exact:
        return exact[0], schemas[exact[0]]
    base = [n for n in schemas if n.lower() == rl.rstrip("s")
            and not any(s in n for s in ("_Create", "_Update", "FVO", "MVO", "Ref", "Event"))]
    if base:
        return base[0], schemas[base[0]]
    return None, None


def _version_key(v: str):
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def build_index(force: bool = False) -> dict:
    """primary-resource(lower) → {file, version, tmf, title}. Keeps the highest version
    per resource. Cached in-process and on disk (data/.profile_index.json)."""
    global _INDEX
    if _INDEX is not None and not force:
        return _INDEX
    if not force and os.path.exists(_CACHE):
        try:
            _INDEX = json.load(open(_CACHE))
            return _INDEX
        except Exception:
            pass

    idx: dict = {}
    for f in glob.glob(os.path.join(_DATA, "**", "*"), recursive=True):
        base = os.path.basename(f)
        mver = _CANON.search(base)
        if not (os.path.isfile(f) and mver):
            continue
        spec = _load(f)
        if not isinstance(spec, dict):
            continue
        resources = _collection_resources(spec)
        if not resources:
            continue
        tmf = (_TMF.search(base) or [""])
        tmf = tmf.group(0).upper() if hasattr(tmf, "group") else ""
        meta = {
            "file": os.path.relpath(f, _HERE),
            "version": mver.group(1),
            "tmf": tmf,
            "title": (spec.get("info", {}) or {}).get("title", base),
        }
        key = resources[0].lower()                      # primary resource
        cur = idx.get(key)
        if not cur or _version_key(meta["version"]) > _version_key(cur["version"]):
            idx[key] = meta

    _INDEX = idx
    try:
        json.dump(idx, open(_CACHE, "w"))
    except Exception:
        pass
    return idx


def clear_index():
    """Drop the cache (call after the knowledge base is re-ingested)."""
    global _INDEX
    _INDEX = None
    try:
        os.remove(_CACHE)
    except Exception:
        pass


def compare_to_canonical(spec: dict) -> dict:
    """Detect the TMF API and diff against its canonical spec. Returns {'detected': None}
    when the spec doesn't map to a known TMF API."""
    if not isinstance(spec, dict):
        return {"detected": None}
    idx = build_index()
    resources = _collection_resources(spec)
    primary = resources[0] if resources else None
    if not primary:
        return {"detected": None}

    meta = idx.get(primary.lower())
    confidence = "high"
    if not meta:
        # Fall back to an explicit TMF number in the title.
        tok = _TMF.search((spec.get("info", {}) or {}).get("title", ""))
        if tok:
            meta = next((m for m in idx.values() if m["tmf"] == tok.group(0).upper()), None)
            confidence = "medium"
    if not meta:
        return {"detected": None}

    cspec = _load(os.path.join(_HERE, meta["file"]))
    if not isinstance(cspec, dict):
        return {"detected": None}

    cops, uops = _ops(cspec), _ops(spec)
    missing_ops = sorted(cops - uops)
    ops_total = len(cops)
    ops_present = len(cops & uops)

    cn, cs = _primary_schema(cspec, primary)
    un, us = _primary_schema(spec, primary)
    cprops = _schema_props(cspec, cs or {})
    uprops = _schema_props(spec, us or {})
    missing_fields = sorted(f for f in (cprops - uprops) if not f.startswith("@"))
    attrs_total = len(cprops)
    attrs_present = len(cprops & uprops)

    op_cov = (ops_present / ops_total) if ops_total else 1.0
    at_cov = (attrs_present / attrs_total) if attrs_total else 1.0
    coverage = round(100 * (0.5 * op_cov + 0.5 * at_cov))

    return {
        "detected": {
            "tmf": meta["tmf"],
            "title": (cspec.get("info", {}) or {}).get("title", meta["title"]),
            "version": meta["version"],
            "file": os.path.basename(meta["file"]),
            "confidence": confidence,
        },
        "coverage": coverage,
        "operations": {
            "total": ops_total,
            "present": ops_present,
            "missing": [{"method": m.upper(), "path": p} for m, p in missing_ops],
        },
        "resource": {
            "name": cn or (primary[0].upper() + primary[1:]),
            "user_attrs": len(uprops),
            "canonical_attrs": attrs_total,
            "missing": missing_fields,
        },
    }
