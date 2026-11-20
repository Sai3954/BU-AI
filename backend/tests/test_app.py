"""Run with:  cd backend && python -m pytest -q"""
import json
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test.db")
os.environ["LLM_PROVIDER"] = "none"
os.environ["ADMIN_TOKEN"] = "Zq8-vR3pL_x7Nw2Kc9-Hy4Tm"
os.environ["CHAT_RATE_PER_MINUTE"] = "1000"
os.environ["INDEX_WATCH_SECONDS"] = "0"

import pytest
from fastapi.testclient import TestClient

from app import crawl, main
from app.retrieval import index, is_high_risk

# (question, role, expected seed ids/urls substring that should appear in the top 3)
RETRIEVAL_CASES = [
    ("How do I request CPT?", "international", "faq.php?id=39"),
    ("Can I start working on CPT before my classes begin?", "international", "faq.php?id=79"),
    ("When can I apply for OPT?", "international", "faq.php?id=28|faq.php?id=29"),
    ("Do I need a job offer for OPT?", "international", "faq.php?id=30"),
    ("How many days can I be unemployed on OPT?", "international", "faq.php?id=30"),
    ("Can I travel to India while my OPT is pending?", "international", "faq.php?id=56"),
    ("How do I bring my wife on F2?", "international", "faq.php?id=51"),
    ("I can't attend my residency weekend", "graduate", "faq.php?id=11"),
    ("What TOEFL score do I need?", "international", "grad-international/apply"),
    ("What are the MSITM concentrations?", "graduate", "faq.php?id=20"),
    ("How do I transfer credits?", "", "faq.php?id=46"),
    ("My SEVIS was terminated, what should I do?", "international", "faq.php?id=66"),
    ("What GPA do I need to get in as a freshman?", "prospective", "admission/undergrad"),
    ("Do I have to live on campus?", "undergraduate", "housing"),
    ("What time is dinner served?", "undergraduate", "dining"),
    ("How much is a 40 meal plan?", "", "dining"),
    ("What are the library hours?", "", "library"),
    ("Where can I get tutoring?", "undergraduate", "care"),
    ("How do I request a disability accommodation?", "", "care"),
    ("I forgot my email password", "", "email"),
    ("Who can help me with my resume?", "", "career"),
    ("Is there an online data science master's?", "prospective", "admission/online"),
    ("What doctoral programs do you offer?", "prospective", "doctorate"),
    ("When is homecoming?", "alumni", "university-life/index"),
    ("Where do I find the academic calendar?", "", "academic-calendar"),
    ("How do alumni get transcripts?", "alumni", "alumni"),
    ("Where can I see a doctor near campus?", "undergraduate", "health"),
    ("How do I set up Duo two-factor?", "", "email"),
]


@pytest.fixture(scope="module")
def client():
    if os.path.exists("data/test.db"):
        os.remove("data/test.db")
    with TestClient(main.app) as c:
        yield c


def test_meta(client):
    m = client.get("/api/meta").json()
    assert m["passages"] >= 60 and "International" in m["categories"]


@pytest.mark.parametrize("q,role,expect", RETRIEVAL_CASES)
def test_retrieval_top3(client, q, role, expect):
    urls = [d.url for d in index.search(q, role=role, k=3)]
    assert any(e in u for e in expect.split("|") for u in urls), f"{q} -> {urls}"


def test_off_topic_returns_no_sources(client):
    assert index.search("How do I become an astronaut?") == []


def test_chat_stream_and_logging(client):
    r = client.post("/api/chat", json={"question": "How do I request CPT?", "role": "international"})
    events = [e for e in r.text.split("\n\n") if e.strip()]
    kinds = [e.split("\n")[0].replace("event: ", "") for e in events]
    assert kinds[0] == "sources" and "delta" in kinds and kinds[-1] == "done"
    done = json.loads(events[-1].split("data: ", 1)[1])
    assert client.post("/api/feedback", json={"query_id": done["query_id"], "helpful": True}).json()["ok"]


