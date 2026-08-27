from __future__ import annotations

import pytest

from app.quota import DailyQuota, QuotaExceeded


def test_quota_counts_down_per_client() -> None:
    quota = DailyQuota(limit=3)
    assert quota.check_and_consume("a", now=0) == 2
    assert quota.check_and_consume("a", now=1) == 1
    assert quota.check_and_consume("b", now=1) == 2


def test_quota_raises_when_exhausted() -> None:
    quota = DailyQuota(limit=1)
    quota.check_and_consume("a", now=0)
    with pytest.raises(QuotaExceeded) as exc:
        quota.check_and_consume("a", now=10)
    assert exc.value.limit == 1
    assert exc.value.retry_after > 0


def test_quota_window_rolls_over_after_a_day() -> None:
    quota = DailyQuota(limit=1)
    quota.check_and_consume("a", now=0)
    assert quota.check_and_consume("a", now=86_401) == 0
