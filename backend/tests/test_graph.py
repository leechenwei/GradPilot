import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app import quota
from app.graph import APPROVAL_THRESHOLD, MAX_REVISIONS, run
from app.main import app

POSTING = (
    "Junior Backend Engineer\nWe need Python, FastAPI and SQL. Docker is a plus. "
    "Small team, ships weekly, values ownership."
)
SESSION = "11111111-2222-4333-8444-555555555555"

CV = (
    "Chen Wei, CS graduate. Built a Python REST API for a campus club. "
    "Coursework in SQL and data structures. Comfortable with git."
)


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("GRADPILOT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GRADPILOT_ALLOW_MOCK", "1")
    quota.reset()


def events():
    return list(run(POSTING, CV))


def test_graph_visits_every_agent_and_finishes():
    seen = [e["agent"] for e in events() if e["type"] == "result"]
    assert seen[0] == "scout"
    assert seen[1] == "matcher"
    assert seen[-1] == "interviewer"
    assert set(seen) == {"scout", "matcher", "writer", "critic", "interviewer"}


def test_critic_rejects_the_first_draft_then_approves_the_revision():
    scores = [
        e["data"]["score"]
        for e in events()
        if e["type"] == "result" and e.get("agent") == "critic"
    ]
    assert len(scores) >= 2, "the revision loop never ran"
    assert scores[0] < APPROVAL_THRESHOLD
    assert scores[-1] >= APPROVAL_THRESHOLD


def test_revision_loop_is_bounded():
    writes = [e for e in events() if e["type"] == "result" and e["agent"] == "writer"]
    assert len(writes) <= MAX_REVISIONS + 1


def test_final_result_is_approved_and_complete():
    done = events()[-1]
    assert done["type"] == "done"
    assert done["result"]["approved"] is True
    assert done["result"]["draft"]["bullets"]
    assert done["result"]["interviewer"]["questions"]


def test_run_endpoint_streams_sse_and_spends_quota():
    client = TestClient(app)
    before = client.get("/api/quota", headers={"X-Session-Id": SESSION}).json()["remaining"]
    response = client.post(
        "/api/run", json={"posting": POSTING, "cv": CV}, headers={"X-Session-Id": SESSION}
    )
    assert response.status_code == 200
    payloads = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert payloads[-1]["type"] == "done"
    after = client.get("/api/quota", headers={"X-Session-Id": SESSION}).json()["remaining"]
    assert after == before - 1


def test_forged_session_headers_still_hit_the_ip_backstop(monkeypatch):
    monkeypatch.setattr(quota, "IP_RUNS_PER_DAY", 3)
    client = TestClient(app)
    body = {"posting": POSTING, "cv": CV}
    codes = [
        client.post("/api/run", json=body, headers={"X-Session-Id": str(uuid.uuid4())}).status_code
        for _ in range(4)
    ]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429, "a fresh session id per request bypassed the cap"


def test_junk_session_headers_share_one_bucket_and_do_not_grow_the_map():
    client = TestClient(app)
    body = {"posting": POSTING, "cv": CV}
    for i in range(quota.FREE_RUNS + 1):
        client.post("/api/run", json=body, headers={"X-Session-Id": f"junk-{i}"})
    assert len(quota._used) <= 4, "attacker-supplied ids each got their own entry"


def test_quota_blocks_after_the_free_runs():
    client = TestClient(app)
    body = {"posting": POSTING, "cv": CV}
    sid = str(uuid.uuid4())
    for _ in range(quota.FREE_RUNS):
        assert client.post("/api/run", json=body, headers={"X-Session-Id": sid}).status_code == 200
    assert client.post("/api/run", json=body, headers={"X-Session-Id": sid}).status_code == 429


def test_short_input_is_rejected():
    client = TestClient(app)
    assert TestClient(app).post("/api/run", json={"posting": "hi", "cv": CV}).status_code == 422
    assert client.get("/api/health").json()["provider"] == "mock"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0.72, 0.72), ("0.72", 0.72), (72, 0.72), ("72%", 0.72), ("good", 0.0), (None, 0.0)],
)
def test_scores_are_normalised_however_the_model_writes_them(raw, expected):
    from app.graph import _score

    assert _score({"score": raw}) == pytest.approx(expected)


def test_the_best_draft_wins_not_the_last_one(monkeypatch):
    """A third pass can score worse than the second. The user gets the best one."""
    from app import graph

    scripted = iter([("weak", 0.3), ("strong", 0.7), ("worse", 0.4)])

    def fake(agent, system, user, creds=None):
        if agent == "writer":
            fake.current = next(scripted)
            return {"bullets": [fake.current[0]], "cover_letter": fake.current[0]}
        if agent == "critic":
            return {"score": fake.current[1], "notes": ["n"]}
        return {"requirements": [], "gaps": [], "questions": []}

    monkeypatch.setattr(graph, "complete", fake)
    done = list(graph.run(POSTING, CV))[-1]
    assert done["result"]["draft"]["bullets"] == ["strong"]
    assert done["result"]["critique"]["score"] == 0.7
    assert done["result"]["approved"] is False
