"use client";
import { useEffect, useMemo, useState } from "react";
import { getOffices, logHandoff, type Office, type Source } from "@/lib/api";
import { cleanTitle } from "@/lib/sources";

/** Human handoff: when Bela can't fully help, prepare a request to the right office.
 *  The student reviews it and sends it themselves (email, DSO ticket or phone); nothing is sent for them. */
export function Handoff({ question, sources, text, suggested, queryId, prominent }: {
  question: string; sources: Source[]; text: string; suggested?: Office | null; queryId?: number; prominent: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [offices, setOffices] = useState<Office[]>([]);
  const [name, setName] = useState(suggested?.name || "");
  const [q, setQ] = useState(question);
  const [details, setDetails] = useState("");
  const [done, setDone] = useState("");

  useEffect(() => { if (open && !offices.length) getOffices().then(setOffices); }, [open, offices.length]);
  const office = useMemo(() => offices.find(o => o.name === name) || (suggested?.name === name ? suggested : undefined), [offices, name, suggested]);

  const cited = useMemo(() => {
    const used = new Set(Array.from(text.matchAll(/\[(\d+)\]/g)).map(x => Number(x[1])));
    const seen = new Set<string>();
    return sources.filter((s, i) => used.has(i + 1)).filter(s => !seen.has(s.url) && seen.add(s.url)).slice(0, 4);
  }, [sources, text]);

  const body = [
    "Hello,", "",
    q.trim(), ...(details.trim() ? ["", details.trim()] : []),
    ...(cited.length ? ["", "Pages I already looked at:", ...cited.map(s => `- ${cleanTitle(s.title)}: ${s.url}`)] : []),
    "", "Thank you,", "[Your name]",
  ].join("\n");
  const subject = `Question: ${q.trim().slice(0, 70)}`;
  const isTicket = !!office?.url && /open\.php/.test(office.url);

  const record = (how: string) => { if (queryId && office) logHandoff(queryId, office.name); setDone(how); };
  const copy = async () => { try { await navigator.clipboard.writeText(body); record("Request copied. Paste it into your message to the office."); } catch { setDone("Couldn't copy. Select the text above and copy it."); } };

  if (!open) {
    return prominent ? (
      <div className="handoff-card">
        <div><b>Get help from a person</b>
          <p className="muted">{suggested ? <>Bela suggests <b>{suggested.name}</b>. {suggested.reason}</> : "Bela can prepare a request to the right university office."}</p></div>
        <button className="btn-primary" onClick={() => setOpen(true)}>Prepare a request</button>
      </div>
    ) : (
      <button className="handoff-link" onClick={() => setOpen(true)}>Need a person? Prepare a request{suggested ? ` to ${suggested.name}` : " to an office"}</button>
    );
  }

  return (
    <div className="handoff-card open" role="region" aria-label="Prepare a request to a university office">
      <div className="handoff-head"><b>Prepare a request</b><button className="icon-btn" aria-label="Close" onClick={() => setOpen(false)}>✕</button></div>
      <label className="hf">Office
        <select value={name} onChange={e => { setName(e.target.value); setDone(""); }}>
          {!name && <option value="">Choose an office…</option>}
          {(offices.length ? offices : suggested ? [suggested] : []).map(o => <option key={o.name} value={o.name}>{o.name}</option>)}
        </select>
        {office?.handles && <span className="muted">Handles: {office.handles}</span>}
      </label>
      <label className="hf">Your question
        <textarea rows={2} value={q} onChange={e => setQ(e.target.value)} />
      </label>
      <label className="hf">Anything else they should know <span className="muted">(optional)</span>
        <textarea rows={2} value={details} onChange={e => setDetails(e.target.value)} placeholder="For example: my program and start term" />
      </label>
      <p className="handoff-privacy">Don’t include your student ID, SEVIS number or passwords. The office will ask for what they need.</p>
      {office && (
        <div className="handoff-actions">
          {isTicket ? (
            <a className="btn-primary" href={office.url} target="_blank" rel="noopener noreferrer" onClick={() => { navigator.clipboard?.writeText(body).catch(() => {}); record("Ticket page opened, and your request was copied. Paste it into the ticket."); }}>Open a DSO support ticket</a>
          ) : office.email ? (
            <a className="btn-primary" href={`mailto:${office.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`} onClick={() => record(`Your email app opened with the request to ${office.email}. Review it, then send.`)}>Open email to {office.email}</a>
          ) : office.phone ? (
            <a className="btn-primary" href={`tel:${office.phone.replace(/[^\d+]/g, "")}`} onClick={() => record(`Calling ${office.phone}.`)}>Call {office.phone}</a>
          ) : null}
          <button className="btn-secondary" onClick={copy}>Copy request</button>
          {office.phone && !isTicket && office.email && <span className="muted">or call {office.phone}</span>}
          {office.url && !isTicket && <a href={office.url} target="_blank" rel="noopener noreferrer">Office page</a>}
        </div>
      )}
      {done && <p className="handoff-done" role="status">✓ {done}</p>}
      <details className="handoff-preview"><summary>Preview the request</summary><pre>{body}</pre></details>
    </div>
  );
}
