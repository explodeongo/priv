"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import AppShell from "./components/AppShell";
import { useBranding } from "./components/BrandingContext";
import { useConvos } from "./components/ConversationContext";
import { loadPrefs } from "./settings/page";
import { WelcomeModal, CoverageStrip, type Coverage } from "./components/Welcome";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// Auth header for per-user conversation history endpoints.
function authH(json = false): Record<string, string> {
  const t = typeof window !== "undefined" ? localStorage.getItem("synaptdi_token") : null;
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

interface Convo { id: string; title: string; count: number; updated: number; }

interface Source {
  name: string;
  file: string;
  chunk: number;
  preview: string;
  url?: string;
  upload?: boolean;
  origin_type?: string;   // "" = bundled KB · "repo" · "web" · "file"
  domain?: string;        // KB domain (TM Forum / ODA / MEF / …) when origin_type === ""
}

// Trust tier for a citation — drives the badge icon, colour and label.
function sourceTier(s: Source): { label: string; cls: string; dot: string; icon: React.ReactNode } {
  const ot = s.origin_type;
  if (ot === "repo") return {
    label: "GitHub repository", cls: "text-violet-600 dark:text-violet-400", dot: "bg-violet-500",
    icon: <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.58 2 12.25c0 4.53 2.87 8.37 6.84 9.73.5.1.68-.22.68-.49l-.01-1.9c-2.78.62-3.37-1.2-3.37-1.2-.46-1.18-1.11-1.5-1.11-1.5-.91-.64.07-.62.07-.62 1 .07 1.53 1.06 1.53 1.06.9 1.56 2.36 1.11 2.94.85.09-.66.35-1.11.63-1.36-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.27 2.75 1.05a9.4 9.4 0 015 0c1.91-1.32 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.94-2.34 4.81-4.57 5.06.36.32.68.94.68 1.9l-.01 2.81c0 .27.18.6.69.49A10.03 10.03 0 0022 12.25C22 6.58 17.52 2 12 2z"/></svg>,
  };
  if (ot === "web") return {
    label: "Web page", cls: "text-sky-600 dark:text-sky-400", dot: "bg-sky-500",
    icon: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><path strokeLinecap="round" d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18" /></svg>,
  };
  if (ot === "file") return {
    label: "Internal upload", cls: "text-amber-600 dark:text-amber-400", dot: "bg-amber-500",
    icon: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>,
  };
  return {
    label: `Official${s.domain ? " · " + s.domain : ""}`, cls: "text-emerald-600 dark:text-emerald-400", dot: "bg-emerald-500",
    icon: <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>,
  };
}

interface Conf { level?: string; score?: number; strong?: number }
interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  latency_ms?: number;
  error?: boolean;
  cached?: boolean;
  confidence?: Conf;
}

// Small grounding-strength meter shown next to an answer's sources.
function ConfidenceBadge({ c }: { c?: Conf }) {
  if (!c || !c.level) return null;
  const map: Record<string, { label: string; cls: string; bars: number }> = {
    high:   { label: "High confidence",   cls: "text-emerald-600 dark:text-emerald-400", bars: 3 },
    medium: { label: "Medium confidence", cls: "text-amber-600 dark:text-amber-400",     bars: 2 },
    low:    { label: "Limited grounding",  cls: "text-gray-400 dark:text-slate-500",      bars: 1 },
  };
  const m = map[c.level] || map.low;
  const title = `${m.label}${c.strong ? ` · ${c.strong} strong match${c.strong === 1 ? "" : "es"}` : ""}`;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${m.cls}`} title={title}>
      <span className="flex items-end gap-0.5" aria-hidden>
        {[1, 2, 3].map(i => (
          <span key={i} className={`w-1 rounded-sm ${i <= m.bars ? "bg-current" : "bg-gray-200 dark:bg-slate-700"}`} style={{ height: `${i * 3 + 2}px` }} />
        ))}
      </span>
      {m.label}
    </span>
  );
}

const SUGGESTED = [
  "What mandatory fields does TMF622 Product Order require?",
  "What is the difference between TMF620 and TMF633?",
  "How do I handle pagination in TM Forum Open APIs?",
  "Which ODA component handles trouble tickets?",
  "How do I create a service order with TMF641?",
  "What is the SID ABE for customer data?",
];

// Strip markdown syntax from plain text
function stripMd(text: string) {
  return text.replace(/\*\*/g, "").replace(/`/g, "").replace(/#{1,3}\s/g, "").trim();
}

