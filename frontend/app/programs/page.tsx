"use client";

import { useEffect, useState } from "react";
import { AskLink, Header } from "@/components/Header";
import { getJSON } from "@/lib/api";

type Program = { name: string; degree: string; level: string; format: string; area: string; url: string; concentrations?: string[] };
type Resp = { count: number; programs: Program[]; facets: { levels: string[]; formats: string[]; areas: string[] }; source: string };

const LEVEL_ORDER = ["Associate", "Undergraduate", "Graduate", "Doctoral", "Certificate"];

export default function Programs() {
  const [q, setQ] = useState("");
  const [level, setLevel] = useState("");
  const [format, setFormat] = useState("");
  const [area, setArea] = useState("");
  const [data, setData] = useState<Resp | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      getJSON<Resp>("/api/programs", { q, level, format, area }).then(d => { setData(d); setErr(""); }).catch(e => setErr(e.message));
    }, 150);
    return () => clearTimeout(t);
  }, [q, level, format, area]);

  const levels = data ? [...data.facets.levels].sort((a, b) => LEVEL_ORDER.indexOf(a) - LEVEL_ORDER.indexOf(b)) : [];
  return (
    <div className="shell">
      <Header />
      <main className="tool">
        <div className="tool-h">
          <h1>Program Finder</h1>
          <p className="lede">Search every degree and certificate, then ask the assistant about requirements, cost or format.</p>
        </div>
        <div className="filters">
          <label htmlFor="pq" className="sr">Search programs</label>
          <input id="pq" className="field grow" value={q} onChange={e => setQ(e.target.value)} placeholder="Search, e.g. data, nursing, cyber, MBA" />
          <label htmlFor="pl" className="sr">Level</label>
          <select id="pl" className="field" value={level} onChange={e => setLevel(e.target.value)}>
            <option value="">All levels</option>{levels.map(l => <option key={l}>{l}</option>)}
          </select>
          <label htmlFor="pf" className="sr">Format</label>
          <select id="pf" className="field" value={format} onChange={e => setFormat(e.target.value)}>
            <option value="">Any format</option>{data?.facets.formats.map(f => <option key={f}>{f}</option>)}
          </select>
          <label htmlFor="pa" className="sr">Area</label>
          <select id="pa" className="field" value={area} onChange={e => setArea(e.target.value)}>
            <option value="">All areas</option>{data?.facets.areas.map(a => <option key={a}>{a}</option>)}
          </select>
        </div>
        {err && <p className="err">{err}</p>}
        {data && <p className="muted">{data.count} programs · from the official <a href={data.source} target="_blank" rel="noopener noreferrer">Program Finder</a></p>}
        <div className="cards">
          {data?.programs.map((p, i) => (
            <article className="card" key={i}>
              <div className="card-top">
                <span className="pill-s">{p.level}</span>
                <span className={`pill-s ${p.format.startsWith("Online") ? "on" : p.format.startsWith("Hybrid") ? "hy" : ""}`}>{p.format}</span>
              </div>
              <h3>{p.name}</h3>
              <p className="deg">{p.degree} · {p.area}</p>
              {p.concentrations && <p className="conc">Concentrations: {p.concentrations.join(", ")}</p>}
              <div className="card-actions">
                <a className="ghost sm" href={p.url} target="_blank" rel="noopener noreferrer">Official page</a>
                <AskLink q={`Tell me about the ${p.name} ${p.degree} program: format, requirements and cost.`}>Ask about it</AskLink>
              </div>
            </article>
          ))}
        </div>
      </main>
    </div>
  );
}
