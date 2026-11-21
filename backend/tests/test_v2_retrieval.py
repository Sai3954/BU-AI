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
