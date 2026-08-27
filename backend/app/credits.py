"""Paid run credits.

Money outlives a deploy, so the balance cannot live in this process. Set
SUPABASE_URL and SUPABASE_SERVICE_KEY and it goes to Postgres; without them it
falls back to memory, which is fine for local work and WRONG for real payments.
Table: credits(session text primary key, balance int, updated_at timestamptz).
"""

from __future__ import annotations

import os
import threading

import httpx

TIMEOUT = 10.0


class CreditError(RuntimeError):
    pass


class MemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rows: dict[str, int] = {}

    def balance(self, session: str) -> int:
        with self._lock:
            return self._rows.get(session, 0)

    def add(self, session: str, amount: int) -> int:
        with self._lock:
            self._rows[session] = self._rows.get(session, 0) + amount
            return self._rows[session]

    def spend(self, session: str) -> int:
        with self._lock:
            left = self._rows.get(session, 0)
            if left <= 0:
                raise CreditError("no credits")
            self._rows[session] = left - 1
            return left - 1


class SupabaseStore:
    """Thin PostgREST client.

    # ponytail: read-modify-write, so two runs racing the same session can both
    # read the same balance. Move to an `rpc/spend_credit` SQL function if a user
    # ever double-spends; at one run per click it is not worth the migration yet.
    """

    def __init__(self, url: str, key: str) -> None:
        self._url = url.rstrip("/") + "/rest/v1/credits"
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _request(self, method: str, **kwargs: object) -> list[dict[str, object]]:
        try:
            response = httpx.request(
                method, self._url, headers=self._headers, timeout=TIMEOUT, **kwargs  # type: ignore[arg-type]
            )
        except httpx.HTTPError as exc:
            raise CreditError("credit store unreachable") from exc
        if response.status_code >= 400:
            raise CreditError(f"credit store said {response.status_code}")
        return response.json() if response.content else []

    def balance(self, session: str) -> int:
        rows = self._request("GET", params={"session": f"eq.{session}", "select": "balance"})
        return int(str(rows[0]["balance"])) if rows else 0

    def add(self, session: str, amount: int) -> int:
        total = self.balance(session) + amount
        self._request(
            "POST",
            headers={
                **self._headers,
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
            json={"session": session, "balance": total},
        )
        return total

    def spend(self, session: str) -> int:
        left = self.balance(session)
        if left <= 0:
            raise CreditError("no credits")
        self._request("PATCH", params={"session": f"eq.{session}"}, json={"balance": left - 1})
        return left - 1


def _build() -> MemoryStore | SupabaseStore:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY")
    return SupabaseStore(url, key) if url and key else MemoryStore()


store: MemoryStore | SupabaseStore = _build()


def is_durable() -> bool:
    """False means a redeploy wipes paid balances. Checkout refuses in that state."""
    return isinstance(store, SupabaseStore)
