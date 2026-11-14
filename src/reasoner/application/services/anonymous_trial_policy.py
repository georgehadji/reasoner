"""Anonymous trial spend cap.

Anonymous runs (``/api/run`` with ``ALLOW_ANONYMOUS_RUNS=true``, no account)
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
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from fastapi import HTTPException

from reasoner.core.state_machine import Machine

logger = logging.getLogger(__name__)


class AnonTrialState(StrEnum):
    """Where one ``anon_spend:{ip}:{day}`` counter is in its day (SM-M5)."""

    ABSENT = "absent"  # no key yet today
    COUNTING = "counting"  # key exists with a TTL, under the cap
    OVER_CAP = "over_cap"  # the request that crossed the cap is refunded back to COUNTING
    EXPIRED = "expired"  # the day's TTL ran out: the key is gone, a new day starts a new key


ANON_TRIAL_MACHINE = Machine(
    "anon_trial",
    {
        AnonTrialState.ABSENT: {AnonTrialState.COUNTING},
        AnonTrialState.COUNTING: {
            AnonTrialState.COUNTING,
            AnonTrialState.OVER_CAP,
            AnonTrialState.EXPIRED,
        },
        AnonTrialState.OVER_CAP: {AnonTrialState.COUNTING, AnonTrialState.EXPIRED},
        AnonTrialState.EXPIRED: set(),
    },
    initial=AnonTrialState.ABSENT,
)

_KEY_PREFIX = "anon_spend"
_WINDOW_TTL_SECONDS = 86_400

# Atomic refund: touches the key only while it exists (so it can never create one),
# floors at zero, and keeps the TTL. exists-then-decrby across midnight left a
# negative key with no TTL.
_REFUND_LUA = (
    "local v = tonumber(redis.call('GET', KEYS[1])) "
    "if not v then return -1 end "
    "v = v - tonumber(ARGV[1]) "
    "if v < 0 then v = 0 end "
    "redis.call('SET', KEYS[1], v, 'KEEPTTL') "
    "return v"
)


def _daily_key(client_ip: str) -> str:
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    return f"{_KEY_PREFIX}:{client_ip}:{day}"


@dataclass(frozen=True)
class AnonymousTrialCharge:
    """Credits counted against an address today, so a refusal can take them back.

    Carries the key, not the address: a refund after midnight must hit the day it
    was counted on, not a fresh counter.
    """

    key: str
    credits: int


async def enforce_anonymous_trial_cap(
    client_ip: str, estimated_cost_usd: float
) -> AnonymousTrialCharge | None:
    """Raise 429 once an anonymous caller's estimated daily spend would
    exceed ``settings.ANONYMOUS_DAILY_CREDIT_CAP``.

    Returns the credits counted, for :func:`refund_anonymous_trial`, or None when
    nothing was counted (a zero estimate, or Valkey down).

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
        return None

    key = _daily_key(client_ip)
    try:
        client = get_valkey_pool()
        # Create the key with its TTL in one atomic command, then count. INCRBY then
        # EXPIRE left a counter with no TTL when the process died between them, which
        # blocked that address until someone deleted the key by hand.
        await client.set(key, 0, ex=_WINDOW_TTL_SECONDS, nx=True)
        spent = await client.incrby(key, estimated_credits)
    except Exception as exc:
        logger.warning("Anonymous trial cap check failed (Valkey unreachable); allowing: %s", exc)
        return None

    charge = AnonymousTrialCharge(key=key, credits=estimated_credits)
    if spent > settings.ANONYMOUS_DAILY_CREDIT_CAP:
        ANON_TRIAL_MACHINE.move(AnonTrialState.COUNTING, AnonTrialState.OVER_CAP)
        # A refused run spent nothing: take back what this attempt counted.
        await refund_anonymous_trial(charge)
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
    return charge


async def refund_anonymous_trial(charge: AnonymousTrialCharge | None) -> None:
    """Take back credits counted for a run that was refused or never started.

    Never raises. One Lua script, so a counter that expires mid-refund (midnight
    UTC) is skipped rather than recreated negative with no TTL.
    """
    if charge is None:
        return
    from reasoner.infrastructure.valkey.client import get_valkey_pool

    try:
        client = get_valkey_pool()
        left = await client.eval(_REFUND_LUA, 1, charge.key, charge.credits)
        ANON_TRIAL_MACHINE.move(
            AnonTrialState.COUNTING,
            AnonTrialState.EXPIRED if int(left) < 0 else AnonTrialState.COUNTING,
        )
    except Exception as exc:
        logger.warning("Anonymous trial refund failed; the credits stay counted: %s", exc)


__all__ = ["AnonymousTrialCharge", "enforce_anonymous_trial_cap", "refund_anonymous_trial"]
