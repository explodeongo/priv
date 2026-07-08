#!/usr/bin/env bash
# One-command pre-flight for the TMFC043 Component CTK demo.
# Verifies the cluster + demo are warm and the component status is published & reachable,
# and (idempotently) re-runs the status reconcile so a live run can't fail on staleness.
# Safe to run any number of times. No inline comments are echoed to your shell.
set -uo pipefail
export PATH="/opt/homebrew/bin:$PATH"
export DOCKER_HOST="unix:///Users/aryan/.colima/default/docker.sock"
export KUBECONFIG="$HOME/.kube/config"

NS=synaptdi-oda-demo
COMP=synaptdi-tmfc043-demo
ok(){ printf "  \033[32m✓\033[0m %s\n" "$1"; }
bad(){ printf "  \033[31m✗\033[0m %s\n" "$1"; }

echo "TMFC043 CTK demo — pre-flight"

if colima status >/dev/null 2>&1; then ok "colima running"; else bad "colima not running — run: colima start"; exit 1; fi
if kubectl get nodes 2>/dev/null | grep -q " Ready "; then ok "k8s node Ready"; else bad "k8s node not Ready"; exit 1; fi

POD=$(kubectl get pods -n "$NS" -l app=${COMP}-fault -o jsonpath='{.items[0].status.phase}' 2>/dev/null || true)
if [ "$POD" = "Running" ]; then ok "demo pod Running"; else bad "demo pod not Running (phase=$POD)"; fi

HEALTH=$(curl -s -m 5 -o /dev/null -w "%{http_code}" http://localhost:30043/health 2>/dev/null || echo 000)
if [ "$HEALTH" = "200" ]; then ok "demo reachable on localhost:30043"; else bad "demo not reachable (http=$HEALTH)"; fi

echo "publishing/refreshing verified component status…"
if bash "$(dirname "$0")/reconcile-status.sh" >/tmp/preflight_reconcile.log 2>&1; then
  STATUS=$(kubectl get component "$COMP" -n "$NS" -o jsonpath='{.status.summary/status.deployment_status}' 2>/dev/null || true)
  ok "component deployment_status = $STATUS"
else
  bad "reconcile failed — see /tmp/preflight_reconcile.log"; exit 1
fi

echo
echo "READY. Run the demo with either:"
echo "  A) official CTK :  cd /Users/aryan/Downloads/CTK/componentCTK/scripts && \\"
echo "       PATH=\"/opt/homebrew/bin:\$PATH\" KUBECONFIG=~/.kube/config \\"
echo "       DOCKER_HOST=\"unix:///Users/aryan/.colima/default/docker.sock\" \\"
echo "       /Users/aryan/Downloads/CTK/ctk-venv/bin/python CTK_Executor.py"
echo "  B) SynaptDI UI  :  start the backend with the CTK env (see demo/tmfc043-demo/README.md)"
