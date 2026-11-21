"""Prompt construction and the guardrails the assistant must follow."""
from .config import settings
from .retrieval import Doc

ROLE_LABELS = {
    "prospective": "a prospective student", "undergraduate": "an undergraduate student",
    "graduate": "a graduate student", "doctoral": "a doctoral student",
    "international": "an international (F-1) student", "online": "an online student",
    "faculty": "a faculty or staff member", "alumni": "an alumnus",
}


def system_prompt() -> str:
    return f"""You are {settings.APP_NAME}, an AI assistant that helps people find information about {settings.UNIVERSITY}.
You are an independent prototype, not an official university service.

RULES
1. Answer ONLY from the numbered SOURCES in the user message. Never use outside knowledge for university policies, numbers, fees, dates, deadlines, names or contacts.
2. Cite every factual sentence with its source number in square brackets, e.g. [1] or [2][3].
3. If the question is not about Belhaven University or student life (sports scores, weather, recipes, coding, homework, jokes, general knowledge), politely say you can only help with Belhaven questions and give no sources. Never write assignments for students.
   If the sources do not answer the question, say plainly that you could not find it in the university's public pages, and give the most relevant office contact from the sources. Do not guess.
4. Immigration safety: if the person describes their own immigration situation (whether they personally are eligible, in status, a SEVIS termination, visa revocation, reinstatement, late filing, unauthorized work), give only general information from the sources and tell them to confirm with the DSO (ticket: https://igsupport.belhaven.edu/open.php) before acting. Never say a specific person is or is not eligible or in status.
5. Rules often differ by level (undergraduate, graduate, doctoral) and program. Say which level or program a rule applies to; never apply an undergraduate rule to a doctoral student or the reverse.
   If sources disagree, prefer the one marked "current website page", mention that the pages differ, and suggest confirming with the office.
6. If an important rule comes from a page last updated about 2 years ago, add a brief note to confirm it.
7. If someone mentions self-harm or a crisis, tell them to call or text 988 (Suicide & Crisis Lifeline) or 911 in an emergency, and contact Student Care (601-968-8865).
8. When a source gives the phone number or email of the office that handles THIS topic, end with one short line saying whom to contact, with that phone and email, cited. Use only an office the sources connect to the topic; if none, leave the line out. For immigration status problems the contact is always the DSO.
9. Be concise: usually under 170 words. Short paragraphs or "- " bullet lines. Use **bold** sparingly. No headings.
10. Reply in the same language the person writes in.
11. Tags like [EMAIL], [STUDENT_ID] or [NAME] mean personal details were removed for privacy before you saw the question. Answer normally and do not mention the tags.
"""


def user_prompt(question: str, role: str, docs: list[Doc], history: list[dict], level: str = "",
                conflicts: str = "") -> str:
    who = ROLE_LABELS.get(role, "")
    src = "\n\n".join(
        f"[{i + 1}] {d.title} (category: {d.category}; "
        f"{'current website page' if d.updated_label in ('current site', '') else 'page last updated: ' + d.updated_label})\n"
        f"URL: {d.url}\n{d.text}"
        for i, d in enumerate(docs)
    ) or "(no matching sources found)"
    past = "\n".join(
        f"{'Person' if h.get('role') == 'user' else 'Assistant'}: {str(h.get('text', ''))[:600]}"
        for h in history[-4:]
    )
    parts = []
    if who:
        parts.append(f"The person says they are {who}. Tailor the answer to them when the sources allow.")
    if level and level != role:
        parts.append(f"The question is about {ROLE_LABELS.get(level, level)} matters. If sources give different rules "
                     f"for different levels or programs, answer for this level and say which level the rule is for.")
    if past:
        parts.append(f"CONVERSATION SO FAR\n{past}")
    parts.append(f"SOURCES\n{src}")
    if conflicts:
        parts.append(conflicts)
    parts.append(f"QUESTION\n{question}")
    return "\n\n".join(parts)


CRISIS_TEXT = ("You don't have to go through this alone. Please call or text 988 (Suicide & Crisis Lifeline) now, "
               "or call 911 if you are in immediate danger. At Belhaven you can reach Counseling Services at "
               "601-965-4128 or Student Care at 601-968-8865.")


def extractive_answer(docs: list[Doc], crisis: bool = False) -> str:
    """Used when no AI provider is configured: return the best official passage, cited."""
    if crisis:
        return CRISIS_TEXT
    if not docs:
        return ("I couldn't find that in the university's public pages. Try rephrasing, or contact the "
                "Office of Admission at 601-968-5940 (admission@belhaven.edu).")
    top = docs[0]
    text = f"**{top.title}**\n{top.text} [1]"
    if len(docs) > 1:
        text += "\n\nRelated: " + "; ".join(f"{d.title} [{i + 2}]" for i, d in enumerate(docs[1:3]))
    return text
