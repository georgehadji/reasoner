from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager

import asyncio
import json
from fastapi import FastAPI, Request, Depends, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from reasoner.core.settings import settings
from reasoner.core.constants import (
    CORS_MAX_AGE_SECONDS,
    TRUNCATION,
)
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from datetime import datetime, timezone
import logging

# Setup logger
logger = logging.getLogger(__name__)

# SafeLoggingFilter is installed at the package level in reasoner/__init__.py
# so it applies to CLI, tests, and all entry points — not just the API.

# Initialize Sentry (Critical Enhancement 7.2)
from reasoner.api.sentry import init_sentry
init_sentry()

# --- Action 1.2: Observability Strictness & Metrics --- START
if settings.ENVIRONMENT == "production":
    # Any one configured backend satisfies the gate — see api/observability.py
    # for why this is no longer Langfuse-specific.
    from reasoner.api.observability import require_observability_backend

    logger.info(
        "Observability backends active: %s", ", ".join(require_observability_backend())
    )

    if settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY:
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
from reasoner.rate_limiter import get_rate_limiter, RateLimitConfig
from reasoner.auth import get_auth_manager, AuthenticationError

from reasoner.api.middleware import SecurityHeadersMiddleware

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
    from reasoner.application.event_bus.bus import init_default_subscribers, get_event_bus
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
            # Raise in any non-development environment, not just production.
            if settings.ENVIRONMENT != "development":
                logger.critical(message)
                raise RuntimeError(
                    f"Unsafe rate limiter configuration: RATE_LIMITER_MODE=memory with "
                    f"UVICORN_WORKERS={uvicorn_workers} in {settings.ENVIRONMENT}. "
                    f"Set RATE_LIMITER_MODE=redis."
                )
            logger.warning(message)
        if settings.CIRCUIT_BREAKER_MODE == "memory":
            logger.warning(
                "Circuit breaker is in 'memory' mode but UVICORN_WORKERS=%d. "
                "Circuit state is not shared across workers. "
                "Set CIRCUIT_BREAKER_MODE to a shared backend (e.g., 'redis') for production.",
                uvicorn_workers,
            )

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
            raise RuntimeError(
                f"RATE_LIMITER_MODE={settings.RATE_LIMITER_MODE} but Valkey is "
                f"unreachable at startup: {probe_exc}. "
                f"Fix the Valkey connection or set RATE_LIMITER_MODE=memory "
                f"(only safe for UVICORN_WORKERS=1)."
            ) from probe_exc

    # ── Inject core → infra boundary dependencies ──
    # Inverts the dependency: core defines ports, infra provides impls.
    try:
        from reasoner.core.search import set_build_provider
        from reasoner.infrastructure.llm.registry import build_provider
        set_build_provider(build_provider)
        logger.info("Core→infra dependencies injected: build_provider")
    except Exception as exc:
        logger.warning("Failed to inject core→infra deps: %s", exc)

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
        _compaction_store = PostgreSQLEventStore(settings.DATABASE_URL)
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
from reasoner.infrastructure.persistence import get_event_store
from reasoner.application.handlers import get_handler_registry
from reasoner.application.queries import (
    GetPipelineStatusQuery,
)


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
        from reasoner.infrastructure.llm.registry import build_provider, _REGISTRY
        
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
from reasoner.infrastructure.redis.run_state import _run_state_manager as _run_store

# ─────────────────────────────────────────────────────────────────────
# CACHE
# ─────────────────────────────────────────────────────────────────────

from .cache import (
    CACHE_DIR,
    _MEMORY_CACHE,
    _cache_key,
    clear_memory_cache,
    _load_cache,
    _save_cache,
)


