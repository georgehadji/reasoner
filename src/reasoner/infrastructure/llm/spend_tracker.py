"""In-process monthly LLM spend tracker.

Backs the monthly half of the tier spend ceilings. Keyed by billing subject
(the user id), so a user cannot reset their month by starting a new
conversation.

`record_shared` is the cross-worker path: a Valkey INCRBYFLOAT keyed by
`spend:{subject}:{period}` (~40-day TTL), mirrored into the in-process dict so
the synchronous `get` used by the admission gate stays warm. When Valkey is
unavailable it falls back to the in-process dict, which is volatile and
per-worker (ceiling then roughly `monthly_usd x worker_count`).
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

# {(subject, period): total_usd} — period scopes the entry to a calendar
# month so old entries stop counting without a sweep job.
_SPEND: dict[tuple[str, str], float] = {}
_LOCK = threading.Lock()
_TTL_SECONDS = 40 * 86400
logger = logging.getLogger(__name__)


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


async def record_shared(subject: str, cost_usd: float) -> float:
    """`record`, but counted across workers through Valkey; falls back to local."""
    if not subject or cost_usd <= 0:
        return get(subject)
    period = current_period()
    key = f"spend:{subject}:{period}"
    try:
        from reasoner.infrastructure.valkey.client import get_valkey_pool
        from reasoner.infrastructure.valkey.guarded import get_guarded_valkey

        valkey = get_guarded_valkey(get_valkey_pool())
        total = float(await valkey.run(lambda: valkey.client.incrbyfloat(key, cost_usd)))
        await valkey.expire(key, _TTL_SECONDS)
    except Exception as exc:
        logger.warning("Shared spend counter unavailable, using local: %s", exc)
        return record(subject, cost_usd)
    with _LOCK:
        _SPEND[(subject, period)] = max(_SPEND.get((subject, period), 0.0), total)
    return total


async def refresh(subject: str) -> float:
    """Pull the shared Valkey total into the local dict before a sync `get`.

    The admission gate is synchronous, so callers that can await refresh first
    and the gate then sees spend recorded by other workers.
    """
    if not subject:
        return 0.0
    period = current_period()
    try:
        from reasoner.infrastructure.valkey.client import get_valkey_pool
        from reasoner.infrastructure.valkey.guarded import get_guarded_valkey

        valkey = get_guarded_valkey(get_valkey_pool())
        raw = await valkey.run(lambda: valkey.client.get(f"spend:{subject}:{period}"))
    except Exception as exc:
        logger.warning("Shared spend counter unavailable, using local: %s", exc)
        return get(subject)
    if raw is not None:
        with _LOCK:
            _SPEND[(subject, period)] = max(_SPEND.get((subject, period), 0.0), float(raw))
    return get(subject)


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


__all__ = ["current_period", "record", "record_shared", "refresh", "get", "reset"]
