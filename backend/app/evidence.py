"""How well the retrieved pages support an answer, and what to do when they don't.

Every question goes through the same steps, whatever the topic:

1. normalize_query: everyday wording and abbreviations ("LOA", "whats", "intl", "comp sci") become the words the
   university's pages use, before searching.
2. assess: each retrieved passage is scored on how much of the question it covers (rare words count more than
   common ones) and how close it is in meaning. Passages that are clearly unrelated are dropped, so they are never
   shown or cited as an answer. The rest are labelled "direct" or "related".
3. The overall evidence level tells the answer writer what kind of reply the sources allow:
      direct  - at least one passage squarely covers the question
      related - only nearby information: say what it is, without presenting it as the answer
      none    - nothing usable: say so briefly and give the right verified office contact
4. answer_type classifies the finished reply (direct / partial / related / not verified), for the dashboard and tests.

No hand-written answers for particular questions: only general rules, so it works for every topic.
"""
from __future__ import annotations

import math
import re

import numpy as np

from .retrieval import GENERIC, SYN, Doc, stem, tokenize

# Everyday wording -> the words official pages use. Applied to the question only (never to the index).
ABBREV: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bloa\b", re.I), "leave of absence"),
    (re.compile(r"\bsap\b", re.I), "satisfactory academic progress"),
    (re.compile(r"\bfin(ancial)?\.? ?aid\b|\bfinaid\b", re.I), "financial aid"),
    (re.compile(r"\bintl\b|\binternat'?l\b", re.I), "international"),
    (re.compile(r"\bcomp\.? ?sci\b|\bc\.?s\.? (degree|major|program)\b", re.I), "computer science \\1"),
    (re.compile(r"\bprofs?\b", re.I), "professor"),
    (re.compile(r"\breg\b", re.I), "registration"),
    (re.compile(r"\bacct\b", re.I), "account"),
    (re.compile(r"\binfo\b", re.I), "information"),
    (re.compile(r"\bappt\b", re.I), "appointment"),
    (re.compile(r"\bsched\b", re.I), "schedule"),
    (re.compile(r"\bdept\b", re.I), "department"),
    (re.compile(r"\bresidence hall\b", re.I), "housing residence hall"),
    (re.compile(r"\bwhats\b", re.I), "what is"),
    (re.compile(r"\bwheres\b", re.I), "where is"),
    (re.compile(r"\bhows\b", re.I), "how is"),
    (re.compile(r"\bim\b", re.I), "i'm"),
    (re.compile(r"\bcant\b", re.I), "can't"),
    (re.compile(r"\bdont\b", re.I), "don't"),
    (re.compile(r"\bu\b", re.I), "you"),
    (re.compile(r"\bur\b", re.I), "your"),
    (re.compile(r"\b(pls|plz)\b", re.I), "please"),
    (re.compile(r"\bw/o\b", re.I), "without"),
    (re.compile(r"\bw/", re.I), "with "),
]
# Words that say how the student feels or asks, not what the answer is about.
FILLER = {stem(w) for w in ("really", "actually", "exactly", "currently", "right", "now", "today", "soon", "m",
                            "whats", "anybody", "somebody", "guys", "basically", "kinda", "sorta")}


def normalize_query(q: str) -> str:
    out = q or ""
    for rx, rep in ABBREV:
        out = rx.sub(rep, out)
    return re.sub(r"\s+", " ", out).strip()


def content_terms(query: str) -> list[str]:
    base = list(dict.fromkeys(tokenize(query)))
    words = [w for w in base if w not in GENERIC and w not in FILLER]
    return words or [w for w in base if w not in FILLER] or base


def _idf(index, w: str) -> float:
    hit = index.post.get(w)
    df = len(hit[0]) if hit is not None else 0
    n = max(1, len(index.docs))
    return math.log(1 + n / (df + 1))


def _alts(w: str) -> set[str]:
    return {w, *(stem(x) for x in SYN.get(w, []))}


def key_term(index, query: str) -> str:
    """The question's most specific word (the rarest across the pages), e.g. "intramural" or "absence"."""
    terms = content_terms(query)
    return max(terms, key=lambda w: _idf(index, w)) if terms else ""


def coverage(index, query: str, d: Doc) -> tuple[float, list[str]]:
    """Share of the question's meaningful words found in a passage, weighted so rare words count more."""
    terms = content_terms(query)
    if not terms:
        return 1.0, []
    have = set(tokenize(d.title)) | set(tokenize(d.text))
    tot = cov = 0.0
    missing = []
    for w in terms:
        wt = _idf(index, w)
        tot += wt
        if _alts(w) & have:
            cov += wt
        else:
            missing.append(w)
    return (cov / tot if tot else 1.0), missing


# Word coverage (rare words weigh more) is the main signal: the small on-server meaning model is noisy, so a high
# meaning score can only rescue a passage, never demote one.
DIRECT_COV, DIRECT_SIM_ALONE, DIRECT_SIM_MIN_COV = 0.60, 0.70, 0.45
# Below both of these, a passage is unrelated and is dropped.
KEEP_COV, KEEP_SIM = 0.35, 0.50


