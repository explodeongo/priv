// Pure catalog logic + types for the ODA Component Catalog (Phase 6A).
// No React, no side effects — search + badge derivation are unit-tested (odaCatalog.test.ts).
// Availability flags come from the backend (GET /oda/components); this file only PRESENTS
// them. It NEVER fabricates execution support or contract availability — a component shows
// "Execution Ready" / "Contract Available" only when the backend says so.

export interface CatalogApi {
  name?: string;
  tmf?: string;
  segment?: string;
}

export interface CatalogComponent {
  code: string;                 // TMFCNNN — the component id
  short: string;                // e.g. FaultManagement
  name: string;                 // e.g. Fault Management
  block: string;                // functional block
  spec_url?: string;
  exposed?: CatalogApi[];
  dependent?: CatalogApi[];
  // Derived, backend-authoritative availability flags (see backend/oda.py::component_status):
  supported_execution: boolean;
  contract_available: boolean;
  specification_available: boolean;
}

export interface Catalog {
  source?: string;
  release?: string;
  directory_url?: string;
  blocks?: Record<string, unknown> | unknown[];
  components: CatalogComponent[];
}

// ── Search (client-side) — by component id (code), name, short name, or functional block ──
export function filterComponents(components: CatalogComponent[], query: string): CatalogComponent[] {
  const q = (query || "").trim().toLowerCase();
  if (!q) return components;
  return components.filter((c) =>
    (c.code || "").toLowerCase().includes(q) ||
    (c.name || "").toLowerCase().includes(q) ||
    (c.short || "").toLowerCase().includes(q) ||
    (c.block || "").toLowerCase().includes(q)
  );
}

// ── Badge derivation (never fabricates support/availability) ──────────────────────────
export type BadgeTone = "green" | "blue" | "gray" | "amber";
export interface CatalogBadge { tone: BadgeTone; label: string; }

export function componentBadges(c: CatalogComponent): CatalogBadge[] {
  const badges: CatalogBadge[] = [];
  if (c.supported_execution) badges.push({ tone: "green", label: "Execution Ready" });
  if (c.contract_available) badges.push({ tone: "blue", label: "Contract Available" });
  if (c.specification_available) badges.push({ tone: "gray", label: "Specification Available" });
  // Honest negative state: only shown when execution is genuinely not (yet) supported.
  if (!c.supported_execution) badges.push({ tone: "amber", label: "Execution Coming Soon" });
  return badges;
}

// Whether the "Run Component CTK" action is available — strictly mirrors the backend flag.
export function canRunExecution(c: CatalogComponent | null | undefined): boolean {
  return !!c && c.supported_execution === true;
}
