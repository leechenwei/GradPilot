"""Provider-agnostic chat client.

Every provider is reduced to `complete(system, user) -> str`. A `mock` provider
runs the full graph offline with deterministic responses so the app is always
demoable without credentials.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Any, Protocol

import httpx

from .config import Settings
from .mock_responses import mock_completion

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4


class LLMError(RuntimeError):
    pass


class ChatClient(Protocol):
    async def complete(self, system: str, user: str) -> str: ...


class MockClient:
    """Deterministic stand-in used when no API key is configured."""

    async def complete(self, system: str, user: str) -> str:
        return mock_completion(system, user)


class HTTPChatClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.api_key:
            raise LLMError(f"missing API key for provider {settings.provider}")
        self.settings = settings

    async def complete(self, system: str, user: str) -> str:
        url, headers, payload = self._build_request(system, user)
        async with httpx.AsyncClient(timeout=self.settings.request_timeout) as client:
            for attempt in range(_MAX_ATTEMPTS):
                response = await client.post(url, headers=headers, json=payload)
                if response.status_code < 400:
                    return self._extract(response.json())
                last_attempt = attempt == _MAX_ATTEMPTS - 1
                if response.status_code not in _RETRYABLE_STATUS or last_attempt:
                    raise LLMError(
                        f"{self.settings.provider} returned {response.status_code}: {response.text[:300]}"
                    )
                await asyncio.sleep(self._backoff(attempt, response))
        raise LLMError("unreachable")

    @staticmethod
    def _backoff(attempt: int, response: httpx.Response) -> float:
        """Honour Retry-After when the provider sends one, otherwise exponential with jitter."""
        retry_after = response.headers.get("retry-after")
        if retry_after and retry_after.isdigit():
            return min(float(retry_after), 30.0)
        return min(2.0**attempt, 8.0) + random.uniform(0, 0.5)

    def _build_request(self, system: str, user: str) -> tuple[str, dict[str, str], dict[str, Any]]:
        provider, model, key = self.settings.provider, self.settings.model, self.settings.api_key
        if provider == "gemini":
            return (
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                {"x-goog-api-key": str(key), "content-type": "application/json"},
                {
                    "systemInstruction": {"parts": [{"text": system}]},
                    "contents": [{"role": "user", "parts": [{"text": user}]}],
                    "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"},
                },
            )
        if provider == "anthropic":
            return (
                "https://api.anthropic.com/v1/messages",
                {"x-api-key": str(key), "anthropic-version": "2023-06-01", "content-type": "application/json"},
                {
                    "model": model,
                    "max_tokens": 4096,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
        if provider == "openai":
            return (
                "https://api.openai.com/v1/chat/completions",
                {"authorization": f"Bearer {key}", "content-type": "application/json"},
                {
                    "model": model,
                    "temperature": 0.4,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
        raise LLMError(f"unsupported provider: {provider}")

    def _extract(self, body: dict[str, Any]) -> str:
        provider = self.settings.provider
        try:
            if provider == "gemini":
                parts = body["candidates"][0]["content"]["parts"]
                return "".join(part.get("text", "") for part in parts)
            if provider == "anthropic":
                return "".join(b.get("text", "") for b in body["content"])
            return str(body["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected {provider} response shape: {json.dumps(body)[:300]}") from exc


def build_client(settings: Settings) -> ChatClient:
    return MockClient() if settings.is_mock else HTTPChatClient(settings)


def parse_json_object(raw: str) -> dict[str, Any]:
    """Extract the first JSON object from a model response.

    Models wrap JSON in prose or fences often enough that a bare `json.loads`
    is not usable as the only strategy.
    """
    candidates: list[str] = [raw.strip()]
    fenced = _JSON_BLOCK.search(raw)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LLMError(f"model did not return a JSON object: {raw[:300]}")
