"use client";

import { useEffect, useState, useCallback } from "react";
import type { ReactNode } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

export function DocPreview({ file, name, onClose }: { file: string; name?: string; onClose: () => void }) {
  const [data, setData] = useState<Raw | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const isPdf = (name || file).toLowerCase().endsWith(".pdf");

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
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [close]);

  const title = name || data?.name || file;
  const subtitle = data
    ? `${prettyBytes(data.bytes)}${data.extracted ? " · text extracted" : ""}${data.truncated ? " · preview truncated" : ""}`
    : isPdf ? "PDF document" : loading ? "Loading…" : "";

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm" onClick={close}>
      <div onClick={e => e.stopPropagation()}
        className="w-full max-w-4xl h-[86vh] flex flex-col bg-white dark:bg-slate-900 rounded-2xl border border-gray-200 dark:border-slate-700 shadow-2xl overflow-hidden">
        {/* header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-gray-100 dark:border-slate-800 flex-shrink-0">
          <svg className="w-5 h-5 flex-shrink-0 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.8">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold text-gray-900 dark:text-slate-100 truncate">{title}</div>
            <div className="text-[11px] text-gray-400">{subtitle}</div>
          </div>
          <a href={viewUrl} target="_blank" rel="noreferrer"
            className="text-xs font-medium px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors">Open raw</a>
          <a href={dlUrl}
            className="text-xs font-medium px-2.5 py-1.5 rounded-lg border border-gray-200 dark:border-slate-700 text-gray-600 dark:text-slate-300 hover:bg-gray-50 dark:hover:bg-slate-800 transition-colors">Download</a>
          <button onClick={close} title="Close (Esc)"
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 dark:hover:text-slate-200 hover:bg-gray-100 dark:hover:bg-slate-800 transition-colors">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>

        {/* body */}
        <div className="flex-1 overflow-auto bg-white dark:bg-slate-900">
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
          ) : data?.kind === "markdown" ? (
            <div className="px-6 py-5 max-w-3xl">{renderMarkdown(data.content)}</div>
          ) : (
            <pre className="px-6 py-5 text-[12.5px] leading-relaxed font-mono text-gray-800 dark:text-slate-200 whitespace-pre-wrap break-words">{data?.content}</pre>
          )}
        </div>
      </div>
    </div>
  );
}
