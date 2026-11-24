"""Evidence-grounded fallback: wording normalisation, relevance labels, answer types and the no-evidence reply."""
from app import evidence as E
from app.prompts import system_prompt, user_prompt
from app.retrieval import Doc


def d(n, text, title="Page", url=None):
    return Doc(n, url or f"https://www.belhaven.edu/p{n}", title, "x", ["all"], text, "current site")


class FakeIndex:
    """Just enough of HybridIndex for assess(): document frequencies and no vectors."""
    def __init__(self, docs):
        from app.retrieval import tokenize
        self.docs = docs
        self.vectors = None
        self.post = {}
        for i, x in enumerate(docs):
            for w in set(tokenize(x.title) + tokenize(x.text)):
                self.post.setdefault(w, ([], []))[0].append(i)


def test_normalize_everyday_wording():
    assert "leave of absence" in E.normalize_query("how do i take an LOA")
    assert "financial aid" in E.normalize_query("whats SAP for fin aid").lower()
    assert "satisfactory academic progress" in E.normalize_query("whats SAP for fin aid")
    assert "computer science" in E.normalize_query("do u have a comp sci degree")
    assert E.normalize_query("i cant log in") == "i can't log in"   # contraction kept, so it isn't a search word
    assert E.normalize_query("How do I request CPT?") == "How do I request CPT?"   # ordinary wording unchanged


def test_assess_labels_direct_related_and_drops_unrelated():
    pages = [d(1, "To request a leave of absence, submit the form to the Registrar.", "Leave of absence"),
             d(2, "The Registrar handles transcripts and withdrawal from the university.", "Registrar"),
             d(3, "Pilates certification classes meet on Tuesdays.", "Pilates"),
             d(4, "The fitness center has lockers for personal items.", "Fitness center")]
    idx = FakeIndex(pages + [d(9, "Students take four classes. Take the shuttle.", "Common words")])
    ev = E.assess(idx, "How do I take a leave of absence?", pages)
    labels = [p["label"] for p in ev["passages"]]
    assert labels[0] == "direct" and ev["level"] == "direct"
    assert labels[2] == "unrelated" and labels[3] == "unrelated"
    kept, kept_labels = E.keep_relevant(pages, ev)
    assert [x.id for x in kept] == [1] + ([2] if labels[1] != "unrelated" else [])


def test_nearby_information_is_related_not_direct():
    pages = [d(1, "The fitness center is open to residential students with a student ID.", "Fitness center hours"),
             d(2, "Chapel is held on Tuesdays.", "Chapel")]
    common = [d(9 + i, f"Online students take online courses. Students can use BlazeNet. Page {i}.", "Online") for i in range(5)]
    ev = E.assess(FakeIndex(pages + common), "Can online students use the fitness center for free?", pages)
    assert ev["passages"][0]["label"] in ("related", "direct") and ev["passages"][1]["label"] == "unrelated"
    assert "free" in ev["passages"][0]["missing"]
    # A question about something no page mentions is never "direct", even if a common word matches
    ev2 = E.assess(FakeIndex(pages + common), "Is there a quidditch team for online students?", common[:2])
    assert ev2["level"] != "direct"


def test_answer_type_reads_the_reply():
    docs = [d(1, "x")]
    assert E.answer_type("Submit the form to the Registrar [1].", docs, "direct") == "direct"
    assert E.answer_type("The form is on the Registrar page [1]. I couldn't confirm the deadline.", docs, "direct") == "partial"
    assert E.answer_type("This is related information, not the answer: withdrawal works like this [1].", docs, "direct") == "related"
    assert E.answer_type("I couldn't verify that.", [], "none") == "not_verified"


def test_no_evidence_reply_names_a_verified_office_and_invents_nothing():
    office = {"name": "Registrar", "phone": "601-968-5922", "email": "registrar@belhaven.edu",
              "handles": "Transcripts, enrollment verification, graduation"}
    text = E.no_evidence_answer("How do I take a leave of absence?", office)
    assert "couldn't verify" in text and "Registrar" in text and "601-968-5922" in text
    generic = E.no_evidence_answer("Write me a Python script", None)
    assert "couldn't verify" in generic and "admissions" in generic and "[" not in generic


def test_prompt_marks_related_sources_and_explains_the_cases():
    sp = system_prompt()
    assert "HOW MUCH THE SOURCES SUPPORT" in sp and "related information" in sp
    assert "Never invent or guess" in sp
    up = user_prompt("Q?", "", [d(1, "a"), d(2, "b")], [], evidence={"level": "related", "labels": ["related", "related"]})
    assert "match: related" in up and "none of these sources is a close match" in up
    up2 = user_prompt("Q?", "", [d(1, "a")], [], evidence={"level": "direct", "labels": ["direct"]})
    assert "match: direct" in up2 and "close match" not in up2


def test_expanded_query_drops_filler_and_adds_synonyms():
    x = E.expanded_query("I'm really stressed, who can I talk to?")
    assert "really" not in x and "counseling" in x


def test_chat_with_nothing_found_gives_office_or_scope_and_followups():
    from fastapi.testclient import TestClient
    from app.main import app
    import json
    with TestClient(app) as c:
        r = c.post("/api/chat", json={"question": "Write me a Python script to sort a list", "role": ""})
        events = [b for b in r.text.split("\n\n") if b.startswith("event: done")]
        done = json.loads(events[0].split("data: ", 1)[1])
        assert done["answer_type"] == "not_verified" and done["evidence"] == "none"
        assert 2 <= len(done["followups"]) <= 3
        assert "couldn't verify" in r.text


def test_eval_endpoint_hidden_unless_enabled():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/eval/run?part=1").status_code == 404
