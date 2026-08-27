"""Deterministic responses that let the whole agent graph run without an API key.

Each agent tags its system prompt with `[agent:<name>]`, which is how the mock
picks a reply. The critic intentionally rejects the first draft so the revision
loop is exercised in demos and tests.
"""

from __future__ import annotations

import json
import re
from typing import Any

_AGENT_TAG = re.compile(r"\[agent:([a-z_]+)\]")
_REVISION_HINT = "previous_draft"
_QUANTIFIED_OUTCOME = "40% fewer manual refreshes"


def _scout() -> dict[str, Any]:
    return {
        "company": "Northwind Analytics",
        "role": "Graduate Data Engineer",
        "seniority": "graduate",
        "requirements": [
            {"text": "Python and SQL fundamentals", "kind": "must_have"},
            {"text": "Experience building ETL or data pipelines", "kind": "must_have"},
            {"text": "Cloud exposure (AWS or GCP)", "kind": "nice_to_have"},
            {"text": "Clear written communication with non-technical stakeholders", "kind": "nice_to_have"},
        ],
        "keywords": ["python", "sql", "etl", "airflow", "dbt", "gcp"],
        "company_signals": [
            "Small data team, so ownership is expected early",
            "Posting stresses documentation and stakeholder updates",
        ],
    }


def _matcher() -> dict[str, Any]:
    return {
        "overall_fit": 72,
        "matches": [
            {
                "requirement": "Python and SQL fundamentals",
                "evidence": "Final year project used Python and PostgreSQL for a 2M-row dataset",
                "score": 5,
            },
            {
                "requirement": "Experience building ETL or data pipelines",
                "evidence": "Coursework scraper with a scheduled refresh, but no production pipeline",
                "score": 3,
            },
            {"requirement": "Cloud exposure (AWS or GCP)", "evidence": "No cloud work listed", "score": 1},
            {
                "requirement": "Clear written communication with non-technical stakeholders",
                "evidence": "Presented capstone to a non-technical panel",
                "score": 4,
            },
        ],
        "strengths": [
            "Hands-on Python and SQL with a dataset large enough to matter",
            "Already comfortable explaining technical work to non-specialists",
        ],
        "gaps": ["No cloud platform experience", "No orchestration tool on the CV"],
        "quick_wins": [
            "Finish the free GCP data engineering quest and list it under Certifications",
            "Rebuild the scraper as a small Airflow DAG and push it to GitHub this week",
        ],
    }


def _writer(revision: bool) -> dict[str, Any]:
    suffix = " Measured the impact at 40% fewer manual refreshes." if revision else ""
    return {
        "headline": "Graduate data engineer with production-shaped Python and SQL projects",
        "cv_bullets": [
            "Built a Python ETL that ingested 2M rows into PostgreSQL and cut report prep from 3 hours to 12 minutes."
            + suffix,
            "Modelled a star schema in dbt-style SQL, documenting every transformation for non-technical reviewers.",
            "Automated a daily scraper with retry and alerting, keeping the dataset fresh without manual runs.",
        ],
        "cover_letter": (
            "Dear Northwind Analytics team,\n\n"
            "Your graduate data engineer posting asks for someone who can own a pipeline end to end and explain "
            "it to the people who depend on it. That is exactly the loop I have been practising.\n\n"
            "In my final year project I ingested two million rows into PostgreSQL with Python, modelled the data "
            "for analysts, and presented the result to a non-technical panel." + suffix + "\n\n"
            "I am currently closing my main gap by rebuilding that pipeline on GCP with an orchestrator, and I "
            "would like to keep learning that at Northwind.\n\nKind regards,\nA. Graduate"
        ),
    }


def _critic(draft_is_quantified: bool) -> dict[str, Any]:
    if draft_is_quantified:
        return {
            "score": 88,
            "approved": True,
            "issues": [],
            "instructions": "",
        }
    return {
        "score": 68,
        "approved": False,
        "issues": [
            "Lead bullet states the task but not the measurable outcome",
            "Cover letter does not acknowledge the cloud gap concretely enough",
        ],
        "instructions": (
            "Add a quantified outcome to the lead bullet and make the gap paragraph name the specific "
            "cloud skill being closed."
        ),
    }


def _interviewer() -> dict[str, Any]:
    return {
        "questions": [
            {
                "question": "Walk me through the pipeline you built and one thing that broke.",
                "why_asked": "They want to hear real debugging, not a tutorial walkthrough.",
                "star_answer": (
                    "Situation: my capstone ingested 2M rows nightly. Task: the job silently produced "
                    "duplicates. Action: I added a primary-key upsert and a row-count assertion that failed "
                    "loudly. Result: duplicates dropped to zero and I caught two upstream schema changes early."
                ),
            },
            {
                "question": "You have no cloud experience. How would you ramp up?",
                "why_asked": "It is the obvious gap; they are testing self-awareness over defensiveness.",
                "star_answer": (
                    "I name the gap directly, describe the GCP quest I am part way through, and explain how I "
                    "am porting my existing pipeline to BigQuery so the learning is concrete rather than theoretical."
                ),
            },
            {
                "question": "How do you explain a broken dashboard to a non-technical stakeholder?",
                "why_asked": "The posting stresses stakeholder communication.",
                "star_answer": (
                    "Lead with impact and the fix window, avoid jargon, then follow up in writing so the "
                    "stakeholder has something to forward."
                ),
            },
        ],
        "questions_to_ask_them": [
            "What does the first pipeline I own look like?",
            "How does the team decide when a dataset is trustworthy enough to publish?",
            "What does a graduate doing well after six months look like here?",
        ],
    }


def mock_completion(system: str, user: str) -> str:
    match = _AGENT_TAG.search(system)
    agent = match.group(1) if match else ""
    revision = _REVISION_HINT in user
    if agent == "scout":
        payload = _scout()
    elif agent == "matcher":
        payload = _matcher()
    elif agent == "writer":
        payload = _writer(revision)
    elif agent == "critic":
        payload = _critic(_QUANTIFIED_OUTCOME in user)
    elif agent == "interviewer":
        payload = _interviewer()
    else:
        payload = {}
    return json.dumps(payload)
