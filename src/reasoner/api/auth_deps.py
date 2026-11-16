"""Authentication and rate-limiting FastAPI dependencies."""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from reasoner.api.csrf import verify_csrf_token
from reasoner.domain.api_keys import looks_like_api_key

logger = logging.getLogger(__name__)
from reasoner.core.settings import settings
from reasoner.rate_limiter import RateLimitConfig, RateLimiter, get_rate_limiter

# ── Rate Limiter Singleton (for auth_deps) ──
_rate_limiter_instance_auth_deps: RateLimiter | None = None

def _get_rate_limiter_instance_auth_deps() -> RateLimiter:
    """Factory for RateLimiter instance within auth_deps."""
    global _rate_limiter_instance_auth_deps
    if _rate_limiter_instance_auth_deps is None:
        _rate_limiter_instance_auth_deps = get_rate_limiter(
            RateLimitConfig(
                requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
                requests_per_hour=settings.RATE_LIMIT_PER_HOUR,
                burst_size=settings.RATE_LIMIT_BURST,
            )
        )
    return _rate_limiter_instance_auth_deps

async def _is_authenticated_api_key_request(request: Request) -> bool:
    """Whether this request presents a valid Reasoner API key.

    Used to exempt programmatic callers from CSRF. CSRF defends against a
    browser replaying ambient credentials from an attacker's page; a page
    cannot attach a victim's secret API key to an Authorization header, so the
    threat CSRF addresses does not exist on this path. The key must actually
    authenticate — an unverified `rsn_`-shaped string is not enough, or the
    exemption itself would become the bypass.
    """
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith("bearer "):
        return False

    token = header[7:].strip()
    if not looks_like_api_key(token):
        return False

    # Already resolved by an auth dependency earlier in the chain.
    if getattr(request.state, "auth_method", None) == "api_key":
        return True

    try:
        from reasoner.api.dependencies import _get_api_key_service
        return await _get_api_key_service().authenticate(token) is not None
    except Exception as exc:
        logger.warning("API key CSRF exemption check failed: %s", exc)
        return False


async def require_csrf(request: Request):
    """
    Require a valid CSRF token on state-changing requests.

    Reads the X-CSRF-Token header and validates its HMAC signature.
    Raises HTTPException(403) if missing, invalid, or if CSRF is
    misconfigured (no secret set).

    Can be disabled globally via CSRF_ENFORCE_BACKEND=false.
    """
    if not settings.CSRF_ENFORCE_BACKEND:
        return True

    if await _is_authenticated_api_key_request(request):
        return True

    token = request.headers.get("X-CSRF-Token")
    if not token:
        raise HTTPException(
            status_code=403,
            detail="Missing CSRF token. Include X-CSRF-Token header.",
        )

    try:
        valid = verify_csrf_token(token)
    except RuntimeError as e:
        logger.error("CSRF verification misconfigured: %s", e)
        raise HTTPException(
            status_code=500,
            detail="CSRF protection misconfigured on server.",
        ) from e

    if not valid:
        raise HTTPException(
            status_code=403,
            detail="Invalid CSRF token.",
        )

    return True
