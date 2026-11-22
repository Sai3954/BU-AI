from app.conflicts import find_conflicts
from app.retrieval import Doc, detect_level


def d(n, text, url=None, title="Page"):
    return Doc(n, url or f"https://www.belhaven.edu/p{n}", title, "x", ["all"], text, "current site")


def test_detect_level():
    assert detect_level("When is my DBA residency?") == "doctoral"
    assert detect_level("MBA tuition per credit hour") == "graduate"
    assert detect_level("Is there an undergraduate honors college?") == "undergraduate"
    assert detect_level("When is graduation?") == ""
    assert detect_level("When is graduation?", "doctoral") == "doctoral"
    assert detect_level("library hours", "international") == ""


def test_conflict_found_between_two_pages():
    c = find_conflicts([d(1, "Tuition is $650 per credit hour."), d(2, "Tuition is $695 per credit hour.")])
    assert c and c[0]["fact"] == "Tuition per credit hour"


def test_no_conflict_same_value_or_one_table_or_catalog_years():
    assert not find_conflicts([d(1, "$650 per credit hour"), d(2, "Cost: $650 per credit hour")])
    assert not find_conflicts([d(1, "MBA $650 per credit hour; DBA $795 per credit hour")])
    assert not find_conflicts([
        d(1, "$600 per credit hour", "https://www.belhaven.edu/catalog/2024-2025/fees"),
        d(2, "$650 per credit hour", "https://www.belhaven.edu/catalog/2025-2026/fees")])



def test_trace_endpoint_shows_working():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/trace", json={"question": "How do I request CPT? my email is a@b.com", "role": "international"})
        assert r.status_code == 200
        j = r.json()
        assert j["final"] and j["final"][0]["url"].startswith("http")
        assert "EMAIL" in j["pii_removed"] or "email" in str(j["pii_removed"]).lower()
        assert "a@b.com" not in j["prompt"]["user"]
        assert j["keyword"] and j["timings"]["search_ms"] >= 0


def test_feedback_reason_saved_and_summarized():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db import SessionLocal, QueryLog
    with TestClient(app) as c:
        with SessionLocal() as s:
            r = QueryLog(question="test q"); s.add(r); s.commit(); qid = r.id
        assert c.post("/api/feedback", json={"query_id": qid, "helpful": False, "reason": "missing"}).status_code == 200
        assert c.post("/api/feedback", json={"query_id": qid, "helpful": False, "reason": "rude"}).status_code == 422
        with SessionLocal() as s:
            assert s.get(QueryLog, qid).feedback_reason == "missing"


def test_admin_summary_counts_likes_and_dislikes():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import settings
    from app.db import SessionLocal, QueryLog
    with TestClient(app) as c:
        with SessionLocal() as s:
            a = QueryLog(question="liked q", helpful=True); b = QueryLog(question="disliked q", helpful=False, feedback_reason="wrong")
            s.add_all([a, b]); s.commit()
        old = settings.ADMIN_TOKEN
        settings.ADMIN_TOKEN = "Qv7-Lr2xKp9-Zw4mJt8-Hc6"
        try:
            r = c.get("/api/admin/summary", headers={"X-Admin-Token": settings.ADMIN_TOKEN})
        finally:
            settings.ADMIN_TOKEN = old
        assert r.status_code == 200, r.text
        t = r.json()["totals"]
        assert t["likes"] >= 1 and t["dislikes"] >= 1 and t["not_helpful_reasons"].get("wrong", 0) >= 1
        assert any(d["question"] == "disliked q" for d in r.json()["disliked"])


def test_question_votes_counts_same_question_only():
    from app.main import question_votes
    from app.db import SessionLocal, QueryLog
    with SessionLocal() as s:
        s.add_all([QueryLog(question="How do I request OPT?", helpful=True),
                   QueryLog(question="how do i request  opt", helpful=True),
                   QueryLog(question="How do I request OPT?", helpful=False),
                   QueryLog(question="How do I request OPT extension?", helpful=True)])
        s.commit()
    v = question_votes("How do I request OPT?")
    assert v["likes"] >= 2 and v["dislikes"] >= 1
    assert question_votes("Something nobody asked?") == {"likes": 0, "dislikes": 0}


def test_handoff_routing_and_logging():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.handoff import suggest_office
    from app.db import SessionLocal, QueryLog
    assert suggest_office("How do I apply for CPT?", "international")["name"].startswith("DSO")
    assert suggest_office("I forgot my password", "")["name"] == "IT Help Desk"
    assert suggest_office("When is my tuition due?", "online")["name"] == "Online & Graduate Student Services"
    assert suggest_office("Tell me something nice", "") is None
    with TestClient(app) as c:
        assert any(o["name"] == "Registrar" for o in c.get("/api/offices").json()["offices"])
        with SessionLocal() as s:
            r = QueryLog(question="hand me off"); s.add(r); s.commit(); qid = r.id
        assert c.post("/api/handoff", json={"query_id": qid, "office": "Registrar"}).status_code == 200
        assert c.post("/api/handoff", json={"query_id": qid, "office": "Hackers Inc"}).status_code == 422
        with SessionLocal() as s:
            assert s.get(QueryLog, qid).handoff_office == "Registrar"


def test_trim_unfinished_answer():
    from app.main import trim_unfinished as t
    cut = t("Steps\n1. Do this [1].\n2. Then that [2].\n**Key rules**\n- The job must")
    assert "The job must" not in cut and "Key rules" not in cut and cut.startswith("Steps\n1. Do this [1].\n2. Then that [2].")
    assert t("All complete [1].") == "All complete [1]."
    assert t("Done [1]. And this is cut off mid").startswith("Done [1].")


def test_crisis_lines_are_not_flagged():
    from app.guard import check
    docs = [d(1, "Students may visit the library for study help.")]
    ans = ("I'm sorry you're feeling overwhelmed. Ask your advisor about study help [1]. "
           "If the stress ever feels like too much, contact Student Care at 601-968-8865. "
           "You can also call or text 988 (Suicide & Crisis Lifeline) any time, or 911 in an emergency.")
    r = check(ans, docs)
    assert r["unverified"] == [] and r["misattributed"] == [] and r["uncited"] == []
    # an ordinary made-up number is still caught
    assert "601-555-0100" in check("Call the office at 601-555-0100 [1].", docs)["unverified"]
