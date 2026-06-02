"""Health check endpoint — /api/health.

Comprehensive health check for system status and subsystem pass/fail.
Public response omits internal details (memory bytes, pool sizes, Python version).
Full diagnostics available with valid X-Admin-Key header.
"""

from __future__ import annotations

import secrets
import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from reasoner.core.settings import settings

router = APIRouter()


@router.get("/api/health")
async def health_check(request: Request):
    """Comprehensive health check endpoint."""
    admin_key = request.headers.get("X-Admin-Key", "")
    admin_api_key = settings.ADMIN_API_KEY or ""
    is_admin = bool(admin_api_key and secrets.compare_digest(admin_key, admin_api_key))

    health: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "version": "2.0",
        "checks": {},
    }

    if is_admin:
        health["python"] = sys.version

    # Memory check
    try:
        import psutil
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        status = "ok" if memory_mb < settings.MEMORY_LIMIT_MB else "warning"
        health["checks"]["memory"] = {
            "status": status,
            **(
                {"used_mb": round(memory_mb, 1), "limit_mb": settings.MEMORY_LIMIT_MB}
                if is_admin else {}
            ),
        }
    except ImportError:
        health["checks"]["memory"] = {"status": "unknown", "reason": "psutil not installed"}

    # Circuit breaker status
    from reasoner.circuit_breaker import get_all_circuit_breakers
    circuits = get_all_circuit_breakers()
    open_circuits = [name for name, cb in circuits.items() if cb["state"] == "open"]
    health["checks"]["circuit_breakers"] = {
        "status": "ok" if not open_circuits else "degraded",
        **(
            {"open_circuits": open_circuits, "total": len(circuits)}
            if is_admin else {}
        ),
    }

    # Cache status
    from reasoner.api.cache import CACHE_DIR
    cache_files = list(CACHE_DIR.glob("*.json"))
    health["checks"]["cache"] = {
        "status": "ok",
        **({"files": len(cache_files)} if is_admin else {}),
    }

    # Postgres check
    from reasoner.api.cache import _health_postgres_pool
    global _health_postgres_pool  # noqa: PLW0603
    try:
        if _health_postgres_pool is None:
            import asyncpg
            dsn = settings.DATABASE_URL.replace("+asyncpg", "")
            _health_postgres_pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        await _health_postgres_pool.fetchval("SELECT 1")
        health["checks"]["postgres"] = {"status": "ok"}
        from reasoner.metrics import REASONER_POSTGRES_POOL_SIZE, REASONER_POSTGRES_POOL_FREE
        REASONER_POSTGRES_POOL_SIZE.set(_health_postgres_pool.get_size())
        REASONER_POSTGRES_POOL_FREE.set(
            _health_postgres_pool.get_size() - _health_postgres_pool.get_idle_size()
        )
    except Exception as e:
        health["checks"]["postgres"] = {"status": "error", "reason": str(e)}
        _health_postgres_pool = None

    # Redis check
    try:
        from reasoner.infrastructure.redis.client import get_redis
        redis = get_redis()
        await redis.ping()
        health["checks"]["redis"] = {"status": "ok"}
        from reasoner.metrics import REASONER_REDIS_POOL_SIZE
        pool_info = redis.connection_pool.max_connections
        REASONER_REDIS_POOL_SIZE.set(pool_info or 0)
    except Exception as e:
        health["checks"]["redis"] = {"status": "error", "reason": str(e)}

    # Stripe check
    try:
        if settings.STRIPE_SECRET_KEY:
            health["checks"]["stripe"] = {"status": "ok"}
        else:
            health["checks"]["stripe"] = {"status": "ok", "reason": "not configured"}
    except Exception as e:
        health["checks"]["stripe"] = {"status": "warning", "reason": str(e)}

    # Determine overall status
    if any(c.get("status") == "error" for c in health["checks"].values()):
        health["status"] = "unhealthy"
    elif any(c.get("status") in ("warning", "degraded") for c in health["checks"].values()):
        health["status"] = "degraded"

    return health
