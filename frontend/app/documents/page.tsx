"use client";
import { useState, useRef, useEffect, useCallback, Fragment } from "react";
import AppShell from "../components/AppShell";
import { useAuth } from "../components/AuthProvider";
import { useToast } from "../components/Toast";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function usePageTitle(t: string) {
  useEffect(() => {
    document.title = `${t} · SynaptDI`;
    return () => { document.title = "SynaptDI"; };
  }, [t]);
}

// ── Types ─────────────────────────────────────────────────────────────────────
type DocStatus = "indexed" | "processing" | "failed";
type DocsTab   = "management" | "performance";

interface LibraryDoc {
  file:    string;
  name:    string;
  folder:  string;
  chunks:  number;
  status:  "indexed";
}

interface LibraryGroup {
  id:        string;
  name:      string;
  files:     number;
  chunks:    number;
  documents: LibraryDoc[];
}

interface Doc {
  file:     string;
  name:     string;
  size?:    string;
  status:   DocStatus;
  chunks:   number;
  uploaded?: string;
  error?:   string;
  type?:    "file" | "repo" | "web";
  url?:     string;
  category?: string;
  folder?:   string;
}

// ── Shared ─────────────────────────────────────────────────────────────────────
const STATUS_CFG: Record<DocStatus, { label: string; badge: string; dot: string }> = {
  indexed:    { label: "Indexed",    badge: "bg-green-100 text-green-700",  dot: "bg-green-500" },
  processing: { label: "Processing", badge: "bg-amber-100 text-amber-700",  dot: "bg-amber-400" },
  failed:     { label: "Failed",     badge: "bg-red-100 text-red-700",      dot: "bg-red-500" },
};

