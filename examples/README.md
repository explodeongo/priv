# SynaptDI examples — one folder per use case

Ready-made files to exercise every SynaptDI capability. Each folder is a scenario; grab the file, drop it into the surface you're using (web app, VS Code, CLI, SDK, or an AI agent via MCP), and you'll see a meaningful result immediately.

> Web app → `http://localhost:3000` · backend on `:8000` (compliance features need **no Ollama**).

---

## 1 · Single API check — `1-single-api-check/`
*Score one OpenAPI spec against TM Forum, fix it, complete it.*

| File | What it demonstrates |
|---|---|
| `product-ordering.broken.yaml` | The **"before"**: scores **0/100** (8 fixable issues), detected as **TMF622 at 27% coverage** |
| `product-ordering.compliant.yaml` | The **"after"**: **100/100** — what Auto-fix produces |

- **Web:** Conformance → *Single spec* → drop the broken file → watch score, coverage, **Auto-fix**, **Scaffold**.
- **VS Code:** open the broken file → live score pill + `vs TMF622` pill → Auto-fix (wand) → Scaffold (diff icon).
- **CLI:** `cd backend && python synaptdi_check.py ../examples/1-single-api-check/product-ordering.broken.yaml --min 90` *(exits 1 — this is what blocks a PR)*
- **SDK:** `SynaptDI().check("examples/1-single-api-check/product-ordering.broken.yaml")["score"]`
- **Claude/Cursor (MCP):** *“Check this spec against TM Forum: examples/1-single-api-check/product-ordering.broken.yaml”*

## 2 · Portfolio X-ray — `2-portfolio-xray/`
*Audit a whole API estate at once — the pre-sales / architecture-review weapon.*

Three partial "homegrown" APIs with a realistic spread:
`service-ordering.yaml` (**16%** of TMF641) · `trouble-ticket.yaml` (**22%** of TMF621) · `customer.yaml` (**72%** of TMF629).

- **Web:** Conformance → *Portfolio X-ray* → select all three files → summary cards + worst-first table (click rows for full gaps) → **Download report (.md)**.
- **VS Code:** open this folder → dashboard button in the SynaptDI panel → board-ready report.
- **CLI:** `cd backend && python xray.py ../examples/2-portfolio-xray` *(writes `synaptdi-xray.md`)*

## 3 · ODA Component check — `3-oda-component/`
*Validate at the level TM Forum certifies: the ODA Component.*

| File | What it demonstrates |
|---|---|
| `product-inventory.component.yaml` | Clean pass — exposes **TMF637** (core) + **TMF669** (security), avg **100/100**, *ODA-conformant* |
| `party-management.component.yaml` | Multi-segment component (core + security, 3 exposed APIs) — all resolve and score |
| `acme-custom.component.yaml` | The realistic **mixed** case: one standard TMF API (scored) + one proprietary API (honestly marked *spec not found*) |

- **Web:** **ODA Map** → *Validate a component* → drop a manifest → segment-grouped report in ODA colours.
- **CLI:** `cd backend && python oda.py ../examples/3-oda-component/party-management.component.yaml`
- **SDK:** `SynaptDI().component("examples/3-oda-component/party-management.component.yaml")`
- **MCP:** *“Check this ODA component: examples/3-oda-component/acme-custom.component.yaml”*

Browse the full official component map (35 components, 6 functional blocks) on the **ODA Map** page.

## 4 · CI gate — `4-ci-gate/`
*Block non-compliant specs from ever merging.*

`github-workflow.example.yml` — copy into your repo as `.github/workflows/tmf-conformance.yml`, point `path` at your spec folder, done: every PR gets a TMF conformance check. (This repo runs the same gate on `examples/1-single-api-check/product-ordering.compliant.yaml` — see `.github/workflows/`.)

Pre-commit hook + more CI recipes: `backend/COMPLIANCE.md`.

---

**All deterministic.** Scores, coverage, fixes, scaffolds and component verdicts come from a rules + diff engine validated against **169 official TM Forum specs (avg 99.9/100)** — no LLM in the loop, identical results every run. Only the *chat* features use the local model.
