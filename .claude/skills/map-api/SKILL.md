---
name: map-api
description: Folder map of src/reasoner/api — FastAPI HTTP/SSE/WebSocket/MCP driving adapters. Use when adding or changing endpoints, SSE streaming, auth dependencies, middleware, CSRF, billing/credits routes, or MCP tools, to find the right file without searching.
folders:
  - src/reasoner/api
---

# src/reasoner/api — Folder Map

**Purpose:** Driving adapters. Translates HTTP requests, SSE streams, WebSocket frames, and MCP tool calls into application-layer calls. No business logic lives here — routes call `application/handlers` and `application/services`. Three adapters share the same application core: HTTP routes (`routes/`), MCP tools (`mcp/`), and WebSocket (`routes/websocket.py`).

## Root files

| File | What it does |
|------|--------------|
| `__init__.py` (37KB) | App factory + `lifespan`; CORS, middleware, router mounting, `/api/run` streaming entry, CSRF token route, architecture-components endpoint, active-user loop. Largest file in the folder — most cross-cutting wiring lives here. |
| `admin_auth.py` | Shared `verify_admin_key` / `require_admin_key` primitive used by all five admin call sites. |
| `auth_deps.py` | FastAPI auth + rate-limit dependencies: `require_api_key`, `require_auth`, `optional_auth`, `get_client_id`. |
| `billing_router.py` | Stripe/PayPal checkout, portal, subscription, webhook endpoints. |
| `cache.py` | Two-tier response cache (memory + disk) with pruning; `_cache_key`, `get_cache_stats`, `clear_memory_cache`. |
| `client_ip.py` | `get_client_ip` — trusted-proxy-aware; only trusts X-Forwarded-For from `TRUSTED_PROXIES`. |
| `cron.py` | Periodic background jobs: `reset_all_quotas_monthly`, `run_neuro_maintenance`. |
| `csrf.py` | Stateless double-submit CSRF via HMAC-SHA256; must match the Next.js frontend implementation. |
| `dependencies.py` (26KB) | SaaS auth DI: resolves API keys/JWTs to users, quota + rate-limit gates, provisioning pool. |
| `error_handler.py` | Global exception handlers (HTTP, validation, generic); persists errors with request context. `register_error_handlers`. |
| `history.py` | Local run-history persistence helpers (`HistoryEntry`, `_list_history`, `_save_history_entry`). |
| `idempotency_http.py` | `register_run_or_error` — HTTP translation of the app-layer idempotency guard for `client_run_id`. |
| `metrics.py` | Prometheus scrape endpoint + `QueryTimer`. Metric *definitions* live in `reasoner/metrics.py`. |
| `middleware.py` | `SecurityHeadersMiddleware`, `AuditMiddleware` (IP anonymization, URL sanitizing), `MemoryLimitMiddleware`, `RequestTimeoutMiddleware`. |
| `phase_executor.py` | Phase→router-role hints, `get_phase_start_models`, `get_critical_phases`, `run_phase_with_keepalive`. |
| `run_observability.py` | `CreditSink` + `PrometheusObserver` — concrete bindings for `run_metering.metered()` protocols. |
| `run_state.py` | Shim → RunStateStore. |
| `saas_router.py` | `/me`, quota status, data export, account deletion, auth-event logging. |
| `schemas.py` | All Pydantic request/response models (`RunRequest`, `FollowupRequest`, `GenerateImageRequest`, …). |
| `sentry.py` | `init_sentry` — error tracking init. |
| `serializers.py` | Shim → `application/services/serializers.py`. Import from there in new code. |
| `sse_utils.py` | SSE frame formatting `_event`, WS fan-out `_broadcast_ws`, `_persist_event`. |
| `streaming.py` | Core SSE generators: `run_stream`, `run_followup_stream`, `run_stream_cached`, widget events, phase sub-agent lookup. |

## execution/

| File | What it does |
|------|--------------|
| `cancel.py` | `StreamingConnectionContext` — cancellation + WS broadcast wiring. |
| `direct.py` | HyperGate DIRECT/WEB_SEARCH streaming path with model fallback (`_stream_direct_answer`). |
| `pipeline.py` (35KB) | `PipelineExecutionService` — the imperative shell driving a full pipeline run for streaming. |
| `web_search.py` | `_stream_web_search_results`. |

## routes/

| File | What it does |
|------|--------------|
| `account_keys.py` | User-owned API keys: create (plaintext shown once), list, revoke. |
| `admin.py` | Admin ops: compaction, dead-letter list/replay, neuro maintenance, ACR status/leaderboard/profile/mode. |
| `agent.py` | Bearer-key agent API: `agent_tools`, `agent_run` (SSE), `agent_run_sync`, metered. |
| `context.py` | `run_with_context` — external context integration. |
| `credits.py` | Balance, ledger, credit pricing, admin grants. |
| `errors.py` | `POST /api/error-report` (client, unauthenticated) + admin error log. |
| `estimate.py` | `POST /api/estimate` — token/cost/duration estimate without running. |
| `feedback.py` | Feedback submission + admin stats. |
| `gate.py` | `POST /api/gate` — HyperGate decision without executing the pipeline. |
| `gdpr.py` | `erase_user_data`. |
| `health.py` | `/api/health` — subsystem pass/fail; public response omits internals. |
| `history.py` | History list/tagged/get/delete/clear. |
| `images.py` | Image generation with credit reserve/release, auto model select, provenance scrub. |
| `keys.py` | Provider API-key status + validation. |
| `legacy_widgets.py` | Weather, stocks, calculator, discover. |
| `pipelines.py` | Event-store stats, list/status/delete pipelines, resume (sync + SSE), ownership check. |
| `provenance.py` | Inspect/scrub/rewrite AI-provenance carriers in text and image metadata (C2PA/EXIF/XMP). |
| `telemetry.py` | Read-only harness scorecard. |
| `uploads.py` | Upload, list, fetch, delete files. |
| `websocket.py` | Ticket issue → handshake auth → `pipeline_websocket` live updates + stats. |
| `widgets.py` | UI status, presets/models listing, suggestions, widget execute/list/detect. |

## mcp/

| File | What it does |
|------|--------------|
| `__init__.py` | `build_mcp_server` — optional `mcp` extra; a driving adapter peer to HTTP. |
| `context.py` | Per-call bearer auth for MCP (`resolve_caller`, `McpAuthError`) — no FastAPI DI available here. |
| `tools.py` | Tool definitions; thin translation to the same calls `routes/agent.py` makes, with idempotency + billing. |

## Key entry points & gotchas

- App is built in `__init__.py`; `asgi.py` at repo root exposes it. Routers mount there, plus `saas_router.py` and `billing_router.py`.
- Streaming path: run route → `application/handlers` `RunPipelineCommandHandler` → `execution/pipeline.py` → `streaming.py` SSE generators → `sse_utils._event`.
- HyperGate DIRECT/WEB_SEARCH answers bypass the pipeline entirely via `execution/direct.py`.
- Serializers moved out: use `application/services/serializers.py`, not `api/serializers.py`.
- CSRF is double-submit HMAC — backend `csrf.py` and the Next.js proxy must agree. `CSRF_ENFORCE_BACKEND=false` in CI.
- Three auth surfaces exist: `auth_deps.py` (legacy/API key), `dependencies.py` (SaaS user/JWT/quota), `admin_auth.py` (admin key). Pick the matching one; don't add a fourth.
