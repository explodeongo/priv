"""
Centralized public-response sanitization boundary (execution-backed conformance, layer E)
════════════════════════════════════════════════════════════════════════════════════════
Every value that reaches an ODA Component CTK API client — job view, results view,
dry-run/validate response, contract error — MUST pass through this module. It is the
ONLY place that decides what a caller may see. No other module should hand-roll
redaction; oda_ctk_jobs.py / main.py call these functions rather than string-replacing
inline (Phase 4 audit finding: scattered ad-hoc redaction missed `result.raw_result_path`,
the dry-run `errors` list, and the contract PARSE_ERROR reason — see PHASE4_AUDIT.md).

Two independent concerns, both handled here:
  1. SECRETS  — dict keys that look like Authorization/token/kubeconfig/etc. Values
     redacted regardless of nesting depth (existing behavior, centralized).
  2. HOST PATHS — absolute filesystem paths (the isolated CTK workspace, the framework
     install path, the Python interpreter path, `str(exception)` reprs that embed a
     path) must never reach a client. Free text is scrubbed; filenames are collapsed to
     their basename. This is heuristic/regex-based, so it is defense-in-depth layered
     ON TOP OF removing the worst offenders (raw stdout/stderr tails) from the non-admin
     response entirely, rather than a sole line of defense.

Trust boundary this module does NOT change: the conformance VERDICT (PASS/FAIL/
INCOMPLETE/EXECUTION_ERROR) and every numeric coverage field are passed through
unmodified. This module only ever removes or rewrites TEXT/PATH content — never a
verdict, count, or outcome.
"""
import re

# ── Secrets (dict keys whose VALUES must never be returned) ───────────────────────────
_SECRET_KEY = re.compile(r"authorization|bearer|api[-_]?key|x-api-key|token|cookie|"
                         r"password|passwd|secret|kubeconfig|credential", re.I)
_REDACTED = "***REDACTED***"


