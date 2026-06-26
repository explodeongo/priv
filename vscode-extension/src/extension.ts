import * as vscode from "vscode";
import * as http from "http";
import * as https from "https";

// Tiny POST-JSON over node http(s) — works on every VS Code version (no fetch dependency).
function postJson(url: string, body: unknown): Promise<{ ok: boolean; status: number; json: any; text: string }> {
  return new Promise((resolve, reject) => {
    let u: URL;
    try { u = new URL(url); } catch (e) { reject(e); return; }
    const lib = u.protocol === "https:" ? https : http;
    const data = Buffer.from(JSON.stringify(body));
    const req = lib.request(u, { method: "POST", headers: { "Content-Type": "application/json", "Content-Length": data.length } }, (res) => {
      let buf = "";
      res.on("data", (c) => (buf += c));
      res.on("end", () => {
        let json: any = null; try { json = JSON.parse(buf); } catch { /* non-JSON */ }
        const code = res.statusCode || 0;
        resolve({ ok: code >= 200 && code < 300, status: code, json, text: buf });
      });
    });
    req.on("error", reject);
    req.setTimeout(15000, () => req.destroy(new Error("timeout")));
    req.write(data); req.end();
  });
}

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

  // ── Apply-as-diff + multi-file context (chat → editor) ──
  const proposed = new Map<string, string>();
  const DIFF_SCHEME = "synaptdi-proposed";
  context.subscriptions.push(
    vscode.workspace.registerTextDocumentContentProvider(DIFF_SCHEME, {
      provideTextDocumentContent: (uri) => proposed.get(uri.toString()) || "",
    })
  );
  const applyCode = async (code: string) => {
    if (!code.trim()) return;
    const ed = vscode.window.activeTextEditor
      || vscode.window.visibleTextEditors.find((e) => e.document.uri.scheme === "file")
      || vscode.window.visibleTextEditors[0];
    if (!ed) { vscode.window.showWarningMessage("SynaptDI: open the file you want to apply this code to first."); return; }
    const doc = ed.document;
    const sel = ed.selection;
    const whole = !sel || sel.isEmpty;
    const range = whole ? new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length)) : new vscode.Range(sel.start, sel.end);
    const text = doc.getText();
    const next = text.slice(0, doc.offsetAt(range.start)) + code + text.slice(doc.offsetAt(range.end));
    const name = doc.fileName.split(/[\\/]/).pop() || "file";
    const uri = vscode.Uri.from({ scheme: DIFF_SCHEME, path: "/" + name, query: String(Date.now()) });
    proposed.set(uri.toString(), next);
    await vscode.commands.executeCommand("vscode.diff", doc.uri, uri, "SynaptDI: " + name + " — review proposed changes");
    const pick = await vscode.window.showInformationMessage(
      "Apply SynaptDI's proposed changes to " + name + (whole ? "" : " (selection)") + "?", "Apply", "Cancel");
    proposed.delete(uri.toString());
    if (pick !== "Apply") return;
    const edit = new vscode.WorkspaceEdit();
    edit.replace(doc.uri, range, code);
    await vscode.workspace.applyEdit(edit);
    vscode.window.showInformationMessage("SynaptDI: applied changes to " + name + ".");
  };
  context.subscriptions.push(
    vscode.commands.registerCommand("synaptdi._applyCode", (code: string) => applyCode(code)),
    vscode.commands.registerCommand("synaptdi._pickFiles", async () => {
      const picks = await vscode.window.showOpenDialog({
        canSelectMany: true, canSelectFolders: false, openLabel: "Add to chat context",
        filters: { "Specs & code": ["yaml", "yml", "json", "ts", "js", "py", "java", "go"], "All files": ["*"] },
      });
      if (!picks || !picks.length) return;
      const files: any[] = [];
      for (const uri of picks.slice(0, 4)) {
        try {
          const doc = await vscode.workspace.openTextDocument(uri);
          let code = doc.getText();
          if (code.length > 6000) code = code.slice(0, 6000) + "\n/* …truncated… */";
          files.push({ file: uri.fsPath.split(/[\\/]/).pop() || "file", lang: doc.languageId || "", code });
        } catch {}
      }
      if (files.length) provider.postExtraFiles(files);
    })
  );

  // ── Live compliance diagnostics (deterministic TMF630 — no model, instant) ──
  const diagnostics = vscode.languages.createDiagnosticCollection("synaptdi");
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  status.command = "synaptdi.checkCompliance";
  context.subscriptions.push(diagnostics, status);

  const runCompliance = async (doc: vscode.TextDocument, silent = false) => {
    if (!isSpecDoc(doc)) {
      if (!silent) vscode.window.showWarningMessage("SynaptDI: open an OpenAPI / Swagger spec (JSON or YAML) to check for TM Forum compliance.");
      return;
    }
    try {
      const filename = doc.fileName.split(/[\\/]/).pop() || "";
      const res = await postJson(cfg().apiUrl + "/conformance/text", { content: doc.getText(), filename });
      if (!res.ok) {
        diagnostics.delete(doc.uri); status.hide();
        if (!silent) vscode.window.showWarningMessage("SynaptDI: " + (res.status === 400 ? "that file isn't a recognisable OpenAPI spec." : `compliance check failed (${res.status}).`));
        return;
      }
      const report = res.json;
      diagnostics.set(doc.uri, buildDiagnostics(doc, report));
      updateStatus(status, report);
      provider.pushCompliance(doc, report);
      if (!silent) {
        const s = report.summary || {};
        vscode.window.showInformationMessage(`SynaptDI · ${report.api || "spec"}: ${report.score}/100 — ${s.failed || 0} error(s), ${s.warnings || 0} warning(s). See Problems panel.`);
      }
    } catch {
      status.hide();
      if (!silent) vscode.window.showWarningMessage("SynaptDI: couldn't reach the backend at " + cfg().apiUrl + " — is it running on :8000?");
    }
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("synaptdi.checkCompliance", async () => {
      const ed = vscode.window.activeTextEditor;
      if (!ed) { vscode.window.showWarningMessage("SynaptDI: open a spec file first."); return; }
      await runCompliance(ed.document, false);
    }),
    // Internal: silent check of the active spec when the chat panel first loads.
    vscode.commands.registerCommand("synaptdi._checkActive", () => {
      const ed = vscode.window.activeTextEditor;
      if (ed && isSpecDoc(ed.document)) runCompliance(ed.document, true);
    }),
    // auto-check spec files on save + when one becomes the active editor
    vscode.workspace.onDidSaveTextDocument((doc) => { if (isSpecDoc(doc)) runCompliance(doc, true); }),
    vscode.window.onDidChangeActiveTextEditor((ed) => {
      provider.pushContext();
      if (ed && isSpecDoc(ed.document)) runCompliance(ed.document, true);
      else status.hide();
    })
  );

  // Keep the chat's "reading <file>" context fresh, and check specs live as you type.
  let ctxTimer: ReturnType<typeof setTimeout> | undefined;
  let liveTimer: ReturnType<typeof setTimeout> | undefined;
  context.subscriptions.push(
    vscode.window.onDidChangeTextEditorSelection(() => {
      if (ctxTimer) clearTimeout(ctxTimer);
      ctxTimer = setTimeout(() => provider.pushContext(), 120);
    }),
    vscode.workspace.onDidChangeTextDocument((e) => {
      const ed = vscode.window.activeTextEditor;
      if (!ed || e.document !== ed.document) return;
      if (isSpecDoc(e.document)) { if (liveTimer) clearTimeout(liveTimer); liveTimer = setTimeout(() => runCompliance(e.document, true), 700); }
    })
  );
  // ── Layer 2: deterministic auto-fix (no model — same engine fixes what it flags) ──
  const applyFix = async (uri: vscode.Uri, ids?: string[]) => {
    let doc: vscode.TextDocument;
    try { doc = await vscode.workspace.openTextDocument(uri); } catch { return; }
    try {
      const res = await postJson(cfg().apiUrl + "/conformance/fix", { content: doc.getText(), ids: ids && ids.length ? ids : undefined });
      if (!res.ok) { vscode.window.showWarningMessage("SynaptDI: auto-fix failed (" + res.status + ")."); return; }
      const out = res.json;
      if (!out || !out.content || !(out.fixed || []).length) { vscode.window.showInformationMessage("SynaptDI: nothing here can be auto-fixed."); return; }
      const edit = new vscode.WorkspaceEdit();
      const full = new vscode.Range(doc.positionAt(0), doc.positionAt(doc.getText().length));
      edit.replace(uri, full, out.content);
      await vscode.workspace.applyEdit(edit);
      await doc.save();                       // save → re-check fires automatically
      vscode.window.showInformationMessage(`SynaptDI auto-fixed: ${(out.fixed || []).join(", ")} — score now ${out.score}/100.`);
    } catch {
      vscode.window.showWarningMessage("SynaptDI: couldn't reach the backend at " + cfg().apiUrl + ".");
    }
  };

  context.subscriptions.push(
    vscode.commands.registerCommand("synaptdi.fix", (uri: vscode.Uri, ids?: string[]) => applyFix(uri, ids)),
    vscode.commands.registerCommand("synaptdi.fixAll", async () => {
      const ed = vscode.window.activeTextEditor;
      if (!ed || !isSpecDoc(ed.document)) { vscode.window.showWarningMessage("SynaptDI: open an OpenAPI spec to fix."); return; }
      await applyFix(ed.document.uri, undefined);
    }),
    vscode.languages.registerCodeActionsProvider(
      [{ language: "yaml" }, { language: "yml" as any }, { language: "json" }, { language: "jsonc" }, { pattern: "**/*.{yaml,yml,json}" }],
      new ComplianceFixProvider(),
      { providedCodeActionKinds: [vscode.CodeActionKind.QuickFix] }
    )
  );

  // ── Layer 3: scan the whole workspace for compliance ──
  const scanChannel = vscode.window.createOutputChannel("SynaptDI Compliance");
  context.subscriptions.push(scanChannel,
    vscode.commands.registerCommand("synaptdi.scanWorkspace", async () => {
      const uris = await vscode.workspace.findFiles("**/*.{yaml,yml,json}", "**/{node_modules,out,.next,dist,.git}/**", 800);
      if (!uris.length) { vscode.window.showInformationMessage("SynaptDI: no YAML/JSON files in the workspace."); return; }
      const rows: { file: string; score: number; failed: number; warnings: number }[] = [];
      let reachedBackend = true;
      await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "SynaptDI: scanning specs for TM Forum compliance…" }, async (progress) => {
        for (const uri of uris) {
          let doc: vscode.TextDocument;
          try { doc = await vscode.workspace.openTextDocument(uri); } catch { continue; }
          if (!isSpecDoc(doc)) continue;
          progress.report({ message: vscode.workspace.asRelativePath(uri) });
          try {
            const res = await postJson(cfg().apiUrl + "/conformance/text", { content: doc.getText(), filename: uri.path.split("/").pop() || "" });
            if (!res.ok) continue;
            const rep = res.json;
            diagnostics.set(uri, buildDiagnostics(doc, rep));
            rows.push({ file: vscode.workspace.asRelativePath(uri), score: rep.score, failed: rep.summary.failed, warnings: rep.summary.warnings });
          } catch { reachedBackend = false; break; }
        }
      });
      if (!reachedBackend) { vscode.window.showWarningMessage("SynaptDI: couldn't reach the backend at " + cfg().apiUrl + "."); return; }
      if (!rows.length) { vscode.window.showInformationMessage("SynaptDI: no OpenAPI/Swagger specs found to check."); return; }
      rows.sort((a, b) => a.score - b.score);
      scanChannel.clear();
      scanChannel.appendLine("TM Forum (TMF630) compliance — workspace scan");
      scanChannel.appendLine("".padEnd(60, "-"));
      for (const r of rows) scanChannel.appendLine(`  ${String(r.score).padStart(3)}/100   ${r.failed}E ${r.warnings}W   ${r.file}`);
      const below = rows.filter((r) => r.score < 90).length;
      scanChannel.appendLine("".padEnd(60, "-"));
      scanChannel.appendLine(`  ${rows.length - below}/${rows.length} specs >= 90 - lowest ${rows[0].score}/100`);
      scanChannel.show(true);
      vscode.window.showInformationMessage(`SynaptDI: scanned ${rows.length} spec(s), ${below} below 90/100 - see Problems + the SynaptDI Compliance output.`);
    })
  );

  // check whatever's already open
  const open = vscode.window.activeTextEditor;
  if (open && isSpecDoc(open.document)) runCompliance(open.document, true);
}

