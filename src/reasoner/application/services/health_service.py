"""Liveness/dependency health check, shared by the HTTP and MCP adapters.

Moved out of api/routes/health.py -- the only HTTP-specific part of that
handler was reading X-Admin-Key off the request to decide how much detail to
expose; everything else is pure dependency probing. is_admin is now a plain
argument instead.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def _failed(check: str, status: str, exc: Exception, is_admin: bool) -> dict[str, Any]:
    """A failed probe. The exception text goes to the log and to admins only:
    `GET /api/health` is public, and driver errors can name hosts, ports or DSNs.
    Callers log the failure themselves, so each handler carries its own signal."""
    return {"status": status, "reason": str(exc)} if is_admin else {"status": status}

_health_postgres_pool = None

# Per-probe cap. useServerStatus aborts at 3s; probes run in parallel.
_PROBE_TIMEOUT_S = 2.0


async def _probe_postgres(database_url: str | None, is_admin: bool) -> dict[str, Any]:
    if not database_url:
        return {"status": "ok", "reason": "not configured"}
    global _health_postgres_pool  # noqa: PLW0603
    try:
        if _health_postgres_pool is None:
            import asyncpg

            dsn = database_url.replace("+asyncpg", "")
            _health_postgres_pool = await asyncio.wait_for(
                asyncpg.create_pool(dsn, min_size=1, max_size=2),
                timeout=_PROBE_TIMEOUT_S,
            )
        await asyncio.wait_for(
            _health_postgres_pool.fetchval("SELECT 1"), timeout=_PROBE_TIMEOUT_S
        )
        # Deliberately NO reasoner_postgres_pool_* gauges from this pool: it is a
        # private probe pool (min 1, max 2), not a serving pool. The app's real
        # pools live inside each Postgres repository (DB_POOL_SIZE connections
        # each), so a gauge fed from here read ~1 permanently and drove
        # PostgresPoolLow/PostgresPoolExhaustion on a number unrelated to load.
        return {"status": "ok"}
    except Exception as e:
        _health_postgres_pool = None
        logger.warning("health check postgres failed: %s", e)
        return _failed("postgres", "error", e, is_admin)


async def _probe_valkey(is_admin: bool) -> dict[str, Any]:
    # Canonical VALKEY_URL; falls back to REDIS_URL for backward compat.
    if not (os.environ.get("VALKEY_URL") or os.environ.get("REDIS_URL", "")):
        return {"status": "ok", "reason": "not configured"}
    try:
        from reasoner.infrastructure.valkey.client import get_valkey_pool

        valkey_client = get_valkey_pool()
        await asyncio.wait_for(valkey_client.ping(), timeout=_PROBE_TIMEOUT_S)
        from reasoner.infrastructure.metrics import REASONER_VALKEY_POOL_SIZE

        pool_info = valkey_client.connection_pool.max_connections
        REASONER_VALKEY_POOL_SIZE.set(pool_info or 0)
        return {"status": "ok"}
    except Exception as e:
        logger.warning("health check valkey failed: %s", e)
        return _failed("valkey", "error", e, is_admin)


async def check_health(
    is_admin: bool = False, *, cache_file_count: int | None = None
) -> dict[str, Any]:
    """Probe memory, circuit breakers, cache, Postgres, Valkey, and Stripe config.

    cache_file_count is supplied by the caller rather than read here: the
    on-disk response cache is an api-layer artifact (api/cache.py), and this
    module must not import from api/ (application may not depend on api).
    The count is admin-diagnostic only -- it never affects overall status,
    so omitting it (the default) is a legitimate call, not a degraded one.
    """
    from reasoner.core.settings import settings

    health: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
    health["checks"]["cache"] = {
        "status": "ok",
        **({"files": cache_file_count} if is_admin and cache_file_count is not None else {}),
    }

    # Network probes run concurrently, each capped at _PROBE_TIMEOUT_S, so the
    # whole check stays under the UI's 3s liveness timeout even when both
    # dependencies are down. Run in sequence with 5s caps, a down Postgres and
    # Valkey took ~6s and the UI showed a running backend as "Offline".
    health["checks"]["postgres"], health["checks"]["valkey"] = await asyncio.gather(
        _probe_postgres(settings.DATABASE_URL, is_admin),
        _probe_valkey(is_admin),
    )

    # Stripe check
    try:
        if settings.STRIPE_SECRET_KEY:
            health["checks"]["stripe"] = {"status": "ok"}
        else:
            health["checks"]["stripe"] = {"status": "ok", "reason": "not configured"}
    except Exception as e:
        logger.warning("health check stripe failed: %s", e)
        health["checks"]["stripe"] = _failed("stripe", "warning", e, is_admin)

    # Determine overall status
    if any(c.get("status") == "error" for c in health["checks"].values()):
        health["status"] = "unhealthy"
    elif any(c.get("status") in ("warning", "degraded") for c in health["checks"].values()):
        health["status"] = "degraded"

    return health


__all__ = ["check_health"]
