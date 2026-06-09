import * as vscode from "vscode";

// ── Activation ──────────────────────────────────────────────────────────────
export function activate(context: vscode.ExtensionContext) {
  const provider = new SynaptDIViewProvider(context);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("synaptdi.chat", provider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );

  // Re-render the panel when apiUrl / scope config changes.
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("synaptdi")) provider.reload();
    })
  );

  const reveal = async () => vscode.commands.executeCommand("synaptdi.chat.focus");

  // Palette: free-form question.
  context.subscriptions.push(
    vscode.commands.registerCommand("synaptdi.ask", async () => {
      const q = await vscode.window.showInputBox({
        prompt: "Ask SynaptDI a TM Forum / domain question",
        placeHolder: "e.g. How does TMF641 Service Ordering handle state transitions?",
      });
      if (q && q.trim()) { await reveal(); provider.ask(q.trim()); }
    })
  );

  // Editor context actions — use the selection (or whole file) as context.
  const withCode = (build: (code: string, lang: string) => string) => async () => {
    const ctx = getCodeContext();
    if (!ctx) { vscode.window.showWarningMessage("SynaptDI: open a file and select some code first."); return; }
    await reveal();
    provider.ask(build(ctx.code, ctx.lang));
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("synaptdi.explain", withCode((code, lang) =>
      `Explain what the following ${lang} code does, step by step. If it relates to any TM Forum / ODA / MEF / eTOM / SID concepts or APIs, call those out specifically.\n\n\`\`\`${lang}\n${code}\n\`\`\``
    )),
    vscode.commands.registerCommand("synaptdi.validate", withCode((code, lang) =>
      `Review the following ${lang} code against the relevant TM Forum Open API specification. Check resource and field naming, schema shape, HTTP methods, status codes, pagination, filtering, and error format. List any deviations and the correct TMF-compliant approach, citing the specific TMF API where you can.\n\n\`\`\`${lang}\n${code}\n\`\`\``
    )),
    vscode.commands.registerCommand("synaptdi.generateClient", withCode((code, lang) =>
      `Based on the context below, generate a clean, typed client/snippet that calls the relevant TM Forum Open API correctly — proper endpoints, request/response models, pagination and error handling. Prefer ${lang}. Return the code in a single fenced block.\n\n\`\`\`${lang}\n${code}\n\`\`\``
    )),
    vscode.commands.registerCommand("synaptdi.newChat", async () => { await reveal(); provider.newChat(); })
  );
}

export function deactivate() {}

// ── Helpers ─────────────────────────────────────────────────────────────────
function cfg() {
  const c = vscode.workspace.getConfiguration("synaptdi");
  return {
    apiUrl: (c.get<string>("apiUrl") || "http://localhost:8000").replace(/\/+$/, ""),
    scope: c.get<string>("scope") || "all",
  };
}

const MAX_CODE = 6000;
function getCodeContext(): { code: string; lang: string } | undefined {
  const ed = vscode.window.activeTextEditor;
  if (!ed) return undefined;
  const sel = ed.selection;
  let code = sel && !sel.isEmpty ? ed.document.getText(sel) : ed.document.getText();
  if (!code.trim()) return undefined;
  if (code.length > MAX_CODE) code = code.slice(0, MAX_CODE) + "\n/* …truncated… */";
  return { code, lang: ed.document.languageId || "" };
}

// ── Webview provider ────────────────────────────────────────────────────────
class SynaptDIViewProvider implements vscode.WebviewViewProvider {
  private view?: vscode.WebviewView;
  private ready = false;
  private pending?: string;

  constructor(private readonly context: vscode.ExtensionContext) {}