export function deactivate() {}

// Quick-fix actions on each SynaptDI compliance squiggle → deterministic auto-fix.
class ComplianceFixProvider implements vscode.CodeActionProvider {
  provideCodeActions(doc: vscode.TextDocument, _range: vscode.Range | vscode.Selection, context: vscode.CodeActionContext): vscode.CodeAction[] | undefined {
    const ours = context.diagnostics.filter((d) => String(d.source || "").startsWith("SynaptDI") && d.code);
    if (!ours.length) return;
    const actions: vscode.CodeAction[] = [];
    const seen = new Set<string>();
    for (const d of ours) {
      const id = String(d.code);
      if (seen.has(id)) continue;
      seen.add(id);
      const a = new vscode.CodeAction("Fix this with SynaptDI (TMF630)", vscode.CodeActionKind.QuickFix);
      a.diagnostics = [d];
      a.command = { command: "synaptdi.fix", title: "Fix", arguments: [doc.uri, [id]] };
      actions.push(a);
    }
    const ids = Array.from(seen);
    if (ids.length > 1) {
      const all = new vscode.CodeAction("Fix all TM Forum issues (SynaptDI)", vscode.CodeActionKind.QuickFix);
      all.command = { command: "synaptdi.fix", title: "Fix all", arguments: [doc.uri, ids] };
      actions.push(all);
    }
    return actions;
  }
}

