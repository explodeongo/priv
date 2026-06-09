import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext) {
  const provider = new SynaptDIViewProvider();
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("synaptdi.chat", provider)
  );
  context.subscriptions.push(
    vscode.commands.registerCommand("synaptdi.ask", async () => {
      const q = await vscode.window.showInputBox({ prompt: "Ask SynaptDI a TM Forum / domain question" });
      if (q) {
        await vscode.commands.executeCommand("synaptdi.chat.focus");
        provider.prefill(q);
      }
    })
  );
}

function cfg() {
  const c = vscode.workspace.getConfiguration("synaptdi");
  return {
    apiUrl: (c.get<string>("apiUrl") || "http://localhost:8000").replace(/\/+$/, ""),
    scope: c.get<string>("scope") || "all",
  };
}

class SynaptDIViewProvider implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;

  resolveWebviewView(view: vscode.WebviewView) {
    this.view = view;
    view.webview.options = { enableScripts: true };
    view.webview.html = this.html();
  }

  prefill(text: string) {
    this.view?.webview.postMessage({ type: "prefill", text });
  }

  private html(): string {
    const { apiUrl, scope } = cfg();
    let origin = apiUrl;
    try { origin = new URL(apiUrl).origin; } catch { /* keep as-is */ }
    const csp = [
      "default-src 'none'",
      "style-src 'unsafe-inline'",
      "script-src 'unsafe-inline'",
      `connect-src ${origin}`,
    ].join("; ");

    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta http-equiv="Content-Security-Policy" content="${csp}" />
<style>
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground); font-size: 13px; padding: 8px; }
  #ans { white-space: pre-wrap; line-height: 1.5; margin-top: 10px; }
  .src { display:inline-block; margin:3px 4px 0 0; padding:2px 8px; border:1px solid var(--vscode-panel-border);
         border-radius:10px; font-size:11px; color: var(--vscode-descriptionForeground); text-decoration:none; }
  .row { display:flex; gap:6px; }
  textarea { flex:1; resize:vertical; min-height:46px; background: var(--vscode-input-background);
             color: var(--vscode-input-foreground); border:1px solid var(--vscode-input-border); border-radius:6px; padding:6px; font-family:inherit; }
  button { background: var(--vscode-button-background); color: var(--vscode-button-foreground);
           border:none; border-radius:6px; padding:0 12px; cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
  .muted { color: var(--vscode-descriptionForeground); font-size:11px; margin-top:6px; }
  code, pre { background: var(--vscode-textCodeBlock-background); border-radius:4px; padding:1px 4px; font-family: var(--vscode-editor-font-family); }
</style>
</head>
<body>
  <div class="row">
    <textarea id="q" placeholder="Ask about TM Forum APIs, ODA, MEF, eTOM, SID..."></textarea>
    <button id="ask">Ask</button>
  </div>
  <div class="muted" id="status"></div>
  <div id="ans"></div>
  <div id="srcs"></div>
<script>
  const vscodeApi = acquireVsCodeApi();
  const API = ${JSON.stringify(apiUrl)};
  const SCOPE = ${JSON.stringify(scope)};
  const q = document.getElementById('q');
  const askBtn = document.getElementById('ask');
  const ans = document.getElementById('ans');
  const srcs = document.getElementById('srcs');
  const status = document.getElementById('status');

  async function ask() {
    const text = q.value.trim();
    if (!text) return;
    askBtn.disabled = true; status.textContent = 'Thinking…'; ans.textContent = ''; srcs.innerHTML = '';
    try {
      const res = await fetch(API + '/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: text, top_k: 8, scope: SCOPE }),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      ans.textContent = data.answer || '(no answer)';
      status.textContent = data.latency_ms ? (data.latency_ms / 1000).toFixed(1) + 's' : '';
      (data.sources || []).forEach(function (s) {
        const el = document.createElement(s.url ? 'a' : 'span');
        el.className = 'src'; el.textContent = s.name;
        if (s.url) { el.href = s.url; el.target = '_blank'; }
        srcs.appendChild(el);
      });
    } catch (e) {
      status.textContent = '';
      ans.textContent = 'Could not reach SynaptDI at ' + API + ' — is the backend running? (' + e + ')';
    } finally {
      askBtn.disabled = false;
    }
  }

  askBtn.addEventListener('click', ask);
  q.addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } });
  window.addEventListener('message', function (ev) {
    if (ev.data && ev.data.type === 'prefill') { q.value = ev.data.text; ask(); }
  });
</script>
</body>
</html>`;
  }
}

export function deactivate() {}
