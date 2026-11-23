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
SKIP_PATH = re.compile(r"[?&](key|signature|expires)=|/404\.html$|(/login|/open\.php|/view\.php|/account|/apply/account|\.(jpg|jpeg|png|gif|svg|webp|"
                       r"mp4|mp3|zip|docx?|xlsx?|pptx?)$|/news/20(0|1)\d/)", re.I)
PDF_MAX_BYTES = 15 * 1024 * 1024
PDF_MAX_PAGES = 80

# URL path -> (category, audiences). More specific patterns first; audiences drive program/level-aware answers.
RULES = [
    (r"/news/", ("News", ["all"])),   # announcements: kept, but ranked below official pages
    (r"igsupport\.belhaven\.edu.*cid=4|residency", ("Academics", ["international", "graduate", "doctoral"])),
    (r"igsupport\.belhaven\.edu", ("International", ["international", "graduate", "doctoral"])),
    (r"/international/", ("International", ["international"])),
    (r"dissertation|/doctora|/dba|/phd|/edd|doctor-of", ("Academics", ["doctoral"])),
    (r"/online/|/adult|/admission/online", ("Admissions", ["online", "prospective"])),
    (r"/admission/masters|/graduate|/masters|master-of|/mba", ("Admissions", ["graduate", "prospective"])),
    (r"/admission/doctorate", ("Admissions", ["doctoral", "prospective"])),
    (r"/financial-aid/|/aid/|tuition|scholarship|/cost|fees|business-office|/payment", ("Financial Aid", ["prospective", "undergraduate", "graduate", "doctoral", "online"])),
    (r"/admission/|/visit|/apply", ("Admissions", ["prospective", "undergraduate"])),
    (r"/library", ("Library", ["all"])),
    (r"/career|internship|externship", ("Careers", ["all"])),
    (r"academic-calendar|calendar.*\.pdf|exam-schedule", ("Academics", ["all"])),
    (r"/news/|announce|/calendar|/events", ("Events", ["all"])),
    (r"/care/|/health|counsel|wellness|accommodation|disabilit|accessib", ("Wellness", ["all"])),
    (r"safety|security|police|title-ix|titleix|emergency|clery", ("Campus Safety", ["all"])),
    (r"/athletics|blazers\.|sports", ("Campus Life", ["prospective", "undergraduate"])),
    (r"/housing|/dining|/residence|/campus-life|/university-life/|/student-life|organization|/clubs|/ministry", ("Campus Life", ["prospective", "undergraduate"])),
    (r"email|helpdesk|/canvas|technology|/it/|computer", ("IT Support", ["all"])),
    (r"/alumni", ("Alumni", ["alumni"])),
    (r"/faculty-staff|/hr/|human-resources|employment|/faculty/", ("Faculty & Staff", ["faculty"])),
    (r"handbook|policy|policies|catalog|/registrar|transcript|graduation|commencement", ("Policies & Registrar", ["all"])),
    (r"publication|research|journal|/press", ("Research", ["graduate", "doctoral", "faculty"])),
    (r"/about/contact|directory|/offices", ("Student Services", ["all"])),
    (r"/academics/|/programs?/|/majors|/minors", ("Academics", ["all"])),
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
    # The first <main> or content-id element that actually holds text: the catalogue's skip-link target
    # (id="acalog-content") is an empty anchor, and some pages have an empty <main> in the header.
    candidates = soup.find_all("main") + soup.find_all(id=re.compile("content|main", re.I))
    main = next((c for c in candidates if len(c.get_text(" ", strip=True)) > 200), None) or soup.body or soup
    blocks = []
    for el in main.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "td", "th", "dt", "dd"]):
        t = el.get_text(" ", strip=True)
        if el.name == "li" and el.find("li") is None:
            a = el.find("a", href=True)
            if a is not None and a["href"].startswith("#") and a.get_text(" ", strip=True) == t:
                continue  # a table-of-contents entry (in-page link only): not content
        if len(t) > 2:
            # h5/h6 are section headings in the university catalogue and student handbook (The Kilt)
            blocks.append(("#" if el.name in ("h1", "h2", "h3", "h4", "h5", "h6") else "") + t)
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


