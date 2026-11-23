"""The topic a typed question is about, read from its own words.

Used to (1) give retrieval the same small category boost that the topic buttons already give, so a question
about graduate scholarships prefers Financial Aid pages over a music-major page that mentions scholarships,
and (2) pick follow-up suggestions that match the question rather than whatever pages happened to be found.
Conservative on purpose: clear keywords only; anything else returns "" and nothing changes.
"""
from __future__ import annotations

import re

# Checked in order: the first match wins ("CPT scholarship" is an immigration question first).
TOPICS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(cpt|opt|stem opt|sevis|i-?20|f-?1|f-?2|visa|dso|ead)\b", re.I), "International"),
    (re.compile(r"\b(password|passwords|duo|two-factor|mfa|portalguard|wi-?fi|blazenet|canvas|locked out|"
                r"log ?in|sign ?in|e-?mail (account|password|access|login)|"
                r"(can'?t|cannot|unable to|trouble|problems?)\b[^.?!]{0,25}\be-?mail)\b",
                re.I), "IT Support"),
    (re.compile(r"\b(scholarships?|financial aid|fafsa|loans?|grants?|work-?study|tuition|payment plan|refund|"
                r"1098-?t|cost of attendance)\b", re.I), "Financial Aid"),
    (re.compile(r"\b(admissions?|admitted|enrollment deposit|apply(ing)? (to|as) (belhaven|a|an|the)|"
                r"application (deadline|fee|status|requirements?))\b", re.I), "Admissions"),
    (re.compile(r"\b(library|librarian|interlibrary|databases?)\b", re.I), "Library"),
]
GRAD = re.compile(r"\b(graduate|master'?s?|mba|mha|mpa|m\.?ed|doctoral|doctorate|dba|ph\.?d|ed\.?d)\b", re.I)
DOCTORAL = re.compile(r"\b(doctoral|doctorate|dba|ph\.?d|ed\.?d|dissertation)\b", re.I)


def topic(question: str) -> str:
    for pat, cat in TOPICS:
        if pat.search(question or ""):
            return cat
    return ""
