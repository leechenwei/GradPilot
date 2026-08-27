"""Canned agent replies for offline demos.

Stateless on purpose: the critic decides from the draft it is given, not from a
call counter, so the revision loop is reproducible in any order.
"""

from __future__ import annotations

import re
from typing import Any

# ponytail: keyword scrape, not a parser. Enough to make the demo echo the posting.
_SKILLS = [
    "python", "typescript", "react", "fastapi", "sql", "docker", "aws", "kubernetes",
    "pandas", "pytorch", "node", "go", "java", "git", "ci/cd", "rest", "llm",
]


def _found(text: str, words: list[str]) -> list[str]:
    low = text.lower()
    return [w for w in words if w in low]


def mock_reply(agent: str, prompt: str) -> dict[str, Any]:
    skills = _found(prompt, _SKILLS) or ["python", "sql"]
    if agent == "scout":
        return {
            "role": _first_line(prompt) or "Software Engineer",
            "company_signals": ["ships weekly", "small team", "values ownership"],
            "requirements": [
                {"text": f"Hands-on {s}", "weight": 3 if i < 2 else 2}
                for i, s in enumerate(skills[:5])
            ],
        }
    if agent == "matcher":
        have = skills[:3]
        missing = skills[3:5]
        return {
            "overall_fit": 0.72,
            "strengths": [{"requirement": s, "evidence": f"CV shows {s} in a shipped project"}
                          for s in have],
            "gaps": [{"requirement": s, "advice": f"Name any coursework or side project using {s}"}
                     for s in missing],
        }
    if agent == "writer":
        revising = "critic feedback" in prompt.lower()
        return {
            "bullets": _bullets(skills, revising),
            "cover_letter": _letter(skills, revising),
        }
    if agent == "critic":
        return _critique(prompt)
    if agent == "interviewer":
        return {
            "questions": [
                {
                    "question": f"Walk me through a project where you used {s}.",
                    "why": f"The posting weights {s} heavily.",
                    "star": {
                        "situation": "A project with a real user or deadline",
                        "task": "What you personally owned",
                        "action": f"How you applied {s}",
                        "result": "A number: time saved, users served, bugs cut",
                    },
                }
                for s in skills[:4]
            ]
        }
    raise ValueError(f"no mock reply for agent {agent!r}")


def _first_line(prompt: str) -> str:
    for line in prompt.splitlines():
        line = line.strip()
        if line and not line.endswith(":"):
            return line[:80]
    return ""


def _bullets(skills: list[str], revising: bool) -> list[str]:
    if not revising:
        return [
            f"Worked with {s} on university and personal projects." for s in skills[:3]
        ]
    return [
        f"Built a {skills[0]} service handling 1,200 requests/day, cutting manual work "
        "by 6 h/week.",
        f"Shipped a {skills[1] if len(skills) > 1 else skills[0]} feature used by 40 classmates, "
        "with 92% test coverage.",
        "Reduced a nightly batch job from 45 min to 4 min by batching queries.",
    ]


def _letter(skills: list[str], revising: bool) -> str:
    if not revising:
        return (
            "Dear Hiring Team,\n\nI am very passionate about technology and I believe I "
            f"would be a great fit for this role. I have experience with {', '.join(skills[:3])} "
            "and I am a fast learner.\n\nSincerely,\nA Candidate"
        )
    return (
        "Dear Hiring Team,\n\nYour posting asks for someone who ships. Last semester I built a "
        f"{skills[0]} service that now handles 1,200 requests a day for 40 classmates, and I cut "
        "its nightly batch from 45 minutes to 4 by batching queries.\n\nI would like to do that "
        "same work on your team.\n\nSincerely,\nA Candidate"
    )


def _critique(prompt: str) -> dict[str, Any]:
    """Score the draft the way a blunt reviewer would: numbers or it did not happen."""
    numbers = len(re.findall(r"\d", prompt))
    filler = sum(prompt.lower().count(w) for w in ("passionate", "fast learner", "great fit"))
    evidence = min(1.0, numbers / 12)
    tone = max(0.0, 1.0 - filler * 0.25)
    # A canned reviewer that hands out 1.00 reads as fake. Cap it.
    score = round(min(0.95, 0.5 * evidence + 0.3 * tone + 0.2), 2)
    notes = []
    if evidence < 0.6:
        notes.append("Bullets state duties, not results. Add a number to each one.")
    if tone < 1.0:
        notes.append("Cut filler like 'passionate' and 'fast learner'. Show the work instead.")
    if not notes:
        notes.append("Grounded and specific. Ship it.")
    return {"score": score, "notes": notes}