def sitemap_urls(client: httpx.Client, host: str, limit: int = 5000) -> list[str]:
    """Page URLs listed in the host's sitemap(s), from robots.txt "Sitemap:" lines or /sitemap.xml."""
    found, todo, done = [], [], set()
    try:
        r = client.get(f"https://{host}/robots.txt")
        todo += [ln.split(":", 1)[1].strip() for ln in r.text.splitlines() if ln.lower().startswith("sitemap:")]
    except Exception:
        pass
    todo = todo or [f"https://{host}/sitemap.xml"]
    while todo and len(found) < limit:
        sm = todo.pop()
        if sm in done or urlparse(sm).netloc.lower() not in settings.CRAWL_ALLOWED_HOSTS:
            continue
        done.add(sm)
        try:
            r = client.get(sm)
            if r.status_code != 200:
                continue
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
        except Exception:
            continue
        for loc in locs:
            (todo if loc.lower().endswith(".xml") else found).append(loc.replace("&amp;", "&"))
    return [u for u in dict.fromkeys(found) if allowed(u)][:limit]


def read_robots(client: httpx.Client, host: str) -> RobotFileParser | None:
    """robots.txt fetched with the crawler's own client and user agent (urllib's default agent is
    refused by some hosts, which RobotFileParser would treat as "disallow everything").
    None = no usable robots.txt, so everything not otherwise blocked is allowed."""
    rp = RobotFileParser(f"https://{host}/robots.txt")
    try:
        r = client.get(f"https://{host}/robots.txt")
    except Exception:
        return None
    if r.status_code in (401, 403):
        rp.disallow_all = True
    elif r.status_code == 200:
        rp.parse(r.text.splitlines())
    else:
        return None
    return rp


def crawl(seeds: list[str], max_pages: int, use_sitemap: bool = False, follow_links: bool = True,
          finalize: bool = True, client: httpx.Client | None = None) -> dict:
    """Fetch pages from the seeds (following links on allowed hosts unless follow_links=False).
    finalize=False leaves embedding and the index rebuild to the API's index watcher."""
    init_db()
    robots: dict[str, RobotFileParser] = {}
    seen, queue = set(), deque((u, "") for u in seeds)
    stats = {"fetched": 0, "changed": 0, "errors": 0}
    problems = stats.setdefault("problems", [])   # first few failures, for the health check
    note = lambda u, why: len(problems) < 5 and problems.append(f"{why}: {u[-60:]}")
    own = client is None
    if own:
        client = httpx.Client(headers={"User-Agent": settings.CRAWL_USER_AGENT}, follow_redirects=False, timeout=30)
    try:
        if use_sitemap:
            for host in settings.CRAWL_ALLOWED_HOSTS:
                urls = sitemap_urls(client, host)
                stats[f"sitemap:{host}"] = len(urls)
                queue.extend((u, "sitemap") for u in urls)
        while queue and stats["fetched"] < max_pages:
            url, parent = queue.popleft()
            if url in seen or not allowed(url):
                continue
            seen.add(url)
            host = urlparse(url).netloc
            if host not in robots:
                robots[host] = read_robots(client, host)
            if robots[host] is not None and not robots[host].can_fetch(settings.CRAWL_USER_AGENT, url):
                stats.setdefault("robots_blocked", 0)
                stats["robots_blocked"] += 1
                note(url, "robots.txt disallows")
                continue
            delay = settings.CRAWL_DELAY_SECONDS
            if robots[host] is not None:  # honour the site's Crawl-delay (the catalogue asks for 120 s)
                try:
                    delay = max(delay, min(float(robots[host].crawl_delay(settings.CRAWL_USER_AGENT) or 0), 300.0))
                except (TypeError, ValueError):
                    pass
            try:
                r, final_url = fetch(client, url)
            except Exception as e:
                log.warning("fetch failed %s: %s", url, e)
                stats["errors"] += 1
                note(url, type(e).__name__)
                continue
            finally:
                if queue:
                    time.sleep(delay)
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
                note(url, f"HTTP {r.status_code}")
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
                note(url, f"not HTML ({ctype[:30]})")
                continue
            title, text, updated, links = extract(r.text, url)
            if len(text) <= 200:
                note(url, f"too little text ({len(text)} chars; HTTP {r.status_code}, {len(r.content)} bytes, "
                          f"{r.headers.get('server', '?')[:20]}, {'script-only' if '<p' not in r.text.lower() else 'has <p>'})")
            if len(text) > 200 and store_page(url, title, text, updated, r.status_code):
                stats["changed"] += 1
                monitor.record_change(url, title)
            if follow_links:
                for link in links:
                    if link not in seen and allowed(link):
                        queue.append((link, url))
            log.info("[%d] %s %s", stats["fetched"], r.status_code, url)
    finally:
        if own:
            client.close()
    if not finalize:
        return stats
    stats["embedded"] = embed_missing()
    stats["chunks"] = rebuild_index()
    stats.update(monitor.scan())
    return stats


