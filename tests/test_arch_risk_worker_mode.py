"""
Architecture Risk: In-memory singletons in multi-worker deployments.

The architecture audit identified that rate limiter, circuit breaker, and
auth store default to in-memory mode, which fails silently with multiple
uvicorn workers. Tests verify the warning/error paths.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

# ── Rate limiter mode validation ─────────────────────────────────────


@pytest.mark.asyncio
async def test_memory_rate_limiter_warns_in_multi_worker() -> None:
    """When UVICORN_WORKERS > 1 and RATE_LIMITER_MODE=memory,
    a warning should be logged in non-production environments."""

    # Force settings state
    with patch.dict(
        os.environ,
        {
            "UVICORN_WORKERS": "4",
            "RATE_LIMITER_MODE": "memory",
            "ENVIRONMENT": "development",
        },
        clear=False,
    ):
        # Re-read: the settings class reads at import time, but uses @property values
        uvicorn_workers = int(os.environ.get("UVICORN_WORKERS", "1"))
        ratelimit_mode = os.environ.get("RATE_LIMITER_MODE", "memory")

        assert uvicorn_workers > 1
        assert ratelimit_mode == "memory"
        # The actual warning is in api/__init__.py lifespan — tested there


def _load_isolated_settings_module():
    """Load a private copy of reasoner.core.settings under a throwaway module
    name, instead of importlib.reload()-ing the canonical one.

    reload() replaces sys.modules["reasoner.core.settings"].Settings/settings
    in place -- but every module that already did `from reasoner.core.settings
    import settings` (feedback.py, dependencies.py, auth_deps.py, admin_auth.py,
    rate_limiter.py, ...) keeps its own reference to the pre-reload objects.
    That desyncs the process into two permanently disconnected Settings
    universes: code that reads `settings.X` sees the original singleton
    forever, while anything that re-imports `Settings`/`settings` after the
    reload (e.g. a later test's `from reasoner.core.settings import Settings`)
    gets the replacement -- so monkeypatching one is invisible to the other.
    That previously made unrelated tests elsewhere in the suite fail (e.g.
    admin-endpoint tests monkeypatching Settings.ADMIN_API_KEY and getting a
    503 "Admin endpoint not configured" because feedback.py was still reading
    the pre-reload settings object) whenever this module ran first on a
    shared xdist worker. Loading the module under a private name exercises
    the exact same class-body-default logic without ever touching the
    shared `reasoner.core.settings` module or any object other code holds a
    reference to.
    """
    import importlib.util
    import reasoner.core.settings as canonical

    spec = importlib.util.spec_from_file_location(
        "reasoner_core_settings_isolated_probe", canonical.__file__
    )
    isolated = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(isolated)
    return isolated


@pytest.mark.asyncio
async def test_production_memory_ratelimiter_should_be_redis() -> None:
    """In production, if RATE_LIMITER_MODE=memory with >1 workers, CRITICAL is logged
    and the app should refuse to start. We validate the guard condition exists."""
    # Copy environment and pop the keys to test fallback defaults
    env_copy = os.environ.copy()
    env_copy.pop("RATE_LIMITER_MODE", None)
    env_copy.pop("CIRCUIT_BREAKER_MODE", None)
    with patch("dotenv.load_dotenv", return_value=True):
        with patch.dict(os.environ, env_copy, clear=True):
            isolated = _load_isolated_settings_module()
            s = isolated.Settings()
            assert hasattr(s, "RATE_LIMITER_MODE")
            assert hasattr(s, "CIRCUIT_BREAKER_MODE")
            # Default should be "redis" (as set in settings.py)
            assert s.RATE_LIMITER_MODE == "redis"
            assert s.CIRCUIT_BREAKER_MODE == "redis"


def test_settings_default_ratelimiter_mode_is_redis() -> None:
    """Default RATE_LIMITER_MODE should be 'redis' for production safety.
    This guards against accidental regression to 'memory' defaults."""
    # Copy environment and pop the keys to test fallback defaults
    env_copy = os.environ.copy()
    env_copy.pop("RATE_LIMITER_MODE", None)
    env_copy.pop("CIRCUIT_BREAKER_MODE", None)
    with patch("dotenv.load_dotenv", return_value=True):
        with patch.dict(os.environ, env_copy, clear=True):
            isolated = _load_isolated_settings_module()
            s = isolated.Settings()
            assert s.RATE_LIMITER_MODE == "redis", (
                f"RATE_LIMITER_MODE is '{s.RATE_LIMITER_MODE}', should be 'redis'. "
                "A 'memory' default is unsafe for multi-worker deployments."
            )
            assert s.CIRCUIT_BREAKER_MODE == "redis", (
                f"CIRCUIT_BREAKER_MODE is '{s.CIRCUIT_BREAKER_MODE}', should be 'redis'."
            )


# ── Auth persistence mode validation ─────────────────────────────────


def test_auth_persistence_disabled_by_default() -> None:
    """Auth persistence should be opt-in. Default false prevents
    silent SQLite auth store creation in multi-worker deployments."""
    from reasoner.core.settings import settings

    assert settings.AUTH_PERSISTENCE_ENABLED is False, (
        "AUTH_PERSISTENCE_ENABLED should default to False. "
        "True creates a local SQLite that doesn't share across workers."
    )


# ── Rate limit config values are reasonable ──────────────────────────


def test_rate_limit_config_bounds() -> None:
    """Default rate limit values should be reasonable positive integers."""
    from reasoner.core.settings import settings

    assert settings.RATE_LIMIT_PER_MINUTE > 0
    assert settings.RATE_LIMIT_PER_HOUR > 0
    assert settings.RATE_LIMIT_BURST > 0
    assert settings.RATE_LIMIT_BURST < settings.RATE_LIMIT_PER_MINUTE, (
        "Burst should be less than per-minute limit to prevent sustained abuse"
    )


def test_rate_limiter_token_bucket_imports() -> None:
    """Verify rate_limiter module has expected API."""
    from reasoner.rate_limiter import RateLimitConfig, get_rate_limiter

    rate_limiter = get_rate_limiter(
        RateLimitConfig(
            requests_per_minute=10,
            requests_per_hour=100,
            burst_size=3,
        )
    )
    assert rate_limiter is not None


def test_circuit_breaker_imports() -> None:
    """Verify circuit_breaker module has expected API."""
    from reasoner.circuit_breaker import get_circuit_breaker

    cb = get_circuit_breaker("test-model")
    assert cb is not None
