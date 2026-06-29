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
        "failing": [f["title"] for f in rep.get("findings", [])
                    if f["status"] == "fail" and f["severity"] in ("error", "warning")],
        "profile": ({
            "tmf": det["tmf"],
            "version": det["version"],
            "confidence": det["confidence"],
            "coverage": prof["coverage"],
            "resource": prof["resource"]["name"],
            "missing_ops": len(prof["operations"]["missing"]),
            "missing_fields": len(prof["resource"]["missing"]),
            "top_fields": prof["resource"]["missing"][:6],
            "operations": [o["method"] + " " + o["path"] for o in prof["operations"]["missing"]],
            "fields": prof["resource"]["missing"],
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


def _verdict(row: dict) -> str:
    p = row.get("profile")
    if not p:
        return "Unprofiled"
    if p["coverage"] >= 80 and row["structural"] >= 90:
        return "Ready"
    if p["coverage"] >= 40 or row["structural"] >= 70:
        return "Needs work"
    return "Major gaps"


def _scaffoldable(row: dict) -> int:
    p = row.get("profile")
    return (p["missing_ops"] + p["missing_fields"]) if p else 0


def render_markdown(report: dict) -> str:
    s = report["summary"]
    rows = report["rows"]
    ready = sum(1 for r in rows if _verdict(r) == "Ready")
    needs = sum(1 for r in rows if _verdict(r) == "Needs work")
    major = sum(1 for r in rows if _verdict(r) == "Major gaps")
    total_fixable = sum(r.get("fixable", 0) for r in rows)
    total_scaffold = sum(_scaffoldable(r) for r in rows)
    worst = next((r for r in rows if r.get("profile")), None)   # rows are sorted worst-coverage first

    out = ["# SynaptDI — API estate X-ray", ""]
    out.append("_Generated %s · deterministic TM Forum (TMF630 + profile) analysis, no AI._" % report["generated"])
    out += ["", "## Executive summary", ""]
    out.append("- **%d API%s analysed** · avg structure **%d/100** · avg TMF coverage **%d%%**."
              % (s["apis"], "" if s["apis"] == 1 else "s", s["avg_structural"], s["avg_coverage"]))
    out.append("- Readiness: **%d ready** · **%d need work** · **%d major gaps**." % (ready, needs, major))
    if worst:
        wp = worst["profile"]
        out.append("- Biggest gap: **%s** (`%s`) — only **%d%%** of %s." % (worst["api"], worst["file"], wp["coverage"], wp["tmf"]))
    out.append("- Quick wins: **%d** structural issue%s auto-fixable, and **%d** missing operations/fields can be scaffolded straight from the canonical specs — most of the gap closes automatically (Auto-fix + Scaffold)."
               % (total_fixable, "" if total_fixable == 1 else "s", total_scaffold))

    out += ["", "## Priorities (worst first)", "",
            "| # | API | Verdict | Structure | TMF | Coverage | Auto-fixable | Scaffoldable |",
            "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        p = r.get("profile")
        out.append("| %d | %s | %s | %d/100 | %s | %s | %d | %d |" % (
            i, r["api"], _verdict(r), r["structural"], (p["tmf"] if p else "—"),
            ("%d%%" % p["coverage"]) if p else "—", r.get("fixable", 0), _scaffoldable(r)))

    out += ["", "## Per-API detail"]
    for r in rows:
        p = r.get("profile")
        out += ["", "### %s — `%s`" % (r["api"], r["file"])]
        head = "Structure **%d/100**" % r["structural"]
        if p:
            head += " · **%s v%s** coverage **%d%%**" % (p["tmf"], p["version"], p["coverage"])
        head += " · _%s_" % _verdict(r)
        out += [head, ""]
        if r.get("failing"):
            out.append("- **Structure issues (%d):** %s" % (len(r["failing"]), ", ".join(r["failing"])))
        if p and p.get("operations"):
            out.append("- **Missing operations (%d):** %s" % (len(p["operations"]), ", ".join("`%s`" % o for o in p["operations"])))
        if p and p.get("fields"):
            out.append("- **Missing %s attributes (%d):** %s" % (p.get("resource", "resource"), len(p["fields"]), ", ".join("`%s`" % f for f in p["fields"])))
        if p:
            rem = []
            if r.get("fixable"):
                rem.append("run **Auto-fix** (%d mechanical fix%s available)" % (r["fixable"], "" if r["fixable"] == 1 else "es"))
            if _scaffoldable(r):
                rem.append("**Scaffold** the %d missing operations/fields from %s" % (_scaffoldable(r), p["tmf"]))
            out.append("- **Remediation:** " + ("; ".join(rem) + "." if rem else "already aligned — no action needed."))

    out += ["",
            "> Coverage = how much of the official TM Forum API a spec implements. Structure = TMF630 design-rule "
            "conformance. Auto-fixable = mechanical TMF630 fixes; Scaffoldable = operations/fields copyable from the "
            "canonical spec. All computed deterministically against TM Forum's published specs — no AI."]
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