def redact_secrets(obj):
    """Deep-copy with secret-named dict VALUES redacted. Safe on any JSON-shaped value."""
    if isinstance(obj, dict):
        return {k: (_REDACTED if isinstance(k, str) and _SECRET_KEY.search(k) else redact_secrets(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    return obj


# ── Host filesystem paths (free text + filenames) ──────────────────────────────────────
_SENSITIVE_ROOT = r"(?:Users|home|root|private|var|tmp|opt|etc|srv|mnt|Applications|proc|dev)"
_POSIX_ABS = re.compile(rf"/{_SENSITIVE_ROOT}(?:/[^\s\"'()\[\]]*)?")
_WORKSPACE_DIR = re.compile(r"synaptdi_odactk_[A-Za-z0-9_]+")
_WIN_ABS = re.compile(r"[A-Za-z]:\\[^\s\"']*")


def _basename_of(path_like: str) -> str:
    tail = re.split(r"[\\/]", path_like.rstrip("/\\"))
    return (tail[-1] if tail and tail[-1] else "‹path hidden›")


def _redact_secret_lines(text: str) -> str:
    """Line-based secret redaction for free text (stdout/stderr tails, exception
    messages). The adapter already does this once at capture time
    (oda_ctk_adapter._redact_text); this is defense-in-depth so the public-response
    boundary does not rely solely on that earlier pass catching everything."""
    out = []
    for line in text.splitlines():
        if _SECRET_KEY.search(line):
            key = line.split(":", 1)[0] if ":" in line else line[:40]
            out.append(f"{key}: {_REDACTED}")
        else:
            out.append(line)
    return "\n".join(out)


def sanitize_text(s):
    """Free-text scrub, applied uniformly to every text field a client can see:
    - secret-bearing lines (Authorization/token/kubeconfig/etc, by key-like prefix)
      are redacted line-by-line — defense-in-depth on top of the adapter's own capture-
      time redaction, not a replacement for it;
    - absolute POSIX/Windows paths under a sensitive root, and any reference to the
      isolated workspace directory name, are collapsed to a neutral marker (or their
      basename, when that preserves useful meaning).
    Non-secret, non-path text (error categories, human messages, URLs) passes through
    unchanged. None-safe."""
    if s is None:
        return None
    if not isinstance(s, str):
        s = str(s)
    out = _redact_secret_lines(s)
    out = _POSIX_ABS.sub(lambda m: _basename_of(m.group(0)), out)
    out = _WORKSPACE_DIR.sub("‹workspace›", out)
    out = _WIN_ABS.sub(lambda m: _basename_of(m.group(0)), out)
    return out


def sanitize_filename(name):
    """A CTK result filename is legitimate evidence to show (e.g. 'TMF642_v4.json') but
    must never be an absolute/host path — collapse anything path-shaped to its basename."""
    if not name:
        return name
    s = str(name)
    looks_absolute = (s.startswith("/") or s.startswith("\\")
                       or re.match(r"^[A-Za-z]:\\", s) or "synaptdi_odactk_" in s)
    return _basename_of(s) if looks_absolute else s


# ── Composite sanitizers for each shape returned by the ODA CTK endpoints ─────────────
def sanitize_error(err):
    """execution_error {category, message?, messages?} → category kept as-is (a fixed,
    curated enum — see oda_ctk_adapter.CONFIGURATION_ERROR etc.), free text scrubbed."""
    if not isinstance(err, dict):
        return err
    out = redact_secrets(err)
    if "message" in out:
        out["message"] = sanitize_text(out["message"])
    if isinstance(out.get("messages"), list):
        out["messages"] = [sanitize_text(m) for m in out["messages"]]
    return out


def _sanitize_failed_test(f):
    if not isinstance(f, dict):
        return f
    out = dict(f)
    if "detail" in out:
        out["detail"] = sanitize_text(out["detail"])
    if "result_file" in out:
        out["result_file"] = sanitize_filename(out["result_file"])
    return out


def _sanitize_requirement_row(r):
    if not isinstance(r, dict):
        return r
    out = dict(r)
    if "reason" in out:
        out["reason"] = sanitize_text(out["reason"])
    if "result_file" in out:
        out["result_file"] = sanitize_filename(out["result_file"])
    if isinstance(out.get("result_files"), list):
        out["result_files"] = [sanitize_filename(x) for x in out["result_files"]]
    return out


def _sanitize_evidence(ev):
    if not isinstance(ev, dict):
        return ev
    out = dict(ev)
    if isinstance(out.get("execution_error"), str):
        out["execution_error"] = sanitize_text(out["execution_error"])
    if "result_parse_error" in out:
        out["result_parse_error"] = sanitize_text(out["result_parse_error"])
    if isinstance(out.get("api_ctk_result_files"), list):
        out["api_ctk_result_files"] = [sanitize_filename(x) for x in out["api_ctk_result_files"]]
    return out


def sanitize_result(result):
    """Normalized CTK result → client-safe copy.
    - `raw_result_path` (a host workspace path — set on every completed execution, not
      only on error) is REMOVED outright; it has no legitimate client-facing use.
    - `warnings` / `failed_tests[].detail` / `per_requirement_results[].reason` are
      scrubbed (these can echo untrusted consolidatedResults.json content, e.g. a
      hostile componentName string, or an adapter-side exception str()).
    - `result_file` fields are collapsed to a basename.
    Verdict fields (overall_status, mandatory_*, per_requirement outcome/versions) are
    returned unmodified — this function never touches the conformance verdict."""
    if not isinstance(result, dict):
        return result
    out = dict(result)
    out.pop("raw_result_path", None)
    if isinstance(out.get("warnings"), list):
        out["warnings"] = [sanitize_text(w) for w in out["warnings"]]
    if isinstance(out.get("failed_tests"), list):
        out["failed_tests"] = [_sanitize_failed_test(f) for f in out["failed_tests"]]
    if isinstance(out.get("per_requirement_results"), list):
        out["per_requirement_results"] = [_sanitize_requirement_row(r) for r in out["per_requirement_results"]]
    if isinstance(out.get("evidence"), dict):
        out["evidence"] = _sanitize_evidence(out["evidence"])
    return out


def sanitize_job_view(job: dict, is_admin: bool = False) -> dict:
    """THE function that builds a client-facing job JSON — replaces ad-hoc `public_view`.
    Drops private `_`-prefixed keys (workspace path, raw request), then sanitizes every
    remaining field. Raw stdout/stderr tails are an ADMIN-ONLY debugging aid (the
    frontend never renders them; a non-admin owner gets the curated execution_error
    instead) — and even for admins, host paths inside them are scrubbed, since the
    workspace is already deleted by the time anyone reads the job and a raw path has no
    remaining operational value to anyone."""
    out = {k: v for k, v in job.items() if not (isinstance(k, str) and k.startswith("_"))}
    if out.get("execution_error"):
        out["execution_error"] = sanitize_error(out["execution_error"])
    if out.get("result"):
        out["result"] = sanitize_result(out["result"])
    if out.get("config_snapshot"):
        out["config_snapshot"] = redact_secrets(out["config_snapshot"])
    if is_admin:
        if out.get("stdout_tail"):
            out["stdout_tail"] = sanitize_text(out["stdout_tail"])
        if out.get("stderr_tail"):
            out["stderr_tail"] = sanitize_text(out["stderr_tail"])
    else:
        out.pop("stdout_tail", None)
        out.pop("stderr_tail", None)
    return out


def sanitize_dry_run(dry_run: dict) -> dict:
    """POST /oda/conformance/jobs/validate response. `errors` can include a raised
    exception's str() (e.g. FileNotFoundError with the framework's host install path,
    or a workspace-preparation OSError) — scrub before returning."""
    if not isinstance(dry_run, dict):
        return dry_run
    out = dict(dry_run)
    if isinstance(out.get("errors"), list):
        out["errors"] = [sanitize_text(e) for e in out["errors"]]
    if "generated_change_me" in out:
        out["generated_change_me"] = redact_secrets(out["generated_change_me"])
    return out


def sanitize_reason(reason):
    """A contract-resolution `reason` string (e.g. PARSE_ERROR) may embed a YAML
    parser exception whose repr carries the vendored asset's absolute host path."""
    return sanitize_text(reason)
