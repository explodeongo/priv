# SynaptDI — demo runbook

A 5-minute, low-risk demo of the whole platform. The compliance features are **deterministic and need no AI**, so the core demo runs without Ollama — fast, reproducible, and zero crash risk.

## Start the backend with no model loaded
Compliance / profile / scaffold / X-ray need no LLM, so start lean:
```bash
cd backend && source venv/bin/activate
WARM_MODELS=0 uvicorn main:app --port 8000
```
*(Only the chat demo, #7, needs `ollama serve`.)*

---

## 1 · Trust — it's validated, not guessing  *(30s, no backend needed)*
```bash
cd backend && source venv/bin/activate
python validate_conformance.py        # → 169 official TM Forum specs, avg 99.9/100
```
The opener: our compliance engine agrees with TM Forum's *own* published specs, deterministically.

## 2 · VS Code — the headline  *(install `vscode-extension/synaptdi-0.15.0.vsix`)*
1. Open `examples/1-single-api-check/product-ordering.broken.yaml`.
2. A live **`0/100`** score pill and a **`vs TMF622`** coverage pill appear in the SynaptDI panel.
3. Click **Auto-fix** → jumps to **100/100**.
4. Click **Scaffold** → coverage leaps (e.g. ~27% → ~95%) by pulling the missing operations + fields from the canonical spec, as a reviewable diff.
5. Open the `examples/2-portfolio-xray` folder → click the **dashboard (X-ray)** button → a board-ready portfolio report. Click any row to expand the full gap list.

## 3 · Web app — for a browser audience
```bash
cd frontend && npm run build && npm start     # steadier than `npm run dev`
```
→ `http://localhost:3000` → **Conformance** tab → drop a spec → score + profile + Auto-fix. **ODA Map** tab → browse the 35 components → **Validate a component** with `examples/3-oda-component/`. Switch to **Portfolio X-ray** → drop the `examples/2-portfolio-xray` files → click rows to expand the full gaps. Download the `.md` report.

## 4 · CI gate — blocks bad code
```bash
python backend/synaptdi_check.py examples/1-single-api-check/product-ordering.broken.yaml --min 90
# exits 1 → this is what fails a pull request
```
Then show `action.yml` + `.github/workflows/tmf-conformance.yml` — the live GitHub check teams drop into their repos.

## 5 · Python SDK — consumed by external systems
```bash
pip install ./sdk
python -c "from synaptdi import SynaptDI; print(SynaptDI().check('examples/1-single-api-check/product-ordering.broken.yaml')['score'])"
```

## 6 · MCP — AI agents query it natively
Add the config from `mcp-server/README.md` to Claude Desktop / Cursor, then ask the agent:
> "Check this OpenAPI file against TM Forum" · "What's missing for this to be a valid TMF641 Service Order?"

It calls SynaptDI's tools directly.

## 7 · Chat (RAG) — *needs Ollama*
```bash
ollama serve
```
In the web app's **Chat** tab (use **Fast** mode to stay light), ask:
> "What mandatory fields does a Product Order have in TMF622?"

→ a cited answer grounded in the actual spec files.

---

## Recommended flow for a leadership demo
**1 → 2 → 4** lands the entire story in ~5 minutes, deterministically, with no Ollama and no crash risk. Add **3** for the browser, **6** for the "agents use it natively" wow. Keep **7** (chat) for last, only if the machine has headroom.
