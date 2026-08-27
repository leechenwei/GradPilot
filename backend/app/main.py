from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import quota
from app.graph import run
from app.llm import LLMError, provider

app = FastAPI(title="GradPilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ponytail: no cookies, no secrets. Lock down if auth lands.
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    posting: str = Field(min_length=40, max_length=20_000)
    cv: str = Field(min_length=40, max_length=20_000)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": provider()}


@app.get("/api/quota")
def get_quota(x_session_id: str = Header(default="anonymous")) -> dict[str, int]:
    return {"remaining": quota.remaining(x_session_id), "free_runs": quota.FREE_RUNS}


@app.post("/api/run")
def start_run(
    body: RunRequest, x_session_id: str = Header(default="anonymous")
) -> StreamingResponse:
    try:
        left = quota.consume(x_session_id)
    except quota.QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    return StreamingResponse(
        _stream(body, left),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream(body: RunRequest, left: int) -> Iterator[str]:
    try:
        for event in run(body.posting, body.cv):
            if event["type"] == "done":
                event["result"]["runs_left"] = left
            yield _sse(event)
    except LLMError as exc:
        # The client already has a 200 and half a stream, so the error must ride the stream.
        yield _sse({"type": "error", "message": str(exc)})


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
