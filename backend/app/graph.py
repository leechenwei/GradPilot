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
    # Revisions do not always improve: real critics scored pass 3 below pass 2 in
    # testing. Keep the best draft seen, not the last one written.
    best: tuple[float, dict[str, Any], dict[str, Any]] = (-1.0, {}, {})
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
        score = _score(critique)
        if score > best[0]:
            best = (score, dict(draft), dict(critique))
        if score >= APPROVAL_THRESHOLD:
            break
        feedback = "\n\nCRITIC FEEDBACK (fix every point):\n" + "\n".join(
            f"- {n}" for n in critique.get("notes", [])
        )

    score, draft, critique = best
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
            "approved": score >= APPROVAL_THRESHOLD,
            "passes": attempt + 1,
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


def _score(critique: dict[str, Any]) -> float:
    """Models write 0.72, "0.72", 72 and "72%". Land them all on 0-1, junk on 0."""
    raw = critique.get("score", 0)
    if isinstance(raw, str):
        raw = raw.strip().rstrip("%")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    if value > 1:
        value = value / 100
    return max(0.0, min(1.0, value))


def _dump(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)
