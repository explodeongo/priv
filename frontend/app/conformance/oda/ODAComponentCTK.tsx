"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Card, Button, Badge, EmptyState } from "../../components/ui";
import { useAuth } from "../../components/AuthProvider";
import { Contract, DryRun, Job, isTerminal } from "../../lib/odaCtk";
import ODAContractPanel from "./ODAContractPanel";
import ODAExecutionConfig, { CtkFormValue, EMPTY_CONFIG } from "./ODAExecutionConfig";
import ODAValidationResult from "./ODAValidationResult";
import ODAJobTimeline from "./ODAJobTimeline";
import ODACTKVerdict from "./ODACTKVerdict";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const COMPONENT_ID = "TMFC043"; // Phase 1 golden path — the only execution-backed component.

// Build the backend ODACTKJobReq body. The Authorization secret is injected here (POST
// body only — never a query parameter) and is passed in explicitly by the caller so it is
// never read from a stale render.
function buildReq(cfg: CtkFormValue, authorization: string) {
  const headers = authorization
    ? { Accept: "application/json", "Content-Type": "application/json", Authorization: authorization }
    : {};
  return {
    component_id: COMPONENT_ID,
    component_version: null,
    release_name: cfg.release_name.trim(),
    namespace: cfg.namespace.trim() || "components",
    run_exposed_optional: cfg.run_exposed_optional,
    run_dependent_optional: cfg.run_dependent_optional,
    run_security_optional: cfg.run_security_optional,
    ctkconfig: {
      company_name: cfg.company_name.trim(),
      product_name: cfg.product_name.trim(),
      product_url: cfg.product_url.trim(),
      product_version: cfg.product_version.trim(),
      headers,
      payloads: {},
      reject_unauthorized: cfg.reject_unauthorized,
    },
  };
}

const REQUIRED: (keyof CtkFormValue)[] = [
  "release_name", "company_name", "product_name", "product_url", "product_version",
];

