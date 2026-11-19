"""Polite crawler for the university's public website. Refreshes the knowledge base automatically.

    python -m app.crawl                      # crawl from CRAWL_SEEDS, up to CRAWL_MAX_PAGES
    python -m app.crawl --max 50             # smaller run
    python -m app.crawl --url https://...    # refresh one page

It respects robots.txt, waits between requests, stays on the allowed hosts, skips login-protected
systems (BlazeNet, Canvas, portals), and only stores public page text. Run it nightly (cron / a
scheduled container job) to keep answers current.
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import time
from collections import deque
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import delete, select

from . import monitor
from .config import settings
from .db import Chunk, Page, SessionLocal, init_db, now
from .ingest import embed_missing, rebuild_index

log = logging.getLogger("crawl")

SKIP_HOST_PARTS = ("blazenet", "instructure", "portalguard", "adfs", "login", "elluciancrmrecruit",
                   "starrez", "cashnet", "bncollege")
SKIP_PATH = re.compile(r"(/login|/open\.php|/view\.php|/account|/apply/account|\.(jpg|jpeg|png|gif|svg|webp|"
                       r"mp4|mp3|zip|docx?|xlsx?|pptx?)$|/news/20(0|1)\d/)", re.I)
PDF_MAX_BYTES = 15 * 1024 * 1024
PDF_MAX_PAGES = 80

# URL path -> (category, audiences)
RULES = [
    (r"igsupport\.belhaven\.edu.*cid=4|residency", ("Academics", ["international", "graduate", "doctoral"])),
    (r"igsupport\.belhaven\.edu", ("International", ["international", "graduate", "doctoral"])),
    (r"/international/", ("International", ["international"])),
    (r"/financial-aid/|/aid/|tuition|scholarship", ("Financial Aid", ["prospective", "undergraduate", "graduate", "online"])),
    (r"/admission/online|/admission/masters|/admission/doctorate", ("Admissions", ["prospective", "online", "graduate", "doctoral"])),
    (r"/admission/", ("Admissions", ["prospective", "undergraduate"])),
    (r"/library", ("Library", ["all"])),
    (r"/career", ("Careers", ["all"])),
    (r"academic-calendar|calendar.*\.pdf|exam-schedule", ("Academics", ["all"])),
    (r"/calendar|/news/", ("Events", ["all"])),
    (r"/care/|/health|counsel|wellness|accommodation", ("Wellness", ["all"])),
    (r"/housing|/dining|/campus/|/university-life/", ("Campus Life", ["prospective", "undergraduate"])),
    (r"/athletics|blazers\.", ("Campus Life", ["prospective", "undergraduate"])),
    (r"email|helpdesk|/canvas|technology", ("IT Support", ["all"])),
    (r"/alumni", ("Alumni", ["alumni"])),
    (r"/faculty-staff|/about/contact", ("Student Services", ["faculty", "all"])),
    (r"/academics/|/registrar|catalog", ("Academics", ["all"])),
]
UPDATED = re.compile(r"Last Updated\s+([\w ]+?ago)", re.I)


def classify(url: str) -> tuple[str, list[str]]:
    for pat, val in RULES:
        if re.search(pat, url, re.I):
            return val
    return "Student Services", ["all"]


def allowed(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    host = p.netloc.lower()
    if host not in settings.CRAWL_ALLOWED_HOSTS or any(x in host for x in SKIP_HOST_PARTS):
        return False
    if SKIP_PATH.search(p.path + ("?" + p.query if p.query else "")):
        return False
    return True


def extract(html: str, url: str) -> tuple[str, str, str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    links = [urldefrag(urljoin(url, a["href"]))[0] for a in soup.find_all("a", href=True)]
    title = (soup.title.string if soup.title and soup.title.string else "").strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(" ", strip=True)
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "svg", "iframe"]):
        tag.decompose()
    main = soup.find("main") or soup.find(id=re.compile("content|main", re.I)) or soup.body or soup
    blocks = []
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "td", "th", "dt", "dd"]):
        t = el.get_text(" ", strip=True)
        if len(t) > 2:
            blocks.append(("#" if el.name in ("h1", "h2", "h3", "h4") else "") + t)
    text = "\n".join(dict.fromkeys(blocks))  # de-duplicate repeated lines, keep order
    m = UPDATED.search(soup.get_text(" "))
    return title or url, text, (m.group(1) if m else "current site"), links


def extract_pdf(data: bytes, url: str) -> tuple[str, str]:
    """Text from a PDF (academic calendars, fee schedules, handbooks). Returns (title, text)."""
    import io
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages[:PDF_MAX_PAGES]:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(re.sub(r"[ \t]+", " ", p).strip() for p in pages)
    text = "\n".join(line for line in text.splitlines() if line.strip())
    meta_title = ""
    try:
        meta_title = (reader.metadata.title or "").strip() if reader.metadata else ""
    except Exception:
        pass
    name = urlparse(url).path.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " ").replace("_", " ")
    return (meta_title or name.title()) + " (PDF)", text


def chunk_text(text: str, max_chars: int = 1400) -> list[tuple[str, str]]:
    """Split on headings, then pack paragraphs up to max_chars. Returns (section, text)."""
    sections, cur_head, cur = [], "", []
    for line in text.split("\n"):
        if line.startswith("#"):
            if cur:
                sections.append((cur_head, cur))
            cur_head, cur = line.lstrip("#").strip(), []
        else:
            cur.append(line)
    if cur:
        sections.append((cur_head, cur))
    out = []
    for head, lines in sections:
        buf = ""
        for ln in lines:
            if len(buf) + len(ln) > max_chars and buf:
                out.append((head, buf.strip()))
                buf = ""
            buf += ln + "\n"
        if len(buf.strip()) > 40:
            out.append((head, buf.strip()))
    return out


def store_page(url: str, title: str, text: str, updated: str, status: int) -> bool:
    """Save a page's chunks. Returns True if the content changed."""
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    cat, aud = classify(url)
    with SessionLocal() as s:
        page = s.get(Page, url)
        changed = page is None or page.content_hash != h
        if page is None:
            page = Page(url=url)
            s.add(page)
        page.title, page.status, page.updated_label, page.last_crawled = title, status, updated, now()
        if changed:
            page.content_hash, page.last_changed = h, now()
            s.execute(delete(Chunk).where(Chunk.url == url, Chunk.source == "crawl"))
            for i, (head, body) in enumerate(chunk_text(text)):
                s.add(Chunk(key=f"crawl:{h[:12]}:{i}:{url}"[:300], url=url,
                            title=f"{title} - {head}" if head and head != title else title,
                            category=cat, audiences=",".join(aud), text=body,
                            updated_label=updated, source="crawl"))
            # Crawled content replaces the hand-written seed summary for the same page.
            s.execute(delete(Chunk).where(Chunk.url == url, Chunk.source == "seed"))
        s.commit()
    return changed and page is not None


