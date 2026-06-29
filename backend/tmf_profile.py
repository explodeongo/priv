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
import threading

from conformance import _iter_ops, _is_collection, _is_notification, _resolve_ref, _schemas, _schema_props

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_CACHE = os.path.join(_DATA, ".profile_index.json")
# Canonical, modern release files: "...-v4.0.0.swagger.json" / "...-v5.0.0.oas.yaml".
_CANON = re.compile(r"-v(\d+\.\d+\.\d+).*\.(swagger\.json|oas\.ya?ml)$", re.I)
_TMF = re.compile(r"TMF\d{3}", re.I)

_INDEX = None              # in-process cache: primary-resource → canonical metadata
_LOCK = threading.Lock()   # guards the (one-time) index build


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
    with _LOCK:
        if _INDEX is not None and not force:
            return _INDEX
        if not force and os.path.exists(_CACHE):
            try:
                _INDEX = json.load(open(_CACHE))
                return _INDEX
            except Exception:
                pass
        _INDEX = _scan_corpus()
        try:
            json.dump(_INDEX, open(_CACHE, "w"))
        except Exception:
            pass
        return _INDEX


def _scan_corpus() -> dict:
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
    return idx


def warm_index():
    """Build the index in the background so the first real request never stalls."""
    if _INDEX is not None:
        return
    threading.Thread(target=build_index, daemon=True).start()


def _index_nonblocking():
    """Return the index if it's ready (memory or disk cache) WITHOUT a full corpus
    scan; otherwise kick a background build and return None."""
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    if os.path.exists(_CACHE):
        try:
            with _LOCK:
                if _INDEX is None:
                    _INDEX = json.load(open(_CACHE))
            return _INDEX
        except Exception:
            pass
    warm_index()
    return None


def clear_index():
    """Drop the cache (call after the knowledge base is re-ingested)."""
    global _INDEX
    with _LOCK:
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
    idx = _index_nonblocking()
    if idx is None:
        return {"detected": None, "indexing": True}   # first-ever build still warming up
    resources = _collection_resources(spec)
    primary = resources[0] if resources else None
    if not primary:
        return {"detected": None}

    meta = idx.get(primary.lower())
    matched_by = "resource" if meta else None
    if not meta:
        # Fall back to an explicit TMF number in the title.
        tok = _TMF.search((spec.get("info", {}) or {}).get("title", ""))
        if tok:
            meta = next((m for m in idx.values() if m["tmf"] == tok.group(0).upper()), None)
            matched_by = "title" if meta else None
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

    # Honest confidence — guards against a coincidental resource-name clash on a
    # non-TMF API. "high" only when the resource matches AND the user's spec really
    # shares structure with the canonical (so the UI never mislabels a random file).
    overlap = ops_present + attrs_present
    if matched_by == "resource" and attrs_present >= 1 and overlap >= 3:
        confidence = "high"
    elif overlap >= 2:
        confidence = "medium"
    else:
        confidence = "low"

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


# ── Scaffold: complete a partial spec from the canonical one (deterministic) ──────
def _schema_prop_defs(spec: dict, schema, _depth: int = 0) -> dict:
    """{name: definition} for a schema, resolving $ref + allOf composition."""
    if not isinstance(schema, dict) or _depth > 8:
        return {}
    if "$ref" in schema:
        return _schema_prop_defs(spec, _resolve_ref(spec, schema["$ref"]), _depth + 1)
    out = dict(schema.get("properties") or {})
    for sub in (schema.get("allOf") or []) + (schema.get("oneOf") or []) + (schema.get("anyOf") or []):
        for k, v in _schema_prop_defs(spec, sub, _depth + 1).items():
            out.setdefault(k, v)
    return out


_KIND_BY_SEG = {"definitions": "schemas", "schemas": "schemas", "parameters": "parameters", "responses": "responses"}


def _parse_ref(ref):
    """Internal $ref → (kind, name), version-agnostic. None for external refs."""
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    parts = ref.lstrip("#/").split("/")
    if len(parts) < 2:
        return None
    for seg in parts[:-1]:
        if seg in _KIND_BY_SEG:
            return _KIND_BY_SEG[seg], parts[-1]
    return None


def _container(spec: dict, kind: str, create: bool = False):
    """The dict holding components of `kind` in the spec's OWN convention (Swagger-2
    definitions/parameters/responses vs OpenAPI-3 components/*), plus its $ref prefix."""
    if spec.get("swagger") and kind in ("schemas", "parameters", "responses"):
        path = ["definitions"] if kind == "schemas" else [kind]
    else:
        path = ["components", kind]
    d = spec
    for p in path:
        if p not in d:
            if not create:
                return None, "#/" + "/".join(path) + "/"
            d[p] = {}
        d = d[p]
    return (d if isinstance(d, dict) else None), "#/" + "/".join(path) + "/"


