from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from reasoner.core.constants import (
    CORS_MAX_AGE_SECONDS,
    TRUNCATION,
)
from reasoner.core.settings import settings

# Setup logger
logger = logging.getLogger(__name__)

# SafeLoggingFilter is installed at the package level in reasoner/__init__.py
# so it applies to CLI, tests, and all entry points — not just the API.

# Initialize Sentry (Critical Enhancement 7.2)
from reasoner.api.sentry import init_sentry

init_sentry()

# --- Action 1.2: Observability Strictness & Metrics --- START
if settings.ENVIRONMENT == "production":
    if not settings.LANGFUSE_PUBLIC_KEY or not settings.LANGFUSE_SECRET_KEY:
        raise RuntimeError("CRITICAL: Langfuse keys (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY) are missing in production environment. Observability is mandatory in production.")
    # Lightweight Langfuse connectivity probe: verify the SDK is reachable
    # by attempting a simple public-key check.  Connection errors are logged
    # but non-fatal — the app can run without observability in degraded mode.
    try:
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
        )
        _langfuse.auth_check()
        logger.info("Langfuse connectivity probe: OK")
    except Exception as probe_exc:
        logger.warning(
            "Langfuse connectivity check failed (non-fatal): %s", probe_exc
        )
# --- Action 1.2: Observability Strictness & Metrics --- END

# Register global exception handlers (Critical Enhancement 7.7)
from reasoner.api.error_handler import register_exception_handlers

# Security dependencies
security = HTTPBearer(auto_error=False)

# Import rate limiter and auth
from reasoner.api.middleware import SecurityHeadersMiddleware
from reasoner.auth import AuthenticationError, get_auth_manager
from reasoner.rate_limiter import RateLimitConfig, get_rate_limiter

# Module-level singleton for health-check Postgres pool (Critical Enhancement 5.6)
_health_postgres_pool = None


