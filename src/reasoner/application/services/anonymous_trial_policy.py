"""Anonymous trial spend cap.

Anonymous runs (``/api/run`` with ``ENABLE_LEGACY_API_KEY=true``, no account)
skip the per-user credit ledger entirely by design -- ``run_metering.metered()``
never settles against a ``user_id=None`` context, because there's no account
to charge. That's correct, but without a separate check it also means
anonymous traffic is unmetered *and* uncapped beyond generic per-IP rate
limiting: nothing bounds how much real provider spend one address can trigger
in a day.

This reuses the same Valkey pool the rate limiter already depends on
(``infrastructure/valkey/client.py``) rather than introducing new storage --
a plain per-IP, per-UTC-day counter incremented by the *estimated* credit
cost at the same point a real reservation would fire for an authenticated
caller.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_KEY_PREFIX = "anon_spend"
_WINDOW_TTL_SECONDS = 86_400


def _daily_key(client_ip: str) -> str:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"{_KEY_PREFIX}:{client_ip}:{day}"


async def enforce_anonymous_trial_cap(client_ip: str, estimated_cost_usd: float) -> None:
    """Raise 429 once an anonymous caller's estimated daily spend would
    exceed ``settings.ANONYMOUS_DAILY_CREDIT_CAP``.

    Fails *open* (log + allow) when Valkey is unreachable: unlike the credit
    ledger, there's no real money at risk here for the business to lose --
    only bounded abuse-cost exposure, and the daily window resets on its own
    once the backend recovers.
    """
    from reasoner.core.settings import settings
    from reasoner.domain.credits import usd_to_credits
    from reasoner.infrastructure.valkey.client import get_valkey_pool

    estimated_credits = usd_to_credits(estimated_cost_usd)
    if estimated_credits <= 0:
        return

    key = _daily_key(client_ip)
    try:
        client = get_valkey_pool()
        spent = await client.incrby(key, estimated_credits)
        await client.expire(key, _WINDOW_TTL_SECONDS)
    except Exception as exc:
        logger.warning("Anonymous trial cap check failed (Valkey unreachable); allowing: %s", exc)
        return

    if spent > settings.ANONYMOUS_DAILY_CREDIT_CAP:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Anonymous trial limit reached",
                "message": (
                    "Free trial usage for this address is exhausted for today. "
                    "Sign in for a full account."
                ),
                "retry_after": _WINDOW_TTL_SECONDS,
            },
            headers={"Retry-After": str(_WINDOW_TTL_SECONDS)},
        )


__all__ = ["enforce_anonymous_trial_cap"]
