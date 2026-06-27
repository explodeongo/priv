"""
API estate X-ray
════════════════
Roll up the conformance + profile engines across a whole folder/portfolio of API
specs into one board-ready report: for each API, its TMF630 structural score and
its coverage against the real canonical TMF spec — plus the top gaps.

Pure & offline (no LLM). Used by the `/conformance/portfolio` endpoint, the VS Code
"API estate X-ray" command, and a standalone CLI (`python xray.py <dir>`).
"""
import glob
import json
import os
import time

import conformance
import tmf_profile

try:
    import yaml
except Exception:
    yaml = None


def _parse(content: str):
    try:
        return json.loads(content)
    except Exception:
        if yaml:
            try:
                return yaml.safe_load(content)
            except Exception:
                return None
    return None


def _looks_like_spec(spec) -> bool:
    return isinstance(spec, dict) and bool(spec.get("paths")) and bool(
        spec.get("openapi") or spec.get("swagger") or spec.get("info"))


def analyze_one(filename: str, content: str):
    spec = _parse(content)
    if not _looks_like_spec(spec):
        return None
    rep = conformance.check_spec(spec)
    prof = tmf_profile.compare_to_canonical(spec)
    det = prof.get("detected")
    return {
        "file": filename,
        "api": rep.get("api", "API"),
        "structural": rep.get("score", 0),
        "errors": rep["summary"]["failed"],
        "warnings": rep["summary"]["warnings"],
        "fixable": rep.get("fixable", 0),
        "profile": ({
            "tmf": det["tmf"],
            "version": det["version"],
            "confidence": det["confidence"],
            "coverage": prof["coverage"],
            "missing_ops": len(prof["operations"]["missing"]),
            "missing_fields": len(prof["resource"]["missing"]),
            "top_fields": prof["resource"]["missing"][:6],
        } if det else None),
    }


def build_portfolio(items) -> dict:
    """items: [{filename, content}] → rolled-up report."""
    tmf_profile.build_index()                       # ensure profiles are populated (blocking, one-time)
    rows = []
    for it in items:
        r = analyze_one(it.get("filename") or it.get("file") or "spec", it.get("content") or "")
        if r:
            rows.append(r)
    rows.sort(key=lambda r: (r["profile"]["coverage"] if r["profile"] else 10 ** 6, r["structural"]))

    structural = [r["structural"] for r in rows]
    covs = [r["profile"]["coverage"] for r in rows if r["profile"]]
    summary = {
        "apis": len(rows),
        "detected": sum(1 for r in rows if r["profile"]),
        "avg_structural": round(sum(structural) / len(structural)) if structural else 0,
        "avg_coverage": round(sum(covs) / len(covs)) if covs else 0,
        "fully_compliant": sum(1 for r in rows if r["structural"] == 100),
    }
    return {"generated": time.strftime("%Y-%m-%d %H:%M"), "summary": summary, "rows": rows}


def render_markdown(report: dict) -> str:
    s = report["summary"]
    out = [
        "# SynaptDI — API estate X-ray",
        "",
        "_Generated %s · deterministic TM Forum analysis, no AI._" % report["generated"],
        "",
        "**%d APIs analysed** · %d matched a TMF profile · avg structure %d/100 · avg TMF coverage %d%% · %d fully TMF630-compliant"
        % (s["apis"], s["detected"], s["avg_structural"], s["avg_coverage"], s["fully_compliant"]),
        "",
        "| API | File | Structure | TMF profile | Coverage | Top gaps |",
        "|---|---|---|---|---|---|",
    ]
    for r in report["rows"]:
        p = r["profile"]
        prof = ("%s v%s" % (p["tmf"], p["version"])) if p else "—"
        cov = ("%d%%" % p["coverage"]) if p else "—"
        gaps = "—"
        if p:
            bits = []
            if p["missing_ops"]:
                bits.append("%d ops" % p["missing_ops"])
            if p["missing_fields"]:
                bits.append("%d fields" % p["missing_fields"])
            gaps = ", ".join(bits) or "complete"
            if p["top_fields"]:
                gaps += " (" + ", ".join(p["top_fields"][:4]) + "…)"
        out.append("| %s | `%s` | %d/100 | %s | %s | %s |" % (r["api"], r["file"], r["structural"], prof, cov, gaps))
    out += [
        "",
        "> Coverage = how much of the official TM Forum API a spec implements (operations + resource attributes). "
        "Structure = TMF630 design-rule conformance. Both are computed deterministically against TM Forum's published specs.",
    ]
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    tmf_profile.build_index()
    items = []
    for f in glob.glob(os.path.join(root, "**", "*"), recursive=True):
        if os.path.isfile(f) and f.lower().endswith((".yaml", ".yml", ".json")):
            try:
                items.append({"filename": os.path.relpath(f, root), "content": open(f, encoding="utf-8", errors="ignore").read()})
            except Exception:
                pass
    report = build_portfolio(items)
    md = render_markdown(report)
    print(md)
    try:
        out_path = os.path.join(root, "synaptdi-xray.md")
        open(out_path, "w").write(md)
        print("\nwrote " + out_path)
    except Exception:
        pass
