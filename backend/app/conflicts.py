"""Answer-time conflict check: do the passages retrieved for THIS question disagree on a key fact?

The knowledge monitor (monitor.py) scans the whole site for staff. This module looks only at the few
sources behind one answer, so the student is told when two official pages say different things.
"""
from __future__ import annotations

import re

from .retrieval import Doc, _academic_year

# (label, pattern with one capture group for the value). Patterns are narrow on purpose: a false
# "pages disagree" warning costs more trust than a missed one.
FACTS: list[tuple[str, re.Pattern]] = [
    ("Tuition per credit hour", re.compile(r"\$\s?([\d,]{3,6}(?:\.\d\d)?)\s*(?:per|/|a)\s*(?:credit[- ]hour|credit|hour)\b", re.I)),
    ("Minimum GPA", re.compile(r"(?:minimum|cumulative|at least an?)\s+(?:\w+\s+){0,2}GPA\s+(?:of\s+)?(\d\.\d{1,2})", re.I)),
    ("TOEFL iBT minimum", re.compile(r"TOEFL[^.;]{0,45}?\b(\d{2,3})\s*(?:\(?iBT)", re.I)),
    ("IELTS minimum", re.compile(r"IELTS[^.;]{0,30}?\b(\d(?:\.\d)?)\b", re.I)),
    ("Total credit hours", re.compile(r"\b(?:total of|requires|consists of)\s+(\d{2,3})\s*(?:semester\s+)?credit[- ]hours", re.I)),
    ("Application fee", re.compile(r"application fee[^.;]{0,20}?\$\s?(\d{2,3})", re.I)),
    ("Credit hours per term (F-1)", re.compile(r"(?:at least|minimum of)\s*(\d{1,2})\s*credit hours? per (?:term|semester)", re.I)),
]


def _norm(v: str) -> str:
    v = v.replace(",", "").strip()
    try:
        f = float(v)
        return f"{f:g}"
    except ValueError:
        return v


def find_conflicts(docs: list[Doc]) -> list[dict]:
    """Facts where the retrieved sources give different values. Sources from different catalog years
    are not a conflict (fees change each year); the prompt already prefers the newest year."""
    out = []
    for label, rx in FACTS:
        seen: dict[str, list[int]] = {}
        years: dict[str, set[int]] = {}
        for n, d in enumerate(docs, 1):
            for m in rx.finditer(d.text):
                v = _norm(m.group(1))
                if n not in seen.setdefault(v, []):
                    seen[v].append(n)
                years.setdefault(v, set()).add(_academic_year(d))
        if len(seen) < 2:
            continue
        # Same fact, values only differ across catalog years -> history, not a conflict.
        ys = [ys - {0} for ys in years.values()]
        if all(ys) and len(set.union(*ys)) == len(ys) and all(len(y) == 1 for y in ys):
            continue
        # One source listing several values (e.g. a fee table for different programs) is a table, not a conflict.
        if len({n for ns in seen.values() for n in ns}) < 2:
            continue
        out.append({"fact": label, "values": [{"value": v, "sources": ns} for v, ns in seen.items()]})
    return out[:3]


def conflict_note(conflicts: list[dict]) -> str:
    if not conflicts:
        return ""
    lines = []
    for c in conflicts:
        vals = "; ".join(f"{x['value']} in {', '.join(f'[{n}]' for n in x['sources'])}" for x in c["values"])
        lines.append(f"- {c['fact']}: {vals}")
    return ("POSSIBLE CONFLICT BETWEEN SOURCES\n" + "\n".join(lines) +
            "\nIf these values apply to the same program and year, say the pages differ, give both with citations, "
            "prefer the current page, and suggest confirming with the office. If they apply to different "
            "programs or levels, give only the one for this person.")
