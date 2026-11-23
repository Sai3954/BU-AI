"""Programmatic checks on AI answers, in addition to the prompt rules.

Checks, sentence by sentence:
  1. Citations: numbers in brackets that point to no source are removed.
  2. Figures (amounts, dates, credit hours, counts, including single digits next to a unit such as
     "6 credit hours"): each must appear in the source cited in that sentence.
       - unverified:    found in no source
       - misattributed: found in the sources, but not in the cited one, or in the cited source next to
                        a different subject ("$620" for a 40-meal plan when the page gives $620 for 80 meals)
  3. Uncited: sentences that state a figure or a rule but cite nothing.
  4. Unsupported claims: promises such as "guaranteed admission" or "you will be approved" whose key word
     doesn't appear in the cited sources.
  5. Optional AI review (VERIFY_WITH_AI=true): a second model call lists sentences the sources don't
     support. Off by default because it roughly doubles AI cost per answer.

Pattern rules catch common errors cheaply; they are not a full fact-checker. Anything flagged is shown to
the student as "Check before relying on this" and counted on the admin dashboard.
"""
from __future__ import annotations

import json
import re

from .retrieval import Doc, stem

CITE = re.compile(r"\[(\d+)\]")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z*\-\[(])|\n+")
UNIT = (r"(?:credit|credits|credit-hour|hours?|days?|weeks?|months?|years?|semesters?|terms?|courses?|classes|"
        r"class|times?|residenc(?:y|ies)|meals?|pages?|letters?|attempts?|signatures?|percent|%)")
FIG = re.compile(rf"\$?\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?%?|\$?\d[\d,]*(?:\.\d+)?%?(?=\s*{UNIT}\b)|\$?\d{{2,}}[\d,]*(?:\.\d+)?%?|\$\d(?:\.\d+)?|\d+\.\d+", re.I)
CLAUSE = re.compile(r",(?!\d{3}(?!\d))|[;:()]|\s(?:and|but|while|whereas)\s|\.\s")  # "27,275" stays whole
PHONE = re.compile(r"\(?\b\d{3}\)?[-.\s]\d{3}[-.]\d{4}\b")
CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")  # a clock time is one figure, not "10" and "00"


def _time_on_page(h: str, m: str, scope: str) -> bool:
    """10:00 in the answer matches 10:00, 10:00pm or "10 p.m." on the page; 7:30 needs 7:30."""
    h = str(int(h))
    if re.search(rf"(?<!\d)0?{h}:{m}(?!\d)", scope):
        return True
    return m == "00" and re.search(rf"(?<![\d:])0?{h}\s*(?:a\.?\s?m\b|p\.?\s?m\b|o'clock|noon|midnight)", scope, re.I) is not None
NOISE = re.compile(r"https?://\S+|\b[\w.+-]+@[\w-]+\.[\w.]+|\b[A-Z]-\d{1,4}\b|"
                   r"(?:about |~)?\b\d+\s+(?:years?|months?)\s+ago\b", re.I)  # links, emails, form IDs (I-20), page ages: not figures
RISKY = re.compile(r"\b(guarantee[sd]?|guaranteed|automatically|definitely|certainly|"
                   r"no (?:need|requirement)|not required|unlimited|free of charge|100%|"
                   r"(?:you|students?) (?:will|are going to) (?:be )?(?:admitted|accepted|approved|eligible|"
                   r"get|receive|qualify))\b", re.I)
GENERIC = set("""the a an is are be it this that of to for in on at by with and or your you can will per
each its their there as from cost costs fee fees price priced charge charged total about up usd dollars
dollar""".split())
RULE_WORDS = re.compile(r"\b(must|required|requires|need to|deadline|due|minimum|maximum|at least|"
                        r"no later than|eligible|cannot|can't|not allowed)\b", re.I)


def _norm(s: str) -> str:
    # "$85.00" on the page and "$85" in the answer are the same amount; "85.50" stays different.
    return re.sub(r"\.0+$", "", s.replace("$", "").replace(",", "").rstrip("%").rstrip("."))


def _words(s: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z][a-z]+", s.lower()) if w not in GENERIC and len(w) > 2}


