"""Suggested follow-up questions shown under an answer.

Taken first from the official pages Bela just used (many Belhaven FAQ pages are titled with a question, such as
"Transfer Students - Does My GPA Transfer With My Credits?"), so a suggestion always points at something the
knowledge base can answer. A short, hand-written list per topic fills any gap. No AI call: instant and free.
"""
from __future__ import annotations

import difflib
import re

# Hand-written fallbacks, by page category. Each is a question the knowledge base answers well
# (checked in the 300-question test).
DEFAULTS: dict[str, list[str]] = {
    "International": ["What are the eligibility requirements for CPT?", "How long can I work on OPT?",
                      "How do I get a travel signature on my I-20?"],
    "Financial Aid": ["What is Belhaven's FAFSA school code?", "Does Belhaven offer a payment plan?",
                      "How do I contact the Financial Aid office?"],
    "Admissions": ["What are the admission requirements for first-year students?", "How do I schedule a campus visit?",
                   "What scholarships are available for incoming freshmen?"],
    "Academics": ["Where can I find the academic calendar?", "How do I drop a class?", "When are final exams?"],
    "Policies & Registrar": ["How do I request an official transcript?", "How do I contact the Registrar's Office?",
                             "What is the last day to withdraw from a course?"],
    "Campus Life": ["What meal plans are available?", "How do I apply for on-campus housing?",
                    "What clubs and organizations can I join?"],
    "Student Services": ["How do I contact the Registrar's Office?", "Is there free tutoring?",
                         "How do I request disability accommodations?"],
    "Wellness": ["How do I make an appointment with a counselor?", "Is there a health clinic on campus?",
                 "Is there free tutoring?"],
    "Campus Safety": ["Who do I contact for campus security?", "How do I get emergency alerts on my phone?"],
    "IT Support": ["How do I contact the IT Help Desk?", "How do I log in to Canvas?",
                   "How do I set up multi-factor authentication?"],
    "Library": ["What are the library hours?", "How do I access library databases from off campus?",
                "Can I borrow books through interlibrary loan?"],
    "Careers": ["Who can help me with my resume?", "Can alumni use the career services office?"],
    "Alumni": ["How can alumni request a transcript?", "Who do I contact in the alumni office?"],
    "Faculty & Staff": ["How do I contact Human Resources?", "Where is the employee directory?"],
}
GENERAL = ["How do I contact the Registrar's Office?", "How do I contact the Financial Aid office?",
           "What are the library hours?"]

ADDRESSED = re.compile(r"\b(you|your)\b", re.I)   # staff-interview titles ("What do you like most…?")


def _from_title(title: str) -> str | None:
    t = (title or "").strip()
    if "?" not in t:
        return None
    q = t.rsplit(" - ", 1)[-1].strip()
    if not q.endswith("?") or ADDRESSED.search(q) or not 15 <= len(q) <= 110:
        return None
    return q[0].upper() + q[1:]


def _similar(a: str, b: str) -> bool:
    a, b = a.lower().rstrip("?. "), b.lower().rstrip("?. ")
    if difflib.SequenceMatcher(None, a, b).ratio() > 0.6:
        return True
    wa, wb = set(re.findall(r"[a-z0-9]{4,}", a)), set(re.findall(r"[a-z0-9]{4,}", b))
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= 0.75


def followups(question: str, docs: list, k: int = 3) -> list[str]:
    """Up to k questions a student might ask next, none repeating the question just asked."""
    out: list[str] = []

    def add(q: str | None) -> None:
        if q and len(out) < k and not _similar(q, question) and not any(_similar(q, o) for o in out):
            out.append(q)

    for d in docs:
        if getattr(d, "category", "") != "News":
            add(_from_title(getattr(d, "title", "")))
    category = next((d.category for d in docs if getattr(d, "category", "") in DEFAULTS), "")
    for q in DEFAULTS.get(category, []) + GENERAL:
        add(q)
    return out
