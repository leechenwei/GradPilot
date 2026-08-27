"""toyyibPay checkout.

Chosen because an individual can register without an SSM company, it carries FPX
plus selected e-wallets, and a bill is two HTTP calls. Everything here is inert
until TOYYIBPAY_SECRET and TOYYIBPAY_CATEGORY are set.
"""

from __future__ import annotations

import os

import httpx

TIMEOUT = 20.0
PACKAGE_RUNS = 20
PACKAGE_PRICE_SEN = 1000  # RM 10.00, priced in sen like the API wants


class PaymentError(RuntimeError):
    pass


def _base() -> str:
    return "https://dev.toyyibpay.com" if os.getenv("TOYYIBPAY_SANDBOX") else "https://toyyibpay.com"


def configured() -> bool:
    return bool(os.getenv("TOYYIBPAY_SECRET") and os.getenv("TOYYIBPAY_CATEGORY"))


def create_bill(session: str, return_url: str, callback_url: str) -> str:
    """Return the hosted payment URL for one 20-run package."""
    if not configured():
        raise PaymentError("Payments are not configured on this server.")
    payload = {
        "userSecretKey": os.environ["TOYYIBPAY_SECRET"],
        "categoryCode": os.environ["TOYYIBPAY_CATEGORY"],
        "billName": "GradPilot 20 runs",
        "billDescription": f"{PACKAGE_RUNS} tailoring runs",
        "billPriceSetting": 1,
        "billPayorInfo": 0,
        "billAmount": PACKAGE_PRICE_SEN,
        "billReturnUrl": return_url,
        "billCallbackUrl": callback_url,
        # The session is the only thing tying a payment back to a browser.
        "billExternalReferenceNo": session,
        "billTo": "",
        "billEmail": "",
        "billPhone": "",
    }
    data = _post("/index.php/api/createBill", payload)
    try:
        code = data[0]["BillCode"]
    except (KeyError, IndexError, TypeError) as exc:
        raise PaymentError(f"toyyibPay rejected the bill: {data}") from exc
    return f"{_base()}/{code}"


def verify(bill_code: str) -> tuple[bool, str]:
    """Ask toyyibPay directly whether the bill is paid.

    The callback POST is attacker-forgeable, so it is only a nudge to call this.
    Returns (paid, session).
    """
    rows = _post("/index.php/api/getBillTransactions", {"billCode": bill_code})
    if not rows:
        raise PaymentError("unknown bill")
    row = rows[0]
    paid = str(row.get("billpaymentStatus")) == "1"
    amount = float(str(row.get("billpaymentAmount") or 0))
    if paid and round(amount * 100) < PACKAGE_PRICE_SEN:
        raise PaymentError("amount paid is short of the package price")
    return paid, str(row.get("billExternalReferenceNo") or "")


def _post(path: str, payload: dict[str, object]) -> list[dict[str, object]]:
    try:
        response = httpx.post(_base() + path, data=payload, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise PaymentError("toyyibPay could not be reached") from exc
    if response.status_code >= 400:
        raise PaymentError(f"toyyibPay said {response.status_code}")
    try:
        body = response.json()
    except ValueError as exc:
        raise PaymentError("toyyibPay returned a non-JSON body") from exc
    return body if isinstance(body, list) else [body]