  resolveWebviewView(view: vscode.WebviewView) {
    this.view = view;
    this.ready = false;
    view.webview.options = { enableScripts: true };
    view.webview.html = this.html();

    view.webview.onDidReceiveMessage(async (msg) => {
      if (!msg || typeof msg.type !== "string") return;
      if (msg.type === "ready") { this.ready = true; this.flush(); return; }
      if (msg.type === "copy") {
        await vscode.env.clipboard.writeText(String(msg.text ?? ""));
        vscode.window.setStatusBarMessage("SynaptDI: copied to clipboard", 1500);
        return;
      }
      if (msg.type === "insert") {
        const ed = vscode.window.activeTextEditor || vscode.window.visibleTextEditors[0];
        if (!ed) { vscode.window.showWarningMessage("SynaptDI: open a file to insert the code into."); return; }
        const code = String(msg.code ?? "");
        await ed.edit((b) => b.replace(ed.selection, code));
        vscode.window.showTextDocument(ed.document, ed.viewColumn);
        return;
      }
    });
  }

  reload() { if (this.view) { this.ready = false; this.view.webview.html = this.html(); } }
  newChat() { this.view?.webview.postMessage({ type: "clear" }); }

  ask(question: string) {
    this.pending = question;
    if (this.view) { this.view.show?.(true); this.flush(); }
  }

  private flush() {
    if (this.ready && this.pending && this.view) {
      this.view.webview.postMessage({ type: "ask", question: this.pending });
      this.pending = undefined;
    }
  }

  private html(): string {
    const { apiUrl, scope } = cfg();
    return renderWebviewHtml(apiUrl, scope);
  }
}