// Render answer markdown (handles fenced ``` code blocks, headings, bullets, inline code/bold)
function renderMarkdown(text: string, sources: Source[] = [], onCite?: (n: number) => void) {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let key = 0;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block ```
    if (line.trim().startsWith("```")) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) { code.push(lines[i]); i++; }
      i++; // skip closing fence
      nodes.push(
        <pre key={key++} className="my-2 bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto text-xs font-mono leading-relaxed">
          <code>{code.join("\n")}</code>
        </pre>
      );
      continue;
    }

    // Markdown table: header row + |---| separator + body rows
    if (line.includes("|") && i + 1 < lines.length &&
        /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const parseRow = (l: string) => l.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const header = parseRow(line);
      i += 2; // skip header + separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) { rows.push(parseRow(lines[i])); i++; }
      nodes.push(
        <div key={key++} className="my-2 overflow-x-auto">
          <table className="text-xs border-collapse">
            <thead>
              <tr>{header.map((h, hi) => (
                <th key={hi} className="border border-gray-200 dark:border-slate-700 bg-gray-50 dark:bg-slate-800 px-2.5 py-1.5 text-left font-semibold text-gray-700 dark:text-slate-200 whitespace-nowrap">{inlineFormat(h, sources, onCite)}</th>
              ))}</tr>
            </thead>
            <tbody>
              {rows.map((r, ri) => (
                <tr key={ri}>{r.map((c, ci) => (
                  <td key={ci} className="border border-gray-200 px-2.5 py-1.5 text-gray-700 align-top dark:border-slate-700 dark:text-slate-300">{inlineFormat(c, sources, onCite)}</td>
                ))}</tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      continue;
    }

    if (!line.trim()) { nodes.push(<div key={key++} className="h-2" />); i++; continue; }

    if (line.startsWith("## ") || line.startsWith("### ")) {
      nodes.push(<p key={key++} className="font-semibold text-gray-900 dark:text-slate-100 mt-3 mb-1">{line.replace(/^#{2,3}\s/, "")}</p>);
    } else if (line.match(/^[\*\-\+]\s/)) {
      nodes.push(
        <div key={key++} className="flex gap-2 my-0.5 ml-1">
          <span className="text-gray-400 dark:text-slate-500 flex-shrink-0 mt-0.5">•</span>
          <span>{inlineFormat(line.slice(2), sources, onCite)}</span>
        </div>
      );
    } else if (line.match(/^\s{2,}[\+\-\*]\s/)) {
      nodes.push(
        <div key={key++} className="flex gap-2 my-0.5 ml-6">
          <span className="text-gray-400 flex-shrink-0">◦</span>
          <span>{inlineFormat(line.replace(/^\s+[\+\-\*]\s/, ""), sources, onCite)}</span>
        </div>
      );
    } else {
      nodes.push(<p key={key++} className="my-0.5 leading-relaxed">{inlineFormat(line, sources, onCite)}</p>);
    }
    i++;
  }
  return nodes;
}

function inlineFormat(text: string, sources: Source[] = [], onCite?: (n: number) => void): React.ReactNode {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\[(?:Sources?\s+)?\d+(?:\s*,\s*\d+)*\])/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`"))
      return <code key={i} className="bg-gray-100 dark:bg-slate-700 text-red-700 dark:text-red-300 font-mono text-xs px-1.5 py-0.5 rounded">{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**"))
      return <strong key={i} className="font-semibold text-gray-900 dark:text-slate-100">{part.slice(2, -2)}</strong>;
    const cite = part.match(/^\[(?:Sources?\s+)?(\d+(?:\s*,\s*\d+)*)\]$/);
    if (cite) {
      const nums = cite[1].split(",").map(s => parseInt(s.trim(), 10));
      return (
        <span key={i} className="inline-flex gap-0.5 align-super mx-0.5">
          {nums.map((n, j) => {
            const src = sources[n - 1];
            if (!src) return <span key={j} className="text-[10px] text-gray-400">[{n}]</span>;
            return (
              <span key={j} className="relative group/cite inline-block">
                <button onClick={() => onCite?.(n)}
                  className="text-[10px] font-semibold text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/15 hover:bg-red-100 dark:hover:bg-red-500/25 border border-red-200 dark:border-red-500/30 rounded px-1 leading-tight transition-colors">
                  {n}
                </button>
                <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 z-50 w-72 opacity-0 group-hover/cite:opacity-100 transition-opacity duration-150">
                  <span className="block rounded-lg bg-slate-900 dark:bg-slate-800 border border-slate-700 shadow-xl p-2.5 text-left">
                    <span className="block text-[11px] font-semibold text-red-300 mb-1 truncate" style={{ textTransform: "none" }}>{stripMd(src.name)}{src.file ? ` · ${src.file}` : ""}</span>
                    <span className="block text-[11px] font-normal text-slate-300 leading-relaxed line-clamp-4" style={{ whiteSpace: "normal", textTransform: "none" }}>{src.preview}</span>
                  </span>
                </span>
              </span>
            );
          })}
        </span>
      );
    }
    return part;
  });
}

// Source Drawer
function SourceDrawer({ source, onClose }: { source: Source; onClose: () => void }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const cleanName = stripMd(source.name);
  const tier = sourceTier(source);

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 h-full w-full max-w-lg bg-white dark:bg-slate-900 z-50 shadow-2xl flex flex-col"
           style={{ animation: "slideIn 0.2s ease-out" }}>
        <style>{`@keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }`}</style>

        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-gray-100 dark:border-slate-800 bg-gray-50 dark:bg-slate-800/50">
          <div className="flex-1 min-w-0 pr-3">
            <div className="flex items-center gap-2 mb-1.5">
              <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2 py-0.5 rounded-full bg-gray-100 dark:bg-slate-800 ${tier.cls}`}>
                {tier.icon}{tier.label}
              </span>
            </div>
            <h3 className="font-semibold text-gray-900 dark:text-slate-100 text-sm leading-snug">{cleanName}</h3>
            <p className="text-xs text-gray-400 mt-1 font-mono">{source.file} · chunk {source.chunk}</p>
          </div>
          <button onClick={onClose}
            className="w-7 h-7 rounded-full hover:bg-gray-200 dark:hover:bg-slate-700 flex items-center justify-center text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 transition-colors flex-shrink-0 text-lg">
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Link to actual source */}
          {source.url ? (
            <a href={source.url} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-3 p-3.5 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 hover:border-red-300 dark:hover:border-red-500/40 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-xl transition-all group">
              <div className="w-8 h-8 bg-gray-100 group-hover:bg-red-100 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors">
                <svg className="w-4 h-4 text-gray-500 group-hover:text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-700 dark:text-slate-200 group-hover:text-red-700 dark:group-hover:text-red-400 transition-colors">View on GitHub</p>
                <p className="text-xs text-gray-400 truncate">{source.url.replace("https://github.com/", "")}</p>
              </div>
              <svg className="w-4 h-4 text-gray-300 group-hover:text-red-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </a>
          ) : (
            <div className="flex items-center gap-3 p-3.5 bg-gray-50 dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl">
              <div className="w-8 h-8 bg-gray-100 rounded-lg flex items-center justify-center flex-shrink-0">
                <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-600">TM Forum Member Portal</p>
                <p className="text-xs text-gray-400">Available at tmforum.org (member access required)</p>
              </div>
            </div>
          )}

          {/* Retrieved chunk */}
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-2">Retrieved Chunk</p>
            <div className="bg-gray-50 dark:bg-slate-800 rounded-xl p-4 border border-gray-100 dark:border-slate-700">
              <pre className="text-xs text-gray-700 dark:text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">{source.preview}</pre>
            </div>
            <p className="text-xs text-gray-400 mt-2 text-center">Retrieved via semantic similarity search · nomic-embed-text</p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-100 dark:border-slate-800 bg-gray-50 dark:bg-slate-800/50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="bg-red-600 text-white text-xs px-2 py-0.5 rounded font-bold">SynaptDI</span>
            <span className="text-xs text-gray-400">Synapt Domain Intelligence</span>
          </div>
          <button onClick={onClose} className="text-xs text-gray-400 hover:text-gray-600 transition-colors">Close</button>
        </div>
      </div>
    </>
  );
}

