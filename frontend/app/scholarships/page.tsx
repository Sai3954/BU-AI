"use client";

import { useEffect, useState } from "react";
import { AskLink, Header } from "@/components/Header";
import { getJSON } from "@/lib/api";

type Award = { name: string; amount: string; criteria: string; deadline: string; renewal: string; fafsa_required: boolean; url: string };
type Resp = { group: string; eligible: Award[]; maybe: Award[]; note: string | null; notes: Record<string, string>; groups: Record<string, string> };

const TAGS: [string, string][] = [
  ["arts", "Arts major"], ["church", "Church member / pastor's family"], ["legacy", "Family attended Belhaven"],
  ["mississippi", "Mississippi resident"], ["military", "Military or veteran"], ["first_responder", "First responder"],
  ["alumni", "Belhaven graduate"], ["nursing", "Registered nurse"],
];

function AwardCard({ a, tone }: { a: Award; tone: "yes" | "maybe" }) {
  return (
    <article className={`card award ${tone}`}>
      <div className="card-top"><span className={`pill-s ${tone === "yes" ? "on" : ""}`}>{tone === "yes" ? "You qualify" : "May qualify"}</span></div>
      <h3>{a.name}</h3>
      <p className="amount">{a.amount}</p>
      <p className="deg">{a.criteria}</p>
      {(a.deadline || a.renewal || a.fafsa_required) && (
        <ul className="facts">
          {a.deadline && <li>Deadline: {a.deadline}</li>}
          {a.renewal && <li>Renewal: {a.renewal}</li>}
          {a.fafsa_required && <li>FAFSA required (school code 002397)</li>}
        </ul>
      )}
      <div className="card-actions">
        <a className="ghost sm" href={a.url} target="_blank" rel="noopener noreferrer">Official page</a>
        <AskLink q={`How do I get the ${a.name}?`}>Ask about it</AskLink>
      </div>
    </article>
  );
}

export default function Scholarships() {
  const [group, setGroup] = useState("first_year");
  const [gpa, setGpa] = useState("");
  const [act, setAct] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [data, setData] = useState<Resp | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    getJSON<Resp>("/api/scholarships", { group, gpa: gpa || undefined, act: act || undefined, tags: tags.join(",") })
      .then(d => { setData(d); setErr(""); }).catch(e => setErr(e.message));
  }, [group, gpa, act, tags]);

  const toggle = (t: string) => setTags(ts => ts.includes(t) ? ts.filter(x => x !== t) : [...ts, t]);
  const showScores = group === "first_year" || group === "transfer";
  return (
    <div className="shell">
      <Header />
      <main className="tool">
        <div className="tool-h">
          <h1>Scholarship &amp; Aid Finder</h1>
          <p className="lede">Answer a few questions to see the Belhaven scholarships, discounts and grants that fit you. Amounts come from the official scholarship pages.</p>
        </div>
        <section className="panel form">
          <div className="filters">
            <div className="fld"><label htmlFor="sg">I am a…</label>
              <select id="sg" className="field" value={group} onChange={e => setGroup(e.target.value)}>
                {data && Object.entries(data.groups).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select></div>
            {showScores && <div className="fld"><label htmlFor="sgpa">{group === "transfer" ? "College GPA" : "High school GPA"}</label>
              <input id="sgpa" className="field" type="number" step="0.01" min="0" max="4" value={gpa} onChange={e => setGpa(e.target.value)} placeholder="e.g. 3.4" /></div>}
            {group === "first_year" && <div className="fld"><label htmlFor="sact">ACT score (optional)</label>
              <input id="sact" className="field" type="number" min="1" max="36" value={act} onChange={e => setAct(e.target.value)} placeholder="e.g. 24" /></div>}
          </div>
          <div className="roles" role="group" aria-label="Also applies to me">
            <span className="roles-h">Also applies to me:</span>
            {TAGS.map(([k, v]) => <button key={k} className="chip" aria-pressed={tags.includes(k)} onClick={() => toggle(k)}>{v}</button>)}
          </div>
        </section>
        {err && <p className="err">{err}</p>}
        {data?.note && <div className="alert">{data.note}</div>}
        {data && (
          <>
            <h2 className="sec">Likely matches <span className="muted">({data.eligible.length})</span></h2>
            {data.eligible.length ? <div className="cards">{data.eligible.map(a => <AwardCard key={a.name} a={a} tone="yes" />)}</div>
              : <p className="muted">{showScores ? "Enter your GPA (and ACT for first-year merit awards) to see the awards you qualify for." : "No automatic matches. Check the options below."}</p>}
            {data.maybe.length > 0 && (
              <>
                <h2 className="sec">Worth checking <span className="muted">({data.maybe.length})</span></h2>
                <div className="cards">{data.maybe.map(a => <AwardCard key={a.name} a={a} tone="maybe" />)}</div>
              </>
            )}
            <p className="muted small">Matching several merit awards doesn&apos;t mean you receive all of them; Financial Aid decides your final package. {data.notes.rates_year} {data.notes.stacking} Final awards are decided by Financial Aid (601-968-5933, studentaid@belhaven.edu).</p>
          </>
        )}
      </main>
    </div>
  );
}
