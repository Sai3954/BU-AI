const RAW_API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Where the assistant API lives.
 *  On Render the website is "<name>-web.onrender.com" and the API "<name>-api.onrender.com", so the browser can
 *  work it out from its own address; this keeps working even if the build-time setting is missing or internal. */
function apiBase(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h.endsWith(".onrender.com") && h.includes("-web")) return `https://${h.replace("-web", "-api")}`;
  }
  return RAW_API.includes("://") ? RAW_API : `https://${RAW_API}`;
}
export const API = apiBase();

export type Source = { title: string; url: string; category: string; updated: string; text: string };
export type Conflict = { fact: string; values: { value: string; sources: number[] }[] };
export type Flags = { high_risk: boolean; crisis: boolean; pii_removed?: string[]; level?: string; conflicts?: Conflict[] };
export type Meta = {
  app_name: string; tagline: string; university: string; roles: string[];
  categories: Record<string, number>; sources: number; passages: number;
  last_refresh: string | null; ai: boolean; retrieval: string;
};
export type Checks = { unverified: string[]; misattributed: string[]; uncited: string[]; unsupported_claims: string[]; ai_flags: string[] };
export type Turn = { role: "user" | "assistant"; text: string };

export async function getMeta(): Promise<Meta> {
  const r = await fetch(`${API}/api/meta`, { cache: "no-store" });
  if (!r.ok) throw new Error("API unavailable");
  return r.json();
}

type Handlers = {
  onSources: (s: Source[], f: Flags) => void;
  onDelta: (t: string) => void;
  onDone: (queryId: number, checks: Checks, votes?: { likes: number; dislikes: number }) => void;
  onReplace?: (t: string) => void;
  onStage?: (stage: string) => void;
  onError: (msg: string) => void;
};

/** POST a question and read the server-sent event stream. */
export async function streamChat(
  body: { question: string; role: string; category: string; history: Turn[] },
  h: Handlers,
  signal?: AbortSignal
) {
  let res: Response;
  try {
    res = await fetch(`${API}/api/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal,
    });
  } catch {
    h.onError("Can't reach the assistant service. Check that the backend is running."); return;
  }
  if (res.status === 429) { h.onError("You're asking very quickly. Wait a minute, then try again."); return; }
  if (!res.ok || !res.body) { h.onError(`The assistant returned an error (${res.status}).`); return; }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, i); buf = buf.slice(i + 2);
      const ev = /^event: (.*)$/m.exec(raw)?.[1];
      const data = /^data: (.*)$/m.exec(raw)?.[1];
      if (!ev || !data) continue;
      const d = JSON.parse(data);
      if (ev === "sources") h.onSources(d.sources, d.flags);
      else if (ev === "delta") h.onDelta(d.text);
      else if (ev === "replace") h.onReplace?.(d.text);
      else if (ev === "stage") h.onStage?.(d.stage);
      else if (ev === "done") h.onDone(d.query_id, { unverified: d.unverified || [], misattributed: d.misattributed || [], uncited: d.uncited || [], unsupported_claims: d.unsupported_claims || [], ai_flags: d.ai_flags || [] }, d.votes);
      else if (ev === "error") h.onError(d.message);
    }
  }
}

export async function sendFeedback(queryId: number, helpful: boolean, reason: "" | "wrong" | "missing" | "unclear" = "") {
  await fetch(`${API}/api/feedback`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query_id: queryId, helpful, reason }),
  }).catch(() => {});
}

export async function getAdminSummary(token: string, days = 30) {
  const r = await fetch(`${API}/api/admin/summary?days=${days}`, { headers: { "X-Admin-Token": token }, cache: "no-store" });
  if (r.status === 401) throw new Error("That admin token isn't correct.");
  if (r.status === 503) {
    const d = await r.json().catch(() => ({}));
    throw new Error(`${d.detail || "Admin is turned off."} Set a strong ADMIN_TOKEN in .env (see README), then restart the backend.`);
  }
  if (r.status === 429) throw new Error("Too many attempts. Wait a minute and try again.");
  if (!r.ok) throw new Error("Couldn't load analytics.");
  return r.json();
}

export async function reindex(token: string) {
  const r = await fetch(`${API}/api/admin/reindex`, { method: "POST", headers: { "X-Admin-Token": token } });
  if (!r.ok) throw new Error("Reindex failed.");
  return r.json();
}

export async function getJSON<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== "") qs.set(k, String(v)); });
  const r = await fetch(`${API}${path}${qs.toString() ? "?" + qs : ""}`, { cache: "no-store" });
  if (!r.ok) throw new Error("Couldn't load data from the assistant service.");
  return r.json();
}