from reasoner.api.schemas import (
    FollowupRequest,
    RunResult,
    RunRequest,
    SearchRequest,
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


from reasoner.api.streaming import (
    run_followup_stream,
    run_stream,
    run_stream_cached,
)

from reasoner.api.auth_deps import optional_auth, require_api_key, require_csrf
from reasoner.api.dependencies import (
    check_rate_limit, 
    get_current_user, 
    get_optional_user, 
    check_quota_if_authenticated,
    check_preset_access_if_authenticated,
    get_preset_service,
    get_pipeline_service,
    get_search_service
)
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.pipeline_service import PipelineService
from reasoner.application.services.search_service import SearchService
from reasoner.domain.saas import User, QuotaResult

# ─────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────

@app.post("/api/csrf")
async def get_csrf_token():
    """Generate a signed CSRF token for frontend use."""
    from reasoner.api.csrf import generate_signed_csrf_token
    return {"token": generate_signed_csrf_token()}


async def _run_stream_with_metrics(
    req: RunRequest,
    request: Request,
    user: User | None,
    preset_service: PresetService,
    pipeline_service: PipelineService,
):
    """Wrap run_stream_cached with Prometheus metrics."""
    from reasoner.logging_utils import set_log_context

    tier = "anonymous" if user is None else "free"
    preset = req.preset or "auto-budget"
    set_log_context(user_id=str(user.id) if user else None, tier=tier, preset=preset)

    # Metrics are optional — degrade gracefully if QueryTimer is missing
    timer = None
    try:
        from reasoner.metrics import REASONER_QUERIES_TOTAL
        from reasoner.api.metrics import QueryTimer
        timer = QueryTimer(preset=preset)
        timer.start()
    except (ImportError, AttributeError):
        pass

    has_error = False
    try:
        async for chunk in run_stream_cached(
            req,
            request=request,
            user_id=str(user.id) if user else None,
            preset_service=preset_service,
            pipeline_service=pipeline_service,
        ):
            yield chunk
    except Exception:
        has_error = True
        raise
    finally:
        if timer is not None:
            timer.observe()
        try:
            REASONER_QUERIES_TOTAL.labels(
                tier=tier,
                preset=preset,
                status="error" if has_error else "success",
            ).inc()
        except Exception as exc:
            logger.warning("Failed to record prometheus query metrics: %s", exc)


def _require_auth_if_legacy_disabled(user: User | None) -> None:
    """Backward-compat gate: require auth when legacy API key mode is disabled."""
    if user is None and not settings.ENABLE_LEGACY_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Set ENABLE_LEGACY_API_KEY=true for v1 backward compatibility.",
        )


# ── Agent-Facing Endpoints ──────────────────────────────────────
# These use Authorization: Bearer <key> instead of CSRF tokens,
# making them callable by AI agents (Claude, LangChain, curl, etc.).


@app.post("/api/agent/tools", include_in_schema=False)
async def agent_tools():
    """Return compact function-calling schema for agent consumption."""
    return [
        {
            "name": "reasoner_run",
            "description": "Run a multi-model reasoning pipeline on a problem. Returns SSE stream of events.",
            "endpoint": "POST /api/agent/run",
            "parameters": {
                "problem": {"type": "string", "required": True, "description": "The question or problem to reason about"},
                "preset": {"type": "string", "required": False, "default": "scientific-budget", "description": "Pipeline preset name"},
                "top_k": {"type": "integer", "required": False, "default": 2},
                "source_type": {"type": "string", "required": False, "enum": ["general", "academic", "news"]},
            },
            "auth": "Bearer API key in Authorization header",
        },
        {
            "name": "reasoner_run_sync",
            "description": "Run pipeline and return aggregated JSON result. Best for agents that want a single response.",
            "endpoint": "POST /api/agent/run/sync",
            "parameters": {
                "problem": {"type": "string", "required": True, "description": "The question or problem to reason about"},
                "preset": {"type": "string", "required": False, "default": "scientific-budget"},
                "top_k": {"type": "integer", "required": False, "default": 2},
            },
            "auth": "Bearer API key in Authorization header",
        },
        {
            "name": "reasoner_health",
            "description": "Check if Reasoner is running and healthy.",
            "endpoint": "GET /api/health",
            "parameters": {},
            "auth": "None",
        },
    ]


