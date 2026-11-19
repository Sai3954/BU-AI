"""AI knowledge monitor: finds outdated pages, conflicting facts and broken links in university content."""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import delete, select

from .db import Chunk, Issue, SessionLocal

# Facts that should have one value across the whole site. (label, regex with one capture group)
FACTS = [
    ("TOEFL iBT minimum score", re.compile(r"TOEFL[^.;]{0,45}?\b(\d{2,3})\s*(?:\(?iBT)", re.I)),
    ("MBA total credit hours", re.compile(r"\bMBA\b[^.;]{0,40}?\b(\d{2})\s*credit[- ]hour", re.I)),
    ("MSITM total credit hours", re.compile(r"\bMSITM\b[^.;]{0,40}?\b(\d{2})\s*credit[- ]hour", re.I)),
    ("Minimum credit hours per term (F-1)", re.compile(r"(?:at least|minimum of|maintain[^.]{0,20}?)\s*(\d{1,2})\s*credit hours? per term", re.I)),
    ("Makeup residency fee", re.compile(r"makeup residency fee[^.]{0,20}?USD\s*(\d+)", re.I)),
]
PHONE_EMAIL = re.compile(r"(\d{3}-\d{3}-\d{4})[^.;\n]{0,40}?\b([\w.+-]+@belhaven\.edu)", re.I)
STALE = re.compile(r"(\d+)\s*years?\s*ago|a year ago", re.I)


def _stale_years(label: str) -> int:
    m = STALE.search(label or "")
    if not m:
        return 0
    return int(m.group(1)) if m.group(1) else 1


def scan() -> dict:
    """Recompute stale-content and conflict issues from the current knowledge base."""
    with SessionLocal() as s:
        rows = list(s.scalars(select(Chunk)))
        s.execute(delete(Issue).where(Issue.kind.in_(["stale", "conflict"])))

        stale_urls: dict[str, tuple[str, int]] = {}
        for r in rows:
            y = _stale_years(r.updated_label)
            if y >= 1:
                stale_urls[r.url] = (r.title, y)
        for url, (title, y) in stale_urls.items():
            s.add(Issue(kind="stale", severity="high" if y >= 2 else "medium", url=url,
                        detail=f"'{title}' was last updated about {y} year{'s' if y > 1 else ''} ago. "
                               f"Ask the owning office to review it."))

        n_conf = 0
        for label, rx in FACTS:
            values: dict[str, set[str]] = defaultdict(set)
            titles: dict[str, str] = {}
            for r in rows:
                for m in rx.finditer(r.text):
                    values[m.group(1)].add(r.url)
                    titles[r.url] = r.title
            if len(values) > 1:
                parts = "; ".join(f"{v} on {', '.join(sorted(urls)[:3])}" for v, urls in sorted(values.items()))
                first = sorted(next(iter(values.values())))[0]
                s.add(Issue(kind="conflict", severity="high", url=first,
                            detail=f"{label}: pages disagree ({parts})."))
                n_conf += 1
        # The same office email listed next to different phone numbers on different pages.
        by_email: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for r in rows:
            for m in PHONE_EMAIL.finditer(r.text):
                phone = m.group(1)
                between = r.text[m.end(1):m.start(2)]
                if re.search(r"\d{3}-\d{3}-\d{4}", between):
                    continue  # another phone sits closer to the email
                by_email[m.group(2).lower()][phone].add(r.url)
        # Emails the directory itself lists for several offices (shared inboxes) can't be compared.
        from collections import Counter as _C
        from .features import offices
        shared = {e for e, n in _C(o["email"].lower() for o in offices() if o["email"]).items() if n > 1}
        for email, phones in by_email.items():
            if len(phones) > 1 and email not in shared:
                parts = "; ".join(f"{p} on {', '.join(sorted(u)[:2])}" for p, u in sorted(phones.items()))
                s.add(Issue(kind="conflict", severity="medium", url=sorted(next(iter(phones.values())))[0],
                            detail=f"Phone number for {email}: pages disagree ({parts})."))
                n_conf += 1
        s.commit()
        return {"stale": len(stale_urls), "conflicts": n_conf}


def record_link_problem(url: str, status: int, found_on: str = "") -> None:
    with SessionLocal() as s:
        exists = s.scalar(select(Issue.id).where(Issue.kind == "broken_link", Issue.url == url))
        if exists:
            return
        s.add(Issue(kind="broken_link", severity="medium", url=url,
                    detail=f"Link returns HTTP {status}" + (f" (linked from {found_on})" if found_on else "")))
        s.commit()


def record_change(url: str, title: str) -> None:
    with SessionLocal() as s:
        s.add(Issue(kind="changed", severity="low", url=url,
                    detail=f"'{title}' changed since the last refresh; the assistant now uses the new version."))
        s.commit()


if __name__ == "__main__":
    from .db import init_db
    init_db()
    print(scan())
