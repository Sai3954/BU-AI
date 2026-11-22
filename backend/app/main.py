"""FastAPI backend for the student success assistant."""
from __future__ import annotations

import hmac
import re
import json
import logging
import threading
import time
from collections import Counter, defaultdict, deque
from contextlib import asynccontextmanager
from typing import Literal
from datetime import timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from . import features, guard, monitor
from .config import settings
from .db import Chunk, Issue, Page, QueryLog, SessionLocal, now
from .ingest import bootstrap, embed_missing, rebuild_index
from .llm import get_embedder, get_provider
from .prompts import extractive_answer, system_prompt, user_prompt
from .redact import redact
from .retrieval import ROLES, detect_level, for_meaning, index, is_crisis, is_follow_up, is_high_risk
from .conflicts import conflict_note, find_conflicts
from .handoff import office_list, suggest_office

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

provider = get_provider()
embedder = get_embedder()
PLACEHOLDER = re.compile(r"\[[A-Z_]+\]")
NOT_FOUND = ("couldn't find", "could not find", "not able to find", "no information")


def is_answered(answer: str, docs: list) -> bool:
    """Answered = sources found and the reply cites them. A cited reply that also says
    "I couldn't find the Saturday hours" still answered the question; an uncited "couldn't find" did not."""
    if not docs:
        return False
    low = answer.lower()
    if re.search(r"\[\d+\]", answer):
        return not low.lstrip().startswith(("i couldn't find that", "i could not find that"))
    return not any(p in low for p in NOT_FOUND)
COMMON_PARTS = ("admin", "password", "passw0rd", "belhaven", "change", "demo", "test", "secret", "token",
                "1234", "qwerty", "letmein", "welcome", "default", "abcdef", "university", "blazer")


def token_problem(t: str) -> str | None:
    """Why an admin token is too weak, or None if it's acceptable."""
    if len(t) < 20:
        return "it must be at least 20 characters"
    low = t.lower()
    if any(p in low for p in COMMON_PARTS):
        return "it contains a common word or sequence"
    if len(set(t)) < 12:
        return "it repeats too few different characters"
    classes = sum(bool(re.search(rx, t)) for rx in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        return "it needs at least three of: lowercase, uppercase, digits, symbols"
    return None


def admin_enabled() -> bool:
    return token_problem(settings.ADMIN_TOKEN) is None


# ---------- background jobs: index watcher + scheduled crawl ----------

def _index_signature() -> tuple:
    with SessionLocal() as s:
        return s.execute(select(func.count(Chunk.id), func.max(Chunk.id), func.max(Chunk.fetched_at))).one()


def _watch_index(stop: threading.Event) -> None:
    """Rebuild the in-memory index when another process (the crawler) changes the content."""
    last = _index_signature()
    while not stop.wait(settings.INDEX_WATCH_SECONDS):
        try:
            sig = _index_signature()
            if sig != last:
                embed_missing()
                n = rebuild_index()
                monitor.scan()
                last = sig
                log.info("Content changed; index rebuilt with %d passages", n)
        except Exception:
            log.exception("index watcher error")


def _scheduled_crawl(stop: threading.Event) -> None:
    from .crawl import crawl
    every = settings.CRAWL_EVERY_HOURS * 3600
    while not stop.wait(every):
        try:
            log.info("Scheduled crawl starting")
            log.info("Scheduled crawl finished: %s", crawl(settings.CRAWL_SEEDS, settings.CRAWL_MAX_PAGES))
        except Exception:
            log.exception("scheduled crawl failed")


@asynccontextmanager
async def lifespan(_app):
    info = bootstrap()
    monitor.scan()
    log.info("Ready: %s | provider=%s embeddings=%s", info, provider.name, embedder.name)
    if not admin_enabled():
        log.warning("Admin dashboard DISABLED: ADMIN_TOKEN is weak (%s). Generate one with: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(24))\"", token_problem(settings.ADMIN_TOKEN))
    stop = threading.Event()
    threads = []
    if settings.INDEX_WATCH_SECONDS > 0:
        threads.append(threading.Thread(target=_watch_index, args=(stop,), daemon=True))
    if settings.CRAWL_EVERY_HOURS > 0:
        threads.append(threading.Thread(target=_scheduled_crawl, args=(stop,), daemon=True))
    for t in threads:
        t.start()
    yield
    stop.set()


app = FastAPI(title=f"{settings.APP_NAME} API", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "X-Admin-Token"])
app.include_router(features.router)


