#!/usr/bin/env bash
# Minimal stand-in for the ODA Canvas component/API operators.
# ─────────────────────────────────────────────────────────────────────────────
# In a full ODA Canvas, the component operator sets the Component CR's
# status["summary/status"].deployment_status and the API operator publishes each exposed
# API's gateway URL into status.coreAPIs/securityAPIs. Installing full Canvas (Istio/Kong +
# cert-manager + the operator suite) on local k3s is out of scope for this demo, so this
# script performs the SAME reconciliation the operators would — but only AFTER verifying the
# component is genuinely deployed and its APIs are genuinely reachable. It never invents a
# healthy status: `Complete` is written only if the real pod is Ready and the real endpoints
# actually answer. This is the ONLY operator-substituted piece; the CTK baseline + the two
# API CTKs that follow are entirely real.
set -euo pipefail
export PATH="/opt/homebrew/bin:$PATH" DOCKER_HOST="unix:///Users/aryan/.colima/default/docker.sock"

# Parameterized so the same reconcile serves the conformant demo (defaults) and the
# deliberately-broken FAIL demo (override NS/COMP/NODEPORT).
NS="${NS:-synaptdi-oda-demo}"
COMP="${COMP:-synaptdi-tmfc043-demo}"
NODEPORT="${NODEPORT:-30043}"
# Two network perspectives on the SAME demo pod (colima forwards the k3s NodePort to the
# host's localhost; docker containers reach it via host.docker.internal):
#   • the API CTK Newman containers run inside docker → host.docker.internal:<nodeport>
#   • deployment.js testPartyRole runs on the host       → localhost:<nodeport>
CONTAINER_HOST="host.docker.internal:${NODEPORT}"
HOST_HOST="localhost:${NODEPORT}"
ALARM_URL="http://${CONTAINER_HOST}/tmf-api/alarmManagement/v4/"
ROLE_URL_CONTAINER="http://${CONTAINER_HOST}/tmf-api/partyRoleManagement/v4/"
ROLE_URL_HOST="http://${HOST_HOST}/tmf-api/partyRoleManagement/v4/"

echo "1) verifying the component pod is actually Ready…"
kubectl wait --for=condition=ready pod -l app=${COMP}-fault -n ${NS} --timeout=60s >/dev/null
echo "   pod Ready ✓"

echo "2) verifying both mandatory APIs answer from a container (host.docker.internal) …"
a=$(docker run --rm --network tmf --platform linux/amd64 curlimages/curl:8.11.1 -s -m 8 -o /dev/null -w "%{http_code}" -X POST "${ALARM_URL}alarm" -H 'Content-Type: application/json' -d '{"alarmType":"x","perceivedSeverity":"minor","probableCause":"y","sourceSystemId":"z","state":"raised","alarmRaisedTime":"2019-07-03T03:32:17.235Z","alarmedObject":{"id":"1"}}')
r=$(docker run --rm --network tmf --platform linux/amd64 curlimages/curl:8.11.1 -s -m 8 -o /dev/null -w "%{http_code}" "${ROLE_URL_CONTAINER}partyRole")
echo "   [container] TMF642 POST /alarm -> ${a} | TMF669 GET /partyRole -> ${r}"
echo "   verifying the security role is published + reachable from the host (localhost) …"
role=$(curl -s -m 8 "${ROLE_URL_HOST}partyRole")
h=$(echo "$role" | grep -c "fault-admin" || true)
echo "   [host] GET /partyRole contains canvas system role 'fault-admin': $([ "$h" -ge 1 ] && echo yes || echo no)"
if [ "$a" != "201" ] || [ "$r" != "200" ] || [ "$h" -lt 1 ]; then
  echo "   ✗ component not genuinely reachable/healthy — refusing to set status Complete." >&2
  exit 1
fi
echo "   component genuinely reachable + role published ✓"

echo "3) publishing verified status onto the Component CR (as Canvas operators would)…"
# TMF669 appears in coreAPIs (container URL, used first by deployment.js for the API CTK) AND
# in securityAPIs (host URL, used by testPartyRole) — the same API reached from two network
# perspectives, both verified reachable above.
kubectl patch component ${COMP} -n ${NS} --subresource=status --type=merge -p "$(cat <<JSON
{
  "status": {
    "summary/status": { "deployment_status": "Complete" },
    "coreAPIs": [
      { "name": "alarm-management-api", "implementation": "${COMP}-tmf642", "url": "${ALARM_URL}", "ready": true },
      { "name": "party-role-management-api", "implementation": "${COMP}-tmf669", "url": "${ROLE_URL_CONTAINER}", "ready": true }
    ],
    "securityAPIs": [
      { "name": "party-role-management-api", "implementation": "${COMP}-tmf669", "url": "${ROLE_URL_HOST}", "ready": true }
    ]
  }
}
JSON
)" >/dev/null
echo "   status published ✓"
kubectl get component ${COMP} -n ${NS} -o jsonpath='{.status}' | sed 's/,/,\n  /g'
echo
echo "reconcile complete."
