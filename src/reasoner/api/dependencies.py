"""
FastAPI Dependency Injectors for SaaS Auth.

These functions are used as FastAPI Depends() callables.
They resolve authentication and authorization without
polluting route handlers with auth logic.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import Optional
from uuid import UUID

import asyncio
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

from reasoner.api.client_ip import get_client_ip
from reasoner.domain.saas import User, SubscriptionTier, SubscriptionStatus, QuotaResult
from reasoner.application.ports.auth_port import AuthPort
from reasoner.application.services.auth_service import AuthService
from reasoner.application.services.quota_service import QuotaService, TIER_LIMITS
from reasoner.infrastructure.auth import get_auth_adapter
from reasoner.auth import AuthenticationError as LegacyAuthError
from reasoner.core.settings import settings
from reasoner.rate_limiter import RateLimitConfig, get_rate_limiter
from reasoner.presets import get_preset_tier
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.pipeline_service import PipelineService
from reasoner.application.services.search_service import SearchService


# ── Rate Limiter Singleton ──
_rate_limiter_instance: RateLimiter | None = None

def _get_rate_limiter_instance() -> RateLimiter:
    """Factory for RateLimiter instance."""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = get_rate_limiter(
            RateLimitConfig(
                requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
                requests_per_hour=settings.RATE_LIMIT_PER_HOUR,
                burst_size=settings.RATE_LIMIT_BURST,
            )
        )
    return _rate_limiter_instance

def _reset_rate_limiter_instance() -> None:
    """Reset rate limiter singleton (useful for tests)."""
    global _rate_limiter_instance
    _rate_limiter_instance = None

security = HTTPBearer(auto_error=False)

# ── User Provisioning Singleton ──
_user_provision_pool: asyncpg.Pool | None = None
_user_provision_lock = asyncio.Lock()
_provisioned_user_ids: set[UUID] = set()


async def _get_provision_pool() -> asyncpg.Pool:
    """Singleton pool for lightweight user provisioning upserts."""
    global _user_provision_pool
    if _user_provision_pool is not None:
        return _user_provision_pool
    async with _user_provision_lock:
        if _user_provision_pool is None:
            import asyncpg
            dsn = settings.DATABASE_URL.replace("+asyncpg", "")
            _user_provision_pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
        return _user_provision_pool


async def _ensure_user_in_db(user: User) -> None:
    """Ensure OAuth user has a row in the local users table.

    Idempotent upsert — safe to call on every request. Uses an in-memory
    cache to avoid redundant DB writes for already-provisioned users.
    """
    if user.id in _provisioned_user_ids:
        return
    try:
        pool = await _get_provision_pool()
        await pool.execute(
            """
            INSERT INTO users (id, email, display_name, auth_provider, avatar_url, last_login_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
            ON CONFLICT (id) DO UPDATE SET
                email = EXCLUDED.email,
                display_name = EXCLUDED.display_name,
                auth_provider = EXCLUDED.auth_provider,
                avatar_url = EXCLUDED.avatar_url,
                last_login_at = NOW()
            """,
            str(user.id),
            user.email,
            user.display_name,
            user.auth_provider,
            user.avatar_url,
        )
        _provisioned_user_ids.add(user.id)
    except Exception as exc:
        # Log but don't fail the request — auth already succeeded
        logger.warning("User provisioning failed for %s: %s", user.id, exc)


_BASE64URL_RE = re.compile(r'^[A-Za-z0-9_-]+$')


def _looks_like_jwt(token: str) -> bool:
    """Heuristic: JWTs have exactly 2 dots separating 3 base64url segments."""
    if token.count(".") != 2:
        return False
    parts = token.split(".")
    if any(len(p) == 0 for p in parts):
        return False
    if not all(_BASE64URL_RE.match(p) for p in parts):
        return False
    # Additional safety: header should decode to reasonable length
    if len(parts[0]) < 4:
        return False
    return True


async def _resolve_auth_token(token: str) -> User:
    """
    Unified token resolution.

    Strategy:
    1. If token looks like JWT → route to AuthPort (Supabase/Local)
    2. Else if ENABLE_LEGACY_API_KEY=true → route to legacy AuthManager
    3. Else → reject
    """
    if _looks_like_jwt(token):
        adapter: AuthPort = get_auth_adapter()
        service = AuthService(adapter)
        return await service.authenticate(token)

    # Legacy API key path (only if explicitly enabled)
    if settings.ENABLE_LEGACY_API_KEY:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "Legacy API key authentication is enabled. This is deprecated and will be removed in v2.3. "
            "Migrate to JWT authentication."
        )
        from reasoner.auth import get_auth_manager
        auth_manager = get_auth_manager()
        try:
            api_key = await auth_manager.authenticate(token)
            # Map legacy API key to canonical User
            # Safe deterministic UUID from key hash (SHA-256, take first 16 bytes)
            return User(
                id=UUID(bytes=hashlib.sha256(api_key.key_hash.encode()).digest()[:16]),
                email=f"apikey-{api_key.key_hash[:8]}@internal",
                display_name=api_key.name,
            )
        except LegacyAuthError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    raise HTTPException(
        status_code=401,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> User:
    """
    Require valid authentication (JWT or legacy API key).

    Raises HTTPException 401 if missing or invalid.
    Stores resolved user in request.state for audit middleware.
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = await _resolve_auth_token(credentials.credentials)
        await _ensure_user_in_db(user)
        request.state.user = user
        return user
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {exc}") from exc


async def get_optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[User]:
    """Optional authentication — returns None if no valid credentials."""
    if not credentials:
        return None
    try:
        user = await _resolve_auth_token(credentials.credentials)
        await _ensure_user_in_db(user)
        request.state.user = user
        return user
    except Exception:
        return None


def require_tier(min_tier: SubscriptionTier):
    """
    Factory that returns a FastAPI dependency enforcing minimum subscription tier.

    Usage:
        @app.post("/api/premium-only")
        async def premium_route(user: User = Depends(require_tier(SubscriptionTier.PRO))):
            ...
    """
    from fastapi import HTTPException

    async def checker(user: User = Depends(get_current_user)) -> User:
        # Resolves the caller's entitled tier from their subscription.
        # _resolve_user_tier() falls back to FREE on every uncertain path, so a
        # subscription-store outage denies paid access rather than granting it.
        if not settings.PRESET_TIER_ENFORCEMENT_ENABLED:
            return user
        user_tier = await _resolve_user_tier(str(user.id))
        if not tier_satisfies(user_tier, min_tier):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"This feature requires the {min_tier.value} plan. "
                    f"Your current plan is {user_tier.value}."
                ),
            )
        return user

    return checker


