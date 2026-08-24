"""
SaaS Router — All new SaaS-related API endpoints.

This router is mounted in api/__init__.py to keep the main file
from growing uncontrollably.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from reasoner.api.dependencies import (
    _get_quota_service,
    get_current_user,
    get_optional_user,
)
from reasoner.api.middleware import _anonymize_ip
from reasoner.application.services.quota_service import TIER_LIMITS
from reasoner.core.settings import settings
from reasoner.domain.saas import SubscriptionTier, User
from reasoner.rate_limiter import RateLimitConfig, get_rate_limiter

router = APIRouter(prefix="/api", tags=["saas"])

# Strict rate limiter for sensitive endpoints (Critical Enhancement 6.4)
_strict_rate_limiter = get_rate_limiter(
    RateLimitConfig(
        requests_per_minute=5,
        requests_per_hour=20,
        burst_size=2,
    )
)


async def _check_strict_rate_limit(request: Request):
    """Rate limit sensitive endpoints (export, delete) to prevent DoS."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host if request.client else "unknown"
    user = getattr(request.state, "user", None)
    client_id = f"user:{user.id}" if user else f"ip:{ip}"
    allowed, info = await _strict_rate_limiter.is_allowed(client_id)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"error": "Rate limit exceeded for sensitive endpoint", "retry_after": int(info.get("retry_after") or 60)},
            headers={"Retry-After": str(int(info.get("retry_after") or 60))},
        )


async def _log_auth_event(
    user_id: UUID | None,
    event_type: str,
    ip: str | None,
    user_agent: str | None,
) -> None:
    """Insert an auth audit log row (Critical Enhancement 6.3)."""
    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
    dsn = settings.DATABASE_URL.replace("+asyncpg", "")
    repo = PostgresQuotaRepository(dsn, pool_size=2)
    pool = await repo._get_pool()
    await pool.execute(
        """
        INSERT INTO auth_audit_log (user_id, event_type, ip_address, user_agent)
        VALUES ($1, $2, $3, $4)
        """,
        str(user_id) if user_id else None,
        event_type,
        ip,
        user_agent,
    )


@router.get("/auth/me")
async def get_me(user: User = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "auth_provider": user.auth_provider,
        "avatar_url": user.avatar_url,
    }


@router.get("/auth/me/optional")
async def get_me_optional(user: User | None = Depends(get_optional_user)):
    """Return user if authenticated, null otherwise. Useful for UI state hydration."""
    if user is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "auth_provider": user.auth_provider,
        "avatar_url": user.avatar_url,
    }


@router.get("/quota")
async def get_quota_status(user: User = Depends(get_current_user)):
    """Return current usage and remaining quota."""
    service = _get_quota_service()
    result = await service.check(str(user.id), SubscriptionTier.FREE)
    # TODO(#502): use actual user tier
    used = (TIER_LIMITS[SubscriptionTier.FREE] - result.remaining) if result.remaining >= 0 else 0
    return {
        "used": used,
        "max": TIER_LIMITS[SubscriptionTier.FREE],
        "remaining": result.remaining,
        "reset_date": (datetime.now(UTC).replace(day=1) + timedelta(days=32)).replace(day=1).isoformat(),
    }


# ── GDPR Endpoints (Critical Enhancement 6.4) ──

@router.get("/account/export")
async def export_data(
    request: Request,
    user: User = Depends(get_current_user),
    _: None = Depends(_check_strict_rate_limit),
):
    """Export all personal data as JSON (GDPR Article 20).

    Critical Enhancement 6.7: capped at 1000 query logs to prevent OOM.
    """
    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
    dsn = settings.DATABASE_URL.replace("+asyncpg", "")
    repo = PostgresQuotaRepository(dsn, pool_size=2)
    pool = await repo._get_pool()

    # Explicit allowlists for GDPR export (SEC-010)
    PROFILE_FIELDS = ["id", "email", "display_name", "created_at"]
    SUBSCRIPTION_FIELDS = ["tier", "status", "current_period_end", "stripe_subscription_id"]
    QUOTA_FIELDS = ["tier", "used_queries", "max_queries", "period_start"]
    QUERY_FIELDS = ["preset", "method", "tokens_in", "tokens_out", "cost_usd", "timestamp"]

    profile = await pool.fetchrow(
        f"SELECT {', '.join(PROFILE_FIELDS)} FROM users WHERE id = $1", str(user.id)
    )
    subscriptions = await pool.fetch(
        f"SELECT {', '.join(SUBSCRIPTION_FIELDS)} FROM subscriptions WHERE user_id = $1", str(user.id)
    )
    quotas = await pool.fetchrow(
        f"SELECT {', '.join(QUOTA_FIELDS)} FROM usage_quotas WHERE user_id = $1", str(user.id)
    )
    queries = await pool.fetch(
        f"SELECT {', '.join(QUERY_FIELDS)} FROM query_audit_logs WHERE user_id = $1 ORDER BY timestamp DESC LIMIT 1000",
        str(user.id),
    )

    await _log_auth_event(
        user.id, "data_export",
        _anonymize_ip(request.client.host if request.client else None),
        request.headers.get("User-Agent"),
    )

    return {
        "profile": dict(profile) if profile else {},
        "subscriptions": [dict(s) for s in subscriptions],
        "quota": dict(quotas) if quotas else {},
        "queries": [dict(q) for q in queries],
        "exported_at": datetime.now(UTC).isoformat(),
    }


