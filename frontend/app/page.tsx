"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Answer, SourceList } from "@/components/Answer";
import { Header } from "@/components/Header";
import { Activity, ActivityEvent, Stage } from "@/components/Activity";
import { Handoff } from "@/components/Handoff";
import type { Office } from "@/lib/api";
import { Checks, Flags, Meta, Source, Turn, getMeta, sendFeedback, streamChat } from "@/lib/api";

const ROLES: { id: string; label: string }[] = [
  { id: "prospective", label: "Prospective student" },
  { id: "undergraduate", label: "Undergraduate" },
  { id: "graduate", label: "Graduate" },
  { id: "doctoral", label: "Doctoral" },
  { id: "international", label: "International" },
  { id: "online", label: "Online" },
  { id: "faculty", label: "Faculty / Staff" },
  { id: "alumni", label: "Alumni" },
];

const SERVICES: { cat: string; label: string; ask: string; icon: string }[] = [
  { cat: "Admissions", label: "Admissions", ask: "How do I apply, and what are the admission requirements?", icon: "M4 20h16M6 20V10l6-5 6 5v10M10 20v-5h4v5" },
  { cat: "Academics", label: "Academics", ask: "Where do I find the academic calendar and exam schedule?", icon: "M3 7l9-4 9 4-9 4-9-4zm3 2v5c0 2 3 4 6 4s6-2 6-4V9" },
  { cat: "Financial Aid", label: "Financial Aid", ask: "What financial aid and scholarships are available?", icon: "M4 7h16v10H4zM4 11h16M8 15h3" },
  { cat: "International", label: "Immigration & CPT/OPT", ask: "How do I request CPT?", icon: "M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18" },
  { cat: "Campus Life", label: "Housing & Dining", ask: "What are the dining hours and meal plan options?", icon: "M5 21V9l7-5 7 5v12M9 21v-6h6v6" },
  { cat: "Careers", label: "Careers", ask: "Who can help me with my resume and finding an internship?", icon: "M4 8h16v11H4zM9 8V5h6v3M4 13h16" },
  { cat: "Events", label: "Events", ask: "What events are coming up on campus?", icon: "M5 5h14v15H5zM5 9h14M9 3v4M15 3v4" },
  { cat: "Library", label: "Library", ask: "What are the library hours and how do I get research help?", icon: "M5 4h4v16H5zM10 4h4v16h-4zM15 5l3.5-1 3 15-3.5 1z" },
  { cat: "IT Support", label: "IT Support", ask: "I forgot my email password. How do I reset it?", icon: "M4 5h16v11H4zM8 20h8M12 16v4" },
  { cat: "Wellness", label: "Wellness & Support", ask: "Where can I get tutoring or disability accommodations?", icon: "M12 20s-7-4.5-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.5-7 10-7 10z" },
  { cat: "Student Services", label: "Student Services", ask: "Who do I contact for help with my student account?", icon: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 4-6 8-6s8 2 8 6" },
  { cat: "Alumni", label: "Alumni", ask: "How can alumni request transcripts and stay connected?", icon: "M12 3l2.5 5 5.5.8-4 3.9.9 5.5L12 15.6 7.1 18.2l.9-5.5-4-3.9 5.5-.8z" },
];

type Msg = {
  id: number; q: string; text: string; sources: Source[]; flags?: Flags;
  status: "searching" | "streaming" | "done" | "error"; queryId?: number; rated?: boolean; checks?: Checks;
  stage: Stage; events: ActivityEvent[]; started: number; reason?: "" | "wrong" | "missing" | "unclear"; askWhy?: boolean;
  copied?: boolean; votes?: { likes: number; dislikes: number }; myVote?: "up" | "down";
  answered?: boolean; handoff?: Office | null;
};

/** Follow-up suggestions grounded in what was found: titles of retrieved FAQ pages that are themselves
 *  questions (so Bela can answer them), not already asked. */
function suggestions(m: Msg, asked: string[]): string[] {
  const norm = (x: string) => x.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();
  const STOP = new Set("a an the i my me do does can to of for in on is are be at before after how what when where who".split(" "));
  const words = (x: string) => new Set(norm(x).split(/\s+/).filter(w => w.length > 2 && !STOP.has(w)));
  const askedWords = asked.map(words);
  const tooClose = (t: string) => { const w = words(t); return askedWords.some(a => {
    const common = Array.from(w).filter(x => a.has(x)).length; return w.size > 0 && common / Math.min(w.size, a.size || 1) >= 0.5; }); };
  const seen = new Set(asked.map(norm));
  const out: string[] = [];
  for (const s of m.sources) {
    const t = s.title.replace(/^(faq|frequently asked questions?)\s*[-–:]\s*/i, "").trim();
    if (!t.endsWith("?") || t.length > 70 || seen.has(norm(t)) || tooClose(t)) continue;
    seen.add(norm(t)); out.push(t);
    if (out.length === 3) break;
  }
  return out;
}

/* eslint-disable @typescript-eslint/no-explicit-any */
function getRecognizer(): any {
  if (typeof window === "undefined") return null;
  const R = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
  return R ? new R() : null;
}

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
  );
}