async def _update_active_users_loop() -> None:
    """Background task to update active users gauge every 60s (Critical Enhancement 7.3)."""
    from reasoner.metrics import REASONER_ACTIVE_USERS
    while True:
        try:
            await asyncio.sleep(60)
            if _health_postgres_pool is not None:
                row = await _health_postgres_pool.fetchval(
                    "SELECT COUNT(DISTINCT user_id) FROM query_audit_logs WHERE timestamp > NOW() - INTERVAL '24 hours'"
                )
                REASONER_ACTIVE_USERS.set(row or 0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Active users update failed: %s", exc)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown orchestration."""
    # ── Startup ──
    from reasoner.application.event_bus.bus import get_event_bus, init_default_subscribers
    bus = get_event_bus()
    await bus.start()
    await init_default_subscribers(bus)

    from reasoner.infrastructure.websocket import setup_event_bus_integration
    await setup_event_bus_integration()

    from reasoner.core.health_validator import validate_all
    await validate_all()

    # Valkey probe for production — warn on failure, don't block startup.
    # All Valkey consumers handle unreachable Valkey gracefully via in-memory fallback.
    if settings.ENVIRONMENT == "production":
        try:
            from reasoner.infrastructure.valkey.client import get_valkey_pool
            _probe_valkey = get_valkey_pool()
            await _probe_valkey.set("_prod_startup_probe", "1", ex=10, nx=True)
            logger.info("Valkey probe (production): reachable")
        except Exception as probe_exc:
            logger.warning(
                "Valkey is unreachable in production: %s. "
                "All Valkey consumers have in-memory fallbacks, but cross-worker "
                "cancellation and distributed rate limiting will not work. "
                "Start Valkey or set RATE_LIMITER_MODE=memory (single-worker only).",
                probe_exc,
            )

    # Warn if running in multi-worker mode with in-memory rate limiting / circuit breaker
    uvicorn_workers = settings.UVICORN_WORKERS
    if uvicorn_workers > 1:
        if settings.RATE_LIMITER_MODE == "memory":
            message = (
                f"Rate limiter is in 'memory' mode but UVICORN_WORKERS={uvicorn_workers}. "
                "Each worker maintains its own token bucket, allowing rate-limit bypass. "
                "Set RATE_LIMITER_MODE to a shared backend (e.g., 'redis')."
            )
            # Raise ONLY in production environment to avoid blocking non-prod.
            if settings.ENVIRONMENT == "production":
                logger.critical(message)
                raise RuntimeError(
                    f"Unsafe rate limiter configuration: RATE_LIMITER_MODE=memory with "
                    f"UVICORN_WORKERS={uvicorn_workers} in {settings.ENVIRONMENT}. "
                    f"Set RATE_LIMITER_MODE=redis."
                )
            logger.warning(message)
        if settings.CIRCUIT_BREAKER_MODE == "memory":
            message = (
                "Circuit breaker is in 'memory' mode but UVICORN_WORKERS=%d. "
                "Circuit state is not shared across workers. "
                "Set CIRCUIT_BREAKER_MODE to a shared backend (e.g., 'redis') for production."
            )
            # Raise ONLY in production environment to avoid blocking non-prod.
            if settings.ENVIRONMENT == "production":
                raise RuntimeError(message % uvicorn_workers)
            logger.warning(message, uvicorn_workers)
        if settings.ENVIRONMENT == "production" and not settings.AUTH_PERSISTENCE_ENABLED:
            raise RuntimeError(
                "AUTH_PERSISTENCE_ENABLED must be true for multi-worker production deployments."
            )

    # Neuro's endpoints are mounted on the public app and self-called over
    # loopback. Without the shared key they are open: /audit is an unmetered
    # LLM proxy and /learn writes into tenant memory.
    if not settings.neuro_internal_key:
        message = (
            "NEURO_INTERNAL_KEY is unset: /api/neuro/* is unauthenticated. "
            "Set the same value on every API worker and on the Next server "
            "(its /api/neuro/* proxy routes forward it upstream)."
        )
        if settings.ENVIRONMENT == "production":
            logger.critical(message)
            raise RuntimeError(message)
        logger.warning(message)

    # Single-worker SSE warning: health checks time out during long pipeline runs
    if uvicorn_workers == 1 and settings.ENVIRONMENT != "development":
        logger.warning(
            "Single-worker mode detected (UVICORN_WORKERS=1). "
            "Health checks and other concurrent requests will block during "
            "long-running SSE pipeline streams (typically 30-60s). "
            "Consider UVICORN_WORKERS >= 2 for production to keep health "
            "endpoints responsive."
        )

    # Valkey reachability probe when RATE_LIMITER_MODE requires shared backend
    if settings.RATE_LIMITER_MODE in ("redis", "valkey"):
        try:
            from reasoner.infrastructure.valkey.client import get_valkey_pool
            _probe_valkey = get_valkey_pool()
            await _probe_valkey.set("_startup_probe", "1", ex=10, nx=True)
            logger.info("Valkey rate limiter probe: reachable")
        except Exception as probe_exc:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError(
                    f"RATE_LIMITER_MODE={settings.RATE_LIMITER_MODE} but Valkey is "
                    f"unreachable at startup: {probe_exc}. "
                    f"Fix the Valkey connection or set RATE_LIMITER_MODE=memory "
                    f"(only safe for UVICORN_WORKERS=1)."
                ) from probe_exc
            else:
                logger.warning(
                    f"RATE_LIMITER_MODE={settings.RATE_LIMITER_MODE} but Valkey is "
                    f"unreachable at startup: {probe_exc}. "
                    f"Continuing since ENVIRONMENT={settings.ENVIRONMENT}, but rate limiting "
                    f"will fall back to in-memory (split-brain if UVICORN_WORKERS > 1)."
                )

    # ── Inject core → infra boundary dependencies ──
    # Inverts the dependency: core defines ports, infra provides impls.
    try:
        from reasoner.core.ports.model_registry_port import set_model_registry_port
        from reasoner.core.search import set_build_provider
        from reasoner.infrastructure.llm.registry import RegistryAdapter, build_provider
        set_build_provider(build_provider)
        set_model_registry_port(RegistryAdapter())
        logger.info("Core→infra dependencies injected: build_provider, model_registry_port")
    except Exception as exc:
        logger.warning("Failed to inject core→infra deps: %s", exc)

    # Memory is best-effort: a broken neuro config must not stop the app, it
    # just leaves get_memory_port() returning None and recall returning [].
    try:
        from reasoner.core.ports.memory_port import set_memory_port
        from reasoner.neuro.server import get_neuro_service

        set_memory_port(get_neuro_service())
    except Exception as exc:
        logger.warning("Memory port unavailable, neuro recall disabled: %s", exc)

    logger.info("Reasoner startup complete")
    logger.info(f"Web UI: http://{settings.SERVER_HOST}:{settings.SERVER_PORT}")
    logger.info(f"API Docs: http://{settings.SERVER_HOST}:{settings.SERVER_PORT}/docs")
    logger.info(f"WebSocket: ws://{settings.SERVER_HOST}:{settings.SERVER_PORT}/ws")
    logger.info(f"Memory limit: {MEMORY_LIMIT_MB}MB (warning at {MEMORY_WARNING_MB}MB)")
    logger.info(f"Request timeout: {REQUEST_TIMEOUT_SECONDS}s")

    # Background task: update active users gauge (Critical Enhancement 7.3)
    _active_users_task = asyncio.create_task(_update_active_users_loop())

    # Background task: token cache eviction (B-18 fix)
    from reasoner.infrastructure.token_cache import get_token_cache
    _token_cache = get_token_cache()
    _cache_cleanup_task = await _token_cache.start_background_cleanup(interval_seconds=300)

    # Background task: nightly event store compaction (P2-A)
    from reasoner.application.services.compaction_service import run_nightly_compaction_loop
    if settings.DATABASE_URL:
        from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore
        _compaction_store = PostgreSQLEventStore(settings.DATABASE_URL, pool_size=5)
        await _compaction_store.initialize()
    else:
        from reasoner.infrastructure.persistence.event_store import get_event_store
        _compaction_store = get_event_store()
    _compaction_task = asyncio.create_task(
        run_nightly_compaction_loop(_compaction_store),
        name="event_store_compaction",
    )

    yield

    # Cancel background tasks on shutdown (reverse order)
    _compaction_task.cancel()
    try:
        await _compaction_task
    except asyncio.CancelledError:
        pass

    _cache_cleanup_task.cancel()
    try:
        await _cache_cleanup_task
    except asyncio.CancelledError:
        pass

    _active_users_task.cancel()
    try:
        await _active_users_task
    except asyncio.CancelledError:
        pass

    # Drain event bus before closing connections
    await bus.stop()

    # ── Shutdown (each close wrapped in try/except so one failure doesn't skip others) ──
    global _event_store, _health_postgres_pool

    if _event_store and hasattr(_event_store, 'close'):
        try:
            _event_store.close()
        except Exception as exc:
            logger.warning("Event store close failed: %s", exc)

    try:
        from reasoner.infrastructure.llm.providers.openai_compat import OpenAICompatibleProvider
        await OpenAICompatibleProvider.close_shared_pool()
    except Exception as exc:
        logger.warning("OpenAI shared pool close failed: %s", exc)

    try:
        from reasoner.scraper import close_scraper_client
        await close_scraper_client()
    except Exception as exc:
        logger.warning("Scraper client close failed: %s", exc)

    try:
        # Close Valkey connection pool
        from reasoner.infrastructure.valkey.client import close_valkey_pool
        await close_valkey_pool()
    except Exception as exc:
        logger.warning("Valkey close failed: %s", exc)

    try:
        # Close shared neuro HTTP client (B4 fix — resource leak)
        from reasoner.clients import close_neuro_client
        await close_neuro_client()
    except Exception as exc:
        logger.warning("Neuro client close failed: %s", exc)

    try:
        # Close resilient neuro wrappers (Phase 0.4 — httpx leak)
        from reasoner.neuro.providers import close_all_resilient_wrappers
        await close_all_resilient_wrappers()
    except Exception as exc:
        logger.warning("Resilient wrapper close failed: %s", exc)

    try:
        # Close health-check Postgres pool
        if _health_postgres_pool is not None:
            await _health_postgres_pool.close()
            _health_postgres_pool = None
    except Exception as exc:
        logger.warning("Health-check Postgres pool close failed: %s", exc)
        _health_postgres_pool = None

    logger.info("Reasoner shutdown complete")


app = FastAPI(title="Reasoner v2.0", lifespan=lifespan)
register_exception_handlers(app)

# Add security middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add audit middleware (Critical Enhancement 6.3)
from reasoner.api.middleware import AuditMiddleware

app.add_middleware(AuditMiddleware)

# Add CORS middleware — production-aware (Critical Enhancement 6.1.2)
_env = settings.ENVIRONMENT
if _env == "production":
    _allowed_origins = [settings.APP_URL] if settings.APP_URL else []
else:
    _allowed_origins = settings.cors_origins_list
    logger.warning(
        "CORS is in development mode with allow_credentials=True. "
        "Ensure no malicious sites are running on allowed origins: %s",
        _allowed_origins,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=[
        "authorization",
        "content-type",
        "accept",
        "accept-language",
        "x-csrf-token",
        "x-requested-with",
    ],
    max_age=CORS_MAX_AGE_SECONDS,
)

# Initialize rate limiter
rate_limiter = get_rate_limiter(RateLimitConfig(
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    requests_per_hour=settings.RATE_LIMIT_PER_HOUR,
    burst_size=settings.RATE_LIMIT_BURST,
))

# Initialize auth manager
auth_manager = get_auth_manager()

from reasoner.infrastructure.llm.registry import _REGISTRY

# Neuro Integration
from reasoner.neuro.server import create_neuro_router

app.include_router(create_neuro_router())

# New Architecture Integration
from reasoner.application.handlers import get_handler_registry
from reasoner.application.queries import (
    GetPipelineStatusQuery,
)
from reasoner.infrastructure.persistence import get_event_store

# Widget Integrations (legacy fallback)

# Initialize new architecture components
_event_store = None
_handler_registry = None

def get_architecture_components():
    """Lazy initialization of new architecture components."""
    global _event_store, _handler_registry

    if _event_store is None:
        _event_store = get_event_store()

    if _handler_registry is None:
        # Create a simple router for new architecture components
        # Uses Claude as primary by default, falls back to legacy router for actual LLM calls
        from reasoner.infrastructure.llm.registry import _REGISTRY, build_provider

        # Try to get a primary provider (use first available OpenRouter model)
        primary_provider = None
        for model_id in sorted(_REGISTRY):
            if _REGISTRY[model_id].get("is_local"):
                continue
            try:
                primary_provider = build_provider(model_id)
                break
            except Exception:
                continue

        # If no provider available, create a dummy one
        if primary_provider is None:
            from reasoner.infrastructure.llm.providers.noop import NoopProvider
            primary_provider = NoopProvider(model="dummy")

        from reasoner.api.execution.pipeline import PipelineExecutionService
        _handler_registry = get_handler_registry(
            primary_provider, _event_store,
            pipeline_executor=PipelineExecutionService(),
        )

    return _event_store, _handler_registry


def _filter_routing(routing: dict[str, str], primary_id: str) -> dict[str, str]:
    """Drop routing entries whose API key is missing; fall back to primary."""
    filtered = {}
    for role, model_id in routing.items():
        entry = _REGISTRY.get(model_id, {})
        env = entry.get("env")
        if env and not os.environ.get(env):
            continue  # no key → omit, ProviderRouter falls back to primary
        filtered[role] = model_id
    return filtered

# Per-run cancellation tracking.
# Encapsulated in RunStateManager for testability and safe async locking.
# Redis-backed with in-memory fallback (Critical Enhancement 9.1–9.3, 9.7).
from reasoner.api.auth_deps import optional_auth, require_csrf
from reasoner.api.dependencies import (
    check_quota_if_authenticated,
    check_rate_limit,
    get_current_user,
    get_optional_user,
    get_pipeline_service,
    get_preset_service,
    get_search_service,
    require_credits_if_authenticated,
)
from reasoner.api.schemas import (
    FollowupRequest,
    RunRequest,
    SearchRequest,
)
from reasoner.api.streaming import (
    run_followup_stream,
    run_stream,
    run_stream_cached,
)
from reasoner.application.services.pipeline_service import PipelineService
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.search_service import SearchService
from reasoner.domain.saas import QuotaResult, User
from reasoner.infrastructure.redis.run_state import _run_state_manager as _run_store

# ─────────────────────────────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────────────────────────────
from .cache import (
    _MEMORY_CACHE,
    CACHE_DIR,
    _cache_key,
    _load_cache,
    _save_cache,
    clear_memory_cache,
)

# ─────────────────────────────────────────────────────────────────────
# SERIALIZERS — one per phase
# ─────────────────────────────────────────────────────────────────────
from .serializers import (
    _event,
    _is_debate,
    _is_orchestrated,
    _is_scientific,
    _is_socratic,
    _ser_0,
    _ser_1,
    _ser_1_5,
    _ser_2,
    _ser_3,
    _ser_4,
    _ser_5,
)

# ─────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────

@app.post("/api/csrf")
async def get_csrf_token():
    """Generate a signed CSRF token for frontend use."""
    from reasoner.api.csrf import generate_signed_csrf_token
    return {"token": generate_signed_csrf_token()}


def _extract_run_cost(chunk: str) -> float | None:
    """Pull ``total_cost_usd`` out of a terminal ``done`` SSE frame.

    Returns None for every other frame. Malformed frames are ignored rather
    than raised: a parsing problem must never break the stream the user is
    reading.
    """
    from reasoner.application.services.run_metering import extract_run_cost

    return extract_run_cost(chunk)


async def _run_stream_with_metrics(
    req: RunRequest,
    request: Request,
    user: User | None,
    preset_service: PresetService,
    pipeline_service: PipelineService,
    *,
    reference_id: str,
    reserved_credits: int = 0,
):
    """Stream a run through the shared metering wrapper.

    Settlement, disconnect handling, and metrics all live in
    ``application/services/run_metering.py`` so the sync endpoint and the MCP
    adapter bill a run exactly the way this one does.

    ``reference_id``/``reserved_credits`` come from the caller, which already
    reserved this run's estimated cost (``reserve_run_budget``, called before
    ``StreamingResponse`` is constructed so an ``InsufficientCreditsError``
    can still become a clean 402 -- a generator body is too late for that,
    the response has already started).
    """
    from reasoner.logging_utils import set_log_context

    tier = "anonymous" if user is None else "free"
    preset = req.preset or "auto-budget"
    set_log_context(user_id=str(user.id) if user else None, tier=tier, preset=preset)

    # Metrics are optional — degrade gracefully if QueryTimer is missing
    timer = None
    try:
        from reasoner.api.metrics import QueryTimer
        timer = QueryTimer(preset=preset)
        timer.start()
    except (ImportError, AttributeError):
        pass

    from reasoner.api.run_observability import CreditSink, PrometheusObserver
    from reasoner.application.services.run_metering import RunContext, metered

    user_id = str(user.id) if user else None
    ctx = RunContext(
        preset=preset,
        reference_id=reference_id,
        user_id=user_id,
        tier=tier,
        interface="web",
        reserved_credits=reserved_credits,
    )
    stream = run_stream_cached(
        req,
        request=request,
        user_id=user_id,
        preset_service=preset_service,
        pipeline_service=pipeline_service,
    )
    async for chunk in metered(
        stream,
        ctx,
        CreditSink(),
        PrometheusObserver(tier=tier, preset=preset, interface="web", timer=timer),
    ):
        yield chunk


async def _run_followup_stream_with_metrics(
    req: FollowupRequest,
    request: Request,
    user: User | None,
    *,
    reference_id: str,
    reserved_credits: int = 0,
):
    """Stream a follow-up run through the shared metering wrapper.

    A follow-up costs real LLM spend, and the caller has already *debited* the
    estimate against the user's balance before this generator starts. Only
    ``metered()``'s finally -> _true_up -> sink.release gives that hold back and
    settles the run's actual cost, so streaming the raw generator (as this
    endpoint did) charged every follow-up turn the full worst-case estimate,
    permanently, and never billed what the run really used. Mirrors
    _run_stream_with_metrics above -- the reservation and the settlement must
    share one reference_id.
    """
    from reasoner.logging_utils import set_log_context
    from reasoner.api.run_observability import CreditSink, PrometheusObserver
    from reasoner.application.services.run_metering import RunContext, metered

    tier = "anonymous" if user is None else "free"
    preset = req.preset or "auto-budget"
    user_id = str(user.id) if user else None
    set_log_context(user_id=user_id, tier=tier, preset=preset)

    timer = None
    try:
        from reasoner.api.metrics import QueryTimer
        timer = QueryTimer(preset=preset)
        timer.start()
    except (ImportError, AttributeError):
        pass

    ctx = RunContext(
        preset=preset,
        reference_id=reference_id,
        user_id=user_id,
        tier=tier,
        interface="web",
        reserved_credits=reserved_credits,
    )
    stream = run_followup_stream(req, request=request, user_id=user_id)
    async for chunk in metered(
        stream,
        ctx,
        CreditSink(),
        PrometheusObserver(tier=tier, preset=preset, interface="web", timer=timer),
    ):
        yield chunk


def _require_auth_if_legacy_disabled(user: User | None) -> None:
    """Backward-compat gate: require auth when legacy API key mode is disabled."""
    if user is None and not settings.ENABLE_LEGACY_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Set ENABLE_LEGACY_API_KEY=true for v1 backward compatibility.",
        )