def _numbers(s: str) -> set[str]:
    return {_norm(x) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", s)}


def _clauses(text: str) -> list[str]:
    return [c for c in CLAUSE.split(text) if c and c.strip()]


def _occurrences(value: str, text: str) -> list[str]:
    """Clauses of a source that contain the figure."""
    return [c for c in _clauses(text) if value in _numbers(c)]


def _context_ok(fig_value: str, answer_clause: str, src_clauses: list[str], answer_wide: str = "",
                wide=lambda c: c) -> bool:
    """The figure's subject in the answer should match its subject in the source.

    Numbers are compared clause to clause ("40 meals" vs "80 meals"); subject words may sit one clause away
    ("Active duty: USD 250 for undergraduate" vs "active duty USD 250 per credit (undergraduate)")."""
    a_nums = _numbers(answer_clause) - {fig_value}
    a_words = _words(CITE.sub(" ", answer_wide or answer_clause))
    for sc in src_clauses:
        s_nums = _numbers(sc) - {fig_value}
        if a_nums and s_nums and not (a_nums & s_nums):
            continue  # e.g. answer pairs $620 with "40 meals"; source pairs it with "80 meals"
        s_words = _words(wide(sc))
        if not a_words or (a_words & s_words) or not s_words:
            return True
    return False


def _sentences(text: str) -> list[tuple[str, list[int]]]:
    """Sentences, each with the citations of the next cited sentence on the same line.

    "Download the packet. Fill in the form. [1]" cites [1] once for the whole line, so the first sentence
    is checked against [1] instead of being reported as uncited."""
    out = []
    for block in re.split(r"\n\s*\n", text):  # a citation at the end of a paragraph or list covers it
        parts = [p for p in re.split(r"(?<=[.!?])\s+(?=[A-Z*\-\[(])|\n", block) if p.strip()]
        following: list[int] = []
        tagged = []
        for p in reversed(parts):
            own = sorted({int(c) - 1 for c in CITE.findall(p)})
            if own:
                following = own
            tagged.append((p, [] if own else following))
        tagged.reverse()
        previous: list[int] = []  # "Hours are: [1]" then an uncited list: the lead-in's citation covers it
        for j, (p, inh) in enumerate(tagged):
            own = sorted({int(c) - 1 for c in CITE.findall(p)})
            if own:
                previous = own
            elif not inh:
                tagged[j] = (p, previous)
        out.extend(tagged)
    return out


# Safety lines Bela is told to give (prompts.py, CRISIS_TEXT): fixed, hand-checked numbers, not claims from sources.
SAFETY = re.compile(r"\b988\b|crisis lifeline|\b911\b", re.I)
SAFETY_PHONES = {"6019688865", "6019654128"}


def check(answer: str, docs: list[Doc], question: str = "") -> dict:
    n = len(docs)
    bad_cites = sorted({int(m) for m in CITE.findall(answer) if not 1 <= int(m) <= n})
    cleaned = CITE.sub(lambda m: m.group(0) if 1 <= int(m.group(1)) <= n else "", answer)
    texts = [f"{d.title}. {d.text} Page date: {getattr(d, 'updated_label', '') or 'not listed'}." for d in docs]
    all_text = " ".join(texts)

    unverified, misattributed, uncited, unsupported = [], [], [], []
    if not docs:  # our own "couldn't find" message: nothing to check against
        return {"text": cleaned, "unverified": [], "misattributed": [], "uncited": [], "unsupported_claims": [],
                "invalid_citations": bad_cites, "cited": False}
    q_nums = _numbers(question)
    digits = lambda x: re.sub(r"\D", "", x)
    all_phones = {digits(p) for p in PHONE.findall(all_text)}
    for sentence, inherited in _sentences(cleaned):
        if SAFETY.search(sentence):
            continue  # a crisis line: always shown, never flagged
        cited = sorted({int(c) - 1 for c in CITE.findall(sentence)}) or inherited
        scope = " ".join(texts[i] for i in cited) if cited else all_text
        body = NOISE.sub(" ", CITE.sub(" ", sentence))
        for ph in PHONE.findall(body):
            d = digits(ph)
            if d in SAFETY_PHONES:
                continue
            if d not in {digits(p) for p in PHONE.findall(scope)}:
                (misattributed if d in all_phones else unverified).append(ph.strip())
        body = PHONE.sub(" ", body)
        for tm in CLOCK.finditer(body):
            if not _time_on_page(tm.group(1), tm.group(2), scope):
                unverified.append(tm.group(0))
        body = CLOCK.sub(" ", body)
        figs = [m for m in FIG.finditer(body)]
        own_voice = (re.match(r"^\W*(i|i'm|i've|i'd)\b", body, re.I) or re.search(r"\b(the|these|those)( same)? (sources|pages)\b", body, re.I)
                     or body.strip().endswith(":"))
        if (figs or RULE_WORDS.search(body)) and not cited and not own_voice and len(body.split()) >= 3:
            uncited.append(body.strip()[:160])
        for m in figs:
            raw = m.group(0).rstrip(".,")
            v = _norm(raw)
            if not v or v in q_nums:  # the student's own numbers (GPA, ACT) are not claims
                continue
            bc = _clauses(body)
            ci = next((i for i, c in enumerate(bc) if raw in c or v in _numbers(c)), -1)
            clause = bc[ci] if ci >= 0 else body
            answer_wide = (bc[ci - 1] + " " + clause) if ci > 0 else clause
            sc = _clauses(scope)
            wide = lambda c, sc=sc: " ".join(x for x in (sc[sc.index(c) - 1] if sc.index(c) > 0 else "", c,
                                                         sc[sc.index(c) + 1] if sc.index(c) + 1 < len(sc) else "") if x)
            in_scope = _occurrences(v, scope)
            # In "a 40-meal block costs $620", judge the amount; the count is only its subject.
            subject_only = not raw.startswith("$") and "$" in clause
            if in_scope:
                if not subject_only and not _context_ok(v, clause, in_scope, answer_wide, wide):
                    misattributed.append(raw)
            elif v in _numbers(all_text):
                misattributed.append(raw)
            else:
                unverified.append(raw)
        for rm in RISKY.finditer(body):
            key = rm.group(0).lower()
            anchor = {"guarantee": "guarantee", "guaranteed": "guarantee", "guarantees": "guarantee",
                      "automatically": "automatic", "unlimited": "unlimited", "100%": "100%",
                      "free of charge": "free", "not required": "not required", "no need": "no need",
                      "no requirement": "no requirement"}.get(key, key.split()[-1])
            low = scope.lower()
            stem_ = anchor.rstrip("ed").rstrip("e")
            neg = r"(?:not|no|never|cannot|can't|isn't|aren't|doesn't|don't|won't|does not|do not|is not)"
            if re.search(rf"\b{neg}\s+(?:\w+\s+){{0,8}}{re.escape(stem_)}", body.lower()):
                continue  # "doesn't guarantee an award" is the cautious reading, not a promise
            if anchor not in low:
                unsupported.append(rm.group(0))
                continue
            # The source mentions it, but denies it ("approval is not guaranteed") while the answer affirms it.
            denied = re.search(rf"\b(?:{neg[3:-1]}|without)\s+(?:\w+\s+){{0,4}}{re.escape(stem_)}", low)
            if denied:
                unsupported.append(rm.group(0))
    return {
        "text": cleaned,
        "unverified": sorted(set(unverified))[:10],
        "misattributed": sorted(set(misattributed))[:10],
        "uncited": uncited[:5],
        "unsupported_claims": sorted(set(unsupported))[:5],
        "invalid_citations": bad_cites,
        "cited": bool(CITE.search(cleaned)),
    }


def issue_count(result: dict) -> int:
    return (len(result.get("unverified", [])) + len(result.get("misattributed", []))
            + len(result.get("uncited", [])) + len(result.get("unsupported_claims", []))
            + len(result.get("ai_flags", [])))


# ---------- optional AI review ----------

VERIFY_SYSTEM = """You check answers for a university help assistant. You are given numbered SOURCES and an ANSWER.
List every sentence of the ANSWER that states something the SOURCES do not support, or that attaches a number,
date or rule to the wrong subject. Respond with JSON only: {"unsupported": ["<sentence>", ...]}. Use an empty list
if everything is supported."""


def ai_review(provider, answer: str, docs: list[Doc]) -> list[str]:
    src = "\n\n".join(f"[{i + 1}] {d.title}\n{d.text}" for i, d in enumerate(docs))
    raw = "".join(provider.stream(VERIFY_SYSTEM, f"SOURCES\n{src}\n\nANSWER\n{answer}"))
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0)).get("unsupported", [])
    except (ValueError, AttributeError):
        return []
    return [str(x)[:200] for x in items if str(x).strip()][:5]