MAX_REDIRECTS = 5


def fetch(client: httpx.Client, url: str) -> tuple[httpx.Response | None, str]:
    """GET a URL, following redirects manually so every hop is checked against the allowed hosts.
    Returns (response, final_url); response is None if a redirect leaves the allowed site."""
    for _ in range(MAX_REDIRECTS + 1):
        r = client.get(url)
        if r.is_redirect and r.headers.get("location"):
            nxt = urldefrag(urljoin(url, r.headers["location"]))[0]
            if not allowed(nxt):
                log.info("redirect blocked: %s -> %s", url, nxt)
                return None, nxt
            url = nxt
            continue
        return r, url
    log.info("too many redirects: %s", url)
    return None, url


def crawl(seeds: list[str], max_pages: int) -> dict:
    init_db()
    robots: dict[str, RobotFileParser] = {}
    seen, queue = set(), deque((u, "") for u in seeds)
    stats = {"fetched": 0, "changed": 0, "errors": 0}
    with httpx.Client(headers={"User-Agent": settings.CRAWL_USER_AGENT}, follow_redirects=False, timeout=20) as client:
        while queue and stats["fetched"] < max_pages:
            url, parent = queue.popleft()
            if url in seen or not allowed(url):
                continue
            seen.add(url)
            host = urlparse(url).netloc
            if host not in robots:
                rp = RobotFileParser(f"https://{host}/robots.txt")
                try:
                    rp.read()
                except Exception:
                    rp = None
                robots[host] = rp
            if robots[host] is not None and not robots[host].can_fetch(settings.CRAWL_USER_AGENT, url):
                continue
            try:
                r, final_url = fetch(client, url)
            except Exception as e:
                log.warning("fetch failed %s: %s", url, e)
                stats["errors"] += 1
                continue
            finally:
                time.sleep(settings.CRAWL_DELAY_SECONDS)
            stats["fetched"] += 1
            if r is None:
                stats.setdefault("redirects_blocked", 0)
                stats["redirects_blocked"] += 1
                continue
            if final_url != url:
                if final_url in seen:
                    continue
                seen.add(final_url)
                url = final_url
            if r.status_code >= 400:
                monitor.record_link_problem(url, r.status_code, parent)
                stats["errors"] += 1
                continue
            ctype = r.headers.get("content-type", "")
            if "application/pdf" in ctype or urlparse(url).path.lower().endswith(".pdf"):
                if len(r.content) > PDF_MAX_BYTES:
                    continue
                try:
                    title, text = extract_pdf(r.content, url)
                except Exception as e:
                    log.warning("PDF unreadable %s: %s", url, e)
                    continue
                if len(text) > 200 and store_page(url, title, text, "PDF document", r.status_code):
                    stats["changed"] += 1
                    monitor.record_change(url, title)
                log.info("[%d] PDF %s", stats["fetched"], url)
                continue
            if "text/html" not in ctype:
                continue
            title, text, updated, links = extract(r.text, url)
            if len(text) > 200 and store_page(url, title, text, updated, r.status_code):
                stats["changed"] += 1
                monitor.record_change(url, title)
            for link in links:
                if link not in seen and allowed(link):
                    queue.append((link, url))
            log.info("[%d] %s %s", stats["fetched"], r.status_code, url)
    stats["embedded"] = embed_missing()
    stats["chunks"] = rebuild_index()
    stats.update(monitor.scan())
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=settings.CRAWL_MAX_PAGES)
    ap.add_argument("--url", action="append", help="crawl only these URLs (repeatable)")
    a = ap.parse_args()
    seeds = a.url or settings.CRAWL_SEEDS
    limit = len(a.url) if a.url and a.max == settings.CRAWL_MAX_PAGES else a.max
    print(crawl(seeds, limit))
