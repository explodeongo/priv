#!/usr/bin/env bash
# One-command direct demo of the OFFICIAL TM Forum Component CTK against the deployed
# TMFC043 demo, printing SynaptDI's deterministic verdict.
#   bash demo-run.sh pass   -> conformant component  -> PASS
#   bash demo-run.sh fail   -> non-conformant clone  -> FAIL
# Refreshes the component status, runs the real framework, then normalizes the real artifact.
set -uo pipefail
export PATH="/opt/homebrew/bin:$PATH"
export KUBECONFIG="$HOME/.kube/config"
export DOCKER_HOST="unix:///Users/aryan/.colima/default/docker.sock"
VENV=/Users/aryan/Downloads/CTK/ctk-venv/bin/python
CTK=/Users/aryan/Downloads/CTK/componentCTK
BACKEND=/Users/aryan/Downloads/SynaptDI/backend
DEMODIR="$(cd "$(dirname "$0")" && pwd)"

MODE="${1:-pass}"
if [ "$MODE" = "fail" ]; then
  REL=synaptdi-tmfc043-broken; NS=synaptdi-oda-demo-broken; PORT=30044
elif [ "$MODE" = "pass" ]; then
  REL=synaptdi-tmfc043-demo;   NS=synaptdi-oda-demo;        PORT=30043
else
  echo "usage: bash demo-run.sh [pass|fail]"; exit 2
fi
MODE_UC=$(printf '%s' "$MODE" | tr '[:lower:]' '[:upper:]')
echo "============================================================"
echo " DEMO: ${MODE_UC}   release=$REL   namespace=$NS"
echo "============================================================"

echo "[1/3] refreshing component status (verifies real readiness first)…"
NS="$NS" COMP="$REL" NODEPORT="$PORT" bash "$DEMODIR/reconcile-status.sh" >/tmp/demo_reconcile.log 2>&1 \
  && echo "      status = Complete" || { echo "      reconcile FAILED — see /tmp/demo_reconcile.log"; exit 1; }

"$VENV" -c "import sys;sys.path.insert(0,'$BACKEND');import oda_ctk_adapter as A,json;json.dump(A.generate_change_me({'component_id':'TMFC043','release_name':'$REL','namespace':'$NS','ctkconfig':{'company_name':'SynaptDI Demo','product_name':'TMFC043 Demo','product_url':'http://localhost','product_version':'1.0.0','headers':{'Accept':'application/json','Content-Type':'application/json'},'payloads':{}}}),open('$CTK/CHANGE_ME.json','w'),indent=4)"

echo "[2/3] running the OFFICIAL TM Forum Component CTK (real framework, may take ~1 min)…"
( cd "$CTK/scripts" && "$VENV" CTK_Executor.py ) >/tmp/demo_ctk.log 2>&1
echo "      CTK executor exit $?  (full log: /tmp/demo_ctk.log)"

echo "[3/3] SynaptDI deterministic verdict over the real consolidatedResults.json:"
"$VENV" - <<PY
import sys; sys.path.insert(0,"$BACKEND")
import oda_component_contract as C, oda_ctk_results as R
n=R.normalize_from_path("$CTK/resources/consolidatedResults.json", C.resolve_contract("TMFC043"), {"execution_completed":True})
bar = "🟢" if n["overall_status"]=="PASS" else ("🔴" if n["overall_status"]=="FAIL" else "🟠")
print("      %s  VERDICT: %s   (mandatory passed %d / failed %d)" % (bar, n["overall_status"], n["mandatory_passed"], n["mandatory_failed"]))
for r in n["per_requirement_results"]:
    if r["requirement"]=="MANDATORY":
        print("         %-7s %-8s  %s/%s assertions failed" % (r["id"], r["outcome"], r.get("failed",0), r.get("total","?")))
PY
