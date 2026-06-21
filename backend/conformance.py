"""
TMF630 conformance checker
══════════════════════════
Given a user's OpenAPI / Swagger spec (as a dict), run a set of deterministic checks
based on the TM Forum API Design Guidelines (TMF630) and return a structured report.

Pure & offline — no LLM, no network — so it's fast, repeatable, and unit-testable.
Each finding has: id, title, severity (error|warning|info), status (pass|fail), detail,
and up to a few concrete examples of where it applies.
"""
from typing import Any

SEV_WEIGHT = {"error": 2, "warning": 1, "info": 0}


def _schemas(spec: dict) -> dict:
    return (spec.get("components", {}) or {}).get("schemas", {}) or spec.get("definitions", {}) or {}


def _paths(spec: dict) -> dict:
    return spec.get("paths", {}) or {}


def _resolve_ref(spec: dict, ref: str) -> dict:
    node: Any = spec
    for part in ref.lstrip("#/").split("/"):
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}


def _query_params(op: dict, path_item: dict, spec: dict) -> set:
    """Query-param names for an operation, resolving $ref params (common in TMF specs)."""
    names = set()
    for p in (op.get("parameters", []) or []) + (path_item.get("parameters", []) or []):
        if isinstance(p, dict) and "$ref" in p:
            p = _resolve_ref(spec, p["$ref"])
        if isinstance(p, dict) and p.get("in") == "query" and p.get("name"):
            names.add(p["name"])
    return names


def _is_collection(path: str) -> bool:
    """A collection path doesn't end in a path parameter (…/productOrder, not …/{id})."""
    last = [seg for seg in path.split("/") if seg]
    return bool(last) and not (last[-1].startswith("{") and last[-1].endswith("}"))


def _iter_ops(spec: dict):
    for path, item in _paths(spec).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() in ("get", "post", "put", "patch", "delete") and isinstance(op, dict):
                yield path, item, method.lower(), op


def check_spec(spec: dict) -> dict:
    title   = (spec.get("info", {}) or {}).get("title", "Untitled API")
    version = (spec.get("info", {}) or {}).get("version", "")
    schemas = _schemas(spec)
    findings = []

    def finding(fid, title_, severity, ok, detail, examples=None):
        findings.append({
            "id": fid, "title": title_, "severity": severity,
            "status": "pass" if ok else "fail", "detail": detail,
            "examples": (examples or [])[:5],
        })

    coll_gets   = [(p, it, op) for p, it, m, op in _iter_ops(spec) if m == "get" and _is_collection(p)]
    all_gets    = [(p, it, op) for p, it, m, op in _iter_ops(spec) if m == "get"]
    posts       = [(p, it, op) for p, it, m, op in _iter_ops(spec) if m == "post" and _is_collection(p)]
    deletes     = [(p, it, op) for p, it, m, op in _iter_ops(spec) if m == "delete"]

    # R1 — Pagination (offset & limit) on collection GETs
    miss = [p for p, it, op in coll_gets if not {"offset", "limit"} <= _query_params(op, it, spec)]
    finding("pagination", "Collection GETs support offset & limit pagination", "error",
            ok=(bool(coll_gets) and not miss),
            detail=("All collection GET operations declare offset and limit." if coll_gets and not miss
                    else "Add offset and limit query parameters to list endpoints (TMF630 §pagination)."
                    if coll_gets else "No collection GET operations found to check."),
            examples=miss)

    # R2 — Sparse fieldsets (fields) on GETs
    miss = [p for p, it, op in all_gets if "fields" not in _query_params(op, it, spec)]
    finding("fields", "GETs support attribute selection via 'fields'", "error",
            ok=(bool(all_gets) and not miss),
            detail=("All GET operations declare the fields query parameter." if all_gets and not miss
                    else "Add a 'fields' query parameter so clients can request sparse fieldsets."),
            examples=miss)

    # R3 — Sorting (sort) on collection GETs
    miss = [p for p, it, op in coll_gets if "sort" not in _query_params(op, it, spec)]
    finding("sort", "Collection GETs support a 'sort' parameter", "warning",
            ok=(bool(coll_gets) and not miss),
            detail=("Collection GETs declare a sort parameter." if coll_gets and not miss
                    else "Add a 'sort' query parameter for ordering results."),
            examples=miss)

    # R4 — TMF Error structure (an Error schema with code + reason)
    err_ok = any(
        "error" in name.lower() and isinstance(d, dict)
        and {"code", "reason"} <= set((d.get("properties", {}) or {}).keys())
        for name, d in schemas.items()
    )
    finding("error-structure", "Defines the TMF Error structure (code + reason)", "error",
            ok=err_ok,
            detail=("An Error schema with code and reason is defined." if err_ok
                    else "Define a TMF-style Error schema (code, reason, message, status, referenceError)."))

    # R5 — Polymorphism (@type present on resources)
    typed = [n for n, d in schemas.items() if isinstance(d, dict) and "@type" in (d.get("properties", {}) or {})]
    finding("polymorphism", "Resources expose @type for polymorphism", "warning",
            ok=bool(typed),
            detail=(f"{len(typed)} schema(s) declare @type." if typed
                    else "Add @type (and @baseType/@schemaLocation) to resource schemas per TMF630."),
            examples=[n for n in schemas if n not in typed][:5] if not typed else [])

    # R6 — POST returns 201 Created
    miss = [p for p, it, op in posts if "201" not in (op.get("responses", {}) or {})]
    finding("post-201", "POST (create) returns 201", "warning",
            ok=(not posts or not miss),
            detail=("POST operations return 201 Created." if not miss
                    else "Create operations should return 201 with the created resource."),
            examples=miss)

    # R7 — DELETE returns 204
    miss = [p for p, it, op in deletes if "204" not in (op.get("responses", {}) or {})]
    finding("delete-204", "DELETE returns 204", "warning",
            ok=(not deletes or not miss),
            detail=("DELETE operations return 204 No Content." if not miss
                    else "Delete operations should return 204 No Content."),
            examples=miss)

    # R8 — camelCase property names (no snake_case)
    snake = []
    for name, d in schemas.items():
        for prop in (d.get("properties", {}) or {}) if isinstance(d, dict) else {}:
            if "_" in prop and not prop.startswith("@") and not prop.startswith("_"):
                snake.append(f"{name}.{prop}")
    finding("camelcase", "Property names are camelCase", "warning",
            ok=not snake,
            detail=("Property names follow camelCase." if not snake
                    else f"{len(snake)} snake_case property name(s) found; TMF630 requires camelCase."),
            examples=snake)

    # R9 — Versioned (info.version present)
    finding("versioning", "API declares a version", "info",
            ok=bool(version),
            detail=(f"Version {version}." if version else "Add info.version to the spec."))

    # Score — weighted by severity; info rules don't affect the score.
    earned = sum(SEV_WEIGHT[f["severity"]] for f in findings if f["status"] == "pass")
    possible = sum(SEV_WEIGHT[f["severity"]] for f in findings)
    score = round(100 * earned / possible) if possible else 0

    return {
        "api": title,
        "version": version,
        "score": score,
        "summary": {
            "passed":   sum(1 for f in findings if f["status"] == "pass"),
            "failed":   sum(1 for f in findings if f["status"] == "fail" and f["severity"] == "error"),
            "warnings": sum(1 for f in findings if f["status"] == "fail" and f["severity"] == "warning"),
            "total":    len(findings),
        },
        "findings": findings,
    }