def assess(index, query: str, docs: list[Doc], qvec=None) -> dict:
    """Label each passage direct / related / unrelated and give the overall evidence level."""
    sims: list[float | None] = [None] * len(docs)
    if qvec is not None and index.vectors is not None and docs:
        pos = {id(d): i for i, d in enumerate(index.docs)}
        v = np.asarray(qvec, dtype=np.float32)
        v = v / (np.linalg.norm(v) + 1e-9)
        for k, d in enumerate(docs):
            i = pos.get(id(d))
            if i is not None:
                sims[k] = float(index.vectors[i] @ v)
    rows = []
    key = key_term(index, query)
    for d, sim in zip(docs, sims):
        cov, missing = coverage(index, query, d)
        s = sim if sim is not None else 0.0
        if cov >= DIRECT_COV or (s >= DIRECT_SIM_ALONE and cov >= DIRECT_SIM_MIN_COV):
            label = "direct"
        elif cov >= KEEP_COV or s >= KEEP_SIM or (key and key not in missing):
            label = "related"
        else:
            label = "unrelated"
        rows.append({"label": label, "coverage": round(cov, 2), "similarity": None if sim is None else round(s, 3),
                     "missing": missing})
    labels = [r["label"] for r in rows]
    level = "direct" if "direct" in labels else "related" if "related" in labels else "none"
    return {"level": level, "passages": rows}


def keep_relevant(docs: list[Doc], ev: dict) -> tuple[list[Doc], list[str]]:
    """Drop unrelated passages, so they are neither shown nor cited. Returns the kept docs and their labels."""
    kept, labels = [], []
    for d, r in zip(docs, ev["passages"]):
        if r["label"] != "unrelated":
            kept.append(d)
            labels.append(r["label"])
    return kept, labels


LEVEL_RANK = {"none": 0, "related": 1, "direct": 2}


def better(a: tuple[list, dict], b: tuple[list, dict]) -> bool:
    """True when result b is clearly better supported than result a (used after rewriting a weak query)."""
    ra, rb = LEVEL_RANK[a[1]["level"]], LEVEL_RANK[b[1]["level"]]
    if rb != ra:
        return rb > ra
    def best(r):
        return max((p["coverage"] + (p["similarity"] or 0) for p in r[1]["passages"] if p["label"] != "unrelated"),
                   default=0)
    return best(b) > best(a) + 0.05


def expanded_query(query: str) -> str:
    """A rewrite for a second search when the first one found only weak evidence: everyday words are swapped for
    the official ones, filler is removed and each remaining word's synonyms are added."""
    terms = content_terms(normalize_query(query))
    extra = []
    for w in terms:
        for s in SYN.get(w, []):
            if stem(s) not in terms and s not in extra:
                extra.append(s)
    return " ".join(terms + extra)


# ---------- classifying a finished answer (for tests and the dashboard; no AI call) ----------

NOT_FOUND = re.compile(r"\b(i (couldn't|could not|didn't|did not|wasn't able to|was not able to) (find|verify|confirm)|"
                       r"(isn't|is not|aren't|are not|wasn't|was not) (listed|in the sources|on the (university's )?pages|"
                       r"covered|available in)|(the )?(sources|pages) (i have |i found )?(don't|do not) "
                       r"(say|list|give|mention|describe|explain|include|cover))", re.I)
RELATED = re.compile(r"\b(related information|doesn't (directly )?answer|does not (directly )?answer|"
                     r"not a confirmed|isn't a confirmed|nearest|closest (information|page)|"
                     r"what i (did )?find (is|was) (about|on))", re.I)
CITE = re.compile(r"\[\d+\]")


def answer_type(answer: str, docs: list[Doc], level: str) -> str:
    """direct / partial / related / not_verified / declined - read from the reply itself and the evidence level."""
    text = answer or ""
    cited = bool(CITE.search(text)) and bool(docs)
    gap = bool(NOT_FOUND.search(text))
    if not cited:
        return "not_verified"
    if level == "related" or RELATED.search(text):
        return "related"
    return "partial" if gap else "direct"


# ---------- the reply when nothing usable was found ----------

def no_evidence_answer(question: str, office: dict | None) -> str:
    """Short, honest reply with a verified contact. Never invents a policy, number or date."""
    lines = ["I couldn't verify an answer to that in Belhaven's public web pages, so I don't want to guess."]
    if office:
        bits = [b for b in (office.get("phone"), office.get("email")) if b]
        handles = office.get("handles", "")
        who = f"**{office['name']}**" + (f" ({handles[0].lower() + handles[1:]})" if handles else "")
        lines.append(f"The office that handles this is {who}" + (f": {', '.join(bits)}." if bits else "."))
        lines.append("They can give you the confirmed answer for your situation.")
    else:
        lines.append("I can help with questions about Belhaven, such as admissions, financial aid, classes, "
                     "international student rules, campus life and student services. Try asking about one of "
                     "those, or rephrase your question with a few more details.")
    return "\n\n".join(lines)