function StatusBadge({ status }: { status: DocStatus }) {
  const c = STATUS_CFG[status];
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full ${c.badge}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${c.dot} ${status === "processing" ? "animate-pulse" : ""}`} />
      {c.label}
    </span>
  );
}

function RelevanceBar({ value }: { value: number }) {
  const pct   = Math.round(value * 100);
  const color = pct >= 90 ? "bg-green-500" : pct >= 80 ? "bg-blue-500" : pct >= 70 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gray-100 dark:bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-medium text-gray-600 dark:text-slate-400 w-8 text-right">{pct}%</span>
    </div>
  );
}

// ── Document Management Tab ───────────────────────────────────────────────────
function ManagementTab({ user }: { user: { role: string } | null }) {
  const toast = useToast();
  const [docs, setDocs]         = useState<Doc[]>([]);
  const [filter, setFilter]     = useState<DocStatus | "all">("all");
  const [search, setSearch]     = useState("");
  const [dragging, setDragging] = useState(false);
  const [loadingList, setLL]    = useState(true);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Library (data/ folder) state ──────────────────────────────────────────
  const [libGroups, setLibGroups]     = useState<LibraryGroup[]>([]);
  const [libSummary, setLibSummary]   = useState({ total_files: 0, total_chunks: 0 });
  const [activeLib, setActiveLib]     = useState<string | null>(null);
  const [loadingLib, setLoadingLib]   = useState(true);
  const [folders, setFolders]         = useState<{ name: string; count: number }[]>([]);

  const canUpload = user?.role === "admin" || user?.role === "analyst";

  const [repoUrl, setRepoUrl] = useState("");
  const [webUrl,  setWebUrl]  = useState("");
  const [adding,  setAdding]  = useState<"repo" | "web" | null>(null);

  const addSource = async (kind: "repo" | "weblink", url: string) => {
    if (!url.trim()) { toast("Please enter a URL", "warning"); return; }
    setAdding(kind === "repo" ? "repo" : "web");
    try {
      const t = typeof window !== "undefined" ? localStorage.getItem("synaptdi_token") : null;
      const r = await fetch(`${API}/sources/${kind}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify({ url: url.trim() }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || (r.status === 403 ? "Admin access required" : "Failed to add source"));
      toast("Added — indexing in the background", "info");
      setRepoUrl(""); setWebUrl("");
      fetchDocs();
    } catch (e: any) {
      toast(e.message || "Failed to add source", "error");
    } finally {
      setAdding(null);
    }
  };

  // ── Fetch document list ────────────────────────────────────────────────────
  const fetchDocs = useCallback(async () => {
    try {
      const r = await fetch(`${API}/documents`);
      if (!r.ok) return;
      const data = await r.json();
      setDocs(data.documents ?? []);
      try { const fr = await fetch(`${API}/folders`); if (fr.ok) setFolders((await fr.json()).folders || []); } catch {}
    } catch {}
  }, []);

  // ── Fetch knowledge-base library ───────────────────────────────────────────
  const fetchLibrary = useCallback(async () => {
    try {
      const r = await fetch(`${API}/documents/library`);
      if (!r.ok) return;
      const data = await r.json();
      setLibGroups(data.groups ?? []);
      setLibSummary({ total_files: data.total_files ?? 0, total_chunks: data.total_chunks ?? 0 });
    } catch {}
  }, []);

  useEffect(() => {
    fetchDocs().finally(() => setLL(false));
    fetchLibrary().finally(() => setLoadingLib(false));
  }, [fetchDocs, fetchLibrary]);

  // Poll while any doc is processing
  useEffect(() => {
    const hasProcessing = docs.some(d => d.status === "processing");
    if (hasProcessing && !pollRef.current) {
      pollRef.current = setInterval(fetchDocs, 3000);
    } else if (!hasProcessing && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [docs, fetchDocs]);

  // ── Upload ─────────────────────────────────────────────────────────────────
  const uploadFile = async (file: File) => {
    const sizeMB = (file.size / 1_048_576).toFixed(1);
    // Optimistic entry
    const optimistic: Doc = {
      file: file.name, name: file.name.replace(/\.[^.]+$/, ""),
      size: `${sizeMB} MB`, status: "processing", chunks: 0,
      uploaded: "Now",
    };
    setDocs(prev => [optimistic, ...prev.filter(d => d.file !== file.name)]);
    toast(`Uploading "${file.name}"…`, "info");

    const form = new FormData();
    form.append("file", file);

    try {
      const r = await fetch(`${API}/documents/upload`, { method: "POST", body: form });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: "Upload failed" }));
        throw new Error(err.detail ?? "Upload failed");
      }
      toast(`"${file.name}" uploaded — indexing in background`, "info");
      fetchDocs();
    } catch (e: any) {
      toast(e.message ?? "Upload failed", "error");
      setDocs(prev => prev.map(d =>
        d.file === file.name ? { ...d, status: "failed" } : d
      ));
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
    e.target.value = "";
  };

  // ── Retry ──────────────────────────────────────────────────────────────────
  const retryDoc = async (doc: Doc) => {
    const raw = await fetch(`${API}/documents/${encodeURIComponent(doc.file)}/status`).catch(() => null);
    if (!raw) { toast("Could not reach backend", "error"); return; }
    // Re-upload the original file from disk is not possible without storing it
    // Instead mark as processing and re-trigger ingest from stored file
    toast(`Retrying "${doc.name}"…`, "info");
    await fetch(`${API}/documents/${encodeURIComponent(doc.file)}`, { method: "DELETE" });
    toast(`Removed failed entry — please re-upload the file.`, "info");
    fetchDocs();
  };

  // ── Delete ─────────────────────────────────────────────────────────────────
  const deleteDoc = async (doc: Doc) => {
    setDocs(prev => prev.filter(d => d.file !== doc.file));
    try {
      const r = await fetch(`${API}/documents/${encodeURIComponent(doc.file)}`, { method: "DELETE" });
      if (!r.ok) throw new Error("Delete failed");
      toast(`"${doc.name}" removed`, "info");
    } catch {
      toast("Failed to delete document", "error");
      fetchDocs(); // restore
    }
  };

  // ── Refresh a single repo/web source ───────────────────────────────────────
  const refreshSource = async (doc: Doc) => {
    setDocs(prev => prev.map(d => d.file === doc.file ? { ...d, status: "processing" } : d));
    toast(`Refreshing "${doc.name}" from source…`, "info");
    try {
      const t = typeof window !== "undefined" ? localStorage.getItem("synaptdi_token") : null;
      const r = await fetch(`${API}/sources/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) },
        body: JSON.stringify({ origin: doc.file }),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || "Refresh failed"); }
      fetchDocs();   // background polling picks up the new status + chunk count
    } catch (e: any) {
      toast(e.message || "Failed to refresh source", "error");
      fetchDocs();
    }
  };

  // ── Folder management ───────────────────────────────────────────────────────
  const authHdr = () => {
    const t = typeof window !== "undefined" ? localStorage.getItem("synaptdi_token") : null;
    return { "Content-Type": "application/json", ...(t ? { Authorization: `Bearer ${t}` } : {}) };
  };
  const createFolder = async () => {
    const name = (prompt("New folder name:") || "").trim();
    if (!name) return;
    try {
      const r = await fetch(`${API}/folders`, { method: "POST", headers: authHdr(), body: JSON.stringify({ name }) });
      if (!r.ok) throw new Error();
      toast(`Folder "${name}" created`, "success"); fetchDocs();
    } catch { toast("Failed to create folder (admin only)", "error"); }
  };
  const moveDoc = async (doc: Doc, folder: string) => {
    setDocs(prev => prev.map(d => d.file === doc.file ? { ...d, folder } : d));
    try {
      const r = await fetch(`${API}/documents/${encodeURIComponent(doc.file)}/folder`,
        { method: "POST", headers: authHdr(), body: JSON.stringify({ folder }) });
      if (!r.ok) throw new Error();
      fetchDocs();
    } catch { toast("Failed to move (admin only)", "error"); fetchDocs(); }
  };
  const deleteFolder = async (name: string) => {
    if (!confirm(`Delete folder "${name}"? Its documents move to Uncategorized — they are not deleted.`)) return;
    try {
      const r = await fetch(`${API}/folders/${encodeURIComponent(name)}`, { method: "DELETE", headers: authHdr() });
      if (!r.ok) throw new Error();
      toast(`Folder "${name}" deleted`, "info"); fetchDocs();
    } catch { toast("Failed to delete folder", "error"); }
  };
  const refreshFolder = async (name: string) => {
    toast(`Refreshing sources in "${name}"…`, "info");
    try {
      const r = await fetch(`${API}/folders/${encodeURIComponent(name)}/refresh`, { method: "POST", headers: authHdr() });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error();
      toast(d.refreshed ? `Refreshing ${d.refreshed} source(s)…` : (d.note || "Nothing to refresh here"), "info");
      fetchDocs();
    } catch { toast("Failed to refresh folder", "error"); }
  };

  const visible = docs.filter(d =>
    (filter === "all" || d.status === filter) &&
    d.name.toLowerCase().includes(search.toLowerCase())
  );

  // Group sources into the user's folders (Uncategorized last). Empty folders still
  // show so you can move documents into them.
  const [collapsedCats, setCollapsedCats] = useState<Set<string>>(new Set());
  const toggleCat = (c: string) =>
    setCollapsedCats(s => { const n = new Set(s); n.has(c) ? n.delete(c) : n.add(c); return n; });
  const folderGroups = (() => {
    const names = new Set<string>(folders.map(f => f.name));
    for (const d of visible) if (d.folder) names.add(d.folder);
    const ordered = [...names].sort((a, b) => a.localeCompare(b));
    const m: Record<string, Doc[]> = { Uncategorized: [] };
    for (const n of ordered) m[n] = [];
    for (const d of visible) (m[d.folder || "Uncategorized"] ||= []).push(d);
    return [...ordered, "Uncategorized"]
      .filter(k => (m[k]?.length ?? 0) > 0 || k !== "Uncategorized")   // hide Uncategorized only when empty
      .map(k => ({ cat: k, docs: m[k] || [] }));
  })();

  const stats = {
    total:      docs.length,
    indexed:    docs.filter(d => d.status === "indexed").length,
    processing: docs.filter(d => d.status === "processing").length,
    chunks:     docs.reduce((s, d) => s + (d.chunks || 0), 0),
  };

  // The ONE search box filters uploads AND the knowledge base. While searching,
  // KB results flatten into a direct file list — no folder-opening hunt.
  const q = search.trim().toLowerCase();
  const libMatches = q
    ? libGroups.flatMap(g => g.documents
        .filter(d => d.name.toLowerCase().includes(q) || d.file.toLowerCase().includes(q))
        .map(d => ({ ...d, group: g.name })))
    : [];

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Uploaded docs",    value: stats.total,                                              color: "text-gray-900 dark:text-slate-100" },
          { label: "Spec files (KB)",  value: libSummary.total_files.toLocaleString(),                  color: "text-blue-600" },
          { label: "Processing",       value: stats.processing,                                         color: "text-amber-600" },
          { label: "Total chunks",     value: (stats.chunks + libSummary.total_chunks).toLocaleString(), color: "text-red-600"  },
        ].map(s => (
          <div key={s.label} className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-sm px-5 py-4">
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-gray-500 dark:text-slate-400 font-medium mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Upload dropzone */}
      {canUpload && (
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileRef.current?.click()}
          className={`border-2 border-dashed rounded-2xl px-5 py-4 cursor-pointer transition-all flex items-center gap-4 ${
            dragging ? "border-red-400 bg-red-50" : "border-gray-200 dark:border-slate-700 hover:border-red-300 hover:bg-red-50/30 dark:hover:bg-slate-800/40"
          }`}
        >
          <input ref={fileRef} type="file" accept=".pdf,.docx,.xlsx,.pptx,.csv,.txt,.md,.json,.yaml,.yml"
            className="hidden" onChange={handleFileInput} />
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 transition-colors ${dragging ? "bg-red-100" : "bg-gray-100 dark:bg-slate-800"}`}>
            <svg className={`w-5 h-5 transition-colors ${dragging ? "text-red-500" : "text-gray-400"}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
            </svg>
          </div>
          <div className="min-w-0">
            <p className={`text-sm font-semibold transition-colors ${dragging ? "text-red-600" : "text-gray-700 dark:text-slate-300"}`}>
              {dragging ? "Drop to upload & index" : "Drag & drop to upload — or click to browse"}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">PDF, DOCX, XLSX, PPTX, CSV, TXT, MD, JSON, YAML</p>
          </div>
        </div>
      )}

      {/* Add from a Git repo or a web link */}
      {canUpload && (
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-sm p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-semibold text-gray-700 dark:text-slate-300">From a Git repo</span>
              <span className="text-[10px] text-gray-400 uppercase tracking-wide">GitHub · TMF · MEF</span>
            </div>
            <div className="flex gap-2">
              <input value={repoUrl} onChange={e => setRepoUrl(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") addSource("repo", repoUrl); }}
                placeholder="https://github.com/org/repo"
                className="flex-1 min-w-0 border border-gray-200 dark:border-slate-700 rounded-xl px-3 py-2 text-sm text-gray-800 dark:text-slate-200 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500" />
              <button onClick={() => addSource("repo", repoUrl)} disabled={adding === "repo"}
                className="flex-shrink-0 bg-red-600 hover:bg-red-700 disabled:bg-gray-200 text-white rounded-xl px-4 py-2 text-sm font-semibold transition-colors">
                {adding === "repo" ? "…" : "Add"}
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-1.5">Clones &amp; indexes every OpenAPI spec + doc in the repo.</p>
          </div>
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-sm p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-semibold text-gray-700 dark:text-slate-300">From a web link</span>
              <span className="text-[10px] text-gray-400 uppercase tracking-wide">page or PDF</span>
            </div>
            <div className="flex gap-2">
              <input value={webUrl} onChange={e => setWebUrl(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") addSource("weblink", webUrl); }}
                placeholder="https://example.com/spec"
                className="flex-1 min-w-0 border border-gray-200 dark:border-slate-700 rounded-xl px-3 py-2 text-sm text-gray-800 dark:text-slate-200 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500" />
              <button onClick={() => addSource("weblink", webUrl)} disabled={adding === "web"}
                className="flex-shrink-0 bg-red-600 hover:bg-red-700 disabled:bg-gray-200 text-white rounded-xl px-4 py-2 text-sm font-semibold transition-colors">
                {adding === "web" ? "…" : "Add"}
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-1.5">Fetches the page (or PDF) and indexes its text.</p>
          </div>
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search everything — your documents & all knowledge-base specs…"
            className="w-full border border-gray-200 dark:border-slate-700 rounded-xl pl-9 pr-4 py-2 text-sm text-gray-700 dark:text-slate-300 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500 bg-white dark:bg-slate-800" />
        </div>
        <div className="flex gap-1 bg-gray-100 dark:bg-slate-800 rounded-xl p-1">
          {(["all","indexed","processing","failed"] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all capitalize ${
                filter === f ? "bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 shadow-sm" : "text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-300"
              }`}>{f}</button>
          ))}
        </div>
        {canUpload && (
          <button onClick={createFolder}
            className="flex items-center gap-1.5 text-sm font-medium text-gray-600 dark:text-slate-300 border border-gray-200 dark:border-slate-700 rounded-xl px-3 py-2 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg>
            New folder
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-sm overflow-hidden">
        {loadingList ? (
          <div className="p-5 space-y-3">
            {[92, 78, 85, 64].map((w, i) => (
              <div key={i} className="flex items-center gap-4">
                <div className="skeleton h-9 w-9 rounded-lg flex-shrink-0" />
                <div className="flex-1 space-y-1.5">
                  <div className="skeleton h-3" style={{ width: `${w}%` }} />
                  <div className="skeleton h-2.5 w-24" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 dark:bg-slate-800 border-b border-gray-100 dark:border-slate-800">
                {["Document","Status","Chunks",""].map((h, i) => (
                  <th key={i} className={`text-[11px] font-bold text-gray-400 uppercase tracking-widest px-5 py-2.5 ${i === 0 ? "text-left" : "text-center"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {folderGroups.map(g => (
                <Fragment key={g.cat}>
                  <tr className="bg-gray-50 dark:bg-slate-800/60 select-none group/fold">
                    <td colSpan={4} className="px-5 py-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-slate-300 cursor-pointer" onClick={() => toggleCat(g.cat)}>
                          <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform ${collapsedCats.has(g.cat) ? "" : "rotate-90"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><polyline points="9 18 15 12 9 6"/></svg>
                          <svg className="w-4 h-4 text-amber-500" fill="currentColor" viewBox="0 0 24 24"><path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z"/></svg>
                          {g.cat}
                          <span className="text-xs font-normal text-gray-400">· {g.docs.length} {g.docs.length === 1 ? "source" : "sources"}</span>
                        </div>
                        {canUpload && g.cat !== "Uncategorized" && (
                          <div className="flex items-center gap-1 opacity-0 group-hover/fold:opacity-100 transition-opacity">
                            <button onClick={() => refreshFolder(g.cat)} title="Refresh all repo/web sources in this folder"
                              className="p-1 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors">
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg>
                            </button>
                            <button onClick={() => deleteFolder(g.cat)} title="Delete folder (documents move to Uncategorized)"
                              className="p-1 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors">
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6m5 0V4h4v2"/></svg>
                            </button>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                  {(search.trim() !== "" || !collapsedCats.has(g.cat)) && g.docs.map(doc => (
                    <tr key={doc.file} className="hover:bg-gray-50 dark:hover:bg-slate-800/70 transition-colors group">
                  <td className="px-5 py-2.5">
                    <div className="flex items-center gap-3">
                      <div className="w-7 h-7 bg-red-50 dark:bg-red-500/10 border border-red-100 dark:border-red-500/20 rounded-lg flex items-center justify-center flex-shrink-0">
                        <svg className="w-3.5 h-3.5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/>
                        </svg>
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-gray-900 dark:text-slate-100 truncate max-w-xs">{doc.name}</span>
                          {doc.type && doc.type !== "file" && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 flex-shrink-0 tracking-wide">
                              {doc.type === "repo" ? "GIT REPO" : "WEB"}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-400 truncate">
                          <span className="font-mono">{doc.url || doc.file}</span>
                          {doc.size ? <span> · {doc.size}</span> : null}
                          {doc.uploaded ? <span> · {doc.uploaded}</span> : null}
                        </div>
                        {doc.error && <div className="text-xs text-red-500 mt-0.5">Error: {doc.error}</div>}
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-2.5 text-center"><StatusBadge status={doc.status} /></td>
                  <td className="px-5 py-2.5 text-center">
                    <span className="text-sm font-medium text-gray-700 dark:text-slate-300">
                      {doc.chunks > 0 ? doc.chunks.toLocaleString() : "—"}
                    </span>
                  </td>
                  <td className="px-5 py-2.5">
                    <div className="flex items-center justify-end gap-1.5">
                      {canUpload && (
                        <select value={doc.folder || ""} onChange={e => moveDoc(doc, e.target.value)}
                          title="Move to folder"
                          className="text-xs border border-gray-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-gray-600 dark:text-slate-300 px-1.5 py-1 max-w-[120px] focus:outline-none focus:ring-1 focus:ring-red-500">
                          <option value="">Uncategorized</option>
                          {folders.map(f => <option key={f.name} value={f.name}>{f.name}</option>)}
                        </select>
                      )}
                      <span className="flex items-center gap-1.5 opacity-60 group-hover:opacity-100 transition-opacity">
                      {doc.status === "failed" && (
                        <button onClick={() => retryDoc(doc)} title="Remove failed entry"
                          className="p-1.5 rounded-lg text-amber-500 hover:text-amber-700 hover:bg-amber-50 dark:hover:bg-amber-500/10 transition-colors">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                            <polyline points="1 4 1 10 7 10"/>
                            <path d="M3.51 15a9 9 0 102.13-9.36L1 10"/>
                          </svg>
                        </button>
                      )}
                      {canUpload && (doc.type === "repo" || doc.type === "web") && doc.status !== "processing" && (
                        <button onClick={() => refreshSource(doc)} title="Re-fetch & re-index this source"
                          className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-500/10 transition-colors">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                            <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
                          </svg>
                        </button>
                      )}
                      {canUpload && doc.status !== "processing" && (
                        <button onClick={() => deleteDoc(doc)} title="Delete document"
                          className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6l-1 14H6L5 6m5 0V4h4v2"/>
                          </svg>
                        </button>
                      )}
                      </span>
                    </div>
                  </td>
                </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
        {!loadingList && visible.length === 0 && (
          <div className="text-center py-16">
            <p className="text-gray-400 text-sm">
              {docs.length === 0
                ? "No documents uploaded yet. Drag & drop a file above to get started."
                : "No documents match your filter."}
            </p>
          </div>
        )}
      </div>

      {/* ── Knowledge Base (data/ folder) ──────────────────────────────────── */}
      <div>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Knowledge Base</h2>
          <p className="text-xs text-gray-400">
            {libSummary.total_files.toLocaleString()} files · {libSummary.total_chunks.toLocaleString()} chunks · pre-indexed, read-only
          </p>
        </div>

        {loadingLib ? (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
            {[0, 1, 2].map(i => <div key={i} className="skeleton h-16 rounded-xl" />)}
          </div>
        ) : q ? (
          /* Searching → flat results across every folder, no clicking around */
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-sm overflow-hidden">
            <div className="px-4 py-2.5 border-b border-gray-100 dark:border-slate-800 text-xs text-gray-400">
              {libMatches.length} spec{libMatches.length === 1 ? "" : "s"} matching “{search.trim()}”
            </div>
            <div className="divide-y divide-gray-50 dark:divide-slate-800 max-h-80 overflow-y-auto">
              {libMatches.map(doc => (
                <div key={doc.file} className="flex items-center gap-3 px-4 py-2 hover:bg-gray-50 dark:hover:bg-slate-800/60 transition-colors">
                  <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-500/10 text-blue-700 dark:text-blue-400 border border-blue-200 dark:border-blue-500/30 flex-shrink-0">{doc.group}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-gray-800 dark:text-slate-200 truncate">{doc.name}</div>
                    <div className="text-[11px] text-gray-400 font-mono truncate">{doc.file}</div>
                  </div>
                  <span className="text-xs text-gray-400 flex-shrink-0">{doc.chunks.toLocaleString()} chunks</span>
                </div>
              ))}
              {libMatches.length === 0 && (
                <div className="py-8 text-center text-sm text-gray-400">No specs match — try a TMF number or a keyword like “order”.</div>
              )}
            </div>
          </div>
        ) : (
          /* Browsing → compact folder grid; click a folder to see its files below */
          <>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {libGroups.map(group => {
                const active = activeLib === group.id;
                return (
                  <button key={group.id} onClick={() => setActiveLib(active ? null : group.id)}
                    className={`flex items-center gap-2.5 px-3.5 py-3 rounded-xl border text-left transition-all ${
                      active
                        ? "bg-red-50 dark:bg-red-500/10 border-red-300 dark:border-red-500/40 shadow-sm"
                        : "bg-white dark:bg-slate-900 border-gray-200 dark:border-slate-700 hover:border-red-200 dark:hover:border-slate-500 hover:shadow-sm"
                    }`}>
                    <svg className={`w-5 h-5 flex-shrink-0 ${active ? "text-red-500" : "text-amber-500"}`} fill="currentColor" viewBox="0 0 24 24">
                      <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z"/>
                    </svg>
                    <div className="min-w-0">
                      <div className={`text-sm font-semibold truncate ${active ? "text-red-700 dark:text-red-400" : "text-gray-800 dark:text-slate-200"}`}>{group.name}</div>
                      <div className="text-[11px] text-gray-400">{group.files} files · {group.chunks.toLocaleString()} chunks</div>
                    </div>
                    <svg className={`w-3.5 h-3.5 ml-auto flex-shrink-0 text-gray-300 dark:text-slate-600 transition-transform ${active ? "rotate-90 text-red-400" : ""}`}
                      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><polyline points="9 18 15 12 9 6"/></svg>
                  </button>
                );
              })}
            </div>

            {activeLib && (() => {
              const group = libGroups.find(g => g.id === activeLib);
              if (!group) return null;
              return (
                <div className="mt-2 bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-sm overflow-hidden">
                  <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-slate-800">
                    <span className="text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider">{group.name} — {group.files} files</span>
                    <button onClick={() => setActiveLib(null)} className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-slate-300">Close</button>
                  </div>
                  <div className="divide-y divide-gray-50 dark:divide-slate-800 max-h-80 overflow-y-auto">
                    {group.documents.map(doc => (
                      <div key={doc.file} className="flex items-center gap-3 px-4 py-2 hover:bg-gray-50 dark:hover:bg-slate-800/60 transition-colors">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-gray-800 dark:text-slate-200 truncate">{doc.name}</div>
                          <div className="text-[11px] text-gray-400 font-mono truncate">{doc.file}</div>
                        </div>
                        <span className="text-xs text-gray-400 flex-shrink-0">{doc.chunks.toLocaleString()} chunks</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })()}
          </>
        )}
      </div>
    </div>
  );
}

// ── Performance Tab ────────────────────────────────────────────────────────────
function PerformanceTab() {
  const [docs, setDocs]         = useState<Doc[]>([]);
  const [hits, setHits]         = useState<Record<string, number>>({});
  const [period, setPeriod]     = useState<"7d"|"30d"|"90d">("30d");
  const [sortBy, setSortBy]     = useState<"queries"|"chunks">("queries");
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    Promise.all([
      fetch(`${API}/documents`).then(r => r.json()),
      fetch(`${API}/stats/queries`).then(r => r.json()),
    ]).then(([docData, hitsData]) => {
      setDocs(docData.documents ?? []);
      setHits(hitsData.hits ?? {});
    }).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const indexed = docs.filter(d => d.status === "indexed");
  const multiplier: Record<string, number> = { "7d": 0.23, "30d": 1, "90d": 2.8 };
  const m = multiplier[period];

  // Enrich with hit counts
  const enriched = indexed.map(d => ({
    ...d,
    queries: Math.round((hits[d.name] ?? 0) * m),
    // Synthetic relevance based on chunk count (more chunks → better coverage)
    relevance: d.chunks > 0 ? Math.min(0.97, 0.70 + (d.chunks / 3000) * 0.25) : 0,
  }));

  const sorted = [...enriched].sort((a, b) =>
    sortBy === "queries" ? b.queries - a.queries : b.chunks - a.chunks
  );

  const totalQueries = enriched.reduce((s, d) => s + d.queries, 0);
  const avgChunks    = indexed.length ? Math.round(indexed.reduce((s, d) => s + d.chunks, 0) / indexed.length) : 0;
  const topDoc       = sorted[0];

  if (loading) {
    return <div className="py-20 text-center text-sm text-gray-400">Loading performance data…</div>;
  }

  if (indexed.length === 0) {
    return (
      <div className="py-20 text-center">
        <p className="text-gray-400 text-sm">No indexed documents yet.</p>
        <p className="text-gray-300 text-xs mt-1">Upload a document in the Management tab to see performance data.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Period selector */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <p className="text-sm text-gray-500 dark:text-slate-400">Performance metrics for {indexed.length} indexed document{indexed.length !== 1 ? "s" : ""}</p>
        <div className="flex gap-1 bg-gray-100 dark:bg-slate-800 rounded-xl p-1">
          {(["7d","30d","90d"] as const).map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                period === p ? "bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 shadow-sm" : "text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-300"
              }`}>{p === "7d" ? "7 days" : p === "30d" ? "30 days" : "90 days"}</button>
          ))}
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          { label: "Total queries", value: totalQueries.toLocaleString(),
            sub: "across all docs", icon: "💬", bg: "bg-red-50", color: "text-red-600" },
          { label: "Avg chunks/doc", value: avgChunks.toLocaleString(),
            sub: "indexed vectors", icon: "📦", bg: "bg-blue-50", color: "text-blue-600" },
          { label: "Top document",
            value: topDoc ? topDoc.name.slice(0, 22) + (topDoc.name.length > 22 ? "…" : "") : "—",
            sub: topDoc ? `${topDoc.queries.toLocaleString()} queries` : "No data",
            icon: "⭐", bg: "bg-amber-50", color: "text-amber-600" },
        ].map(c => (
          <div key={c.label} className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-sm p-6">
            <div className={`w-10 h-10 ${c.bg} rounded-xl flex items-center justify-center text-xl mb-3`}>{c.icon}</div>
            <div className={`text-2xl font-bold ${c.color} leading-none`}>{c.value}</div>
            <div className="text-xs text-gray-500 dark:text-slate-400 font-medium mt-1">{c.label}</div>
            <div className="text-[11px] text-gray-400">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-slate-800">
          <h2 className="text-sm font-semibold text-gray-900 dark:text-slate-100">Document Performance</h2>
          <div className="flex gap-1 bg-gray-100 dark:bg-slate-800 rounded-lg p-0.5">
            {(["queries","chunks"] as const).map(s => (
              <button key={s} onClick={() => setSortBy(s)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  sortBy === s ? "bg-white dark:bg-slate-700 text-gray-900 dark:text-slate-100 shadow-sm" : "text-gray-500 dark:text-slate-400"
                }`}>{s === "queries" ? "By queries" : "By chunks"}</button>
            ))}
          </div>
        </div>
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50 dark:bg-slate-800 border-b border-gray-100 dark:border-slate-800">
              <th className="text-left text-[11px] font-bold text-gray-400 uppercase tracking-widest px-6 py-3">Document</th>
              <th className="text-center text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-3">Queries</th>
              <th className="text-left text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-3 w-44">Coverage</th>
              <th className="text-center text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-3">Chunks</th>
              <th className="text-center text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-3">Rank</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {sorted.map((doc, idx) => (
              <tr key={doc.file} className="hover:bg-gray-50 dark:hover:bg-slate-800/60 transition-colors">
                <td className="px-6 py-4">
                  <div className="text-sm font-semibold text-gray-900 dark:text-slate-100">{doc.name}</div>
                  <div className="text-xs text-gray-400 font-mono mt-0.5">{doc.file}</div>
                </td>
                <td className="px-4 py-4 text-center">
                  <span className="text-sm font-bold text-gray-900 dark:text-slate-100">{doc.queries.toLocaleString()}</span>
                </td>
                <td className="px-4 py-4"><RelevanceBar value={doc.relevance} /></td>
                <td className="px-4 py-4 text-center">
                  <span className="text-sm text-gray-600 dark:text-slate-400">{doc.chunks.toLocaleString()}</span>
                </td>
                <td className="px-4 py-4 text-center">
                  <span className={`text-xs font-bold w-6 h-6 rounded-full inline-flex items-center justify-center ${
                    idx === 0 ? "bg-amber-100 text-amber-700" :
                    idx === 1 ? "bg-gray-100 dark:bg-slate-800 text-gray-600 dark:text-slate-400" :
                    idx === 2 ? "bg-orange-100 text-orange-600" : "bg-gray-50 dark:bg-slate-800 text-gray-400"
                  }`}>{idx + 1}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function DocumentsPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<DocsTab>("management");
  usePageTitle("Documents");

  const tabs: { id: DocsTab; label: string }[] = [
    { id: "management",  label: "Document Management" },
    { id: "performance", label: "Document Performance" },
  ];

  return (
    <AppShell>
      <div className="flex flex-col h-full">
        <header className="flex items-center justify-between px-6 py-4 bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-700 flex-shrink-0">
          <div>
            <h1 className="text-base font-semibold text-gray-900 dark:text-slate-100">Documents</h1>
            <p className="text-xs text-gray-400 mt-0.5">Manage your knowledge base and monitor performance</p>
          </div>
        </header>

        <div className="flex border-b border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-6 flex-shrink-0">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-5 py-3.5 text-sm font-medium border-b-2 transition-all -mb-px ${
                tab === t.id ? "border-red-600 text-red-600" : "border-transparent text-gray-500 dark:text-slate-400 hover:text-gray-800 dark:hover:text-slate-200"
              }`}>{t.label}</button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto bg-gray-50 dark:bg-slate-800">
          <div className="max-w-6xl mx-auto px-6 py-8">
            {tab === "management"  && <ManagementTab user={user} />}
            {tab === "performance" && <PerformanceTab />}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
