"use client";
import { useMemo, useState } from "react";
import { Card, Input, Badge } from "../../components/ui";
import { Catalog, filterComponents, componentBadges } from "../../lib/odaCatalog";

// Searchable ODA Component Catalog. Client-side search by TMFC code, name, short name, or
// functional block. Every badge is derived from the backend flags (odaCatalog.componentBadges).
export default function ODACatalog({ catalog, onSelect }: {
  catalog: Catalog;
  onSelect: (code: string) => void;
}) {
  const [q, setQ] = useState("");
  const results = useMemo(() => filterComponents(catalog.components, q), [catalog.components, q]);

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-gray-900 dark:text-white">ODA Component Catalog</h2>
        <p className="text-sm text-gray-500 dark:text-slate-400 mt-0.5">
          {catalog.components.length} official TM Forum ODA components
          {catalog.release ? ` · ${catalog.release}` : ""}. Select a component to see its details.
        </p>
      </div>

      <Input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Search components — TMFC code, name, or functional block…"
        aria-label="Search ODA components"
      />

      {results.length === 0 ? (
        <Card className="p-8 text-center text-sm text-gray-400 dark:text-slate-500">
          No components match “{q.trim()}”.
        </Card>
      ) : (
        <div className="grid sm:grid-cols-2 gap-3">
          {results.map((c) => (
            <button
              key={c.code}
              onClick={() => onSelect(c.code)}
              className="text-left rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/50"
            >
              <Card className="p-4 h-full hover:border-gray-300 dark:hover:border-slate-700 hover:shadow transition-all">
                <div className="flex items-center gap-2">
                  <code className="text-[11px] font-mono bg-gray-100 dark:bg-slate-800 text-gray-500 dark:text-slate-400 rounded px-1.5 py-0.5">{c.code}</code>
                  <span className="text-xs text-gray-400 dark:text-slate-500 truncate">{c.block}</span>
                </div>
                <div className="text-sm font-semibold text-gray-900 dark:text-slate-100 mt-1.5">{c.name}</div>
                <div className="flex flex-wrap gap-1.5 mt-2.5">
                  {componentBadges(c).map((b) => <Badge key={b.label} tone={b.tone}>{b.label}</Badge>)}
                </div>
              </Card>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
