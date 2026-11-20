"""Hybrid retrieval: BM25 keyword search + vector similarity, fused with Reciprocal Rank Fusion.

Keyword search catches exact terms (CPT, I-20, form names); vector search catches paraphrases
("can I go home for winter break while waiting on my work permit"). Either half works alone.
"""
from __future__ import annotations

import json
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass

import numpy as np

STOP = set("""a an and are as at be by can do does for from get how i if in is it me my of on or should the to
was what when where which who why will with you your am have has need about into than that this these those there
their they we our us any set up go going get got use using know tell find help want wanted like please
thanks thank hi hello hey just also doesn don didn isn aren wasn won t s ll ve re d long used there here much many some way ways able possible anyone someone things thing""".split())

PHRASES = [
    (r"\bi[- ]?20s?\b", " i20 "), (r"\bi[- ]?765\b", " i765 "), (r"\bi[- ]?983\b", " i983 "),
    (r"\bi[- ]?94\b", " i94 "), (r"\bi[- ]?797\b", " i797 "), (r"\bf[- ]?1\b", " f1 "), (r"\bf[- ]?2\b", " f2 "),
    (r"\bh[- ]?1b\b", " h1b "), (r"\be[- ]?verify\b", " everify "), (r"social security( number)?", " ssn "),
    (r"green card", " greencard "), (r"cap[- ]gap", " capgap "), (r"blaze ?net", " blazenet "),
    (r"e[- ]?mail", " email "), (r"two[- ]factor|2fa|mfa", " duo "),
]
SYN = {
    "cost": ["tuition", "fee"], "price": ["tuition", "fee"], "fee": ["tuition"], "tuition": ["fee", "cost"],
    "trip": ["travel"], "abroad": ["travel"], "vacation": ["travel"], "home": ["travel"],
    "job": ["employment", "career"], "work": ["employment", "job"], "internship": ["career", "cpt"],
    "scholarship": ["aid", "financial"], "aid": ["financial", "scholarship"], "money": ["tuition", "aid"],
    "insurance": ["health"], "wife": ["spouse", "dependent"], "husband": ["spouse", "dependent"],
    "kid": ["child", "dependent"], "children": ["child", "dependent"], "spouse": ["dependent", "f2"],
    "login": ["password", "helpdesk"], "password": ["login", "portalguard"], "canvas": ["login", "blazenet"],
    "miss": ["makeup"], "missed": ["makeup"], "diploma": ["graduation"], "lawyer": ["attorney"],
    "terminated": ["termination", "sevis"], "revoked": ["revocation"], "withdraw": ["withdrawal"],
    "unemployed": ["unemployment"], "english": ["toefl", "proficiency"], "toefl": ["english", "proficiency"],
    "ielts": ["english", "proficiency"], "apply": ["application", "admission"], "admission": ["apply"],
    "license": ["driver"], "dmv": ["driver"], "tax": ["taxes"], "h1b": ["capgap"],
    "balance": ["proof", "fund"], "bank": ["proof", "fund"], "phone": ["contact"], "office": ["contact"],
    "dorm": ["housing", "residence"], "room": ["housing", "residence"], "roommate": ["housing"],
    "food": ["dining", "meal"], "eat": ["dining", "meal"], "lunch": ["dining"], "breakfast": ["dining"],
    "log": ["login", "logg", "helpdesk"], "call": ["contact", "phone"], "book": ["library"], "borrow": ["loan", "library"], "renew": ["renewal", "library"], "research": ["library", "database"], "tutor": ["think", "tutoring"],
    "tutoring": ["think"], "disability": ["accommodation", "ada"], "counseling": ["care", "wellness"],
    "sick": ["health", "clinic"], "doctor": ["health", "clinic"], "resume": ["career"],
    "semester": ["term", "calendar"], "break": ["calendar", "holiday"], "deadline": ["calendar", "date"],
    "transcript": ["registrar"], "graduation": ["commencement", "registrar"], "wifi": ["helpdesk"],
    "event": ["calendar", "events"], "freshman": ["first", "undergraduate", "admission"],
    "gpa": ["admission"], "bill": ["payment", "tuition"], "plan": ["payment"], "pay": ["payment", "blazenet"], "gym": ["fitness"],
    "workout": ["fitness"], "parking": ["security", "campus"], "id": ["security", "student"], "college": ["admission", "undergraduate"], "concert": ["events"], "homecoming": ["events"],
}
RISK = re.compile(r"\b(terminat|revok|revocation|out of status|deport|arrest|reinstat|illegal|overstay|"
                  r"unauthori[sz]ed work|lost (my )?status|"
                  r"work(ed|ing)? (off[- ]campus )?without (an? )?(cpt|opt|ead|authori[sz]ation|permission)|"
                  r"(am|was) i (still )?(in|out of) status|sevis (record )?(inactive|terminat))", re.I)
