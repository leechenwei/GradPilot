from __future__ import annotations

import pytest

from app.config import Settings
from app.graph import Event, run_graph
from app.llm import MockClient
from app.schemas import RunRequest, RunResult

POSTING = "Graduate Data Engineer at Northwind Analytics. Python, SQL and pipeline work required."
CV = "BSc Computer Science graduate. Built a Python ETL into PostgreSQL for a 2 million row dataset."


def make_settings(max_revisions: int = 2) -> Settings:
    return Settings(
        provider="mock",
        model="mock-1",
        api_key=None,
        free_runs_per_day=5,
        max_revisions=max_revisions,
        request_timeout=10.0,
    )


async def collect(max_revisions: int = 2) -> list[Event]:
    request = RunRequest(job_posting=POSTING, cv=CV, target_role="Graduate Data Engineer")
    return [event async for event in run_graph(request, MockClient(), make_settings(max_revisions))]


async def test_graph_runs_every_agent_in_order() -> None:
    events = await collect()
    started = [e.agent for e in events if e.type == "agent_started"]
    assert started == ["scout", "matcher", "writer", "critic", "writer", "critic", "interviewer"]


async def test_graph_emits_start_and_finish_envelope() -> None:
    events = await collect()
    assert events[0].type == "run_started"
    assert events[-1].type == "run_finished"


async def test_critic_rejection_triggers_exactly_one_revision() -> None:
    events = await collect()
    result = RunResult.model_validate(events[-1].data)
    assert result.revisions == 1
    assert result.critique.approved is True


async def test_revision_budget_of_zero_skips_the_loop() -> None:
    events = await collect(max_revisions=0)
    writer_runs = [e for e in events if e.type == "agent_started" and e.agent == "writer"]
    assert len(writer_runs) == 1
    result = RunResult.model_validate(events[-1].data)
    assert result.critique.approved is False


async def test_revised_draft_incorporates_critic_feedback() -> None:
    events = await collect()
    result = RunResult.model_validate(events[-1].data)
    assert "40% fewer manual refreshes" in result.application.cv_bullets[0]


async def test_result_is_fully_populated() -> None:
    events = await collect()
    result = RunResult.model_validate(events[-1].data)
    assert result.brief.requirements
    assert result.match.matches and result.match.gaps
    assert len(result.application.cv_bullets) >= 3
    assert result.interview.questions and result.interview.questions_to_ask_them


async def test_events_serialise_to_sse_frames() -> None:
    events = await collect()
    frame = events[-1].to_sse()
    assert frame.startswith("data: ") and frame.endswith("\n\n")


def test_run_request_rejects_thin_input() -> None:
    with pytest.raises(ValueError):
        RunRequest(job_posting="too short", cv=CV)