@router.post("/account/delete")
async def delete_account(
    request: Request,
    user: User = Depends(get_current_user),
    _: None = Depends(_check_strict_rate_limit),
):
    """Hard delete user and all data (GDPR Article 17).

    Critical Enhancement 6.2: cancels active Stripe subscription first.
    Phase 0.2 fix: atomic transaction with no-FK deletion-log audit.
    """
    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
    dsn = settings.DATABASE_URL.replace("+asyncpg", "")
    repo = PostgresQuotaRepository(dsn, pool_size=2)
    pool = await repo._get_pool()

    ip = _anonymize_ip(request.client.host if request.client else None)
    ua = request.headers.get("User-Agent")

    # Phase 1: Cancel billing subscriptions (BEFORE transaction — external side-effects).
    sub_row = await pool.fetchrow(
        "SELECT stripe_sub_id, paypal_sub_id FROM subscriptions WHERE user_id = $1 AND status = 'active' LIMIT 1",
        str(user.id),
    )
    if sub_row:
        if sub_row["stripe_sub_id"]:
            try:
                from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter
                adapter = StripeBillingAdapter()
                await adapter.cancel_subscription(sub_row["stripe_sub_id"])
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to cancel Stripe subscription %s for user %s: %s",
                    sub_row["stripe_sub_id"], user.id, exc,
                )
        if sub_row["paypal_sub_id"]:
            try:
                from reasoner.infrastructure.billing.paypal_adapter import PayPalBillingAdapter
                adapter = PayPalBillingAdapter()
                await adapter.cancel_subscription(sub_row["paypal_sub_id"])
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to cancel PayPal subscription %s for user %s: %s",
                    sub_row["paypal_sub_id"], user.id, exc,
                )

    # Phase 2: Atomic DB transaction — audit BEFORE delete
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Write deletion-audit to no-FK table BEFORE user delete
            await conn.execute(
                """
                INSERT INTO account_deletion_log (user_id, ip_address, user_agent)
                VALUES ($1, $2, $3)
                """,
                str(user.id), ip, ua,
            )
            # Delete user — CASCADE cleans auth_audit_log, subscriptions, quotas
            await conn.execute("DELETE FROM users WHERE id = $1", str(user.id))

    deleted = {"db": True, "uploads": 0, "history": 0, "vectors": 0, "cache": 0}

    # Phase 3: External side-effects (best-effort, AFTER transaction commits)
    # Uploads
    try:
        from reasoner.uploader import delete_file, list_uploads
        user_uploads = list_uploads(user_id=str(user.id))
        for upload in user_uploads:
            if delete_file(upload["file_id"]):
                deleted["uploads"] += 1
    except Exception:
        pass

    # History files
    try:
        import json as _json

        from reasoner.api.history import HISTORY_DIR
        for f in HISTORY_DIR.glob("*.json"):
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                if data.get("user_id") == str(user.id):
                    f.unlink(missing_ok=True)
                    deleted["history"] += 1
            except Exception:
                pass
    except Exception:
        pass

    # Vector store (best-effort)
    try:
        from reasoner.documents.vector_store import DocumentVectorStore
        store = DocumentVectorStore()
        for upload in user_uploads:
            try:
                store.delete_index(upload["file_id"])
                deleted["vectors"] += 1
            except Exception:
                pass
    except Exception:
        pass

    # Redis cache keys (best-effort)
    try:
        from reasoner.infrastructure.valkey.client import get_valkey_pool
        redis = get_valkey_pool()
        pattern = f"user:{user.id}:*"
        keys = await redis.keys(pattern)
        if keys:
            await redis.delete(*keys)
            deleted["cache"] = len(keys)
    except Exception:
        pass

    return {"status": "deleted", "user_id": str(user.id), "deleted": deleted}
