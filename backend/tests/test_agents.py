from __future__ import annotations

import httpx
import pytest

from app.agents import SCOUT
from app.llm import HTTPChatClient, LLMError
from tests.test_llm import make_settings


class ScriptedClient:
    """Returns each queued reply in turn and records the prompts it was given."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    async def complete(self, system: str, user: str) -> str:
        self.prompts.append(user)
        return self.replies.pop(0)


VALID = (
    '{"company": "Acme", "role": "Grad Engineer", "seniority": "graduate", '
    '"requirements": [], "keywords": [], "company_signals": []}'
)


async def test_agent_parses_a_valid_reply() -> None:
    brief = await SCOUT.run(ScriptedClient(VALID), "posting")
    assert brief.company == "Acme"


async def test_agent_repairs_an_invalid_reply_once() -> None:
    client = ScriptedClient("not json at all", VALID)
    brief = await SCOUT.run(client, "posting")
    assert brief.role == "Grad Engineer"
    assert "Validation error" in client.prompts[1]


async def test_agent_gives_up_after_one_repair() -> None:
    client = ScriptedClient("nope", "still nope")
    with pytest.raises(LLMError, match="scout returned an invalid payload"):
        await SCOUT.run(client, "posting")
    assert len(client.prompts) == 2


async def test_hyphenated_enums_from_the_model_are_accepted() -> None:
    reply = (
        '{"company": "Acme", "role": "Grad", "seniority": "Graduate", '
        '"requirements": [{"text": "SQL", "kind": "must-have"}, {"text": "GCP", "kind": "Nice To Have"}], '
        '"keywords": [], "company_signals": []}'
    )
    brief = await SCOUT.run(ScriptedClient(reply), "posting")
    assert brief.seniority == "graduate"
    assert [r.kind for r in brief.requirements] == ["must_have", "nice_to_have"]


def test_backoff_honours_retry_after_header() -> None:
    response = httpx.Response(429, headers={"retry-after": "7"})
    assert HTTPChatClient._backoff(0, response) == 7.0


def test_backoff_grows_without_a_header() -> None:
    response = httpx.Response(503)
    first = HTTPChatClient._backoff(0, response)
    third = HTTPChatClient._backoff(2, response)
    assert third > first


def test_agent_system_prompt_is_tagged_for_the_mock() -> None:
    assert SCOUT.system.startswith("[agent:scout]")
    assert make_settings("mock", None).is_mock