def test_high_risk_flag(client):
    assert is_high_risk("my SEVIS record was terminated")
    r = client.post("/api/chat", json={"question": "My visa was revoked, can I keep working?"})
    first = json.loads(r.text.split("\n\n")[0].split("data: ", 1)[1])
    assert first["flags"]["high_risk"] is True


def test_admin_requires_token(client):
    assert client.get("/api/admin/summary").status_code == 401
    s = client.get("/api/admin/summary", headers={"X-Admin-Token": "Zq8-vR3pL_x7Nw2Kc9-Hy4Tm"}).json()
    assert s["totals"]["questions"] >= 2
    kinds = s["issue_counts"]
    assert kinds.get("conflict", 0) >= 3 and kinds.get("stale", 0) > 0
    details = " ".join(i["detail"] for i in s["issues"] if i["kind"] == "conflict")
    assert "TOEFL" in details and "onlineadmission@belhaven.edu" in details


def test_crawler_extract_and_chunk():
    html = """<html><head><title>Housing | X</title></head><body><nav>menu</nav><main>
    <h1>Residence Halls</h1><p>All halls are furnished and students bring their own sheets.</p>
    <h2>Deposit</h2><p>The housing deposit is $150 and is paid in BlazeNet.</p><p>Last Updated 2 years ago</p>
    <a href="/university-life/campus/dining/index.html">Dining</a><a href="https://blazenet.belhaven.edu/">BlazeNet</a>
    </main><footer>footer</footer></body></html>"""
    title, text, updated, links = crawl.extract(html, "https://www.belhaven.edu/university-life/campus/housing/index.html")
    assert title == "Residence Halls" and "menu" not in text and updated == "2 years ago"
    assert crawl.allowed(links[0]) and not crawl.allowed(links[1])
    chunks = crawl.chunk_text(text)
    assert any(h == "Deposit" for h, _ in chunks)
    assert crawl.classify("https://www.belhaven.edu/university-life/campus/housing/index.html")[0] == "Campus Life"


def test_generative_path_uses_sources_and_prompt(client, monkeypatch):
    seen = {}

    class Fake:
        name, generative = "fake", True

        def stream(self, system, user):
            seen["system"], seen["user"] = system, user
            yield "Open a ticket "
            yield "with the CPT form [1]."

    monkeypatch.setattr(main, "provider", Fake())
    r = client.post("/api/chat", json={"question": "How do I request CPT?", "role": "international",
                                       "history": [{"role": "user", "text": "hi"}]})
    text = "".join(json.loads(e.split("data: ", 1)[1]).get("text", "")
                   for e in r.text.split("\n\n") if e.startswith("event: delta"))
    assert text == "Open a ticket with the CPT form [1]."
    assert "Answer ONLY from the numbered SOURCES" in seen["system"]
    assert "international (F-1) student" in seen["user"] and "[1]" in seen["user"]


# ---------- round 3: tools, security, answer checks ----------

def test_program_finder(client):
    r = client.get("/api/programs", params={"level": "Graduate", "format": "Online", "q": "data"}).json()
    assert any(p["name"] == "Data Science" for p in r["programs"])
    assert client.get("/api/programs").json()["count"] >= 80
    intl = client.get("/api/programs", params={"q": "cyber"}).json()["programs"]
    assert intl and "Hybrid" in intl[0]["format"]


def test_directory(client):
    r = client.get("/api/directory", params={"q": "password"}).json()
    assert r["offices"][0]["name"] == "IT Help Desk"


def test_scholarship_finder(client):
    r = client.get("/api/scholarships", params={"group": "first_year", "gpa": 3.6, "act": 27}).json()
    names = {a["name"] for a in r["eligible"]}
    assert "President's Scholarship" in names and "Distinguished Merit Scholarship" not in names
    low = client.get("/api/scholarships", params={"group": "first_year", "gpa": 2.8}).json()
    assert "Advantage Scholarship" in {a["name"] for a in low["eligible"]}
    intl = client.get("/api/scholarships", params={"group": "international_hybrid"}).json()
    assert intl["note"] and not intl["eligible"]


