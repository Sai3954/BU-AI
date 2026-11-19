"""Structured student tools: Program Finder, Contact Navigator, Scholarship & Aid Finder, Onboarding.

Each tool reads a JSON file in backend/data/ (collected from the public website) and is also turned
into searchable passages, so the chat assistant can answer from the same data.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from .config import BASE_DIR

DATA = BASE_DIR / "data"
router = APIRouter(prefix="/api")


@lru_cache
def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def programs() -> list[dict]:
    return _load("programs.json")["programs"]


def offices() -> list[dict]:
    return _load("directory.json")["offices"]


def awards() -> dict:
    return _load("scholarships.json")


def checklists() -> dict:
    return _load("onboarding.json")["checklists"]


def _words(s: str) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9]+", s.lower()) if len(w) > 1]


# ---------- Program Finder ----------

@router.get("/programs")
def list_programs(q: str = "", level: str = "", format: str = "", area: str = ""):
    out = []
    terms = _words(q)
    for p in programs():
        if level and p["level"] != level:
            continue
        if format and not p["format"].lower().startswith(format.lower()):
            continue
        if area and p["area"] != area:
            continue
        hay = " ".join([p["name"], p["degree"], p["area"], " ".join(p.get("concentrations", []))]).lower()
        if terms and not all(t in hay for t in terms):
            continue
        out.append(p)
    facets = {
        "levels": sorted({p["level"] for p in programs()}),
        "formats": sorted({p["format"] for p in programs()}),
        "areas": sorted({p["area"] for p in programs()}),
    }
    return {"count": len(out), "programs": out, "facets": facets,
            "source": _load("programs.json")["source"]}


# ---------- Contact Navigator ----------

@router.get("/directory")
def directory(q: str = ""):
    terms = _words(q)
    scored = []
    for o in offices():
        hay = " ".join([o["name"], o["handles"], o["group"], o.get("keywords", "")]).lower()
        score = sum(hay.count(t) for t in terms) if terms else 1
        if score:
            scored.append((score, o))
    scored.sort(key=lambda x: -x[0])
    return {"count": len(scored), "offices": [o for _, o in scored],
            "groups": sorted({o["group"] for o in offices()}), "source": _load("directory.json")["source"]}


# ---------- Scholarship & Aid Finder ----------

GROUPS = {
    "first_year": "New first-year (on campus)", "transfer": "Transfer (on campus)", "online": "Online student",
    "graduate": "Graduate (online)", "doctoral": "Doctoral", "international_hybrid": "International graduate (hybrid CPT)",
}


@router.get("/scholarships")
def scholarships(group: str = "first_year", gpa: float | None = None, act: int | None = None, tags: str = ""):
    data = awards()
    if group not in GROUPS:
        raise HTTPException(400, f"group must be one of {list(GROUPS)}")
    want = {t for t in tags.split(",") if t}
    eligible, maybe = [], []
    for a in data["awards"]:
        if group not in a["groups"]:
            continue
        if a["tags"] and not (set(a["tags"]) & (want | {"need", "education"})):
            # tagged awards (church, military, arts...) only when the student ticks that box;
            # need-based and education awards are always shown as "may qualify".
            continue
        ok = True
        if a["min_gpa"] is not None and gpa is not None and gpa < a["min_gpa"]:
            ok = False
        if a["min_act"] is not None:
            if act is None:
                ok = ok and a["name"] == "Advantage Scholarship"
            elif act < a["min_act"]:
                ok = False
        if a["name"] == "Achievement Grant" and act is not None and act >= 20:
            ok = False  # Achievement is specifically for ACT 18-19
        needs_info = (a["min_gpa"] is not None and gpa is None) or (a["min_act"] is not None and act is None)
        if ok and not needs_info and not (set(a["tags"]) & {"need", "education"}):
            eligible.append(a)
        elif ok or needs_info:
            maybe.append(a)
    note = data["notes"].get("international_hybrid") if group == "international_hybrid" else None
    return {"group": GROUPS[group], "eligible": eligible, "maybe": maybe, "note": note,
            "notes": data["notes"], "groups": GROUPS}


# ---------- Onboarding ----------

@router.get("/onboarding")
def onboarding_index():
    return {k: v["label"] for k, v in checklists().items()}


@router.get("/onboarding/{kind}")
def onboarding(kind: str):
    c = checklists().get(kind)
    if not c:
        raise HTTPException(404, "Unknown student type")
    return c


# ---------- passages for the chat index ----------

def passages() -> list[dict]:
    """Turn the structured data into searchable passages (same shape as seed entries)."""
    out = []
    groups: dict[tuple, list[dict]] = {}
    for p in programs():
        groups.setdefault((p["area"], p["level"], p["format"]), []).append(p)
    for (area, level, fmt), ps in groups.items():
        names = "; ".join(f"{p['name']} ({p['degree']})" + (
            f" with concentrations in {', '.join(p['concentrations'])}" if p.get("concentrations") else "") for p in ps)
        aud = {"Undergraduate": ["prospective", "undergraduate"], "Associate": ["prospective", "online"],
               "Graduate": ["prospective", "graduate"], "Doctoral": ["prospective", "doctoral"],
               "Certificate": ["prospective", "online", "graduate"]}.get(level, ["all"])
        if "international" in fmt.lower():
            aud = ["international", "graduate", "doctoral"]
        out.append({"id": f"programs-{area}-{level}-{fmt}", "cat": "Academics", "audiences": aud,
                    "title": f"{level} programs in {area} ({fmt})",
                    "url": ps[0]["url"] if len(ps) == 1 else _load("programs.json")["source"], "updated": "current site",
                    "text": f"Belhaven {level.lower()} programs in {area}, format {fmt}: {names}. "
                            f"Explore all programs in the Program Finder."})
    for o in offices():
        bits = [f"{o['name']} handles: {o['handles']}."]
        if o["phone"] and o["email"]:
            bits.append(f"Phone {o['phone']}, email {o['email']}.")
        elif o["phone"]:
            bits.append(f"Phone {o['phone']}.")
        elif o["email"]:
            bits.append(f"Email {o['email']}.")
        if o["location"]:
            bits.append(f"Location: {o['location']}.")
        out.append({"id": f"office-{o['name']}", "cat": "Student Services", "audiences": ["all"],
                    "title": f"Contact: {o['name']}", "url": o["url"], "updated": "current site", "text": " ".join(bits)})
    return out
