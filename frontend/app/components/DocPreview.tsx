"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import type { ReactNode, MutableRefObject } from "react";
import { useRouter } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const FIND_CAP = 2000;   // cap highlighted matches so a 1-char query on a huge spec stays fast

// Render `content` with every occurrence of `query` wrapped in <mark>; the active match
// gets the ref (for scroll-into-view) and a brighter colour. Used only while Find is open.
function renderFind(content: string, query: string, active: number, ref: MutableRefObject<HTMLElement | null>): ReactNode {
  const segs: ReactNode[] = [];
  const lc = content.toLowerCase(), q = query.toLowerCase();
  let pos = 0, n = 0, idx = lc.indexOf(q);
  while (idx !== -1 && n < FIND_CAP) {
    if (idx > pos) segs.push(content.slice(pos, idx));
    const isActive = n === active;
    segs.push(
      <mark key={n} ref={isActive ? (el => { ref.current = el; }) : undefined}
        className={isActive ? "bg-amber-400 text-black rounded-sm" : "bg-amber-200/70 dark:bg-amber-500/40 dark:text-amber-50 rounded-sm"}>
        {content.slice(idx, idx + q.length)}
      </mark>
    );
    pos = idx + q.length; n++;
    idx = lc.indexOf(q, pos);
  }
  segs.push(content.slice(pos));
  return segs;
}

type Raw = {
  name: string; ext: string; kind: "markdown" | "code" | "text";
  lang: string; extracted: boolean; bytes: number;
  truncated: boolean; content: string; downloadable: boolean;
};

function prettyBytes(n: number): string {
  if (!n) return "0 B";
  const u = ["B", "KB", "MB", "GB"]; const i = Math.min(u.length - 1, Math.floor(Math.log(n) / Math.log(1024)));
  return `${(n / 1024 ** i).toFixed(i ? 1 : 0)} ${u[i]}`;
}

// ── lightweight syntax highlighting (json / yaml), line-by-line ──────────────────
const C = {
  key:   "text-sky-700 dark:text-sky-400",
  str:   "text-emerald-700 dark:text-emerald-400",
  num:   "text-amber-600 dark:text-amber-400",
  bool:  "text-purple-600 dark:text-purple-400",
  punct: "text-gray-400 dark:text-slate-500",
  cmt:   "text-gray-400 dark:text-slate-500 italic",
  plain: "text-gray-700 dark:text-slate-300",
};

function hlJson(line: string): ReactNode {
  const out: ReactNode[] = [];
  const re = /("(?:[^"\\]|\\.)*")(\s*:)?|(\btrue\b|\bfalse\b|\bnull\b)|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|([{}[\],])/g;
  let last = 0, k = 0; let m: RegExpExecArray | null;
  while ((m = re.exec(line)) !== null) {
    if (m.index > last) out.push(line.slice(last, m.index));
    if (m[1] !== undefined) {
      if (m[2] !== undefined) { out.push(<span key={k++} className={C.key}>{m[1]}</span>, <span key={k++} className={C.punct}>{m[2]}</span>); }
      else out.push(<span key={k++} className={C.str}>{m[1]}</span>);
    } else if (m[3] !== undefined) out.push(<span key={k++} className={C.bool}>{m[3]}</span>);
    else if (m[4] !== undefined) out.push(<span key={k++} className={C.num}>{m[4]}</span>);
    else if (m[5] !== undefined) out.push(<span key={k++} className={C.punct}>{m[5]}</span>);
    last = re.lastIndex;
  }
  if (last < line.length) out.push(line.slice(last));
  return out.length ? out : " ";
}