def test_onboarding(client):
    assert "international" in client.get("/api/onboarding").json()
    steps = client.get("/api/onboarding/international").json()["steps"]
    assert any("CPT" in s["title"] for s in steps)


def test_chat_uses_structured_data(client):
    urls = [d.url for d in index.search("Do you have an online data science master's?", role="prospective", k=4)]
    assert any("data-science" in u or "program-finder" in u or "admission/online" in u for u in urls)
    titles = [d.title for d in index.search("who do I call about counseling", k=3)]
    assert any("Counsel" in t for t in titles)


def test_pii_is_redacted_before_logging(client):
    from app.db import QueryLog, SessionLocal
    from sqlalchemy import select
    r = client.post("/api/chat", json={"question": "My SEVIS ID is N0012345678 and email ravi@gmail.com, how do I request CPT?"})
    first = json.loads(r.text.split("\n\n")[0].split("data: ", 1)[1])
    assert set(first["flags"]["pii_removed"]) == {"EMAIL", "SEVIS_ID"}
    with SessionLocal() as s:
        last = s.scalars(select(QueryLog).order_by(QueryLog.id.desc())).first()
    assert "N0012345678" not in last.question and "ravi@gmail.com" not in last.question
    assert "[SEVIS_ID]" in last.question


def test_rate_limit(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "CHAT_RATE_PER_MINUTE", 2)
    main.chat_limiter.hits.clear()
    codes = [client.post("/api/chat", json={"question": "library hours"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    main.chat_limiter.hits.clear()


def test_admin_disabled_with_weak_token(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "ADMIN_TOKEN", "change-me")
    assert client.get("/api/admin/summary", headers={"X-Admin-Token": "change-me"}).status_code == 503


def test_guard_flags_unsupported_figures():
    from app import guard
    from app.retrieval import Doc
    d = Doc(1, "u", "Makeup residency", "Academics", ["all"], "The makeup residency fee is USD 300.", "")
    ok = guard.check("The fee is $300 [1].", [d])
    assert ok["unverified"] == [] and ok["cited"]
    bad = guard.check("The fee is $450 and you have 14 days [1][4].", [d])
    assert "$450" in bad["unverified"] and "14" in bad["unverified"]
    assert bad["invalid_citations"] == [4] and "[4]" not in bad["text"]


def test_index_picks_up_new_content(client):
    from app.db import Chunk, SessionLocal
    before = main._index_signature()
    with SessionLocal() as s:
        s.add(Chunk(key="crawl:test", url="https://www.belhaven.edu/test.html", title="Quidditch club",
                    category="Campus Life", audiences="all", text="The quidditch club meets on Fridays.",
                    updated_label="current site", source="crawl"))
        s.commit()
    assert main._index_signature() != before
    rebuild_index_and_search = __import__("app.ingest", fromlist=["rebuild_index"]).rebuild_index
    rebuild_index_and_search()
    assert index.search("quidditch club")[0].title == "Quidditch club"


# ---------- v0.4 fixes ----------

@pytest.mark.parametrize("text,kind,leak", [
    ("my email is priya.s@students.belhaven.edu", "EMAIL", "priya.s@students.belhaven.edu"),
    ("my name is ravi kumar and I need CPT", "NAME", "ravi kumar"),
    ("student id B00123456 can't log in", "STUDENT_ID", "B00123456"),
    ("my id is 0098765", "STUDENT_ID", "0098765"),
    ("reach me on +91 98480 22338", "PHONE", "98480"),
    ("Thanks,\nAnil Reddy", "NAME", "Anil Reddy"),
])
def test_redaction_cases(text, kind, leak):
    from app.redact import redact
    out, kinds = redact(text)
    assert kind in kinds and leak not in out


def test_redaction_keeps_office_contacts_and_fees():
    from app.redact import redact
    for t in ["Email registrar@belhaven.edu or call 601-968-5922", "Tuition is $30,700", "TOEFL code 1055",
              "I am an international student", "call 800-960-5940"]:
        assert redact(t) == (t, [])


def test_admin_token_strength():
    assert main.token_problem("Zq8-vR3pL_x7Nw2Kc9-Hy4Tm") is None
    for weak in ["change-me", "Belhaven2026!Belhaven2026!", "aaaaaaaaaaaaaaaaaaaaaaaa", "Password123456789012!",
                 "admintokenadmintoken12", "abcdefghijklmnopqrstuvwxyz"]:
        assert main.token_problem(weak), weak


def test_daily_ai_limit_survives_restart(client, monkeypatch):
    from app.config import settings
    from app.db import QueryLog, SessionLocal
    with SessionLocal() as s:
        for _ in range(3):
            s.add(QueryLog(question="q", ai=True))
        s.commit()
    monkeypatch.setattr(settings, "DAILY_AI_LIMIT", main.ai_calls_today())
    main._ai_inflight["n"] = 0  # simulate a fresh process: in-memory state gone
    assert main.ai_budget_ok() is False
    monkeypatch.setattr(settings, "DAILY_AI_LIMIT", main.ai_calls_today() + 1)
    assert main.ai_budget_ok() is True
    main._ai_inflight["n"] = 0


def test_guard_checks_figures_against_the_cited_source():
    from app import guard
    from app.retrieval import Doc
    dining = Doc(1, "u", "Dining", "x", ["all"], "40 meals cost USD 320.", "")
    housing = Doc(2, "u", "Housing", "x", ["all"], "The housing deposit is USD 150.", "")
    r = guard.check("A 40-meal plan costs $150 [1]. The deposit is $150 [2].", [dining, housing])
    assert r["misattributed"] == ["$150"] and r["unverified"] == []


def test_crawler_reads_pdf_calendar(client):
    import io
    from reportlab.pdfgen import canvas
    from app import crawl
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setTitle("Traditional Academic Calendar 2026-2027")
    y = 800
    for line in ["Fall 2026", "Classes begin August 19, 2026", "Last day to add a class August 26, 2026",
                 "Thanksgiving holiday November 25-27, 2026", "Final exams December 7-10, 2026",
                 "Spring 2027 classes begin January 11, 2027", "Spring break March 15-19, 2027"]:
        c.drawString(72, y, line); y -= 20
    c.save()
    url = "https://www.belhaven.edu/pdfs/academics/traditional-academic-calendar.pdf"
    title, text = crawl.extract_pdf(buf.getvalue(), url)
    assert "Calendar" in title and "Thanksgiving holiday" in text
    assert crawl.allowed(url) and crawl.classify(url)[0] == "Academics"
    crawl.store_page(url, title, text, "PDF document", 200)
    crawl.rebuild_index()
    hit = index.search("When is Thanksgiving break and final exams?", k=3)
    assert hit and hit[0].url == url


def test_redaction_placeholders_do_not_steer_search(client):
    r = client.post("/api/chat", json={"question": "What time is dinner? my email is a.b@students.belhaven.edu"})
    first = json.loads(r.text.split("\n\n")[0].split("data: ", 1)[1])
    assert "dining" in first["sources"][0]["url"]


# ---------- v0.4.1: adversarial review findings ----------

@pytest.mark.parametrize("text,leak", [
    ("email me at john.smith@belhaven.edu", "john.smith@belhaven.edu"),          # personal staff/student address
    ("My name is RAVI KUMAR", "RAVI KUMAR"),
    ("I am ravi kumar and I need CPT", "ravi kumar"),
    ("I AM RAVI KUMAR", "RAVI KUMAR"),
    ("Thanks, anil reddy", "anil reddy"),
    ("I live at 245 Oak Grove Rd, Apt 12, Ridgeland, MS 39157", "245 Oak Grove"),
    ("send it to 3101 Old Canton Road Apt 5B", "3101 Old Canton"),
    ("my address is 12 MG Road, Hyderabad", "MG Road"),
    ("call me on 601-555-0147", "601-555-0147"),
])
def test_redaction_adversarial(text, leak):
    from app.redact import redact
    out, kinds = redact(text)
    assert leak not in out and kinds, (text, out)


@pytest.mark.parametrize("text", [
    "Email registrar@belhaven.edu or call 601-968-5922", "The campus is at 1500 Peachtree Street",
    "i am going home for winter break", "I am an international student", "i am confused about opt",
    "I am a junior nursing major", "Thanks, Financial Aid", "Tuition is $30,700",
])
def test_redaction_no_false_positives(text):
    from app.redact import redact
    assert redact(text) == (text, [])


def test_redaction_allowlist_follows_crawled_content():
    from app.redact import redact, refresh_allowlist
    assert "[EMAIL]" in redact("write to newoffice@belhaven.edu")[0]
    refresh_allowlist(["Contact the New Office at newoffice@belhaven.edu or 601-968-1111."])
    assert redact("write to newoffice@belhaven.edu")[0] == "write to newoffice@belhaven.edu"
    from app.ingest import rebuild_index
    rebuild_index()  # restore the real allowlist




def _docs():
    from app.retrieval import Doc
    return [
        Doc(1, "u1", "Dining hours and meal plans", "x", ["all"],
            "Meal blocks: 10 meals USD 85, 40 meals USD 320, 80 meals USD 620, 120 meals USD 900.", ""),
        Doc(2, "u2", "Minimum credit hours per term", "x", ["all"],
            "International graduate (F-1) students must take at least 6 credit hours per term.", ""),
        Doc(3, "u3", "Undergraduate admission", "x", ["all"],
            "Admission is test-optional, but you need a high school GPA of at least 2.75 to be eligible.", ""),
    ]


def test_guard_wrong_fee_from_same_cited_page():
    from app import guard
    r = guard.check("A 40-meal block costs $620 [1].", _docs())
    assert r["misattributed"] == ["$620"]
    assert guard.check("A 40-meal block costs $320 [1].", _docs())["misattributed"] == []


def test_guard_single_digit_credit_hours():
    from app import guard
    assert guard.check("F-1 students must take at least 3 credit hours per term [2].", _docs())["unverified"] == ["3"]
    assert guard.issue_count(guard.check("F-1 students must take at least 6 credit hours per term [2].", _docs())) == 0


def test_guard_unsupported_guarantee_and_uncited_claims():
    from app import guard
    assert guard.check("With a 2.75 GPA you are guaranteed admission [3].", _docs())["unsupported_claims"]
    assert guard.check("With a 2.75 GPA you will be admitted [3].", _docs())["unsupported_claims"]
    assert guard.check("You must take at least 6 credit hours each term.", _docs())["uncited"]
    assert guard.issue_count(guard.check("You need a GPA of at least 2.75 to be eligible [3].", _docs())) == 0


def test_guard_ai_review_with_fake_provider():
    from app import guard

    class Judge:
        def stream(self, system, user):
            assert "SOURCES" in user and "ANSWER" in user
            yield '{"unsupported": ["You will be admitted."]}'
    assert guard.ai_review(Judge(), "You will be admitted.", _docs()) == ["You will be admitted."]

    class Broken:
        def stream(self, system, user):
            yield "not json"
    assert guard.ai_review(Broken(), "x", _docs()) == []


class _SlowAI:
    name, generative = "fake", True

    def stream(self, system, user):
        for w in ["Open ", "a ", "ticket ", "[1]."]:
            yield w


def test_interrupted_stream_releases_slot_and_counts_usage(client, monkeypatch):
    from app.db import QueryLog, SessionLocal
    from app.config import settings
    from sqlalchemy import select
    monkeypatch.setattr(main, "provider", _SlowAI())
    monkeypatch.setattr(settings, "DAILY_AI_LIMIT", 10_000)
    main.chat_limiter.hits.clear()
    before = main.ai_calls_today()
    with client.stream("POST", "/api/chat", json={"question": "How do I request CPT?"}) as r:
        for _ in r.iter_lines():
            break  # student closes the page after the first event
    assert all(v == 0 for v in main.concurrency.active.values())
    assert main._ai_inflight["n"] == 0
    assert main.ai_calls_today() == before + 1  # the AI call still counts toward the daily limit
    with SessionLocal() as s:
        last = s.scalars(select(QueryLog).order_by(QueryLog.id.desc())).first()
    assert last.ai is True


def test_concurrent_requests_cannot_exceed_daily_limit(monkeypatch):
    import threading
    from app.config import settings
    main._ai_inflight["n"] = 0
    monkeypatch.setattr(settings, "DAILY_AI_LIMIT", main.ai_calls_today() + 3)
    results = []
    threads = [threading.Thread(target=lambda: results.append(main.ai_budget_ok())) for _ in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(True) == 3
    main._ai_inflight["n"] = 0


def test_per_visitor_concurrency_limit(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "MAX_CONCURRENT_PER_IP", 1)
    main.chat_limiter.hits.clear()
    assert main.concurrency.acquire("testclient")
    try:
        assert client.post("/api/chat", json={"question": "library hours"}).status_code == 429
    finally:
        main.concurrency.release("testclient")


def test_crawler_blocks_offsite_redirects():
    import httpx
    from app import crawl

    def handler(request):
        if request.url.path == "/go-away":
            return httpx.Response(302, headers={"location": "https://evil.example.com/steal"})
        if request.url.path == "/moved":
            return httpx.Response(301, headers={"location": "/new-home.html"})
        return httpx.Response(200, text="<html><body><p>ok</p></body></html>", headers={"content-type": "text/html"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False) as c:
        r, final = crawl.fetch(c, "https://www.belhaven.edu/go-away")
        assert r is None and "evil.example.com" in final
        r, final = crawl.fetch(c, "https://www.belhaven.edu/moved")
        assert r.status_code == 200 and final == "https://www.belhaven.edu/new-home.html"


# ---------- v0.4.2: second adversarial review ----------

def test_guard_flags_guarantee_the_source_denies():
    from app import guard
    from app.retrieval import Doc
    d = [Doc(1, "u", "CPT", "x", [], "The goal is 48 business hours, but approval is not guaranteed.", "")]
    assert guard.check("Your CPT approval is guaranteed within 48 hours [1].", d)["unsupported_claims"]
    assert not guard.check("CPT approval is not guaranteed [1].", d)["unsupported_claims"]


def test_guard_flags_short_uncited_statements():
    from app import guard
    assert guard.check("The fee is $300.", _docs())["uncited"]
    assert guard.check("It takes 48 hours.", _docs())["uncited"]


def test_redaction_four_word_names():
    from app.redact import redact
    out, kinds = redact("My name is Maria Jose Garcia Lopez and I need help")
    assert "Lopez" not in out and "Maria" not in out and "NAME" in kinds


def test_student_and_outside_emails_never_allowlisted_from_crawled_pages():
    from app.ingest import rebuild_index
    from app.redact import redact, refresh_allowlist
    refresh_allowlist(["Congrats to jane.doe@students.belhaven.edu and coach@gmail.com; contact news@belhaven.edu"])
    out, _ = redact("email jane.doe@students.belhaven.edu, coach@gmail.com or news@belhaven.edu")
    assert "jane.doe" not in out and "coach@gmail.com" not in out and "news@belhaven.edu" in out
    rebuild_index()


def test_unauthorized_work_triggers_dso_banner():
    from app.retrieval import is_high_risk
    assert is_high_risk("Am I still eligible for OPT if I worked off campus without CPT?")
    assert is_high_risk("Am I still in status?")
    assert not is_high_risk("When can I apply for OPT?")
    assert not is_high_risk("How do I request CPT?")


def test_page_age_note_is_not_flagged():
    from app.guard import check
    from app.retrieval import Doc
    d = Doc(1, "https://igsupport.belhaven.edu/kb/faq.php?id=39", "How to request CPT", "International", ["all"],
            "Download the CPT packet and open a ticket.", "~2 years ago")
    r = check("This page was last updated about 2 years ago, so confirm with the DSO [1].", [d])
    assert "2" not in r["unverified"]


from app import guard  # noqa: E402


def _cost_docs():
    from app.retrieval import Doc
    return [
        Doc(1, "u1", "Undergraduate tuition", "x", ["all"],
            "Tuition USD 15,350 per semester (USD 30,700 per year). Proof of funds of at least USD 27,275.", ""),
        Doc(2, "u2", "IT Help Desk", "x", ["all"], "IT Help Desk: 601-968-8777, helpdesk@belhaven.edu.", ""),
        Doc(3, "u3", "Admission", "x", ["all"], "Office of Admission: 601-968-5940.", ""),
    ]


def test_guard_thousands_and_phones_not_false_flags():
    r = guard.check("Tuition is USD 30,700 per year, or USD 15,350 per semester [1]. Show at least USD 27,275 [1].",
                    _cost_docs())
    assert not r["misattributed"] and not r["unverified"]
    r = guard.check("Call the IT Help Desk at 601-968-8777 [2].", _cost_docs())
    assert not r["misattributed"] and not r["unverified"]


def test_guard_wrong_phone_still_caught():
    r = guard.check("Call the IT Help Desk at 601-968-5940 [2].", _cost_docs())
    assert "601-968-5940" in r["misattributed"]
    r = guard.check("Call the IT Help Desk at 601-968-1111 [2].", _cost_docs())
    assert "601-968-1111" in r["unverified"]
    r = guard.check("Tuition is USD 31,700 per year [1].", _cost_docs())
    assert r["unverified"]


def test_guard_line_citation_covers_earlier_sentences():
    r = guard.check("- Download the packet. Pay USD 15,350 per semester. [1]", _cost_docs())
    assert not r["uncited"] and not r["misattributed"]
    r = guard.check("Pay USD 15,350 per semester.\n\nSee the page [1].", _cost_docs())
    assert r["uncited"]


def test_guard_small_thousands_form_ids_and_page_age():
    r = guard.check("Visiting adds USD 1,000 to the package [1]. File Form I-765 [1]. "
                    "The page was last updated about 2 years ago [1].", _cost_docs())
    assert "1,000" in r["unverified"] and "000" not in r["unverified"]
    assert "765" not in r["misattributed"] + r["unverified"]
    assert "2" not in r["misattributed"] + r["unverified"]
    assert guard.check("I couldn't find that. Call 601-968-5940.", [])["unverified"] == []


def test_guard_ignores_numbers_from_the_question():
    r = guard.check("With a 3.6 GPA and a 27 ACT, see the scholarship page [1].", _cost_docs(),
                    "I have a 3.6 GPA and 27 ACT. What scholarship could I get?")
    assert not r["unverified"] and not r["misattributed"]


def test_partial_gap_still_counts_as_answered():
    docs = _cost_docs()
    assert main.is_answered("Dinner is 4:45-7 p.m. on weekdays [1]. I couldn't find a Saturday time.", docs)
    assert not main.is_answered("I couldn't find that in the university's public pages.", docs)
    assert not main.is_answered("Anything", [])


def test_guard_negated_promise_wide_subject_and_crisis_fallback():
    from app.prompts import extractive_answer
    from app.retrieval import Doc
    docs = [Doc(1, "u1", "Online tuition", "x", ["all"],
                "Military rates: active duty USD 250 per credit (undergraduate) and USD 375 (master's).", ""),
            Doc(2, "u2", "Dining", "x", ["all"], "Meal blocks: 10 meals USD 85, 40 meals USD 320, 80 meals USD 620.", "")]
    assert not guard.check("- Active duty: USD 250 for undergraduate and USD 375 for master's [1]", docs)["misattributed"]
    assert "620" in guard.check("A 40-meal block costs USD 620 [2].", docs)["misattributed"]
    assert not guard.check("Meeting the minimums doesn't guarantee an award [1].", docs)["unsupported_claims"]
    assert guard.check("You are guaranteed an award [1].", docs)["unsupported_claims"]
    assert not guard.check("I can't say whether you can keep working.", docs)["uncited"]
    assert "988" in extractive_answer([], crisis=True)


def test_role_does_not_bury_the_topic():
    from app.retrieval import index
    for role in ("", "graduate", "doctoral", "undergraduate"):
        titles = [d.title for d in index.search("When can I apply for OPT?", role=role)[:4]]
        assert "How to apply for OPT" in titles, (role, titles)


def test_guard_far_negation_is_not_a_promise():
    assert not guard.check("They don't say that meeting those numbers means you will receive it [1].",
                           _cost_docs())["unsupported_claims"]


def test_guard_restating_a_window_from_the_sources():
    from app.retrieval import Doc
    docs = [Doc(1, "u1", "How to apply for OPT", "x", ["all"],
                "Apply up to 90 days before and up to 60 days after program completion. USCIS must receive it "
                "before the program end date.", "")]
    r = guard.check("You can apply up to 90 days before and up to 60 days after [1]. USCIS must receive it before "
                    "the end date [1]. This conflicts slightly with the 60-days-after window stated in the same "
                    "sources, so please confirm with the DSO.", docs)
    assert not r["misattributed"] and not r["unverified"] and not r["uncited"]


def test_guard_cited_lead_in_covers_the_list_below():
    from app.retrieval import Doc
    docs = [Doc(1, "u1", "Library", "x", ["all"], "Hours: Monday-Friday 7:30 a.m.-10 p.m., Saturday 1:30-10 p.m.", "")]
    r = guard.check("Regular hours are: [1]\n- Monday-Friday: 7:30 a.m.-10 p.m.\n- Saturday: 1:30-10 p.m.", docs)
    assert not r["uncited"] and not r["unverified"]


def test_crawl_export_roundtrip_and_tagging(tmp_path):
    from app import crawl
    from app.db import Chunk, SessionLocal
    from sqlalchemy import select
    assert crawl.classify("https://www.belhaven.edu/academics/business/online/doctor-of-business-administration.html")[1] == ["doctoral"]
    assert crawl.classify("https://www.belhaven.edu/campus-safety/index.html")[0] == "Campus Safety"
    assert crawl.classify("https://www.belhaven.edu/student-handbook.pdf")[0] == "Policies & Registrar"
    url = "https://www.belhaven.edu/test-roundtrip/index.html"
    crawl.store_page(url, "Roundtrip Page", "#Hours\nOpen Monday to Friday, 8 a.m. to 5 p.m., for all students. " * 3,
                     "current site", 200)
    out = tmp_path / "pages.json.gz"
    assert crawl.export_pages(str(out)) >= 1
    import gzip, json
    pages = json.load(gzip.open(out, "rt"))["pages"]
    assert any(p["url"] == url and "Open Monday" in p["text"] for p in pages)
    with SessionLocal() as s:  # loading is skipped while crawled content already exists
        assert s.scalar(select(Chunk.id).where(Chunk.source == "crawl").limit(1)) is not None
    assert crawl.load_export(str(out)) == 0
    assert crawl.load_export(str(tmp_path / "missing.json.gz")) == 0
