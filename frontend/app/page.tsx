"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import AppShell from "./components/AppShell";
import { useBranding } from "./components/BrandingContext";
import { loadPrefs } from "./settings/page";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Source {
  name: string;
  file: string;
  chunk: number;
  preview: string;
  url?: string;
  upload?: boolean;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  latency_ms?: number;
  error?: boolean;
}

const SUGGESTED = [
  "What mandatory fields does TMF622 Product Order require?",
  "What is the difference between TMF620 and TMF633?",
  "How do I handle pagination in TM Forum Open APIs?",
  "Which ODA component handles trouble tickets?",
  "Explain the eTOM Level 1 processes",
  "What is the SID ABE for customer data?",
];

// Strip markdown syntax from plain text
function stripMd(text: string) {
  return text.replace(/\*\*/g, "").replace(/`/g, "").replace(/#{1,3}\s/g, "").trim();
}

// Render answer markdown
function renderMarkdown(text: string) {
  const lines = text.split("\n");
  const nodes: React.ReactNode[] = [];
  let key = 0;

  for (const line of lines) {
    if (!line.trim()) { nodes.push(<div key={key++} className="h-2" />); continue; }

    if (line.startsWith("## ") || line.startsWith("### ")) {
      nodes.push(<p key={key++} className="font-semibold text-gray-900 mt-3 mb-1">{line.replace(/^#{2,3}\s/, "")}</p>);
    } else if (line.match(/^[\*\-\+]\s/)) {
      nodes.push(
        <div key={key++} className="flex gap-2 my-0.5 ml-1">
          <span className="text-red-500 flex-shrink-0 mt-0.5">•</span>
          <span>{inlineFormat(line.slice(2))}</span>
        </div>
      );
    } else if (line.match(/^\s{2,}[\+\-\*]\s/)) {
      const txt = line.replace(/^\s+[\+\-\*]\s/, "");
      nodes.push(
        <div key={key++} className="flex gap-2 my-0.5 ml-6">
          <span className="text-gray-400 flex-shrink-0">◦</span>
          <code className="text-xs font-mono bg-gray-100 text-red-700 px-1.5 py-0.5 rounded">{txt}</code>
        </div>
      );
    } else {
      nodes.push(<p key={key++} className="my-0.5 leading-relaxed">{inlineFormat(line)}</p>);
    }
  }
  return nodes;
}

function inlineFormat(text: string): React.ReactNode {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`"))
      return <code key={i} className="bg-gray-100 text-red-700 font-mono text-xs px-1.5 py-0.5 rounded">{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**"))
      return <strong key={i} className="font-semibold text-gray-900">{part.slice(2, -2)}</strong>;
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

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed right-0 top-0 h-full w-full max-w-lg bg-white z-50 shadow-2xl flex flex-col"
           style={{ animation: "slideIn 0.2s ease-out" }}>
        <style>{`@keyframes slideIn { from { transform: translateX(100%); } to { transform: translateX(0); } }`}</style>

        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-gray-100 bg-gray-50">
          <div className="flex-1 min-w-0 pr-3">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
              <span className="text-xs font-bold text-red-600 uppercase tracking-widest">Source Document</span>
            </div>
            <h3 className="font-semibold text-gray-900 text-sm leading-snug">{cleanName}</h3>
            <p className="text-xs text-gray-400 mt-1 font-mono">{source.file} · chunk {source.chunk}</p>
          </div>
          <button onClick={onClose}
            className="w-7 h-7 rounded-full hover:bg-gray-200 flex items-center justify-center text-gray-400 hover:text-gray-700 transition-colors flex-shrink-0 text-lg">
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          {/* Link to actual source */}
          {source.url ? (
            <a href={source.url} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-3 p-3.5 bg-white border border-gray-200 hover:border-red-300 hover:bg-red-50 rounded-xl transition-all group">
              <div className="w-8 h-8 bg-gray-100 group-hover:bg-red-100 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors">
                <svg className="w-4 h-4 text-gray-500 group-hover:text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-700 group-hover:text-red-700 transition-colors">View on GitHub</p>
                <p className="text-xs text-gray-400 truncate">{source.url.replace("https://github.com/", "")}</p>
              </div>
              <svg className="w-4 h-4 text-gray-300 group-hover:text-red-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </a>
          ) : (
            <div className="flex items-center gap-3 p-3.5 bg-gray-50 border border-gray-200 rounded-xl">
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
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-100">
              <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">{source.preview}</pre>
            </div>
            <p className="text-xs text-gray-400 mt-2 text-center">Retrieved via semantic similarity search · nomic-embed-text</p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-100 bg-gray-50 flex items-center justify-between">
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
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    fetch(`${API}/stats`).then(r => r.json()).then(setStats).catch(() => {});
    const p = loadPrefs();
    setPrefs({ topK: p.topK, showSrc: p.showSrc });
    try { const l = localStorage.getItem("synaptdi_logo"); if (l) setLogo(l); } catch {}
  }, []);

  const firstLetter = (branding.companyName || "S")[0].toUpperCase();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const ask = useCallback(async (question: string) => {
    if (!question.trim() || loading) return;
    // Recent turns (before this one) so follow-ups like "what about its events?" work.
    const history = messages.filter(m => m.content && !m.error)
                            .slice(-6).map(m => ({ role: m.role, content: m.content }));
    setInput("");
    // Add the user turn + an empty assistant bubble we stream into.
    setMessages(prev => [...prev, { role: "user", content: question }, { role: "assistant", content: "" }]);
    setLoading(true);

    // Immutably patch the trailing assistant message. Pure updater (no in-place
    // mutation) so React StrictMode's double-invocation can't double the text.
    const setLast = (patch: Partial<Message>) => setMessages(prev => {
      const copy = [...prev];
      const i = copy.length - 1;
      if (i >= 0 && copy[i].role === "assistant") copy[i] = { ...copy[i], ...patch };
      return copy;
    });
    let acc = "";   // full answer so far (set, never appended-in-place)

    try {
      const res = await fetch(`${API}/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k: prefs.topK, scope, history }),
        signal: AbortSignal.timeout(180000),
      });
      if (!res.ok || !res.body) throw new Error(`API error ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";              // keep the last partial line
        for (const line of lines) {
          if (!line.trim()) continue;
          let evt: any;
          try { evt = JSON.parse(line); } catch { continue; }
          if (evt.type === "token")      { acc += evt.text; setLast({ content: acc }); }
          else if (evt.type === "done")  setLast({ sources: evt.sources, latency_ms: evt.latency_ms });
          else if (evt.type === "error") { acc = evt.text; setLast({ content: acc, error: true }); }
        }
      }
    } catch (e: any) {
      const msg = e.name === "TimeoutError"
        ? "Request timed out. The model may still be loading — try again in 30 seconds."
        : `Could not reach SynaptDI API: ${e.message}. Make sure uvicorn is running on port 8000.`;
      setLast({ content: msg, error: true });
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  }, [loading, scope, prefs, messages]);

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input); }
  }

  return (
    <AppShell>
      <div className="flex flex-col h-full bg-white">

        {/* Header */}
        <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 shadow-sm flex-shrink-0 z-10">
          <div className="flex items-center gap-3">
            <span className="font-semibold text-gray-800 text-sm tracking-tight">Chat</span>
            {stats?.chunks_indexed != null && (
              <span className="text-xs text-gray-400 bg-gray-100 px-2.5 py-1 rounded-full hidden sm:inline-block">
                {stats.chunks_indexed.toLocaleString()} chunks indexed
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {messages.length > 0 && (
              <button onClick={() => setMessages([])}
                className="text-xs text-gray-400 hover:text-gray-600 px-2.5 py-1.5 rounded-lg hover:bg-gray-100 transition-colors">
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
                    <h2 className="text-xl font-bold text-gray-900">What would you like to know?</h2>
                    <p className="text-gray-400 text-sm mt-1">{branding.tagline}</p>
                  </div>
                  {stats?.chunks_indexed != null && (
                    <div className="flex items-center gap-1.5 text-xs text-gray-400 bg-gray-50 border border-gray-200 px-3 py-1.5 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                      {stats.chunks_indexed.toLocaleString()} chunks indexed and ready
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-2xl">
                  {SUGGESTED.map((q, i) => (
                    <button key={i} onClick={() => ask(q)}
                      className="text-left text-sm text-gray-600 bg-white hover:bg-red-50 hover:text-red-700 border border-gray-200 hover:border-red-200 hover:shadow-sm rounded-xl px-4 py-3.5 transition-all">
                      <span className="text-red-500 mr-2 text-xs">→</span>{q}
                    </button>
                  ))}
                </div>
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
                      ? "bg-red-50 text-red-800 border border-red-200 rounded-tl-sm"
                      : "bg-gray-50 text-gray-800 border border-gray-100 rounded-tl-sm"
                  }`}>
                    {msg.role === "assistant" && !msg.error
                      ? (msg.content
                          ? renderMarkdown(msg.content)
                          : <span className="flex items-center gap-1.5 py-0.5">
                              {[0, 150, 300].map(d => (
                                <span key={d} className="w-2 h-2 rounded-full bg-red-400 animate-bounce" style={{ animationDelay: `${d}ms` }} />
                              ))}
                            </span>)
                      : <span>{msg.content}</span>}
                  </div>

                  {prefs.showSrc && msg.sources && msg.sources.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-2 items-center">
                      <span className="text-xs text-gray-400 font-medium">Sources:</span>
                      {msg.sources.map((src, si) => (
                        <span key={si} className="inline-flex items-center">
                          {src.url ? (
                            <>
                              <a href={src.url} target="_blank" rel="noopener noreferrer"
                                className="group flex items-center gap-1.5 text-xs bg-white border border-gray-200 text-gray-500 hover:text-red-600 hover:border-red-300 hover:bg-red-50 rounded-l-full px-3 py-1 transition-all">
                                <span className="w-1.5 h-1.5 rounded-full bg-red-500 flex-shrink-0" />
                                {stripMd(src.name)}
                                <span className="text-gray-300 group-hover:text-red-400">↗</span>
                              </a>
                              <button onClick={() => setActiveSource(src)}
                                className="text-xs bg-white border border-l-0 border-gray-200 text-gray-400 hover:text-red-600 hover:border-red-300 hover:bg-red-50 rounded-r-full px-2 py-1 transition-all"
                                title="View chunk preview">
                                ···
                              </button>
                            </>
                          ) : (
                            <button onClick={() => setActiveSource(src)}
                              className="group flex items-center gap-1.5 text-xs bg-white border border-gray-200 text-gray-500 hover:text-red-600 hover:border-red-300 hover:bg-red-50 rounded-full px-3 py-1 transition-all">
                              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${src.upload ? "bg-amber-500" : "bg-red-500"}`} />
                              {stripMd(src.name)}
                              {src.upload && <span className="text-amber-600 text-[10px] font-medium">· your doc</span>}
                            </button>
                          )}
                        </span>
                      ))}
                      {msg.latency_ms && (
                        <span className="text-xs text-gray-300 ml-1">{(msg.latency_ms / 1000).toFixed(1)}s</span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}

            <div ref={bottomRef} />
          </div>
        </main>

        {/* Input */}
        <div className="border-t border-gray-200 bg-white px-4 py-4 flex-shrink-0">
          <div className="max-w-3xl mx-auto mb-2 flex items-center gap-1.5">
            <span className="text-xs text-gray-400 mr-0.5">Search:</span>
            {([["all", "Everything"], ["kb", "Knowledge Base"], ["docs", "My Documents"]] as const).map(([v, label]) => (
              <button key={v} onClick={() => setScope(v)} type="button"
                className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                  scope === v
                    ? "bg-red-600 text-white border-red-600"
                    : "bg-white text-gray-500 border-gray-200 hover:bg-gray-50"
                }`}>
                {label}
              </button>
            ))}
          </div>
          <div className="max-w-3xl mx-auto flex items-end gap-3">
            <textarea ref={inputRef} value={input}
              onChange={e => setInput(e.target.value)} onKeyDown={handleKey}
              placeholder="Ask about TM Forum APIs, ODA, eTOM, SID..." rows={1} disabled={loading}
              className="flex-1 resize-none border border-gray-200 rounded-xl px-4 py-3 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent bg-gray-50 disabled:opacity-50"
              style={{ maxHeight: "120px" }}
              onInput={e => {
                const t = e.target as HTMLTextAreaElement;
                t.style.height = "auto";
                t.style.height = Math.min(t.scrollHeight, 120) + "px";
              }}
            />
            <button onClick={() => ask(input)} disabled={!input.trim() || loading}
              className="flex-shrink-0 bg-red-600 hover:bg-red-700 disabled:bg-gray-200 disabled:cursor-not-allowed text-white rounded-xl px-5 py-3 text-sm font-semibold transition-colors shadow-sm">
              {loading ? "···" : "Ask →"}
            </button>
          </div>
          <p className="max-w-3xl mx-auto mt-2 text-center text-xs text-gray-400">
            Answers grounded in TM Forum docs · Click any source to view chunk + GitHub link · SynaptDI — Enterprise domains at your fingertips
          </p>
        </div>
      </div>

      {activeSource && <SourceDrawer source={activeSource} onClose={() => setActiveSource(null)} />}
    </AppShell>
  );
}
