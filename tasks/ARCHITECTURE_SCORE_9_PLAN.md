# Architecture Score 9/10 Remediation Plan

**Source audit:** ARCH-AUDIT-V2, 2026-06-06
**Current score:** 6 / 10 — Early Production
**Target score:** > 9 / 10 — Production
**Scope:** `src/reasoner/` — Python backend only

---

## Scoring gap analysis

To move from 6 → 9 the following must be eliminated:

| Category | Current violations | Required at 9+ |
|----------|--------------------|----------------|
| CRITICAL | 2 | 0 |
| HIGH | 6 | 0 |
| MEDIUM | 4 | ≤ 1 (low-propagation residual) |
| Horizontal scaling defects | 2 documented | 0 |
| Parallel execution paths | 3 | 1 |
| Layer violations (core → infra) | 1 runtime | 0 |

---

## Sprint 0 — Emergency fixes (< 1 day, touch ≤ 3 lines each)

These are production crash risks. Fix before any other work.

---

### 0-A: `asyncio.run()` inside async context

**File:** `src/reasoner/infrastructure/search/discovery.py:126`

**Problem:** `asyncio.run(old.close())` is called inside a class method that is reached from an async code path. Under uvicorn, the event loop is always running. `asyncio.run()` in a running loop raises `RuntimeError: This event loop is already running`.

**Fix:**

```python
# BEFORE
asyncio.run(old.close())

# AFTER — drop into the running loop
import asyncio as _asyncio
try:
    loop = _asyncio.get_running_loop()
    loop.create_task(old.close())
except RuntimeError:
    _asyncio.run(old.close())  # Only reached in non-async context (CLI, tests)
```

**Acceptance criteria:**
- [ ] `asyncio.run` no longer called from any code path reachable inside a uvicorn worker
- [ ] `test_searxng_integration.py` passes
- [ ] No `RuntimeError: This event loop is already running` in logs

---

### 0-B: `sys.modules` mutation in request handler

**File:** `src/reasoner/api/streaming.py:56-80`

**Problem:** `_ensure_fresh_preset_service()` deletes entries from `sys.modules` and calls `importlib.reload()` on the first request. Under concurrent load, Thread A deletes `reasoner.domain.preset_registry` from `sys.modules` while Thread B imports it → gets a `None` or partially-initialized module object.

**Fix:** Remove the function entirely. Initialize `PresetService` once at application startup and store it on the `app.state` object.

**Step 1** — add to `api/__init__.py` lifespan startup block:

```python
# Inside lifespan(app) startup section
from reasoner.application.services.preset_service import PresetService
app.state.preset_service = PresetService()
```

**Step 2** — add a FastAPI dependency in `api/dependencies.py`:

```python
def get_preset_service(request: Request) -> PresetService:
    return request.app.state.preset_service
```

**Step 3** — update `streaming.py` to receive it via dependency injection instead of calling `_ensure_fresh_preset_service()`. Replace every call site:

```python
# BEFORE
preset_service = _ensure_fresh_preset_service()

# AFTER (in each SSE function signature)
async def run_stream(req: RunRequest, preset_service: PresetService = Depends(get_preset_service), ...):
    ...
```

**Step 4** — delete `_ensure_fresh_preset_service`, `_preset_service`, and `_PRESET_SERVICE_LOADED` from `streaming.py`.

**Acceptance criteria:**
- [ ] `_ensure_fresh_preset_service` is gone
- [ ] No `sys.modules` or `importlib.reload` calls in any request handler
- [ ] `PresetService` initialized exactly once per process in `lifespan`
- [ ] `test_api_presets_models.py` and `test_presets.py` pass

---

## Sprint 1 — Layer purity (1–2 days)

Eliminates the two remaining dependency-rule violations in core and application layers.

---

### 1-A: Remove infrastructure import from `core/search.py`

**File:** `src/reasoner/core/search.py:44`

**Problem:** `from reasoner.infrastructure.llm.registry import build_provider` is a runtime import inside `core/`. The core layer must have zero outward dependencies.

