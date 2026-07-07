"""
ODA Component conformance
═════════════════════════
An ODA Component (TM Forum Open Digital Architecture) is a standardized building block
defined by a manifest (`*.component.yaml`, `kind: Component`) that declares the TMF Open
APIs it **exposes** and **depends on**, grouped by function segment (core / management /
security / notification — the hexagon in the ODA spec).

Since SynaptDI already validates TMF Open APIs, it lifts naturally from *API* conformance
to *Component* conformance: parse a component manifest → resolve each exposed OpenAPI to
its spec → run the deterministic TMF630 + profile engine → roll up a component-level
report. Pure & offline. This is the machine behind "ODA Component Conformance".
"""
import glob
import json
import os
import re

import conformance
import tmf_profile

try:
    import yaml
except Exception:
    yaml = None

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA = os.path.join(_HERE, "data")
_TMF = re.compile(r"TMF\d{3}", re.I)


def _load_spec(path):
    text = open(path, encoding="utf-8", errors="ignore").read()
    try:
        return json.loads(text)
    except Exception:
        return yaml.safe_load(text) if yaml else None


def _spec_url(api: dict) -> str:
    s = api.get("specification")
    if isinstance(s, list) and s:
        s = s[0]
    if isinstance(s, dict):
        return s.get("url") or s.get("$ref") or ""
    return s or ""


def _tmf_of(api: dict) -> str:
    m = _TMF.search(json.dumps(api))
    return m.group(0).upper() if m else ""


def _find_local(url: str, tmf: str):
    """Resolve an exposed API to a spec file shipped in backend/data (offline)."""
    if url:
        base = url.rsplit("/", 1)[-1]
        for f in glob.glob(os.path.join(_DATA, "**", base), recursive=True):
            return f
    if tmf:
        for pat in (tmf + "*swagger*.json", tmf + "*.oas.y*ml", tmf + "*.json", tmf + "*.y*ml"):
            hits = sorted(glob.glob(os.path.join(_DATA, "**", pat), recursive=True))
            if hits:
                return hits[0]
    return None


def _collect(spec: dict):
    """Every exposed/dependent API across the component's function segments."""
    exposed, dependent = [], []
    for seg, val in spec.items():
        if isinstance(val, dict):
            for a in (val.get("exposedAPIs") or []):
                exposed.append((seg, a))
            for a in (val.get("dependentAPIs") or []):
                dependent.append((seg, a))
    for a in (spec.get("exposedAPIs") or []):      # older/top-level manifests
        exposed.append(("component", a))
    for a in (spec.get("dependentAPIs") or []):
        dependent.append(("component", a))
    return exposed, dependent


def check_component(text: str) -> dict:
    """Parse an ODA Component manifest and score each exposed OpenAPI it declares."""
    comp = None
    try:
        for d in (yaml.safe_load_all(text.replace("\x00", "")) if yaml else []):
            if isinstance(d, dict) and d.get("kind") == "Component":
                comp = d
                break
    except Exception:
        return {"component": None, "error": "Could not parse the component manifest (invalid YAML)."}
    if not comp:
        return {"component": None, "error": "Not an ODA Component manifest (kind: Component)."}

    spec = comp.get("spec") or {}
    name = spec.get("name") or (comp.get("metadata") or {}).get("name") or "component"
    ex_raw, dep_raw = _collect(spec)

    exposed = []
    for seg, a in ex_raw:
        if a.get("apiType") != "openapi":
            continue
        url, tmf = _spec_url(a), _tmf_of(a)
        local = _find_local(url, tmf)
        row = {"name": a.get("name"), "segment": seg, "tmf": tmf, "resolved": bool(local)}
        if local:
            sp = _load_spec(local)
            if isinstance(sp, dict):
                rep = conformance.check_spec(sp)
                row["score"] = rep.get("score")
                row["api"] = rep.get("api")
                prof = tmf_profile.compare_to_canonical(sp)
                row["coverage"] = prof["coverage"] if prof.get("detected") else None
        exposed.append(row)

    dependent = [{"name": a.get("name"), "segment": seg, "tmf": _tmf_of(a)}
                 for seg, a in dep_raw if a.get("apiType") == "openapi"]

    scored = [r for r in exposed if isinstance(r.get("score"), int)]
    summary = {
        "component": name,
        "exposed_openapi": len(exposed),
        "dependent_openapi": len(dependent),
        "scored": len(scored),
        "avg_score": round(sum(r["score"] for r in scored) / len(scored)) if scored else 0,
        "all_conformant": bool(scored) and all(r["score"] >= 90 for r in scored),
    }
    return {"component": name, "summary": summary, "exposed": exposed, "dependent": dependent}