@app.post("/api/agent/run")
async def agent_run_pipeline(
    request: Request,
    req: RunRequest,
    api_key = Depends(require_api_key),
    rate_limit_checked = Depends(check_rate_limit),
):
    """Run pipeline with API key auth. No CSRF token needed — designed for agents.

    Returns SSE stream identical to /api/run.
    """
    from reasoner.api.streaming import run_stream_cached
    return StreamingResponse(
        run_stream_cached(req, request=request, user_id=api_key.name),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/agent/run/sync", response_model=RunResult)
async def agent_run_sync(
    request: Request,
    req: RunRequest,
    api_key = Depends(require_api_key),
    rate_limit_checked = Depends(check_rate_limit),
):
    """Run pipeline synchronously and return aggregated JSON result.

    Best for agents that want a single response without parsing SSE.
    """
    from reasoner.api.streaming import run_stream_cached
    events: list[dict] = []
    errors: list[str] = []

    async for sse_line in run_stream_cached(req, request=request, user_id=api_key.name):
        if sse_line.startswith("data: "):
            try:
                ev = json.loads(sse_line[6:])
                events.append(ev)
                if ev.get("type") == "error":
                    errors.append(str(ev.get("error", "")))
            except json.JSONDecodeError:
                pass

    # Extract synthesis from the last phase_complete with core_solution (reverse search)
    synthesis = ""
    for ev in reversed(events):
        if ev.get("type") == "phase_complete":
            data = ev.get("data", {})
            core = data.get("core_solution", "") or data.get("core_solution", "")
            if isinstance(core, dict):
                core = core.get("core_solution", "") or core.get("synthesis", "")
            if core and isinstance(core, str):
                synthesis = core
                break

    done = next((e for e in events if e.get("type") in ("done", "end")), {})
    models_used = list(dict.fromkeys(
        m for e in events if e.get("type") == "phase_complete"
        for m in (e.get("data", {}).get("models", []) if isinstance(e.get("data"), dict) else [])
    ))

    return RunResult(
        preset=req.preset,
        errors=errors,
        total_tokens=done.get("total_tokens", {"input": 0, "output": 0, "total": 0}),
        duration_seconds=done.get("duration", 0.0),
        synthesis=synthesis,
        critical_insights=done.get("critical_insights", []),
        open_questions=done.get("open_questions", []),
        citations=done.get("citations", []),
        models_used=models_used,
    )


# ── Main pipeline endpoint ───────────────────────────────────────


@app.post("/api/run")
async def run_pipeline(
    request: Request,
    req: RunRequest,
    user: User | None = Depends(get_optional_user),
    authenticated = Depends(optional_auth),
    rate_limit_checked = Depends(check_rate_limit),
    quota: QuotaResult | None = Depends(check_quota_if_authenticated),
    csrf_checked = Depends(require_csrf),
    preset_service: PresetService = Depends(get_preset_service),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
):
    """
    Run pipeline with optional authentication and rate limiting.

    Authenticated users get higher rate limits and priority processing.
    """
    _require_auth_if_legacy_disabled(user)
    await check_preset_access_if_authenticated(req.preset, user)
    # Idempotency: atomically register client_run_id (C2)
    if req.client_run_id:
        from reasoner.infrastructure.redis.run_state import _run_state_manager
        try:
            if not await _run_state_manager.is_authoritative():
                raise HTTPException(
                    status_code=503,
                    detail="Run state store unavailable. Retry after Redis recovers.",
                    headers={"Retry-After": "10"},
                )
            if not await _run_state_manager.try_register(req.client_run_id):
                raise HTTPException(
                    status_code=409,
                    detail=f"Run {req.client_run_id} is already in progress",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Idempotency check failed due to run-state store error: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Idempotency check failed due to temporary storage issue. Please try again.",
                headers={"Retry-After": "5"},
            ) from exc
    # TODO(#502): use actual user tier from subscription DB
    return StreamingResponse(
        _run_stream_with_metrics(req, request, user, preset_service, pipeline_service),
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
    rate_limit_checked = Depends(check_rate_limit),
    csrf_checked = Depends(require_csrf),
):
    """
    Run the Reasoner pipeline for a follow-up question with full conversation context.
    """
    _require_auth_if_legacy_disabled(user)
    await check_preset_access_if_authenticated(req.preset, user)
    # Idempotency: atomically register client_run_id (Phase 2.1)
    if req.client_run_id:
        from reasoner.infrastructure.redis.run_state import _run_state_manager
        try:
            if not await _run_state_manager.is_authoritative():
                raise HTTPException(
                    status_code=503,
                    detail="Run state store unavailable. Retry after Redis recovers.",
                    headers={"Retry-After": "10"},
                )
            if not await _run_state_manager.try_register(req.client_run_id):
                raise HTTPException(
                    status_code=409,
                    detail=f"Run {req.client_run_id} is already in progress",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Idempotency check failed for followup: %s", exc)
            raise HTTPException(
                status_code=503,
                detail="Idempotency check failed due to temporary storage issue. Please try again.",
                headers={"Retry-After": "5"},
            ) from exc
    return StreamingResponse(
        run_followup_stream(req, request=request, user_id=str(user.id) if user else None),
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
        if req.smart:
            from reasoner.core.search import smart_search

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


@app.delete("/api/cache")
async def clear_cache(
    csrf_checked = Depends(require_csrf),
):
    cleared = 0
    for f in CACHE_DIR.glob("*.json"):
        try:
            f.unlink(missing_ok=True)
            cleared += 1
        except OSError:
            pass
    clear_memory_cache()
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

from reasoner.api.routes.feedback import router as feedback_router
from reasoner.api.routes.estimate import router as estimate_router
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

# Mount Metrics endpoint (Critical Enhancement 6.1: restrict by IP)
from reasoner.api.metrics import metrics_endpoint

from reasoner.api.client_ip import get_client_ip


async def _metrics_ip_restricted(request: Request):
    allowed = settings.METRICS_ALLOWED_IPS.split(",")
    client_ip = get_client_ip(request)
    if client_ip not in allowed:
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
