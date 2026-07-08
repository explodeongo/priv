# Real TMFC043 Component CTK artifact — provenance

`tmfc043_real_consolidatedResults.json` is a **genuine** `resources/consolidatedResults.json`
produced by the official TM Forum Component CTK (`componentCTK/scripts/CTK_Executor.py`)
executing against a real deployed TMFC043 demo component on a local Kubernetes cluster.
It was **not** hand-written, edited, mocked, or simulated. It is stored **byte-for-byte
unmodified** (SHA-256 below) as the first real CTK evidence fixture.

| Field | Value |
|---|---|
| Execution date | 2026-07-08 |
| Framework | TM Forum Component CTK (`/Users/aryan/Downloads/CTK/componentCTK`), CHANGE_ME `ctkVersion` v1.2.0 |
| CTK runtime | Python 3.14.5 venv (`/Users/aryan/Downloads/CTK/ctk-venv`), Node 26 / npm 11 |
| Cluster | k3s v1.35.0 (colima 0.10.3, Apple Virtualization + Rosetta, arm64) |
| Component id / version | TMFC043 / 1.0.0 |
| Helm release | `synaptdi-tmfc043-demo` |
| Namespace | `synaptdi-oda-demo` |
| Mandatory CTKs resolved | TMF642 v4 (Alarm Management, coreFunction), TMF669 v4 (Party Role Management, securityFunction) |
| API CTK images | `tmforumorg/tmf642-v4.0.0-ctk:1.0.1`, `tmforumorg/tmf669-v4.0.0-ctk:1.0.1` (linux/amd64, real Newman collections) |
| Demo component | **Synthetic** — a minimal FastAPI implementation of TMF642 v4 + TMF669 v4 built solely as a CTK target (`SynaptDI/demo/tmfc043-demo`). It genuinely answers the CTK's HTTP requests; it is not a production fault-management product. |
| Canvas | **Not installed.** The Component CR's `.status` (`summary/status.deployment_status=Complete` + `coreAPIs`/`securityAPIs[].url`) — normally written by the ODA Canvas operators — was published by a minimal stand-in reconciler (`demo/tmfc043-demo/reconcile-status.sh`) **only after** verifying the pod was Ready and both APIs genuinely answered. This is the ONLY operator-substituted piece; the baseline mocha suites and both API CTKs are entirely real. |
| SHA-256 | `6c7db5fb41ee65468b1507a6aa3ffb4dbba4ef8dea10606808d4a4f34d2790b0` |

## Real results contained in the artifact
| Section | Result |
|---|---|
| `configurationReport` (mocha baseline) | 18 tests, 18 passed, 0 failed |
| `deploymentReport` (mocha baseline) | 5 tests, 5 passed, 0 failed |
| `apiCtkResults` TMF642_v4 (Newman) | 323 assertions, 0 failed |
| `apiCtkResults` TMF669_v4 (Newman) | 100 assertions, 0 failed |
| `resultsSummary.ctkPassed` | `true` |

## SynaptDI deterministic verdict over this artifact
`oda_ctk_results.normalize_from_path(...)` →
**`PASS`** · mandatory total 2 / executed 2 / passed 2 / failed 0 / missing 0 / ambiguous 0 ·
baseline passed · no warnings. The verdict is derived deterministically from this evidence;
it is not hardcoded. See `test_oda_ctk_real_artifact.py`.

---

## FAIL counterpart — `tmfc043_broken_consolidatedResults.json`
A second **real** CTK run against a deliberately non-conformant deploy of the same component
(`helm install … --set broken=true`, release `synaptdi-tmfc043-broken`, namespace
`synaptdi-oda-demo-broken`), whose alarm API omits the mandatory TMF642 attribute `state`.
Same cluster, same framework, same day. Proves SynaptDI reports an honest **FAIL** — it does
not rubber-stamp.

| Section | Result |
|---|---|
| `configurationReport` | 18/18 passed (manifest is valid) |
| `deploymentReport` | 5/5 passed (component **is** deployed + reachable) |
| `apiCtkResults` TMF642_v4 | 292 assertions, **61 failed** (missing mandatory `state`) |
| `apiCtkResults` TMF669_v4 | 100 assertions, 0 failed (party-role API still conformant) |
| `resultsSummary.ctkPassed` | `false` |
| SHA-256 | `ac5e1ed08544ace1b18556f0ad096087c7cdc3962a6c83a598403cc33bc0c4e6` |

SynaptDI deterministic verdict → **`FAIL`** · mandatory passed 1 / failed 1 · TMF642 `FAILED`
(61/292 failed, "mandatory API CTK reported failures") · TMF669 `PASSED`. The baselines still
pass — the component **is** deployed; it simply **is not conformant**. That distinction is the
whole point of the tool.
