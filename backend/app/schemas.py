"""Pydantic models shared by the API and the agent graph."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Seniority = Literal["internship", "graduate", "junior", "mid", "unknown"]
RequirementKind = Literal["must_have", "nice_to_have"]


def _normalise_enum(value: object) -> object:
    """Models write 'must-have' or 'Nice To Have' as often as the exact token."""
    if isinstance(value, str):
        return value.strip().lower().replace("-", "_").replace(" ", "_")
    return value


class RunRequest(BaseModel):
    job_posting: str = Field(min_length=40, max_length=20_000)
    cv: str = Field(min_length=40, max_length=20_000)
    target_role: str = Field(default="", max_length=200)

    @field_validator("job_posting", "cv")
    @classmethod
    def _strip(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 40:
            raise ValueError("needs at least 40 characters of real content")
        return stripped


class Requirement(BaseModel):
    text: str
    kind: RequirementKind = "must_have"

    @field_validator("kind", mode="before")
    @classmethod
    def _normalise_kind(cls, value: object) -> object:
        normalised = _normalise_enum(value)
        return normalised if normalised in {"must_have", "nice_to_have"} else "must_have"


class JobBrief(BaseModel):
    company: str = "Unknown"
    role: str = "Unknown"
    seniority: Seniority = "unknown"
    requirements: list[Requirement] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    company_signals: list[str] = Field(default_factory=list)

    @field_validator("seniority", mode="before")
    @classmethod
    def _normalise_seniority(cls, value: object) -> object:
        normalised = _normalise_enum(value)
        return normalised if normalised in {"internship", "graduate", "junior", "mid"} else "unknown"


class RequirementMatch(BaseModel):
    requirement: str
    evidence: str = ""
    score: int = Field(ge=0, le=5, default=0)


class MatchReport(BaseModel):
    overall_fit: int = Field(ge=0, le=100, default=0)
    matches: list[RequirementMatch] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    quick_wins: list[str] = Field(default_factory=list)


class Application(BaseModel):
    headline: str = ""
    cv_bullets: list[str] = Field(default_factory=list)
    cover_letter: str = ""


class Critique(BaseModel):
    score: int = Field(ge=0, le=100, default=0)
    approved: bool = False
    issues: list[str] = Field(default_factory=list)
    instructions: str = ""


class InterviewQuestion(BaseModel):
    question: str
    why_asked: str = ""
    star_answer: str = ""


class InterviewPack(BaseModel):
    questions: list[InterviewQuestion] = Field(default_factory=list)
    questions_to_ask_them: list[str] = Field(default_factory=list)


class RunResult(BaseModel):
    run_id: str
    brief: JobBrief
    match: MatchReport
    application: Application
    critique: Critique
    interview: InterviewPack
    revisions: int = 0