// Main
export default function Home() {
  const { branding } = useBranding();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const [stats, setStats]       = useState<{ chunks_indexed?: number } | null>(null);
  const [activeSource, setActiveSource] = useState<Source | null>(null);
  const [prefs, setPrefs] = useState({ topK: 5, showSrc: true });
  const [logo, setLogo] = useState<string | undefined>();
  const [scope, setScope] = useState<"all" | "kb" | "docs">("all");
  const [mode, setMode]   = useState<"deep" | "fast">("deep");
  const [chatCfg, setChatCfg] = useState<{ placeholder: string; suggestions: string[] }>({
    placeholder: "Ask about TM Forum APIs, ODA, eTOM, SID...", suggestions: SUGGESTED,
  });
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [feedbackIdx, setFeedbackIdx] = useState<Record<number, string>>({});
  const [trace, setTrace] = useState<{ specs: string[]; sources: string[] } | null>(null);
  const [followups, setFollowups] = useState<string[]>([]);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [showWelcome, setShowWelcome] = useState(false);
  const { activeId, setActiveId, refresh: refreshConvos, loadSignal, consume } = useConvos();
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);
  const abortRef  = useRef<AbortController | null>(null);
  const stoppedRef = useRef(false);

  // React to the sidebar: open a saved chat, or clear for a new one.
  useEffect(() => {
    if (!loadSignal) return;
    setFollowups([]); setTrace(null);
    if (loadSignal.kind === "new") {
      setMessages([]); inputRef.current?.focus();
    } else if (loadSignal.kind === "open") {
      fetch(`${API}/conversations/${loadSignal.id}`, { headers: authH() })
        .then(r => (r.ok ? r.json() : null))
        .then(c => { if (c) setMessages(c.messages || []); })
        .catch(() => {});
    }
    consume();
  }, [loadSignal, consume]);

  const persistConvo = async (msgs: Message[]) => {
    if (typeof window !== "undefined" && !localStorage.getItem("synaptdi_token")) return;
    const title = (msgs.find(m => m.role === "user")?.content || "New chat").slice(0, 60);
    try {
      if (activeId) {
        await fetch(`${API}/conversations/${activeId}`, {
          method: "PUT", headers: authH(true), body: JSON.stringify({ messages: msgs, title }) });
      } else {
        const r = await fetch(`${API}/conversations`, {
          method: "POST", headers: authH(true), body: JSON.stringify({ messages: msgs, title }) });
        if (r.ok) setActiveId((await r.json()).id);
      }
      refreshConvos();
    } catch {}
  };

  useEffect(() => {
    fetch(`${API}/stats`).then(r => r.json()).then(setStats).catch(() => {});
    fetch(`${API}/chat-config`).then(r => r.json())
      .then(c => setChatCfg({ placeholder: c.placeholder || "Ask a question…",
                              suggestions: (c.suggestions?.length ? c.suggestions : SUGGESTED) }))
      .catch(() => {});
    const p = loadPrefs();
    setPrefs({ topK: p.topK, showSrc: p.showSrc });
    try { const l = localStorage.getItem("synaptdi_logo"); if (l) setLogo(l); } catch {}
    fetch(`${API}/coverage`).then(r => r.json()).then(setCoverage).catch(() => {});
    try { if (!localStorage.getItem("synaptdi_welcomed")) setShowWelcome(true); } catch {}
    try { const m = localStorage.getItem("synaptdi_mode"); if (m === "fast" || m === "deep") setMode(m); } catch {}
  }, []);

  const firstLetter = (branding.companyName || "S")[0].toUpperCase();

  // Deep-link from the document reader: /?ask=<question>&scope=<all|kb|docs>
  useEffect(() => {
    try {
      const p = new URLSearchParams(window.location.search);
      const ask = p.get("ask");
      if (!ask) return;
      setInput(ask);
      const sc = p.get("scope");
      if (sc === "kb" || sc === "docs" || sc === "all") setScope(sc);
      window.history.replaceState({}, "", window.location.pathname);   // don't re-fire on refresh
      setTimeout(() => { const el = inputRef.current; if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }, 80);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Core streaming routine — `prior` is the explicit message history (so it works
  // for both a new question and a regenerate without stale-closure issues).
  const runStream = useCallback(async (question: string, prior: Message[], fresh = false) => {
    setLoading(true);
    stoppedRef.current = false;
    setTrace(null); setFollowups([]);
    const controller = new AbortController();
    abortRef.current = controller;
    // Idle timeout: abort only if the stream goes SILENT this long. It resets on
    // every chunk, so a slow-but-working answer — or a cold model load on a weak
    // PC — never gets killed mid-generation; only a truly stuck request fails.
    const IDLE_MS = 300000;
    let timeout = setTimeout(() => controller.abort(), IDLE_MS);
    const bump = () => { clearTimeout(timeout); timeout = setTimeout(() => controller.abort(), IDLE_MS); };
    const history = prior.filter(m => m.content && !m.error)
                         .slice(-6).map(m => ({ role: m.role, content: m.content }));

    const setLast = (patch: Partial<Message>) => setMessages(prev => {
      const copy = [...prev];
      const i = copy.length - 1;
      if (i >= 0 && copy[i].role === "assistant") copy[i] = { ...copy[i], ...patch };
      return copy;
    });
    let acc = "";
    let hadError = false;
    let doneSources: Source[] | undefined;
    let doneLatency: number | undefined;
    let doneConfidence: Conf | undefined;
    let lastFlush = 0;   // throttle markdown re-renders during streaming (perf on slower CPUs)
    const save = () => persistConvo([...prior,
      { role: "user", content: question },
      { role: "assistant", content: acc, sources: doneSources, latency_ms: doneLatency, confidence: doneConfidence }]);

    try {
      const res = await fetch(`${API}/query/stream`, {
        method: "POST",
        headers: authH(true),
        body: JSON.stringify({ question, top_k: prefs.topK, scope, history, mode, no_cache: fresh }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) throw new Error(`API error ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        bump();                                   // data is flowing — reset the idle timer
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          let evt: any;
          try { evt = JSON.parse(line); } catch { continue; }
          if (evt.type === "context")    { setTrace({ specs: evt.specs || [], sources: evt.sources || [] }); }
          else if (evt.type === "token") { acc += evt.text; const now = Date.now(); if (now - lastFlush > 66) { lastFlush = now; setLast({ content: acc }); } }
          else if (evt.type === "done")  { doneSources = evt.sources; doneLatency = evt.latency_ms; doneConfidence = evt.confidence; setLast({ content: acc, sources: evt.sources, latency_ms: evt.latency_ms, cached: !!evt.cached, confidence: evt.confidence }); }
          else if (evt.type === "error") { acc = evt.text; hadError = true; setLast({ content: acc, error: true }); }
        }
      }
      save();
      // Suggest related questions (async; never blocks the answer).
      if (acc && !hadError && !acc.toLowerCase().startsWith("i don't have enough")) {
        fetch(`${API}/followups`, { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question, answer: acc }) })
          .then(r => (r.ok ? r.json() : null))
          .then(d => { if (d && Array.isArray(d.questions)) setFollowups(d.questions.slice(0, 3)); })
          .catch(() => {});
      }
    } catch (e: any) {
      if (e.name === "AbortError" && stoppedRef.current) {
        setLast({ content: acc ? acc + "\n\n_(stopped)_" : "_(stopped)_" });
        if (acc) save();
      } else if (e.name === "AbortError" || e.name === "TimeoutError") {
        setLast({ content: "The model went quiet for too long — on a slower PC it may still be loading. Try **Fast** mode (next to the scope buttons), or ask again in a moment.", error: true });
      } else {
        setLast({ content: "Couldn't reach SynaptDI just now — the server may be starting up or restarting. It reconnects automatically; please try your question again in a moment.", error: true });
      }
    } finally {
      clearTimeout(timeout);
      abortRef.current = null;
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [scope, mode, prefs, activeId]);

  const ask = useCallback((question: string) => {
    if (!question.trim() || loading) return;
    setInput("");
    const prior = messages;
    setMessages(prev => [...prev, { role: "user", content: question }, { role: "assistant", content: "" }]);
    runStream(question, prior);
  }, [loading, messages, runStream]);

  const regenerate = useCallback(() => {
    if (loading) return;
    let idx = -1;
    for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "user") { idx = i; break; }
    if (idx < 0) return;
    const q = messages[idx].content;
    const base = messages.slice(0, idx);
    setMessages([...base, { role: "user", content: q }, { role: "assistant", content: "" }]);
    runStream(q, base, true);   // Regenerate → force a fresh answer, skip the cache
  }, [loading, messages, runStream]);

  const stop = () => { stoppedRef.current = true; abortRef.current?.abort(); };

  // Keyboard: "/" focuses the composer, Esc stops generation.
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const typing = !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
      if (e.key === "/" && !typing) { e.preventDefault(); inputRef.current?.focus(); }
      else if (e.key === "Escape" && loading) { e.preventDefault(); stop(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [loading]);

  const copyMsg = (i: number, text: string) => {
    try { navigator.clipboard?.writeText(stripMd(text)); setCopiedIdx(i); setTimeout(() => setCopiedIdx(null), 1500); } catch {}
  };

  // Export the whole conversation as clean Markdown (for Teams / email / Confluence).
  const exportConversation = () => {
    if (!messages.length) return;
    const ts = new Date();
    const out: string[] = ["# SynaptDI conversation", `_Exported ${ts.toLocaleString()}_`, ""];
    messages.forEach(m => {
      if (m.role === "user") { out.push("## You", "", m.content, ""); return; }
      out.push("## SynaptDI", "", m.content || "_(no answer)_", "");
      if (m.sources?.length) {
        out.push("**Sources:** " + m.sources.map(s => s.url ? `[${stripMd(s.name)}](${s.url})` : stripMd(s.name)).join(" · "), "");
      }
      out.push("---", "");
    });
    const blob = new Blob([out.join("\n")], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `synaptdi-chat-${ts.toISOString().slice(0, 10)}.md`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  };

  const sendFeedback = (i: number, rating: "up" | "down") => {
    const q = i > 0 && messages[i - 1]?.role === "user" ? messages[i - 1].content : "";
    const sources = (messages[i].sources || []).map(s => s.name);
    fetch(`${API}/feedback`, { method: "POST", headers: authH(true), body: JSON.stringify({ rating, question: q, sources }) }).catch(() => {});
    setFeedbackIdx(prev => ({ ...prev, [i]: rating }));
  };

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); }
  }

  return (
    <AppShell>
      <div className="flex flex-col h-full bg-white dark:bg-slate-950">

        {/* Header */}
        <header className="flex items-center justify-between px-6 py-3 bg-white dark:bg-slate-900 border-b border-gray-200 dark:border-slate-800 shadow-sm flex-shrink-0 z-10">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-gray-800 dark:text-slate-100 text-sm tracking-tight">Chat</span>
            {stats?.chunks_indexed != null && (
              <span className="text-xs text-gray-400 dark:text-slate-400 bg-gray-100 dark:bg-slate-800 px-2.5 py-1 rounded-full hidden sm:inline-block">
                {stats.chunks_indexed.toLocaleString()} chunks indexed
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {messages.length > 0 && (
              <button onClick={exportConversation} title="Export this conversation as Markdown"
                className="text-xs text-gray-400 hover:text-gray-600 dark:text-slate-500 dark:hover:text-slate-300 px-2.5 py-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                Export
              </button>
            )}
            {messages.length > 0 && (
              <button onClick={() => setMessages([])}
                className="text-xs text-gray-400 hover:text-gray-600 dark:text-slate-500 dark:hover:text-slate-300 px-2.5 py-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors">
                Clear chat
              </button>
            )}
            <div className="w-2 h-2 rounded-full bg-green-500" title="Connected" />
          </div>
        </header>

        {/* Chat */}
        <main className="flex-1 overflow-y-auto px-4 py-6">
          <div className="max-w-3xl mx-auto">

            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center min-h-[60vh] gap-7 text-center" style={{ animation: "fadeUp 0.35s ease-out" }}>
                <style>{`@keyframes fadeUp { from { opacity:0; transform:translateY(12px); } to { opacity:1; transform:translateY(0); } }`}</style>
                <div className="flex flex-col items-center gap-3">
                  {logo ? (
                    <img src={logo} alt="Logo"
                      className="w-14 h-14 rounded-2xl object-contain shadow-lg mb-1 bg-white border border-gray-100" />
                  ) : (
                    <div className="w-14 h-14 rounded-2xl flex items-center justify-center shadow-lg mb-1"
                      style={{ backgroundColor: branding.primaryColor, boxShadow: `0 10px 25px -5px ${branding.primaryColor}40` }}>
                      <span className="text-white font-extrabold text-2xl select-none">{firstLetter}</span>
                    </div>
                  )}
                  <div>
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">What would you like to know?</h2>
                    <p className="text-gray-400 text-sm mt-1">{branding.tagline}</p>
                  </div>
                  {stats?.chunks_indexed != null && (
                    <div className="flex items-center gap-1.5 text-xs text-gray-400 dark:text-slate-400 bg-gray-50 dark:bg-slate-800/60 border border-gray-200 dark:border-slate-700 px-3 py-1.5 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                      {stats.chunks_indexed.toLocaleString()} chunks indexed and ready
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-2xl">
                  <p className="col-span-full text-xs font-semibold text-gray-400 uppercase tracking-wider text-center mb-0.5">Popular questions</p>
                  {chatCfg.suggestions.map((q, i) => (
                    <button key={i} onClick={() => ask(q)}
                      className="text-left text-sm text-gray-600 dark:text-slate-300 bg-white dark:bg-slate-900 hover:bg-red-50 dark:hover:bg-slate-800 hover:text-red-700 dark:hover:text-red-300 border border-gray-200 dark:border-slate-700 hover:border-red-200 dark:hover:border-slate-600 hover:shadow-sm rounded-xl px-4 py-3.5 transition-all">
                      <span className="text-red-500 mr-2 text-xs">→</span>{q}
                    </button>
                  ))}
                </div>
                <CoverageStrip coverage={coverage} />
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`mb-6 flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                {msg.role === "assistant" && (
                  logo ? (
                    <img src={logo} alt="Logo"
                      className="w-8 h-8 rounded-full object-contain mr-3 mt-0.5 flex-shrink-0 shadow-sm bg-white border border-gray-100" />
                  ) : (
                    <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold mr-3 mt-0.5 flex-shrink-0 shadow-sm"
                      style={{ backgroundColor: branding.primaryColor }}>
                      {firstLetter}
                    </div>
                  )
                )}
                <div className="max-w-2xl min-w-0">
                  <div className={`rounded-2xl px-5 py-4 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "bg-red-600 text-white rounded-tr-sm"
                      : msg.error
                      ? "bg-red-50 dark:bg-red-950/40 text-red-800 dark:text-red-300 border border-red-200 dark:border-red-900/50 rounded-tl-sm"
                      : "bg-gray-50 dark:bg-slate-800 text-gray-800 dark:text-slate-100 border border-gray-100 dark:border-slate-700 rounded-tl-sm"
                  }`}>
                    {msg.role === "assistant" && !msg.error
                      ? (msg.content
                          ? renderMarkdown(msg.content, msg.sources || [], (n) => { const s = (msg.sources || [])[n - 1]; if (s) setActiveSource(s); })
                          : (
                            <div className="space-y-2.5 py-0.5 min-w-[240px]">
                              {trace && (trace.specs.length > 0 || trace.sources.length > 0) && (
                                <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-slate-400 mb-1">
                                  <svg className="w-3.5 h-3.5 animate-spin text-red-500" viewBox="0 0 24 24" fill="none">
                                    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="3" strokeOpacity="0.25" />
                                    <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                                  </svg>
                                  <span>Searching {(trace.specs.length ? trace.specs : trace.sources).slice(0, 4).map(stripMd).join(", ")}{(trace.specs.length ? trace.specs : trace.sources).length > 4 ? "…" : ""}</span>
                                </div>
                              )}
                              <div className="skeleton h-3 w-[92%]" />
                              <div className="skeleton h-3 w-[78%]" />
                              <div className="skeleton h-3 w-[55%]" />
                            </div>
                          ))
                      : <span>{msg.content}</span>}
                  </div>

                  {prefs.showSrc && msg.sources && msg.sources.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-2 items-center">
                      {msg.confidence?.level && (
                        <>
                          <ConfidenceBadge c={msg.confidence} />
                          <span className="text-gray-300 dark:text-slate-600">·</span>
                        </>
                      )}
                      <span className="text-xs text-gray-400 font-medium">Sources:</span>
                      {msg.sources.map((src, si) => {
                        const tier = sourceTier(src);
                        return (
                        <span key={si} className="inline-flex items-center">
                          {src.url ? (
                            <>
                              <a href={src.url} target="_blank" rel="noopener noreferrer" title={`${tier.label} — open source`}
                                className="group flex items-center gap-1.5 text-xs bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 text-gray-500 dark:text-slate-300 hover:text-red-600 dark:hover:text-red-400 hover:border-red-300 dark:hover:border-red-500/40 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-l-full pl-2.5 pr-3 py-1 transition-all">
                                <span className={`flex-shrink-0 ${tier.cls}`}>{tier.icon}</span>
                                {stripMd(src.name)}
                                <svg className="w-3 h-3 text-gray-300 group-hover:text-red-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
                              </a>
                              <button onClick={() => setActiveSource(src)} title="View the exact chunk"
                                className="inline-flex items-center text-xs bg-white dark:bg-slate-800 border border-l-0 border-gray-200 dark:border-slate-700 text-gray-400 dark:text-slate-400 hover:text-red-600 dark:hover:text-red-400 hover:border-red-300 dark:hover:border-red-500/40 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-r-full px-2 py-1 transition-all">
                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /><path strokeLinecap="round" strokeLinejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" /></svg>
                              </button>
                            </>
                          ) : (
                            <button onClick={() => setActiveSource(src)} title={`${tier.label} — view the exact chunk`}
                              className="group flex items-center gap-1.5 text-xs bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 text-gray-500 dark:text-slate-300 hover:text-red-600 dark:hover:text-red-400 hover:border-red-300 dark:hover:border-red-500/40 hover:bg-red-50 dark:hover:bg-red-500/10 rounded-full pl-2.5 pr-3 py-1 transition-all">
                              <span className={`flex-shrink-0 ${tier.cls}`}>{tier.icon}</span>
                              {stripMd(src.name)}
                            </button>
                          )}
                        </span>
                      );})}
                      {msg.cached ? (
                        <span className="inline-flex items-center gap-1 text-xs text-amber-500 ml-1" title="Served from the answer cache">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><path d="M13 2L4.5 13.5H11l-1 8.5 8.5-11.5H12l1-8.5z" /></svg>instant
                        </span>
                      ) : msg.latency_ms ? (
                        <span className="text-xs text-gray-300 ml-1">{(msg.latency_ms / 1000).toFixed(1)}s</span>
                      ) : null}
                    </div>
                  )}

                  {msg.role === "assistant" && !msg.error && msg.content && (
                    <div className="mt-2 flex items-center gap-1">
                      <button onClick={() => copyMsg(i, msg.content)} title="Copy answer"
                        className="text-xs text-gray-400 hover:text-gray-700 dark:text-slate-500 dark:hover:text-slate-200 px-1.5 py-1 rounded hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors flex items-center gap-1">
                        {copiedIdx === i ? (
                          <><svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>Copied</>
                        ) : (
                          <><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>Copy</>
                        )}
                      </button>
                      {i === messages.length - 1 && !loading && (
                        <button onClick={regenerate} title="Regenerate answer"
                          className="text-xs text-gray-400 hover:text-gray-700 dark:text-slate-500 dark:hover:text-slate-200 px-1.5 py-1 rounded hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors flex items-center gap-1">
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>Regenerate
                        </button>
                      )}
                      <span className="mx-1 w-px h-3.5 bg-gray-200 dark:bg-slate-700" />
                      <button onClick={() => sendFeedback(i, "up")} title="Helpful"
                        className={`p-1 rounded hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors ${feedbackIdx[i] === "up" ? "text-emerald-500" : "text-gray-400 hover:text-gray-600 dark:text-slate-500 dark:hover:text-slate-300"}`}>
                        <svg className="w-3.5 h-3.5" fill={feedbackIdx[i] === "up" ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3zM7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3" /></svg>
                      </button>
                      <button onClick={() => sendFeedback(i, "down")} title="Not helpful"
                        className={`p-1 rounded hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors ${feedbackIdx[i] === "down" ? "text-red-500" : "text-gray-400 hover:text-gray-600 dark:text-slate-500 dark:hover:text-slate-300"}`}>
                        <svg className="w-3.5 h-3.5" fill={feedbackIdx[i] === "down" ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3zm7-13h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17" /></svg>
                      </button>
                    </div>
                  )}

                  {msg.role === "assistant" && !msg.error && msg.content && i === messages.length - 1 && !loading && followups.length > 0 && (
                    <div className="mt-3.5">
                      <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1.5">Related</p>
                      <div className="flex flex-col gap-1.5">
                        {followups.map((fq, fi) => (
                          <button key={fi} onClick={() => ask(fq)}
                            className="group text-left text-sm text-gray-600 dark:text-slate-300 bg-white dark:bg-slate-800 hover:bg-red-50 dark:hover:bg-slate-700 hover:text-red-700 dark:hover:text-red-300 border border-gray-200 dark:border-slate-700 hover:border-red-200 dark:hover:border-slate-600 hover:shadow-sm rounded-lg px-3.5 py-2.5 transition-all flex items-center gap-2.5">
                            <span className="text-red-400 group-hover:text-red-500 font-medium flex-shrink-0">+</span>
                            <span className="flex-1">{fq}</span>
                            <span className="text-gray-300 group-hover:text-red-400 flex-shrink-0">→</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            <div ref={bottomRef} />
          </div>
        </main>

        {/* Input */}
        <div className="border-t border-gray-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-4 flex-shrink-0">
          <div className="max-w-3xl mx-auto mb-2 flex items-center gap-1.5">
            <span className="text-xs text-gray-400 mr-0.5">Search:</span>
            {([["all", "Everything"], ["kb", "Knowledge Base"], ["docs", "My Documents"]] as const).map(([v, label]) => (
              <button key={v} onClick={() => setScope(v)} type="button"
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                  scope === v
                    ? "bg-red-600 text-white border-red-600"
                    : "bg-white dark:bg-slate-800 text-gray-500 dark:text-slate-400 border-gray-200 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-700"
                }`}>
                {label}
              </button>
            ))}
            <span className="flex-1" />
            <button type="button" onClick={() => setMode(m => { const n = m === "deep" ? "fast" : "deep"; try { localStorage.setItem("synaptdi_mode", n); } catch {} return n; })}
              title={mode === "deep" ? "Deep: full 8B model — best quality" : "Fast: small model — quick lookups"}
              className={`text-xs px-2.5 py-1 rounded-full border transition-colors flex items-center gap-1 ${
                mode === "fast"
                  ? "bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-500/40"
                  : "bg-white dark:bg-slate-800 text-gray-500 dark:text-slate-400 border-gray-200 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-700"
              }`}>
              {mode === "fast" ? (
                <><svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24"><path d="M13 2L4.5 13.5H11l-1 8.5 8.5-11.5H12l1-8.5z" /></svg>Fast</>
              ) : (
                <><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m6-15l2.5 6.5L21 13l-6.5 2.5L12 22l-2.5-6.5L3 13l6.5-2.5L12 2z" /></svg>Deep</>
              )}
            </button>
          </div>
          <div className="max-w-3xl mx-auto flex items-end gap-3">
            <textarea ref={inputRef} value={input}
              onChange={e => setInput(e.target.value)} onKeyDown={handleKey}
              placeholder={chatCfg.placeholder} rows={1} disabled={loading}
              className="flex-1 resize-none border border-gray-200 dark:border-slate-700 rounded-xl px-4 py-3 text-sm text-gray-800 dark:text-slate-100 placeholder-gray-400 dark:placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent bg-gray-50 dark:bg-slate-800 disabled:opacity-50"
              style={{ maxHeight: "120px" }}
              onInput={e => {
                const t = e.target as HTMLTextAreaElement;
                t.style.height = "auto";
                t.style.height = Math.min(t.scrollHeight, 120) + "px";
              }}
            />
            {loading ? (
              <button onClick={stop} title="Stop generating"
                className="flex-shrink-0 bg-gray-800 hover:bg-gray-900 text-white rounded-xl px-5 py-3 text-sm font-semibold transition-colors shadow-sm flex items-center gap-2">
                <span className="w-2.5 h-2.5 bg-white rounded-[3px]" /> Stop
              </button>
            ) : (
              <button onClick={() => ask(input)} disabled={!input.trim()}
                className="flex-shrink-0 bg-red-600 hover:bg-red-700 disabled:bg-gray-200 disabled:cursor-not-allowed text-white rounded-xl px-5 py-3 text-sm font-semibold transition-colors shadow-sm">
                Ask →
              </button>
            )}
          </div>
          <p className="max-w-3xl mx-auto mt-2 text-center text-xs text-gray-400">
            Grounded answers with inline citations · Press “/” to focus, “Esc” to stop · Click any [n] or source to view its chunk
          </p>
        </div>
      </div>

      {activeSource && <SourceDrawer source={activeSource} onClose={() => setActiveSource(null)} />}
      {showWelcome && (
        <WelcomeModal
          coverage={coverage}
          onAsk={(q) => { try { localStorage.setItem("synaptdi_welcomed", "1"); } catch {} setShowWelcome(false); ask(q); }}
          onClose={() => { try { localStorage.setItem("synaptdi_welcomed", "1"); } catch {} setShowWelcome(false); }}
        />
      )}
    </AppShell>
  );
}
