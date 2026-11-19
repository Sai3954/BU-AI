"use client";

import { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { getJSON } from "@/lib/api";

type Office = { name: string; group: string; handles: string; phone: string; email: string; location: string; url: string };
type Resp = { count: number; offices: Office[]; groups: string[]; source: string };

const EXAMPLES = ["password", "transcript", "CPT", "housing", "counseling", "scholarship", "tutoring", "career"];

export default function Directory() {
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [data, setData] = useState<Resp | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      getJSON<Resp>("/api/directory", { q }).then(d => { setData(d); setErr(""); }).catch(e => setErr(e.message));
    }, 150);
    return () => clearTimeout(t);
  }, [q]);

  const list = data?.offices.filter(o => !group || o.group === group) || [];
  return (
    <div className="shell">
      <Header />
      <main className="tool">
        <div className="tool-h">
          <h1>Who do I contact?</h1>
          <p className="lede">Describe what you need and find the right office, with its phone, email and location.</p>
        </div>
        <div className="filters">
          <label htmlFor="dq" className="sr">What do you need help with?</label>
          <input id="dq" className="field grow" value={q} onChange={e => setQ(e.target.value)} placeholder="What do you need help with? e.g. reset my password" />
          <label htmlFor="dg" className="sr">Group</label>
          <select id="dg" className="field" value={group} onChange={e => setGroup(e.target.value)}>
            <option value="">All offices</option>{data?.groups.map(g => <option key={g}>{g}</option>)}
          </select>
        </div>
        <div className="roles">
          {EXAMPLES.map(x => <button key={x} className="chip" aria-pressed={q === x} onClick={() => setQ(q === x ? "" : x)}>{x}</button>)}
        </div>
        {err && <p className="err">{err}</p>}
        <div className="cards">
          {list.map((o, i) => (
            <article className={`card ${i === 0 && q ? "best" : ""}`} key={o.name}>
              {i === 0 && q && <span className="pill-s on">Best match</span>}
              <h3>{o.name}</h3>
              <p className="deg">{o.handles}</p>
              <dl className="contact">
                {o.phone && <><dt>Phone</dt><dd>{o.phone}</dd></>}
                {o.email && <><dt>Email</dt><dd>{o.email}</dd></>}
                {o.location && <><dt>Where</dt><dd>{o.location}</dd></>}
              </dl>
              <div className="card-actions"><a className="ghost sm" href={o.url} target="_blank" rel="noopener noreferrer">Official page</a></div>
            </article>
          ))}
        </div>
        {data && !list.length && <p className="muted">No office matches. Try different words, or ask the assistant.</p>}
        {data && <p className="muted small">Contacts from the university&apos;s <a href={data.source} target="_blank" rel="noopener noreferrer">contact directory</a>. Some pages list different numbers for the same office; the admin view flags those.</p>}
      </main>
    </div>
  );
}
