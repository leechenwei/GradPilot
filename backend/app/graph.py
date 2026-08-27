"""The agent graph: scout -> matcher -> writer <-> critic -> interviewer.

A plain loop, not a graph framework. Five nodes and one back-edge do not need one.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from app.llm import Creds, complete

APPROVAL_THRESHOLD = 0.8
MAX_REVISIONS = 2

SYSTEM = {
    "scout": "You parse job postings. Reply with JSON: role, company_signals[], "
             "requirements[{text, weight 1-3}]. Never invent requirements.",
    "matcher": "You score a CV against requirements. Reply with JSON: overall_fit 0-1, "
               "strengths[{requirement, evidence}], gaps[{requirement, advice}]. "
               "Evidence must be quoted from the CV.",
    "writer": "You rewrite CV bullets and a cover letter. Reply with JSON: bullets[], "
              "cover_letter. Use only facts present in the CV. Never invent employers, "
              "dates or numbers.",
    "critic": "You review an application draft. Reply with JSON: score 0-1, notes[]. "
              "Judge evidence, specificity and tone. Be blunt.",
    "interviewer": "You prepare interview questions. Reply with JSON: "
                   "questions[{question, why, star{situation, task, action, result}}].",
}


def run(posting: str, cv: str, creds: Creds | None = None) -> Iterator[dict[str, Any]]:
    """Yield one event per node transition, then a final 'done' event."""
    scout: dict[str, Any] = {}
    yield from _step(scout, "scout", SYSTEM["scout"], f"JOB POSTING:\n{posting}", creds=creds)

    matcher: dict[str, Any] = {}
    yield from _step(
        matcher,
        "matcher",
        SYSTEM["matcher"],
        f"REQUIREMENTS:\n{_dump(scout)}\n\nCV:\n{cv}",
        creds=creds,
    )

    draft: dict[str, Any] = {}
    critique: dict[str, Any] = {}
    feedback = ""
    for attempt in range(MAX_REVISIONS + 1):
        yield from _step(
            draft,
            "writer",
            SYSTEM["writer"],
            f"ROLE:\n{_dump(scout)}\n\nMATCH:\n{_dump(matcher)}\n\nCV:\n{cv}" + feedback,
            revision=attempt,
            creds=creds,
        )
        yield from _step(
            critique,
            "critic",
            SYSTEM["critic"],
            f"REQUIREMENTS:\n{_dump(scout)}\n\nDRAFT:\n{_dump(draft)}",
            revision=attempt,
            creds=creds,
        )
        if float(critique.get("score", 0)) >= APPROVAL_THRESHOLD:
            break
        feedback = "\n\nCRITIC FEEDBACK (fix every point):\n" + "\n".join(
            f"- {n}" for n in critique.get("notes", [])
        )

    interviewer: dict[str, Any] = {}
    yield from _step(
        interviewer,
        "interviewer",
        SYSTEM["interviewer"],
        f"ROLE:\n{_dump(scout)}\n\nGAPS:\n{_dump(matcher.get('gaps', []))}\n\nCV:\n{cv}",
        creds=creds,
    )

    yield {
        "type": "done",
        "result": {
            "scout": scout,
            "matcher": matcher,
            "draft": draft,
            "critique": critique,
            "interviewer": interviewer,
            "approved": float(critique.get("score", 0)) >= APPROVAL_THRESHOLD,
        },
    }


def _step(
    out: dict[str, Any], agent: str, system: str, user: str, revision: int = 0,
    creds: Creds | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield 'start' before the call so the UI can show the node lighting up.

    The result lands in `out` because a generator cannot both stream and return.
    """
    yield {"type": "start", "agent": agent, "revision": revision}
    out.clear()
    out.update(complete(agent, system, user, creds))
    yield {"type": "result", "agent": agent, "revision": revision, "data": dict(out)}


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)
