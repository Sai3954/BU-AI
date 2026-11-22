"use client";
import { useState } from "react";
import type { Checks, Source } from "@/lib/api";
import { sourceMeta } from "@/lib/sources";

export type Stage = "searching" | "reading" | "writing" | "verifying" | "done" | "error";
export type ActivityEvent = { at: number; kind: "search" | "found" | "write" | "verify" | "ready"; label: string };

const LIVE: Record<string, string> = {
  searching: "Searching Belhaven's official pages",
  reading: "Reading the sources",
  writing: "Writing your answer",
  verifying: "Checking every fact against the sources",
};

const secs = (ms: number) => (ms < 1000 ? `${Math.max(0, Math.round(ms))} ms` : `${(ms / 1000).toFixed(1)} s`);

function Spark() {
  return (
    <svg className="spark" viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
      <path d="M12 3l1.6 4.9L18.5 9.5l-4.9 1.6L12 16l-1.6-4.9L5.5 9.5l4.9-1.6z" fill="currentColor" />
      <path d="M19 15l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z" fill="currentColor" opacity=".7" />
    </svg>
  );
}

function verifyResult(c?: Checks): string {
  if (!c) return "";
  const n = c.unverified.length + c.misattributed.length + c.unsupported_claims.length;
  return n ? `${n} item${n > 1 ? "s" : ""} flagged to double-check` : "All figures and citations matched their sources";
}

/** Status line while Bela works (shows only the step that is really running), then a quiet
 *  "Answer ready" summary that expands into the full activity log with the sources read. */
export function Activity({ stage, events, sources, checks }: {
  stage: Stage; events: ActivityEvent[]; sources: Source[]; checks?: Checks;
}) {
  const [open, setOpen] = useState(false);
  const working = stage !== "done" && stage !== "error";
  const total = events.length ? events[events.length - 1].at : 0;
  const pages = new Set(sources.map(s => s.url.split("#")[0])).size;
  return (
    <div className={`activity ${working ? "working" : ""}`}>
      <button type="button" className="activity-line" aria-expanded={open} onClick={() => setOpen(o => !o)}>
        {working ? (
          <><Spark /><span>{LIVE[stage]}</span><span className="adots" aria-hidden="true"><i /><i /><i /></span></>
        ) : stage === "done" ? (
          <><span className="ok" aria-hidden="true">✓</span><span>Answer ready{sources.length ? ` · ${sources.length} sources checked` : ""} · {secs(total)}</span></>
        ) : <span>Stopped</span>}
        <span className="activity-toggle">{open ? "Hide activity" : "Show activity"}</span>
      </button>
      {open && (
        <ol className="activity-log">
          {events.map((e, i) => (
            <li key={i} className={`ev ${e.kind}`}>
              <span className="ev-t">{secs(e.at)}</span>
              <div>
                <b>{e.label}</b>
                {e.kind === "found" && sources.length > 0 && (
                  <ul className="ev-src">
                    {sources.map((s, n) => (
                      <li key={n}><span className="src-n">{n + 1}</span>
                        <a href={s.url} target="_blank" rel="noopener noreferrer">{sourceMeta(s).title}</a>
                        <span className="age">{sourceMeta(s).kind}{sourceMeta(s).date ? ` · ${sourceMeta(s).date.toLowerCase()}` : ""}</span></li>
                    ))}
                  </ul>
                )}
                {e.kind === "verify" && checks && stage === "done" && <div className="muted">{verifyResult(checks)}</div>}
              </div>
            </li>
          ))}
          {working && events[events.length - 1]?.label.replace("’", "'") !== LIVE[stage].replace("’", "'") && <li className="ev now"><span className="ev-t">…</span><div><b>{LIVE[stage]}</b></div></li>}
          {!working && pages > 0 && <li className="ev meta"><span className="ev-t" /><div className="muted">Only Belhaven’s public pages were used ({pages} page{pages > 1 ? "s" : ""}). No student records.</div></li>}
        </ol>
      )}
    </div>
  );
}
