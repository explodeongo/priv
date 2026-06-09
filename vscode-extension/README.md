# SynaptDI — VS Code Extension

Ask TM Forum / domain questions and get **cited answers** in a VS Code sidebar, without leaving your editor. It talks to your running SynaptDI backend.

## Features
- **Sidebar panel** ("Ask SynaptDI" in the activity bar) — type a question, get a grounded answer with source chips (GitHub links).
- **Command** — `SynaptDI: Ask a question` (⇧⌘P) opens a quick input and shows the answer in the panel.
- **Configurable** — point it at any SynaptDI backend and choose the search scope.

## Settings
| Setting | Default | Description |
|---|---|---|
| `synaptdi.apiUrl` | `http://localhost:8000` | Base URL of the SynaptDI backend |
| `synaptdi.scope` | `all` | `all` · `kb` (knowledge base only) · `docs` (your uploads only) |

## Develop / run locally
```bash
cd vscode-extension
npm install
npm run compile          # builds out/extension.js
# then press F5 in VS Code to launch an Extension Development Host
```
Make sure the SynaptDI backend is running (`./start.sh` / `start.bat`) so the panel can reach `http://localhost:8000`.

## Package (optional)
```bash
npm install -g @vscode/vsce
vsce package             # produces synaptdi-0.1.0.vsix → Install from VSIX…
```