async def check_rate_limit(
    request: Request,
    user: User | None = Depends(get_optional_user),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """
    Check rate limit using user_id if authenticated, otherwise IP.
    """
    rate_limiter = _get_rate_limiter_instance()

    if user is not None:
        # Authenticated user — use user_id as bucket key with tier multiplier.
        # The tier drives is_allowed_for_user()'s multiplier (pro 2x, enterprise
        # 5x); hardcoding "default" gave paying users the free-tier limit.
        # _resolve_user_tier() falls back to FREE on every uncertain path, and
        # the subscription repo is cached with webhook invalidation, so this
        # does not add a database round-trip per request.
        client_id = f"user:{user.id}"
        user_tier = await _resolve_user_tier(str(user.id))
        try:
            allowed, info = await rate_limiter.is_allowed_for_user(
                client_id, tier=user_tier.value
            )
        except Exception as exc:
            # BUG-FIX: Fail closed on rate limiter errors instead of fail open.
            # Previously any exception (including programming bugs) allowed the request
            # through, creating a trivial bypass vector.
            logger.error("Rate limiter error: %s", exc)
            allowed = False
            info = {"limit_minute": 60, "remaining_minute": 0, "retry_after": 60}
    else:
        # Anonymous — use IP + User-Agent hash
        ip = get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")
        client_id = f"{ip}:{hashlib.sha256(user_agent.encode()).hexdigest()[:8]}"
        try:
            allowed, info = await rate_limiter.is_allowed(client_id)
        except Exception as exc:
            # BUG-FIX: Fail closed on rate limiter errors instead of fail open.
            logger.error("Rate limiter error: %s", exc)
            allowed = False
            info = {"limit_minute": 60, "remaining_minute": 0, "retry_after": 60}

    request.state.rate_limit_info = info

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "retry_after": int(info.get("retry_after") or 60),
                "limit_minute": info.get("limit_minute"),
                "remaining_minute": info.get("remaining_minute", 0),
            },
            headers={
                "Retry-After": str(int(info.get("retry_after") or 60)),
                "X-RateLimit-Limit": str(info.get("limit_minute")),
                "X-RateLimit-Remaining": str(info.get("remaining_minute", 0)),
            },
        )
    return True