**Root cause:** `DiscoveryClient` needs an LLM provider for AI-reranking but pulls it from the registry directly.

**Fix:** Constructor injection.

```python
# BEFORE — core/search.py reaches into infra
class DiscoveryClient:
    def __init__(self, ...):
        ...
        # somewhere inside:
        from reasoner.infrastructure.llm.registry import build_provider
        self._provider = build_provider(...)

# AFTER — provider injected at construction site
class DiscoveryClient:
    def __init__(self, ..., llm_provider=None):
        self._provider = llm_provider  # may be None; feature degrades gracefully
```

**Construction site** (`application/services/search_service.py` or wherever `DiscoveryClient` is instantiated):

```python
from reasoner.infrastructure.llm.registry import build_provider
provider = build_provider(role="deep_read")
client = DiscoveryClient(..., llm_provider=provider)
```

**Acceptance criteria:**
- [ ] `grep -rn "from reasoner.infrastructure" src/reasoner/core/` returns zero matches
- [ ] `test_search_client_factory.py` and `test_context_vetting.py` pass
- [ ] `DiscoveryClient` can be constructed without any infrastructure imports in scope

---

### 1-B: Remove `pipeline.py` globals from application-layer flows

**Files:**
- `src/reasoner/application/flows/synthesis_phase.py:30`
- `src/reasoner/application/flows/perspective_phases.py:60`

**Problem:** These flow files do `from reasoner.pipeline import TOKEN_OPTIMIZATION, USE_PHASE_SUBAGENTS`. The `WorkflowStrategy` pattern was designed to decouple flows from `pipeline.py`; this import re-couples them.

**Fix:** Surface this config through `WorkflowServices`.

**Step 1** — add fields to `application/flows/base.py`:

```python
class WorkflowServices(Protocol):
    ...
    @property
    def token_optimization(self) -> dict: ...
    @property
    def use_subagents(self) -> dict: ...
```

**Step 2** — implement on `PipelineWorkflowServices` (`application/flows/services.py`):

```python
@property
def token_optimization(self) -> dict:
    return self._pipeline.token_optimization  # or from settings

@property
def use_subagents(self) -> dict:
    return self._pipeline.use_subagents
```

**Step 3** — move `TOKEN_OPTIMIZATION` and `USE_PHASE_SUBAGENTS` from module-level in `pipeline.py` to instance attributes on `ReasonerPipeline.__init__`, driven by `settings`:

```python
class ReasonerPipeline:
    def __init__(self, ...):
        ...
        self.token_optimization = {
            "dynamic_budgets": settings.TOKEN_DYNAMIC_BUDGETS,
            "context_compression": settings.TOKEN_CONTEXT_COMPRESSION,
            ...
        }
        self.use_subagents = {
            "synthesis": settings.USE_SUBAGENT_SYNTHESIS,
            ...
        }
```

**Step 4** — update `synthesis_phase.py` and `perspective_phases.py` to read from `services`:

```python
# BEFORE
from reasoner.pipeline import TOKEN_OPTIMIZATION, USE_PHASE_SUBAGENTS
if USE_PHASE_SUBAGENTS["synthesis"]: ...

# AFTER
if services.use_subagents["synthesis"]: ...
```

**Acceptance criteria:**
- [ ] `grep -rn "from reasoner.pipeline import" src/reasoner/application/flows/` returns zero matches
- [ ] `TOKEN_OPTIMIZATION` and `USE_PHASE_SUBAGENTS` are gone as module-level globals in `pipeline.py`
- [ ] `test_synthesis_fixes.py` and `test_perspective_registry.py` pass

---

## Sprint 2 — Execution path consolidation (2–3 days)

Eliminates the three parallel execution paths, making `PipelineOrchestrator` the single entry point.

---

### 2-A: Route `run-with-context` through `PipelineOrchestrator`

**File:** `src/reasoner/api/routes/context.py:54-100`