def render_markdown(report: dict) -> str:
    if not report.get("component"):
        return "Not a recognisable ODA Component manifest."
    s = report["summary"]
    out = [
        "# ODA Component conformance — %s" % report["component"],
        "",
        "_Deterministic TM Forum analysis of the component's exposed Open APIs, no AI._",
        "",
        "**%d exposed OpenAPI(s)** · %d dependent · avg TMF630 score **%d/100** · verdict: **%s**"
        % (s["exposed_openapi"], s["dependent_openapi"], s["avg_score"],
           "ODA-conformant" if s["all_conformant"] else "gaps found"),
        "",
        "| Exposed API | TMF | Function segment | TMF630 score | Coverage |",
        "|---|---|---|---|---|",
    ]
    for r in report["exposed"]:
        score = ("%d/100" % r["score"]) if isinstance(r.get("score"), int) else ("— (spec not found)" if not r["resolved"] else "—")
        cov = ("%d%%" % r["coverage"]) if isinstance(r.get("coverage"), int) else "—"
        out.append("| %s | %s | %s | %s | %s |" % (r.get("name"), r.get("tmf") or "—", r.get("segment"), score, cov))
    if report["dependent"]:
        out += ["", "**Depends on:** " + ", ".join("%s (%s)" % (d["name"], d["tmf"] or "?") for d in report["dependent"])]
    return "\n".join(out)


# ── ODA Component catalog (the components map) ────────────────────────────────
_CATALOG_FILE = os.path.join(_HERE, "oda_components.json")
_CATALOG = None   # cached, enriched catalog


def _manifest_apis():
    """{manifest-name(lower): {exposed, dependent}} from the plain (non-Helm) component
    manifests shipped in the ingested reference-example-components repo."""
    out = {}
    for f in glob.glob(os.path.join(_DATA, "reference-example-components", "source", "*", "*.component.yaml")):
        try:
            text = open(f, encoding="utf-8", errors="ignore").read()
            if "{{" in text:                       # Helm-templated → not plain YAML
                continue
            # The repo organizes manifests one directory per component — the directory
            # name (e.g. source/ProductInventory/) is the reliable component key.
            dirname = os.path.basename(os.path.dirname(f)).lower().replace("-", "")
            for d in yaml.safe_load_all(text.replace("\x00", "")):
                if not (isinstance(d, dict) and d.get("kind") == "Component"):
                    continue
                spec = d.get("spec") or {}
                ex_raw, dep_raw = _collect(spec)
                apis = {
                    "exposed": [{"name": a.get("name"), "segment": seg, "tmf": _tmf_of(a)}
                                for seg, a in ex_raw if a.get("apiType") == "openapi"],
                    "dependent": [{"name": a.get("name"), "tmf": _tmf_of(a)}
                                  for seg, a in dep_raw if a.get("apiType") == "openapi"],
                }
                if apis["exposed"] and dirname not in out:
                    out[dirname] = apis
        except Exception:
            continue
    return out


def catalog() -> dict:
    """The official ODA component map (35 components, TM Forum v1.0.0 release). Every
    component is enriched with its exposed/dependent TMF APIs from the official component
    specifications (oda_component_apis.json, fetched from TM Forum's published repo);
    local reference manifests fill in only where the official data is absent."""
    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    data = json.load(open(_CATALOG_FILE, encoding="utf-8"))
    try:
        official = json.load(open(os.path.join(_HERE, "oda_component_apis.json"),
                                  encoding="utf-8"))["components"]
    except Exception:
        official = {}
    manifests = _manifest_apis()
    for c in data["components"]:
        short = c["short"].lower()
        off = official.get(c["code"])
        if off:
            c["exposed"] = [a for a in off["exposed"] if (a.get("tmf") or "").startswith("TMF")]
            c["dependent"] = [a for a in off["dependent"] if (a.get("tmf") or "").startswith("TMF")]
        else:
            hit = manifests.get(short) or next(
                (v for k, v in manifests.items() if short.startswith(k) and len(k) >= 8), None)
            if hit:
                c["exposed"] = hit["exposed"]
                c["dependent"] = hit["dependent"]
        c["spec_url"] = data["spec_url_pattern"].replace("{code}", c["code"]).replace("{short}", c["short"])
    _CATALOG = data
    return data


if __name__ == "__main__":
    import sys
    tmf_profile.build_index()
    path = sys.argv[1]
    print(render_markdown(check_component(open(path, encoding="utf-8", errors="ignore").read())))
