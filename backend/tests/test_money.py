"""Anything that touches money or a user's API key gets a test."""

import uuid

import pytest
from fastapi.testclient import TestClient

from app import credits, payments, quota
from app.main import app

BODY = {
    "posting": "Junior AI Engineer. We need Python, FastAPI and SQL. Small team, ships weekly.",
    "cv": "Chen Wei, CS graduate. Built a Python REST API for a campus club. Coursework in SQL.",
}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("GRADPILOT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GRADPILOT_ALLOW_MOCK", "1")
    quota.reset()
    monkeypatch.setattr(credits, "store", credits.MemoryStore())


def session() -> dict[str, str]:
    return {"X-Session-Id": str(uuid.uuid4())}


def drain(client: TestClient, headers: dict[str, str]) -> None:
    for _ in range(quota.FREE_RUNS):
        assert client.post("/api/run", json=BODY, headers=headers).status_code == 200


def test_a_users_own_key_skips_the_free_cap():
    client = TestClient(app)
    headers = session()
    drain(client, headers)
    assert client.post("/api/run", json=BODY, headers=headers).status_code == 429
    byok = {**headers, "X-LLM-Provider": "openai", "X-LLM-Key": "sk-" + "x" * 40}
    assert client.post("/api/run", json=BODY, headers=byok).status_code == 200


def test_a_junk_key_or_provider_is_refused_before_any_call():
    client = TestClient(app)
    bad_provider = {**session(), "X-LLM-Provider": "definitely-not", "X-LLM-Key": "x" * 40}
    assert client.post("/api/run", json=BODY, headers=bad_provider).status_code == 400
    short_key = {**session(), "X-LLM-Provider": "openai", "X-LLM-Key": "abc"}
    assert client.post("/api/run", json=BODY, headers=short_key).status_code == 400


def test_credits_take_over_when_the_free_runs_are_gone():
    client = TestClient(app)
    headers = session()
    drain(client, headers)
    assert client.post("/api/run", json=BODY, headers=headers).status_code == 429
    credits.store.add(headers["X-Session-Id"], 2)
    assert client.post("/api/run", json=BODY, headers=headers).status_code == 200
    assert credits.store.balance(headers["X-Session-Id"]) == 1


def test_checkout_refuses_while_the_store_is_not_durable():
    """A memory store loses paid balances on redeploy, so selling must be off."""
    client = TestClient(app)
    assert credits.is_durable() is False
    assert client.post("/api/checkout", headers=session()).status_code == 503


def test_callback_grants_only_what_toyyibpay_itself_confirms(monkeypatch):
    client = TestClient(app)
    buyer = str(uuid.uuid4())
    monkeypatch.setattr(payments, "verify", lambda code: (True, buyer))
    assert client.post("/api/payment/callback", data={"billcode": "abc123"}).json() == {
        "status": "granted"
    }
    assert credits.store.balance(buyer) == payments.PACKAGE_RUNS


def test_a_replayed_callback_grants_credits_once(monkeypatch):
    client = TestClient(app)
    buyer = str(uuid.uuid4())
    monkeypatch.setattr(payments, "verify", lambda code: (True, buyer))
    for _ in range(3):
        client.post("/api/payment/callback", data={"billcode": "abc123"})
    assert credits.store.balance(buyer) == payments.PACKAGE_RUNS


def test_an_unpaid_bill_grants_nothing(monkeypatch):
    client = TestClient(app)
    buyer = str(uuid.uuid4())
    monkeypatch.setattr(payments, "verify", lambda code: (False, buyer))
    assert client.post("/api/payment/callback", data={"billcode": "nope"}).json() == {
        "status": "ignored"
    }
    assert credits.store.balance(buyer) == 0


def test_underpayment_is_rejected_by_the_verifier(monkeypatch):
    """Bill prices are client-visible; a short payment must not buy a package."""
    monkeypatch.setattr(
        payments, "_post",
        lambda path, payload: [
            {"billpaymentStatus": "1", "billpaymentAmount": "1.00", "billExternalReferenceNo": "s"}
        ],
    )
    with pytest.raises(payments.PaymentError, match="short"):
        payments.verify("abc123")


def test_without_a_model_the_run_is_refused_rather_than_faked(monkeypatch):
    """Mock text must never reach a user who thinks it was written for them."""
    monkeypatch.delenv("GRADPILOT_ALLOW_MOCK", raising=False)
    client = TestClient(app)
    response = client.post("/api/run", json=BODY, headers=session())
    assert response.status_code == 412
    assert "api key" in response.json()["detail"].lower()


def test_a_users_own_key_still_runs_when_the_server_has_no_model(monkeypatch):
    monkeypatch.delenv("GRADPILOT_ALLOW_MOCK", raising=False)
    client = TestClient(app)
    headers = {**session(), "X-LLM-Provider": "openai", "X-LLM-Key": "sk-" + "x" * 40}
    # The call itself fails on a fake key, but it is a real attempt, not canned text.
    assert client.post("/api/run", json=BODY, headers=headers).status_code == 200


def test_openrouter_is_an_accepted_provider_with_a_model_override():
    from app.main import _creds

    creds = _creds("openrouter", "sk-or-v1-" + "b" * 40, "minimax/minimax-m3:free")
    assert creds is not None
    assert (creds.provider, creds.model) == ("openrouter", "minimax/minimax-m3:free")


def test_a_model_name_with_odd_characters_is_refused():
    from fastapi import HTTPException

    from app.main import _creds

    with pytest.raises(HTTPException):
        _creds("openrouter", "sk-or-v1-" + "b" * 40, "model; rm -rf /")


def test_json_wrapped_in_chatter_is_still_parsed():
    """Free models often answer 'Sure! {...}'. Take the object, do not fail the run."""
    from app.llm import _parse

    assert _parse('Sure, here you go:\n{"score": 0.9, "notes": []}\nHope that helps!') == {
        "score": 0.9,
        "notes": [],
    }


def test_a_provider_error_object_is_reported_not_crashed():
    """A missing 'choices' used to raise KeyError, which reads as our bug, not theirs."""
    from app.llm import LLMError, _dig

    with pytest.raises(LLMError, match="unexpected reply"):
        _dig({"error": {"message": "rate limited"}}, "choices", 0, "message", "content")


def test_an_empty_completion_is_an_error_not_empty_output():
    from app.llm import LLMError, _dig

    with pytest.raises(LLMError, match="no text"):
        _dig({"choices": [{"message": {"content": "   "}}]}, "choices", 0, "message", "content")


def test_json_wrapped_in_a_one_item_array_is_unwrapped():
    from app.llm import _parse

    assert _parse('[{"score": 0.8, "notes": []}]') == {"score": 0.8, "notes": []}
