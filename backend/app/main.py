from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import credits, ingest, payments, quota
from app.graph import run
from app.llm import PROVIDERS, Creds, LLMError, provider

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
    return {"status": "ok", "provider": provider(), "model_ready": str(model_ready()).lower()}


@app.get("/api/quota")
def get_quota(x_session_id: str = Header(default="anonymous")) -> dict[str, object]:
    return {
        "remaining": quota.remaining(x_session_id),
        "free_runs": quota.FREE_RUNS,
        "credits": credits.store.balance(x_session_id),
        "package": {"runs": payments.PACKAGE_RUNS, "price": "RM10"},
        "can_buy": payments.configured() and credits.is_durable(),
        "model_ready": model_ready(),
    }


def _mock_allowed() -> bool:
    """Mock replies exist for tests and local work, never for a user's real application."""
    return os.getenv("GRADPILOT_ALLOW_MOCK") == "1"


def model_ready() -> bool:
    return provider() != "mock" or _mock_allowed()


def _creds(header_provider: str, header_key: str, header_model: str = "") -> Creds | None:
    """A key the user pasted. Validated, used for this request, never stored or logged."""
    key = header_key.strip()
    if not key:
        return None
    name = (header_provider or "openai").strip().lower()
    if name not in PROVIDERS:
        raise HTTPException(
            status_code=400, detail=f"Provider must be one of {', '.join(PROVIDERS)}."
        )
    if not 20 <= len(key) <= 200:
        raise HTTPException(status_code=400, detail="That does not look like an API key.")
    model = header_model.strip()[:100]
    if model and not re.fullmatch(r"[\w./:-]+", model):
        raise HTTPException(status_code=400, detail="That model name has odd characters.")
    return Creds(provider=name, key=key, model=model)


@app.post("/api/checkout")
def checkout(request: Request, x_session_id: str = Header(default="anonymous")) -> dict[str, str]:
    """Create a toyyibPay bill for one run package and hand back its payment page."""
    if not credits.is_durable():
        # Selling credits that a redeploy erases is worse than not selling any.
        raise HTTPException(status_code=503, detail="Payments are off: no credit store configured.")
    api = os.getenv("PUBLIC_API_URL") or str(request.base_url).rstrip("/")
    app_url = os.getenv("PUBLIC_APP_URL") or api
    try:
        url = payments.create_bill(
            session=x_session_id,
            return_url=f"{app_url}/#paid",
            callback_url=f"{api}/api/payment/callback",
        )
    except payments.PaymentError as exc:
        log.error("checkout failed: %s", exc)
        raise HTTPException(status_code=502, detail="Could not start the payment.") from exc
    return {"url": url}


@app.post("/api/payment/callback")
def payment_callback(
    billcode: str = Form(default=""), refno: str = Form(default="")
) -> dict[str, str]:
    """toyyibPay pings this. The POST is forgeable, so ask toyyibPay itself before granting."""
    code = (billcode or refno).strip()
    if not code:
        raise HTTPException(status_code=400, detail="missing billcode")
    try:
        paid, session = payments.verify(code)
    except payments.PaymentError as exc:
        log.error("verify failed for %s: %s", code, exc)
        raise HTTPException(status_code=502, detail="could not verify") from exc
    if not paid or not session:
        return {"status": "ignored"}
    marker = f"bill:{code}"
    if credits.store.balance(marker):
        return {"status": "already granted"}  # toyyibPay retries; grant once
    credits.store.add(marker, 1)
    credits.store.add(session, payments.PACKAGE_RUNS)
    return {"status": "granted"}


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
    body: RunRequest,
    request: Request,
    x_session_id: str = Header(default="anonymous"),
    x_llm_provider: str = Header(default=""),
    x_llm_key: str = Header(default=""),
    x_llm_model: str = Header(default=""),
) -> StreamingResponse:
    # ponytail: the socket peer, not X-Forwarded-For — that header is client-set.
    # Behind a proxy, read it from the platform's trusted variant instead.
    ip = request.client.host if request.client else "unknown"
    creds = _creds(x_llm_provider, x_llm_key, x_llm_model)
    if not creds and not model_ready():
        # Canned text dressed up as a tailored application would be worse than nothing:
        # someone could send it to a real employer. Refuse instead.
        raise HTTPException(
            status_code=412,
            detail=(
                "No model is configured on this server, so nothing can be written for you. "
                "Add your own API key to run."
            ),
        )
    if creds:
        left = -1  # their key, their bill: the free cap does not apply
    else:
        try:
            left = quota.consume(x_session_id, ip)
        except quota.QuotaExceeded as exc:
            try:
                left = credits.store.spend(x_session_id)
            except credits.CreditError:
                raise HTTPException(status_code=429, detail=str(exc)) from exc
    return StreamingResponse(
        _stream(body, left, creds),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream(body: RunRequest, left: int, creds: Creds | None = None) -> Iterator[str]:
    try:
        for event in run(body.posting, body.cv, creds):
            if event["type"] == "done":
                event["result"]["runs_left"] = left
            yield _sse(event)
    except LLMError as exc:
        # The client already has a 200 and half a stream, so the error must ride the stream.
        # Upstream text can carry keys, URLs and quota details: log it, do not echo it.
        ref = uuid.uuid4().hex[:8]
        log.error("llm call failed ref=%s byok=%s: %s", ref, bool(creds), exc)
        if creds:
            fallback = (
                "clear it to use the free runs"
                if model_ready()
                else "try another key or model"
            )
            detail = (
                f"The {creds.provider} call failed: the key was rejected, the account has no "
                f"credit, or that free model is busy. Check the key, or {fallback}."
            )
        else:
            detail = f"The model provider failed. Reference {ref}."
        yield _sse({"type": "error", "message": detail})


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