function CheckNote({ c }: { c: Checks }) {
  const items: string[] = [];
  if (c.unverified.length) items.push(`${c.unverified.join(", ")} ${c.unverified.length > 1 ? "don't" : "doesn't"} appear in the official sources`);
  if (c.misattributed.length) items.push(`${c.misattributed.join(", ")} ${c.misattributed.length > 1 ? "don't" : "doesn't"} match what the cited page says`);
  if (c.unsupported_claims.length) items.push(`the claim "${c.unsupported_claims.join('", "')}" isn't stated in the sources`);
  if (c.uncited.length) items.push(`${c.uncited.length} statement${c.uncited.length > 1 ? "s have" : " has"} no source`);
  if (c.ai_flags.length) items.push(`a second review found ${c.ai_flags.length} statement${c.ai_flags.length > 1 ? "s" : ""} the sources don't support`);
  if (!items.length) return null;
  return <div className="alert"><b>Check before relying on this:</b> {items.join("; ")}. Confirm with the linked page.</div>;
}

export default function Home() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [apiDown, setApiDown] = useState(false);
  const [embed, setEmbed] = useState(false);
  const [role, setRole] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [canVoice, setCanVoice] = useState(false);
  const recRef = useRef<any>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    getMeta().then(setMeta).catch(() => setApiDown(true));
    let savedRole = "";
    try { savedRole = localStorage.getItem("role") || ""; if (savedRole) setRole(savedRole); } catch {}
    setCanVoice(!!getRecognizer());
    const params = new URLSearchParams(window.location.search);
    if (params.get("embed") === "1") {
      setEmbed(true);
      window.addEventListener("keydown", e => { if (e.key === "Escape") window.parent.postMessage({ type: "buai-close" }, "*"); });
    }
    const q = params.get("q");
    if (q) {
      window.history.replaceState(null, "", params.get("embed") === "1" ? "/?embed=1" : "/");
      setTimeout(() => ask(q, params.get("cat") || "", savedRole), 0);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleVoice = () => {
    if (listening) { recRef.current?.stop(); return; }
    const rec = getRecognizer();
    if (!rec) return;
    rec.lang = navigator.language || "en-US";
    rec.interimResults = true;
    rec.onresult = (e: any) => setInput(Array.from(e.results).map((r: any) => r[0].transcript).join(" "));
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    setListening(true);
    rec.start();
  };
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs]);

  const pickRole = (r: string) => {
    const next = r === role ? "" : r;
    setRole(next);
    try { localStorage.setItem("role", next); } catch {}
  };

  const update = (id: number, patch: Partial<Msg> | ((m: Msg) => Partial<Msg>)) =>
    setMsgs(ms => ms.map(m => (m.id === id ? { ...m, ...(typeof patch === "function" ? patch(m) : patch) } : m)));

  async function ask(question: string, category = "", roleOverride?: string) {
    const q = question.trim();
    if (!q || busy) return;
    setInput(""); setBusy(true);
    const id = Date.now();
    const history: Turn[] = msgs.flatMap(m => [
      { role: "user" as const, text: m.q },
      { role: "assistant" as const, text: m.text.replace(/\[\d+\]/g, "") },
    ]).slice(-6);
    const started = Date.now();
    const at = () => Date.now() - started;
    setMsgs(ms => [...ms, { id, q, text: "", sources: [], status: "searching", stage: "searching", started,
      events: [{ at: 0, kind: "search", label: "Searching Belhaven’s official pages" }] }]);
    abortRef.current = new AbortController();
    await streamChat({ question: q, role: roleOverride ?? role, category, history }, {
      onSources: (sources, flags) => update(id, m => {
        const pages = new Set(sources.map(s => s.url.split("#")[0])).size;
        return { sources, flags, status: "streaming", stage: "reading", events: [...m.events, { at: at(), kind: "found",
          label: sources.length ? `Found ${sources.length} passage${sources.length > 1 ? "s" : ""} on ${pages} official page${pages > 1 ? "s" : ""} and read them` : "No official page answers this" }] };
      }),
      onDelta: t => update(id, m => m.stage === "writing" ? { text: m.text + t }
        : { text: m.text + t, stage: "writing", events: [...m.events, { at: at(), kind: "write", label: "Wrote the answer from those sources" }] }),
      onReplace: text => update(id, { text }),
      onStage: st => { if (st === "verifying") update(id, m => ({ stage: "verifying", events: [...m.events, { at: at(), kind: "verify", label: "Checked every fact against the sources" }] })); },
      onDone: (queryId, checks, votes, extra) => update(id, m => ({ status: "done", stage: "done", queryId, checks, votes,
        answered: extra?.answered, handoff: extra?.handoff,
        events: [...m.events, { at: at(), kind: "ready", label: "Answer ready" }] })),
      onError: msg => update(id, m => ({ status: "error", stage: "error", text: m.text || msg })),
    }, abortRef.current.signal);
    setBusy(false);
  }

  const submit = (e: FormEvent) => { e.preventDefault(); ask(input); };
  const rate = (m: Msg, helpful: boolean) => {
    if (helpful) { if (m.queryId) sendFeedback(m.queryId, true); update(m.id, v => ({ rated: true, myVote: "up", votes: bump(v.votes, "likes") })); }
    else update(m.id, { askWhy: true });
  };
  const why = (m: Msg, reason: "wrong" | "missing" | "unclear") => {
    if (m.queryId) sendFeedback(m.queryId, false, reason);
    update(m.id, v => ({ rated: true, askWhy: false, reason, myVote: "down", votes: bump(v.votes, "dislikes") }));
  };
  const bump = (v: Msg["votes"], k: "likes" | "dislikes") => ({ likes: v?.likes ?? 0, dislikes: v?.dislikes ?? 0, [k]: (v?.[k] ?? 0) + 1 });
  const copy = async (m: Msg) => {
    const used = new Set(Array.from(m.text.matchAll(/\[(\d+)\]/g)).map(x => Number(x[1])));
    const src = m.sources.map((s, i) => ({ s, n: i + 1 })).filter(x => used.has(x.n)).map(x => `[${x.n}] ${x.s.title}: ${x.s.url}`);
    try { await navigator.clipboard.writeText(m.text + (src.length ? "\n\nSources:\n" + src.join("\n") : "")); update(m.id, { copied: true }); } catch { /* clipboard blocked */ }
  };
  const reset = () => { abortRef.current?.abort(); setMsgs([]); setBusy(false); };

  const name = meta?.app_name || process.env.NEXT_PUBLIC_APP_NAME || "Bela";
  const chatting = msgs.length > 0;

  return (
    <div className={embed ? "shell embed" : "shell"}>
      {!embed && <Header name={name} tagline={meta?.tagline} onHome={reset} />}

      {apiDown && (
        <div className="banner">The assistant service isn't running. Start the backend (see README), then refresh this page.</div>
      )}

      <main className={chatting ? "main chat" : "main home"}>
        {!chatting && (
          <section className="hero">
            <h1>{embed ? "Hi! How can I help?" : "Your university. Your AI assistant."}</h1>
            <p className="lede">{embed ? "Ask about admissions, aid, CPT/OPT, classes or campus life. Answers link to official Belhaven pages." : <>Ask anything about admissions, classes, financial aid, immigration, campus life and student services. Every answer links to the official {meta?.university || "university"} page it came from.</>}</p>
            <div className="roles" role="group" aria-label="I am a">
              <span className="roles-h">I am a…</span>
              {ROLES.map(r => (
                <button key={r.id} className="chip" aria-pressed={role === r.id} onClick={() => pickRole(r.id)}>{r.label}</button>
              ))}
            </div>
          </section>
        )}

        {chatting && (
          <div className="chatbar">
            <span className="muted">{role ? `Answering as: ${ROLES.find(r => r.id === role)?.label}` : "Tip: pick who you are on the home page for tailored answers."}</span>
            <button className="ghost sm" onClick={reset}>New chat</button>
          </div>
        )}
        {chatting && (
          <div className="thread" aria-live="polite">
            {msgs.map(m => (
              <div key={m.id} className="turn">
                <div className="q">{m.q}</div>
                <div className="a">
                  {m.flags?.crisis && (
                    <div className="alert crisis"><b>You're not alone.</b> If you're in crisis, call or text <b>988</b> (Suicide &amp; Crisis Lifeline) now, or call <b>911</b> in an emergency. Belhaven Student Care: 601-968-8865.</div>
                  )}
                  {m.flags?.high_risk && (
                    <div className="alert"><b>Talk to your DSO first.</b> Status problems need a person to review your case. Open a ticket at <a href="https://igsupport.belhaven.edu/open.php" target="_blank" rel="noopener noreferrer">igsupport.belhaven.edu</a> and consider an immigration attorney. Don't travel or work until it's resolved.</div>
                  )}
                  {m.flags?.pii_removed && m.flags.pii_removed.length > 0 && (
                    <p className="note">For your privacy, personal details ({m.flags.pii_removed.join(", ").toLowerCase().replace(/_/g, " ")}) were removed before your question was processed.</p>
                  )}
                  <Activity stage={m.stage} events={m.events} sources={m.sources} checks={m.checks} />
                  {m.text && <Answer text={m.text} sources={m.sources} />}
                  {m.status === "done" && m.checks && <CheckNote c={m.checks} />}
                  {m.status === "done" && m.flags?.conflicts && m.flags.conflicts.length > 0 && (
                    <p className="note conflict">
                      <b>Official pages differ:</b>{" "}
                      {m.flags.conflicts.map(c => `${c.fact}: ` + c.values.map(v => `${v.value} (source ${v.sources.join(", ")})`).join(" vs ")).join("; ")}.
                      {" "}Please confirm with the office before relying on it.
                    </p>
                  )}
                  {m.status === "done" && <SourceList sources={m.sources} text={m.text} />}
                  {m.status === "done" && m.queryId && (
                    <div className="rate">
                      <button className="icon-btn" onClick={() => copy(m)} aria-label="Copy answer with sources" title={m.copied ? "Copied" : "Copy answer with sources"}>
                        {m.copied ? <span aria-hidden="true">✓</span> : <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 012-2h10" /></svg>}
                      </button>
                      <button className={`icon-btn vote ${m.myVote === "up" ? "on" : ""}`} onClick={() => !m.rated && rate(m, true)} disabled={m.rated}
                        aria-label={`Helpful${m.votes?.likes ? `, ${m.votes.likes} so far` : ""}`} title="Helpful">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true"><path d="M7 11v9H4v-9zM7 11l4-8a2 2 0 012 2v4h5a2 2 0 012 2.3l-1.2 7A2 2 0 0116.8 20H7" /></svg>
                        {m.votes?.likes ? <span className="vcount">{m.votes.likes}</span> : null}
                      </button>
                      <button className={`icon-btn vote ${m.myVote === "down" || m.askWhy ? "on" : ""}`} onClick={() => !m.rated && rate(m, false)} disabled={m.rated}
                        aria-label={`Not helpful${m.votes?.dislikes ? `, ${m.votes.dislikes} so far` : ""}`} title="Not helpful">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true"><path d="M17 13V4h3v9zM17 13l-4 8a2 2 0 01-2-2v-4H6a2 2 0 01-2-2.3l1.2-7A2 2 0 017.2 4H17" /></svg>
                        {m.votes?.dislikes ? <span className="vcount">{m.votes.dislikes}</span> : null}
                      </button>
                      {m.rated ? <span className="muted">{m.reason ? "Thanks, that helps us improve." : "Thanks for the feedback."}</span> : (<>
                        {m.askWhy && (<span className="why"><span className="muted">What was wrong?</span>
                          <button className="pill-btn" onClick={() => why(m, "wrong")}>Wrong info</button>
                          <button className="pill-btn" onClick={() => why(m, "missing")}>Missing info</button>
                          <button className="pill-btn" onClick={() => why(m, "unclear")}>Hard to understand</button></span>)}
                      </>)}
                    </div>
                  )}
                  {m.status === "done" && !m.flags?.crisis && (() => {
                    // Prominent when Bela couldn't answer, for immigration-status risk, or after a 👎; else a small link on the latest answer.
                    const prominent = m.answered === false || !!m.flags?.high_risk || m.myVote === "down";
                    return (prominent || m.id === msgs[msgs.length - 1]?.id) ? (
                      <Handoff question={m.q} sources={m.sources} text={m.text} suggested={m.handoff} queryId={m.queryId} prominent={prominent} />
                    ) : null;
                  })()}
                  {m.status === "done" && m.id === msgs[msgs.length - 1]?.id && suggestions(m, msgs.map(x => x.q)).length > 0 && (
                    <div className="suggest">
                      <div className="muted">You might also ask</div>
                      <div className="suggest-row">
                        {suggestions(m, msgs.map(x => x.q)).map(sq => (
                          <button key={sq} className="suggest-chip" onClick={() => ask(sq)} disabled={busy}>
                            <svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path d="M12 3l1.6 4.9L18.5 9.5l-4.9 1.6L12 16l-1.6-4.9L5.5 9.5l4.9-1.6z" fill="currentColor" /></svg>{sq}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={endRef} />
          </div>
        )}

        <form className={chatting ? "ask docked" : "ask"} onSubmit={submit}>
          <label htmlFor="q" className="sr">Ask a question</label>
          <input id="q" value={input} onChange={e => setInput(e.target.value)} autoComplete="off"
            placeholder={chatting ? "Ask a follow-up…" : "Ask Bela about admissions, classes, aid…"} />
          {canVoice && (
            <button type="button" className={`mic ${listening ? "on" : ""}`} onClick={toggleVoice}
              aria-pressed={listening} aria-label={listening ? "Stop voice input" : "Ask by voice"} title="Ask by voice">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
                <rect x="9" y="3" width="6" height="11" rx="3" /><path d="M5 11a7 7 0 0014 0M12 18v3" />
              </svg>
            </button>
          )}
          <button type="submit" disabled={busy || !input.trim()}>Ask</button>
        </form>

        {!chatting && (
          <section className="services" aria-label="Explore university services">
            <h2>Explore university services</h2>
            <div className="grid">
              {SERVICES.map(s => (
                <button key={s.cat} className="tile" onClick={() => ask(s.ask, s.cat)}>
                  <span className="ic"><Icon d={s.icon} /></span>
                  <span className="t">{s.label}</span>
                  <span className="ex">{s.ask}</span>
                  {meta?.categories?.[s.cat] ? <span className="count">{meta.categories[s.cat]} topics</span> : null}
                </button>
              ))}
            </div>
          </section>
        )}
      </main>

      {embed && !chatting && (
        <nav className="embed-tools" aria-label="Bela tools">
          <a href="/programs" target="_blank" rel="noopener noreferrer">Programs</a>
          <a href="/scholarships" target="_blank" rel="noopener noreferrer">Scholarships</a>
          <a href="/directory" target="_blank" rel="noopener noreferrer">Contacts</a>
          <a href="/onboarding" target="_blank" rel="noopener noreferrer">Getting started</a>
        </nav>
      )}
      <footer className="foot">
        <span>{meta ? `${meta.passages} passages from ${meta.sources} official pages · ${meta.ai ? "AI answers" : "Official-text answers (no AI key set)"} · ${meta.retrieval} search` : "Loading…"}</span>
        <span>Not an official {meta?.university || "university"} service. Confirm immigration decisions with your DSO. <a href="/admin">Admin</a></span>
      </footer>
    </div>
  );
}
