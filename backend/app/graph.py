"""Agent graph orchestration.

    scout -> matcher -> writer -> critic --(rejected, budget left)--> writer
                                     |
                                     +--(approved or budget spent)--> interviewer

The loop is bounded by `Settings.max_revisions` so a stubborn critic can never
run up an unbounded bill.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from .agents import CRITIC, INTERVIEWER, MATCHER, SCOUT, WRITER
from .config import Settings
from .llm import ChatClient
from .schemas import Application, Critique, JobBrief, MatchReport, RunRequest, RunResult


@dataclass
class Event:
    """A step in the run, streamed to the client as it happens."""

    type: str
    agent: str = ""
    message: str = ""
    data: dict[str, Any] | None = None

    def to_sse(self) -> str:
        payload = {"type": self.type, "agent": self.agent, "message": self.message, "data": self.data}
        return f"data: {json.dumps(payload)}\n\n"


def _brief_prompt(request: RunRequest) -> str:
    target = f"\nThe candidate is targeting: {request.target_role}" if request.target_role else ""
    return f"JOB POSTING:\n{request.job_posting}{target}"


def _match_prompt(request: RunRequest, brief: JobBrief) -> str:
    return f"JOB BRIEF:\n{brief.model_dump_json(indent=2)}\n\nCANDIDATE CV:\n{request.cv}"


def _write_prompt(
    request: RunRequest,
    brief: JobBrief,
    match: MatchReport,
    previous: Application | None,
    critique: Critique | None,
) -> str:
    sections = [
        f"JOB BRIEF:\n{brief.model_dump_json(indent=2)}",
        f"MATCH REPORT:\n{match.model_dump_json(indent=2)}",
        f"CANDIDATE CV:\n{request.cv}",
    ]
    if previous is not None and critique is not None:
        sections.append(f"previous_draft:\n{previous.model_dump_json(indent=2)}")
        sections.append(
            f"REVISION INSTRUCTIONS (apply all):\n{critique.instructions}\n"
            + "\n".join(f"- {issue}" for issue in critique.issues)
        )
    return "\n\n".join(sections)


def _critique_prompt(brief: JobBrief, application: Application) -> str:
    return f"JOB BRIEF:\n{brief.model_dump_json(indent=2)}\n\nDRAFT:\n{application.model_dump_json(indent=2)}"


def _interview_prompt(request: RunRequest, brief: JobBrief, match: MatchReport) -> str:
    return (
        f"JOB BRIEF:\n{brief.model_dump_json(indent=2)}\n\n"
        f"MATCH REPORT:\n{match.model_dump_json(indent=2)}\n\n"
        f"CANDIDATE CV:\n{request.cv}"
    )


async def run_graph(
    request: RunRequest, client: ChatClient, settings: Settings
) -> AsyncIterator[Event]:
    run_id = uuid.uuid4().hex[:12]
    yield Event("run_started", message="Assembling the crew", data={"run_id": run_id})

    yield Event("agent_started", SCOUT.name, "Reading the posting")
    brief = await SCOUT.run(client, _brief_prompt(request))
    yield Event("agent_finished", SCOUT.name, f"{brief.role} at {brief.company}", brief.model_dump())

    yield Event("agent_started", MATCHER.name, "Scoring your CV against each requirement")
    match = await MATCHER.run(client, _match_prompt(request, brief))
    yield Event("agent_finished", MATCHER.name, f"Overall fit {match.overall_fit}%", match.model_dump())

    application: Application | None = None
    critique: Critique | None = None
    revisions = 0

    for attempt in range(settings.max_revisions + 1):
        label = "Drafting your application" if attempt == 0 else "Applying the critic's notes"
        yield Event("agent_started", WRITER.name, label, {"attempt": attempt + 1})
        application = await WRITER.run(
            client, _write_prompt(request, brief, match, application, critique)
        )
        yield Event("agent_finished", WRITER.name, application.headline, application.model_dump())

        yield Event("agent_started", CRITIC.name, "Reviewing the draft like a hiring manager")
        critique = await CRITIC.run(client, _critique_prompt(brief, application))
        verdict = "Approved" if critique.approved else "Sending it back for a rewrite"
        yield Event("agent_finished", CRITIC.name, f"{verdict} ({critique.score}/100)", critique.model_dump())

        if critique.approved:
            break
        if attempt < settings.max_revisions:
            revisions += 1

    assert application is not None and critique is not None

    yield Event("agent_started", INTERVIEWER.name, "Building your interview pack")
    interview = await INTERVIEWER.run(client, _interview_prompt(request, brief, match))
    yield Event(
        "agent_finished",
        INTERVIEWER.name,
        f"{len(interview.questions)} questions ready",
        interview.model_dump(),
    )

    result = RunResult(
        run_id=run_id,
        brief=brief,
        match=match,
        application=application,
        critique=critique,
        interview=interview,
        revisions=revisions,
    )
    yield Event("run_finished", message="Done", data=result.model_dump())