# ---------- rate limiting and cost protection ----------

class RateLimiter:
    def __init__(self) -> None:
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        t = time.time()
        with self.lock:
            q = self.hits[key]
            while q and q[0] < t - window:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(t)
            return True


chat_limiter = RateLimiter()
admin_limiter = RateLimiter()
_ai_lock = threading.Lock()
_ai_inflight = {"n": 0}


def client_ip(request: Request) -> str:
    if settings.TRUST_PROXY and request.headers.get("x-forwarded-for"):
        return request.headers["x-forwarded-for"].split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ai_calls_today() -> int:
    """AI answers logged since midnight UTC. Stored in the database, so restarts don't reset the cap."""
    start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal() as s:
        return s.scalar(select(func.count(QueryLog.id)).where(QueryLog.ai.is_(True), QueryLog.created_at >= start)) or 0


def ai_budget_ok() -> bool:
    """Reserve one AI call if today's limit allows. The lock plus the in-flight counter stop concurrent
    requests from all passing the check before any of them is written to the database."""
    with _ai_lock:
        if ai_calls_today() + _ai_inflight["n"] >= settings.DAILY_AI_LIMIT:
            return False
        _ai_inflight["n"] += 1
        return True


def release_ai_slot() -> None:
    """Call once the reservation row is in the database (it now counts in ai_calls_today)."""
    with _ai_lock:
        _ai_inflight["n"] = max(0, _ai_inflight["n"] - 1)


class Concurrency:
    """Limit simultaneous streaming answers per visitor."""
    def __init__(self) -> None:
        self.active: dict[str, int] = defaultdict(int)
        self.lock = threading.Lock()

    def acquire(self, key: str) -> bool:
        with self.lock:
            if self.active[key] >= settings.MAX_CONCURRENT_PER_IP:
                return False
            self.active[key] += 1
            return True

    def release(self, key: str) -> None:
        with self.lock:
            self.active[key] = max(0, self.active[key] - 1)


concurrency = Concurrency()


# ---------- public API ----------

class Turn(BaseModel):
    role: str
    text: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    role: str = ""
    category: str = ""
    history: list[Turn] = Field(default=[], max_length=10)


class HandoffLog(BaseModel):
    query_id: int
    office: str = Field(max_length=120)


@app.get("/api/offices")
def offices_for_handoff():
    """Offices a student can contact (public directory data only)."""
    return {"offices": office_list()}


@app.post("/api/handoff")
def log_handoff(h: HandoffLog, request: Request):
    """Count that a student prepared a request to an office. Nothing is sent from here: the student sends
    the email or ticket themselves. Only the office name is stored, no message text."""
    if not chat_limiter.allow("ho:" + client_ip(request), 20):
        raise HTTPException(429, "Too many requests. Please wait a moment.")
    if h.office not in {o["name"] for o in office_list()}:
        raise HTTPException(422, "Unknown office")
    with SessionLocal() as s:
        row = s.get(QueryLog, h.query_id)
        if not row:
            raise HTTPException(404, "Not found")
        row.handoff_office = h.office
        s.commit()
    return {"ok": True}


class Feedback(BaseModel):
    query_id: int
    helpful: bool
    reason: Literal["", "wrong", "missing", "unclear"] = ""


@app.get("/api/health")
def health():
    return {"ok": True, "provider": provider.name, "vectors": index.has_vectors, "chunks": len(index.docs)}