function hlYamlVal(v: string): ReactNode {
  const lead = v.match(/^\s*/)?.[0] ?? "";
  const s = v.slice(lead.length);
  if (s === "") return v;
  let cls = C.plain;
  if (/^(true|false|null|~|yes|no)$/i.test(s.trim())) cls = C.bool;
  else if (/^-?\d+(\.\d+)?$/.test(s.trim())) cls = C.num;
  else if (/^["'].*["']\s*$/.test(s)) cls = C.str;
  return <>{lead}<span className={cls}>{s}</span></>;
}

function hlYaml(line: string): ReactNode {
  if (line.trim() === "") return " ";
  if (line.trimStart().startsWith("#")) return <span className={C.cmt}>{line}</span>;
  let m = line.match(/^(\s*(?:-\s+)?)([A-Za-z0-9_.$/-]+)(:)(\s*)(.*)$/);
  if (m) return <>{m[1]}<span className={C.key}>{m[2]}</span><span className={C.punct}>{m[3]}</span>{m[4]}{m[5] ? hlYamlVal(m[5]) : null}</>;
  m = line.match(/^(\s*)(-\s+)(.*)$/);
  if (m) return <>{m[1]}<span className={C.punct}>{m[2]}</span>{hlYamlVal(m[3])}</>;
  return hlYamlVal(line);
}

const HIGHLIGHT_MAX_CHARS = 150_000;   // beyond this, render plain for speed
const LINES_MAX = 7000;

function CodeView({ content, lang, wrap }: { content: string; lang: string; wrap: boolean }) {
  const lines = content.split("\n");
  const tooBig = content.length > HIGHLIGHT_MAX_CHARS || lines.length > LINES_MAX;
  const fn = !tooBig && lang === "json" ? hlJson : !tooBig && lang === "yaml" ? hlYaml : null;

  if (tooBig) {
    return <pre className={`px-5 py-4 text-[12.5px] leading-relaxed font-mono text-gray-800 dark:text-slate-200 ${wrap ? "whitespace-pre-wrap break-words" : "whitespace-pre"}`}>{content}</pre>;
  }
  return (
    <div className="flex text-[12.5px] font-mono leading-[1.6]">
      {!wrap && (
        <div aria-hidden className="select-none text-right py-4 pl-4 pr-3 text-gray-300 dark:text-slate-600 bg-gray-50/60 dark:bg-slate-950/40 border-r border-gray-100 dark:border-slate-800 flex-shrink-0">
          {lines.map((_, i) => <div key={i}>{i + 1}</div>)}
        </div>
      )}
      <code className={`py-4 px-4 block flex-1 text-gray-800 dark:text-slate-200 ${wrap ? "whitespace-pre-wrap break-words" : "whitespace-pre overflow-x-auto"}`}>
        {lines.map((ln, i) => <div key={i}>{fn ? fn(ln) : (ln || " ")}</div>)}
      </code>
    </div>
  );
}

// ── Compact markdown renderer (headings / bold / italic / code / links / lists / tables) ──
function inline(t: string): ReactNode {
  const out: ReactNode[] = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(\[[^\]]+\]\([^)]+\))/;
  let rest = t, k = 0;
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const m = rest.match(re);
    if (!m || m.index === undefined) { if (rest) out.push(rest); break; }
    if (m.index > 0) out.push(rest.slice(0, m.index));
    const tok = m[0];
    if (tok.startsWith("`"))
      out.push(<code key={k++} className="px-1 py-0.5 rounded bg-gray-100 dark:bg-slate-800 text-[0.88em] font-mono text-rose-600 dark:text-rose-400">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("**")) out.push(<strong key={k++}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("*")) out.push(<em key={k++}>{tok.slice(1, -1)}</em>);
    else {
      const mm = tok.match(/\[([^\]]+)\]\(([^)]+)\)/)!;
      out.push(<a key={k++} href={mm[2]} target="_blank" rel="noreferrer" className="text-red-500 hover:underline">{mm[1]}</a>);
    }
    rest = rest.slice(m.index + tok.length);
  }
  return out;
}