# ── Agent-Facing Endpoints ──────────────────────────────────────
# Moved to reasoner.api.routes.agent: bearer-key auth (account keys or JWT,
# via get_current_user), idempotency-guarded, and metered identically to a
# web run. See that module's docstring for why this replaced the previous
# require_api_key-authenticated, unmetered handlers.

from reasoner.api.routes.agent import router as agent_router

app.include_router(agent_router)


# ── Main pipeline endpoint ───────────────────────────────────────


@app.post("/api/run")
async def run_pipeline(
    request: Request,
    req: RunRequest,
    user: User | None = Depends(get_optional_user),
    authenticated = Depends(optional_auth),
    rate_limit_checked = Depends(check_rate_limit),
    quota: QuotaResult | None = Depends(check_quota_if_authenticated),
    credits_checked = Depends(require_credits_if_authenticated),
    csrf_checked = Depends(require_csrf),
    preset_service: PresetService = Depends(get_preset_service),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
):
    """
    Run pipeline with optional authentication and rate limiting.

    Authenticated users get higher rate limits and priority processing.
    """
    _require_auth_if_legacy_disabled(user)
    from reasoner.api.idempotency_http import register_run_or_error

    await register_run_or_error(req.client_run_id)

    from reasoner.api.dependencies import reserve_or_402

    reference_id = req.client_run_id or f"run:{uuid.uuid4()}"
    preset = req.preset or "auto-budget"

    if user is None:
        # No account to reserve credits against -- capped separately so
        # anonymous traffic stays bounded regardless (Phase 2 metering).
        from reasoner.api.client_ip import get_client_ip
        from reasoner.application.services.anonymous_trial_policy import (
            enforce_anonymous_trial_cap,
        )
        from reasoner.application.services.estimate_service import estimate_cost

        estimate = await estimate_cost(req.problem, preset)
        await enforce_anonymous_trial_cap(get_client_ip(request), estimate["estimated_cost_usd"])

    reserved_credits = await reserve_or_402(
        user_id=str(user.id) if user else None,
        preset=preset,
        problem=req.problem,
        reference_id=reference_id,
    )

    # TODO(#502): use actual user tier from subscription DB
    return StreamingResponse(
        _run_stream_with_metrics(
            req, request, user, preset_service, pipeline_service,
            reference_id=reference_id, reserved_credits=reserved_credits,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-RateLimit-Limit": str(request.state.rate_limit_info.get("limit_minute")),
            "X-RateLimit-Remaining": str(request.state.rate_limit_info.get("remaining_minute")),
        },
    )


