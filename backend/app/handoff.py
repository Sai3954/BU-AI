"""Human handoff: which university office should a student contact when Bela can't fully help.

Plain, reviewable rules (not AI guesses), checked in order. The student always sees the suggestion
and can pick another office, and sends any request themselves: nothing is sent on their behalf.
"""
from __future__ import annotations

import re

from .features import offices

IMMIGRATION = re.compile(r"\b(cpt|opt|stem opt|i-?20|sevis|f-?1|visa|status|travel signature|dso|work authori[sz]ation)\b", re.I)

# (pattern, office name, or a dict of office name by role/level)
RULES: list[tuple[re.Pattern, str | dict]] = [
    (re.compile(r"\b(password|duo|log ?in|sign ?in|wi-?fi|email account|blazenet|canvas (login|access))\b", re.I), "IT Help Desk"),
    # Library before Financial Aid, so an "interlibrary loan" is not read as a student loan
    (re.compile(r"\b(library|databases?|research help|interlibrary)\b", re.I), "Warren A. Hood Library"),
    (re.compile(r"\b(fafsa|scholarships?|grants?|loans?|financial aid|work[- ]study)\b", re.I), "Financial Aid"),
    (re.compile(r"\b(tuition|bill|billing|payments?|payment plan|refunds?|balance|1098)\b", re.I),
     {"online": "Online & Graduate Student Services", "graduate": "Online & Graduate Student Services",
      "doctoral": "Online & Graduate Student Services", "": "Business Office"}),
    (re.compile(r"\b(transcripts?|enrollment verification|graduat(e|ion) application|apply (for|to) graduat\w*|graduation|diploma|"
                r"grade appeal|register for classes|registration|drop (a )?class|withdraw|substitution|course waiver)\b", re.I), "Registrar"),
    (re.compile(r"\b(housing|dorm|residence hall|roommate)\b", re.I), "Office of Student Development / Housing"),
    (re.compile(r"\b(meal plan|dining|dinner|lunch|breakfast)\b", re.I), "Bailey Dining Commons"),
    # An admission counselor, or a counseling degree, is an admission question, not a wellbeing one
    (re.compile(r"\b(admissions?|enrollment) counselors?\b|\b(master'?s|degree|program|major)\b[^.?!]*\bcounsel|\bcounsel\w*\b[^.?!]*\b(degree|program|major)\b", re.I),
     {"international": "International Graduate Admission / Graduate International Office",
      "graduate": "Online & Graduate Admission", "online": "Online & Graduate Admission",
      "doctoral": "Online & Graduate Admission", "": "Undergraduate Admission"}),
    (re.compile(r"\b(counsel(ing|or)|stress(ed)?|anxi(ous|ety)|depress(ed|ion)|lonely)\b", re.I), "Counseling Services"),
    (re.compile(r"\b(tutor(ing)?|accommodations?|disabilit(y|ies)|academic advis(or|ing))\b", re.I), "Student Care & Think Center"),
    (re.compile(r"\b(career|resume|cover letter|internships?|job interview|handshake)\b", re.I), "Center for Career & Calling"),
    (re.compile(r"\b(veterans?|military|gi bill)\b", re.I), "Veterans Services"),
    (re.compile(r"\b(alumni|alumnus|alumna)\b", re.I), "Alumni / College Relations"),
    (re.compile(r"\b(apply|application|admission|admitted|accepted|transfer credit)\b", re.I),
     {"international": "International Graduate Admission / Graduate International Office",
      "graduate": "Online & Graduate Admission", "online": "Online & Graduate Admission",
      "doctoral": "Online & Graduate Admission", "": "Undergraduate Admission"}),
]

REASONS = {
    "immigration": "Immigration and CPT/OPT questions are handled by the DSO.",
    "rule": "This office handles this kind of question.",
}


def _public(o: dict) -> dict:
    return {k: o.get(k, "") for k in ("name", "email", "phone", "url", "location", "handles")}


def suggest_office(question: str, role: str = "", level: str = "") -> dict | None:
    """The office to suggest for a handoff, with a one-line reason, or None (the student chooses)."""
    by_name = {o["name"]: o for o in offices()}
    q = question or ""
    if IMMIGRATION.search(q):
        name = ("International Student Office (undergraduate)" if (level or role) == "undergraduate"
                else "DSO Support Tickets (International Graduate)")
        o = by_name.get(name)
        return {**_public(o), "reason": REASONS["immigration"]} if o else None
    key = level or role
    for rx, target in RULES:
        if rx.search(q):
            name = target if isinstance(target, str) else target.get(key, target.get(role, target[""]))
            o = by_name.get(name)
            if o:
                return {**_public(o), "reason": REASONS["rule"]}
    return None


def office_list() -> list[dict]:
    return [_public(o) for o in offices()]
