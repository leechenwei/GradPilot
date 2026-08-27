"""Runtime configuration resolved from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "gemini": "gemini-2.5-flash",
    "mock": "mock-1",
}

KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    api_key: str | None
    free_runs_per_day: int
    max_revisions: int
    request_timeout: float

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock"


def _resolve_provider() -> str:
    explicit = os.getenv("GRADPILOT_LLM_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    for provider, env_name in KEY_ENV.items():
        if os.getenv(env_name):
            return provider
    return "mock"


def load_settings() -> Settings:
    provider = _resolve_provider()
    api_key = os.getenv(KEY_ENV[provider]) if provider in KEY_ENV else None
    if provider != "mock" and not api_key:
        provider, api_key = "mock", None
    return Settings(
        provider=provider,
        model=os.getenv("GRADPILOT_LLM_MODEL") or DEFAULT_MODELS.get(provider, "mock-1"),
        api_key=api_key,
        free_runs_per_day=int(os.getenv("GRADPILOT_FREE_RUNS_PER_DAY", "5")),
        max_revisions=int(os.getenv("GRADPILOT_MAX_REVISIONS", "2")),
        request_timeout=float(os.getenv("GRADPILOT_REQUEST_TIMEOUT", "90")),
    )