@app.post("/api/run-followup")
async def run_followup_pipeline(
    request: Request,
    req: FollowupRequest,
    user: User | None = Depends(get_optional_user),
    authenticated = Depends(optional_auth),
    rate_limit_checked = Depends(check_rate_limit),
    quota: QuotaResult | None = Depends(check_quota_if_authenticated),
    credits_checked = Depends(require_credits_if_authenticated),
    csrf_checked = Depends(require_csrf),
):
    """
    Run the Reasoner pipeline for a follow-up question with full conversation context.

    Carries the same gates as ``/api/run``: a follow-up runs the identical
    pipeline at identical cost, so quota, credits, and the anonymous trial cap
    all have to apply here too. Without them an anonymous caller could hand-build
    a conversation payload and run unbounded premium pipelines on the operator's
    provider keys behind nothing but the per-IP rate limiter.
    """
    _require_auth_if_legacy_disabled(user)
    from reasoner.api.idempotency_http import register_run_or_error
    from reasoner.api.dependencies import reserve_or_402

    if user is None:
        from reasoner.api.client_ip import get_client_ip
        from reasoner.application.services.anonymous_trial_policy import (
            enforce_anonymous_trial_cap,
        )
        from reasoner.application.services.estimate_service import estimate_cost

        estimate = await estimate_cost(req.question, req.preset or "auto-budget")
        await enforce_anonymous_trial_cap(get_client_ip(request), estimate["estimated_cost_usd"])

    await register_run_or_error(req.client_run_id)
    reference_id = req.client_run_id or f"followup:{uuid.uuid4()}"
    reserved_credits = await reserve_or_402(
        user_id=str(user.id) if user else None,
        preset=req.preset or "auto-budget",
        problem=req.question,
        reference_id=reference_id,
    )
    return StreamingResponse(
        _run_followup_stream_with_metrics(
            req, request, user,
            reference_id=reference_id, reserved_credits=reserved_credits,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-RateLimit-Limit": str(request.state.rate_limit_info.get("limit_minute")),
            "X-RateLimit-Remaining": str(request.state.rate_limit_info.get("remaining_minute")),
        },
    )


