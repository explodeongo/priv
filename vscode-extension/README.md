# SynaptDI — VS Code Extension

Ask TM Forum / domain questions and get **cited, streaming answers** in a VS Code sidebar — and use your own code as context — without leaving the editor. It talks to your running SynaptDI backend.

## Features
- **Streaming chat panel** ("Ask SynaptDI" in the activity bar) — answers stream in token-by-token, with full Markdown: headings, tables, bullets, and syntax-styled code blocks.
- **Conversation thread** — your questions and answers stay in a scrollable thread (with short follow-up memory); they persist when you hide/show the panel. **New chat** clears it (title-bar `+`).
- **Code blocks → editor** — every generated code block has **Copy** and **Insert** buttons; *Insert* drops it at your cursor in the active file.
- **Right-click your code** → **SynaptDI**:
  - **Explain Selected Code** — what it does, plus any TM Forum / ODA / MEF / eTOM / SID concepts involved.
  - **Validate Against TM Forum Spec** — checks naming, schemas, methods, status codes, pagination, and error format against the relevant TMF Open API.
  - **Generate API Client** — produces a TMF-compliant client/snippet from the selection.
  - (No selection? It uses the whole file.)
- **Scope switcher** in the panel header — Everything · Knowledge base · My documents.
- **Cited sources** — clickable source chips under each answer (GitHub/spec links; your uploads tagged "yours").
- **Stop** — the Ask button becomes **Stop** mid-stream.
- **Command palette** — `SynaptDI: Ask a question`, plus the three code actions and `New Chat`.

## Settings
| Setting | Default | Description |
|---|---|---|
| `synaptdi.apiUrl` | `http://localhost:8000` | Base URL of the SynaptDI backend |
| `synaptdi.scope` | `all` | Default scope: `all` · `kb` (knowledge base only) · `docs` (your uploads only) |

> The panel must be able to reach the backend, so make sure SynaptDI is running (`./start.sh` / `start.bat`).

## Install (no terminal needed)
1. In VS Code: **⇧⌘P → "Extensions: Install from VSIX…"**
2. Pick `synaptdi-0.2.0.vsix` (in this folder).
3. Reload if prompted → a **SynaptDI** icon appears in the left activity bar.

## Develop / run locally
```bash
cd vscode-extension
npm install
npm run compile          # builds out/extension.js
# then open THIS folder in VS Code and press F5 → Extension Development Host
```

## Package
```bash
npm install -g @vscode/vsce
vsce package             # produces synaptdi-0.2.0.vsix → Install from VSIX…
```
