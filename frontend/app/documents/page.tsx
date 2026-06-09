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
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-medium text-gray-600 w-8 text-right">{pct}%</span>
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
  const [libExpanded, setLibExpanded] = useState<Set<string>>(new Set());
  const [libSearch, setLibSearch]     = useState("");
  const [loadingLib, setLoadingLib]   = useState(true);

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
      if (data.groups?.length) setLibExpanded(new Set([data.groups[0].id]));
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

  const visible = docs.filter(d =>
    (filter === "all" || d.status === filter) &&
    d.name.toLowerCase().includes(search.toLowerCase())
  );

  // Group sources into collapsible domain folders (TM Forum / ODA / MEF / …)
  const [collapsedCats, setCollapsedCats] = useState<Set<string>>(new Set());
  const toggleCat = (c: string) =>
    setCollapsedCats(s => { const n = new Set(s); n.has(c) ? n.delete(c) : n.add(c); return n; });
  const CAT_ORDER = ["TM Forum", "ODA", "MEF", "ETSI", "3GPP", "IETF", "Other"];
  const folderGroups = (() => {
    const m: Record<string, Doc[]> = {};
    for (const d of visible) { const c = d.category || "Other"; if (!m[c]) m[c] = []; m[c].push(d); }
    return Object.keys(m)
      .sort((a, b) => ((CAT_ORDER.indexOf(a) + 1 || 99) - (CAT_ORDER.indexOf(b) + 1 || 99)) || a.localeCompare(b))
      .map(c => ({ cat: c, docs: m[c] }));
  })();

  const stats = {
    total:      docs.length,
    indexed:    docs.filter(d => d.status === "indexed").length,
    processing: docs.filter(d => d.status === "processing").length,
    chunks:     docs.reduce((s, d) => s + (d.chunks || 0), 0),
  };

  const toggleLib = (id: string) =>
    setLibExpanded(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const filteredLibGroups = libGroups.map(g => ({
    ...g,
    documents: g.documents.filter(d =>
      libSearch === "" ||
      d.name.toLowerCase().includes(libSearch.toLowerCase()) ||
      d.file.toLowerCase().includes(libSearch.toLowerCase())
    ),
  })).filter(g => libSearch === "" || g.documents.length > 0);

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[
          { label: "Uploaded docs",    value: stats.total,                                              color: "text-gray-900" },
          { label: "Spec files (KB)",  value: libSummary.total_files.toLocaleString(),                  color: "text-blue-600" },
          { label: "Processing",       value: stats.processing,                                         color: "text-amber-600" },
          { label: "Total chunks",     value: (stats.chunks + libSummary.total_chunks).toLocaleString(), color: "text-red-600"  },
        ].map(s => (
          <div key={s.label} className="bg-white rounded-2xl border border-gray-200 shadow-sm px-5 py-4">
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-gray-500 font-medium mt-0.5">{s.label}</div>
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
          className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${
            dragging ? "border-red-400 bg-red-50" : "border-gray-200 hover:border-red-300 hover:bg-red-50/30"
          }`}
        >
          <input ref={fileRef} type="file" accept=".pdf,.docx,.xlsx,.pptx,.csv,.txt,.md,.json,.yaml,.yml"
            className="hidden" onChange={handleFileInput} />
          <div className={`w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-3 transition-colors ${dragging ? "bg-red-100" : "bg-gray-100"}`}>
            <svg className={`w-6 h-6 transition-colors ${dragging ? "text-red-500" : "text-gray-400"}`}
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
            </svg>
          </div>
          <p className={`text-sm font-semibold transition-colors ${dragging ? "text-red-600" : "text-gray-600"}`}>
            {dragging ? "Drop to upload & index" : "Drag & drop to upload"}
          </p>
          <p className="text-xs text-gray-400 mt-1">PDF, DOCX, XLSX, PPTX, CSV, TXT, MD, JSON, YAML · Click to browse</p>
        </div>
      )}

      {/* Add from a Git repo or a web link */}
      {canUpload && (
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-semibold text-gray-700">From a Git repo</span>
              <span className="text-[10px] text-gray-400 uppercase tracking-wide">GitHub · TMF · MEF</span>
            </div>
            <div className="flex gap-2">
              <input value={repoUrl} onChange={e => setRepoUrl(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") addSource("repo", repoUrl); }}
                placeholder="https://github.com/org/repo"
                className="flex-1 min-w-0 border border-gray-200 rounded-xl px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500" />
              <button onClick={() => addSource("repo", repoUrl)} disabled={adding === "repo"}
                className="flex-shrink-0 bg-red-600 hover:bg-red-700 disabled:bg-gray-200 text-white rounded-xl px-4 py-2 text-sm font-semibold transition-colors">
                {adding === "repo" ? "…" : "Add"}
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-1.5">Clones &amp; indexes every OpenAPI spec + doc in the repo.</p>
          </div>
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-semibold text-gray-700">From a web link</span>
              <span className="text-[10px] text-gray-400 uppercase tracking-wide">page or PDF</span>
            </div>
            <div className="flex gap-2">
              <input value={webUrl} onChange={e => setWebUrl(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") addSource("weblink", webUrl); }}
                placeholder="https://example.com/spec"
                className="flex-1 min-w-0 border border-gray-200 rounded-xl px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500" />
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
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search documents…"
            className="w-full border border-gray-200 rounded-xl pl-9 pr-4 py-2 text-sm text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500 bg-white" />
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
          {(["all","indexed","processing","failed"] as const).map(f => (
            <button key={f} onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all capitalize ${
                filter === f ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
              }`}>{f}</button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        {loadingList ? (
          <div className="py-16 text-center text-sm text-gray-400">Loading documents…</div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-100">
                {["Document","Status","Chunks","Size","Uploaded",""].map((h, i) => (
                  <th key={i} className={`text-[11px] font-bold text-gray-400 uppercase tracking-widest px-5 py-3.5 ${i === 0 ? "text-left" : "text-center"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {folderGroups.map(g => (
                <Fragment key={g.cat}>
                  <tr className="bg-gray-50/60 hover:bg-gray-100/60 cursor-pointer select-none" onClick={() => toggleCat(g.cat)}>
                    <td colSpan={6} className="px-5 py-2.5">
                      <div className="flex items-center gap-2 text-sm font-semibold text-gray-700">
                        <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform ${collapsedCats.has(g.cat) ? "" : "rotate-90"}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><polyline points="9 18 15 12 9 6"/></svg>
                        <svg className="w-4 h-4 text-amber-500" fill="currentColor" viewBox="0 0 24 24"><path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z"/></svg>
                        {g.cat}
                        <span className="text-xs font-normal text-gray-400">· {g.docs.length} {g.docs.length === 1 ? "source" : "sources"}</span>
                      </div>
                    </td>
                  </tr>
                  {!collapsedCats.has(g.cat) && g.docs.map(doc => (
                    <tr key={doc.file} className="hover:bg-gray-50/70 transition-colors group">
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 bg-red-50 border border-red-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <svg className="w-4 h-4 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/>
                        </svg>
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold text-gray-900 truncate max-w-xs">{doc.name}</span>
                          {doc.type && doc.type !== "file" && (
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200 flex-shrink-0 tracking-wide">
                              {doc.type === "repo" ? "GIT REPO" : "WEB"}
                            </span>
                          )}
                          {doc.category && (
                            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 flex-shrink-0">
                              {doc.category}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-400 font-mono truncate">{doc.url || doc.file}</div>
                        {doc.error && <div className="text-xs text-red-500 mt-0.5">Error: {doc.error}</div>}
                      </div>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-center"><StatusBadge status={doc.status} /></td>
                  <td className="px-5 py-4 text-center">
                    <span className="text-sm font-medium text-gray-700">
                      {doc.chunks > 0 ? doc.chunks.toLocaleString() : "—"}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-center">
                    <span className="text-sm text-gray-500">{doc.size || "—"}</span>
                  </td>
                  <td className="px-5 py-4 text-center">
                    <span className="text-xs text-gray-400">{doc.uploaded || "—"}</span>
                  </td>
                  <td className="px-5 py-4 text-center">
                    <div className="flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      {doc.status === "failed" && (
                        <button onClick={() => retryDoc(doc)} title="Remove failed entry"
                          className="text-amber-500 hover:text-amber-700 transition-colors">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                            <polyline points="1 4 1 10 7 10"/>
                            <path d="M3.51 15a9 9 0 102.13-9.36L1 10"/>
                          </svg>
                        </button>
                      )}
                      {canUpload && doc.status !== "processing" && (
                        <button onClick={() => deleteDoc(doc)} title="Delete document"
                          className="text-gray-400 hover:text-red-600 transition-colors">
                          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6l-1 14H6L5 6m5 0V4h4v2"/>
                          </svg>
                        </button>
                      )}
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
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Knowledge Base</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Pre-indexed spec files · {libSummary.total_files.toLocaleString()} files · {libSummary.total_chunks.toLocaleString()} chunks · read-only
            </p>
          </div>
          <div className="relative">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400"
              fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input value={libSearch} onChange={e => setLibSearch(e.target.value)}
              placeholder="Search specs…"
              className="border border-gray-200 rounded-xl pl-8 pr-3 py-1.5 text-xs text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500 bg-white w-44" />
          </div>
        </div>

        {loadingLib ? (
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm py-10 text-center text-sm text-gray-400">
            Loading knowledge base…
          </div>
        ) : (
          <div className="space-y-2">
            {filteredLibGroups.map(group => (
              <div key={group.id} className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
                <button
                  onClick={() => toggleLib(group.id)}
                  className="w-full flex items-center justify-between px-5 py-3.5 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-7 h-7 bg-blue-50 border border-blue-100 rounded-lg flex items-center justify-center flex-shrink-0">
                      <svg className="w-3.5 h-3.5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
                      </svg>
                    </div>
                    <div className="text-left min-w-0">
                      <span className="text-sm font-semibold text-gray-800">{group.name}</span>
                      <span className="text-xs text-gray-400 ml-2">{group.files} files · {group.chunks.toLocaleString()} chunks</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-3">
                    <span className="text-xs font-semibold bg-green-100 text-green-700 px-2 py-0.5 rounded-full">Indexed</span>
                    <svg className={`w-4 h-4 text-gray-400 transition-transform ${libExpanded.has(group.id) ? "rotate-180" : ""}`}
                      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7"/>
                    </svg>
                  </div>
                </button>

                {libExpanded.has(group.id) && (
                  <div className="border-t border-gray-100">
                    <table className="w-full">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-100">
                          <th className="text-left text-[11px] font-bold text-gray-400 uppercase tracking-widest px-5 py-2">Document</th>
                          <th className="text-center text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-2">Chunks</th>
                          <th className="text-center text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-2">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-50">
                        {group.documents.map(doc => (
                          <tr key={doc.file} className="hover:bg-gray-50/60 transition-colors">
                            <td className="px-5 py-3">
                              <div className="text-sm font-medium text-gray-800 truncate max-w-sm">{doc.name}</div>
                              <div className="text-xs text-gray-400 font-mono truncate">{doc.file}</div>
                            </td>
                            <td className="px-4 py-3 text-center">
                              <span className="text-sm font-medium text-gray-600">{doc.chunks.toLocaleString()}</span>
                            </td>
                            <td className="px-4 py-3 text-center">
                              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2 py-0.5 rounded-full bg-green-100 text-green-700">
                                <span className="w-1.5 h-1.5 rounded-full bg-green-500" />Indexed
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ))}
            {filteredLibGroups.length === 0 && (
              <div className="bg-white rounded-2xl border border-gray-200 shadow-sm py-10 text-center text-sm text-gray-400">
                No spec files match your search.
              </div>
            )}
          </div>
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
        <p className="text-sm text-gray-500">Performance metrics for {indexed.length} indexed document{indexed.length !== 1 ? "s" : ""}</p>
        <div className="flex gap-1 bg-gray-100 rounded-xl p-1">
          {(["7d","30d","90d"] as const).map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                period === p ? "bg-white text-gray-900 shadow-sm" : "text-gray-500 hover:text-gray-700"
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
          <div key={c.label} className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
            <div className={`w-10 h-10 ${c.bg} rounded-xl flex items-center justify-center text-xl mb-3`}>{c.icon}</div>
            <div className={`text-2xl font-bold ${c.color} leading-none`}>{c.value}</div>
            <div className="text-xs text-gray-500 font-medium mt-1">{c.label}</div>
            <div className="text-[11px] text-gray-400">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-sm font-semibold text-gray-900">Document Performance</h2>
          <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
            {(["queries","chunks"] as const).map(s => (
              <button key={s} onClick={() => setSortBy(s)}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  sortBy === s ? "bg-white text-gray-900 shadow-sm" : "text-gray-500"
                }`}>{s === "queries" ? "By queries" : "By chunks"}</button>
            ))}
          </div>
        </div>
        <table className="w-full">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-100">
              <th className="text-left text-[11px] font-bold text-gray-400 uppercase tracking-widest px-6 py-3">Document</th>
              <th className="text-center text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-3">Queries</th>
              <th className="text-left text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-3 w-44">Coverage</th>
              <th className="text-center text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-3">Chunks</th>
              <th className="text-center text-[11px] font-bold text-gray-400 uppercase tracking-widest px-4 py-3">Rank</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {sorted.map((doc, idx) => (
              <tr key={doc.file} className="hover:bg-gray-50/60 transition-colors">
                <td className="px-6 py-4">
                  <div className="text-sm font-semibold text-gray-900">{doc.name}</div>
                  <div className="text-xs text-gray-400 font-mono mt-0.5">{doc.file}</div>
                </td>
                <td className="px-4 py-4 text-center">
                  <span className="text-sm font-bold text-gray-900">{doc.queries.toLocaleString()}</span>
                </td>
                <td className="px-4 py-4"><RelevanceBar value={doc.relevance} /></td>
                <td className="px-4 py-4 text-center">
                  <span className="text-sm text-gray-600">{doc.chunks.toLocaleString()}</span>
                </td>
                <td className="px-4 py-4 text-center">
                  <span className={`text-xs font-bold w-6 h-6 rounded-full inline-flex items-center justify-center ${
                    idx === 0 ? "bg-amber-100 text-amber-700" :
                    idx === 1 ? "bg-gray-100 text-gray-600" :
                    idx === 2 ? "bg-orange-100 text-orange-600" : "bg-gray-50 text-gray-400"
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
        <header className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200 flex-shrink-0">
          <div>
            <h1 className="text-base font-semibold text-gray-900">Documents</h1>
            <p className="text-xs text-gray-400 mt-0.5">Manage your knowledge base and monitor performance</p>
          </div>
        </header>

        <div className="flex border-b border-gray-200 bg-white px-6 flex-shrink-0">
          {tabs.map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`px-5 py-3.5 text-sm font-medium border-b-2 transition-all -mb-px ${
                tab === t.id ? "border-red-600 text-red-600" : "border-transparent text-gray-500 hover:text-gray-800"
              }`}>{t.label}</button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto bg-gray-50">
          <div className="max-w-6xl mx-auto px-6 py-8">
            {tab === "management"  && <ManagementTab user={user} />}
            {tab === "performance" && <PerformanceTab />}
          </div>
        </div>
      </div>
    </AppShell>
  );
}