@app.post("/api/search")
async def search_web(
    req: SearchRequest,
    user: User | None = Depends(get_optional_user),
    rate_limit_checked = Depends(check_rate_limit),
    search_service: SearchService = Depends(get_search_service),
):
    _require_auth_if_legacy_disabled(user)
    """
    Advanced web search via multi-backend search pipeline.
    Returns raw discovery results. When smart=True, the query is decomposed
    into focused sub-queries via a lightweight LLM, searched in parallel,
    deduplicated, and grouped.
    """
    try:
        from reasoner.core.search import smart_search

        if req.smart:
            results = await smart_search(
                req.query,
                source_type=req.source_type,
                num_results=req.num_results,
            )
        else:
            results = await search_service.search(
                req.query,
                source_type=req.source_type,
                num_results=req.num_results,
            )
        return {
            "query": req.query,
            "source_type": req.source_type,
            "results": results,
        }
    except Exception as exc:
        logger.warning(f"Web search failed: {exc}")
        raise HTTPException(status_code=503, detail=f"Search unavailable: {str(exc)}") from exc


@app.delete("/api/cache", dependencies=[Depends(check_rate_limit)])
async def clear_cache(
    request: Request,
    csrf_checked = Depends(require_csrf),
):
    # Cache deletion is destructive and global -- require the admin key in
    # every environment, not just production (security-remediation-plan.md
    # Phase 5 item 2: this used to be wide open outside production). An
    # operator without ADMIN_API_KEY configured at all (fresh local dev)
    # keeps today's frictionless behavior; anyone who HAS set the key must
    # present it, in every environment.
    #
    # `request: Request` must stay a required, non-Optional param — FastAPI
    # injects it via special-casing on the bare type; `Request | None = None`
    # breaks that special-casing and raises FastAPIError at route
    # registration (Request is not a valid Pydantic field type), which took
    # the whole app down at import time.
    from reasoner.api.admin_auth import verify_admin_key

    if settings.ADMIN_API_KEY and not verify_admin_key(request.headers.get("X-Admin-Key")):
        raise HTTPException(status_code=403, detail="Admin access required")
    cleared = 0
    for f in CACHE_DIR.glob("*.json"):
        try:
            f.unlink(missing_ok=True)
            cleared += 1
        except OSError:
            pass
    clear_memory_cache()
    logger.warning(
        "Cache invalidated: %d entries cleared (admin_key_configured=%s)",
        cleared,
        bool(settings.ADMIN_API_KEY),
    )
    return {"cleared": cleared}