**Problem:** This route constructs `ReasonerPipeline` directly, bypassing quota enforcement, neuro recall, event persistence, and history tracking.

**Fix:** Build a `RunRequest`-compatible adapter and delegate to `PipelineOrchestrator`.

```python
# context.py — AFTER refactor
from reasoner.api.schemas import RunRequest

async def run_with_context(
    req: ContextAnalysisRequest,
    user: User | None = Depends(get_optional_user),
    preset_service: PresetService = Depends(get_preset_service),
    ...
):
    # Validate URLs first (keep existing security check)
    ...

    # Build a RunRequest from ContextAnalysisRequest
    run_req = RunRequest(
        problem=_build_problem_with_context(req),
        preset=req.preset,
        top_k=req.top_k,
    )

    orchestrator = PipelineOrchestrator(
        preset_service=preset_service,
        pipeline_service=PipelineService(),
    )
    decision = await orchestrator.preflight(run_req)
    state = await orchestrator.execute(decision)
    await orchestrator.postflight(state, run_req, user_id=user.id if user else None)

    return _serialize_context_result(state)
```

**Acceptance criteria:**
- [ ] `api/routes/context.py` no longer imports `ReasonerPipeline`
- [ ] `grep -rn "ReasonerPipeline" src/reasoner/api/` returns zero matches
- [ ] Context endpoint applies quota, emits events, and writes history (verify in integration test)
- [ ] `test_api_gate.py` and `test_context_vetting.py` pass

---

### 2-B: Wire `RunPipelineCommandHandler` as the single execution entry point

**Current state:** `streaming.py` calls `PipelineOrchestrator` directly. `RunPipelineCommandHandler` in `handlers.py` exists but is not invoked from any production path.

**Target:** `streaming.py` → `RunPipelineCommandHandler` → `PipelineOrchestrator`.

This is a two-phase migration to avoid breaking the live path:

**Phase 2-B-1 (additive — no breakage):** Make `RunPipelineCommandHandler` delegate to `PipelineOrchestrator` rather than constructing `ReasonerPipeline` directly:

```python
class RunPipelineCommandHandler:
    def __init__(self, orchestrator: PipelineOrchestrator, event_store=None):
        self._orchestrator = orchestrator
        self.event_store = event_store

    async def handle(self, command: RunPipelineCommand) -> PipelineState:
        run_req = _command_to_run_request(command)
        decision = await self._orchestrator.preflight(run_req)
        state = await self._orchestrator.execute(decision)
        await self._orchestrator.postflight(state, run_req, command.user_id)
        return state
```

**Phase 2-B-2:** Update `streaming.py` to create and call the handler:

```python
# BEFORE
orchestrator = PipelineOrchestrator(preset_service=..., pipeline_service=..., ...)
decision = await orchestrator.preflight(req, initial_state)
...

# AFTER
handler = RunPipelineCommandHandler(
    orchestrator=PipelineOrchestrator(preset_service=..., pipeline_service=..., ...),
    event_store=get_event_store(),
)
command = RunPipelineCommand(
    problem=req.problem, preset=req.preset, method=req.method,
    top_k=req.top_k, user_id=user.id if user else None,
    ...
)
state = await handler.handle(command)
```

**Acceptance criteria:**
- [ ] There is exactly **one** code path that constructs and runs `ReasonerPipeline` from the API layer
- [ ] `RunPipelineCommandHandler` is the single command entry point used by `streaming.py`, `main.py`, and `context.py`
- [ ] `test_e2e_comprehensive.py` and `test_pipeline_flow.py` pass on all methods
- [ ] No `PipelineOrchestrator` imported directly from any API route

---

## Sprint 3 — God module decomposition (2–3 days)

Breaks `api/__init__.py` (730 lines, 13 global singletons) into focused modules.

---

### 3-A: Extract lifespan initialization

**New file:** `src/reasoner/api/lifespan.py`

