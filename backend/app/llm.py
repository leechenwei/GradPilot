"""One tiny LLM seam: agents call complete(), nothing else knows about providers."""

from __future__ import annotations

import json
import os
import time
from typing import Any, NamedTuple

import httpx

TIMEOUT = 60.0
RETRY_STATUSES = (429, 502, 503, 529)  # free tiers bounce constantly; one retry is worth it
PROVIDERS = ("openai", "anthropic", "gemini", "openrouter")


class Creds(NamedTuple):
    """A key the user supplied for this request. Never logged, never stored."""

    provider: str
    key: str
    model: str = ""  # OpenRouter's free model ids come and go, so let the user name one


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
    # Free ids rotate; override with GRADPILOT_LLM_MODEL or the model box in the UI.
    "openrouter": "nvidia/nemotron-3-super-120b-a12b:free",
}


def _model(name: str, creds: Creds | None = None) -> str:
    if creds and creds.model:
        return creds.model
    return os.getenv("GRADPILOT_LLM_MODEL") or _DEFAULT_MODELS.get(name, "")


def complete(agent: str, system: str, user: str, creds: Creds | None = None) -> dict[str, Any]:
    """Return the agent's JSON object. `agent` only selects the mock reply."""
    name = creds.provider if creds else provider()
    if name == "mock":
        from app.mock import mock_reply

        return mock_reply(agent, user)
    raw = _call(name, system, user, creds)
    return _parse(raw)


def _parse(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if raw.startswith("```"):  # models like fencing JSON no matter what you ask
        raw = raw.split("```")[1].removeprefix("json").strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        # Smaller models like to wrap JSON in a sentence. Take the outermost object.
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end <= start:
            raise LLMError(f"model did not return JSON: {raw[:200]}") from exc
        try:
            value = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            raise LLMError(f"model did not return JSON: {raw[:200]}") from exc
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        value = value[0]  # some models wrap the object in a one-item array
    if not isinstance(value, dict):
        raise LLMError("model returned JSON but not an object")
    return value


def _call(name: str, system: str, user: str, creds: Creds | None) -> str:
    if name == "openai":
        body = _post(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {_key(creds, 'OPENAI_API_KEY')}"},
            {
                "model": _model(name, creds),
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        return _dig(body, "choices", 0, "message", "content")
    if name == "openrouter":
        # OpenAI-shaped, but no response_format: several free models reject it outright.
        body = _post(
            "https://openrouter.ai/api/v1/chat/completions",
            {
                "Authorization": f"Bearer {_key(creds, 'OPENROUTER_API_KEY')}",
                "HTTP-Referer": "https://github.com/leechenwei/GradPilot",
                "X-Title": "GradPilot",
            },
            {
                "model": _model(name, creds),
                "messages": [
                    {"role": "system", "content": system + " Reply with JSON only."},
                    {"role": "user", "content": user},
                ],
            },
        )
        return _dig(body, "choices", 0, "message", "content")
    if name == "anthropic":
        body = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": _key(creds, "ANTHROPIC_API_KEY"), "anthropic-version": "2023-06-01"},
            {
                "model": _model(name, creds),
                "max_tokens": 2048,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
        return _dig(body, "content", 0, "text")
    if name == "gemini":
        key = _key(creds, "GEMINI_API_KEY")
        body = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{_model(name, creds)}"
            f":generateContent?key={key}",
            {},
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
        return _dig(body, "candidates", 0, "content", "parts", 0, "text")
    raise LLMError(f"unknown provider: {name}")


def _dig(body: Any, *path: str | int) -> str:
    """Walk the provider's reply shape, or say what came back instead.

    A raw KeyError here reads as a bug in GradPilot. It is almost always the
    provider answering with an error object, a moderation block, or an empty
    choices list, and the user needs to see which.
    """
    node = body
    for step in path:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected reply from the model: {str(body)[:300]}") from exc
    if not isinstance(node, str) or not node.strip():
        raise LLMError(f"the model returned no text: {str(body)[:300]}")
    return node


def _key(creds: Creds | None, env: str) -> str:
    """A user-supplied key wins over the server's, so BYO-key costs the server nothing."""
    if creds:
        return creds.key
    value = os.getenv(env)
    if not value:
        raise LLMError(f"{env} is not set")
    return value


def _post(url: str, headers: dict[str, str], body: dict[str, Any]) -> Any:
    for attempt in (0, 1):
        response = httpx.post(url, headers=headers, json=body, timeout=TIMEOUT)
        if response.status_code in RETRY_STATUSES and attempt == 0:
            time.sleep(2)  # free models bounce under load; one retry saves most runs
            continue
        break
    if response.status_code >= 400:
        raise LLMError(f"{response.status_code}: {response.text[:300]}")
    try:
        return response.json()
    except ValueError as exc:
        raise LLMError(f"the provider returned a non-JSON body: {response.text[:200]}") from exc
