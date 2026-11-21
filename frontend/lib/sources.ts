import type { Source } from "./api";

/** How a source is described to students: what kind of page it is, and its date only when the page
 *  itself shows one. Never "current page": being on the website today says nothing about how recent it is. */
export type SourceMeta = { title: string; kind: "University webpage" | "FAQ" | "PDF document"; date: string; older: boolean };

const AGE = /(\d+|a|an)\s+(day|week|month|year)s?\s+ago/i;

export function sourceMeta(s: Source): SourceMeta {
  const u = s.updated || "";
  const kind = /pdf/i.test(u) || /\.pdf($|\?)/i.test(s.url) ? "PDF document"
    : /\/kb\/faq\.php|\/faq/i.test(s.url) || /faq/i.test(s.title) ? "FAQ" : "University webpage";
  const m = AGE.exec(u);
  let date = "", older = false;
  if (m) {
    const n = /^an?$/i.test(m[1]) ? 1 : Number(m[1]);
    const unit = m[2].toLowerCase();
    date = `Updated about ${n} ${unit}${n > 1 ? "s" : ""} ago`;
    older = unit === "year" || (unit === "month" && n >= 12);
  }
  return { title: cleanTitle(s.title), kind, date, older };
}

export function cleanTitle(t: string): string {
  return t
    .replace(/\s*\|\s*Belhaven University\s*$/i, "")
    .replace(/\s*\((PDF)\)\s*$/i, "")
    .replace(/\bCpt\b/g, "CPT").replace(/\bOpt\b/g, "OPT").replace(/\bSevis\b/g, "SEVIS").replace(/\bDso\b/g, "DSO")
    .trim();
}