function renderMarkdown(src: string): ReactNode {
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  const out: ReactNode[] = [];
  let i = 0, key = 0;
  const edgeTrim = (arr: string[]) =>
    arr.filter((_, idx) => !(idx === 0 && arr[0] === "") && !(idx === arr.length - 1 && arr[arr.length - 1] === ""));

  while (i < lines.length) {
    const ln = lines[i];

    if (ln.trim().startsWith("```")) {                       // fenced code
      const buf: string[] = []; i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) { buf.push(lines[i]); i++; }
      i++;
      out.push(<pre key={key++} className="my-3 p-3 rounded-lg bg-gray-50 dark:bg-slate-950 border border-gray-200 dark:border-slate-800 overflow-x-auto text-[12.5px] font-mono leading-relaxed">{buf.join("\n")}</pre>);
      continue;
    }
    const h = ln.match(/^(#{1,4})\s+(.*)/);                  // heading
    if (h) {
      const sz = ["text-xl", "text-lg", "text-base", "text-sm"][h[1].length - 1];
      out.push(<div key={key++} className={`${sz} font-bold text-gray-900 dark:text-slate-100 mt-5 mb-2 first:mt-0`}>{inline(h[2])}</div>);
      i++; continue;
    }
    if (/^(\*\*\*|---|___)\s*$/.test(ln)) { out.push(<hr key={key++} className="my-4 border-gray-200 dark:border-slate-700" />); i++; continue; }

    if (ln.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].includes("-")) {
      const header = edgeTrim(ln.split("|").map(s => s.trim()));
      i += 2; const rows: string[][] = [];
      while (i < lines.length && lines[i].includes("|")) { rows.push(edgeTrim(lines[i].split("|").map(s => s.trim()))); i++; }
      out.push(
        <div key={key++} className="my-3 overflow-x-auto">
          <table className="text-sm border-collapse">
            <thead><tr>{header.map((hh, x) => <th key={x} className="border border-gray-200 dark:border-slate-700 px-3 py-1.5 bg-gray-50 dark:bg-slate-800 text-left font-semibold text-gray-700 dark:text-slate-200">{inline(hh)}</th>)}</tr></thead>
            <tbody>{rows.map((r, y) => <tr key={y}>{r.map((c, x) => <td key={x} className="border border-gray-200 dark:border-slate-700 px-3 py-1.5 text-gray-700 dark:text-slate-300 align-top">{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>
      );
      continue;
    }
    if (/^\s*[-*+]\s+/.test(ln)) {                           // unordered list
      const items: ReactNode[] = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { items.push(<li key={items.length} className="ml-5 list-disc text-gray-700 dark:text-slate-300">{inline(lines[i].replace(/^\s*[-*+]\s+/, ""))}</li>); i++; }
      out.push(<ul key={key++} className="my-2 space-y-1">{items}</ul>); continue;
    }
    if (/^\s*\d+\.\s+/.test(ln)) {                           // ordered list
      const items: ReactNode[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) { items.push(<li key={items.length} className="ml-5 list-decimal text-gray-700 dark:text-slate-300">{inline(lines[i].replace(/^\s*\d+\.\s+/, ""))}</li>); i++; }
      out.push(<ol key={key++} className="my-2 space-y-1">{items}</ol>); continue;
    }
    if (ln.trim() === "") { i++; continue; }

    const buf: string[] = [];                               // paragraph
    while (i < lines.length && lines[i].trim() !== "" && !lines[i].trim().startsWith("```")
      && !/^#{1,4}\s/.test(lines[i]) && !/^\s*[-*+]\s/.test(lines[i]) && !/^\s*\d+\.\s/.test(lines[i])) { buf.push(lines[i]); i++; }
    out.push(<p key={key++} className="my-2 leading-relaxed text-gray-700 dark:text-slate-300">{inline(buf.join(" "))}</p>);
  }
  return out;
}

// Readable prose for EXTRACTED / plain text (PDF/DOCX/XLSX/PPTX/txt) — declutters the
// monospace dump: normalises whitespace, collapses runaway blank lines, real paragraphs.
function ProseView({ content }: { content: string }) {
  const cleaned = content
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")       // trailing spaces
    .replace(/\n{3,}/g, "\n\n")       // runaway blank lines → one blank line
    .trim();
  const blocks = cleaned.split(/\n{2,}/);
  return (
    <div className="px-6 py-5 max-w-2xl mx-auto text-[14px] leading-7 text-gray-800 dark:text-slate-200">
      {blocks.map((b, i) => {
        const h = b.match(/^#{1,3}\s+(.*)$/);   // xlsx "# Sheet" / pptx "# Slide" markers
        if (h) return <h3 key={i} className="text-sm font-bold text-gray-900 dark:text-slate-100 mt-5 mb-1.5 first:mt-0">{h[1]}</h3>;
        return <p key={i} className="mb-3.5 whitespace-pre-wrap break-words">{b}</p>;
      })}
    </div>
  );
}

export function DocPreview({ file, name, askScope = "all", onClose }: { file: string; name?: string; askScope?: "all" | "kb" | "docs"; onClose: () => void }) {
  const router = useRouter();
  const [data, setData] = useState<Raw | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);
  const [wrap, setWrap] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [findOpen, setFindOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const findInputRef = useRef<HTMLInputElement>(null);
  const activeMarkRef = useRef<HTMLElement | null>(null);
  const isPdf = (name || file).toLowerCase().endsWith(".pdf");

  useEffect(() => { const r = requestAnimationFrame(() => setMounted(true)); return () => cancelAnimationFrame(r); }, []);
  const copy = async () => {
    if (!data) return;
    try { await navigator.clipboard.writeText(data.content); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked */ }
  };
  const ask = () => {
    const q = `Explain ${name || data?.name || file} — what is it for, and what are its key resources, fields, and operations?`;
    router.push(`/?ask=${encodeURIComponent(q)}&scope=${askScope}`);
  };
  const isCode = data && data.kind === "code";   // Wrap toggle only applies to the code view

  // ── Find-in-document ──
  const matchCount = useMemo(() => {
    if (!data || !query) return 0;
    const lc = data.content.toLowerCase(), q = query.toLowerCase();
    let pos = 0, n = 0, idx = lc.indexOf(q);
    while (idx !== -1 && n <= FIND_CAP) { n++; pos = idx + q.length; idx = lc.indexOf(q, pos); }
    return n;
  }, [data, query]);
  const shown = Math.min(matchCount, FIND_CAP);
  useEffect(() => { setActive(0); }, [query]);
  useEffect(() => { if (findOpen && query) activeMarkRef.current?.scrollIntoView({ block: "center" }); }, [active, query, findOpen]);
  const step = (d: number) => { if (shown) setActive(a => (a + d + shown) % shown); };
  const onFindKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") { e.preventDefault(); step(e.shiftKey ? -1 : 1); }
  };

  const enc = encodeURIComponent(file);
  const viewUrl = `${API}/documents/file?file=${enc}`;
  const dlUrl = `${API}/documents/file?file=${enc}&download=1`;

  useEffect(() => {
    if (isPdf) { setLoading(false); return; }   // PDFs render via <iframe>, no text fetch
    let alive = true;
    setLoading(true); setErr("");
    fetch(`${API}/documents/raw?file=${enc}`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error(r.status === 404 ? "Document not found" : "Could not load preview")))
      .then((d: Raw) => { if (alive) setData(d); })
      .catch(e => { if (alive) setErr(e.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [enc, isPdf]);

  const close = useCallback(() => onClose(), [onClose]);
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!isPdf && (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "f") {
        e.preventDefault(); setFindOpen(true); setTimeout(() => findInputRef.current?.select(), 30); return;
      }
      if (e.key === "Escape") { if (findOpen) { setFindOpen(false); setQuery(""); } else close(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [close, findOpen, isPdf]);

  const title = name || data?.name || file;
  const subtitle = data
    ? `${prettyBytes(data.bytes)}${data.extracted ? " · text extracted" : ""}${data.truncated ? " · preview truncated" : ""}`
    : isPdf ? "PDF document" : loading ? "Loading…" : "";

  return (
    <div className={`fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm transition-opacity duration-200 ${mounted ? "opacity-100" : "opacity-0"}`} onClick={close}>
      <div onClick={e => e.stopPropagation()}
        className={`w-full max-w-4xl h-[86vh] flex flex-col bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-2xl overflow-hidden transition-all duration-200 ${mounted ? "opacity-100 scale-100" : "opacity-0 scale-[0.97]"}`}>
        {/* header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-gray-100 dark:border-slate-800 flex-shrink-0">
          <svg className="w-5 h-5 flex-shrink-0 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-gray-900 dark:text-slate-100 truncate">{title}</div>
            <div className="text-[11px] text-gray-400">{subtitle}</div>
          </div>
          {!isPdf && data && (
            <button onClick={ask} title="Ask SynaptDI about this document"
              className="text-xs font-semibold px-3 py-1.5 rounded-lg bg-red-500 hover:bg-red-600 text-white inline-flex items-center gap-1.5 transition-colors shadow-sm flex-shrink-0">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.86 9.86 0 01-4-.8L3 20l1.3-3.9A7.96 7.96 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" /></svg>
              Ask about this
            </button>
          )}
          {!isPdf && data && (
            <button onClick={() => { setFindOpen(o => !o); setTimeout(() => findInputRef.current?.select(), 30); }} title="Find in document (⌘F)"
              className="p-1.5 rounded-lg border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors flex-shrink-0">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
            </button>
          )}
          {isCode && (
            <button onClick={() => setWrap(w => !w)} title="Toggle word wrap"
              className="hidden sm:inline-block text-xs font-medium px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors">{wrap ? "No wrap" : "Wrap"}</button>
          )}
          {!isPdf && data && (
            <button onClick={copy} title="Copy contents"
              className="text-xs font-medium px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors inline-flex items-center gap-1.5">
              {copied
                ? <><svg className="w-3.5 h-3.5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>Copied</>
                : <><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>Copy</>}
            </button>
          )}
          <a href={viewUrl} target="_blank" rel="noreferrer"
            className="hidden sm:inline-block text-xs font-medium px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors">Open raw</a>
          <a href={dlUrl}
            className="text-xs font-medium px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors">Download</a>
          <button onClick={close} title="Close (Esc)"
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        {/* body */}
        <div className="relative flex-1 overflow-auto bg-white dark:bg-slate-900">
          {findOpen && !isPdf && (
            <div className="sticky top-0 z-20 flex justify-end pointer-events-none">
              <div className="pointer-events-auto m-3 flex items-center gap-1 pl-2.5 pr-1.5 py-1.5 rounded-xl bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 shadow-lg">
                <svg className="w-4 h-4 text-gray-400 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8"><path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                <input ref={findInputRef} value={query} onChange={e => setQuery(e.target.value)} onKeyDown={onFindKey}
                  placeholder="Find in document" className="bg-transparent text-sm outline-none w-40 text-gray-800 dark:text-slate-200 placeholder:text-gray-400" />
                <span className="text-[11px] text-gray-400 tabular-nums whitespace-nowrap px-1 min-w-[3rem] text-right">
                  {query ? (matchCount ? `${active + 1}/${matchCount > FIND_CAP ? FIND_CAP + "+" : matchCount}` : "0") : ""}
                </span>
                <button onClick={() => step(-1)} disabled={!shown} title="Previous (⇧⏎)" className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700 disabled:opacity-30"><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><polyline points="18 15 12 9 6 15" /></svg></button>
                <button onClick={() => step(1)} disabled={!shown} title="Next (⏎)" className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700 disabled:opacity-30"><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><polyline points="6 9 12 15 18 9" /></svg></button>
                <button onClick={() => { setFindOpen(false); setQuery(""); }} title="Close (Esc)" className="p-1 rounded text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-700"><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg></button>
              </div>
            </div>
          )}
          {isPdf ? (
            <iframe src={viewUrl} title={title} className="w-full h-full border-0" />
          ) : loading ? (
            <div className="p-6 space-y-3">
              {Array.from({ length: 9 }).map((_, i) => <div key={i} className="skeleton h-4 rounded" style={{ width: `${55 + ((i * 37) % 45)}%` }} />)}
            </div>
          ) : err ? (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-center px-6">
              <p className="text-sm text-gray-500 dark:text-slate-400">{err}.</p>
              <a href={dlUrl} className="text-sm text-red-500 hover:underline">Download the file instead</a>
            </div>
          ) : findOpen && query ? (
            <pre className="px-5 pb-4 text-[12.5px] leading-relaxed font-mono whitespace-pre-wrap break-words text-gray-800 dark:text-slate-200">{renderFind(data?.content || "", query, active, activeMarkRef)}</pre>
          ) : data?.kind === "markdown" ? (
            <div className="px-6 py-5 max-w-3xl">{renderMarkdown(data.content)}</div>
          ) : data?.kind === "text" ? (
            <ProseView content={data?.content || ""} />
          ) : (
            <CodeView content={data?.content || ""} lang={data?.lang || ""} wrap={wrap} />
          )}
        </div>
      </div>
    </div>
  );
}