export default function ODAComponentCTK() {
  // SynaptDI's own session token (separate from the deployed-component Authorization the
  // user enters below — that one travels only inside the POST body's ctkconfig.headers).
  const { token } = useAuth();
  const authHeaders = useCallback((): HeadersInit => ({
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }), [token]);

  const [contract, setContract] = useState<Contract | null>(null);
  const [contractError, setContractError] = useState<string | null>(null);
  const [loadingContract, setLoadingContract] = useState(true);

  const [config, setConfig] = useState<CtkFormValue>(EMPTY_CONFIG);
  // The live Authorization secret lives ONLY here (in-memory, per-tab). It is never written
  // to localStorage, never bound back into an input after arming, never put in a URL.
  const authRef = useRef<string>("");
  const [authArmed, setAuthArmed] = useState(false);

  const [dryRun, setDryRun] = useState<DryRun | null>(null);
  const [validating, setValidating] = useState(false);
  const [validateError, setValidateError] = useState<string | null>(null);

  const [job, setJob] = useState<Job | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);

  // ── Contract (deterministic, no LLM) ─────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingContract(true);
      setContractError(null);
      try {
        const r = await fetch(`${API}/oda/components/${COMPONENT_ID}/contract`);
        if (!r.ok) throw new Error(`Contract request failed (HTTP ${r.status})`);
        const data = await r.json();
        if (!cancelled) setContract(data);
      } catch (e) {
        if (!cancelled) setContractError(e instanceof Error ? e.message : "Could not load the component contract.");
      } finally {
        if (!cancelled) setLoadingContract(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // ── Job polling — only real backend states, no synthetic progress ────────────
  const jobId = job?.job_id;
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const iv = setInterval(async () => {
      try {
        const r = await fetch(`${API}/oda/conformance/jobs/${jobId}`, { headers: authHeaders() });
        if (!r.ok) throw new Error();
        const next: Job = await r.json();
        if (cancelled) return;
        setJob(next);
        setPollError(null);
        if (isTerminal(next.state)) clearInterval(iv);
      } catch {
        // Transport failure is a UI condition — NOT a conformance/execution verdict.
        if (!cancelled) setPollError("Temporarily lost contact with the job. Execution continues on the server; retrying…");
      }
    }, 1500);
    return () => { cancelled = true; clearInterval(iv); };
  }, [jobId, authHeaders]);

  const canValidate = REQUIRED.every((k) => String(config[k] || "").trim().length > 0);

  const onValidate = useCallback(async () => {
    // Arm the secret once, then stop displaying it. Re-validations reuse the armed value.
    const typed = config.authorization.trim();
    const auth = typed || authRef.current;
    if (typed) {
      authRef.current = typed;
      setAuthArmed(true);
      setConfig((c) => ({ ...c, authorization: "" }));
    }
    setValidating(true);
    setValidateError(null);
    setRunError(null);
    setJob(null);           // a new validation supersedes any prior run
    setPollError(null);
    try {
      const r = await fetch(`${API}/oda/conformance/jobs/validate`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(buildReq(config, auth)),
      });
      if (!r.ok) throw new Error(`Validation request failed (HTTP ${r.status})`);
      setDryRun(await r.json());
    } catch (e) {
      setDryRun(null);
      setValidateError(e instanceof Error ? e.message : "Validation request failed.");
    } finally {
      setValidating(false);
    }
  }, [config, authHeaders]);

  const onReplaceAuth = useCallback(() => {
    authRef.current = "";
    setAuthArmed(false);
    setConfig((c) => ({ ...c, authorization: "" }));
  }, []);

  const onRun = useCallback(async () => {
    setRunning(true);
    setRunError(null);
    setPollError(null);
    try {
      const r = await fetch(`${API}/oda/conformance/jobs`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(buildReq(config, authRef.current)),
      });
      if (!r.ok) throw new Error(`Could not start execution (HTTP ${r.status})`);
      const created: Job = await r.json();
      // The secret has been handed to the backend job; wipe it from the client's memory.
      authRef.current = "";
      setJob(created);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : "Could not start execution.");
    } finally {
      setRunning(false);
    }
  }, [config, authHeaders]);

  const onReset = useCallback(() => {
    setJob(null);
    setDryRun(null);
    setRunError(null);
    setPollError(null);
    setConfig((c) => ({ ...c, authorization: "" }));
    // keep authArmed as-is so a captured secret stays hidden; user can Replace to change it
  }, []);

  const terminal = job ? isTerminal(job.state) : false;

  return (
    <div className="space-y-5">
      {/* Scope note — do not imply support beyond TMFC043 */}
      <div className="flex items-start gap-2 text-xs text-gray-500 dark:text-slate-400 bg-gray-50 dark:bg-slate-800/40 border border-gray-200 dark:border-slate-800 rounded-xl px-4 py-2.5">
        <Badge tone="blue">Execution</Badge>
        <span>Execution support is currently available for <span className="font-mono font-semibold text-gray-700 dark:text-slate-200">TMFC043</span> (Fault Management). This runs the real TM Forum Component CTK against your deployed component and derives the verdict from CTK evidence.</span>
      </div>

      {/* Contract view (deterministic requirements — not results) */}
      {loadingContract ? (
        <Card className="p-8 text-center text-sm text-gray-400 dark:text-slate-500">Resolving canonical contract…</Card>
      ) : contractError ? (
        <Card className="p-5 border-red-200 dark:border-red-500/40">
          <div className="text-sm font-medium text-red-700 dark:text-red-300">Could not load the component contract</div>
          <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">{contractError}</p>
        </Card>
      ) : contract ? (
        <ODAContractPanel contract={contract} />
      ) : (
        <EmptyState title="No contract" hint="The canonical contract could not be resolved." />
      )}

      {/* Configuration + validation (hidden once a run has started) */}
      {!job && contract && (
        <>
          <ODAExecutionConfig
            value={config}
            onChange={setConfig}
            onValidate={onValidate}
            validating={validating}
            running={running}
            canValidate={canValidate}
            authArmed={authArmed}
            onReplaceAuth={onReplaceAuth}
          />
          {validateError && (
            <div className="text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-xl px-4 py-2.5">
              {validateError}
            </div>
          )}
          {dryRun && (
            <ODAValidationResult
              dryRun={dryRun}
              onRun={onRun}
              running={running}
              runDisabledReason={dryRun.status !== "READY_TO_EXECUTE" ? "Resolve the configuration errors above before running." : null}
            />
          )}
          {runError && (
            <div className="text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-xl px-4 py-2.5">
              {runError}
            </div>
          )}
        </>
      )}

      {/* Execution timeline + verdict */}
      {job && (
        <>
          <ODAJobTimeline state={job.state} />
          {pollError && !terminal && (
            <div className="text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-xl px-4 py-2.5">
              {pollError}
            </div>
          )}
          {terminal && <ODACTKVerdict job={job} />}
          {terminal && (
            <div>
              <Button variant="secondary" onClick={onReset}>Configure another run</Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
