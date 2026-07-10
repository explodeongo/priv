"use client";
import { useEffect, useMemo, useState } from "react";
import { Card } from "../../components/ui";
import { Catalog, CatalogComponent, canRunExecution } from "../../lib/odaCatalog";
import ODACatalog from "./ODACatalog";
import ODAComponentDetail from "./ODAComponentDetail";
import ODAComponentCTK from "./ODAComponentCTK";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type View = "catalog" | "detail" | "execute";

// Orchestrates the catalog → detail → execution flow. Selection from the catalog and the
// (future) drag-drop path converge on the SAME per-component state here. Crucially, running
// the CTK renders the existing, unmodified <ODAComponentCTK /> — the golden TMFC043
// execution UI is reached THROUGH the catalog, never duplicated or forked.
export default function ODACatalogFlow() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>("catalog");
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const r = await fetch(`${API}/oda/components`);
        if (!r.ok) throw new Error(`Catalog request failed (HTTP ${r.status})`);
        const data = await r.json();
        if (!cancelled) setCatalog(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load the ODA component catalog.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const selectedComponent: CatalogComponent | null = useMemo(
    () => catalog?.components.find((c) => c.code === selected) ?? null,
    [catalog, selected],
  );

  if (loading) {
    return <Card className="p-8 text-center text-sm text-gray-400 dark:text-slate-500">Loading the ODA component catalog…</Card>;
  }
  if (error) {
    return (
      <Card className="p-5 border-red-200 dark:border-red-500/40">
        <div className="text-sm font-medium text-red-700 dark:text-red-300">Could not load the catalog</div>
        <p className="text-xs text-gray-500 dark:text-slate-400 mt-1">{error}</p>
      </Card>
    );
  }
  if (!catalog) return null;

  // Catalog list (default, and the safe fallback if nothing is selected).
  if (view === "catalog" || !selectedComponent) {
    return <ODACatalog catalog={catalog} onSelect={(code) => { setSelected(code); setView("detail"); }} />;
  }

  // Execution — the EXISTING TMFC043 execution UI, reached through the catalog. Guarded so
  // only an execution-supported component can ever render it.
  if (view === "execute" && canRunExecution(selectedComponent)) {
    return (
      <div className="space-y-4">
        <button onClick={() => setView("detail")}
          className="text-xs text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200">
          ← Back to {selectedComponent.code} details
        </button>
        <ODAComponentCTK />
      </div>
    );
  }

  // Component details.
  return (
    <ODAComponentDetail
      component={selectedComponent}
      release={catalog.release}
      onBack={() => { setView("catalog"); setSelected(null); }}
      onRun={() => setView("execute")}
    />
  );
}