Move the entire `lifespan()` async context manager out of `api/__init__.py`. It should own:
- Event bus initialization and subscriber registration
- PostgreSQL pool creation and teardown
- Event store initialization
- Handler registry wiring
- Run state manager initialization
- Preset service initialization (Sprint 0-B)
- Background task (`_update_active_users_loop`) management

```python
# api/lifespan.py
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _setup_event_bus(app)
    _setup_postgres(app)
    _setup_event_store(app)
    _setup_handler_registry(app)
    _setup_run_state(app)
    app.state.preset_service = PresetService()
    task = asyncio.create_task(_update_active_users_loop(app))
    yield
    # Shutdown
    task.cancel()
    _teardown_postgres(app)
    await close_redis()
```

All state should be stored on `app.state.*` rather than module-level globals.

### 3-B: Extract route registration

**New file:** `src/reasoner/api/router.py`

Move the 15+ `app.include_router(...)` calls into a `register_routes(app: FastAPI)` function called from `api/__init__.py`.

### 3-C: Eliminate module-level globals in `api/`

Files with module-level `global` mutations to fix:

| File | Global variable | Fix |
|------|----------------|-----|
| `api/__init__.py` | `_event_store`, `_health_postgres_pool`, `_handler_registry` | → `app.state.*` |
| `api/streaming.py` | `_preset_service`, `_PRESET_SERVICE_LOADED` | → deleted (Sprint 0-B) |
| `api/auth_deps.py` | `_rate_limiter_instance_auth_deps`, `_auth_manager_instance_auth_deps` | → `app.state.*` via dependency |
| `api/dependencies.py` | `_rate_limiter_instance`, `_user_provision_pool`, `_quota_service` | → `app.state.*` |
| `api/routes/health.py` | `_health_postgres_pool` | → `request.app.state.postgres_pool` |

**Pattern for all of them:**

```python
# BEFORE — module-level global
_quota_service: QuotaService | None = None

async def get_quota_service() -> QuotaService:
    global _quota_service
    if _quota_service is None:
        _quota_service = QuotaService(...)
    return _quota_service

# AFTER — stored on app.state, injected via dependency
def get_quota_service(request: Request) -> QuotaService:
    return request.app.state.quota_service
```

**Acceptance criteria after Sprint 3:**
- [ ] `api/__init__.py` ≤ 150 lines (app factory + CORS + middleware wiring only)
- [ ] Zero `global` statements in any `api/` module
- [ ] `grep -rn "^global " src/reasoner/api/` returns zero matches
- [ ] All existing API tests pass

---

## Sprint 4 — Horizontal scaling (2–3 days)

Ensures the system works correctly under multi-worker and multi-replica deployments.

---

### 4-A: Redis-backed `RunStateStore`

**File:** `src/reasoner/infrastructure/redis/in_memory.py`

**Problem:** `RunStateStore` uses `asyncio.Event` objects — inherently per-process. Cancel events from worker A are invisible to worker B.

**Fix:** Implement `RedisRunStateStore` alongside the existing in-memory store. Switch via settings.

```python
# infrastructure/redis/run_state.py — add alongside existing class

class RedisRunStateStore:
    """Redis-backed run state for multi-worker deployments."""
    
    _CANCEL_PREFIX = "ara:cancel:"
    _ACTIVE_PREFIX = "ara:active:"
    _TTL = 3600  # 1 hour

    def __init__(self, redis: aioredis.Redis):
        self._redis = redis

    async def add(self, run_id: str, user_id: str | None = None) -> None:
        await self._redis.setex(f"{self._ACTIVE_PREFIX}{run_id}", self._TTL, user_id or "")

    async def cancel(self, run_id: str) -> bool:
        key = f"{self._CANCEL_PREFIX}{run_id}"
        await self._redis.setex(key, self._TTL, "1")
        return True

    async def is_cancelled(self, run_id: str) -> bool:
        return bool(await self._redis.exists(f"{self._CANCEL_PREFIX}{run_id}"))

    async def remove(self, run_id: str) -> None:
        await self._redis.delete(
            f"{self._CANCEL_PREFIX}{run_id}",
            f"{self._ACTIVE_PREFIX}{run_id}",
        )
```