@app.post("/api/stop")
async def stop_pipeline(
    run_id: str | None = None,
    user: User | None = Depends(get_optional_user),
    csrf_checked = Depends(require_csrf),
):
    """Cancel a running pipeline.

    Authenticated users can only cancel their own runs.
    Global stop (no run_id) requires admin scope.
    """
    # Detect whether we're in a real FastAPI call or a direct function call.
    # In direct calls, Depends() objects are passed through instead of resolved.
    from fastapi import params
    is_authenticated = isinstance(user, User)

    # If a specific run_id is provided, cancel only that run.
    if run_id:
        if not _run_store.is_active(run_id):
            return {"status": "not found", "cancelled": []}
        run_owner = _run_store.get_owner(run_id)
        # If the run has an owner, only that owner (or admin) can cancel it
        if run_owner and (not is_authenticated or str(user.id) != run_owner):
            user_scopes = getattr(user, "scopes", None) or []
            if "admin" not in user_scopes:
                raise HTTPException(
                    status_code=403,
                    detail="Cannot cancel another user's run",
                )
        targets = [run_id]
    else:
        # Global stop: admin only
        if not is_authenticated:
            raise HTTPException(
                status_code=401,
                detail="Authentication required for global stop",
            )
        # Check admin scope
        user_scopes = getattr(user, "scopes", None) or []
        if "admin" not in user_scopes:
            raise HTTPException(
                status_code=403,
                detail="Admin scope required for global stop",
            )
        targets = list(_run_store.active_runs)

    for rid in targets:
        await _run_store.request_cancel(rid)

    return {"status": "stop requested", "cancelled": targets}