// ── Compliance helpers (pure-ish, deterministic) ──────────────────────────────
function isSpecDoc(doc: vscode.TextDocument): boolean {
  const byExt = /\.(ya?ml|json)$/i.test(doc.fileName);
  const byLang = ["yaml", "yml", "json", "jsonc"].includes(doc.languageId);
  if (!byExt && !byLang) return false;
  const head = doc.getText().slice(0, 4000).toLowerCase();
  return head.includes("openapi") || head.includes("swagger") || (head.includes("paths") && head.includes("info"));
}

function locate(doc: vscode.TextDocument, token: string): vscode.Range | undefined {
  if (!token) return undefined;
  const idx = doc.getText().indexOf(token);
  if (idx < 0) return undefined;
  return new vscode.Range(doc.positionAt(idx), doc.positionAt(idx + token.length));
}

function buildDiagnostics(doc: vscode.TextDocument, report: any): vscode.Diagnostic[] {
  const sevOf: Record<string, vscode.DiagnosticSeverity> = {
    error: vscode.DiagnosticSeverity.Error,
    warning: vscode.DiagnosticSeverity.Warning,
    info: vscode.DiagnosticSeverity.Information,
  };
  const out: vscode.Diagnostic[] = [];
  for (const f of report?.findings || []) {
    if (f.status !== "fail") continue;
    const sev = sevOf[f.severity] ?? vscode.DiagnosticSeverity.Warning;
    const cite = f.ref ? `  ·  ${f.ref}` : "";
    const base = `${f.title} — ${f.detail}${cite}`;
    const examples: string[] = f.examples || [];
    if (examples.length === 0) {
      const d = new vscode.Diagnostic(new vscode.Range(0, 0, 0, 1), base, sev);
      d.source = "SynaptDI · TMF630"; d.code = f.id;
      out.push(d);
      continue;
    }
    for (const ex of examples) {
      const token = ex.includes(".") ? ex.split(".").pop() || ex : ex;   // "Schema.prop" → "prop"
      const range = locate(doc, token) ?? new vscode.Range(0, 0, 0, 1);
      const msg = ex !== token ? `${base} (${ex})` : base;
      const d = new vscode.Diagnostic(range, msg, sev);
      d.source = "SynaptDI · TMF630"; d.code = f.id;
      out.push(d);
    }
  }
  return out;
}

