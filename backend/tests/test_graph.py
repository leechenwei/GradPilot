import json

import pytest
from fastapi.testclient import TestClient

from app import quota
from app.graph import APPROVAL_THRESHOLD, MAX_REVISIONS, run
from app.main import app

POSTING = (
    "Junior Backend Engineer\nWe need Python, FastAPI and SQL. Docker is a plus. "
    "Small team, ships weekly, values ownership."
)
CV = (
    "Chen Wei, CS graduate. Built a Python REST API for a campus club. "
    "Coursework in SQL and data structures. Comfortable with git."
)


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("GRADPILOT_LLM_PROVIDER", "mock")
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
    before = client.get("/api/quota", headers={"X-Session-Id": "s1"}).json()["remaining"]
    response = client.post(
        "/api/run", json={"posting": POSTING, "cv": CV}, headers={"X-Session-Id": "s1"}
    )
    assert response.status_code == 200
    payloads = [
        json.loads(line[len("data: "):])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert payloads[-1]["type"] == "done"
    after = client.get("/api/quota", headers={"X-Session-Id": "s1"}).json()["remaining"]
    assert after == before - 1


def test_quota_blocks_after_the_free_runs():
    client = TestClient(app)
    body = {"posting": POSTING, "cv": CV}
    for _ in range(quota.FREE_RUNS):
        assert client.post("/api/run", json=body, headers={"X-Session-Id": "s2"}).status_code == 200
    assert client.post("/api/run", json=body, headers={"X-Session-Id": "s2"}).status_code == 429


def test_short_input_is_rejected():
    client = TestClient(app)
    assert TestClient(app).post("/api/run", json={"posting": "hi", "cv": CV}).status_code == 422
    assert client.get("/api/health").json()["provider"] == "mock"