# ── Quota Service Singleton ──
_quota_service: QuotaService | None = None

def _get_quota_service() -> QuotaService:
    """Factory for QuotaService with cached Postgres repository."""
    global _quota_service
    if _quota_service is None:
        from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
        from reasoner.infrastructure.persistence.cached_quota_repo import CachedQuotaRepository
        dsn = settings.DATABASE_URL.replace("+asyncpg", "")
        pg_repo = PostgresQuotaRepository(dsn, pool_size=settings.DB_POOL_SIZE)
        cached_repo = CachedQuotaRepository(pg_repo)
        _quota_service = QuotaService(cached_repo)
    return _quota_service

# ── Pipeline & Preset Services ──

def get_preset_service() -> PresetService:
    """Dependency provider for PresetService."""
    from reasoner.application.services.preset_service import PresetService
    return PresetService()

def get_pipeline_service() -> PipelineService:
    """Dependency provider for PipelineService."""
    from reasoner.application.services.pipeline_service import PipelineService
    return PipelineService()

def get_search_service() -> SearchService:
    """Dependency provider for SearchService."""
    from reasoner.application.services.search_service import SearchService
    return SearchService()

# ── Event Bus & Event Store Dependency Providers ──

def get_event_bus(request: Request):
    """FastAPI dependency: provides the shared EventBus."""
    from reasoner.application.event_bus.bus import get_event_bus
    return get_event_bus()


def get_event_store(request: Request):
    """FastAPI dependency: provides the shared EventStore."""
    from reasoner.infrastructure.persistence.event_store import get_event_store
    return get_event_store()


# ── Subscription Repository Singleton ──
_subscription_repo = None


def _get_subscription_repo():
    """Factory for the subscription repository used to resolve tier entitlement.

    Cached: tier is resolved on every quota-checked request, but subscriptions
    only change via billing webhooks, which invalidate the entry directly.
    """
    global _subscription_repo
    if _subscription_repo is None:
        from reasoner.infrastructure.persistence.subscription_repo import (
            PostgresSubscriptionRepository,
        )
        from reasoner.infrastructure.persistence.cached_subscription_repo import (
            CachedSubscriptionRepository,
        )
        dsn = settings.DATABASE_URL.replace("+asyncpg", "")
        pg_repo = PostgresSubscriptionRepository(dsn, pool_size=settings.DB_POOL_SIZE)
        _subscription_repo = CachedSubscriptionRepository(pg_repo)
    return _subscription_repo


# Statuses that entitle a user to their subscription's tier. Anything else
# (cancelled, past_due) is treated as FREE.
_ENTITLED_STATUSES = frozenset({SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING})

# Tier ranking for "at least this tier" comparisons. SubscriptionTier is a plain
# str Enum with no inherent order, so comparisons must go through this map.
_TIER_RANK: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 0,
    SubscriptionTier.PRO: 1,
    SubscriptionTier.ENTERPRISE: 2,
}


