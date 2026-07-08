"""
ODA Component CTK adapter (execution-backed conformance, layer C)
═════════════════════════════════════════════════════════════════
Wraps the PROVIDED TM Forum Component CTK framework as an external execution engine.
It does NOT reimplement or port CTK_Executor.py — it generates a real CHANGE_ME.json
(the framework's own contract) into an isolated workspace and runs
`python3 scripts/CTK_Executor.py` as a subprocess, then hands the raw
resources/consolidatedResults.json to the deterministic normalizer (oda_ctk_results.py).

Execution boundary — this runs third-party CTK code + infra tooling, so it is locked
down: fixed framework path, fixed canonical repo/tag, validated component/release/
namespace, shell=False + argument arrays (no user command/path), isolated workspace,
timeout, and secret redaction in every persisted snapshot/log. A dry run generates and
validates everything WITHOUT invoking helm/kubectl/docker/npm or the executor.
"""
import os
import re
import shutil
import subprocess
import tempfile
import time

import oda_component_contract
import oda_ctk_results

# ── Fixed, non-user-controllable execution parameters (Phase 1) ───────────────────────
FRAMEWORK_SRC = os.environ.get("ODA_CTK_FRAMEWORK_PATH", "/Users/aryan/Downloads/CTK/componentCTK")
SUPPORTED_COMPONENTS = {"TMFC043"}                    # Phase 1 golden path only
CANONICAL_REPO = {"repoOwner": "tmforum-rand", "repoName": "TMForum-ODA-Ready-for-publication",
                  "gitBranch": "v1.0.0"}
DEFAULT_TIMEOUT_SEC = int(os.environ.get("ODA_CTK_TIMEOUT_SEC", "3600"))
# The provided CTK_Executor.py uses PEP 604 type hints (`Path | None`) → requires Python
# 3.10+. A deployment points this at its 3.10+ interpreter; default 'python3'.
CTK_PYTHON = os.environ.get("ODA_CTK_PYTHON", "python3")

_K8S_NAME = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")   # DNS-1123 label (release/namespace)
_COMPONENT_ID = re.compile(r"^TMFC\d{3}$")
_K8S_NAME_MAXLEN = 63   # DNS-1123 label limit

# Header/config keys whose VALUES are secrets and must never be persisted or returned.
_SECRET_KEY = re.compile(r"authorization|bearer|api[-_]?key|x-api-key|token|cookie|"
                         r"password|passwd|secret|kubeconfig|credential", re.I)
_REDACTED = "***REDACTED***"

# Executor/infra failure categories — kept distinct from a conformance FAIL.
CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
CANONICAL_RESOLUTION_ERROR = "CANONICAL_RESOLUTION_ERROR"
DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
CTK_DOWNLOAD_ERROR = "CTK_DOWNLOAD_ERROR"
CANVAS_CONNECTION_ERROR = "CANVAS_CONNECTION_ERROR"
COMPONENT_NOT_DEPLOYED = "COMPONENT_NOT_DEPLOYED"
EXECUTION_ERROR = "EXECUTION_ERROR"
RESULT_PARSE_ERROR = "RESULT_PARSE_ERROR"
TIMEOUT_ERROR = "TIMEOUT"


# ── Config validation + generation ────────────────────────────────────────────────────
def validate_request(req: dict) -> list:
    """Return a list of validation error strings ([] = valid). Never raises."""
    errs = []
    cid = (req.get("component_id") or "").upper()
    if not _COMPONENT_ID.fullmatch(cid):
        errs.append("component_id must look like TMFCNNN")
    elif cid not in SUPPORTED_COMPONENTS:
        errs.append(f"component_id {cid} is not supported in this phase (supported: {sorted(SUPPORTED_COMPONENTS)})")
    rel = req.get("release_name") or ""
    if not rel:
        errs.append("release_name is required (the deployed component's Helm release)")
    elif not _valid_k8s_name(rel):
        errs.append(f"release_name must be a valid Kubernetes/Helm name (DNS-1123 label, max {_K8S_NAME_MAXLEN} chars)")
    ns = req.get("namespace") or "components"
    if not _valid_k8s_name(ns):
        errs.append(f"namespace must be a valid Kubernetes namespace (DNS-1123 label, max {_K8S_NAME_MAXLEN} chars)")
    return errs