def _ensure(cspec: dict, uspec: dict, ref, seen: set, rmap: dict):
    """Copy a referenced component canonical → user, normalised into the user's
    convention, recording a ref-rewrite so nothing is left dangling or mixed."""
    import copy as _copy
    if ref in seen:
        return
    seen.add(ref)
    parsed = _parse_ref(ref)
    if not parsed:
        return
    kind, name = parsed
    csrc, _ = _container(cspec, kind, create=False)
    src = csrc.get(name) if isinstance(csrc, dict) else None
    if src is None:
        return
    udst, upfx = _container(uspec, kind, create=True)
    rmap[ref] = upfx + name
    if isinstance(udst, dict) and name not in udst:
        udst[name] = _copy.deepcopy(src)
        _walk(cspec, uspec, src, seen, rmap)


def _walk(cspec: dict, uspec: dict, node, seen: set, rmap: dict):
    if isinstance(node, dict):
        if isinstance(node.get("$ref"), str):
            _ensure(cspec, uspec, node["$ref"], seen, rmap)
        for v in node.values():
            _walk(cspec, uspec, v, seen, rmap)
    elif isinstance(node, list):
        for v in node:
            _walk(cspec, uspec, v, seen, rmap)


def _apply_rewrites(node, rmap: dict):
    if isinstance(node, dict):
        r = node.get("$ref")
        if isinstance(r, str) and r in rmap:
            node["$ref"] = rmap[r]
        for v in node.values():
            _apply_rewrites(v, rmap)
    elif isinstance(node, list):
        for v in node:
            _apply_rewrites(v, rmap)


def scaffold_from_canonical(spec: dict) -> dict:
    """Deterministically merge the MISSING operations + primary-resource attributes
    (and their referenced schemas) from the detected canonical TMF spec into a copy of
    the user's spec — auto-completing a partial API toward 100% coverage. No LLM."""
    import copy as _copy
    cmp = compare_to_canonical(spec)
    det = cmp.get("detected")
    empty = {"detected": None, "added": {"operations": [], "fields": [], "components": 0}}
    if not det:
        return empty
    idx = _index_nonblocking() or {}
    primary = (_collection_resources(spec) or [None])[0]
    meta = idx.get((primary or "").lower())
    if not meta:
        tok = _TMF.search((spec.get("info", {}) or {}).get("title", ""))
        meta = next((m for m in idx.values() if tok and m["tmf"] == tok.group(0).upper()), None)
    if not meta:
        return empty
    cspec = _load(os.path.join(_HERE, meta["file"]))
    if not isinstance(cspec, dict):
        return empty

    out = _copy.deepcopy(spec)
    seen: set = set()
    rmap: dict = {}
    uschemas, _ = _container(out, "schemas", create=True)
    n_before = len(uschemas or {})

    # 1) Missing operations — copy the canonical path-item operations + their deps.
    user_ops = _ops(out)
    out_paths = out.setdefault("paths", {})
    added_ops = []
    for cpath, citem in (cspec.get("paths") or {}).items():
        if not isinstance(citem, dict) or _is_notification(cpath):
            continue
        for method, cop in citem.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete") or not isinstance(cop, dict):
                continue
            if (method.lower(), _norm(cpath)) in user_ops:
                continue
            uitem = out_paths.setdefault(cpath, {})
            if method not in uitem:
                uitem[method] = _copy.deepcopy(cop)
                added_ops.append(method.upper() + " " + cpath)
                _walk(cspec, out, cop, seen, rmap)
                if isinstance(citem.get("parameters"), list) and "parameters" not in uitem:
                    uitem["parameters"] = _copy.deepcopy(citem["parameters"])
                    _walk(cspec, out, citem["parameters"], seen, rmap)

    # 2) Missing attributes on the primary resource — copy their definitions + deps.
    added_fields = []
    if primary:
        _, us = _primary_schema(out, primary)
        _, cs = _primary_schema(cspec, primary)
        if isinstance(us, dict) and isinstance(cs, dict):
            have = _schema_props(out, us)
            target = us.setdefault("properties", {})
            for name, pdef in _schema_prop_defs(cspec, cs).items():
                if name.startswith("@") or name in have or name in target:
                    continue
                target[name] = _copy.deepcopy(pdef)
                added_fields.append(name)
                _walk(cspec, out, pdef, seen, rmap)

    _apply_rewrites(out, rmap)   # normalise every copied $ref into the user's convention

    return {
        "detected": det,
        "spec": out,
        "added": {
            "operations": added_ops,
            "fields": added_fields,
            "components": max(0, len(uschemas or {}) - n_before),
        },
        "coverage_before": cmp.get("coverage", 0),
        "coverage_after": compare_to_canonical(out).get("coverage", cmp.get("coverage", 0)),
    }