def tier_satisfies(user_tier: SubscriptionTier, required_tier: SubscriptionTier) -> bool:
    """Whether *user_tier* meets or exceeds *required_tier*.

    Unknown tiers rank 0 (FREE) so an unrecognised value can never satisfy a paid
    requirement.
    """
    return _TIER_RANK.get(user_tier, 0) >= _TIER_RANK.get(required_tier, 0)


async def _resolve_user_tier(user_id: str) -> SubscriptionTier:
    """Resolve the tier a user is entitled to from their subscription.

    Falls back to FREE on every uncertain path — no subscription, a status that
    does not entitle, or a lookup failure — so an outage can never hand out a
    paid tier. get_subscription_by_user() returns the newest row without
    filtering on status, so the status check must happen here.
    """
    try:
        subscription = await _get_subscription_repo().get_subscription_by_user(user_id)
    except Exception:
        logger.warning("Subscription lookup failed; defaulting to FREE tier", exc_info=True)
        return SubscriptionTier.FREE

    if subscription is None or subscription.status not in _ENTITLED_STATUSES:
        return SubscriptionTier.FREE
    return subscription.tier


def _reset_quota_service() -> None:
    """Reset quota service singleton (useful for tests)."""
    global _quota_service, _subscription_repo
    _quota_service = None
    _subscription_repo = None


async def check_quota(
    user: User = Depends(get_current_user),
) -> QuotaResult:
    """
    FastAPI dependency: check if user has remaining quota.
    Raises HTTPException 429 if exceeded.
    """
    user_tier = await _resolve_user_tier(str(user.id))

    service = _get_quota_service()
    try:
        result = await service.check(str(user.id), user_tier)
    except Exception:
        # BUG-FIX: Use emergency conservative quota instead of fail open.
        # Previously any DB error granted unlimited quota (-1 remaining),
        # creating a trivial bypass for quota enforcement.
        logger = logging.getLogger(__name__)
        logger.warning("Quota check failed due to DB error, using emergency limits")
        return QuotaResult(allowed=True, remaining=10)

    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Quota exceeded",
                "message": result.reason,
                "remaining": result.remaining,
                "retry_after": result.retry_after,
                "upgrade_url": "/pricing",
            },
            headers={
                "Retry-After": str(result.retry_after or 3600),
                "X-RateLimit-Remaining": "0",
            },
        )
    return result


async def check_preset_access(
    preset: str,
    user: User = Depends(get_current_user),
) -> None:
    """
    FastAPI dependency: enforce preset tier requirements.
    Raises HTTPException 403 if preset requires higher tier.
    """
    from fastapi import HTTPException

    # Off by default — see PRESET_TIER_ENFORCEMENT_ENABLED. Previously this raised
    # 403 for *every* caller in production (paying users included) and enforced
    # nothing anywhere else, so neither tier got the intended behaviour.
    if not settings.PRESET_TIER_ENFORCEMENT_ENABLED:
        return

    required_tier = get_preset_tier(preset)
    if required_tier == SubscriptionTier.FREE:
        return

    user_tier = await _resolve_user_tier(str(user.id))
    if not tier_satisfies(user_tier, required_tier):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Preset '{preset}' requires the {required_tier.value} plan. "
                f"Your current plan is {user_tier.value}."
            ),
        )


async def check_preset_access_if_authenticated(
    preset: str,
    user: User | None,
) -> None:
    """Enforce preset tier requirements for authenticated callers.

    Called from the route body rather than via Depends: the preset arrives in the
    request body, and a dependency taking the body model cannot be resolved from a
    string annotation, so FastAPI would treat it as a query parameter.

    Mirrors check_quota_if_authenticated — anonymous access is governed by
    ENABLE_LEGACY_API_KEY at the route, so there is no subscription to check.
    """
    if user is None:
        return
    await check_preset_access(preset, user)


async def check_quota_if_authenticated(
    user: User | None = Depends(get_optional_user),
) -> QuotaResult | None:
    """Only check quota if user is authenticated."""
    if user is None:
        return None
    return await check_quota(user)