def _valid_k8s_name(value: str) -> bool:
    """Strict DNS-1123 label check. Uses fullmatch (not match) — Python's `$` anchor
    matches before a trailing '\\n', so `match()` + a '$'-terminated pattern would let
    e.g. "myrelease\\n" pass as valid; fullmatch requires the entire string to match with
    no such exception. Also enforces the real Kubernetes 63-char label limit."""
    return bool(value) and len(value) <= _K8S_NAME_MAXLEN and bool(_K8S_NAME.fullmatch(value))


def redact(obj):
    """Deep-copy with secret VALUES redacted (by key name). Used for every stored config
    snapshot and API response, so Authorization/tokens/kubeconfig never leak."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and _SECRET_KEY.search(k):
                out[k] = _REDACTED
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj


def generate_change_me(req: dict) -> dict:
    """Build a REAL CHANGE_ME.json for the framework (exact keys/nesting from the provided
    file). SynaptDI's typed request is mapped ONTO the framework's own contract — the file
    the executor consumes is genuine CHANGE_ME.json, not a cleaner invented format.

    For TMFC043 (0 dependent APIs) dependentStubs and bddPayloads are empty by design."""
    cid = (req.get("component_id") or "").upper()
    cfg = req.get("ctkconfig") or {}
    return {
        "releaseName": req.get("release_name") or "",
        "component_to_run": cid,
        "component_namespace": req.get("namespace") or "components",
        "standardComponentPath": "",
        "ctk_name_mapping": {},
        "runExposedOptional": bool(req.get("run_exposed_optional", False)),
        "runDependentOptional": bool(req.get("run_dependent_optional", False)),
        "runSecurityOptional": bool(req.get("run_security_optional", False)),
        "ctkVersion": req.get("ctk_version", "v1.2.0"),
        "apiVersionUnderTest": req.get("api_version_under_test", ""),
        "apiVersionOverrides": req.get("api_version_overrides", {}) or {},
        "ctkLogging": {"ctkLogs": "summary", "ctkLogTailLines": 40},
        "download_sslVerify": bool(req.get("download_ssl_verify", True)),
        "standardComponentDownload": {
            "apiBaseUrl": "https://api.github.com",
            "repoOwner": CANONICAL_REPO["repoOwner"],
            "repoName": CANONICAL_REPO["repoName"],
            "repoPath": "Specification",
            "gitUrl": ("https://raw.githubusercontent.com/"
                       f"{CANONICAL_REPO['repoOwner']}/{CANONICAL_REPO['repoName']}/refs/heads"),
            "gitBranch": CANONICAL_REPO["gitBranch"],
        },
        "ctkconfig": {
            "companyName": cfg.get("company_name", ""),
            "productName": cfg.get("product_name", ""),
            "productUrl": cfg.get("product_url", ""),
            "productVersion": cfg.get("product_version", ""),
            "componentUrl": "https://www.tmforum.org/oda/directory/components-map",
            "headers": cfg.get("headers") or {"Accept": "application/json", "Content-Type": "application/json"},
            "payloads": cfg.get("payloads") or {},
            "rejectUnauthorized": bool(cfg.get("reject_unauthorized", False)),
        },
        "dependentStubs": {},                            # TMFC043 declares no dependent APIs
        "bddPayloads": {},                               # → no dependent-API BDD payloads
        "retrySettings": {"maxRetries": 30, "retryInterval": 10000},
    }


# ── Workspace ─────────────────────────────────────────────────────────────────────────
_IGNORE = shutil.ignore_patterns("node_modules", ".git", "resources", "Reports",
                                 "consolidatedResults.json", "__pycache__", ".DS_Store")


def _prepare_workspace(change_me: dict):
    """Create an isolated workspace, copy the framework into it, write CHANGE_ME.json.
    Returns (workspace_root, componentCTK_dir). Raises on framework absence."""
    if not os.path.isdir(FRAMEWORK_SRC):
        raise FileNotFoundError(f"CTK framework not found at {FRAMEWORK_SRC}")
    ws = tempfile.mkdtemp(prefix="synaptdi_odactk_")
    dst = os.path.join(ws, "componentCTK")
    shutil.copytree(FRAMEWORK_SRC, dst, ignore=_IGNORE)
    import json
    with open(os.path.join(dst, "CHANGE_ME.json"), "w", encoding="utf-8") as f:
        json.dump(change_me, f, indent=4)
    return ws, dst


def _framework_files_present(component_ctk_dir: str) -> dict:
    return {
        "scripts/CTK_Executor.py": os.path.isfile(os.path.join(component_ctk_dir, "scripts", "CTK_Executor.py")),
        "src/index.js": os.path.isfile(os.path.join(component_ctk_dir, "src", "index.js")),
        "src/package.json": os.path.isfile(os.path.join(component_ctk_dir, "src", "package.json")),
        "CHANGE_ME.json": os.path.isfile(os.path.join(component_ctk_dir, "CHANGE_ME.json")),
    }


def _prerequisites() -> dict:
    """Availability of infra tools by PATH lookup only — shutil.which does NOT invoke
    them (dry run must not run helm/kubectl/docker/npm)."""
    return {t: bool(shutil.which(t)) for t in ("python3", "node", "npm", "helm", "kubectl", "docker")}


def _expected_ctks(contract: dict) -> list:
    out = []
    for r in oda_component_contract.mandatory_api_coverage(contract):
        maj = re.search(r"v?(\d+)", r["declared_version"] or "")
        out.append(f"{r['id']}_v{maj.group(1) if maj else '?'}")
    return out


# ── Dry run (READY_TO_EXECUTE — NOT a conformance verdict) ─────────────────────────────
def dry_run(req: dict) -> dict:
    """Resolve the contract, validate config, generate CHANGE_ME.json in an isolated
    workspace, verify framework files, compute expected mandatory CTKs, and report
    prerequisites — WITHOUT invoking helm/kubectl/docker/npm or the CTK executor.
    Returns readiness only; READY_TO_EXECUTE never means ODA-conformant."""
    errors = validate_request(req)
    contract = oda_component_contract.resolve_contract(req.get("component_id"), req.get("component_version"))
    if contract.get("status") != "RESOLVED":
        errors.append(f"canonical contract not resolved: {contract.get('status')} "
                      f"({contract.get('reason') or contract.get('resolved_version')})")

    change_me = generate_change_me(req)
    files = {}
    workspace_created = False
    if not errors:
        try:
            ws, cctk = _prepare_workspace(change_me)
            workspace_created = True
            files = _framework_files_present(cctk)
            shutil.rmtree(ws, ignore_errors=True)         # dry-run workspace is disposable
        except Exception as e:
            errors.append(f"workspace preparation failed: {e}")

    prereqs = _prerequisites()
    files_ok = bool(files) and all(files.values())
    ready = (not errors) and files_ok
    missing_prereqs = [t for t in ("python3", "node", "npm", "helm", "kubectl", "docker") if not prereqs.get(t)]

    return {
        "status": "READY_TO_EXECUTE" if ready else "NOT_READY",
        "subprocess_invoked": False,
        "component_id": (req.get("component_id") or "").upper(),
        "errors": errors,
        "contract_status": contract.get("status"),
        "contract": contract if contract.get("status") == "RESOLVED" else None,
        "generated_change_me": redact(change_me),         # secrets redacted
        "framework_files_present": files,
        "framework_files_ok": files_ok,
        "workspace_prepared": workspace_created,
        "expected_mandatory_ctks": _expected_ctks(contract) if contract.get("status") == "RESOLVED" else [],
        "prerequisites": prereqs,
        "missing_prerequisites": missing_prereqs,
        "note": ("READY_TO_EXECUTE means configuration + workspace are valid — it does NOT "
                 "mean the component is ODA-conformant. Conformance is only known after a "
                 "real CTK execution against a deployed component."),
    }


# ── Real execution ────────────────────────────────────────────────────────────────────
def _classify_failure(exit_code, stdout: str, stderr: str, timed_out: bool) -> dict:
    """Map a failed/odd executor run to a distinct infra/executor category (never FAIL)."""
    if timed_out:
        return {"category": TIMEOUT_ERROR, "message": "CTK execution exceeded the timeout"}
    blob = f"{stdout}\n{stderr}".lower()
    if "helm get manifest" in blob or "missing manifest" in blob or "aborting ctk run due to missing manifest" in blob:
        return {"category": COMPONENT_NOT_DEPLOYED, "message": "helm could not get the component manifest — component likely not deployed"}
    if "docker" in blob and ("not running" in blob or "cannot connect" in blob or "daemon" in blob):
        return {"category": DEPENDENCY_ERROR, "message": "Docker unavailable"}
    if "kubectl" in blob or "connection refused" in blob or "could not connect" in blob or "canvas" in blob:
        return {"category": CANVAS_CONNECTION_ERROR, "message": "Kubernetes/ODA Canvas connectivity failure"}
    if "failed downloading ctk" in blob or "ctk key" in blob and "not found" in blob or "failed to download" in blob:
        return {"category": CTK_DOWNLOAD_ERROR, "message": "CTK download failed"}
    if "no component name found" in blob or "could not be downloaded" in blob:
        return {"category": CANONICAL_RESOLUTION_ERROR, "message": "component specification could not be resolved/downloaded"}
    if "npm" in blob and "err" in blob:
        return {"category": DEPENDENCY_ERROR, "message": "npm execution failed"}
    if ("unsupported operand type" in blob and "nonetype" in blob) or "path | none" in blob:
        return {"category": DEPENDENCY_ERROR,
                "message": "CTK executor requires Python 3.10+ (PEP 604 type hints); set ODA_CTK_PYTHON"}
    if "filenotfounderror" in blob and ("'helm'" in blob or "'kubectl'" in blob):
        return {"category": DEPENDENCY_ERROR, "message": "helm/kubectl not installed on the execution host"}
    if "filenotfounderror" in blob and "'docker'" in blob:
        return {"category": DEPENDENCY_ERROR, "message": "docker not installed on the execution host"}
    return {"category": EXECUTION_ERROR, "message": f"CTK executor exited with code {exit_code}"}


def _tail(s: str, lines: int = 60) -> str:
    if not s:
        return ""
    return "\n".join(s.splitlines()[-lines:])


def execute(req: dict, timeout: int = None, on_state=None):
    """Run the real CTK executor subprocess in an isolated workspace and return a
    (raw_execution, normalized_result) pair. On any infra/executor failure the normalized
    result is EXECUTION_ERROR (never a conformance FAIL). Caller owns workspace cleanup.

    `on_state(state)` (optional) fires at each REAL stage boundary so a job model can
    report only genuine progress — PREPARING_WORKSPACE, RUNNING_CTK (fired immediately
    before the subprocess actually starts), NORMALIZING_RESULTS."""
    def _emit(s):
        if on_state:
            try:
                on_state(s)
            except Exception:
                pass
    timeout = timeout or DEFAULT_TIMEOUT_SEC
    contract = oda_component_contract.resolve_contract(req.get("component_id"), req.get("component_version"))
    errors = validate_request(req)
    if contract.get("status") != "RESOLVED":
        errors.append(f"canonical contract not resolved: {contract.get('status')}")
    if errors:
        exec_state = {"execution_completed": False,
                      "execution_error": {"category": CONFIGURATION_ERROR, "messages": errors}}
        return exec_state, oda_ctk_results.normalize(None, contract if contract.get("status") == "RESOLVED" else {}, exec_state)

    change_me = generate_change_me(req)
    ws = cctk = None
    started = time.time()
    try:
        _emit("PREPARING_WORKSPACE")
        ws, cctk = _prepare_workspace(change_me)
        # Stale-artifact hardening: remove any known generated result paths inside THIS
        # isolated workspace before running (defence-in-depth — the fresh copy already
        # excludes them). Strictly guarded to our own synaptdi_odactk_ workspace prefix.
        purge_result_paths(ws, cctk)
        scripts_dir = os.path.join(cctk, "scripts")
        exec_start = time.time()
        timed_out = False
        try:
            _emit("RUNNING_CTK")
            proc = subprocess.run(
                [CTK_PYTHON, "CTK_Executor.py"],
                cwd=scripts_dir, capture_output=True, text=True,
                timeout=timeout, shell=False,             # NEVER shell=True; fixed argv
            )
            exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as e:
            timed_out, exit_code = True, None
            stdout, stderr = (e.stdout or ""), (e.stderr or "")
        duration = round(time.time() - started, 2)

        result_path = os.path.join(cctk, "resources", "consolidatedResults.json")
        # Freshness guard: only accept a consolidatedResults.json actually written during
        # THIS execution window (mtime ≥ subprocess start). A stale artifact is ignored.
        have_result = os.path.exists(result_path) and _is_fresh(result_path, exec_start)

        exec_state = {
            "execution_completed": (exit_code == 0 and have_result and not timed_out),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_sec": duration,
            "workspace": ws,                              # admin-only; never surfaced to non-admin
            "raw_result_path": result_path if have_result else None,
            "stdout_tail": _redact_text(_tail(stdout)),
            "stderr_tail": _redact_text(_tail(stderr)),
            "config_snapshot": redact(change_me),
        }
        _emit("NORMALIZING_RESULTS")
        if exit_code == 0 and have_result and not timed_out:
            normalized = oda_ctk_results.normalize_from_path(result_path, contract, exec_state)
        else:
            err = _classify_failure(exit_code, stdout, stderr, timed_out)
            if exit_code == 0 and not have_result:
                stale = os.path.exists(result_path) and not _is_fresh(result_path, exec_start)
                err = {"category": RESULT_PARSE_ERROR,
                       "message": ("executor completed but consolidatedResults.json is stale "
                                   "(not written this run)" if stale else
                                   "executor completed but consolidatedResults.json is missing")}
            exec_state["execution_error"] = err
            normalized = oda_ctk_results.normalize(None, contract, exec_state)
        return exec_state, normalized
    except Exception as e:
        exec_state = {"execution_completed": False, "workspace": ws,
                      "execution_error": {"category": EXECUTION_ERROR, "message": str(e)}}
        return exec_state, oda_ctk_results.normalize(None, contract, exec_state)


def cleanup_workspace(workspace: str):
    """Safe workspace removal — only paths we created under the system temp prefix."""
    if not workspace:
        return
    base = os.path.basename(workspace)
    if base.startswith("synaptdi_odactk_") and os.path.isdir(workspace):
        shutil.rmtree(workspace, ignore_errors=True)


def _within_workspace(workspace: str, path: str) -> bool:
    """True iff `path` resolves to inside the given synaptdi_odactk_ workspace
    (prefix-guarded and realpath-resolved to defeat traversal). Guards every
    stale-artifact deletion so nothing outside our own workspace is ever removed."""
    if not workspace or not os.path.basename(workspace.rstrip(os.sep)).startswith("synaptdi_odactk_"):
        return False
    try:
        ws = os.path.realpath(workspace)
        p = os.path.realpath(path)
        return p == ws or p.startswith(ws + os.sep)
    except Exception:
        return False


# Only these known, generated result locations are ever removed (never arbitrary paths).
_RESULT_SUBPATHS = (
    ("resources", "results"),
    ("resources", "reports"),
    ("resources", "consolidatedResults.json"),
    ("Reports",),
)


def purge_result_paths(workspace: str, component_ctk_dir: str):
    """Remove the KNOWN generated result paths inside our isolated workspace before a run,
    so a prior artifact can never contaminate a new verdict. Every target is validated to
    live under the synaptdi_odactk_ workspace; nothing outside it is ever touched."""
    for parts in _RESULT_SUBPATHS:
        target = os.path.join(component_ctk_dir, *parts)
        if not _within_workspace(workspace, target):
            continue                                     # strict prefix guard
        try:
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            elif os.path.isfile(target):
                os.remove(target)
        except Exception:
            pass


def _is_fresh(path: str, since_ts: float, slack: float = 2.0) -> bool:
    """True iff `path` was written no earlier than `since_ts` (minus a small filesystem
    clock-resolution slack) — i.e. produced by the current execution, not a stale run."""
    try:
        return os.path.getmtime(path) >= (since_ts - slack)
    except Exception:
        return False


def _redact_text(s: str) -> str:
    """Redact obvious secret-bearing lines from captured logs (Authorization: Bearer …,
    tokens, kubeconfig data)."""
    if not s:
        return s
    out = []
    for line in s.splitlines():
        if _SECRET_KEY.search(line):
            key = line.split(":", 1)[0] if ":" in line else line[:40]
            out.append(f"{key}: {_REDACTED}")
        else:
            out.append(line)
    return "\n".join(out)
