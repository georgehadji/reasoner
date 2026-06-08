"""Authentication and rate-limiting FastAPI dependencies."""

from __future__ import annotations

import hashlib
from typing import Optional

import logging

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from reasoner.auth import AuthenticationError, get_auth_manager
from reasoner.infrastructure.auth_legacy import AuthManager
from reasoner.api.client_ip import get_client_ip
from reasoner.api.csrf import verify_csrf_token

logger = logging.getLogger(__name__)
from reasoner.core.settings import settings
from reasoner.rate_limiter import RateLimitConfig, RateLimiter, get_rate_limiter
from reasoner.exceptions import RateLimitError

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

security = HTTPBearer(auto_error=False)

# ── Auth Manager Singleton (for auth_deps) ──
_auth_manager_instance_auth_deps: AuthManager | None = None

def _get_auth_manager_instance_auth_deps() -> AuthManager:
    """Factory for AuthManager instance within auth_deps."""
    global _auth_manager_instance_auth_deps
    if _auth_manager_instance_auth_deps is None:
        _auth_manager_instance_auth_deps = get_auth_manager()
    return _auth_manager_instance_auth_deps



async def get_client_id(request: Request) -> str:
    """Extract client ID from request (IP + User-Agent)."""
    ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    # SHA-256 with 16 hex chars (64-bit) to make collision-based bypass impractical
    return f"{ip}:{hashlib.sha256(user_agent.encode()).hexdigest()[:16]}"


async def check_rate_limit(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """
    Check rate limit for request.
    Raises HTTPException if rate limit exceeded.
    """
    rate_limiter = _get_rate_limiter_instance_auth_deps()
    client_id = await get_client_id(request)
    try:
        allowed, info = await rate_limiter.is_allowed(client_id)
    except RateLimitError:
        allowed = False
        info = {"limit_minute": 60, "remaining_minute": 0, "retry_after": 60}
    except Exception as exc:
        logger.exception("Rate limiter infrastructure failure")
        raise HTTPException(
            status_code=503,
            detail="Rate limiting unavailable",
        ) from exc

    # Add rate limit headers to response
    request.state.rate_limit_info = info

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "retry_after": int(info.get("retry_after", 60)),
                "limit_minute": info.get("limit_minute"),
                "remaining_minute": info.get("remaining_minute", 0),
            },
            headers={
                "Retry-After": str(int(info.get("retry_after", 60))),
                "X-RateLimit-Limit": str(info.get("limit_minute")),
                "X-RateLimit-Remaining": str(info.get("remaining_minute", 0)),
            },
        )

    return True


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Security(security)
):
    """
    Require valid API key authentication.
    Raises HTTPException if authentication fails.
    """
    auth_manager = _get_auth_manager_instance_auth_deps()
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        api_key = await auth_manager.authenticate(credentials.credentials)
        return api_key
    except AuthenticationError as e:
        # Return generic error to prevent information leakage (timing attack defense)
        raise HTTPException(
            status_code=401,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def optional_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False))
):
    """
    Optional authentication - returns API key if provided, None otherwise.
    """
    auth_manager = _get_auth_manager_instance_auth_deps()
    if not credentials:
        return None

    try:
        return await auth_manager.authenticate(credentials.credentials)
    except AuthenticationError as e:
        logger.warning("Invalid API key rejected in optional_auth: %s", e.message)
        return None


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
        )

    if not valid:
        raise HTTPException(
            status_code=403,
            detail="Invalid CSRF token.",
        )

    return True