CRISIS = re.compile(r"\b(suicid|kill myself|self[- ]harm|hurt myself|end my life)", re.I)

# The student's level, read from the question itself ("my DBA dissertation") or from the chosen role.
LEVELS = [
    ("doctoral", re.compile(r"\b(doctoral|doctorate|dba|ph\.?d|ed\.?d|dissertation|residenc(y|ies)|comps?|"
                            r"comprehensive exam|prospectus|irb|chair)\b", re.I)),
    ("graduate", re.compile(r"\b(graduate|grad school|master'?s?|mba|msitm|msl|m\.?ed|mfa|ma in|ms in)\b", re.I)),
    ("undergraduate", re.compile(r"\b(undergrad\w*|freshm[ae]n|sophomore|junior|senior year|bachelor'?s?|"
                                 r"first[- ]year|transfer student|high school)\b", re.I)),
    ("online", re.compile(r"\b(online|distance|remote(ly)?)\b", re.I)),
]
LEVEL_NAMES = {"doctoral", "graduate", "undergraduate"}
YEAR = re.compile(r"\b(20\d\d)\s*[-–/]\s*(?:20)?\d\d\b")
AGE = re.compile(r"(\d+)\s*years?\s*ago|a year ago", re.I)
VEC_MIN, VEC_STRONG, VEC_WEIGHT = 0.2, 0.5, 0.8   # cosine: a hit at all / strong enough to stand without keyword overlap


def detect_level(q: str, role: str = "") -> str:
    """Level from the question text first (it is more specific), else from the chosen role."""
    if re.search(r"\bgraduation\b", q, re.I) and not re.search(r"\bgraduate (student|program|school)", q, re.I):
        q = re.sub(r"\bgraduation\b", " ", q, flags=re.I)
    for name, rx in LEVELS:
        if rx.search(q):
            return name
    return role if role in LEVEL_NAMES or role == "online" else ""


def _academic_year(d: "Doc") -> int:
    m = YEAR.search(f"{d.url} {d.title}")
    return int(m.group(1)) if m else 0


def _age_years(label: str) -> int:
    m = AGE.search(label or "")
    return 0 if not m else (int(m.group(1)) if m.group(1) else 1)


ROLES = ["prospective", "undergraduate", "graduate", "doctoral", "international", "online", "faculty", "alumni"]


def stem(w: str) -> str:
    if len(w) > 6 and w.endswith("ing"):
        w = w[:-3]
        return w[:-1] if w.endswith("ll") else w
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is", "as")):
        return w[:-1]
    return w


def tokenize(s: str) -> list[str]:
    t = f" {s.lower()} "
    for pat, rep in PHRASES:
        t = re.sub(pat, rep, t)
    return [stem(w) for w in re.split(r"[^a-z0-9]+", t) if w and w not in STOP]


def is_high_risk(q: str) -> bool:
    return bool(RISK.search(q))


def is_crisis(q: str) -> bool:
    return bool(CRISIS.search(q))


@dataclass
class Doc:
    id: int
    url: str
    title: str
    category: str
    audiences: list[str]
    text: str
    updated_label: str

    def public(self) -> dict:
        return {"title": self.title, "url": self.url, "category": self.category,
                "updated": self.updated_label, "text": self.text}


