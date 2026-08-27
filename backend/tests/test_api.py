from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app, quota
from app.schemas import RunResult
from tests.test_graph import CV, POSTING


def parse_events(body: str) -> list[dict[str, object]]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


def test_health_reports_mock_mode() -> None:
    with TestClient(app) as client:
        payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["mock_mode"] is True


def test_sample_endpoint_returns_usable_inputs() -> None:
    with TestClient(app) as client:
        payload = client.get("/api/sample").json()
    assert len(payload["job_posting"]) > 200
    assert len(payload["cv"]) > 200


def test_run_streams_events_to_completion() -> None:
    quota._hits.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/run",
            json={"job_posting": POSTING, "cv": CV, "target_role": ""},
            headers={"X-Client-Id": "test-stream"},
        )
    assert response.status_code == 200
    events = parse_events(response.text)
    assert events[0]["type"] == "quota"
    assert events[-1]["type"] == "run_finished"
    result = RunResult.model_validate(events[-1]["data"])
    assert result.match.overall_fit > 0
    assert result.application.cv_bullets


def test_run_rejects_invalid_payload() -> None:
    with TestClient(app) as client:
        response = client.post("/api/run", json={"job_posting": "short", "cv": "short"})
    assert response.status_code == 422


def test_quota_blocks_after_the_free_limit() -> None:
    quota._hits.clear()
    body = {"job_posting": POSTING, "cv": CV, "target_role": ""}
    headers = {"X-Client-Id": "test-quota"}
    with TestClient(app) as client:
        for _ in range(quota.limit):
            assert client.post("/api/run", json=body, headers=headers).status_code == 200
        blocked = client.post("/api/run", json=body, headers=headers)
    assert blocked.status_code == 429
    assert blocked.json()["detail"]["limit"] == quota.limit