@app.get("/api/meta")
def meta():
    with SessionLocal() as s:
        cats = dict(s.execute(select(Chunk.category, func.count()).group_by(Chunk.category)).all())
        urls = s.scalar(select(func.count(func.distinct(Chunk.url))))
        last = s.scalar(select(func.max(Chunk.fetched_at)))
    return {
        "app_name": settings.APP_NAME, "tagline": settings.APP_TAGLINE, "university": settings.UNIVERSITY,
        "roles": ROLES, "categories": cats, "sources": urls, "passages": len(index.docs),
        "programs": len(features.programs()), "offices": len(features.offices()),
        "last_refresh": last.isoformat() if last else None, "ai": provider.generative,
        "retrieval": "hybrid (keyword + vector)" if index.has_vectors else "keyword (BM25)",
    }


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def question_votes(q: str, days: int = 180) -> dict:
    """👍/👎 totals from everyone who asked this same question (case and spacing ignored)."""
    key = " ".join(q.lower().split()).rstrip("?.! ")
    since = now() - timedelta(days=days)
    with SessionLocal() as s:
        rows = s.execute(select(QueryLog.question, QueryLog.helpful).where(
            QueryLog.created_at >= since, QueryLog.helpful.is_not(None))).all()   # only rated rows: few
    hits = [h for qq, h in rows if " ".join(qq.lower().split()).rstrip("?.! ") == key]
    return {"likes": sum(1 for h in hits if h), "dislikes": sum(1 for h in hits if not h)}


def trim_unfinished(text: str) -> str:
    """Cut an answer that stopped mid-sentence back to its last complete sentence or list item."""
    t = text.rstrip()
    lines = t.split("\n")
    while lines:
        last = lines[-1].rstrip()
        end = max(last.rfind(". "), last.rfind("? "), last.rfind("! "))
        if re.search(r"[.!?](\s*\[\d+\])*\s*$|\]\s*\.?$", last):
            break                                   # the last line is already complete
        if end > 0 and not re.match(r"^\s*([-*•]|\d+\.)\s", last):
            lines[-1] = last[:end + 1]              # paragraph: keep its finished sentences
            break
        lines.pop()                                 # unfinished list item or heading-like line: drop it
        while lines and (not lines[-1].strip() or lines[-1].rstrip().endswith(":") or re.fullmatch(r"\s*\*\*[^*]+\*\*:?\s*", lines[-1])):
            lines.pop()                             # and a lead-in such as "**Key rules**" left without items
    out = "\n".join(lines).rstrip()
    if not out or out == t:
        return t
    return out + "\n\nThe full details are in the official sources below."


def retrieve(sq: str, prev: str, role: str, qvec, category: str, trace: dict | None = None):
    """Search for one question. A follow-up ("What documents do I need?") is searched together with the
    previous question, so it stays on the same topic; the question's own meaning vector still applies."""
    if prev and is_follow_up(sq):
        if trace is not None:
            trace["combined_with_previous"] = prev
        if qvec is not None:
            try:
                qvec = embedder.embed([for_meaning(f"{prev} {sq}")])[0]
            except Exception as e:
                log.warning("follow-up embedding failed: %s", e)
        return index.search(f"{prev} {sq}", role=role, qvec=qvec, category=category, trace=trace)
    docs = index.search(sq, role=role, qvec=qvec, category=category, trace=trace)
    if len(docs) < 3 and prev:
        docs = index.search(f"{prev} {sq}", role=role, qvec=qvec, category=category, trace=trace)
    return docs