class HybridIndex:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.docs: list[Doc] = []
        self.tf: list[Counter] = []
        self.lens: list[int] = []
        self.df: Counter = Counter()
        self.avg = 1.0
        self.vectors: np.ndarray | None = None

    def build(self, rows) -> None:
        docs, tfs, lens, df, vecs = [], [], [], Counter(), []
        for r in rows:
            d = Doc(r.id, r.url, r.title, r.category, (r.audiences or "all").split(","), r.text, r.updated_label)
            tt = tokenize(d.title)
            toks = tt * 3 + tokenize(d.text)
            tf = Counter(toks)
            docs.append(d); tfs.append(tf); lens.append(len(toks)); df.update(tf.keys())
            vecs.append(json.loads(r.embedding) if r.embedding else None)
        vectors = None
        if docs and all(v is not None for v in vecs):
            m = np.array(vecs, dtype=np.float32)
            vectors = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)
        with self.lock:
            self.docs, self.tf, self.lens, self.df = docs, tfs, lens, df
            self.avg = (sum(lens) / len(lens)) if lens else 1.0
            self.vectors = vectors

    @property
    def has_vectors(self) -> bool:
        return self.vectors is not None

    def _bm25(self, query: str) -> list[tuple[int, float]]:
        base = tokenize(query)
        weights: dict[str, float] = {}
        for w in base:
            weights[w] = weights.get(w, 0) + 1
        for w in base:
            for s in SYN.get(w, []):
                weights.setdefault(stem(s), 0.5)
        n, k1, b = len(self.docs), 1.4, 0.6
        out = []
        for i, tf in enumerate(self.tf):
            s = 0.0
            for w, qw in weights.items():
                f = tf.get(w)
                if not f:
                    continue
                dfw = self.df.get(w, 0)
                idf = math.log(1 + (n - dfw + 0.5) / (dfw + 0.5))
                s += qw * idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * self.lens[i] / self.avg))
            if s > 0:
                out.append((i, s))
        out.sort(key=lambda x: -x[1])
        return out

    def _vector(self, qvec: list[float] | None) -> list[tuple[int, float]]:
        if qvec is None or self.vectors is None:
            return []
        q = np.array(qvec, dtype=np.float32)
        q /= (np.linalg.norm(q) + 1e-9)
        sims = self.vectors @ q
        order = np.argsort(-sims)[:30]
        return [(int(i), float(sims[i])) for i in order if sims[i] > VEC_MIN]

    def search(self, query: str, role: str = "", qvec: list[float] | None = None, k: int = 6,
               category: str = "") -> list[Doc]:
        with self.lock:
            if not self.docs:
                return []
            kw = self._bm25(query)
            vec = self._vector(qvec)
            if not kw and not vec:
                return []
            # Off-topic guard: unless the meaning match is strong, require that the best keyword matches
            # cover at least half of the meaningful words in the question.
            base = set(tokenize(query))
            strong_vec = bool(vec) and vec[0][1] >= VEC_STRONG
            if not strong_vec:
                vec = [x for x in vec if x[1] >= VEC_STRONG * 0.8]
            if not strong_vec and base:
                alts = {w: {w, *(stem(x) for x in SYN.get(w, []))} for w in base}
                covered = {w for w in base for i, _ in kw[:3] if alts[w] & self.tf[i].keys()}
                cov = len(covered) / len(base)
                unknown = any(not (alts[w] & self.df.keys()) for w in base)
                if cov < 0.5 or (cov <= 0.5 and unknown):
                    return []
            # Keep keyword hits that are reasonably close to the best one.
            if kw:
                top = kw[0][1]
                kw = [x for x in kw if x[1] >= top * 0.3][:30]
            scores: dict[int, float] = {}
            for rank, (i, _) in enumerate(kw):
                scores[i] = scores.get(i, 0) + 1 / (60 + rank)
            # The on-server embedding model is small, so meaning matches count a bit less than exact terms.
            for rank, (i, _) in enumerate(vec):
                scores[i] = scores.get(i, 0) + VEC_WEIGHT / (60 + rank)
            kw_score = dict(kw)
            kw_top = kw[0][1] if kw else 0
            level = detect_level(query, role)
            vec_top = {i for i, sim in vec[:5] if vec and sim >= vec[0][1] - 0.05}
            newest = max((_academic_year(self.docs[i]) for i in scores), default=0)
            def near(i: int) -> bool:
                return kw_score.get(i, 0) >= kw_top * 0.75 or i in vec_top
            # Only demote another level's page when a close match exists for this student's own level.
            own_level_alt = level in LEVEL_NAMES and any(level in self.docs[j].audiences and near(j) for j in scores)
            for i in scores:
                d = self.docs[i]
                # Prefer pages for the student's level; push down pages written only for another level.
                # (Scores here are rank-fusion values ~0.016; one rank step is ~0.0003, so these are tie-breakers.)
                if level:
                    lv = set(d.audiences) & LEVEL_NAMES
                    if level in d.audiences and near(i):
                        scores[i] += 0.0015
                    elif lv and own_level_alt and "all" not in d.audiences:
                        scores[i] -= 0.0015
                # Prefer current information: older catalog years and pages untouched for years rank lower.
                y = _academic_year(d)
                if y and newest and y < newest:
                    scores[i] -= 0.0015 * min(newest - y, 3)
                scores[i] -= 0.0003 * min(_age_years(d.updated_label), 3)
                aud = self.docs[i].audiences
                # The role only breaks near-ties: a graduate student asking about OPT still gets the OPT pages,
                # not admission pages that merely share the word "apply".
                if role and kw_score.get(i, 0) >= kw_top * 0.75 and (role in aud or "all" in aud):
                    scores[i] += 0.004
                if category and self.docs[i].category == category:
                    scores[i] += 0.006
            # Diversity: at most two passages from the same page, so one long page can't crowd out the rest.
            out, per_url = [], Counter()
            for i, _ in sorted(scores.items(), key=lambda x: -x[1]):
                u = self.docs[i].url.split("#")[0]
                if per_url[u] >= 2:
                    continue
                per_url[u] += 1
                out.append(self.docs[i])
                if len(out) >= k:
                    break
            return out


index = HybridIndex()
