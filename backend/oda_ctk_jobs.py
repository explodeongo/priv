"""
ODA Component CTK job model (execution-backed conformance, layer D)
═══════════════════════════════════════════════════════════════════
A minimal in-process job store for long-running CTK executions. Job LIFECYCLE state
(CREATED…COMPLETED/FAILED_EXECUTION) is kept strictly separate from the conformance
VERDICT (PASS/FAIL/INCOMPLETE/EXECUTION_ERROR, produced by oda_ctk_results). States are
only ever set at real stage boundaries — RUNNING_CTK is reported only while the executor
subprocess is genuinely running (driven by the adapter's on_state hook). No fake %.

Non-admin serialization never exposes server filesystem paths or secrets.
"""
import threading
import time
import uuid

import oda_ctk_adapter
import oda_ctk_sanitize

# Finite, explicit lifecycle states.
CREATED = "CREATED"
VALIDATING = "VALIDATING"
READY = "READY"
PREPARING_WORKSPACE = "PREPARING_WORKSPACE"
RUNNING_CTK = "RUNNING_CTK"
NORMALIZING_RESULTS = "NORMALIZING_RESULTS"
COMPLETED = "COMPLETED"                    # lifecycle done; verdict ∈ {PASS, FAIL, INCOMPLETE}
FAILED_EXECUTION = "FAILED_EXECUTION"      # the execution itself failed (verdict == EXECUTION_ERROR)

_JOBS = {}
_LOCK = threading.Lock()


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_job(req: dict, owner_id: str = None) -> dict:
    return {
        "job_id": uuid.uuid4().hex,
        "component_id": (req.get("component_id") or "").upper(),
        "component_version": req.get("component_version"),
        "state": CREATED,
        "created_at": _now(),
        "started_at": None,
        "completed_at": None,
        "execution_error": None,
        "config_snapshot": oda_ctk_adapter.redact(oda_ctk_adapter.generate_change_me(req)),
        "result": None,
        "stdout_tail": None,
        "stderr_tail": None,
        "_workspace": None,          # private, never serialized to clients
        "_request": dict(req),       # private
        "_owner_id": owner_id,       # private — the authenticated user who created this job
    }


def _set(job_id: str, **patch):
    with _LOCK:
        job = _JOBS.get(job_id)
        if job:
            job.update(patch)


def create_execution_job(req: dict, owner_id: str = None) -> dict:
    """Create a job and start REAL CTK execution in a background thread. Returns the
    job immediately (state CREATED/VALIDATING); poll GET for progress. `owner_id` binds
    the job to the authenticated caller so only they (or an admin) can later read it."""
    job = _new_job(req, owner_id)
    with _LOCK:
        _JOBS[job["job_id"]] = job
    threading.Thread(target=_run_job, args=(job["job_id"],), daemon=True).start()
    return oda_ctk_sanitize.sanitize_job_view(job, is_admin=False)


def _run_job(job_id: str):
    _set(job_id, state=VALIDATING)
    with _LOCK:
        req = dict(_JOBS[job_id]["_request"])
    errors = oda_ctk_adapter.validate_request(req)
    contract = oda_ctk_adapter.oda_component_contract.resolve_contract(
        req.get("component_id"), req.get("component_version"))
    if errors or contract.get("status") != "RESOLVED":
        exec_state, normalized = oda_ctk_adapter.execute(req)   # returns CONFIGURATION_ERROR fast
        _set(job_id, state=FAILED_EXECUTION, completed_at=_now(),
             execution_error=exec_state.get("execution_error"), result=normalized)
        return

    _set(job_id, state=READY, started_at=_now())

    def on_state(stage):
        # Only real stages, emitted by the adapter at true boundaries.
        if stage in (PREPARING_WORKSPACE, RUNNING_CTK, NORMALIZING_RESULTS):
            _set(job_id, state=stage)

    exec_state, normalized = oda_ctk_adapter.execute(req, on_state=on_state)

    workspace = exec_state.get("workspace")
    verdict = normalized.get("overall_status")
    patch = {
        "completed_at": _now(),
        "result": normalized,
        "stdout_tail": exec_state.get("stdout_tail"),
        "stderr_tail": exec_state.get("stderr_tail"),
        "_workspace": workspace,
        "execution_error": exec_state.get("execution_error"),
    }
    if exec_state.get("execution_completed") and verdict in ("PASS", "FAIL", "INCOMPLETE"):
        patch["state"] = COMPLETED
    else:
        patch["state"] = FAILED_EXECUTION
    _set(job_id, **patch)
    # Best-effort workspace cleanup (results already parsed into the normalized model).
    oda_ctk_adapter.cleanup_workspace(workspace)
    _set(job_id, _workspace=None)


def _owned(job: dict, requester_id, is_admin: bool) -> bool:
    """A job is visible to its creator or to an admin. If the job predates ownership
    binding (owner_id is None — should not happen post-Phase-4, kept defensively) it is
    NOT auto-visible to arbitrary callers; only an admin can read it."""
    if is_admin:
        return True
    owner = job.get("_owner_id")
    return owner is not None and requester_id is not None and owner == requester_id


def get_job(job_id: str, requester_id=None, is_admin: bool = False):
    """Returns the client-safe job view, or None if the job doesn't exist OR the
    requester does not own it (deliberately indistinguishable from not-found — a
    non-owner must not learn that a given job_id exists)."""
    with _LOCK:
        job = _JOBS.get(job_id)
    if not job or not _owned(job, requester_id, is_admin):
        return None
    return oda_ctk_sanitize.sanitize_job_view(job, is_admin=is_admin)


def get_results(job_id: str, requester_id=None, is_admin: bool = False):
    with _LOCK:
        job = _JOBS.get(job_id)
    if not job or not _owned(job, requester_id, is_admin):
        return None
    view = oda_ctk_sanitize.sanitize_job_view(job, is_admin=is_admin)
    return {"job_id": job_id, "state": view["state"], "result": view.get("result")}
