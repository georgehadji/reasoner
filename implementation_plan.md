# Reasoner v2.0 — Implementation Plan

> **Generated:** 2025-07-17
> **Based on:** Multi-dimension code audit (19 findings, 5 P1 / 10 P2 / 4 P3)
> **Epistemic labels:** [VF] Verified in code, [HY] Hypothesis, [ES] Estimate

---

## 1. EXECUTIVE SUMMARY

This plan addresses **19 findings** from a structured audit of the Reasoner backend (Python 3.12+ / FastAPI 0.115). The system is a multi-model reasoning pipeline orchestrator supporting 19+ reasoning methods, SSE streaming, HyperGate pre-routing, neuro memory, multi-provider LLM routing, and multi-backend web search.

**Health snapshot:** No P0s (data loss, security breach, or active crash). Five P1s represent issues that **will manifest in production under normal usage within 30 days**. Ten P2s are scaling/edge-case concerns. Four P3s are tech debt.

**Key P1s — "fix first":**
1. **SSE preflight silence** — user sees empty spinner for 0.5–5s before any event; preflight errors yield no error event (documented known issue)
2. **Race-condition preset reload** — `importlib.reload()` of `presets.py` on first pipeline run can corrupt module state under concurrency (documented known issue)
3. **SafeLoggingFilter not installed for CLI paths** — PII leakage risk when `main.py` or scripts import `reasoner` without going through `api/__init__.py`
4. **In-memory run state fallback accepts duplicates** — the `try_register` idempotency gate succeeds even when Redis is down (single-worker only, but the fallback path doesn't reject)
5. **SQLite `busy_timeout` not set** — multi-worker dev deployments can hit `SQLITE_BUSY`

**Estimated effort:** ~16 developer-days across two 2-week sprints.

---

## 2. CURRENT ARCHITECTURE ASSESSMENT

### 2.1 Module Map

```
asgi.py                          ← uvicorn entry point
src/reasoner/
├── api/                         ← FastAPI app, SSE streaming, middleware, routes
│   ├── __init__.py              ← App factory, lifespan, endpoint registration
│   ├── streaming.py             ← SSE generators (run_stream, run_followup_stream, run_stream_cached)
│   ├── middleware.py            ← SecurityHeaders, Audit, MemoryLimit, RequestTimeout
│   ├── phase_executor.py        ← Phase execution with keepalive
│   ├── sse_utils.py             ← Shared SSE protocol helpers
│   └── routes/                  ← Modularized endpoint routers
├── application/                 ← CQRS layer
│   ├── orchestrator.py          ← PipelineOrchestrator: preflight → execute → postflight
│   ├── pipeline.py              ← ReasonerPipeline (strategy-based, 19 phases)
│   ├── commands/                ← Command objects
│   ├── handlers/                ← Command handlers (CQRS)
│   ├── event_bus/               ← In-process event bus + subscribers
│   ├── flows/                   ← Workflow strategy per method
│   └── services/                ← PresetService, PipelineService, SearchService, etc.
├── hypergate/                   ← Pre-flight routing (GateAgent + sub-agents)
├── infrastructure/              ← Adapters (ports→impl)
│   ├── llm/                     ← LLM providers, router, registry, executor
│   │   ├── router.py            ← ProviderRouter with fallback chains
│   │   ├── registry.py          ← Model whitelist + provider factory
│   │   ├── base.py              ← BaseLLMProvider + retry logic
│   │   └── providers/           ← OpenRouter, OpenAI-compat, direct, fine-tuned
│   ├── persistence/             ← EventStore (SQLite), PostgreSQLEventStore
│   ├── redis/                   ← Redis client, run_state, in_memory fallback, Lua scripts
│   ├── search/                  ← Brave, Tavily adapters
│   └── circuit_breaker.py       ← In-memory circuit breaker registry
├── core/                        ← Domain-agnostic constants, settings, exceptions
│   ├── settings.py              ← Centralized env-var reader (singleton)
│   ├── exceptions.py            ← Exception taxonomy (ReasonerError hierarchy)
│   └── constants*.py            ← Model IDs, limits, prompts, temperatures
├── phases/                      ← 19+ phase modules (scientific, debate, bayesian, …)
├── subagents/                   ← Critique, Decomposition, Enhancement, Search, Synthesis
├── neuro/                       ← Memory recall/learn server
├── domain/                      ← Domain types (PipelineState, PresetRegistry, models)
└── presets.py                   ← Preset definitions + auto-preset builder
```

### 2.2 Data Flow (Pipeline Request)

```
POST /api/run
  → rate_limiter.check()
  → csrf.verify()
  → auth (optional)
  → idempotency: try_register(client_run_id)  [Redis SET NX]
  → StreamingResponse(run_stream_cached())
      → cache lookup (disk JSON)
      → run_stream()
          → PipelineOrchestrator.preflight()
              → PresetService.resolve()        [reads presets.py]
              → PresetService.build_router()   [validates _REGISTRY]
              → Neuro recall (HTTP POST)       [optional LLM call]
              → GateAgent.decide()             [LLM call, 500ms–3s]
              → (auto-method) rebuild router
          → ReasonerPipeline.run()             [phase-by-phase SSE emission]
              → Phase 1..N: ProviderRouter.call() per role
                  → circuit_breaker.check()
                  → LLM semaphore (30)
                  → BaseLLMProvider.complete_with_retry()  [3 retries]
                      → OpenRouterProvider.complete()
                  → fallback chain (router-level)
              → SSE events: phase_start, phase_chunk, phase_complete
          → Orchestrator.postflight()
              → Neuro learn (HTTP POST)
              → Telemetry persist
              → History save
```

### 2.3 Architecture Strengths

- **Clean CQRS separation** — commands, handlers, event bus are well-partitioned
- **Provider abstraction** — `BaseLLMProvider` with OpenRouter, direct, and OpenAI-compat impls; circuit breaker per model
- **Fallback chains** — router-level fallback + multi-provider direct fallback (Anthropic/OpenAI/Google)
- **Idempotency** — Redis-backed `SET NX` for `client_run_id` dedup; fails closed (503) when Redis is down
- **Observability** — Langfuse tracing, Sentry error tracking, Prometheus metrics, structured audit logging
- **Security posture** — CSP, CSRF, rate limiting, IP anonymization, URL sanitization, SafeLoggingFilter

### 2.4 Architecture Weaknesses

- **Nested retries** — `BaseLLMProvider.complete_with_retry` (3×) + `ProviderRouter` fallback chain = up to 6+ retries
- **Module-level mutable globals** — `_GLOBAL_RESOLVED_CACHE`, `_LLM_CONCURRENCY_SEMAPHORE` are process-global singletons with no lifecycle hooks
- **Import-time side effects** — `api/__init__.py` installs `SafeLoggingFilter` on root logger; CLI paths skip this
- **Dual module organization** — 4+ backward-compat shims (`pipeline.py` → `application/pipeline.py`, `rate_limiter.py` → `infrastructure/rate_limiter.py`, …)
- **No `pyproject.toml`** — Ruff, pytest, and mypy configuration is implicit (defaults only); no version-controlled tool config
- **`Any`-typed dependencies** — `PipelineOrchestrator.__init__` accepts 5× `Any`-typed parameters

---

## 3. DETAILED IMPLEMENTATION PLAN

### 3.1 Phase Structure

| Phase | Duration | Focus | P1s Fixed | P2s Fixed |
|-------|----------|-------|-----------|-----------|
| **Sprint 1** | 2 weeks | Critical fixes (P1s) | 5 / 5 | 2 |
| **Sprint 2** | 2 weeks | Hardening (P2s) | — | 5 / 10 |
| **Backlog** | Ongoing | Tech debt (P3s) | — | 3 / 10 |

---

### 3.2 Sprint 1 — Critical Fixes (Weeks 1–2)

#### FIX-1: SSE Preflight Error Handling & Keepalive

| Field | Detail |
|-------|--------|
| **Objective** | Eliminate "empty spinner" — guarantee an SSE event within 200ms of connection; surface preflight errors as `error` events rather than silent hangs |
| **Severity** | P1 [VF] |
| **Affected components** | `api/streaming.py`, `application/orchestrator.py` |
| **Current behavior** | `run_stream()` creates `RunPipelineCommand` → handler calls `PipelineOrchestrator.preflight()` (1–2 LLM calls, 0.5–5s) → FIRST SSE event is `phase_start` AFTER preflight completes. If preflight throws, the `async for chunk in gen` loop in `run_stream_cached` catches nothing — the generator dies silently. |
| **Root cause** | `run_stream()` body has no yield before `preflight()`; the `run_task()` exception handler only does `traceback.print_exc()` and puts `None` — no error event is emitted |
| **Design change** | Three-part: **(a)** yield an immediate `preparing` keepalive event before any work; **(b)** wrap preflight in `try/except` that yields `error` events; **(c)** add a 5s composite timeout on preflight (HyperGate + neuro recall) |
| **Implementation tasks** |
| 1. In `api/streaming.py:run_stream()`, add a yield of `_event({"type": "preparing", "data": {}})` as the FIRST action inside the `run_task()` coroutine, before the handler import |
| 2. Wrap the `await handler.handle(command, sse_emit=sse_emit)` call in `try/except Exception` that calls `sse_emit({"type": "error", "error": str(e), "code": error_code_for_exception(e)})` |
| 3. In `application/orchestrator.py:preflight()`, add `asyncio.wait_for(..., timeout=5.0)` around the combined HyperGate + neuro recall block |
| 4. Add a `preflight_timed_out` boolean to `PreflightDecision` — when timeout fires, set `action="pipeline"` with a default multi-perspective method |
| **Refactoring** | Extract the HyperGate + neuro recall block into a private `_run_preflight_checks()` method for clarity and testability |
| **Testing strategy** | Unit: mock `GateAgent.decide()` to raise `asyncio.TimeoutError`, assert error event is yielded. Integration: start server, POST to `/api/run` with `OPENROUTER_API_KEY=""` (force provider failure), assert `preparing` event arrives within 200ms, assert `error` event arrives within 6s |
| **Acceptance criteria** | (1) `preparing` event is always the first SSE line emitted; (2) preflight errors produce `error` events, not silent disconnects; (3) preflight >5s auto-falls-back to pipeline |
| **Rollback** | Revert the `try/except` in `run_task()` — the `preparing` keepalive is additive and harmless to keep |

---

#### FIX-2: Safe Preset Reload Mechanism

| Field | Detail |
|-------|--------|
| **Objective** | Eliminate `importlib.reload()` race condition in preset resolution — replace with a safe, atomic registry update |
| **Severity** | P1 [VF] |
| **Affected components** | `api/streaming.py` (`_ensure_fresh_preset_service`), `application/services/preset_service.py`, `presets.py` |
| **Current behavior** | A function `_ensure_fresh_preset_service()` in `api/streaming.py` calls `importlib.reload()` on `presets` and related modules on the first pipeline run. This is documented in REASONIX.md as a known issue: "can break inline interpreters. Affects any code path importing presets mid-request." |
| **Root cause** | Module reload is a process-global mutation — concurrent requests see partially-reloaded modules; stale references in other modules persist |
| **Design change** | Replace import-time reload with a **file-watcher + atomic swap pattern**: `PresetService` holds an immutable snapshot of preset data; a background task polls `presets.py` mtime and atomically swaps the snapshot on change. No module reload. |
| **Implementation tasks** |
| 1. Add a `_preset_snapshot: dict` and `_preset_lock: asyncio.Lock` to `PresetService` |
| 2. Move the preset-building logic from module-level `get_preset()` calls to a `_build_preset_snapshot()` method that reads `presets.py` data without `importlib.reload()` |
| 3. Add `PresetService.refresh_if_stale()` — checks `os.path.getmtime("presets.py")` against a cached mtime; if changed, rebuilds the snapshot under the lock |
| 4. Call `refresh_if_stale()` at the top of `PresetService.resolve()` (cheap: one `stat` call, <1µs) |
| 5. Remove `_ensure_fresh_preset_service()` entirely |
| 6. Add a background task in the FastAPI lifespan that calls `refresh_if_stale()` every 30s (belt-and-suspenders for multi-worker deployments where one worker may not see the file change first) |
| **Refactoring** | `get_preset()` and related functions in `presets.py` become pure data-returning functions; the `PresetService` caches the result |
| **Testing strategy** | Unit: `PresetService.refresh_if_stale()` — mock `os.path.getmtime` to return a newer timestamp, verify snapshot is rebuilt. Concurrency: spawn 10 concurrent `resolve()` calls while a refresh is in-flight, verify all return consistent data |
| **Acceptance criteria** | (1) No `importlib.reload()` calls in any request path; (2) preset changes reflected within 30s without restart; (3) concurrent requests never see partial preset state |
| **Rollback** | Restore `_ensure_fresh_preset_service()` call — the new path is additive; the old function can be kept as a no-op during transition |

---

#### FIX-3: SafeLoggingFilter Installation Scope

| Field | Detail |
|-------|--------|
| **Objective** | Guarantee that `SafeLoggingFilter` is active regardless of entry point (API, CLI, scripts, tests) |
| **Severity** | P1 [VF] |
| **Affected components** | `api/__init__.py`, `main.py`, `reasoner/__init__.py` |
| **Current behavior** | `api/__init__.py` (line ~25) installs `SafeLoggingFilter` on the root logger. This only executes when the FastAPI app module is loaded. CLI invocations (`python main.py …`) and scripts that import `reasoner` submodules directly skip this — PII (API keys, user prompts) can leak into log output. |
| **Root cause** | The filter installation is coupled to the API entry point, not the package itself |
| **Design change** | Move the filter installation to `src/reasoner/__init__.py` so it executes on ANY import of the `reasoner` package. Add an idempotency guard so multiple imports don't double-install. |
| **Implementation tasks** |
| 1. Move the `SafeLoggingFilter` installation lines from `api/__init__.py` to `reasoner/__init__.py` |
| 2. Add a `_safe_logging_installed: bool = False` module-level guard |
| 3. In `api/__init__.py`, remove the existing installation lines; add a comment referencing the new location |
| 4. Verify `main.py` triggers the filter (it imports from `reasoner.pipeline`, which imports `reasoner`) |
| **Refactoring** | None — pure relocation |
| **Testing strategy** | Unit: `logging.getLogger().addFilter` mock — verify filter is installed when `import reasoner` runs. Integration: run `python main.py --problem "test"` with `-v`, verify no API key appears in debug output |
| **Acceptance criteria** | (1) `SafeLoggingFilter` is active after `import reasoner` regardless of entry point; (2) No double-installation; (3) CLI output is redacted |
| **Rollback** | Move the lines back to `api/__init__.py` — trivial |

---

#### FIX-4: Run State Fallback Hardening

| Field | Detail |
|-------|--------|
| **Objective** | Prevent duplicate pipeline runs when Redis is unavailable — the in-memory fallback must reject `try_register` when not authoritative |
| **Severity** | P1 [VF] |
| **Affected components** | `infrastructure/redis/run_state.py`, `api/__init__.py` |
| **Current behavior** | The API endpoint correctly checks `is_authoritative()` before `try_register()` and returns 503 when Redis is down. However, the in-memory `RunStateStore.try_register()` always succeeds — if any code path calls `try_register()` without the `is_authoritative()` gate, duplicates are accepted |
| **Root cause** | The fallback store was designed for single-worker dev environments where the race window doesn't exist. But `try_register` is a public method — any future caller could skip the gate |
| **Design change** | Two-part: **(a)** Make `RunStateManager.try_register()` self-gating — if Redis is unavailable, it returns `False` (reject) unless `ENVIRONMENT=development` AND `UVICORN_WORKERS=1`. **(b)** Remove the separate `is_authoritative()` check in the endpoint since it's now redundant |
| **Implementation tasks** |
| 1. In `run_state.py:RunStateManager.try_register()`, modify the `except _RedisUnavailable` branch: check `settings.ENVIRONMENT` and `settings.UVICORN_WORKERS`; if safe (dev + single worker), use the fallback; otherwise return `False` |
| 2. Add `is_authoritative()` as a public method on `RunStateManager` for callers that want explicit control |
| 3. Remove the standalone `is_authoritative()` check from `api/__init__.py` — the `try_register` call now self-gates |
| 4. Add a `reason` field to the return or exception so callers can distinguish "duplicate" from "unavailable" |
| **Refactoring** | `try_register` returns `bool` today — consider a tri-state enum (`CREATED`, `DUPLICATE`, `UNAVAILABLE`) for clearer caller semantics |
| **Testing strategy** | Unit: mock Redis to raise `ConnectionError`, verify `try_register()` returns `False` in production mode, `True` in dev+single-worker mode. Integration: kill Redis container, POST two requests with same `client_run_id`, verify the second gets 503 |
| **Acceptance criteria** | (1) `try_register()` never returns `True` when Redis is down in non-dev environments; (2) Duplicate `client_run_id` correctly rejected in all modes |
| **Rollback** | Revert to explicit `is_authoritative()` check in endpoint — the fallback hardening is additive |

---

#### FIX-5: SQLite Busy Timeout

| Field | Detail |
|-------|--------|
| **Objective** | Prevent `SQLITE_BUSY` errors in multi-worker dev deployments |
| **Severity** | P1 [VF] |
| **Affected components** | `infrastructure/persistence/event_store.py` |
| **Current behavior** | `EventStore._init_db()` sets `PRAGMA journal_mode=WAL` but does NOT set `PRAGMA busy_timeout`. SQLite's default busy timeout is 0 — any write contention returns `SQLITE_BUSY` immediately |
| **Root cause** | Missing pragma |
| **Design change** | One-line addition: `PRAGMA busy_timeout=5000` (5-second wait before giving up) |
| **Implementation tasks** |
| 1. In `event_store.py._init_db()`, add `self._connection.execute("PRAGMA busy_timeout=5000")` after the WAL pragma |
| 2. Add a comment documenting that SQLite is only safe for single-worker dev; production uses PostgreSQL |
| **Refactoring** | None |
| **Testing strategy** | Unit: verify the pragma is set by reading it back with `PRAGMA busy_timeout`. Concurrency: spawn 2 writers simultaneously, verify no `SQLITE_BUSY` |
| **Acceptance criteria** | `PRAGMA busy_timeout` returns 5000 after init |
| **Rollback** | Remove the line — zero-cost reversal |

---

### 3.3 Sprint 2 — Hardening (Weeks 3–4)

#### FIX-6: Collapse Dual-Layer Retry Logic

| Field | Detail |
|-------|--------|
| **Objective** | Eliminate nested retries — retry budget should be owned by ONE layer |
| **Severity** | P2 [VF] |
| **Affected components** | `infrastructure/llm/base.py`, `infrastructure/llm/router.py` |
| **Current behavior** | `BaseLLMProvider.complete_with_retry()` retries 3× with exponential backoff. `ProviderRouter.call()` catches the resulting `LLMError` and retries with a different provider — another 3× in the worst case. Total: up to 6+ LLM calls for one logical request |
| **Design change** | Router-level fallback uses `complete()` (single attempt, no retry) instead of `complete_with_retry()`. The provider-level retry covers transient errors (429, 5xx); the router-level fallback covers provider-specific failures |
| **Implementation tasks** |
| 1. Add `BaseLLMProvider.complete_once()` — a single-attempt wrapper around `complete()` that raises immediately on failure |
| 2. In `router.py:_execute_call()`, use `provider.complete_once()` for the fallback path; keep `complete_with_retry()` for the primary attempt |
| 3. Reduce `complete_with_retry` retries from 3 to 2 — the fallback chain provides additional resilience |
| **Testing strategy** | Unit: mock `complete()` to fail 2×, verify primary retries 2× and fallback is tried once. Verify total call count ≤ 4 |
| **Acceptance criteria** | (1) Primary attempt retries ≤ 2×; (2) Fallback attempts ≤ 1× each; (3) Total LLM calls per logical request ≤ 4 |
| **Rollback** | Restore full retry counts — the change is parameter-level, not structural |

---

#### FIX-7: Per-Model LLM Concurrency Semaphore

| Field | Detail |
|-------|--------|
| **Objective** | Prevent slow providers from starving fast ones under high concurrency |
| **Severity** | P2 [VF] |
| **Affected components** | `infrastructure/llm/router.py` |
| **Current behavior** | A single global `asyncio.Semaphore(30)` gates ALL LLM calls. If `claude-sonnet` calls occupy all 30 slots waiting for rate-limit retries, `gpt-5-nano` calls (which complete in 200ms) are blocked |
| **Design change** | Replace the single semaphore with a dict of per-model semaphores. Each model gets its own concurrency limit (configurable via env var with a sensible default). Unknown models fall back to a default semaphore |
| **Implementation tasks** |
| 1. Create `_PER_MODEL_SEMAPHORES: dict[str, asyncio.Semaphore]` with a `threading.Lock` for creation |
| 2. Add `LLM_CONCURRENCY_LIMIT_PER_MODEL` env var (default: `"claude-sonnet:10,gpt-5:15,*:10"`) parsed into a dict |
| 3. `_get_llm_semaphore(model_name)` looks up the model-specific limit; falls back to `*` default |
| 4. Update `_call_with_circuit()` to pass `provider.model` to the semaphore factory |
| **Testing strategy** | Unit: verify different models get different semaphore instances. Load: spam 40 concurrent calls across 3 models, verify fast models complete without waiting for slow models |
| **Acceptance criteria** | (1) Per-model concurrency limits are enforced independently; (2) Global fallback limit of 10 for unknown models; (3) No deadlocks |
| **Rollback** | Restore single semaphore — the factory function can be swapped back via env var `LLM_CONCURRENCY_MODE=global` |

---

#### FIX-8: In-Memory LRU Layer for Token Cache

| Field | Detail |
|-------|--------|
| **Objective** | Reduce disk I/O latency on the cache hot path by adding an in-memory LRU in front of the disk store |
| **Severity** | P2 [ES] |
| **Affected components** | `infrastructure/token_cache.py` |
| **Current behavior** | Every cache hit/miss involves reading/writing JSON files on disk. A typical pipeline run has 5–20 phases, each checking the cache — 5–20 disk reads per run |
| **Design change** | Add an in-memory `OrderedDict`-based LRU (max 512 entries) in front of the disk store. Cache reads check memory first; cache writes update both. The existing 300s background cleanup loop also prunes expired entries from the LRU |
| **Implementation tasks** |
| 1. Add `_lru_cache: collections.OrderedDict` and `_lru_lock: asyncio.Lock` to `TokenCache` |
| 2. `get()`: check LRU first → on miss, read disk and populate LRU |
| 3. `set()`: write disk + update/insert LRU |
| 4. `evict()`: prune oldest entries when LRU exceeds max size |
| **Testing strategy** | Benchmark: 100 cache hits with and without LRU layer — measure p50/p99 latency delta |
| **Acceptance criteria** | (1) Cache hit latency <100µs for LRU hits (vs ~1–5ms for disk); (2) LRU bounded at 512 entries; (3) No stale data (LRU invalidated on disk write miss) |
| **Rollback** | Disable LRU via env var `TOKEN_CACHE_LRU_ENABLED=false` |

---

#### FIX-9: Search Result Caching

| Field | Detail |
|-------|--------|
| **Objective** | Cache web search results with a 60s TTL to reduce redundant API calls |
| **Severity** | P2 [VF] |
| **Affected components** | `api/__init__.py` (`/api/search`), `application/services/search_service.py` |
| **Current behavior** | Every `/api/search` call hits external APIs (Brave, Tavily). Identical queries within the same pipeline run (e.g., research phases) call the search API multiple times |
| **Design change** | Add a request-scoped in-memory cache (`dict` with TTL) to `SearchService`. Cache key: `(query, source_type, num_results)`. TTL: 60s. Max entries: 256 |
| **Implementation tasks** |
| 1. Add `_search_cache: dict` and `_cache_lock: asyncio.Lock` to `SearchService.__init__` |
| 2. In `SearchService.search()`, check cache before calling external adapters; on hit, log `cache_hit=True` and return |
| 3. Add a periodic `_prune_expired()` call in the background cleanup loop |
| **Testing strategy** | Unit: call `search()` twice with same query, verify the second returns cached result and external adapter is NOT called |
| **Acceptance criteria** | (1) Duplicate queries within 60s hit cache; (2) Cache bounded at 256 entries; (3) Cache hit/miss tracked in metrics |
| **Rollback** | Disable via `SEARCH_CACHE_ENABLED=false` env var |

---

#### FIX-10: SSE Connection Lifetime Cap

| Field | Detail |
|-------|--------|
| **Objective** | Prevent unbounded SSE connections from stalled pipelines |
| **Severity** | P2 [VF] |
| **Affected components** | `api/middleware.py`, `api/streaming.py` |
| **Current behavior** | `RequestTimeoutMiddleware` skips `/api/run` paths entirely. A stalled `ReasonerPipeline.run()` keeps the SSE connection open indefinitely |
| **Design change** | Add an absolute 600s (10 min) timeout specifically for SSE connections. This is separate from per-phase timeouts — it's a connection-level kill switch. When triggered, yield a `timeout` error event and close the stream |
| **Implementation tasks** |
| 1. Add `PIPELINE_ABSOLUTE_TIMEOUT_SECONDS` to `core/constants.py` (default: 600) |
| 2. In `api/streaming.py:run_stream()`, wrap the `run_task()` coroutine in `asyncio.wait_for(..., timeout=PIPELINE_ABSOLUTE_TIMEOUT_SECONDS)` |
| 3. On timeout, yield `_event({"type": "error", "error": "Pipeline absolute timeout exceeded", "code": "PIPELINE_TIMEOUT"})` and close |
| **Testing strategy** | Integration: set timeout to 2s, run a pipeline that stalls, verify error event is yielded within 2s |
| **Acceptance criteria** | (1) No SSE connection lives >600s; (2) Timeout produces a clean `error` event; (3) Run state is cleaned up after timeout |
| **Rollback** | Set `PIPELINE_ABSOLUTE_TIMEOUT_SECONDS=0` to disable — backwards compatible |

---

### 3.4 Backlog — Tech Debt (Month 2+)

| # | Finding | Action | Effort |
|---|---------|--------|--------|
| BT-1 | Duplicate `DATABASE_URL` in Settings | Remove the first `str \| None` declaration; keep `str` with default `""` | 15 min |
| BT-2 | Backward-compat shim modules | Add `DeprecationWarning` to shims; remove in 2 releases | 2d |
| BT-3 | `pyproject.toml` creation | Consolidate ruff, pytest, mypy config into `pyproject.toml` | 1d |
| BT-4 | `event_store.py` split | Extract `ConnectionManager`, `CrudOperations`, `SnapshotStore`, `CompactionService` | 3d |
| BT-5 | `DummyProvider` extraction | Move inline class from `get_architecture_components()` to `infrastructure/llm/providers/noop.py` | 1d |
| BT-6 | `extra_body` mutation | Pass `extra_body` as a per-call kwarg rather than mutating the shared provider instance | 2d |
| BT-7 | `Any` → typed dependencies | Add Protocol classes for `PresetService`, `PipelineService`, `SearchService`, `NeuroClient`, `TelemetryStore` | 2d |
| BT-8 | Gate taxonomy audit | Document which phases are intentionally excluded from auto-routing; add missing mappings if needed | 1d |
| BT-9 | Langfuse health check at startup | Add connectivity probe in lifespan after key check | 0.5d |
| BT-10 | HTTP client close wrapping | Wrap each `close_*` in `try/except` at shutdown | 0.5d |

---

## 4. WORK BREAKDOWN STRUCTURE (WBS)

```
1. Sprint 1 — Critical Fixes (P1)
   1.1 FIX-1: SSE Preflight Error Handling & Keepalive
       1.1.1 Add "preparing" keepalive event
       1.1.2 Wrap handler in try/except → error event
       1.1.3 Add 5s preflight timeout
       1.1.4 Refactor: extract _run_preflight_checks()
       1.1.5 Unit tests
       1.1.6 Integration tests
   1.2 FIX-2: Safe Preset Reload
       1.2.1 Add snapshot + lock to PresetService
       1.2.2 Implement refresh_if_stale() with mtime check
       1.2.3 Add background refresh task
       1.2.4 Remove _ensure_fresh_preset_service()
       1.2.5 Unit tests (including concurrency)
   1.3 FIX-3: SafeLoggingFilter Scope
       1.3.1 Move filter install to reasoner/__init__.py
       1.3.2 Add idempotency guard
       1.3.3 Verify CLI + script paths
   1.4 FIX-4: Run State Fallback Hardening
       1.4.1 Self-gate try_register() by env
       1.4.2 Add is_authoritative() public method
       1.4.3 Simplify endpoint checks
       1.4.4 Unit tests
   1.5 FIX-5: SQLite Busy Timeout
       1.5.1 Add PRAGMA busy_timeout=5000
       1.5.2 Unit test

2. Sprint 2 — Hardening (P2)
   2.1 FIX-6: Collapse Retry Layers
       2.1.1 Add complete_once() method
       2.1.2 Router uses complete_once() for fallback
       2.1.3 Reduce primary retries to 2
       2.1.4 Unit + integration tests
   2.2 FIX-7: Per-Model Semaphore
       2.2.1 Per-model semaphore dict
       2.2.2 Env var config parsing
       2.2.3 Update call sites
       2.2.4 Load tests
   2.3 FIX-8: Token Cache LRU
       2.3.1 In-memory LRU implementation
       2.3.2 Integration with existing disk cache
       2.3.3 Benchmark tests
   2.4 FIX-9: Search Result Cache
       2.4.1 In-memory cache in SearchService
       2.4.2 TTL eviction
       2.4.3 Metrics instrumentation
   2.5 FIX-10: SSE Absolute Timeout
       2.5.1 Add timeout constant
       2.5.2 asyncio.wait_for in run_stream
       2.5.3 Clean error event on timeout
       2.5.4 Integration tests

3. Backlog — Tech Debt (P3)
   3.1 BT-1 through BT-10 (see table above)
```

---

## 5. RISK & MITIGATION MATRIX

| Risk ID | Risk | Probability | Impact | Mitigation |
|---------|------|------------|--------|------------|
| R1 | FIX-2 (preset reload) breaks hot-reload for preset designers | Low | Med | Keep old function as no-op during transition; add `PRESET_HOT_RELOAD=legacy` fallback env var |
| R2 | FIX-4 (run state hardening) breaks dev workflows that rely on in-memory fallback | Low | High | Only reject fallback in `ENVIRONMENT=production` OR `UVICORN_WORKERS>1`; dev+single-worker unchanged |
| R3 | FIX-6 (retry collapse) reduces resilience for flaky providers | Med | Med | Monitor fallback success rate after deploy; restore retry count if rate drops |
| R4 | FIX-7 (per-model semaphore) creates deadlock if model names are inconsistent | Low | High | Use canonical model IDs from `_REGISTRY`; add deadlock detection (timeout on semaphore acquisition) |
| R5 | FIX-8 (token cache LRU) introduces stale cache hits | Low | Med | LRU is read-through — cache miss always falls through to disk; TTL honored at both layers |
| R6 | FIX-10 (SSE absolute timeout) kills legitimate long-running pipelines | Med | Med | Set conservative default (600s); make configurable via env var; current longest pipeline phase is ~300s max |
| R7 | Sprint 1 changes interact — multiple SSE/providers changes touch same call path | Med | High | Stagger deploys: deploy FIX-1 + FIX-5 first (independent), then FIX-2 + FIX-3 + FIX-4 together |
| R8 | No `pyproject.toml` means no version-controlled tool config — CI may diverge from local | Low | Med | BT-3 is in backlog; document current defaults in `CONTRIBUTING.md` as interim measure |

---

## 6. TESTING & QUALITY ASSURANCE STRATEGY

### 6.1 Testing Layers

| Layer | Scope | Tools | When |
|-------|-------|-------|------|
| **Unit** | Per-function, per-class | `pytest`, `pytest-asyncio`, `unittest.mock` | Every commit |
| **Integration** | API endpoints, Redis interactions, DB writes | `pytest` + FastAPI `TestClient` | Per-PR |
| **Load** | Concurrency, semaphore behavior | `pytest-xdist`, manual `wrk` | Per-sprint |
| **E2E** | Full pipeline runs | Playwright (frontend), custom scripts | Per-release |

### 6.2 Test Cases Per Fix

| Fix | Unit Tests | Integration Tests | Load Tests |
|-----|-----------|-------------------|------------|
| FIX-1 | Preflight timeout → error event; keepalive emitted first | `curl` SSE endpoint with bad config → verify events | — |
| FIX-2 | Preset snapshot atomicity; concurrent resolve | Multi-worker preset change propagation | 10 concurrent resolves during refresh |
| FIX-3 | Filter installed on `import reasoner` | CLI output redaction | — |
| FIX-4 | `try_register` rejects in prod+redis-down | POST duplicate `client_run_id` | — |
| FIX-5 | `PRAGMA busy_timeout` set | 2 concurrent writers | — |
| FIX-6 | Retry count ≤ 4 total | Provider failure → fallback triggers | — |
| FIX-7 | Per-model semaphore isolation | — | 40 concurrent calls across 3 models |
| FIX-8 | LRU hit < disk hit | — | 100-cache-hit benchmark |
| FIX-9 | Duplicate query hits cache | `/api/search` dedup | — |
| FIX-10 | Timeout → error event | Set 2s timeout, stall pipeline | — |

### 6.3 Regression Gates

Before merging any sprint branch:
```bash
# Python
pytest tests/ -x -v --timeout=60

# Lint
ruff check src/

# Typecheck
mypy src/

# Frontend (if modified)
cd ui-next && npm run lint && npm test
```

### 6.4 CI/CD Pipeline

The existing `.github/workflows/test.yml` and `coverage.yml` already run on PR. Add:
- **`test.yml`**: Add test matrix for `ENVIRONMENT=development` and `ENVIRONMENT=production` (catches env-gated behavior like FIX-4)
- **`coverage.yml`**: Enforce ≥85% coverage on `api/streaming.py`, `application/orchestrator.py`, `infrastructure/llm/router.py`, `infrastructure/redis/run_state.py`

---

## 7. DEPLOYMENT & ROLLBACK PLAN

### 7.1 Deployment Strategy

**Sprint 1:** Canary → 10% → 50% → 100% (each step 1 hour soak)
**Sprint 2:** Blue-green (parallel staging, swap when healthy)

### 7.2 Per-Fix Rollback

| Fix | Rollback Action | Blast Radius |
|-----|----------------|-------------|
| FIX-1 | Revert `try/except` in `run_task()`; keep `preparing` event | SSE streaming only |
| FIX-2 | Set `PRESET_HOT_RELOAD=legacy` env var | Preset resolution |
| FIX-3 | Move filter install lines back to `api/__init__.py` | Log safety (not runtime) |
| FIX-4 | Revert to explicit `is_authoritative()` check in endpoint | Idempotency |
| FIX-5 | Remove `PRAGMA busy_timeout` line | SQLite write behavior |
| FIX-6 | Set `LLM_PRIMARY_RETRIES=3` and `LLM_FALLBACK_RETRIES=3` env vars | LLM call latency |
| FIX-7 | Set `LLM_CONCURRENCY_MODE=global` env var | Concurrency |
| FIX-8 | Set `TOKEN_CACHE_LRU_ENABLED=false` env var | Cache latency |
| FIX-9 | Set `SEARCH_CACHE_ENABLED=false` env var | Search API calls |
| FIX-10 | Set `PIPELINE_ABSOLUTE_TIMEOUT_SECONDS=0` env var | SSE connections |

### 7.3 Monitoring During Deploy

- **Latency:** p50/p95/p99 of `/api/run` endpoint (Prometheus: `reasoner_queries_duration_seconds`)
- **Error rate:** `reasoner_queries_total{status="error"}` — alert if >5%
- **Fallback rate:** `reasoner_fallback_events_total` — spike indicates provider issues
- **Cache hit rate:** `reasoner_cache_hits_total / (hits + misses)`
- **Circuit breaker state:** `reasoner_circuit_breaker_state{model="..."}`
- **SSE connection count:** active connections gauge

---

## 8. POST-IMPLEMENTATION VALIDATION CHECKLIST

### Sprint 1 Validation

- [ ] **FIX-1:** Send 10 requests with `OPENROUTER_API_KEY=""` — all 10 receive `preparing` event within 200ms AND `error` event within 6s. Zero silent disconnects.
- [ ] **FIX-2:** Modify `presets.py` (add a comment), wait 30s, send a request using the modified preset — new behavior reflected without restart.
- [ ] **FIX-3:** Run `python main.py --problem "test" --preset scientific-budget -v 2>&1 | grep -i "sk-"` — zero matches (no API key leakage).
- [ ] **FIX-4:** Kill Redis, POST two requests with same `client_run_id` — second returns 503 with idempotency error.
- [ ] **FIX-5:** Run `PRAGMA busy_timeout` on the event store DB — returns 5000.

### Sprint 2 Validation

- [ ] **FIX-6:** Trigger a provider outage (wrong API key for one model) → primary retries 2×, fallback tried once, total LLM calls ≤ 4.
- [ ] **FIX-7:** Run 30 concurrent calls to `claude-sonnet` (slow) + 10 to `gpt-5-nano` (fast) → `gpt-5-nano` completes without waiting for `claude-sonnet`.
- [ ] **FIX-8:** Run 2 identical pipeline requests → second request has cache hits with <1ms latency per hit.
- [ ] **FIX-9:** Call `/api/search` twice with same query within 30s → second call returns cached results, Brave/Tavily adapter never invoked.
- [ ] **FIX-10:** Set timeout to 5s, run a pipeline that stalls during phase 1 → SSE stream yields error event at 5s, connection closes cleanly.

### General

- [ ] All existing tests pass (`pytest tests/ -x`)
- [ ] No new lint warnings (`ruff check src/`)
- [ ] No type errors (`mypy src/`)
- [ ] Frontend smoke test (start UI, run a pipeline, verify SSE events render)
- [ ] Rate limiter still functional (send >300 requests in 1 minute, verify 429s appear)
- [ ] No regression in pipeline output quality (run 5 diverse prompts through auto-budget preset, manually verify synthesis is coherent)

---

## APPENDIX A: File Change Map

| File | Sprint 1 Changes | Sprint 2 Changes | Backlog |
|------|-----------------|------------------|---------|
| `api/streaming.py` | FIX-1: keepalive + error handling; FIX-2: remove `_ensure_fresh_preset_service()` | FIX-10: timeout in `run_stream()` | — |
| `api/__init__.py` | FIX-3: remove SafeLoggingFilter install; FIX-4: simplify idempotency check | — | — |
| `reasoner/__init__.py` | FIX-3: add SafeLoggingFilter install | — | — |
| `application/orchestrator.py` | FIX-1: preflight timeout + refactor | — | BT-7: typed dependencies |
| `application/services/preset_service.py` | FIX-2: snapshot + refresh_if_stale() | — | — |
| `infrastructure/redis/run_state.py` | FIX-4: self-gating try_register() | — | — |
| `infrastructure/persistence/event_store.py` | FIX-5: busy_timeout pragma | — | BT-4: file split |
| `infrastructure/llm/base.py` | — | FIX-6: add complete_once() | — |
| `infrastructure/llm/router.py` | — | FIX-6: use complete_once() for fallback; FIX-7: per-model semaphore | BT-6: extra_body fix |
| `infrastructure/token_cache.py` | — | FIX-8: in-memory LRU | — |
| `application/services/search_service.py` | — | FIX-9: search cache | — |
| `core/settings.py` | — | — | BT-1: remove duplicate DATABASE_URL |
| `core/constants.py` | — | FIX-10: add PIPELINE_ABSOLUTE_TIMEOUT_SECONDS | — |
| `pyproject.toml` | — | — | BT-3: create file |

---

## APPENDIX B: Epistemic Label Legend

| Label | Meaning |
|-------|---------|
| **[VF]** | Verified Fact — directly observed in source code at cited file:line |
| **[HY]** | Hypothesis — inferred from pattern or partial evidence; needs confirmation |
| **[ES]** | Estimate — quantitative claim not empirically measured; directional only |
