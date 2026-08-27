"""One tiny LLM seam: agents call complete(), nothing else knows about providers."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

TIMEOUT = 60.0


class LLMError(RuntimeError):
    pass


def provider() -> str:
    """Explicit setting wins; otherwise the first key present; otherwise mock."""
    explicit = os.getenv("GRADPILOT_LLM_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    for name, key in (("openai", "OPENAI_API_KEY"), ("anthropic", "ANTHROPIC_API_KEY"),
                      ("gemini", "GEMINI_API_KEY")):
        if os.getenv(key):
            return name
    return "mock"


_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5",
    "gemini": "gemini-2.0-flash",
}


def _model(name: str) -> str:
    return os.getenv("GRADPILOT_LLM_MODEL") or _DEFAULT_MODELS.get(name, "")


def complete(agent: str, system: str, user: str) -> dict[str, Any]:
    """Return the agent's JSON object. `agent` only selects the mock reply."""
    name = provider()
    if name == "mock":
        from app.mock import mock_reply

        return mock_reply(agent, user)
    raw = _call(name, system, user)
    return _parse(raw)


def _parse(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):  # models like fencing JSON no matter what you ask
        raw = raw.split("```")[1].removeprefix("json").strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"model did not return JSON: {raw[:200]}") from exc
    if not isinstance(value, dict):
        raise LLMError("model returned JSON but not an object")
    return value


def _call(name: str, system: str, user: str) -> str:
    if name == "openai":
        return _post(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {_key('OPENAI_API_KEY')}"},
            {
                "model": _model(name),
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
            },
        )["choices"][0]["message"]["content"]
    if name == "anthropic":
        return _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": _key("ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
            {
                "model": _model(name),
                "max_tokens": 2048,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )["content"][0]["text"]
    if name == "gemini":
        key = _key("GEMINI_API_KEY")
        return _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{_model(name)}"
            f":generateContent?key={key}",
            {},
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )["candidates"][0]["content"]["parts"][0]["text"]
    raise LLMError(f"unknown provider: {name}")


def _key(env: str) -> str:
    value = os.getenv(env)
    if not value:
        raise LLMError(f"{env} is not set")
    return value


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
    response = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT)
    if response.status_code >= 400:
        raise LLMError(f"{response.status_code}: {response.text[:300]}")
    return response.json()
