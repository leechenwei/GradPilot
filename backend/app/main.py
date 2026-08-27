from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import ingest, quota
from app.graph import run
from app.llm import LLMError, provider

log = logging.getLogger("gradpilot")

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


@app.get("/")
def root() -> dict[str, str]:
    """The bare host is the first thing anyone pastes. Do not answer it with a 404."""
    return {"service": "GradPilot API", "health": "/api/health", "docs": "/docs"}


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "provider": provider()}


@app.get("/api/quota")
def get_quota(x_session_id: str = Header(default="anonymous")) -> dict[str, int]:
    return {"remaining": quota.remaining(x_session_id), "free_runs": quota.FREE_RUNS}


class ImportRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2_000)


@app.post("/api/extract")
async def extract(file: Annotated[UploadFile, File()]) -> dict[str, str | int]:
    """PDF or text file in, plain text out. Nothing is written to disk."""
    blob = await file.read(ingest.MAX_UPLOAD_BYTES + 1)
    try:
        text = ingest.text_from_upload(file.filename or "", blob)
    except ingest.IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"text": text, "chars": len(text)}


@app.post("/api/import")
def import_posting(body: ImportRequest) -> dict[str, str | int]:
    """Fetch a public job ad by URL. Most big boards will refuse — that is expected."""
    try:
        text = ingest.fetch_posting(body.url)
    except ingest.IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"text": text, "chars": len(text)}


@app.post("/api/run")
def start_run(
    body: RunRequest, request: Request, x_session_id: str = Header(default="anonymous")
) -> StreamingResponse:
    # ponytail: the socket peer, not X-Forwarded-For — that header is client-set.
    # Behind a proxy, read it from the platform's trusted variant instead.
    ip = request.client.host if request.client else "unknown"
    try:
        left = quota.consume(x_session_id, ip)
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
        # Upstream text can carry keys, URLs and quota details: log it, do not echo it.
        ref = uuid.uuid4().hex[:8]
        log.error("llm call failed ref=%s: %s", ref, exc)
        yield _sse({"type": "error", "message": f"The model provider failed. Reference {ref}."})


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