@app.post("/api/trace")
def trace(req: ChatRequest, request: Request):
    """Show the working behind an answer, without calling the AI: what was removed for privacy, which
    passages the keyword and meaning searches found (with scores), what was chosen, and the exact prompt
    the language model would receive. Used by the 'AI question journey' demo page. No cost per call."""
    if not chat_limiter.allow(client_ip(request), settings.CHAT_RATE_PER_MINUTE):
        raise HTTPException(429, "Too many questions in a minute. Please wait a moment and try again.")
    import numpy as np
    t = {}
    t0 = time.perf_counter()
    q, pii = redact(req.question.strip())
    history = [{"role": h.role, "text": redact(h.text)[0]} for h in req.history]
    role = req.role if req.role in ROLES else ""
    t["privacy_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    sq = PLACEHOLDER.sub(" ", q)
    t1 = time.perf_counter()
    qvec = embedder.embed([for_meaning(sq)])[0] if embedder.name != "none" else None
    t["embed_ms"] = round((time.perf_counter() - t1) * 1000, 1)
    t2 = time.perf_counter()
    tr: dict = {}
    prev = next((PLACEHOLDER.sub(" ", h["text"]) for h in reversed(history) if h["role"] == "user"), "")
    docs = retrieve(sq, prev, role, qvec, req.category, tr)
    t["search_ms"] = round((time.perf_counter() - t2) * 1000, 1)
    level = detect_level(sq, role)
    conflicts = find_conflicts(docs)
    kw_rank = {i: (r + 1, sc) for r, (i, sc) in enumerate(tr.get("keyword", []))}
    mv_rank = {i: (r + 1, sc) for r, (i, sc) in enumerate(tr.get("meaning", []))}

    def card(i: int) -> dict:
        d = index.docs[i]
        return {"title": d.title, "url": d.url, "category": d.category, "updated": d.updated_label,
                "verified": d.source == "seed", "audiences": d.audiences}

    final = []
    for n, (i, fused) in enumerate(tr.get("final", []), 1):
        d = index.docs[i]
        final.append({**card(i), "n": n, "text": d.text, "fused": fused,
                      "keyword_rank": kw_rank.get(i, (None, None))[0], "keyword_score": kw_rank.get(i, (None, None))[1],
                      "meaning_rank": mv_rank.get(i, (None, None))[0], "meaning_score": mv_rank.get(i, (None, None))[1]})
    # A 2-D map of meaning space: the question and the candidate passages, projected with PCA.
    space = None
    if qvec is not None and index.vectors is not None:
        ids = list(dict.fromkeys([i for i, _ in tr.get("meaning", [])] + [i for i, _ in tr.get("keyword", [])[:8]]
                                 + [i for i, _ in tr.get("final", [])]))
        if ids:
            qv = np.asarray(qvec, dtype=np.float32)
            qv = qv / (np.linalg.norm(qv) + 1e-9)
            m = np.vstack([qv, index.vectors[ids]])
            c = m - m.mean(axis=0)
            _, _, vt = np.linalg.svd(c, full_matrices=False)
            xy = c @ vt[:2].T
            xy = (xy - xy.min(axis=0)) / (np.ptp(xy, axis=0) + 1e-9)
            chosen = {i for i, _ in tr.get("final", [])}
            space = {"question": [round(float(xy[0, 0]), 3), round(float(xy[0, 1]), 3)],
                     "points": [{"title": index.docs[i].title, "x": round(float(xy[k + 1, 0]), 3),
                                 "y": round(float(xy[k + 1, 1]), 3), "chosen": i in chosen,
                                 "similarity": round(float(index.vectors[i] @ qv), 3)}
                                for k, i in enumerate(ids)]}
    return {
        "question": req.question.strip(), "question_for_search": sq, "pii_removed": pii, "role": role,
        "level": level, "intent": docs[0].category if docs else "", "high_risk": is_high_risk(q),
        "crisis": is_crisis(q), "terms": tr.get("terms", []), "combined_with_previous": tr.get("combined_with_previous", ""), "passages_searched": tr.get("passages_searched", 0),
        "embedding": {"model": embedder.name, "dims": len(qvec) if qvec else 0,
                      "preview": [round(float(x), 3) for x in (qvec or [])[:8]]},
        "keyword": [{**card(i), "score": sc} for i, sc in tr.get("keyword", [])[:8]],
        "meaning": [{**card(i), "score": sc} for i, sc in tr.get("meaning", [])[:8]],
        "final": final, "space": space, "conflicts": conflicts, "timings": t,
        "llm": {"provider": provider.name, "model": getattr(provider, "model", "")},
        "prompt": {"system": system_prompt(),
                   "user": user_prompt(q, role, docs, history, level, conflict_note(conflicts)) if docs else ""},
    }


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    if not chat_limiter.allow(client_ip(request), settings.CHAT_RATE_PER_MINUTE):
        raise HTTPException(429, "Too many questions in a minute. Please wait a moment and try again.")
    t0 = time.time()
    q, pii = redact(req.question.strip())
    history = [{"role": h.role, "text": redact(h.text)[0]} for h in req.history]
    role = req.role if req.role in ROLES else ""
    prev = next((h["text"] for h in reversed(history) if h["role"] == "user"), "")
    qvec = None
    if embedder.name != "none":
        try:
            qvec = embedder.embed([for_meaning(PLACEHOLDER.sub(" ", q))])[0]
        except Exception as e:
            log.warning("query embedding failed: %s", e)
    # Placeholders like [EMAIL] must not steer search toward "email" pages.
    sq, prev = PLACEHOLDER.sub(" ", q), PLACEHOLDER.sub(" ", prev)
    docs = retrieve(sq, prev, role, qvec, req.category)
    level = detect_level(sq, role)
    conflicts = find_conflicts(docs)
    flags = {"high_risk": is_high_risk(q), "crisis": is_crisis(q), "pii_removed": pii,
             "level": level, "conflicts": conflicts}
    ip = client_ip(request)
    if not concurrency.acquire(ip):
        raise HTTPException(429, "Please wait for your current answer to finish.")
    use_ai = provider.generative and bool(docs) and ai_budget_ok()
    # Record the question immediately. For AI answers this row is the usage reservation: it counts
    # toward the daily limit even if the student closes the page mid-answer.
    with SessionLocal() as s:
        row = QueryLog(role=role, question=q[:1000], top_category=docs[0].category if docs else "",
                       sources=json.dumps([d.url for d in docs]), answered=False,
                       high_risk=flags["high_risk"], pii_removed=",".join(pii), ai=use_ai)
        s.add(row)
        s.commit()
        qid = row.id
    if use_ai:
        release_ai_slot()

    def gen():
        answer = ""
        checked: dict = {"unverified": [], "misattributed": [], "uncited": [], "unsupported_claims": [],
                         "invalid_citations": [], "cited": True}
        finished = False
        try:
            yield _sse("sources", {"sources": [d.public() for d in docs], "flags": flags})
            if use_ai:
                try:
                    for delta in provider.stream(system_prompt(), user_prompt(q, role, docs, history, level, conflict_note(conflicts))):
                        answer += delta
                        yield _sse("delta", {"text": delta})
                    if getattr(provider, "last_stop", "") == "max_tokens":
                        # Never show a sentence cut in half: keep the complete part and point to the sources.
                        answer = trim_unfinished(answer)
                        yield _sse("replace", {"text": answer})
                    yield _sse("stage", {"stage": "verifying"})   # the answer checker is running now
                    checked = guard.check(answer, docs, q)
                    if checked["invalid_citations"]:
                        answer = checked["text"]
                        yield _sse("replace", {"text": answer})
                    if settings.VERIFY_WITH_AI:
                        try:
                            checked["ai_flags"] = guard.ai_review(provider, answer, docs)
                        except Exception:
                            log.warning("AI review failed", exc_info=True)
                except Exception:
                    log.exception("LLM error")
                    if not answer:
                        answer = extractive_answer(docs, crisis=flags["crisis"]) + "\n\n(The AI service is unavailable right now, so this is the closest official text.)"
                        yield _sse("delta", {"text": answer})
                    else:
                        yield _sse("error", {"message": "The answer was interrupted. Please try again."})
            else:
                answer = extractive_answer(docs, crisis=flags["crisis"])
                yield _sse("delta", {"text": answer})
            finished = True
            yield _sse("done", {"query_id": qid, "answered": is_answered(answer, docs), "votes": question_votes(q),
                                "handoff": suggest_office(q, role, detect_level(sq, role)),
                                **{k: checked.get(k, []) for k in ("unverified", "misattributed", "uncited",
                                                                    "unsupported_claims", "ai_flags")}})
        finally:
            # Runs on normal completion *and* when the client disconnects mid-stream.
            concurrency.release(ip)
            answered = finished and is_answered(answer, docs)
            with SessionLocal() as s:
                r = s.get(QueryLog, qid)
                if r:
                    r.answered = answered
                    r.latency_ms = (time.time() - t0) * 1000
                    r.unverified = guard.issue_count(checked)
                    s.commit()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/feedback")
def feedback(fb: Feedback, request: Request):
    if not chat_limiter.allow("fb:" + client_ip(request), 30):
        raise HTTPException(429, "Too many requests")
    with SessionLocal() as s:
        row = s.get(QueryLog, fb.query_id)
        if not row:
            raise HTTPException(404, "Unknown question")
        row.helpful = fb.helpful
        row.feedback_reason = "" if fb.helpful else fb.reason
        s.commit()
    return {"ok": True}


@app.get("/api/search")
def search(q: str, role: str = "", k: int = 6):
    return [d.public() for d in index.search(redact(q)[0], role=role, k=min(k, 20))]


# ---------- admin API ----------

def admin(request: Request, x_admin_token: str = Header(default="")):
    if not admin_enabled():
        raise HTTPException(503, f"Admin is disabled: ADMIN_TOKEN is too weak ({token_problem(settings.ADMIN_TOKEN)}).")
    if not admin_limiter.allow("adm:" + client_ip(request), 20):
        raise HTTPException(429, "Too many attempts. Wait a minute.")
    if not hmac.compare_digest(x_admin_token.encode(), settings.ADMIN_TOKEN.encode()):
        raise HTTPException(401, "Admin token required")


@app.get("/api/admin/summary", dependencies=[Depends(admin)])
def admin_summary(days: int = 30):
    since = now() - timedelta(days=days)
    with SessionLocal() as s:
        qs = list(s.scalars(select(QueryLog).where(QueryLog.created_at >= since).order_by(QueryLog.created_at.desc())))
        order = {"conflict": 0, "broken_link": 1, "stale": 2, "changed": 3}
        issues = sorted(s.scalars(select(Issue).order_by(Issue.detected_at.desc()).limit(300)),
                        key=lambda i: (order.get(i.kind, 9), i.severity != "high"))
        pages = s.scalar(select(func.count()).select_from(Page)) or 0
    norm = lambda t: " ".join(t.lower().split())[:140]
    top = Counter(norm(q.question) for q in qs).most_common(10)
    unanswered = Counter(norm(q.question) for q in qs if not q.answered).most_common(10)
    rated = [q for q in qs if q.helpful is not None]
    ai_qs = [q for q in qs if q.ai]
    return {
        "window_days": days,
        "totals": {
            "questions": len(qs),
            "answered_rate": round(sum(q.answered for q in qs) / len(qs), 3) if qs else None,
            "helpful_rate": round(sum(q.helpful for q in rated) / len(rated), 3) if rated else None,
            "likes": sum(1 for q in rated if q.helpful), "dislikes": sum(1 for q in rated if not q.helpful),
            "not_helpful_reasons": dict(Counter(q.feedback_reason for q in rated if not q.helpful and q.feedback_reason)),
            "high_risk": sum(q.high_risk for q in qs),
            "pii_redacted": sum(bool(q.pii_removed) for q in qs),
            "unverified_answers": sum(q.unverified > 0 for q in ai_qs),
            "ai_answers": len(ai_qs),
            "ai_calls_today": ai_calls_today(), "daily_ai_limit": settings.DAILY_AI_LIMIT,
            "avg_latency_ms": round(sum(q.latency_ms for q in qs) / len(qs)) if qs else None,
            "crawled_pages": pages, "passages": len(index.docs),
        },
        "by_role": dict(Counter(q.role or "unspecified" for q in qs)),
        "by_category": dict(Counter(q.top_category or "none" for q in qs)),
        "top_questions": [{"question": k, "count": v} for k, v in top],
        "unanswered": [{"question": k, "count": v} for k, v in unanswered],
        "handoffs": dict(Counter(q.handoff_office for q in qs if q.handoff_office)),
        "disliked": [{"question": norm(q.question), "reason": q.feedback_reason or "no reason given",
                      "when": q.created_at.isoformat()} for q in rated if not q.helpful][:10],
        "issues": [{"kind": i.kind, "severity": i.severity, "url": i.url, "detail": i.detail,
                    "detected_at": i.detected_at.isoformat()} for i in issues],
        "issue_counts": dict(Counter(i.kind for i in issues)),
    }


@app.post("/api/admin/reindex", dependencies=[Depends(admin)])
def admin_reindex():
    embedded = embed_missing()
    n = rebuild_index()
    return {"embedded": embedded, "passages": n, **monitor.scan()}