**Factory function:**

```python
def get_run_state_manager() -> RunStateStore | RedisRunStateStore:
    if settings.REDIS_RUN_STATE_ENABLED:
        return RedisRunStateStore(get_redis())
    return RunStateStore()  # fallback for local dev / single-worker
```

**Polling in pipeline:** Replace `asyncio.Event.wait()` with a polling check against `is_cancelled()`:

```python
# In streaming.py cancel-check loop
while not state.completed:
    if await _run_store.is_cancelled(run_id):
        state.cancelled = True
        break
    await asyncio.sleep(0.5)
```

**Acceptance criteria:**
- [ ] `settings.REDIS_RUN_STATE_ENABLED = True` in production env template
- [ ] `test_saas_run_state.py` and `test_run_state_store.py` pass against the Redis implementation
- [ ] Cancel on worker A stops execution on worker B (integration test with two in-process "workers")

---

### 4-B: Enforce Redis rate limiter in multi-worker mode

**File:** `src/reasoner/rate_limiter.py`

**Problem:** The in-memory fallback is used when `RATE_LIMITER_MODE != "redis"`. This is the default, making per-IP rate limiting per-process.

**Fix:**

1. Change the default env value to `"redis"` in production settings template (`src/reasoner/core/settings.py`).
2. Add a startup check in `lifespan.py`:

```python
if settings.is_multi_worker and settings.RATE_LIMITER_MODE != "redis":
    raise RuntimeError(
        "RATE_LIMITER_MODE must be 'redis' when running multiple workers. "
        "Set RATE_LIMITER_MODE=redis or WORKERS=1."
    )
```

3. Add `WORKERS` to `settings.py` (read from `WEB_CONCURRENCY` or `UVICORN_WORKERS` env):

```python
@property
def is_multi_worker(self) -> bool:
    return int(os.getenv("WEB_CONCURRENCY", "1")) > 1
```

**Acceptance criteria:**
- [ ] Starting with `WEB_CONCURRENCY=4` and `RATE_LIMITER_MODE=memory` raises `RuntimeError` at startup
- [ ] `RATE_LIMITER_MODE=redis` is the documented production default in `.env.example`
- [ ] `test_rate_limiter_concurrency.py` and `test_rate_limiter_edge_cases.py` pass

---

### 4-C: Per-process `token_cache` to shared cache (optional — low risk, high reward)

**File:** `src/reasoner/pipeline.py:92-96`

