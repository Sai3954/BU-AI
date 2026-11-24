import { Fragment, ReactNode } from "react";
import type { Source } from "@/lib/api";
import { sourceMeta } from "@/lib/sources";

const PhoneIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z" />
  </svg>
);
const MailIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="2" y="4" width="20" height="16" rx="2" /><path d="m22 7-10 6L2 7" />
  </svg>
);

// Emails, US phone numbers (601-968-5933, (601) 968-5933, 800.960.5940) and web addresses in answer text.
const CONTACT = /([\w.+-]+@[\w-]+(?:\.[\w-]+)+|\(?\b\d{3}\)?[-. ]\d{3}[-. ]\d{4}\b|https?:\/\/[^\s)]+[^\s).,;])/g;

const PLACEHOLDER = /^(first[-_.]?(name)?[-_.]?last(name)?|first[-_.]?name|last[-_.]?name|your[-_.]?name|user[-_.]?name|name|email|example)@|@example\./i;

/** Plain text with emails, phone numbers and links made tappable. */
function contacts(text: string, key: string): ReactNode[] {
  return text.split(CONTACT).map((p, i) => {
    const k = `${key}-c${i}`;
    if (i % 2 === 0) return p ? <Fragment key={k}>{p}</Fragment> : null;
    // A format example ("firstnamelastname@students.belhaven.edu") is not a real address: show it, don't link it.
    if (p.includes("@") && PLACEHOLDER.test(p)) return <Fragment key={k}>{p}</Fragment>;
    if (p.includes("@")) return <a key={k} className="contact-link" href={`mailto:${p}`}><MailIcon />{p}</a>;
    if (/^https?:/.test(p)) return <a key={k} href={p} target="_blank" rel="noopener noreferrer">{p.replace(/^https?:\/\//, "")}</a>;
    return <a key={k} className="contact-link" href={`tel:+1${p.replace(/\D/g, "")}`}><PhoneIcon />{p}</a>;
  });
}

/** Render the model's plain text: paragraphs, "- " bullets, **bold**, [n] citation chips, tappable contacts. */
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
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={k}>{contacts(p.slice(2, -2), k)}</strong>;
    return <Fragment key={k}>{contacts(p, k)}</Fragment>;
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
    else {
      flush();
      // The closing "Contact: office, phone, email" line gets its own card.
      const contact = /^\s*(\*\*)?(contact|contacts|who to contact|reach)\b/i.test(line) && CONTACT.test(line);
      CONTACT.lastIndex = 0;
      out.push(<p key={i} className={contact ? "contact-line" : undefined}>{inline(line, sources, `p${i}`)}</p>);
    }
  });
  flush();
  return <>{out}</>;
}

export function SourceList({ sources, text }: { sources: Source[]; text: string }) {
  const used = new Set(Array.from(text.matchAll(/\[(\d+)\]/g)).map(m => Number(m[1])));
  // Only the sources the answer actually cites. An answer that cites nothing (off-topic, crisis) shows no source list,
  // so unrelated pages are never presented as "official sources".
  const shown = sources.map((s, i) => ({ s, n: i + 1 })).filter(x => used.has(x.n));
  if (!shown.length) return null;
  return (
    <div className="sources">
      <div className="sources-h">Official sources</div>
      {shown.map(({ s, n }) => (
        <div className="src" key={n}>
          <span className="src-n">{n}</span>
          <span className="src-body">
            <a href={s.url} target="_blank" rel="noopener noreferrer">{sourceMeta(s).title}</a>
            <span className="src-meta">
              <span className="src-kind">{sourceMeta(s).kind}</span>
              {sourceMeta(s).older && <span className="src-old">Older source</span>}
              <span className="age">{sourceMeta(s).date || "Date not listed"}</span>
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}
