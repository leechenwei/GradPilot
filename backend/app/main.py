"""FastAPI application exposing the agent graph over SSE."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from .config import load_settings
from .graph import Event, run_graph
from .llm import LLMError, build_client
from .quota import DailyQuota, QuotaExceeded
from .schemas import RunRequest

settings = load_settings()
quota = DailyQuota(settings.free_runs_per_day)

app = FastAPI(title="GradPilot", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("GRADPILOT_ALLOWED_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _client_id(request: Request, header_value: str | None) -> str:
    raw = header_value or (request.client.host if request.client else "anonymous")
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@app.get("/api/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "provider": settings.provider,
        "model": settings.model,
        "mock_mode": settings.is_mock,
        "free_runs_per_day": settings.free_runs_per_day,
    }


@app.post("/api/run")
async def run(
    request: Request,
    payload: RunRequest,
    x_client_id: str | None = Header(default=None, alias="X-Client-Id"),
) -> StreamingResponse:
    client_id = _client_id(request, x_client_id)
    try:
        remaining = quota.check_and_consume(client_id)
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"error": str(exc), "limit": exc.limit, "retry_after_seconds": exc.retry_after},
        ) from exc

    llm = build_client(settings)

    async def stream() -> AsyncIterator[str]:
        yield Event("quota", message=f"{remaining} free runs left today").to_sse()
        try:
            async for event in run_graph(payload, llm, settings):
                if await request.is_disconnected():
                    return
                yield event.to_sse()
        except (LLMError, ValidationError) as exc:
            yield Event("error", message=str(exc)).to_sse()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/sample")
async def sample() -> dict[str, str]:
    """Prefilled inputs so a first-time visitor can see a run in one click."""
    path = os.path.join(os.path.dirname(__file__), "sample_data.json")
    with open(path, encoding="utf-8") as handle:
        data: dict[str, str] = json.load(handle)
    return data