# ─────────────────────────────────────────────────────────────────────
# FILE UPLOADS
# ─────────────────────────────────────────────────────────────────────

from reasoner.api.routes.uploads import router as uploads_router

app.include_router(uploads_router)

from reasoner.api.routes.images import router as images_router

app.include_router(images_router)

from reasoner.api.routes.provenance import router as provenance_router

app.include_router(provenance_router)


# ─────────────────────────────────────────────────────────────────────
# EXTERNAL CONTEXT INTEGRATION
# ─────────────────────────────────────────────────────────────────────

# ContextAnalysisRequest imported from .schemas


from reasoner.api.routes.context import router as context_router

app.include_router(context_router)

from reasoner.api.routes.widgets import router as widgets_router

app.include_router(widgets_router)

from reasoner.api.routes.pipelines import router as pipelines_router

app.include_router(pipelines_router)


# ─────────────────────────────────────────────────────────────────────
# LEGACY WIDGET ENDPOINTS (Fallback)
# ─────────────────────────────────────────────────────────────────────

from reasoner.api.routes.legacy_widgets import router as legacy_widgets_router

app.include_router(legacy_widgets_router)


# ─────────────────────────────────────────────────────────────────────
# SEARCH HISTORY
# ─────────────────────────────────────────────────────────────────────

