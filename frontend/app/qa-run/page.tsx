"use client";

/* Temporary QA runner (removed after the 300-question test). Asks each question through the real
   /api/chat, one at a time, under the 12-per-minute limit, and prints one result line per question. */
import { useEffect, useState } from "react";
import { streamChat } from "@/lib/api";

type Q = { id: number; group: string; role: string; q: string };
const ROLE: Record<string, string> = { "Prospective student": "prospective", Undergraduate: "undergraduate", Graduate: "graduate",
  Doctoral: "doctoral", International: "international", Online: "online", "Faculty / Staff": "faculty", Alumni: "alumni" };
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms));

function askOnce(q: Q): Promise<any> {
  return new Promise(resolve => {
    const t0 = performance.now();
    let text = ""; let srcs: any[] = []; let err = "";
    streamChat({ question: q.q, role: ROLE[q.role] || "", category: "", history: [] }, {
      onSources: (s: any) => { srcs = s; },
      onDelta: (t: string) => { text += t; },
      onReplace: (t: string) => { text = t; },
      onStage: () => {},
      onDone: (_id: any, checks: any, _v: any, extra: any) => resolve({ id: q.id, s: +((performance.now() - t0) / 1000).toFixed(1), answered: extra?.answered ?? null,
        n: srcs.length, src: srcs.slice(0, 2).map((x: any) => x.url.replace("https://www.belhaven.edu", "")),
        warn: [...checks.unverified, ...checks.misattributed, ...checks.unsupported_claims].slice(0, 4), uncited: checks.uncited.length,
        ho: extra?.handoff?.name || "", a: text.replace(/\s+/g, " ").slice(0, 520) }),
      onError: (m: string) => { err = m; resolve({ id: q.id, err }); },
    } as any);
  });
}

export default function QARun() {
  const [lines, setLines] = useState<string[]>([]);
  const [status, setStatus] = useState("waiting");
  useEffect(() => {
    const p = new URLSearchParams(location.search);
    if (p.get("go") !== "1") { setStatus("add ?go=1&from=1&to=25"); return; }
    const from = +(p.get("from") || 1), to = +(p.get("to") || 25);
    (async () => {
      const all: Q[] = await (await fetch("/qa/questions.json")).json();
      const qs = all.filter(q => q.id >= from && q.id <= to);
      for (let i = 0; i < qs.length; i++) {
        setStatus(`running ${i + 1}/${qs.length}`);
        const start = Date.now();
        let r = await askOnce(qs[i]);
        for (let k = 0; k < 3 && r.err; k++) { await sleep(20000); r = await askOnce(qs[i]); }
        setLines(l => [...l, JSON.stringify(r)]);
        const wait = 5600 - (Date.now() - start);
        if (wait > 0) await sleep(wait);
      }
      setStatus(`DONE ${qs.length}`);
    })();
  }, []);
  return (
    <main style={{ padding: 16, fontFamily: "monospace", fontSize: 12 }}>
      <meta name="robots" content="noindex" />
      <p id="status">{status}</p>
      <pre id="out" style={{ whiteSpace: "pre-wrap" }}>{lines.join("\n")}</pre>
    </main>
  );
}
