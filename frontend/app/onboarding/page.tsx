"use client";

import { useEffect, useState } from "react";
import { AskLink, Header } from "@/components/Header";
import { getJSON } from "@/lib/api";

type Step = { title: string; detail: string; url: string };
type List = { label: string; steps: Step[] };

export default function Onboarding() {
  const [kinds, setKinds] = useState<Record<string, string>>({});
  const [kind, setKind] = useState("first_year");
  const [list, setList] = useState<List | null>(null);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [err, setErr] = useState("");

  useEffect(() => {
    getJSON<Record<string, string>>("/api/onboarding").then(setKinds).catch(e => setErr(e.message));
    try {
      const k = localStorage.getItem("onboardKind"); if (k) setKind(k);
      setDone(JSON.parse(localStorage.getItem("onboardDone") || "{}"));
    } catch {}
  }, []);
  useEffect(() => {
    getJSON<List>(`/api/onboarding/${kind}`).then(setList).catch(e => setErr(e.message));
    try { localStorage.setItem("onboardKind", kind); } catch {}
  }, [kind]);

  const toggle = (key: string) => setDone(d => {
    const next = { ...d, [key]: !d[key] };
    try { localStorage.setItem("onboardDone", JSON.stringify(next)); } catch {}
    return next;
  });
  const steps = list?.steps || [];
  const complete = steps.filter((_, i) => done[`${kind}:${i}`]).length;

  return (
    <div className="shell">
      <Header />
      <main className="tool narrow">
        <div className="tool-h">
          <h1>Getting started</h1>
          <p className="lede">A step-by-step checklist for your first term, built from Belhaven&apos;s official pages. Your progress is saved in this browser.</p>
        </div>
        <div className="roles" role="group" aria-label="Student type">
          {Object.entries(kinds).map(([k, v]) => <button key={k} className="chip" aria-pressed={kind === k} onClick={() => setKind(k)}>{v}</button>)}
        </div>
        {err && <p className="err">{err}</p>}
        {list && (
          <section className="panel">
            <div className="progress">
              <div className="progress-t"><span style={{ width: `${steps.length ? (complete / steps.length) * 100 : 0}%` }} /></div>
              <span className="muted">{complete} of {steps.length} done</span>
            </div>
            <ol className="checklist">
              {steps.map((s, i) => {
                const key = `${kind}:${i}`;
                return (
                  <li key={key} className={done[key] ? "done" : ""}>
                    <input type="checkbox" id={key} checked={!!done[key]} onChange={() => toggle(key)} />
                    <div>
                      <label htmlFor={key}><b>{s.title}</b></label>
                      <p>{s.detail}</p>
                      <div className="card-actions">
                        <a className="ghost sm" href={s.url} target="_blank" rel="noopener noreferrer">Official page</a>
                        <AskLink q={`${s.title}: what exactly do I need to do?`}>Ask about this step</AskLink>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>
        )}
      </main>
    </div>
  );
}
