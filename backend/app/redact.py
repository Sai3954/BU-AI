"""Remove personal information from text before it is logged or sent to an AI provider.

Students sometimes paste their SEVIS ID, phone number, email, address or ID number into a question. The
assistant never needs those to answer, so they are replaced with placeholders like [EMAIL] before
anything leaves the request: the question log, the admin dashboard and the AI provider only ever see
the redacted text.

Only contact details that are *published in the knowledge base* (office emails such as
registrar@belhaven.edu, office phone numbers, the campus street addresses) are kept, because students
ask about them. Everything else that looks personal is removed. The allowlist is rebuilt from the
content whenever the search index is rebuilt (see refresh_allowlist).

Known limits (pattern rules, not AI): a lowercase single first name with nothing around it
("i am ravi") or names written without an introduction ("ravi needs cpt") can still get through.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

EMAIL_RX = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PHONE_CORE = re.compile(r"\d{3}\D{0,3}\d{3}\D?\d{4}")
STREET_SUFFIX = (r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|drive|dr|lane|ln|court|ct|place|pl|way|"
                 r"circle|cir|parkway|pkwy|highway|hwy|terrace|ter|trail|trl|loop|row|square|sq)")

# Everyday words that are never treated as names after "I am ...". The knowledge base vocabulary is
# added at runtime, so university terms ("international", "residency", "transfer") count as words too.
COMMON = set("""
a an the and or not but so if then than that this these those to of in on at by for from with about into over
after before during while because as up down out off again also just only very really too quite still even
i me my mine we our you your he she they them their it its is am are was were be been being have has had do
does did doing will would can could should may might must shall going go gone get getting got make made take
taking took come coming came see saw know knew think thought want wanted need needed looking look trying try
tried planning plan hoping hope asking ask wondering wonder confused worried sure unsure new old current
currently already almost about here there now today tomorrow yesterday soon late early first last next back
student students international undergraduate graduate doctoral online prospective transfer freshman
sophomore junior senior alumni alumnus faculty staff parent mom dad mother father friend applying applied
enrolled enrolling admitted accepted registered working work job employed unemployed interested moving
living staying studying taking finishing finished starting started done ready able unable allowed eligible
not no yes okay ok fine good great bad happy sad sorry glad afraid scared nervous excited tired busy free
f1 f-1 h1b h-1b h4 green card holder citizen resident visa holder from india usa us america
in-state out-of-state mba msitm dba phd masters bachelors major minor nursing business education
""".split())

PATTERNS = [
    ("SSN", re.compile(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b")),
    ("SEVIS_ID", re.compile(r"\bN\s?\d{10}\b", re.I)),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("RECEIPT", re.compile(r"\b(?:IOE|EAC|WAC|LIN|SRC|NBC|MSC|YSC)\d{10}\b", re.I)),
    ("EMAIL", EMAIL_RX),
    ("PHONE", re.compile(r"\+\d{1,3}[\s.-]?\(?\d{2,5}\)?(?:[\s.-]?\d{2,5}){1,3}\b")),
    ("PHONE", re.compile(r"(?:\b1[ .-]?)?\(?\b\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b")),
    ("STUDENT_ID", re.compile(r"\b(?:student\s*(?:id|number|no\.?)|(?:my\s+)?id\s*(?:number|no\.?|#)?(?:\s+is)?)\s*[:#]?\s*[A-Z]{0,2}\d{5,10}\b", re.I)),
    ("STUDENT_ID", re.compile(r"\b[BS]\d{6,9}\b")),
    ("A_NUMBER", re.compile(r"\bA[- ]?\d{8,9}\b", re.I)),
    ("PASSPORT", re.compile(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{8,9}\b")),
    ("DOB", re.compile(r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)\d{2}\b")),
    ("ADDRESS", re.compile(r"(?i:\b(?:i live at|i live on|my address is|my home address is|address\s*:)\s+)[^.?!\n]{4,90}")),
    ("ADDRESS", re.compile(rf"\b\d{{1,6}}\s+(?:[NSEW]\.?\s+)?(?:[A-Za-z0-9'.-]+\s+){{0,4}}{STREET_SUFFIX}\b\.?"
                           rf"(?:,?\s*(?:apt|apartment|unit|suite|ste|#)\.?\s*[\w-]+)?"
                           rf"(?:,?\s*[A-Za-z .]+,?\s*[A-Z]{{2}}\s*\d{{5}}(?:-\d{{4}})?)?", re.I)),
    ("ADDRESS", re.compile(r"(?i:\b(?:apt|apartment|unit)\.?\s*#?\s*)\d+[A-Za-z]?\b")),
    ("ID_NUMBER", re.compile(r"(?<![\d$.,-])\b\d{7,10}\b(?![\d,.%-])")),
]

NAME_WORD = r"[A-Za-z][A-Za-z'-]+"
NAME_INTRO = re.compile(rf"\b((?i:my name is|my name's|this is|name\s*:|i am called|call me|i'm called))\s+({NAME_WORD}(?:\s+{NAME_WORD}){{0,4}})")
NAME_IAM = re.compile(rf"\b((?i:i am|i'm|im))\s+({NAME_WORD}(?:\s+{NAME_WORD}){{0,4}})")
SIGNOFF = re.compile(rf"((?i:thanks|thank you|thx|regards|best regards|sincerely|best|cheers),?\s*\n?\s*-?\s*)({NAME_WORD}(?:\s+{NAME_WORD}){{0,4}})\s*[.!]?\s*$")
# Only university office addresses can be allowlisted; student and outside addresses never are,
# even if they appear on a crawled page (a news story, a club page).
OFFICE_EMAIL = re.compile(r"^[\w.+-]+@belhaven\.edu$", re.I)

_allowed_emails: set[str] = set()
_allowed_phones: set[str] = set()
_allowed_addresses: list[str] = []
_vocab: set[str] = set()


def _digits(s: str) -> str:
    d = re.sub(r"\D", "", s)
    return d[1:] if len(d) == 11 and d.startswith("1") else d


def refresh_allowlist(texts) -> None:
    """Rebuild the published-contact allowlist and vocabulary from knowledge-base text."""
    emails, phones, addrs, vocab = set(), set(), [], set()
    for t in texts:
        emails |= {e.lower() for e in EMAIL_RX.findall(t)}
        phones |= {_digits(p) for p in PHONE_CORE.findall(t)}
        for m in re.finditer(rf"\b\d{{2,6}}\s+(?:[A-Za-z'.-]+\s+){{0,3}}{STREET_SUFFIX}\b", t, re.I):
            addrs.append(m.group(0).lower())
        vocab |= {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]+", t)}
    _allowed_emails.clear(); _allowed_emails.update(e for e in emails if OFFICE_EMAIL.match(e))
    _allowed_phones.clear(); _allowed_phones.update(p for p in phones if len(p) == 10)
    _allowed_addresses.clear(); _allowed_addresses.extend(sorted(set(addrs)))
    _vocab.clear(); _vocab.update(vocab)


def _bootstrap_allowlist() -> None:
    texts = []
    for name in ("seed_kb.json", "directory.json"):
        try:
            texts.append(json.dumps(json.loads((DATA / name).read_text(encoding="utf-8"))))
        except Exception:
            pass
    refresh_allowlist(texts)


_bootstrap_allowlist()


def _published(kind: str, value: str) -> bool:
    v = value.strip()
    if kind == "EMAIL":
        return v.lower() in _allowed_emails
    if kind == "PHONE":
        return _digits(v) in _allowed_phones
    if kind == "ADDRESS":
        low = v.lower()
        return any(a in low or low.strip(" .,") in a for a in _allowed_addresses)
    return False


def _is_word(w: str) -> bool:
    lw = w.lower()
    return lw in COMMON or lw in _vocab


def _name(prefix: str, words: str, found: list[str], strict: bool) -> str:
    """Redact the name part of 'prefix words'. strict: lowercase 'i am ...' needs two unknown words."""
    parts = words.split()
    kept = []
    for w in parts:
        if _is_word(w):
            break
        kept.append(w)
    looks_proper = bool(kept) and all(w[0].isupper() for w in kept)
    if not kept or (strict and not looks_proper and len(kept) < 2):
        return f"{prefix} {words}"
    found.append("NAME")
    rest = parts[len(kept):]
    return f"{prefix} [NAME]" + (" " + " ".join(rest) if rest else "")


def redact(text: str) -> tuple[str, list[str]]:
    """Return (redacted_text, kinds_found)."""
    found: list[str] = []
    out = text
    for kind, rx in PATTERNS:
        def sub(m: re.Match, kind=kind) -> str:
            if _published(kind, m.group(0)):
                return m.group(0)
            found.append(kind)
            return f"[{kind}]"
        out = rx.sub(sub, out)
    out = NAME_INTRO.sub(lambda m: _name(m.group(1), m.group(2), found, strict=False), out)
    out = NAME_IAM.sub(lambda m: _name(m.group(1), m.group(2), found, strict=True), out)
    out = SIGNOFF.sub(lambda m: m.group(1) + "[NAME]" if not _is_word(m.group(2).split()[0]) and found.append("NAME") is None
                      else m.group(0), out)
    return out, sorted(set(found))
