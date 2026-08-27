"""In-memory daily run quota, keyed by client id.

The cap is what makes a paid tier meaningful; it is deliberately simple so it can
be swapped for Redis without touching callers.
"""

from __future__ import annotations

import time
from collections import defaultdict

_DAY = 86_400


class QuotaExceeded(Exception):
    def __init__(self, limit: int, retry_after: int) -> None:
        super().__init__(f"free limit of {limit} runs/day reached")
        self.limit = limit
        self.retry_after = retry_after


class DailyQuota:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check_and_consume(self, client_id: str, now: float | None = None) -> int:
        now = time.time() if now is None else now
        window = [t for t in self._hits[client_id] if now - t < _DAY]
        if len(window) >= self.limit:
            retry_after = int(_DAY - (now - window[0])) + 1
            self._hits[client_id] = window
            raise QuotaExceeded(self.limit, retry_after)
        window.append(now)
        self._hits[client_id] = window
        return self.limit - len(window)
