"use client";

import { FormEvent, useEffect, useState } from "react";
import { getAdminSummary, reindex } from "@/lib/api";

type Summary = {
  window_days: number;
  totals: { questions: number; answered_rate: number | null; helpful_rate: number | null; high_risk: number;
    avg_latency_ms: number | null; crawled_pages: number; passages: number;
    pii_redacted: number; unverified_answers: number; ai_answers: number; ai_calls_today: number; daily_ai_limit: number };
  by_role: Record<string, number>; by_category: Record<string, number>;
  top_questions: { question: string; count: number }[]; unanswered: { question: string; count: number }[];
  issues: { kind: string; severity: string; url: string; detail: string; detected_at: string }[];
  issue_counts: Record<string, number>;
};

const KIND_LABEL: Record<string, string> = {
  conflict: "Conflicting information", stale: "Possibly outdated", broken_link: "Broken link", changed: "Page changed",
};
const pct = (v: number | null) => (v == null ? "–" : `${Math.round(v * 100)}%`);

function Bars({ data }: { data: Record<string, number> }) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...rows.map(r => r[1]));
  if (!rows.length) return <p className="muted">No questions yet.</p>;
  return (
    <div className="bars">
      {rows.map(([k, v]) => (
        <div className="bar" key={k}>
          <span className="bar-l">{k}</span>
          <span className="bar-t"><span style={{ width: `${(v / max) * 100}%` }} /></span>
          <span className="bar-v">{v}</span>
        </div>
      ))}
    </div>
  );
}

export default function Admin() {
  const [token, setToken] = useState("");
  const [data, setData] = useState<Summary | null>(null);
  const [err, setErr] = useState("");
  const [kind, setKind] = useState("all");
  const [note, setNote] = useState("");

  const load = async (t = token) => {
    setErr("");
    try {
      setData(await getAdminSummary(t));
      try { sessionStorage.setItem("adminToken", t); } catch {}
    } catch (e) { setErr((e as Error).message); setData(null); }
  };
  useEffect(() => {
    try { const t = sessionStorage.getItem("adminToken"); if (t) { setToken(t); load(t); } } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const submit = (e: FormEvent) => { e.preventDefault(); load(); };
  const doReindex = async () => {
    setNote("Rebuilding…");
    try { const r = await reindex(token); setNote(`Index rebuilt: ${r.passages} passages, ${r.conflicts} conflicts, ${r.stale} outdated pages.`); load(); }
    catch (e) { setNote((e as Error).message); }
  };

  if (!data) {
    return (
      <div className="admin-login">
        <h1>Admin insights</h1>
        <p className="muted">Enter the admin token from the backend's <code>.env</code> file.</p>
        <form onSubmit={submit} className="ask">
          <label htmlFor="tok" className="sr">Admin token</label>
          <input id="tok" type="password" value={token} onChange={e => setToken(e.target.value)} placeholder="Admin token" />
          <button type="submit" disabled={!token}>Open</button>
        </form>
        {err && <p className="err">{err}</p>}
      </div>
    );
  }

  const t = data.totals;
  const issues = data.issues.filter(i => kind === "all" || i.kind === kind);
  return (
    <div className="admin">
      <header className="admin-h">
        <div>
          <h1>Admin insights</h1>
          <p className="muted">Last {data.window_days} days · anonymous questions only, no student data</p>
        </div>
        <div className="admin-actions">
          <button className="ghost" onClick={() => load()}>Refresh</button>
          <button className="ghost" onClick={doReindex}>Rebuild index</button>
          <a className="ghost" href="/">Back to assistant</a>
        </div>
      </header>
      {note && <p className="muted">{note}</p>}

      <section className="kpis">
        <div className="kpi"><span>Questions asked</span><b>{t.questions}</b></div>
        <div className="kpi"><span>Answered from sources</span><b>{pct(t.answered_rate)}</b></div>
        <div className="kpi"><span>Rated helpful</span><b>{pct(t.helpful_rate)}</b></div>
        <div className="kpi warn"><span>Sent to DSO (status risk)</span><b>{t.high_risk}</b></div>
        <div className="kpi"><span>Personal info removed</span><b>{t.pii_redacted}</b></div>
        <div className="kpi warn"><span>AI answers with unverified figures</span><b>{t.unverified_answers}{t.ai_answers ? <small> / {t.ai_answers}</small> : null}</b></div>
        <div className="kpi"><span>AI calls today / daily limit</span><b>{t.ai_calls_today}<small> / {t.daily_ai_limit}</small></b></div>
        <div className="kpi"><span>Content issues</span><b>{data.issues.length}</b></div>
        <div className="kpi"><span>Knowledge passages</span><b>{t.passages}</b></div>
      </section>

      <section className="cols">
        <div className="panel"><h2>Questions by role</h2><Bars data={data.by_role} /></div>
        <div className="panel"><h2>Questions by topic</h2><Bars data={data.by_category} /></div>
      </section>

      <section className="cols">
        <div className="panel">
          <h2>Most asked</h2>
          {data.top_questions.length ? <ol className="qlist">{data.top_questions.map(q => <li key={q.question}><span>{q.question}</span><b>{q.count}</b></li>)}</ol> : <p className="muted">No questions yet.</p>}
        </div>
        <div className="panel">
          <h2>Couldn't answer <small>(content gaps)</small></h2>
          {data.unanswered.length ? <ol className="qlist">{data.unanswered.map(q => <li key={q.question}><span>{q.question}</span><b>{q.count}</b></li>)}</ol> : <p className="muted">Nothing unanswered.</p>}
        </div>
      </section>

      <section className="panel">
        <div className="panel-h">
          <h2>Knowledge monitor</h2>
          <div className="roles">
            {["all", "conflict", "stale", "broken_link", "changed"].map(k => (
              <button key={k} className="chip" aria-pressed={kind === k} onClick={() => setKind(k)}>
                {k === "all" ? "All" : KIND_LABEL[k]} {k === "all" ? data.issues.length : data.issue_counts[k] || 0}
              </button>
            ))}
          </div>
        </div>
        <div className="issues">
          {issues.map((i, n) => (
            <div className={`issue sev-${i.severity}`} key={n}>
              <span className="pill">{KIND_LABEL[i.kind] || i.kind}</span>
              <div><p>{i.detail}</p><a href={i.url} target="_blank" rel="noopener noreferrer">{i.url}</a></div>
            </div>
          ))}
          {!issues.length && <p className="muted">No issues of this kind.</p>}
        </div>
      </section>
    </div>
  );
}