// Exported (pure, no vscode deps) so the shipped webview script can be parse-checked in CI/Node.
export function renderWebviewHtml(apiUrl: string, scope: string): string {
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
  :root { --gap: 8px; }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body { margin:0; display:flex; flex-direction:column; font-family: var(--vscode-font-family);
         color: var(--vscode-foreground); font-size: 13px; }
  header { display:flex; align-items:center; gap:6px; padding:6px 8px; border-bottom:1px solid var(--vscode-panel-border); }
  header select { background: var(--vscode-dropdown-background); color: var(--vscode-dropdown-foreground);
                  border:1px solid var(--vscode-dropdown-border); border-radius:5px; padding:2px 4px; font-size:11px; }
  header .spacer { flex:1; }
  .ghost { background:transparent; color: var(--vscode-descriptionForeground); border:1px solid var(--vscode-panel-border);
           border-radius:5px; padding:2px 8px; font-size:11px; cursor:pointer; }
  .ghost:hover { color: var(--vscode-foreground); }
  #thread { flex:1; overflow-y:auto; padding:10px 8px; }
  .msg { margin-bottom:14px; }
  .role { font-size:10px; text-transform:uppercase; letter-spacing:.06em; color: var(--vscode-descriptionForeground); margin-bottom:3px; }
  .msg.user .body { background: var(--vscode-textBlockQuote-background); border-left:2px solid var(--vscode-focusBorder);
                    padding:6px 8px; border-radius:4px; }
  .body { line-height:1.5; word-wrap:break-word; overflow-wrap:anywhere; }
  .body p { margin:.25em 0; }
  .body p.h { font-weight:600; margin:.7em 0 .25em; color: var(--vscode-foreground); }
  .li { display:flex; gap:6px; margin:2px 0 2px 2px; }
  .li2 { display:flex; gap:6px; margin:2px 0 2px 16px; }
  .li .b { color: var(--vscode-textLink-foreground); } .li2 .b2 { color: var(--vscode-descriptionForeground); }
  .sp { height:6px; }
  code.inl { background: var(--vscode-textCodeBlock-background); border-radius:4px; padding:1px 5px;
             font-family: var(--vscode-editor-font-family); font-size:.92em; }
  table { border-collapse:collapse; margin:.4em 0; font-size:12px; display:block; overflow-x:auto; }
  th, td { border:1px solid var(--vscode-panel-border); padding:3px 8px; text-align:left; vertical-align:top; }
  th { background: var(--vscode-editorWidget-background); font-weight:600; }
  .code { margin:.5em 0; border:1px solid var(--vscode-panel-border); border-radius:6px; overflow:hidden; }
  .cbar { display:flex; align-items:center; gap:6px; padding:3px 8px; background: var(--vscode-editorWidget-background);
          border-bottom:1px solid var(--vscode-panel-border); }
  .cbar .lang { font-size:10px; text-transform:uppercase; letter-spacing:.05em; color: var(--vscode-descriptionForeground); }
  .cbar .cbtns { margin-left:auto; display:flex; gap:4px; }
  .mini { background:transparent; color: var(--vscode-descriptionForeground); border:1px solid var(--vscode-panel-border);
          border-radius:4px; padding:1px 7px; font-size:10px; cursor:pointer; }
  .mini:hover { color: var(--vscode-foreground); background: var(--vscode-toolbar-hoverBackground); }
  .code pre { margin:0; padding:8px 10px; overflow-x:auto; }
  .code code { font-family: var(--vscode-editor-font-family); font-size:12px; line-height:1.45; white-space:pre; }
  .srcs { margin-top:7px; }
  .src { display:inline-block; margin:3px 4px 0 0; padding:1px 8px; border:1px solid var(--vscode-panel-border);
         border-radius:10px; font-size:10px; color: var(--vscode-descriptionForeground); text-decoration:none; }
  .src:hover { color: var(--vscode-textLink-foreground); }
  .src .tag { color: var(--vscode-textLink-foreground); }
  .meta { font-size:10px; color: var(--vscode-descriptionForeground); margin-top:5px; }
  .err .body { color: var(--vscode-errorForeground); }
  .empty { color: var(--vscode-descriptionForeground); text-align:center; margin-top:30px; line-height:1.6; }
  .empty .k { font-size:11px; }
  .dots::after { content:'▍'; animation: blink 1s steps(2) infinite; }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
  footer { border-top:1px solid var(--vscode-panel-border); padding:8px; }
  .composer { display:flex; gap:6px; }
  textarea { flex:1; resize:none; min-height:38px; max-height:140px; background: var(--vscode-input-background);
             color: var(--vscode-input-foreground); border:1px solid var(--vscode-input-border); border-radius:6px;
             padding:7px 8px; font-family:inherit; font-size:13px; }
  textarea:focus { outline:1px solid var(--vscode-focusBorder); }
  .send { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border:none;
          border-radius:6px; padding:0 14px; cursor:pointer; font-size:13px; }
  .send:hover { background: var(--vscode-button-hoverBackground); }
  .send.stop { background: var(--vscode-inputValidation-errorBackground, #5a1d1d); }
</style>
</head>
<body>
  <header>
    <span class="lang" style="font-size:10px;text-transform:uppercase;letter-spacing:.05em;opacity:.8;">Scope</span>
    <select id="scope" title="Search scope">
      <option value="all">Everything</option>
      <option value="kb">Knowledge base</option>
      <option value="docs">My documents</option>
    </select>
    <span class="spacer"></span>
    <button class="ghost" id="newchat" title="Clear conversation">New chat</button>
  </header>

  <div id="thread"></div>

  <footer>
    <div class="composer">
      <textarea id="q" placeholder="Ask about TM Forum APIs, ODA, MEF, eTOM, SID… (Shift+Enter for newline)"></textarea>
      <button class="send" id="send">Ask</button>
    </div>
  </footer>

<script>
  const vscodeApi = acquireVsCodeApi();
  const API = ${JSON.stringify(apiUrl)};
  const DEFAULT_SCOPE = ${JSON.stringify(scope)};

  const saved = vscodeApi.getState() || {};
  let messages = Array.isArray(saved.messages) ? saved.messages : [];
  let scope = saved.scope || DEFAULT_SCOPE;

  const thread = document.getElementById('thread');
  const q = document.getElementById('q');
  const send = document.getElementById('send');
  const scopeSel = document.getElementById('scope');
  scopeSel.value = scope;

  let controller = null;     // AbortController for the active stream
  let curBody = null;        // DOM node of the streaming assistant body
  const persist = () => vscodeApi.setState({ messages, scope });

  // ── Markdown → HTML (mirrors the web app renderer) ──
  function esc(s){ return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  function inl(t){
    return String(t).split(/(\`[^\`]+\`|\\*\\*[^*]+\\*\\*)/g).map(p => {
      if (p.startsWith('\`') && p.endsWith('\`')) return '<code class="inl">' + esc(p.slice(1,-1)) + '</code>';
      if (p.startsWith('**') && p.endsWith('**')) return '<strong>' + esc(p.slice(2,-2)) + '</strong>';
      return esc(p);
    }).join('');
  }
  function md(text){
    const lines = String(text).split('\\n');
    let html = '', i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (line.trim().startsWith('\`\`\`')) {
        const lang = line.trim().slice(3).trim();
        const code = []; i++;
        while (i < lines.length && !lines[i].trim().startsWith('\`\`\`')) { code.push(lines[i]); i++; }
        i++;
        const raw = code.join('\\n');
        html += '<div class="code"><div class="cbar"><span class="lang">' + esc(lang || 'code') + '</span>'
             +  '<span class="cbtns"><button class="mini" data-act="copy">Copy</button>'
             +  '<button class="mini" data-act="insert">Insert</button></span></div>'
             +  '<pre><code>' + esc(raw) + '</code></pre></div>';
        continue;
      }
      if (line.includes('|') && i+1 < lines.length && /^\\s*\\|?[\\s:|-]+\\|?\\s*$/.test(lines[i+1]) && lines[i+1].includes('-')) {
        const row = l => l.trim().replace(/^\\||\\|$/g,'').split('|').map(c => c.trim());
        const head = row(line); i += 2; const rows = [];
        while (i < lines.length && lines[i].includes('|') && lines[i].trim()) { rows.push(row(lines[i])); i++; }
        html += '<table><thead><tr>' + head.map(h => '<th>' + inl(h) + '</th>').join('') + '</tr></thead><tbody>'
             +  rows.map(r => '<tr>' + r.map(c => '<td>' + inl(c) + '</td>').join('') + '</tr>').join('') + '</tbody></table>';
        continue;
      }
      if (!line.trim()) { html += '<div class="sp"></div>'; i++; continue; }
      if (line.startsWith('## ') || line.startsWith('### ')) html += '<p class="h">' + inl(line.replace(/^#{2,3}\\s/,'')) + '</p>';
      else if (/^[\\*\\-\\+]\\s/.test(line)) html += '<div class="li"><span class="b">•</span><span>' + inl(line.slice(2)) + '</span></div>';
      else if (/^\\s{2,}[\\+\\-\\*]\\s/.test(line)) html += '<div class="li2"><span class="b2">◦</span><span>' + inl(line.replace(/^\\s+[\\+\\-\\*]\\s/,'')) + '</span></div>';
      else html += '<p>' + inl(line) + '</p>';
      i++;
    }
    return html;
  }

  function srcChips(sources){
    if (!sources || !sources.length) return '';
    return '<div class="srcs">' + sources.map(s => {
      const tag = s.upload ? ' <span class="tag">· yours</span>' : '';
      const inner = esc(s.name || s.file || 'source') + tag;
      return s.url ? '<a class="src" href="' + esc(s.url) + '" target="_blank">' + inner + '</a>'
                   : '<span class="src">' + inner + '</span>';
    }).join('') + '</div>';
  }

  function render(){
    if (!messages.length) {
      thread.innerHTML = '<div class="empty">Ask anything about your TM Forum knowledge base.<br>'
        + '<span class="k">Tip: select code in any file, right-click → <b>SynaptDI</b> → Explain / Validate / Generate.</span></div>';
      curBody = null; return;
    }
    thread.innerHTML = messages.map(m => {
      const cls = 'msg ' + (m.role === 'user' ? 'user' : 'bot') + (m.error ? ' err' : '');
      const role = m.role === 'user' ? 'You' : 'SynaptDI';
      const bodyHtml = m.content ? md(m.content) : '<span class="dots"></span>';
      const meta = (m.role === 'assistant' && m.latency_ms) ? '<div class="meta">' + (m.latency_ms/1000).toFixed(1) + 's</div>' : '';
      return '<div class="' + cls + '"><div class="role">' + role + '</div>'
           + '<div class="body">' + bodyHtml + '</div>'
           + (m.role === 'assistant' ? srcChips(m.sources) : '') + meta + '</div>';
    }).join('');
    curBody = thread.querySelector('.msg:last-child .body');
    scrollDown();
  }
  function scrollDown(){ thread.scrollTop = thread.scrollHeight; }
  function setSending(on){ send.textContent = on ? 'Stop' : 'Ask'; send.classList.toggle('stop', on); }

  async function run(question){
    if (controller) { controller.abort(); }   // stop any in-flight stream first
    const history = messages.filter(m => m.content && !m.error).slice(-6).map(m => ({ role: m.role, content: m.content }));
    messages.push({ role: 'user', content: question });
    messages.push({ role: 'assistant', content: '' });
    render(); persist();

    controller = new AbortController();
    const ctrl = controller;
    const timer = setTimeout(() => ctrl.abort(), 180000);
    setSending(true);
    const last = messages[messages.length - 1];
    let acc = '';

    try {
      const res = await fetch(API + '/query/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question, top_k: 8, scope, history }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw new Error('API error ' + res.status);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const parts = buf.split('\\n');
        buf = parts.pop() || '';
        for (const line of parts) {
          if (!line.trim()) continue;
          let evt; try { evt = JSON.parse(line); } catch { continue; }
          if (evt.type === 'token') { acc += evt.text; last.content = acc; if (curBody) curBody.innerHTML = md(acc); scrollDown(); }
          else if (evt.type === 'done') { last.sources = evt.sources; last.latency_ms = evt.latency_ms; }
          else if (evt.type === 'error') { acc = evt.text; last.content = acc; last.error = true; }
        }
      }
    } catch (e) {
      if (e && e.name === 'AbortError') { last.content = acc ? acc + '\\n\\n_(stopped)_' : '_(stopped)_'; }
      else { last.content = 'Could not reach SynaptDI at ' + API + ' — is the backend running on port 8000? (' + (e && e.message || e) + ')'; last.error = true; }
    } finally {
      clearTimeout(timer);
      controller = null;
      setSending(false);
      render(); persist();
      q.focus();
    }
  }

  function submit(){
    if (controller) { controller.abort(); return; }   // Stop
    const text = q.value.trim();
    if (!text) return;
    q.value = ''; autosize();
    run(text);
  }

  // ── Events ──
  send.addEventListener('click', submit);
  q.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });
  function autosize(){ q.style.height = 'auto'; q.style.height = Math.min(q.scrollHeight, 140) + 'px'; }
  q.addEventListener('input', autosize);
  scopeSel.addEventListener('change', () => { scope = scopeSel.value; persist(); });
  document.getElementById('newchat').addEventListener('click', () => {
    if (controller) controller.abort();
    messages = []; render(); persist();
  });

  // Code-block Copy / Insert (event delegation survives re-renders).
  thread.addEventListener('click', e => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const codeEl = btn.closest('.code')?.querySelector('pre code');
    if (!codeEl) return;
    const code = codeEl.textContent || '';
    if (btn.dataset.act === 'copy') { vscodeApi.postMessage({ type: 'copy', text: code }); btn.textContent = 'Copied'; setTimeout(() => btn.textContent = 'Copy', 1200); }
    else if (btn.dataset.act === 'insert') { vscodeApi.postMessage({ type: 'insert', code }); }
  });

  // Messages from the extension host.
  window.addEventListener('message', ev => {
    const m = ev.data;
    if (!m) return;
    if (m.type === 'ask') run(m.question);
    else if (m.type === 'clear') { if (controller) controller.abort(); messages = []; render(); persist(); }
  });

  render();
  vscodeApi.postMessage({ type: 'ready' });
</script>
</body>
</html>`;
}