from reasoner.api.routes.history import router as history_router

app.include_router(history_router)


from reasoner.api.routes.websocket import router as websocket_router

app.include_router(websocket_router)


# ─────────────────────────────────────────────────────────────────────
# API KEY VALIDATION ENDPOINT
# ─────────────────────────────────────────────────────────────────────

from reasoner.api.routes.keys import router as keys_router

app.include_router(keys_router)

from reasoner.api.routes.account_keys import router as account_keys_router
from reasoner.api.routes.credits import router as credits_router

app.include_router(credits_router)
app.include_router(account_keys_router)

from reasoner.api.routes.estimate import router as estimate_router
from reasoner.api.routes.feedback import router as feedback_router
from reasoner.api.routes.gate import router as gate_router

app.include_router(feedback_router)
app.include_router(estimate_router)
app.include_router(gate_router)

from reasoner.api.routes.gdpr import router as gdpr_router

app.include_router(gdpr_router)

from reasoner.api.routes.errors import router as errors_router

app.include_router(errors_router)

from reasoner.api.routes.health import router as health_router
from reasoner.api.routes.telemetry import router as telemetry_router

app.include_router(health_router)
app.include_router(telemetry_router)

from reasoner.api.routes.admin import router as admin_router

app.include_router(admin_router)

# Mount SaaS router
from reasoner.api import saas_router

app.include_router(saas_router.router)

# Mount Billing router
from reasoner.api import billing_router

app.include_router(billing_router.router)

# Optional MCP Streamable-HTTP transport, off by default. Most installs use
# the stdio transport (mcp_server.py) instead; this is for hosted deployments
# that want an MCP endpoint without a second process. A missing 'mcp' extra
# must not take the whole app down -- log and continue without it.
if settings.ENABLE_MCP_HTTP:
    try:
        from reasoner.api.mcp import build_mcp_server
        app.mount("/mcp", build_mcp_server().streamable_http_app())
    except ImportError as exc:
        logger.warning("ENABLE_MCP_HTTP is set but could not be mounted: %s", exc)

# Mount Metrics endpoint (Critical Enhancement 6.1: restrict by IP)
from reasoner.api.client_ip import get_client_ip
from reasoner.api.metrics import metrics_endpoint


async def _metrics_ip_restricted(request: Request):
    allowed = {item.strip() for item in settings.METRICS_ALLOWED_IPS.split(",") if item.strip()}
    client_ip = get_client_ip(request)
    if not allowed or client_ip not in allowed:
        raise HTTPException(status_code=403, detail="Metrics access denied")

app.add_api_route("/api/metrics", metrics_endpoint, methods=["GET"], dependencies=[Depends(_metrics_ip_restricted)])


# ─────────────────────────────────────────────────────────────────────
# MEMORY LIMITS & REQUEST TIMEOUT MIDDLEWARE
# ─────────────────────────────────────────────────────────────────────



# Note: 'resource' module is Unix-only, not available on Windows
# Memory limits use psutil instead


from reasoner.api.middleware import MemoryLimitMiddleware, RequestTimeoutMiddleware

# Add memory and timeout middleware (using centralized settings)
MEMORY_LIMIT_MB = settings.MEMORY_LIMIT_MB
MEMORY_WARNING_MB = settings.MEMORY_WARNING_MB
REQUEST_TIMEOUT_SECONDS = settings.REQUEST_TIMEOUT_SECONDS

app.add_middleware(
    MemoryLimitMiddleware,
    memory_limit_mb=MEMORY_LIMIT_MB,
    warning_mb=MEMORY_WARNING_MB,
)
app.add_middleware(
    RequestTimeoutMiddleware,
    timeout_seconds=REQUEST_TIMEOUT_SECONDS,
)


# ─────────────────────────────────────────────────────────────────────
# ROOT ENDPOINT
# ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "message": "Reasoner v2.0 API",
        "docs": "/docs",
        "health": "/api/health",
        "api": "/api/run",
    }


# ─────────────────────────────────────────────────────────────────────



# ─────────────────────────────────────────────────────────────────────
