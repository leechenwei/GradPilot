"""Free-run cap per browser session.

# ponytail: in-process dict. It resets on redeploy, which is the correct trade
# for a free tier. Swap for Redis when a paid tier makes cheating worth money.
"""

from __future__ import annotations

import os
import threading

FREE_RUNS = int(os.getenv("GRADPILOT_FREE_RUNS", "5"))

_lock = threading.Lock()
_used: dict[str, int] = {}


class QuotaExceeded(Exception):
    pass


def consume(session: str) -> int:
    """Count one run against the session. Return the runs left after it."""
    with _lock:
        used = _used.get(session, 0)
        if used >= FREE_RUNS:
            raise QuotaExceeded(f"{FREE_RUNS} free runs used")
        _used[session] = used + 1
        return FREE_RUNS - used - 1


def remaining(session: str) -> int:
    with _lock:
        return max(0, FREE_RUNS - _used.get(session, 0))


def reset() -> None:
    """Test hook."""
    with _lock:
        _used.clear()