**Problem:** Module-level `token_cache = get_token_cache(…)` creates one cache per process. Under 4 workers, the same LLM call is made 4 times (each worker misses the other's cache).

**Fix:** Move to `app.state.token_cache` and pass it to `ReasonerPipeline` via constructor.

```python
# lifespan.py — startup
app.state.token_cache = get_token_cache(
    max_tokens=1_000_000,
    ttl_seconds=3600,
    cache_dir="cache/tokens",
) if settings.TOKEN_CACHING_ENABLED else None

# api/dependencies.py
def get_token_cache(request: Request):
    return request.app.state.token_cache

# streaming.py — pass to orchestrator → pipeline_service → ReasonerPipeline
pipeline = ReasonerPipeline(router=router, token_cache=token_cache, ...)
```

This doesn't solve cross-worker cache sharing (that would require a Redis token cache), but it eliminates the module-level init side effect and makes the cache injectable/testable.

**Acceptance criteria:**
- [ ] No `token_cache = get_token_cache(…)` at module level in `pipeline.py`
- [ ] `test_token_cache_counter_leak.py` and `test_token_cache_semantic.py` pass

---

## Sprint 5 — Circular dependency structural fix (1–2 days)

Reduces the 55 lazy-import workarounds to a structurally correct dependency graph.

---

### 5-A: Audit and document the dependency graph

Before fixing, map the actual import graph:

```bash
pip install pydeps
pydeps src/reasoner --max-bacon=3 --show-deps --no-show
```

Identify the 5 highest-fanout modules. These are the real coupling hubs.

Expected result based on audit evidence:
- `reasoner.pipeline` — Ca=8 (highest)
- `reasoner.api.__init__` — Ca=many (creates all the cycles)
- `reasoner.core.constants` — Ca=many (but acceptable for constants)
- `reasoner.application.event_bus.bus` — Ca=7+

### 5-B: Break `pipeline.py` ↔ `application/flows/` cycle

After Sprint 1-B (config globals removed) and Sprint 2-B (CQRS wiring), `pipeline.py` should only be imported by:
- `application/orchestrator.py`
- `application/services/pipeline_service.py`
- `application/flows/services.py`
- `main.py`

The flows themselves should import from `base.py` (Protocol), not from `pipeline.py`. Verify:

```bash
grep -rn "from reasoner.pipeline import" src/reasoner/application/flows/
# Should return zero matches after Sprint 1-B
```

### 5-C: Break `api/__init__.py` ↔ `application/handlers/` cycle

After Sprint 3-A (lifespan extraction), `api/__init__.py` will import `lifespan` but not directly touch `application/handlers`. The handler registry should be initialized in `lifespan.py` without `api/__init__.py` knowing the handler types.

**Pattern:** Use a registration protocol so `lifespan.py` imports handlers but `api/__init__.py` does not:

```python
# api/lifespan.py
from reasoner.application.handlers.handlers import get_handler_registry

def _setup_handler_registry(app: FastAPI) -> None:
    app.state.handler_registry = get_handler_registry()
```

**Acceptance criteria for Sprint 5:**
- [ ] `grep -rn "avoid circular\|Break circular\|lazy import to avoid" src/reasoner/` count decreases by ≥ 50% from current 55
- [ ] `python -c "import reasoner.api"` completes without `ImportError` in a fresh interpreter
- [ ] `python -c "import reasoner.application.flows.factory"` does not transitively import `reasoner.api`

---

## Sprint 6 — CQRS completion and event sourcing integrity (2–3 days)

Raises the architectural coherence of the CQRS + Event Sourcing pattern from skeleton to functional.

---

### 6-A: Event store for all pipeline executions

**Current state:** Events are published to the in-memory event bus but the event store (`EventStore`) is not consistently used by all execution paths.

**Fix:** In `RunPipelineCommandHandler.handle()` (after Sprint 2-B), ensure every phase event is persisted:

```python
async def handle(self, command: RunPipelineCommand) -> PipelineState:
    ...
    # Subscribe event store to all events for this run
    async def _persist(event: DomainEvent) -> None:
        await self.event_store.save_events([event])
    
    unsub = await bus.subscribe(EventType.PHASE_COMPLETED, _persist)
    try:
        state = await self._orchestrator.execute(decision)
    finally:
        unsub()
    return state
```

### 6-B: `PipelineAggregate` replay covers all event types

**File:** `src/reasoner/core/aggregates/pipeline.py`

Verify (and extend if needed) that `PipelineAggregate` can replay a stored event sequence and produce a `PipelineState` equivalent to a live run. This enables `--resume` to work from the event log rather than from a state snapshot JSON.

**Acceptance criteria:**
- [ ] `test_aggregates.py` covers all `EventType` variants
- [ ] `test_pipeline_resume.py` can resume a pipeline from its persisted event sequence
- [ ] Running `--resume` on a completed pipeline replays the state correctly

---

## Verification: Score recalculation

After all sprints, re-run ARCH-AUDIT-V2. Expected outcomes:

| Finding | Pre-plan | Post-plan |
|---------|----------|-----------|
| `asyncio.run()` in async context | CRITICAL | [RESOLVED] |
| `sys.modules` mutation in request handler | CRITICAL | [RESOLVED] |
| `api/routes/context.py` bypasses orchestrator | HIGH | [RESOLVED] |
| `core/search.py` infra import | HIGH | [RESOLVED] |
| `pipeline.py` globals in flow layer | HIGH | [RESOLVED] |
| `api/__init__.py` god module | HIGH | [RESOLVED] |
| In-process `RunStateStore` | HIGH | [RESOLVED] |
| In-memory rate limiter | HIGH | [RESOLVED] |
| CQRS handlers unwired | MEDIUM | [RESOLVED] |
| Module-level `token_cache` | MEDIUM | [RESOLVED] |
| Three execution paths | MEDIUM | [RESOLVED] |
| Circular dependency pressure | MEDIUM | [REDUCED — structural] |
| Temporal coupling in `pipeline.run()` | MEDIUM | [RESIDUAL — acceptable] |
| Mutable `PipelineState` | LOW | [RESIDUAL — acceptable] |

**Projected score: 9 / 10**

Residual deduction: `-1` for temporal coupling in `pipeline.run()` (implicit phase ordering is an inherent property of pipeline architectures; declaring a full DAG requires significant redesign with unclear benefit at current scale) and mutable state (`PipelineState` frozen dataclass would require pervasive refactoring across 20+ strategy files).

---

## Implementation order (dependency-aware)

```
Sprint 0-A  (asyncio.run fix)          ← no dependencies
Sprint 0-B  (sys.modules fix)          ← no dependencies
      ↓
Sprint 1-A  (core/search.py injection) ← needs 0-B (PresetService pattern)
Sprint 1-B  (pipeline globals → WorkflowServices) ← needs 0-B
      ↓
Sprint 2-A  (context.py → orchestrator) ← needs 1-B (PipelineOrchestrator clean)
Sprint 2-B  (CQRS as single entry)     ← needs 2-A
      ↓
Sprint 3-A  (lifespan extraction)      ← needs 0-B, 2-B
Sprint 3-B  (route registration)       ← needs 3-A
Sprint 3-C  (eliminate module globals) ← needs 3-A
      ↓
Sprint 4-A  (Redis RunStateStore)      ← needs 3-A (app.state pattern)
Sprint 4-B  (Redis rate limiter)       ← needs 3-A
Sprint 4-C  (token_cache injectable)   ← needs 1-B, 3-A
      ↓
Sprint 5-A  (dependency graph audit)   ← needs 1-B, 2-B, 3-C
Sprint 5-B/C (structural cycle fix)    ← needs 5-A
      ↓
Sprint 6-A  (event store wiring)       ← needs 2-B
Sprint 6-B  (aggregate replay)         ← needs 6-A
```

---

## Test suite obligations

Each sprint must leave the test suite green. Additional tests required:

| Sprint | New tests required |
|--------|-------------------|
| 0-A | `test_search_async_close.py` — assert no `asyncio.run()` in async paths |
| 0-B | `test_preset_service_lifecycle.py` — one instance per process, thread-safe |
| 2-A | `test_context_route_quota.py` — quota enforced on context endpoint |
| 2-B | `test_single_execution_path.py` — all entry points converge on handler |
| 4-A | `test_redis_run_state_cross_worker.py` — cancel visible across "workers" |
| 4-B | `test_rate_limiter_multi_worker.py` — limits enforced across processes |
| 6-A | `test_event_persistence_completeness.py` — all phases produce persisted events |

---

## Estimated total effort

| Sprint | Scope | Effort |
|--------|-------|--------|
| 0 | 2 emergency patches | 2–4 hours |
| 1 | 2 layer violations | 1 day |
| 2 | Execution path consolidation | 2–3 days |
| 3 | God module decomposition | 2–3 days |
| 4 | Horizontal scaling | 2–3 days |
| 5 | Circular dependency structural fix | 1–2 days |
| 6 | CQRS + event sourcing completion | 2–3 days |
| **Total** | | **10–15 engineer-days** |

Sprint 0 is prerequisite to any production deployment with multiple workers. Sprints 1–3 are the highest-leverage architectural improvements. Sprints 4–6 are required for a 9+/10 score but can be parallelized after Sprint 3 completes.
