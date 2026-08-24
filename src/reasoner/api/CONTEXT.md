# Context: Api

## Directory: `src/reasoner/api`

## Description
FastAPI endpoints, middleware, websocket routers, and API server entry points.

## Files
- **`__init__.py`**: Setup logger
- **`admin_auth.py`**: Shared admin-key verification primitive.
- **`auth_deps.py`**: Authentication and rate-limiting FastAPI dependencies.
- **`billing_router.py`**: FastAPI router for all billing endpoints.
- **`cache.py`**: In-memory hot-cache layer to avoid disk I/O on repeated identical requests.
- **`client_ip.py`**: Trusted-proxy-aware client IP resolution.
- **`cron.py`**: Background task handlers for periodic maintenance.
- **`csrf.py`**: Backend CSRF token generation and validation.
- **`dependencies.py`**: ── Rate Limiter Singleton ──
- **`error_handler.py`**: Lazy import to avoid circular deps
- **`history.py`**: Code or resource asset facilitating system functionality.
- **`idempotency_http.py`**: HTTP translation for the application-layer idempotency guard.
- **`metrics.py`**: Prometheus metrics endpoints (FastAPI layer).
- **`middleware.py`**: Critical Enhancement 6.5: CSP header
- **`phase_executor.py`**: ── Phase Role Hints (maps phase name → router role keys) ────────────
- **`run_observability.py`**: HTTP-layer bindings for ``run_metering``'s Protocols.
- **`run_state.py`**: Backward-compatibility shim for RunStateStore.
- **`saas_router.py`**: SaaS Router — All new SaaS-related API endpoints.
- **`schemas.py`**: Pydantic request/response schemas for the Reasoner API.
- **`sentry.py`**: Sentry initialization for FastAPI.
- **`serializers.py`**: Backward-compat shim — serializers moved to application/services/serializers.py.
- **`sse_utils.py`**: SSE protocol utilities shared across streaming endpoints.
- **`streaming.py`**: SSE protocol helpers shared across streaming endpoints.

## Subfolders
- **`execution`**: Execution layer for handling active pipeline jobs, task queues, and asynchronous processing.
- **`mcp`**: Model Context Protocol (MCP) server integration allowing external agents to query the Reasoner codebase or invoke backend functions.
- **`routes`**: The distinct REST and SSE endpoint routers (e.g. running, configuration, billing, neuro states).