def export_pages(path: str) -> int:
    """Write every crawled page (url, title, updated label, full text) to a gzipped JSON file."""
    import gzip
    import json
    with SessionLocal() as s:
        pages = {p.url: p for p in s.scalars(select(Page))}
        by_url: dict[str, list[Chunk]] = {}
        for c in s.scalars(select(Chunk).where(Chunk.source == "crawl").order_by(Chunk.id)):
            by_url.setdefault(c.url, []).append(c)
    out = []
    for url, chunks in by_url.items():
        p = pages.get(url)
        title = p.title if p else chunks[0].title
        body = []
        for c in chunks:
            head = c.title[len(title) + 3:] if c.title.startswith(title + " - ") else ""
            body.append((f"#{head}\n" if head else "") + c.text)
        out.append({"url": url, "title": title, "updated": p.updated_label if p else "",
                    "text": "\n".join(body)})
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"pages": out}, f, ensure_ascii=False)
    return len(out)


def crawl_missing(urls: list[str], client: httpx.Client | None = None) -> dict:
    """Fetch only the listed pages that aren't stored yet (no link following). Used at API start-up
    to add official pages the main crawl never reached, such as the catalogue and student handbook."""
    init_db()
    with SessionLocal() as s:
        have = {u for (u,) in s.execute(select(Page.url).where(Page.url.in_(urls)))}
    todo = [u for u in dict.fromkeys(urls) if u not in have and allowed(u)]
    if not todo:
        return {"fetched": 0, "changed": 0, "errors": 0, "already_stored": len(have)}
    stats = crawl(todo, len(todo), follow_links=False, finalize=False, client=client)
    stats["already_stored"] = len(have)
    return stats


def load_export(path: str) -> int:
    """Load pages saved by export_pages (only into an empty crawl store). Returns pages loaded."""
    import gzip
    import json
    import os
    if not os.path.exists(path):
        return 0
    with SessionLocal() as s:
        if s.scalar(select(Chunk.id).where(Chunk.source == "crawl").limit(1)) is not None:
            return 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    n = 0
    for p in data.get("pages", []):
        if p.get("text") and allowed(p["url"]):
            store_page(p["url"], p["title"], p["text"], p.get("updated", ""), 200)
            n += 1
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=settings.CRAWL_MAX_PAGES)
    ap.add_argument("--url", action="append", help="crawl only these URLs (repeatable)")
    ap.add_argument("--sitemap", action="store_true", help="also queue every page listed in the sitemaps")
    ap.add_argument("--export", help="after crawling, save all crawled pages to this .json.gz file")
    a = ap.parse_args()
    seeds = a.url or settings.CRAWL_SEEDS
    limit = len(a.url) if a.url and a.max == settings.CRAWL_MAX_PAGES else a.max
    print(crawl(seeds, limit, use_sitemap=a.sitemap))
    if a.export:
        print("exported pages:", export_pages(a.export))
