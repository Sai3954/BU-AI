"""/api/eval/run: off unless EVAL_MODE=true and a strong EVAL_TOKEN is set; the token must come in X-Eval-Token."""
from fastapi.testclient import TestClient

from app import main
from app.config import settings

GOOD = "test-only-token-9f3K2pQ7vX1mZ8rT4wY6"


def _client(mode: bool, token: str, monkeypatch):
    monkeypatch.setattr(settings, "EVAL_MODE", mode)
    monkeypatch.setattr(settings, "EVAL_TOKEN", token)
    monkeypatch.setattr(main, "eval_limiter", main.RateLimiter())
    return TestClient(main.app)


def test_disabled_by_default_even_with_a_token(monkeypatch):
    with _client(False, GOOD, monkeypatch) as c:
        assert c.get("/api/eval/run?part=1", headers={"X-Eval-Token": GOOD}).status_code == 404


def test_disabled_when_no_strong_token_is_configured(monkeypatch):
    for weak in ("", "short-token"):
        with _client(True, weak, monkeypatch) as c:
            assert c.get("/api/eval/run?part=1", headers={"X-Eval-Token": weak}).status_code == 404


def test_rejects_missing_or_wrong_token(monkeypatch):
    with _client(True, GOOD, monkeypatch) as c:
        assert c.get("/api/eval/run?part=1").status_code == 401
        assert c.get("/api/eval/run?part=1", headers={"X-Eval-Token": GOOD[:-1] + "x"}).status_code == 401
        # a token in the address is never accepted
        assert c.get(f"/api/eval/run?part=1&x_eval_token={GOOD}").status_code == 401


def test_accepts_the_header_and_keeps_the_response_format(monkeypatch):
    monkeypatch.setattr(settings, "CHAT_RATE_PER_MINUTE", 1000)
    with _client(True, GOOD, monkeypatch) as c:
        r = c.get("/api/eval/run?part=1&size=2", headers={"X-Eval-Token": GOOD})
        assert r.status_code == 200
        j = r.json()
        assert j["part"] == 1 and j["of"] == 50 and len(j["results"]) == 2
        row = j["results"][0]
        for k in ("id", "q", "role", "seconds", "answer", "sources", "source_titles", "evidence", "answer_type",
                  "answered", "handoff", "followups", "checker"):
            assert k in row


def test_repeated_attempts_are_rate_limited(monkeypatch):
    with _client(True, GOOD, monkeypatch) as c:
        codes = [c.get("/api/eval/run?part=1", headers={"X-Eval-Token": "wrong"}).status_code for _ in range(22)]
        assert codes[0] == 401 and codes[-1] == 429
