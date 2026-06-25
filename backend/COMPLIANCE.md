# TM Forum compliance gate

`synaptdi_check.py` scans OpenAPI / Swagger specs against the TM Forum API Design
Guidelines (TMF630) and **exits non-zero** if any spec is below a threshold. It's the same
deterministic engine the app and the VS Code extension use — **pure & offline, no server, no LLM.**

## Use it
```bash
cd backend
python synaptdi_check.py ./apis              # scan a directory tree
python synaptdi_check.py "specs/**/*.yaml"   # globs
python synaptdi_check.py api.yaml --min 95   # custom threshold (default 90)
python synaptdi_check.py ./apis --json       # machine-readable report
```
Only dependency for YAML specs is `pyyaml` (already in `requirements.txt`). Exit code is
`0` when every spec passes, `1` when any spec is below `--min`.

```
TM Forum compliance (TMF630) — threshold 90/100
------------------------------------------------------------
  [FAIL]   9/100   3E 4W   apis/productOrder.json
  [PASS] 100/100   0E 0W   apis/serviceOrder.json
------------------------------------------------------------
  1/2 specs pass · lowest 9/100
```

## Pre-commit hook
Block a commit that introduces a non-compliant spec. Save as `.git/hooks/pre-commit`
(and `chmod +x` it):
```bash
#!/bin/sh
python backend/synaptdi_check.py ./apis --min 90 || {
  echo "TM Forum compliance failed — run 'Auto-fix TM Forum Issues' in VS Code, or fix manually."
  exit 1
}
```

## CI (GitHub Actions)
```yaml
- name: TM Forum compliance gate
  run: |
    pip install pyyaml
    python backend/synaptdi_check.py ./apis --min 90
```

## In the editor (VS Code extension)
- **Check TM Forum Compliance** — squiggles + score on the active spec (auto-runs on save)
- **Auto-fix TM Forum Issues** — deterministically corrects the spec, then re-checks
- **Scan Workspace for TM Forum Compliance** — runs the check across every spec in the repo
