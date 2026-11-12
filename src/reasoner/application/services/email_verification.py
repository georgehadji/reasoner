"""Email-verification gate (docs/plans/email-verification-2026-11-12.md, step 3).

Two features need a verified email: the FREE tier's monthly credit grant and
API key creation. Supabase "Confirm email" is off, so an unconfirmed address
signs in at once; without this gate a throwaway signup collects the free
credits.

An account passes when its email is verified, or when it was created before
``EMAIL_VERIFICATION_CUTOFF`` (grandfathered). Otherwise the access is counted
(``reasoner_unverified_access_total``) and, only in enforce mode, refused.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum

from reasoner.core.ports.metrics_port import count_unverified_access
from reasoner.domain.saas import User

logger = logging.getLogger(__name__)

ENFORCE = "enforce"


class GatedFeature(StrEnum):
    FREE_CREDITS = "free_credits"
    API_KEY_CREATE = "api_key_create"


def parse_cutoff(raw: str | None) -> datetime | None:
    """The grandfather cutoff, or None (nobody grandfathered).

    A value that does not parse grandfathers nobody and logs an error: failing
    open would exempt every account, which is the abuse this gate exists for.
    """
    if not raw:
        return None
    try:
        cutoff = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.error("EMAIL_VERIFICATION_CUTOFF=%r is not ISO-8601; nobody is grandfathered", raw)
        return None
    return cutoff if cutoff.tzinfo else cutoff.replace(tzinfo=UTC)


def _settings_defaults(mode: str | None, cutoff: datetime | None) -> tuple[str, datetime | None]:
    if mode is not None and cutoff is not None:
        return mode, cutoff
    from reasoner.core.settings import settings

    return (
        settings.EMAIL_VERIFICATION_MODE if mode is None else mode,
        parse_cutoff(settings.EMAIL_VERIFICATION_CUTOFF) if cutoff is None else cutoff,
    )


def gate_refuses(user: User, *, mode: str | None = None, cutoff: datetime | None = None) -> bool:
    """True when the gate would refuse *user* now. Counts nothing (a read for 402 bodies)."""
    if user.email_verified:
        return False
    mode, cutoff = _settings_defaults(mode, cutoff)
    if cutoff is not None and user.created_at < cutoff:
        return False
    return mode == ENFORCE


def email_gate_allows(
    user: User,
    feature: GatedFeature,
    *,
    mode: str | None = None,
    cutoff: datetime | None = None,
) -> bool:
    """True when *user* may use *feature*. Never raises.

    ``mode`` and ``cutoff`` default to the settings; tests pass them directly.
    """
    if user.email_verified:
        return True
    mode, cutoff = _settings_defaults(mode, cutoff)
    if cutoff is not None and user.created_at < cutoff:
        return True
    allowed = mode != ENFORCE
    count_unverified_access(feature.value, "allowed" if allowed else "denied")
    logger.info(
        "Unverified email reached %s for user %s (%s)",
        feature.value, user.id, "allowed" if allowed else "denied",
    )
    return allowed