function updateStatus(status: vscode.StatusBarItem, report: any) {
  const score = report?.score ?? 0;
  const s = report?.summary || {};
  status.text = `$(${s.failed ? "error" : score >= 90 ? "pass" : "warning"}) TMF ${score}/100`;
  status.tooltip = `TM Forum (TMF630) compliance: ${score}/100 · ${s.failed || 0} error(s) · ${s.warnings || 0} warning(s)\nClick to re-check`;
  status.color = score >= 90 ? undefined
    : score >= 70 ? new vscode.ThemeColor("editorWarning.foreground")
    : new vscode.ThemeColor("editorError.foreground");
  status.show();
}

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
      if (msg.type === "ready") { this.ready = true; this.flush(); this.pushContext(); vscode.commands.executeCommand("synaptdi._checkActive"); return; }
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
      if (msg.type === "getContent") {
        // The webview asks for the live file when you send a question.
        const ed = vscode.window.activeTextEditor
          || vscode.window.visibleTextEditors.find((e) => e.document.uri.scheme === "file")
          || vscode.window.visibleTextEditors[0];
        let code = "", file = "", lang = "";
        if (ed) {
          const sel = ed.selection;
          code = sel && !sel.isEmpty ? ed.document.getText(sel) : ed.document.getText();
          if (code.length > 6000) code = code.slice(0, 6000) + "\n/* …truncated… */";
          file = ed.document.fileName.split(/[\\/]/).pop() || "untitled";
          lang = ed.document.languageId || "";
        }
        this.view?.webview.postMessage({ type: "content", code, file, lang });
        return;
      }
      if (msg.type === "command" && typeof msg.command === "string") {
        const allow = ["synaptdi.fixAll", "synaptdi.checkCompliance", "synaptdi.scanWorkspace"];
        if (allow.indexOf(msg.command) >= 0) vscode.commands.executeCommand(msg.command);
        return;
      }
      if (msg.type === "applyCode") { vscode.commands.executeCommand("synaptdi._applyCode", String(msg.code || "")); return; }
      if (msg.type === "pickFiles") { vscode.commands.executeCommand("synaptdi._pickFiles"); return; }
    });
  }

  reload() { if (this.view) { this.ready = false; this.view.webview.html = this.html(); } }
  newChat() { this.view?.webview.postMessage({ type: "clear" }); }

  // Tell the webview which file is open so the chat can read it automatically.
  pushContext() {
    if (!this.view || !this.ready) return;
    const ed = vscode.window.activeTextEditor
      || vscode.window.visibleTextEditors.find((e) => e.document.uri.scheme === "file")
      || vscode.window.visibleTextEditors[0];
    if (!ed) { this.view.webview.postMessage({ type: "editorContext", file: null }); return; }
    const sel = ed.selection;
    this.view.webview.postMessage({
      type: "editorContext",
      file: ed.document.fileName.split(/[\\/]/).pop() || "untitled",
      lang: ed.document.languageId || "",
      lines: ed.document.lineCount,
      hasSelection: !!(sel && !sel.isEmpty),
      isSpec: isSpecDoc(ed.document),
    });
  }

  // Push the live TMF compliance score for a spec to the webview (chat pill).
  pushCompliance(doc: vscode.TextDocument, report: any) {
    if (!this.view || !this.ready) return;
    const s = (report && report.summary) || {};
    this.view.webview.postMessage({
      type: "compliance",
      file: doc.fileName.split(/[\\/]/).pop() || "",
      score: (report && report.score) || 0,
      failed: s.failed || 0,
      warnings: s.warnings || 0,
      api: (report && report.api) || "",
      fixable: (report && report.fixable) || 0,
    });
  }

  postExtraFiles(files: any[]) { this.view?.webview.postMessage({ type: "extraFiles", files }); }

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
  .dot { width:8px; height:8px; border-radius:50%; background: var(--vscode-descriptionForeground); flex-shrink:0; }
  .dot.on { background:#3fb950; } .dot.off { background:#e5534b; }
  #mode { font-weight:600; }
  .acts { display:flex; align-items:center; gap:8px; margin-top:7px; flex-wrap:wrap; }
  .conf { font-size:10px; font-weight:600; }
  .conf.cf-hi { color:#3fb950; } .conf.cf-md { color:#d29922; } .conf.cf-lo { color: var(--vscode-descriptionForeground); }
  .instant { font-size:10px; color:#d29922; font-weight:600; }
  .tdot { display:inline-block; width:6px; height:6px; border-radius:50%; margin-right:5px; vertical-align:middle; }
  .tier-kb { background:#3fb950; } .tier-repo { background:#a371f7; } .tier-web { background:#58a6ff; } .tier-file { background:#d29922; }
  .sugs { display:flex; flex-direction:column; gap:6px; margin:12px auto 6px; max-width:340px; }
  .sug { text-align:left; background: var(--vscode-textBlockQuote-background); color: var(--vscode-foreground);
         border:1px solid var(--vscode-panel-border); border-radius:6px; padding:7px 9px; font-size:12px; cursor:pointer; }
  .sug:hover { border-color: var(--vscode-focusBorder); }
  .etitle { font-weight:600; color: var(--vscode-foreground); margin-bottom:4px; font-size:13px; }
  .histbar { padding:6px 8px; border-bottom:1px solid var(--vscode-panel-border); }
  .histq { width:100%; background: var(--vscode-input-background); color: var(--vscode-input-foreground);
           border:1px solid var(--vscode-input-border); border-radius:6px; padding:5px 8px; font-size:12px; }
  .hgroup { font-size:10px; text-transform:uppercase; letter-spacing:.06em; color: var(--vscode-descriptionForeground); padding:9px 10px 2px; font-weight:600; }
  .hitem { position:relative; padding:6px 26px 6px 10px; border-radius:6px; cursor:pointer; }
  .hitem:hover { background: var(--vscode-list-hoverBackground, rgba(255,255,255,.06)); }
  .htitle { font-size:12.5px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .hsnip { font-size:10.5px; color: var(--vscode-descriptionForeground); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:1px; }
  .hdel { position:absolute; right:5px; top:6px; background:transparent; border:none; color: var(--vscode-descriptionForeground);
          cursor:pointer; font-size:15px; line-height:1; opacity:0; padding:0 5px; }
  .hitem:hover .hdel { opacity:1; } .hdel:hover { color: var(--vscode-errorForeground); }
  .ctxbar { padding:0 8px 6px; }
  .ctxchip { display:inline-flex; align-items:center; gap:5px; max-width:100%; font-size:11px;
             background: var(--vscode-textBlockQuote-background); border:1px solid var(--vscode-panel-border);
             border-radius:6px; padding:3px 5px 3px 8px; color: var(--vscode-descriptionForeground); }
  .ctxchip.on { border-color: var(--vscode-focusBorder); color: var(--vscode-foreground); }
  .ctxchip.off { cursor:pointer; } .ctxchip.off:hover { border-color: var(--vscode-focusBorder); }
  .ctxchip b { color: var(--vscode-foreground); font-weight:600; max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .ctxchip svg { flex:0 0 auto; opacity:.85; }
  .ctxchip .x { background:transparent; border:none; color:inherit; cursor:pointer; font-size:13px; line-height:1; padding:0 1px 0 2px; opacity:.65; }
  .ctxchip .x:hover { opacity:1; color: var(--vscode-errorForeground); }
  .compill { display:inline-flex; align-items:center; gap:4px; font-size:11px; cursor:pointer;
             border:1px solid var(--vscode-panel-border); border-radius:6px; padding:3px 7px; color: var(--vscode-foreground); }
  .compill b { font-weight:700; } .compill svg, .fixbtn svg { flex:0 0 auto; }
  .fixbtn { display:inline-flex; align-items:center; gap:4px; font-size:11px; cursor:pointer; border:none; border-radius:6px; padding:3px 8px;
            background: var(--vscode-button-secondaryBackground, var(--vscode-button-background));
            color: var(--vscode-button-secondaryForeground, var(--vscode-button-foreground)); }
  .fixbtn:hover { background: var(--vscode-button-hoverBackground); }
  .addfile { font-size:11px; cursor:pointer; background:transparent; border:1px dashed var(--vscode-panel-border);
             border-radius:6px; padding:3px 8px; color: var(--vscode-descriptionForeground); }
  .addfile:hover { border-color: var(--vscode-focusBorder); color: var(--vscode-foreground); }
</style>
</head>
<body>
  <header>
    <span id="dot" class="dot" title="Backend status"></span>
    <select id="scope" title="Search scope">
      <option value="all">Everything</option>
      <option value="kb">Knowledge base</option>
      <option value="docs">My documents</option>
    </select>
    <button class="ghost" id="mode" title="Answer mode">Fast</button>
    <span class="spacer"></span>
    <button class="ghost" id="history" title="Chat history">History</button>
    <button class="ghost" id="newchat" title="Start a new chat">New chat</button>
  </header>

  <div id="thread"></div>

  <footer>
    <div class="ctxbar" id="ctxbar"></div>
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
  let conversations = Array.isArray(saved.conversations) ? saved.conversations : [];   // local saved chats
  let messages = Array.isArray(saved.messages) ? saved.messages : [];                  // current thread
  let activeId = saved.activeId || null;
  let view = 'chat';                   // 'chat' | 'history'
  let histQuery = '';
  let scope = saved.scope || DEFAULT_SCOPE;
  let mode = saved.mode || 'fast';     // default Fast — lighter on RAM
  let editorCtx = null;                // {file,lang,lines,hasSelection} pushed by the host editor
  let attach = (saved.attach !== false);   // auto-read the open file as context (default on)
  let pendingContent = null;           // resolver awaiting the host's file content
  let comp = null;                     // {file,score,failed,warnings,api,fixable} live TMF score for the open spec
  let extraFiles = [];                 // [{file,lang,code}] extra files added via "+ Add file" (not persisted)
  const FENCE = String.fromCharCode(96, 96, 96);   // triple backtick, without touching the template literal

  const thread = document.getElementById('thread');
  const q = document.getElementById('q');
  const send = document.getElementById('send');
  const scopeSel = document.getElementById('scope');
  const modeBtn = document.getElementById('mode');
  const dot = document.getElementById('dot');
  scopeSel.value = scope;

  let controller = null;     // AbortController for the active stream
  let curBody = null;        // DOM node of the streaming assistant body
  function genId(){ return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
  function syncActive(){
    if (!messages.length) return;
    if (!activeId) activeId = genId();
    var fu = null;
    for (var i = 0; i < messages.length; i++) { if (messages[i].role === 'user' && messages[i].content) { fu = messages[i].content; break; } }
    var title = (fu || 'New chat').slice(0, 60);
    var ex = null;
    for (var j = 0; j < conversations.length; j++) { if (conversations[j].id === activeId) { ex = conversations[j]; break; } }
    if (ex) { ex.messages = messages; ex.title = title; ex.updated = Date.now(); }
    else { conversations.unshift({ id: activeId, title: title, messages: messages, updated: Date.now() }); }
    if (conversations.length > 60) conversations = conversations.slice(0, 60);
  }
  const persist = function(){ syncActive(); vscodeApi.setState({ conversations: conversations, messages: messages, activeId: activeId, scope: scope, mode: mode, attach: attach }); };

  function paintMode(){
    modeBtn.textContent = mode === 'deep' ? 'Deep' : 'Fast';
    modeBtn.title = mode === 'deep'
      ? 'Deep — full 8B model (best quality, slower). Click for Fast.'
      : 'Fast — small model (quick, light on RAM). Click for Deep.';
  }
  paintMode();
  function setDot(ok){ dot.className = 'dot ' + (ok ? 'on' : 'off'); dot.title = ok ? 'Backend connected' : 'Backend unreachable (is it on :8000, and is Ollama running for chat?)'; }
  fetch(API + '/health').then(function(r){ setDot(r.ok); }).catch(function(){ setDot(false); });

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
             +  '<button class="mini" data-act="apply">Apply</button></span></div>'
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

  function tierOf(s){
    var ot = s.origin_type;
    if (ot === 'repo') return { label: 'GitHub repository', cls: 'tier-repo' };
    if (ot === 'web')  return { label: 'Web page', cls: 'tier-web' };
    if (ot === 'file') return { label: 'Internal upload', cls: 'tier-file' };
    return { label: 'Official' + (s.domain ? ' · ' + s.domain : ''), cls: 'tier-kb' };
  }
  function srcChips(sources){
    if (!sources || !sources.length) return '';
    return '<div class="srcs">' + sources.map(function(s){
      var t = tierOf(s);
      var inner = '<span class="tdot ' + t.cls + '"></span>' + esc(s.name || s.file || 'source');
      var ttl = ' title="' + esc(t.label) + '"';
      return s.url ? '<a class="src" href="' + esc(s.url) + '" target="_blank"' + ttl + '>' + inner + '</a>'
                   : '<span class="src"' + ttl + '>' + inner + '</span>';
    }).join('') + '</div>';
  }
  function confBadge(c){
    if (!c || !c.level) return '';
    var m = { high: ['High confidence','cf-hi'], medium: ['Medium confidence','cf-md'], low: ['Limited grounding','cf-lo'] };
    var x = m[c.level] || m.low;
    return '<span class="conf ' + x[1] + '">' + x[0] + '</span>';
  }

  var SUGS = ['What mandatory fields does TMF622 Product Order require?', 'What is the difference between TMF620 and TMF633?', 'How do I paginate results in TM Forum Open APIs?'];
  function render(){
    if (view === 'history') { renderHistory(); return; }
    if (!messages.length) {
      thread.innerHTML = '<div class="empty"><div class="etitle">Ask your TM Forum knowledge base</div>'
        + '<div class="sugs">' + SUGS.map(function(s){ return '<button class="sug" data-q="' + esc(s) + '">' + esc(s) + '</button>'; }).join('') + '</div>'
        + '<span class="k">Tip: select code → right-click → <b>SynaptDI</b> → Explain / Check Compliance.</span></div>';
      curBody = null; return;
    }
    thread.innerHTML = messages.map(function(m, idx){
      var cls = 'msg ' + (m.role === 'user' ? 'user' : 'bot') + (m.error ? ' err' : '');
      var role = m.role === 'user' ? 'You' : 'SynaptDI';
      var bodyHtml = m.content ? md(m.content) : '<span class="dots"></span>';
      var footer = '';
      if (m.role === 'assistant' && m.content && !m.error) {
        var lat = m.cached ? '<span class="instant">instant</span>' : (m.latency_ms ? '<span class="meta">' + (m.latency_ms/1000).toFixed(1) + 's</span>' : '');
        var isLast = idx === messages.length - 1;
        footer = '<div class="acts">' + confBadge(m.confidence) + lat
               + '<button class="mini" data-act="copyMsg">Copy</button>'
               + (isLast ? '<button class="mini" data-act="regen">Regenerate</button>' : '') + '</div>';
      }
      return '<div class="' + cls + '"><div class="role">' + role + '</div>'
           + '<div class="body">' + bodyHtml + '</div>'
           + (m.role === 'assistant' ? srcChips(m.sources) : '') + footer + '</div>';
    }).join('');
    curBody = thread.querySelector('.msg:last-child .body');
    scrollDown();
  }
  function scrollDown(){ thread.scrollTop = thread.scrollHeight; }
  function setSending(on){ send.textContent = on ? 'Stop' : 'Ask'; send.classList.toggle('stop', on); }

  async function run(question, fresh){
    if (controller) { controller.abort(); }   // stop any in-flight stream first
    const history = messages.filter(m => m.content && !m.error).slice(-6).map(m => ({ role: m.role, content: m.content }));
    messages.push({ role: 'user', content: question });
    messages.push({ role: 'assistant', content: '' });
    render(); persist();

    var sendQ = question;
    var ctxParts = [];
    if (attach && editorCtx && editorCtx.file) {
      var c = await requestContent();
      if (c && c.code && c.code.trim()) ctxParts.push({ file: c.file, lang: c.lang, code: c.code });
    }
    for (var ei = 0; ei < extraFiles.length; ei++) {
      var f = extraFiles[ei], dup = false;
      for (var pi = 0; pi < ctxParts.length; pi++) { if (ctxParts[pi].file === f.file) { dup = true; break; } }
      if (!dup) ctxParts.push(f);
    }
    if (ctxParts.length) {
      var blocks = ctxParts.map(function(p){ return '### ' + p.file + (p.lang ? ' (' + p.lang + ')' : '') + '\\n' + FENCE + (p.lang || '') + '\\n' + p.code + '\\n' + FENCE; }).join('\\n\\n');
      var intro = ctxParts.length === 1 ? 'I am working in the file "' + ctxParts[0].file + '".' : 'I am working across these ' + ctxParts.length + ' files:';
      sendQ = intro + '\\n\\n' + blocks
            + '\\n\\nUsing the TM Forum / ODA knowledge base, answer my question about this code, and flag any TM Forum compliance issues you notice.\\n\\nMy question: ' + question;
    }

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
        body: JSON.stringify({ question: sendQ, top_k: mode === 'fast' ? 4 : 8, scope, history, mode, no_cache: !!fresh }),
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) throw new Error('API error ' + res.status);
      setDot(true);
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
          else if (evt.type === 'done') { last.sources = evt.sources; last.latency_ms = evt.latency_ms; last.confidence = evt.confidence; last.cached = evt.cached; }
          else if (evt.type === 'error') { acc = evt.text; last.content = acc; last.error = true; }
        }
      }
    } catch (e) {
      if (e && e.name === 'AbortError') { last.content = acc ? acc + '\\n\\n_(stopped)_' : '_(stopped)_'; }
      else { last.content = 'Could not reach SynaptDI at ' + API + ' — is the backend running on port 8000? (' + (e && e.message || e) + ')'; last.error = true; setDot(false); }
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
  function regenerate(){
    if (controller) return;
    var lastUser = null;
    for (var i = messages.length - 1; i >= 0; i--) { if (messages[i].role === 'user') { lastUser = messages[i].content; break; } }
    if (!lastUser) return;
    if (messages.length >= 2 && messages[messages.length - 1].role === 'assistant') messages.splice(messages.length - 2, 2);
    run(lastUser, true);   // skip cache → genuinely fresh answer
  }

  function ctxIcon(){
    return '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"><path d="M9 1.6H4a1 1 0 0 0-1 1v10.8a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V5.6L9 1.6Z"/><path d="M9 1.6v4h4"/></svg>';
  }
  function shieldIcon(col){
    return '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="' + col + '" stroke-width="1.3" stroke-linejoin="round"><path d="M8 1.5l5 2v4c0 3.2-2.1 5.5-5 6.9C5.1 13 3 10.7 3 7.5v-4l5-2Z"/></svg>';
  }
  function wandIcon(){
    return '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"><path d="M3 13L10 6"/><path d="M9.5 3.5l3 3"/><path d="M11.6 1.4l.4 1.2 1.2.4-1.2.4-.4 1.2-.4-1.2-1.2-.4 1.2-.4.4-1.2Z"/></svg>';
  }
  function scoreColor(s){ return s >= 90 ? '#3fb950' : (s >= 70 ? '#d29922' : '#f85149'); }
  function renderCtx(){
    var bar = document.getElementById('ctxbar');
    if (!bar) return;
    var html = '';
    if (editorCtx && editorCtx.file) {
      var sub = editorCtx.hasSelection ? 'selection' : (editorCtx.lines ? editorCtx.lines + ' lines' : 'file');
      if (attach) {
        html += '<span class="ctxchip on" title="SynaptDI reads this file when you ask">'
          + ctxIcon() + 'Reading <b>' + esc(editorCtx.file) + '</b>'
          + '<span style="opacity:.65">' + esc(sub) + '</span>'
          + '<button class="x" id="ctxoff" title="Ask without the open file">\\u00d7</button></span>';
      } else {
        html += '<span class="ctxchip off" id="ctxon" title="Include the open file as context">'
          + ctxIcon() + 'Use <b>' + esc(editorCtx.file) + '</b></span>';
      }
      if (editorCtx.isSpec && comp && comp.file === editorCtx.file) {
        var col = scoreColor(comp.score);
        var bits = [];
        if (comp.failed) bits.push(comp.failed + ' error' + (comp.failed === 1 ? '' : 's'));
        if (comp.warnings) bits.push(comp.warnings + ' warning' + (comp.warnings === 1 ? '' : 's'));
        var issues = bits.join(' · ') || 'all checks pass';
        html += '<span class="compill" id="compcheck" title="' + esc((comp.api || 'spec') + ' — TMF630 compliance, click for details') + '" style="border-color:' + col + '">'
          + shieldIcon(col) + '<b style="color:' + col + '">' + comp.score + '/100</b>'
          + '<span style="opacity:.7">' + esc(issues) + '</span></span>';
        if (comp.fixable) html += '<button class="fixbtn" id="fixactive" title="Auto-fix the mechanical issues — deterministic, no AI">' + wandIcon() + 'Auto-fix ' + comp.fixable + '</button>';
      }
    }
    for (var i = 0; i < extraFiles.length; i++) {
      html += '<span class="ctxchip" title="Added to the chat context">' + ctxIcon() + '<b>' + esc(extraFiles[i].file) + '</b>'
        + '<button class="x" data-rmfile="' + i + '" title="Remove from context">\\u00d7</button></span>';
    }
    html += '<button class="addfile" id="addfile" title="Add another file to the chat context">+ Add file</button>';
    bar.innerHTML = html;
  }
  function requestContent(){
    return new Promise(function(resolve){
      pendingContent = resolve;
      vscodeApi.postMessage({ type: 'getContent' });
      setTimeout(function(){ if (pendingContent) { var r = pendingContent; pendingContent = null; r(null); } }, 1500);
    });
  }

  function groupByDateJS(list){
    var now = new Date();
    var startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    var defs = [['Today', startToday], ['Yesterday', startToday - 86400000], ['Previous 7 Days', startToday - 7*86400000], ['Previous 30 Days', startToday - 30*86400000], ['Older', -Infinity]];
    var groups = defs.map(function(d){ return { label: d[0], cut: d[1], items: [] }; });
    list.forEach(function(c){ var u = c.updated || 0; for (var i = 0; i < groups.length; i++) { if (u >= groups[i].cut) { groups[i].items.push(c); break; } } });
    return groups.filter(function(g){ return g.items.length; });
  }
  function renderHistory(){
    var ql = histQuery.trim().toLowerCase();
    var list = conversations.filter(function(c){
      if (!ql) return true;
      if ((c.title || '').toLowerCase().indexOf(ql) >= 0) return true;
      return (c.messages || []).some(function(m){ return (m.content || '').toLowerCase().indexOf(ql) >= 0; });
    });
    list.sort(function(a, b){ return (b.updated || 0) - (a.updated || 0); });
    var html = '<div class="histbar"><input id="histq" class="histq" placeholder="Search history (titles + messages)" value="' + esc(histQuery) + '"/></div>';
    if (!conversations.length) {
      html += '<div class="empty">No saved chats yet.<br><span class="k">Your conversations are saved here automatically as you chat.</span></div>';
    } else if (!list.length) {
      html += '<div class="empty">No chats match.</div>';
    } else {
      groupByDateJS(list).forEach(function(g){
        html += '<div class="hgroup">' + g.label + '</div>';
        g.items.forEach(function(c){
          var snip = '';
          if (ql) {
            for (var i = 0; i < (c.messages || []).length; i++) {
              var ct = c.messages[i].content || '';
              var k = ct.toLowerCase().indexOf(ql);
              if (k >= 0) { snip = ((k > 30 ? '…' : '') + ct.slice(Math.max(0, k - 30), k + 60)).replace(/\\n/g, ' '); break; }
            }
          }
          html += '<div class="hitem" data-open="' + c.id + '"><div class="htitle">' + esc(c.title || 'Untitled') + '</div>'
               +  (snip ? '<div class="hsnip">' + esc(snip) + '</div>' : '')
               +  '<button class="hdel" data-del="' + c.id + '" title="Delete chat">\\u00d7</button></div>';
        });
      });
    }
    thread.innerHTML = html;
    var hq = document.getElementById('histq');
    if (hq) { hq.oninput = function(){ histQuery = hq.value; renderHistory(); }; hq.focus(); }
  }
  function openConvo(id){
    var c = null;
    for (var i = 0; i < conversations.length; i++) { if (conversations[i].id === id) { c = conversations[i]; break; } }
    if (!c) return;
    if (controller) controller.abort();
    activeId = id; messages = (c.messages || []).slice(); view = 'chat'; render(); persist();
  }
  function deleteConvo(id){
    conversations = conversations.filter(function(c){ return c.id !== id; });
    if (activeId === id) { activeId = null; messages = []; }
    render(); persist();
  }

  // ── Events ──
  send.addEventListener('click', submit);
  document.getElementById('history').addEventListener('click', function(){ view = (view === 'history' ? 'chat' : 'history'); histQuery = ''; render(); });
  q.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(); } });
  function autosize(){ q.style.height = 'auto'; q.style.height = Math.min(q.scrollHeight, 140) + 'px'; }
  q.addEventListener('input', autosize);
  scopeSel.addEventListener('change', () => { scope = scopeSel.value; persist(); });
  modeBtn.addEventListener('click', function(){ mode = (mode === 'deep' ? 'fast' : 'deep'); paintMode(); persist(); });
  document.getElementById('newchat').addEventListener('click', function(){
    if (controller) controller.abort();
    persist();                 // save the current thread into history first
    messages = []; activeId = null; extraFiles = []; view = 'chat'; render(); renderCtx(); persist();
  });
  document.getElementById('ctxbar').addEventListener('click', function(e){
    if (e.target.closest('#ctxoff')) { attach = false; renderCtx(); persist(); }
    else if (e.target.closest('#ctxon')) { attach = true; renderCtx(); persist(); }
    else if (e.target.closest('#fixactive')) { vscodeApi.postMessage({ type: 'command', command: 'synaptdi.fixAll' }); }
    else if (e.target.closest('#compcheck')) { vscodeApi.postMessage({ type: 'command', command: 'synaptdi.checkCompliance' }); }
    else if (e.target.closest('#addfile')) { vscodeApi.postMessage({ type: 'pickFiles' }); }
    else { var rm = e.target.closest('[data-rmfile]'); if (rm) { extraFiles.splice(parseInt(rm.getAttribute('data-rmfile'), 10), 1); renderCtx(); } }
  });

  // Delegation: suggestions, code Copy/Insert, answer Copy, Regenerate.
  thread.addEventListener('click', function(e){
    var del = e.target.closest('[data-del]');
    if (del) { deleteConvo(del.getAttribute('data-del')); return; }
    var openItem = e.target.closest('[data-open]');
    if (openItem) { openConvo(openItem.getAttribute('data-open')); return; }
    var sug = e.target.closest('.sug');
    if (sug) { run(sug.getAttribute('data-q')); return; }
    var btn = e.target.closest('[data-act]');
    if (!btn) return;
    var act = btn.dataset.act;
    if (act === 'copy' || act === 'apply') {
      var codeWrap = btn.closest('.code');
      var codeEl = codeWrap ? codeWrap.querySelector('pre code') : null;
      if (!codeEl) return;
      var code = codeEl.textContent || '';
      if (act === 'copy') { vscodeApi.postMessage({ type: 'copy', text: code }); btn.textContent = 'Copied'; setTimeout(function(){ btn.textContent = 'Copy'; }, 1200); }
      else { vscodeApi.postMessage({ type: 'applyCode', code: code }); btn.textContent = 'Opening diff…'; setTimeout(function(){ btn.textContent = 'Apply'; }, 1600); }
    } else if (act === 'copyMsg') {
      var msgEl = btn.closest('.msg');
      var body = msgEl ? msgEl.querySelector('.body') : null;
      vscodeApi.postMessage({ type: 'copy', text: body ? body.innerText : '' });
      btn.textContent = 'Copied'; setTimeout(function(){ btn.textContent = 'Copy'; }, 1200);
    } else if (act === 'regen') { regenerate(); }
  });

  // Messages from the extension host.
  window.addEventListener('message', function(ev){
    var m = ev.data;
    if (!m) return;
    if (m.type === 'ask') { view = 'chat'; run(m.question); }
    else if (m.type === 'clear') { if (controller) controller.abort(); persist(); messages = []; activeId = null; extraFiles = []; view = 'chat'; render(); renderCtx(); persist(); }
    else if (m.type === 'editorContext') { editorCtx = m.file ? m : null; if (!editorCtx || (comp && comp.file !== editorCtx.file)) comp = null; renderCtx(); }
    else if (m.type === 'compliance') { comp = m; renderCtx(); }
    else if (m.type === 'extraFiles') {
      var incoming = m.files || [];
      for (var i = 0; i < incoming.length; i++) {
        var nf = incoming[i], have = false;
        for (var j = 0; j < extraFiles.length; j++) { if (extraFiles[j].file === nf.file) { extraFiles[j] = nf; have = true; break; } }
        if (!have) extraFiles.push(nf);
      }
      if (extraFiles.length > 4) extraFiles = extraFiles.slice(-4);
      renderCtx();
    }
    else if (m.type === 'content') { if (pendingContent) { var r = pendingContent; pendingContent = null; r(m); } }
  });

  render();
  renderCtx();
  vscodeApi.postMessage({ type: 'ready' });
</script>
</body>
</html>`;
}
