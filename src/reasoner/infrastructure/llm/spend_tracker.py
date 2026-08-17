"""In-process monthly LLM spend tracker.

Backs the monthly half of the tier spend ceilings. Keyed by billing subject
(the user id), so a user cannot reset their month by starting a new
conversation.

⚠️ Volatile and per-worker: totals reset on restart and are not shared
across uvicorn workers, so the effective ceiling is roughly
`monthly_usd × worker_count`. That is a deliberate MVP tradeoff — it stops
the runaway-user case, which is what the ceiling exists for. Durable
enforcement needs a shared counter (Redis INCRBYFLOAT keyed by
`spend:{subject}:{period}`, or a column on `usage_quotas`); this module is
the seam to swap it in behind.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

# {(subject, period): total_usd} — period scopes the entry to a calendar
# month so old entries stop counting without a sweep job.
_SPEND: dict[tuple[str, str], float] = {}
_LOCK = threading.Lock()


def current_period() -> str:
    """Current billing period as YYYY-MM, in UTC."""
    return datetime.now(UTC).strftime("%Y-%m")


def record(subject: str, cost_usd: float) -> float:
    """Add a cost to the subject's running total and return the new total."""
    if not subject or cost_usd <= 0:
        return get(subject)
    key = (subject, current_period())
    with _LOCK:
        total = _SPEND.get(key, 0.0) + cost_usd
        _SPEND[key] = total
        return total


def get(subject: str) -> float:
    """Current period-to-date spend for a subject."""
    if not subject:
        return 0.0
    with _LOCK:
        return _SPEND.get((subject, current_period()), 0.0)


def reset(subject: str | None = None) -> None:
    """Clear tracked spend — for one subject, or all of it when None."""
    with _LOCK:
        if subject is None:
            _SPEND.clear()
            return
        period = current_period()
        _SPEND.pop((subject, period), None)


__all__ = ["current_period", "record", "get", "reset"]
