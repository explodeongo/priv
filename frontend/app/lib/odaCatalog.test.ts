// Unit tests for the ODA Component Catalog display logic (pure, no React/DOM).
// Runner (same pattern as odaCtk.test.ts):
//   node_modules/.bin/tsc app/lib/odaCatalog.test.ts --outDir /tmp/oc --module commonjs \
//     --target es2019 --moduleResolution node --esModuleInterop --skipLibCheck \
//   && node /tmp/oc/app/lib/odaCatalog.test.js
// These lock the honesty rules: badges are DERIVED from the backend flags and never
// fabricate execution support or contract availability.
import { filterComponents, componentBadges, canRunExecution, CatalogComponent } from "./odaCatalog";

let passed = 0;
let failed = 0;
function ok(cond: boolean, name: string) {
  if (cond) { passed++; } else { failed++; console.error("FAIL  " + name); }
}
function eq(a: unknown, b: unknown, name: string) { ok(JSON.stringify(a) === JSON.stringify(b), name + `  (got ${JSON.stringify(a)})`); }

const tmfc043: CatalogComponent = {
  code: "TMFC043", short: "FaultManagement", name: "Fault Management", block: "Production",
  supported_execution: true, contract_available: true, specification_available: true,
};
const tmfc001: CatalogComponent = {
  code: "TMFC001", short: "ProductCatalogManagement", name: "Product Catalog Management", block: "CoreCommerce",
  supported_execution: false, contract_available: false, specification_available: true,
};
const all = [tmfc001, tmfc043];

// 1. Search — by id, name fragment, block, short name; case-insensitive; empty/whitespace = all.
eq(filterComponents(all, "TMFC043").map((c) => c.code), ["TMFC043"], "search by exact id");
eq(filterComponents(all, "tmfc043").map((c) => c.code), ["TMFC043"], "search is case-insensitive");
eq(filterComponents(all, "fault").map((c) => c.code), ["TMFC043"], "search by name fragment 'fault'");
eq(filterComponents(all, "catalog").map((c) => c.code), ["TMFC001"], "search by name word 'catalog'");
eq(filterComponents(all, "corecommerce").map((c) => c.code), ["TMFC001"], "search by functional block");
eq(filterComponents(all, "faultmanagement").map((c) => c.code), ["TMFC043"], "search by short name");
eq(filterComponents(all, "").map((c) => c.code), ["TMFC001", "TMFC043"], "empty query returns all");
eq(filterComponents(all, "   ").map((c) => c.code), ["TMFC001", "TMFC043"], "whitespace query returns all");
eq(filterComponents(all, "zzz").map((c) => c.code), [], "no match returns empty");

// 2. Badges for the execution-ready component (TMFC043) — three positive badges, no "Coming Soon".
const b43 = componentBadges(tmfc043).map((b) => b.label);
ok(b43.includes("Execution Ready"), "TMFC043 shows Execution Ready");
ok(b43.includes("Contract Available"), "TMFC043 shows Contract Available");
ok(b43.includes("Specification Available"), "TMFC043 shows Specification Available");
ok(!b43.includes("Execution Coming Soon"), "TMFC043 does NOT show Execution Coming Soon");
ok(componentBadges(tmfc043)[0].tone === "green", "TMFC043 leads with the green Execution Ready badge");

// 3. Badges for a non-executable component — NEVER fabricates execution/contract availability.
const b01 = componentBadges(tmfc001).map((b) => b.label);
ok(!b01.includes("Execution Ready"), "non-supported component NEVER shows Execution Ready");
ok(!b01.includes("Contract Available"), "no-contract component NEVER shows Contract Available");
ok(b01.includes("Specification Available"), "spec-available component shows Specification Available");
ok(b01.includes("Execution Coming Soon"), "non-supported component honestly shows Execution Coming Soon");

// 4. A component with no spec + no contract shows only "Execution Coming Soon" (never invented positives).
const bare: CatalogComponent = { code: "TMFC999", short: "X", name: "X", block: "Common",
  supported_execution: false, contract_available: false, specification_available: false };
eq(componentBadges(bare).map((b) => b.label), ["Execution Coming Soon"], "bare component: only Execution Coming Soon");

// 5. canRunExecution strictly mirrors the backend flag (and is null-safe).
ok(canRunExecution(tmfc043) === true, "canRunExecution true only for supported component");
ok(canRunExecution(tmfc001) === false, "canRunExecution false for non-supported component");
ok(canRunExecution(null) === false, "canRunExecution false for null");

console.log(`\nodaCatalog.test: ${passed} passed, ${failed} failed`);
if (failed > 0) process.exit(1);
