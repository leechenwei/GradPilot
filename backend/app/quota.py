"""Free-run cap.

The browser sends its own session id, so it is a UX affordance, not an identity:
clearing storage buys a fresh allowance. A per-IP daily bucket is the real
backstop. Neither is auth — see docs/PROJECT-NOTES.md for the real fix (signup).

# ponytail: in-process dict, bounded and self-expiring by day key. It resets on
# redeploy, which is the correct trade for a free tier. Move to Redis when a paid
# tier makes cheating worth money.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from collections import OrderedDict

FREE_RUNS = int(os.getenv("GRADPILOT_FREE_RUNS", "5"))
IP_RUNS_PER_DAY = int(os.getenv("GRADPILOT_IP_RUNS_PER_DAY", "25"))
MAX_KEYS = 50_000  # bound the map: the session id is attacker-supplied

_UUID = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.I)

_lock = threading.Lock()
_used: OrderedDict[str, int] = OrderedDict()


class QuotaExceeded(Exception):
    pass


def _key(kind: str, raw: str) -> str:
    """Hash the input and stamp the day, so yesterday's buckets age out of the LRU."""
    if kind == "s" and not _UUID.match(raw or ""):
        raw = "malformed"  # every junk header shares one bucket
    digest = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]
    return f"{kind}:{int(time.time() // 86_400)}:{digest}"


def _bump(key: str) -> None:
    _used[key] = _used.get(key, 0) + 1
    _used.move_to_end(key)
    while len(_used) > MAX_KEYS:
        _used.popitem(last=False)


def consume(session: str, ip: str) -> int:
    """Count one run against the session and the IP. Return the session runs left."""
    session_key, ip_key = _key("s", session), _key("ip", ip)
    with _lock:
        if _used.get(session_key, 0) >= FREE_RUNS:
            raise QuotaExceeded(f"{FREE_RUNS} free runs used")
        if _used.get(ip_key, 0) >= IP_RUNS_PER_DAY:
            raise QuotaExceeded("daily limit reached for this network")
        _bump(session_key)
        _bump(ip_key)
        return FREE_RUNS - _used[session_key]


def remaining(session: str) -> int:
    with _lock:
        return max(0, FREE_RUNS - _used.get(_key("s", session), 0))


def reset() -> None:
    """Test hook."""
    with _lock:
        _used.clear()
