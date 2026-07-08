# TMFC043 Component CTK demo target

A minimal, real, deployable TMF642 v4 + TMF669 v4 implementation used **only** as a target
for the official TM Forum Component CTK, so a genuine execution-backed TMFC043 conformance
run completes end to end on a local machine. Not part of SynaptDI's backend/verdict engine.

## Result achieved
Official Component CTK → real `consolidatedResults.json` → SynaptDI deterministic verdict
**PASS** (TMF642 323 assertions/0 failed, TMF669 100/0, both mocha baselines 100%). The
preserved artifact + provenance live in `backend/test_fixtures/oda_ctk/`.

## Reproduce (Apple-silicon macOS)
```bash
# 0) prerequisites (once): brew install colima docker docker-compose kubectl helm
#    python venv for the CTK: python3.10+ -m venv ctk-venv && ctk-venv/bin/pip install -r componentCTK/scripts/requirements.txt
colima start --kubernetes --cpu 4 --memory 8 --disk 60 --vm-type vz --vz-rosetta

# 1) build + deploy the demo
cd demo/tmfc043-demo
docker build -t tmfc043-demo:1.0.0 .
kubectl create namespace synaptdi-oda-demo
kubectl apply -f helm/tmfc043/crds/component-crd.yaml
helm install synaptdi-tmfc043-demo helm/tmfc043 -n synaptdi-oda-demo

# 2) publish the (verified-real) component status the Canvas operators would set
bash reconcile-status.sh

# 3) run the official CTK, or run through SynaptDI with:
export ODA_CTK_PYTHON=/path/to/ctk-venv/bin/python
export TMPDIR=$HOME/synaptdi-ctk-tmp   # workspace must live under $HOME for colima's mount
```

## Networking notes (colima)
- The k3s NodePort (30043) is reached from the **host** at `localhost:30043` and from
  **docker containers** (the Newman API CTKs) at `host.docker.internal:30043`. The component
  status therefore advertises TMF669 at both perspectives (see `reconcile-status.sh`).
- The CTK workspace must be under `$HOME` (`TMPDIR`) because colima only virtiofs-mounts
  `$HOME`; the API CTK docker-compose bind-mounts its `./reports` from inside the workspace.

## Honesty boundary
Everything is real except the Component CR `.status`, which a full ODA Canvas would populate.
`reconcile-status.sh` stands in for the Canvas component/API operators but writes `Complete`
+ the API URLs **only after verifying** the pod is Ready and both APIs genuinely answer. The
baseline suites and both API CTKs are executed for real by the official framework.
