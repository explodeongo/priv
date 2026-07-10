"use client";
import { useEffect, useRef, useState } from "react";
import { Card, Button, Badge } from "../../components/ui";
import { Contract } from "../../lib/odaCtk";
import { CatalogComponent, componentBadges, canRunExecution } from "../../lib/odaCatalog";
import ODAContractPanel from "./ODAContractPanel";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Component details page. Actions are gated on the backend-derived flags: "Run Component
// CTK" only when execution is supported; "View Contract"/"View Requirements" only when a
// canonical contract is vendored. The contract is rendered by the EXISTING ODAContractPanel
// (which already lists the mandatory/optional requirements) — no requirements renderer is
// duplicated. "Run Component CTK" is wired by the parent to the existing execution UI.
export default function ODAComponentDetail({ component, release, onBack, onRun }: {
  component: CatalogComponent;
  release?: string;
  onBack: () => void;
  onRun: () => void;
}) {
  const [showContract, setShowContract] = useState(false);
  const [contract, setContract] = useState<Contract | null>(null);
  const [contractError, setContractError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const contractRef = useRef<HTMLDivElement | null>(null);

  const runnable = canRunExecution(component);

  // Lazily fetch the deterministic contract the first time it is revealed.
  useEffect(() => {
    if (!showContract || contract || !component.contract_available) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setContractError(null);
      try {
        const r = await fetch(`${API}/oda/components/${component.code}/contract`);
        if (!r.ok) throw new Error(`Contract request failed (HTTP ${r.status})`);
        const data = await r.json();
        if (!cancelled) setContract(data);
      } catch (e) {
        if (!cancelled) setContractError(e instanceof Error ? e.message : "Could not load the contract.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [showContract, contract, component.code, component.contract_available]);

  const revealContract = () => {
    setShowContract(true);
    // Defer so the panel exists before we scroll to it.
    requestAnimationFrame(() => contractRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };

  const noContractHint = component.contract_available
    ? undefined
    : "A canonical contract is not yet vendored for this component.";

  return (
    <div className="space-y-5">
      <button onClick={onBack}
        className="text-xs text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200">
        ← Back to catalog
      </button>

      <Card className="p-5">
        <div className="flex items-center gap-2 flex-wrap">
          <code className="text-xs font-mono bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-300 rounded px-1.5 py-0.5">{component.code}</code>
          <span className="text-xs text-gray-400 dark:text-slate-500">{component.block}</span>
          {release && <span className="text-xs text-gray-400 dark:text-slate-500">· Release {release}</span>}
        </div>
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mt-1.5">{component.name}</h2>

        <div className="flex flex-wrap gap-1.5 mt-3">
          {componentBadges(component).map((b) => <Badge key={b.label} tone={b.tone}>{b.label}</Badge>)}
        </div>

        <div className="flex flex-wrap gap-2 mt-5">
          <Button variant="primary" onClick={onRun} disabled={!runnable}
            title={runnable ? undefined : "Execution support is coming soon for this component."}>
            Run Component CTK
          </Button>
          <Button variant="secondary" onClick={() => setShowContract((s) => !s)} disabled={!component.contract_available}
            title={noContractHint}>
            {showContract ? "Hide Contract" : "View Contract"}
          </Button>
          <Button variant="ghost" onClick={revealContract} disabled={!component.contract_available}
            title={noContractHint}>
            View Requirements
          </Button>
        </div>

        {!runnable && (
          <p className="text-xs text-gray-400 dark:text-slate-500 mt-3 leading-relaxed">
            Execution-backed CTK is currently available for <span className="font-mono">TMFC043</span> only.
            Other components show their catalog entry and, where vendored, their canonical contract; execution
            arrives in a later phase.
          </p>
        )}
      </Card>

      {showContract && component.contract_available && (
        <div ref={contractRef}>
          {loading ? (
            <Card className="p-8 text-center text-sm text-gray-400 dark:text-slate-500">Resolving canonical contract…</Card>
          ) : contractError ? (
            <Card className="p-5 border-red-200 dark:border-red-500/40">
              <div className="text-sm font-medium text-red-700 dark:text-red-300">Could not load the contract</div>
              <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">{contractError}</p>
            </Card>
          ) : contract ? (
            <ODAContractPanel contract={contract} />
          ) : null}
        </div>
      )}
    </div>
  );
}
