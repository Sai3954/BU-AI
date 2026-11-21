import { Fragment, ReactNode } from "react";
import type { Source } from "@/lib/api";

/** Render the model's plain text: paragraphs, "- " bullets, **bold**, and [n] citation chips. */
function inline(text: string, sources: Source[], key: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|\[\d+\])/g);
  return parts.map((p, i) => {
    const k = `${key}-${i}`;
    const cite = /^\[(\d+)\]$/.exec(p);
    if (cite) {
      const s = sources[Number(cite[1]) - 1];
      return s ? (
        <a key={k} className="cite" href={s.url} target="_blank" rel="noopener noreferrer" title={s.title}>{cite[1]}</a>
      ) : null;
    }
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={k}>{p.slice(2, -2)}</strong>;
    return <Fragment key={k}>{p}</Fragment>;
  });
}

export function Answer({ text, sources }: { text: string; sources: Source[] }) {
  const lines = text.trim().split(/\n+/);
  const out: ReactNode[] = [];
  let list: ReactNode[] = [];
  const flush = () => { if (list.length) { out.push(<ul key={`ul${out.length}`}>{list}</ul>); list = []; } };
  lines.forEach((line, i) => {
    const li = /^\s*(?:[-*•]|\d+\.)\s+(.*)$/.exec(line);
    if (li) list.push(<li key={i}>{inline(li[1], sources, `l${i}`)}</li>);
    else { flush(); out.push(<p key={i}>{inline(line, sources, `p${i}`)}</p>); }
  });
  flush();
  return <>{out}</>;
}

export function SourceList({ sources, text }: { sources: Source[]; text: string }) {
  const used = new Set(Array.from(text.matchAll(/\[(\d+)\]/g)).map(m => Number(m[1])));
  const shown = sources.map((s, i) => ({ s, n: i + 1 })).filter(x => used.size === 0 ? x.n <= 3 : used.has(x.n));
  if (!shown.length) return null;
  return (
    <div className="sources">
      <div className="sources-h">Sources</div>
      {shown.map(({ s, n }) => (
        <div className="src" key={n}>
          <span className="src-n">{n}</span>
          <span>
            <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a>
            <span className={`age ${/year/.test(s.updated) ? "old" : ""}`}>
              {s.updated === "current site" || !s.updated ? "Current page" : /pdf/i.test(s.updated) ? "PDF document" : `Updated ${s.updated}`}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}
