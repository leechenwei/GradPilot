from __future__ import annotations

import json

import pytest

from app.config import Settings
from app.llm import HTTPChatClient, LLMError, MockClient, build_client, parse_json_object


def make_settings(provider: str = "gemini", api_key: str | None = "key") -> Settings:
    return Settings(
        provider=provider,
        model="test-model",
        api_key=api_key,
        free_runs_per_day=5,
        max_revisions=2,
        request_timeout=10.0,
    )


def test_parse_json_object_handles_bare_json() -> None:
    assert parse_json_object('{"a": 1}') == {"a": 1}


def test_parse_json_object_handles_fenced_json() -> None:
    raw = 'Sure!\n```json\n{"a": 1}\n```'
    assert parse_json_object(raw) == {"a": 1}


def test_parse_json_object_handles_surrounding_prose() -> None:
    assert parse_json_object('Here you go: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}


def test_parse_json_object_rejects_non_object() -> None:
    with pytest.raises(LLMError):
        parse_json_object("just some words")


def test_build_client_returns_mock_without_key() -> None:
    assert isinstance(build_client(make_settings("mock", None)), MockClient)


@pytest.mark.parametrize(
    ("provider", "expected_host"),
    [
        ("gemini", "generativelanguage.googleapis.com"),
        ("anthropic", "api.anthropic.com"),
        ("openai", "api.openai.com"),
    ],
)
def test_build_request_targets_correct_provider(provider: str, expected_host: str) -> None:
    client = HTTPChatClient(make_settings(provider))
    url, headers, payload = client._build_request("system", "user")
    assert expected_host in url
    assert headers
    assert payload


def test_gemini_request_sends_system_instruction_separately() -> None:
    client = HTTPChatClient(make_settings("gemini"))
    _, headers, payload = client._build_request("SYSTEM", "USER")
    assert headers["x-goog-api-key"] == "key"
    assert payload["systemInstruction"]["parts"][0]["text"] == "SYSTEM"
    assert payload["contents"][0]["parts"][0]["text"] == "USER"


def test_extract_reads_gemini_shape() -> None:
    client = HTTPChatClient(make_settings("gemini"))
    body = {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}
    assert json.loads(client._extract(body)) == {"ok": True}


def test_extract_raises_on_unexpected_shape() -> None:
    client = HTTPChatClient(make_settings("gemini"))
    with pytest.raises(LLMError):
        client._extract({"nope": 1})


def test_http_client_requires_api_key() -> None:
    with pytest.raises(LLMError):
        HTTPChatClient(make_settings("gemini", None))
