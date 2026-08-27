"""The five agents.

Each agent is a small, single-responsibility unit: a system prompt, a user
prompt built from the current run state, and a Pydantic model it must return.
Keeping them uniform is what lets `graph.py` stay a plain, readable pipeline.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from .llm import ChatClient, LLMError, parse_json_object
from .schemas import (
    Application,
    Critique,
    InterviewPack,
    JobBrief,
    MatchReport,
)

TModel = TypeVar("TModel", bound=BaseModel)

JSON_RULE = (
    "Return a single JSON object and nothing else. No prose, no markdown fences. "
    "Every field in the schema must be present."
)


class Agent(Generic[TModel]):
    def __init__(self, name: str, system: str, output_model: type[TModel]) -> None:
        self.name = name
        self.system = f"[agent:{name}]\n{system}\n\n{JSON_RULE}"
        self.output_model = output_model

    async def run(self, client: ChatClient, user_prompt: str) -> TModel:
        """Call the model, then give it one chance to repair a malformed reply.

        Schema drift is the normal failure mode here, not the exception, so the
        validation error is fed back rather than surfaced to the user.
        """
        prompt = user_prompt
        last_error: Exception | None = None
        for attempt in range(2):
            raw = await client.complete(self.system, prompt)
            try:
                return self.output_model.model_validate(parse_json_object(raw))
            except (ValidationError, LLMError) as exc:
                last_error = exc
                if attempt == 0:
                    prompt = (
                        f"{user_prompt}\n\nYour previous reply was rejected:\n{raw[:2000]}\n\n"
                        f"Validation error:\n{exc}\n\nReturn corrected JSON only."
                    )
        raise LLMError(f"{self.name} returned an invalid payload: {last_error}")


SCOUT = Agent(
    "scout",
    (
        "You are a recruiter who reads job postings for a living. Extract the company, role and "
        "seniority, then split the posting into concrete must-have and nice-to-have requirements. "
        "Requirements must be specific and testable; never copy marketing fluff. Under company_signals, "
        "note what the wording implies about the team, e.g. that a small team means early ownership. "
        "Schema: {company, role, seniority (internship|graduate|junior|mid|unknown), "
        "requirements: [{text, kind}], keywords: [string], company_signals: [string]}."
    ),
    JobBrief,
)

MATCHER = Agent(
    "matcher",
    (
        "You compare a fresh graduate's CV against a job brief. Score each requirement 0-5 using only "
        "evidence that is actually present in the CV; if there is no evidence, say so and score it low. "
        "Never invent experience. overall_fit is 0-100. quick_wins must be actions the candidate can "
        "realistically complete within a week to close a gap. "
        "Schema: {overall_fit, matches: [{requirement, evidence, score}], strengths: [string], "
        "gaps: [string], quick_wins: [string]}."
    ),
    MatchReport,
)

WRITER = Agent(
    "writer",
    (
        "You rewrite a fresh graduate's application material. Produce cv_bullets that each pair a concrete "
        "action with a measurable outcome, drawn strictly from the CV provided; if a number is absent, "
        "describe scope instead of fabricating one. The cover letter is at most four short paragraphs, "
        "addresses the largest gap honestly, and avoids cliches such as 'passionate' or 'team player'. "
        "If revision instructions are supplied, apply every one of them. "
        "Schema: {headline, cv_bullets: [string], cover_letter}."
    ),
    Application,
)

CRITIC = Agent(
    "critic",
    (
        "You are a blunt hiring manager reviewing a draft application. Score 0-100 on evidence, "
        "specificity, honesty about gaps and tone. Approve only when the draft would survive a real "
        "screen: approved=true requires score >= 80. List concrete issues and write instructions the "
        "writer can act on directly. "
        "Schema: {score, approved, issues: [string], instructions}."
    ),
    Critique,
)

INTERVIEWER = Agent(
    "interviewer",
    (
        "You prepare a fresh graduate for interview. Generate the questions this specific posting and CV "
        "invite, including the uncomfortable one about their biggest gap. Each answer is a STAR scaffold "
        "grounded in the candidate's real experience, written as guidance rather than a script to recite. "
        "Also suggest questions the candidate should ask the interviewer. "
        "Schema: {questions: [{question, why_asked, star_answer}], questions_to_ask_them: [string]}."
    ),
    InterviewPack,
)
