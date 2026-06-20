# Reasoner Enhancement & Fix Plan

**Generated:** 2026-06-10  
**Based on:** Forensic architecture reconstruction (full codebase traversal)  
**Scope:** 15 items — 2 Critical, 4 High, 4 Medium, 3 Optimizations, 4 Enhancements  
**Estimated effort:** 4 sprints (~3 weeks)

---

## Guiding Principles

All changes must respect the project's layered architecture:

```
API / Interface
    ↓ depends on
Application (CQRS handlers, orchestrator, services)
    ↓ depends on
Core / Domain (no outer deps)
    ↑ implemented by
Infrastructure
```

1. **Minimal footprint** — each change touches only the files responsible for the problem.
2. **No architectural regressions** — fixes must not introduce new layer violations.
3. **Tests first** — write a failing test that captures the bug before fixing the code.
4. **Feature flags for risky changes** — gate anything that could affect production behavior.
5. **Backward compatibility** — the `--resume` path and old serialized state files must continue to work.

---

## Sprint 1: Critical Fixes

> These two items represent correctness and security risks in the production path. Address before any other work.

---

### C1 — CQRS Alignment for the Streaming Path

**Priority:** CRITICAL  
**Effort:** Large (2–3 days)  
**Files:** `src/reasoner/api/streaming.py`, `src/reasoner/application/handlers/handlers.py`, `src/reasoner/core/settings.py`

#### Background

`api/streaming.py:run_stream()` (line 336) correctly calls `PipelineOrchestrator.preflight()` and (line 796) `postflight()`. However, it builds the pipeline directly via `pipeline_service.create_pipeline()` (line 359) instead of routing through `RunPipelineCommandHandler`. This means:

- `RunPipelineCommandHandler.handle()` (handlers.py line 54) is dead code for all SSE requests.
- The event-sourced `PipelineAggregate` in the handler is never populated from live SSE runs.
- Any future auth-scoping, billing hooks, or pipeline-lifecycle logic added to the handler is silently bypassed.

The handler's current `handle()` implementation calls `pipeline.run()` synchronously and cannot yield SSE events — making a direct swap impossible without refactoring the handler.

#### Approach

A two-phase approach avoids rewriting the entire streaming path at once:

**Phase 1 (Sprint 1):** Add a `CQRS_BYPASS_STREAMING` feature flag and make the bypass explicit and observable. This makes the architectural decision transparent and gives a clear toggle for the Phase 2 migration.

**Phase 2 (follow-on sprint):** Refactor `RunPipelineCommandHandler` to support an async streaming callback, then switch `CQRS_BYPASS_STREAMING=False`.

#### Phase 1 Implementation

**Step 1** — Add flag to `src/reasoner/core/settings.py` after line 71 (the `ENABLE_LEGACY_API_KEY` line):

```python
# ── CQRS ──
# When True, streaming runs bypass RunPipelineCommandHandler and go directly
# through PipelineOrchestrator. See docs/ENHANCEMENT_PLAN.md C1 for migration plan.
CQRS_BYPASS_STREAMING: bool = os.getenv("CQRS_BYPASS_STREAMING", "true").lower() in ("1", "true", "yes")
```

**Step 2** — Add a guard at the top of `run_stream()` in `src/reasoner/api/streaming.py` (after line 314, before the `cancel_event` registration):

```python
from reasoner.core.settings import settings as _settings
if not _settings.CQRS_BYPASS_STREAMING:
    # Phase 2 path: route through CQRS handler (not yet implemented)
    raise NotImplementedError(
        "CQRS_BYPASS_STREAMING=False requires RunPipelineCommandHandler "
        "to support SSE callbacks. See docs/ENHANCEMENT_PLAN.md C1."
    )
```

**Step 3** — Refactor `RunPipelineCommandHandler` (handlers.py) to accept an optional `on_event` async callback, so Phase 2 can be implemented incrementally. Add to the class:

```python
async def handle_streaming(
    self,
    command: RunPipelineCommand,
    on_event: Callable[[dict], Awaitable[None]],
) -> PipelineAggregate:
    """Streaming-capable handler variant (Phase 2 implementation target).

    Unlike handle(), this method does not call pipeline.run() directly.
    Instead, callers supply on_event to receive SSE events as they arrive.
    Implementation is deferred — see docs/ENHANCEMENT_PLAN.md C1.
    """
    raise NotImplementedError("Phase 2: implement SSE streaming through CQRS handler")
```

**Step 4** — Update `CLAUDE.md` Known Violations section to reflect that this is now a tracked, flagged violation rather than an undocumented one.

#### Acceptance Criteria

- `CQRS_BYPASS_STREAMING=true` (default): all existing SSE tests pass unchanged.
- `CQRS_BYPASS_STREAMING=false`: app raises `NotImplementedError` at startup of the `/api/run` path (not silently bypassing).
- `RunPipelineCommandHandler.handle_streaming()` has a docstring and a `pytest.raises(NotImplementedError)` test.

---

### C2 — Rate Limiter Startup Guard Hardening

**Priority:** CRITICAL  
**Effort:** Small (0.5 days)  
**Files:** `src/reasoner/api/__init__.py`, `src/reasoner/core/settings.py`

#### Background

`api/__init__.py:91–106` raises `RuntimeError` only when `ENVIRONMENT == "production"` and `RATE_LIMITER_MODE == "memory"` with multiple workers. In staging and development with `UVICORN_WORKERS > 1`, it only logs a warning — the insecure configuration is silently accepted.

Additionally, the check only reads a config value. It does not verify that Redis is actually reachable. A misconfigured Redis URL (e.g., pointing to a wrong host) would set `RATE_LIMITER_MODE=redis` in config but fail silently at runtime, reverting to in-memory fallback while the startup guard reports "passed".

#### Implementation

**Step 1** — Extend the startup check in the `lifespan()` function (api/__init__.py, after line 105) to also cover staging:

```python
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
```

**Step 2** — Add a Redis reachability probe when `RATE_LIMITER_MODE=redis`. Place this immediately after the mode check in the same `lifespan()` function:

```python
if settings.RATE_LIMITER_MODE == "redis" and uvicorn_workers > 1:
    try:
        from reasoner.infrastructure.redis.client import get_redis
        _probe_redis = get_redis()
        await _probe_redis.set("_startup_probe", "1", ex=10, nx=True)
        logger.info("Redis rate limiter probe: reachable")
    except Exception as probe_exc:
        raise RuntimeError(
            f"RATE_LIMITER_MODE=redis but Redis is unreachable at startup: {probe_exc}. "
            f"Fix the Redis connection or set RATE_LIMITER_MODE=memory "
            f"(only safe for UVICORN_WORKERS=1)."
        ) from probe_exc
```

**Step 3** — Add `RATE_LIMITER_MODE` to `settings.py` if not already present (verify first — if missing, add after `UVICORN_WORKERS`):

```python
RATE_LIMITER_MODE: str = os.getenv("RATE_LIMITER_MODE", "memory")
```

#### Acceptance Criteria

- Unit test: mock `settings.ENVIRONMENT = "staging"`, `settings.UVICORN_WORKERS = 2`, `settings.RATE_LIMITER_MODE = "memory"` → lifespan raises `RuntimeError`.
- Unit test: mock `settings.RATE_LIMITER_MODE = "redis"`, Redis probe raises `ConnectionError` → lifespan raises `RuntimeError`.
- Integration test: `UVICORN_WORKERS=1`, any mode → lifespan succeeds.

---

## Sprint 2: High-Impact Reliability Fixes

---

### H1 — Remove Redundant `dataclasses.fields()` Loop from All Property Setters

**Priority:** HIGH  
**Effort:** Small (0.5 days, but requires careful review of all setters)  
**File:** `src/reasoner/domain/pipeline_state.py`

#### Background

Every property setter in `PipelineState` contains the following block (e.g., lines 236–243):

```python
import dataclasses
for f in dataclasses.fields(self):
    if not hasattr(self, f.name):
        if f.default_factory is not dataclasses.MISSING:
            object.__setattr__(self, f.name, f.default_factory())
        elif f.default is not dataclasses.MISSING:
            object.__setattr__(self, f.name, f.default)
```

This loop is O(n_fields) and is called on **every attribute write** across all 40+ setters throughout a pipeline run. The `import dataclasses` inside the setter is also redundant (it is already imported at module level on line 12).

The purpose of the loop is to handle deserialized / resumed states where some fields may be absent. However:
- `__post_init__` (called from `__init__` on line 215) already handles this initialization.
- For fully initialized instances, every setter call re-scans all fields unnecessarily.

#### Implementation

**Step 1** — Add an `_initialized` sentinel to the `PipelineState.__init__` method, set at the very end after `__post_init__()` completes:

```python
# At the end of __init__, after self.__post_init__():
object.__setattr__(self, '_initialized', True)
```

**Step 2** — Replace every occurrence of the redundant loop in property setters with a guarded helper call. The current repeated block (which appears identically in ~40 setters) becomes:

```python
# Before (repeated in every setter):
import dataclasses
for f in dataclasses.fields(self):
    if not hasattr(self, f.name):
        if f.default_factory is not dataclasses.MISSING:
            object.__setattr__(self, f.name, f.default_factory())
        elif f.default is not dataclasses.MISSING:
            object.__setattr__(self, f.name, f.default)

# After (one call per setter):
self._ensure_fields_initialized()
```

**Step 3** — Add the `_ensure_fields_initialized` method to `PipelineState`:

```python
def _ensure_fields_initialized(self) -> None:
    """Initialize missing dataclass fields for backward-compatible --resume loading.

    Called only when _initialized is not yet set, meaning this is a partially
    deserialized state. After the first call completes, sets _initialized=True
    so subsequent calls are a no-op.
    """
    if getattr(self, '_initialized', False):
        return
    for f in dc_fields(self):  # dc_fields is already imported at module top as alias
        if not hasattr(self, f.name):
            if f.default_factory is not dataclasses.MISSING:
                object.__setattr__(self, f.name, f.default_factory())
            elif f.default is not dataclasses.MISSING:
                object.__setattr__(self, f.name, f.default)
    object.__setattr__(self, '_initialized', True)
```

Note: `dc_fields` is already imported at line 12 (`from dataclasses import ... fields as dc_fields`). The method uses the module-level import rather than importing inside the body.

**Step 4** — Verify that `PipelineState.load()` (deserialization path) calls `_ensure_fields_initialized()` after reconstructing the object, to ensure resumed states are fully initialized before any setter fires.

#### Acceptance Criteria

- Unit test: create a `PipelineState`, set `problem`, `task_type`, `language` in sequence; assert `_ensure_fields_initialized` was called only once (use a counter or mock).
- Unit test: deserialize a minimal state dict (missing several new fields) via `PipelineState.load()`, assert all fields have defaults without errors.
- Benchmark (optional): measure total property-setter time across a full pipeline run before and after — expect >30% reduction.

---

### H2 — User-Scope the Token Cache Key

**Priority:** HIGH  
**Effort:** Small (0.5 days)  
**File:** `src/reasoner/infrastructure/token_cache.py`, `src/reasoner/application/pipeline.py`

#### Background

`TokenAwareCache._compute_key()` (token_cache.py:122–125) generates cache keys as:

```python
content = f"{problem}:{phase}:{model_id}:{prompt}"
return hashlib.sha256(content.encode()).hexdigest()[:32]
```

There is no user or session component in the key. Two users submitting identical prompts — common for stock/factual queries — share a cache entry. This causes:
1. Wrong cost attribution (tokens counted for whoever populates the cache).
2. Potential privacy leak if context from a previous user's session bleeds into the prompt.

#### Implementation

**Step 1** — Add an optional `agent_id` parameter to `TokenAwareCache.get()`, `set()`, and `_compute_key()`:

```python
def _compute_key(
    self,
    problem: str,
    phase: str,
    model_id: str,
    prompt: str,
    agent_id: str = "",
) -> str:
    """Compute cache key. agent_id scopes the cache to a user/session."""
    content = f"{agent_id}:{problem}:{phase}:{model_id}:{prompt}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]
```

**Step 2** — Update `get()` and `set()` signatures to accept and pass through `agent_id: str = ""`.

**Step 3** — Wherever `LLMExecutor` (or the pipeline) calls `cache.get()` and `cache.set()`, pass the `agent_id` from `PipelineState.conversation_state.conversation_id` (which is already set for authenticated sessions).

**Step 4** — Add a `SHARED_CACHE_ROLES: frozenset[str]` constant in `constants_limits.py` listing LLM roles whose outputs are safe to share across users (e.g., `{"classification"}` — task-type classification of public factual prompts). Callers for those roles pass `agent_id=""` to opt into shared caching. All other roles use the user-scoped key.

#### Note on Existing Cache Entries

The key change will cause all existing cache entries to be cache-misses on first deploy (the old keys have no `agent_id:` prefix). This is acceptable — the cache is ephemeral and the first run after deploy will repopulate it with user-scoped entries.

#### Acceptance Criteria

- Unit test: two `cache.get()` calls with identical `problem/phase/model_id/prompt` but different `agent_id` values → different keys, no cross-user hit.
- Unit test: `SHARED_CACHE_ROLES` opt-in (`agent_id=""`) → same key for both users.
- Regression test: existing `cache.get()` calls without `agent_id` default to `""` (shared) — no call-site failures.

---

### H3 — EventBus Graceful Drain on Shutdown

**Priority:** HIGH  
**Effort:** Medium (1 day)  
**File:** `src/reasoner/application/event_bus/bus.py`

#### Background

`EventBus.stop()` (bus.py:116–127) cancels the worker task immediately:

```python
async def stop(self) -> None:
    if not self._running:
        return
    self._running = False
    if hasattr(self, "_worker_task"):
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
```

Any events in `self._task_queue` that have been `put_nowait()`-ed but not yet consumed by `_queue_worker()` are silently discarded. On `SIGTERM` (every rolling deploy, every crash restart), in-flight events — including `PIPELINE_COMPLETED` and `PHASE_COMPLETED` — are lost. The dead-letter log only records handler errors, not events dropped at shutdown.

Additionally, `_DEAD_LETTER_PATH.parent.mkdir(parents=True, exist_ok=True)` at module scope (line 29) runs at import time, failing with `PermissionError` on read-only filesystems.

#### Implementation

**Step 1** — Move the `mkdir` call out of module scope and into the `start()` method (and wrap defensively):

```python
# Remove line 29:
# _DEAD_LETTER_PATH.parent.mkdir(parents=True, exist_ok=True)

# Add to EventBus.start(), after self._running = True:
try:
    _DEAD_LETTER_PATH.parent.mkdir(parents=True, exist_ok=True)
    self._dead_letter_enabled = True
except PermissionError:
    logger.warning(
        "Cannot create dead-letter log directory %s — dead-letter logging disabled.",
        _DEAD_LETTER_PATH.parent,
    )
    self._dead_letter_enabled = False
```

**Step 2** — Add a `drain()` method to `EventBus`:

```python
async def drain(self, timeout: float = 5.0) -> None:
    """Process all queued events before shutdown.

    Waits up to `timeout` seconds for the queue to empty.
    Events not processed within the timeout are logged to dead-letter.
    """
    if self._task_queue is None or self._task_queue.empty():
        return
    try:
        await asyncio.wait_for(self._task_queue.join(), timeout=timeout)
    except asyncio.TimeoutError:
        remaining = self._task_queue.qsize()
        logger.warning(
            "EventBus drain timed out after %.1fs with %d events remaining.",
            timeout,
            remaining,
        )
        self._dropped_event_count += remaining
```

**Step 3** — Call `drain()` in `stop()` before cancelling the worker:

```python
async def stop(self) -> None:
    if not self._running:
        return
    self._running = False
    await self.drain(timeout=5.0)  # ← new: flush pending events
    if hasattr(self, "_worker_task"):
        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
```

**Step 4** — Call `await bus.stop()` (not just `bus.clear()`) in the `lifespan()` teardown block in `api/__init__.py`, after the compaction task is cancelled (line 151):

```python
# After the background task cancellations:
from reasoner.application.event_bus.bus import get_event_bus
await get_event_bus().stop()
```

**Step 5** — Update `_log_to_dead_letter()` to check `self._dead_letter_enabled` before writing:

```python
async def _log_to_dead_letter(self, event: DomainEvent, error_message: str, handler_name: str = "") -> None:
    if not getattr(self, '_dead_letter_enabled', True):
        return
    # ... existing code ...
```

#### Acceptance Criteria

- Unit test: publish 10 events, call `stop()` with `timeout=1.0`, assert all 10 are processed (handler called 10 times).
- Unit test: publish 10 events, fill queue, call `stop()` with `timeout=0.001`, assert `_dropped_event_count > 0` and a warning is logged.
- Unit test (M1 fix): import `bus` module in a context where the log directory is read-only, assert no exception is raised at import time.

---

### H4 — RunStateManager Idempotency Failsafe Under Redis Failure

**Priority:** HIGH  
**Effort:** Small (0.5 days)  
**Files:** `src/reasoner/infrastructure/redis/run_state.py`, `src/reasoner/api/__init__.py`

#### Background

`RunStateManager.add()` (run_state.py:105–111) always registers the `cancel_event` in the **in-memory fallback** store, regardless of whether Redis succeeded:

```python
async def add(self, run_id: str, user_id: str | None = None) -> asyncio.Event:
    try:
        await self._redis_op(lambda: self._add_redis(run_id))
    except _RedisUnavailable:
        pass
    return await self._get_fallback().add(run_id, user_id=user_id)
```

The idempotency check in `api/__init__.py:477–484` calls `_run_state_manager.get_cancel_event()`:

```python
existing = await _run_state_manager.get_cancel_event(req.client_run_id)
if existing is not None:
    raise HTTPException(status_code=409, ...)
```

`get_cancel_event()` (line 132) only reads from the in-memory fallback:

```python
async def get_cancel_event(self, run_id: str) -> asyncio.Event | None:
    return await self._get_fallback().get_cancel_event(run_id)
```

In a multi-worker deployment where Redis is down:
- Worker A registers run `R-123` in its local in-memory store.
- Worker B receives a duplicate request for `R-123`; its local in-memory store has no entry for it.
- Worker B's idempotency check passes; the duplicate run executes.

#### Implementation

**Step 1** — Add `is_authoritative() -> bool` to `RunStateManager`:

```python
def is_authoritative(self) -> bool:
    """Return True if the state store is shared across all workers (Redis up).

    When False, idempotency guarantees only hold within a single worker process.
    """
    return self._redis_ok
```

**Step 2** — Update the idempotency check in `api/__init__.py` (lines 477–484) to reject requests when the state store is not authoritative:

```python
if req.client_run_id:
    from reasoner.infrastructure.redis.run_state import _run_state_manager
    if not _run_state_manager.is_authoritative():
        raise HTTPException(
            status_code=503,
            detail="Run state store unavailable. Retry after Redis recovers.",
            headers={"Retry-After": "10"},
        )
    existing = await _run_state_manager.get_cancel_event(req.client_run_id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Run {req.client_run_id} is already in progress",
        )
```

**Note:** This returns 503 only for requests that supply a `client_run_id` (opt-in idempotency). Anonymous runs (no `client_run_id`) are not affected and continue to work when Redis is down.

#### Acceptance Criteria

- Unit test: mock `_redis_ok = False` → `is_authoritative()` returns `False`.
- Unit test: mock `_redis_ok = True` → `is_authoritative()` returns `True`.
- Integration test: POST `/api/run` with `client_run_id` when Redis is down → 503 with `Retry-After` header.
- Integration test: POST `/api/run` without `client_run_id` when Redis is down → runs normally (no 503).

---

## Sprint 3: Medium Fixes and Optimizations

---

### M1 — EventBus `mkdir` at Module Scope

> **Resolved as part of H3, Step 1.** See H3 implementation above.

---

### M2 — User Tier Integration (TODO #502)

**Priority:** MEDIUM  
**Effort:** Medium (1–2 days, requires Supabase/Stripe lookup)  
**Files:** `src/reasoner/api/__init__.py`, `src/reasoner/api/auth_deps.py`, `src/reasoner/application/orchestrator.py`

#### Background

`api/__init__.py:485` contains:

```python
# TODO(#502): use actual user tier from subscription DB
```

Until resolved, all authenticated users get the same concurrency and token budget. Premium presets ($0.15–$0.30/run) are financially unsafe without budget enforcement.

#### Implementation

**Step 1** — Define a `UserTier` enum in `src/reasoner/domain/models.py` (alongside `TaskType`):

```python
from enum import Enum

class UserTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"
    ANONYMOUS = "anonymous"
```

**Step 2** — Add `get_user_tier(user_id: str) -> UserTier` to `src/reasoner/api/auth_deps.py`. The implementation queries Supabase (already in requirements.txt) using the `supabase` client:

```python
async def get_user_tier(user_id: str | None) -> UserTier:
    if user_id is None:
        return UserTier.ANONYMOUS
    try:
        from reasoner.infrastructure.billing.supabase_client import get_supabase
        client = get_supabase()
        result = await client.from_("user_subscriptions") \
            .select("tier") \
            .eq("user_id", user_id) \
            .single() \
            .execute()
        tier_str = result.data.get("tier", "free") if result.data else "free"
        return UserTier(tier_str)
    except Exception as exc:
        logger.warning("Failed to fetch user tier for %s: %s", user_id, exc)
        return UserTier.FREE  # Default to free on failure
```

**Step 3** — Pass `user_tier` to `PipelineOrchestrator.preflight()` (orchestrator.py:73). The orchestrator can then enforce budget caps at the preset level: if `user_tier == FREE` and the selected preset is a premium tier, return an appropriate error or downgrade the preset.

**Step 4** — Remove the `TODO(#502)` comment once the above is wired.

#### Acceptance Criteria

- Unit test: `get_user_tier(None)` → `UserTier.ANONYMOUS`.
- Unit test: mock Supabase returning `{"tier": "pro"}` → `UserTier.PRO`.
- Unit test: mock Supabase exception → `UserTier.FREE` (safe default).
- Integration test: free-tier user requests a premium preset → 402 or preset-downgrade response.

---

### M3 — Document or Remove the `article` Workflow Strategy

**Priority:** MEDIUM  
**Effort:** Trivial (0.5 days)  
**Files:** `src/reasoner/application/flows/factory.py`, `src/reasoner/domain/preset_registry.py`, `CLAUDE.md`

#### Background

`WorkflowFactory` (factory.py) registers an `"article"` strategy, but:
- It does not appear in `CLAUDE.md`'s 19-method list.
- No Budget/Premium preset pair exists for it in `preset_registry.py`.
- `streaming.py:399–405` uses `is_article_request()` to override `state.method = "writing"`, not `"article"`, before any flow dispatch.

This means `"article"` is either a dead code path or an undocumented alias for `"writing"`.

#### Implementation

**Option A (preferred if article is a writing alias):** Remove the `"article"` registration from `WorkflowFactory`. Verify that `is_article_request()` only ever routes to `"writing"` and that no test or preset sets `method="article"` directly. Add a comment to the `writing` strategy:

```python
# Handles both explicit "writing" method requests and article-detected rewrites
# from is_article_request() in api/streaming.py.
```

**Option B (if article is intentionally distinct):** Add `article` as a 20th method in `CLAUDE.md`, create a Budget/Premium preset pair in `preset_registry.py`, and add a unit test for the `WorkflowFactory.get_strategy("article")` path.

Run `grep -r '"article"' src/reasoner/` before deciding which option applies.

#### Acceptance Criteria

- After the change, `WorkflowFactory.get_strategy("article")` either returns a valid strategy (Option B) or returns `None` / raises a clear error (Option A — add an explicit assertion).
- `CLAUDE.md` method list is accurate.

---

### M4 — HyperGateAgent Cache TTL

**Priority:** MEDIUM  
**Effort:** Small (0.5 days)  
**File:** `src/reasoner/hypergate/hyperagent.py`

#### Background

`HyperGateAgent` maintains a SHA-256 LRU cache for routing decisions capped at `HYPERGATE_CACHE_SIZE` with no TTL. A routing decision made when the web-search sub-agent was unavailable (e.g., SearXNG down) can be cached as `action="pipeline"` and served indefinitely for the same prompt, even after SearXNG recovers.

#### Implementation

**Step 1** — Replace the plain LRU dict with `cachetools.TTLCache`. If `cachetools` is not already in requirements, add it (it is a small, zero-dependency package):

```python
# requirements.txt: add cachetools>=5.3
from cachetools import TTLCache

# In HyperGateAgent.__init__:
_HYPERGATE_CACHE_TTL_SECONDS = 3600  # 1 hour
self._cache: TTLCache = TTLCache(
    maxsize=settings.HYPERGATE_CACHE_SIZE,
    ttl=_HYPERGATE_CACHE_TTL_SECONDS,
)
```

**Step 2** — The cache lookup and write remain unchanged; `TTLCache` exposes the same dict-like interface, so no call-site changes are needed.

**Step 3** — Expose the cache TTL as a constant in `core/constants_limits.py`:

```python
HYPERGATE_CACHE_TTL_SECONDS: int = int(os.getenv("HYPERGATE_CACHE_TTL", "3600"))
```

#### Acceptance Criteria

- Unit test: populate cache with a decision, advance time past TTL (mock `time.monotonic`), assert cache misses.
- Unit test: cache does not grow beyond `HYPERGATE_CACHE_SIZE` entries.

---

### O1 — ProviderRouter Per-Request Role Resolution Cache

**Priority:** OPTIMIZATION  
**Effort:** Small (0.5 days)  
**File:** `src/reasoner/infrastructure/llm/router.py`

#### Background

`ProviderRouter._call_with_circuit()` resolves the provider from the routing table on every call. A single pipeline run (4–6 phases × 3–6 parallel LLM calls) makes 12–36 routing table walks per run. While each walk is O(dict lookup), the repeated work is unnecessary within the lifetime of a single request.

#### Implementation

**Step 1** — Add a `resolve(role: str) -> Provider` method to `ProviderRouter` that caches results in an instance-level dict:

```python
def resolve(self, role: str) -> Any:
    """Return the provider for a role, with per-instance caching."""
    if not hasattr(self, '_resolved_cache'):
        self._resolved_cache: dict[str, Any] = {}
    if role not in self._resolved_cache:
        self._resolved_cache[role] = self._routing_table.get(role, self.primary)
    return self._resolved_cache[role]
```

**Step 2** — Update `call()` to use `resolve()` internally:

```python
async def call(self, role: str, ...) -> tuple[str, dict]:
    provider = self.resolve(role)
    return await self._call_with_circuit(provider, ...)
```

**Step 3** — `_resolved_cache` is instance-level, so each pipeline run's `ProviderRouter` instance (created fresh per run in `orchestrator.py`) gets a fresh cache. No invalidation is needed.

#### Acceptance Criteria

- Unit test: `router.resolve("constructive")` called twice → routing table accessed once (verify with a mock that counts hits).

---

### O2 — HyperGate Fast-Path Length Guard

**Priority:** OPTIMIZATION  
**Effort:** Trivial (0.25 days)  
**File:** `src/reasoner/hypergate/hyperagent.py`

#### Background

The fast-path in `HyperGateAgent` scans three regex sets (`_CREATIVE_PATTERNS`, `_REALTIME_PATTERNS`, `_FACTUAL_PATTERNS`) for every input, including trivially short prompts (< 50 chars) that will never match multi-word patterns like `write a comprehensive essay`.

#### Implementation

Add a length guard before the regex scan in the fast-path method (the exact method name varies — grep for `_CREATIVE_PATTERNS` usage in hyperagent.py to confirm the method name):

```python
# Before any regex scanning:
if len(problem) < 50:
    # Short inputs never match multi-keyword creative/realtime/factual patterns.
    # Fall through directly to the 5-agent parallel phase.
    return None  # (or whatever the "no fast-path match" sentinel is)
```

#### Acceptance Criteria

- Unit test: 3-word input → fast-path returns no match without scanning any regex.
- Unit test: 100-char creative writing prompt → fast-path still scans and matches.

---

### O3 — `PipelineState.to_context_dict()` Dirty Flag

**Priority:** OPTIMIZATION  
**Effort:** Small (0.5 days)  
**File:** `src/reasoner/domain/pipeline_state.py`

#### Background

`to_context_dict()` is called once per phase (5 times per 5-phase run, up to 9 times for extended methods). At `Aggressive` compression level it invokes `smart_compress()` which performs string scanning and regex replacement on the entire state. Most phase-to-phase transitions update only 2–3 fields; the full context dict doesn't change between reads.

#### Implementation

**Step 1** — Add `_context_dict_dirty: bool = True` to `PipelineState.__init__` (via `object.__setattr__`).

**Step 2** — Set `_context_dict_dirty = True` in the property setters for the fields that contribute to `to_context_dict()`. Identify these by reading `to_context_dict()` — typically `problem`, `decomposition`, `candidates`, `final_solution`, `errors`, and a few others. Only those setters need to set the flag.

**Step 3** — Cache the result:

```python
def to_context_dict(self, compression_level: str = "Standard") -> dict:
    cache_attr = f"_context_dict_cache_{compression_level}"
    if not self._context_dict_dirty and hasattr(self, cache_attr):
        return getattr(self, cache_attr)
    result = self._build_context_dict(compression_level)  # existing logic renamed
    object.__setattr__(self, cache_attr, result)
    object.__setattr__(self, '_context_dict_dirty', False)
    return result
```

#### Acceptance Criteria

- Unit test: call `to_context_dict()` twice without modifying any context-contributing field → `smart_compress()` called once, not twice.
- Unit test: set `problem` between calls → `smart_compress()` called twice.

---

## Sprint 4: Enhancements and Documentation

---

### E1 — Expose `EventBus` Dead-Letter Count to Health Endpoint

**Priority:** ENHANCEMENT  
**Effort:** Small (0.5 days)  
**Files:** `src/reasoner/api/routes/health.py` (or equivalent), `src/reasoner/application/event_bus/bus.py`

#### Background

`EventBus._dropped_event_count` is tracked (bus.py:55, 168) and exposed via the `dropped_event_count` property (bus.py:251–253), but it is never surfaced to monitoring. Event drops are invisible in production dashboards.

#### Implementation

**Step 1** — Add a `stats()` method to `EventBus` that returns a dict of observable metrics:

```python
def stats(self) -> dict[str, int]:
    return {
        "dropped_event_count": self._dropped_event_count,
        "queue_size": self._task_queue.qsize() if self._task_queue else 0,
        "total_subscribers": self.total_subscribers,
        "running": self._running,
    }
```

**Step 2** — Add an `/api/internal/event-bus` endpoint (protected by admin auth):

```python
@app.get("/api/internal/event-bus")
async def event_bus_stats(auth = Depends(require_admin)):
    from reasoner.application.event_bus.bus import get_event_bus
    return get_event_bus().stats()
```

**Step 3** — Include `dropped_event_count` in the existing `/api/health` response (if it exists and is already serializing system metrics). If `dropped_event_count > 0`, add `"event_bus": "degraded"` to the health status.

#### Acceptance Criteria

- `GET /api/internal/event-bus` returns JSON with `dropped_event_count`, `queue_size`, `total_subscribers`.
- After artificially filling the event queue, `dropped_event_count > 0` is visible in the response.

---

### E2 — Replace Stale Preset Count Comment with Runtime Assertion

**Priority:** ENHANCEMENT  
**Effort:** Trivial (15 min)  
**File:** `src/reasoner/domain/preset_registry.py`

#### Background

Line 14 says `"# Declarative configuration for all 24 presets (2 per method)."` but the actual preset count is larger (CLAUDE.md states 48). The comment has not been updated as methods were added, misleading contributors into thinking the list is shorter than it is.

#### Implementation

**Step 1** — Remove the hardcoded count from the comment:

```python
# Declarative configuration — one Budget and one Premium entry per method.
_PRESET_CONFIGS: list[dict] = [
```

**Step 2** — Add a runtime assertion after `PRESETS` is built (at the bottom of the file, after the dict comprehension that builds `PRESETS` from `_PRESET_CONFIGS`):

```python
# Every method must have exactly one Budget and one Premium variant.
_preset_ids = list(PRESETS.keys())
assert len(_preset_ids) % 2 == 0, (
    f"Expected an even number of presets (Budget+Premium pairs), got {len(_preset_ids)}. "
    f"Add or remove a preset to restore pairing. Presets: {_preset_ids}"
)
```

This assertion fires at module import time, so a misconfigured preset list fails loudly during startup rather than silently at runtime.

#### Acceptance Criteria

- Unit test: temporarily add a single unpaired preset to `_PRESET_CONFIGS` → `assert` triggers on import.
- Module imports normally with the current even-count list.

---

### E3 — Update CLAUDE.md Known Violations Section

**Priority:** ENHANCEMENT  
**Effort:** Trivial (15 min)  
**File:** `CLAUDE.md`

#### Background

`CLAUDE.md` Section 1 lists `domain/preset_core.py` as importing from `infrastructure.llm.registry` (a layer violation). The current code at `preset_core.py` contains the comment:

> "Removed ProviderRouter and _REGISTRY imports to restore domain purity"

The violation has been fixed but the documentation still lists it as active.

#### Implementation

Update `CLAUDE.md` Known Violations section:

1. Remove the `domain/preset_core.py` entry (violation resolved).
2. Add the C1 item as a tracked, flagged violation:

```markdown
**Known violations:**
- `api/streaming.py` directly manages pipeline execution rather than routing through
  `RunPipelineCommandHandler`. This is controlled by the `CQRS_BYPASS_STREAMING` feature flag
  (default `true`). See `docs/ENHANCEMENT_PLAN.md` C1 for the migration plan.
- `application/flows/__init__.py` previously had a circular dependency with `api/serializers.py`
  — resolved by removing the import (commented out).
```

#### Acceptance Criteria

- `CLAUDE.md` Known Violations section reflects the current codebase state.
- No entry describes a violation that has already been fixed.

---

### E4 — `PipelineState.save()` Path Traversal Guard Test

**Priority:** ENHANCEMENT  
**Effort:** Small (0.25 days)  
**File:** `tests/unit/test_pipeline_state.py` (create if not exists)

#### Background

`PipelineState.save()` and `load()` contain path traversal guards, but there are no tests asserting they reject adversarial paths. The guard's correctness is unverified.

#### Implementation

Add to `tests/unit/test_pipeline_state.py`:

```python
import pytest
from reasoner.domain.pipeline_state import PipelineState

def make_minimal_state() -> PipelineState:
    return PipelineState(problem="test problem")

class TestPathTraversalGuard:
    """PipelineState.save/load must reject path traversal attempts."""

    @pytest.mark.parametrize("bad_path", [
        "../../etc/passwd",
        "../secret",
        "/absolute/path",
        "subdir/../../outside",
    ])
    def test_save_rejects_traversal(self, bad_path, tmp_path):
        state = make_minimal_state()
        with pytest.raises((ValueError, OSError), match=r"traversal|outside|invalid|absolute"):
            state.save(bad_path)

    @pytest.mark.parametrize("bad_path", [
        "../../etc/shadow",
        "../secret.json",
    ])
    def test_load_rejects_traversal(self, bad_path):
        with pytest.raises((ValueError, OSError), match=r"traversal|outside|invalid|absolute"):
            PipelineState.load(bad_path)
```

If the guard raises a different exception type, update the `pytest.raises` accordingly.

#### Acceptance Criteria

- All 6 parametrized cases pass (traversal paths are rejected).
- A valid path in `tmp_path` saves and loads successfully.

---

### O4 — Add `healing/generated_tests/` to Pytest Discovery

**Priority:** OPTIMIZATION / ENHANCEMENT  
**Effort:** Trivial (15 min)  
**Files:** `pytest.ini` (or `pyproject.toml`), `.github/workflows/test.yml`

#### Background

`healing/generated_tests/` contains 40+ auto-generated test files that are never run by CI because `pytest.ini` `testpaths` only includes `tests/`. These tests run zero times, defeating the purpose of the self-healing engine.

#### Implementation

**Step 1** — Add `healing/generated_tests` to `testpaths` in `pytest.ini`:

```ini
[pytest]
testpaths =
    tests
    healing/generated_tests
```

**Step 2** — The healing tests likely call real LLMs. Add a custom mark `@pytest.mark.healing` and a corresponding `filterwarnings` / `addopts` configuration so the CI fast-suite excludes them:

```ini
markers =
    healing: auto-generated self-healing tests (may require live LLM endpoints)
```

**Step 3** — Add a separate CI job in `.github/workflows/test.yml` that runs only healing tests, triggered nightly:

```yaml
healing-tests:
  runs-on: ubuntu-latest
  if: github.event_name == 'schedule'
  steps:
    - uses: actions/checkout@v4
    - run: python -m pytest healing/generated_tests/ -m healing -v
      env:
        OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
```

**Step 4** — Ensure all files in `healing/generated_tests/` have a `@pytest.mark.healing` decorator added either by the test generation engine or by a one-time migration script.

#### Acceptance Criteria

- `python -m pytest tests/ -m "not healing"` runs the fast suite (unchanged).
- `python -m pytest healing/generated_tests/ -m healing` runs the healing suite and reports collected tests (not 0).

---

## Cross-Cutting Concerns

### Testing Strategy

For each item, the test order is:

1. Write a **failing test** that reproduces the issue (RED).
2. Implement the fix (GREEN).
3. Refactor if needed (IMPROVE).
4. Add regression coverage in the CI `test.yml` pipeline.

Use `pytest.mark.parametrize` extensively for the path traversal and tier checks (E4, M2).

All new tests belong in `tests/unit/` (pure logic, no I/O) or `tests/integration/` (requires live services). Mark integration tests with `@pytest.mark.integration` so the fast CI suite can skip them.

### Rollout Order

Sprint 1 fixes (C1, C2) should land together. Never deploy C2 alone without confirming Redis is reachable in staging first.

Sprint 2 fixes (H1–H4) are independent and can be merged in any order, but H1 should include the `_ensure_fields_initialized` unit tests before H3 (EventBus drain) touches related state.

Sprint 3 and Sprint 4 items are independent improvements and can be merged in any order.

### Backward Compatibility

- **H1** (`_ensure_fields_initialized`): the existing `--resume` path must continue to work. Test with a saved state file that is missing 3+ fields added after it was saved.
- **H2** (token cache key change): document as a cache-busting deploy. First run after deploy will have 0% cache hit rate until the new user-scoped keys warm up. This is expected.
- **E2** (preset assertion): the assertion fires at import time. If any preset configuration is incorrect, the service will refuse to start. This is the desired behavior — fail fast rather than serve broken presets.

### Security Considerations

- **C2** (Redis probe): the probe key `_startup_probe` is set with `ex=10` (expires in 10 seconds) and `nx=True` (only sets if not already present). It does not interfere with application data.
- **H2** (cache scoping): ensure the `agent_id` is validated (non-empty string from an authenticated session) before trusting it as a cache scope. Do not allow user-supplied arbitrary strings as `agent_id`.
- **H4** (503 on Redis failure): ensure the `Retry-After` header is always set on 503 responses to avoid client thundering-herd on recovery.

---

## Summary Table

| ID | Category | File(s) | Effort | Sprint |
|----|----------|---------|--------|--------|
| C1 | Critical | streaming.py, handlers.py, settings.py | Large | 1 |
| C2 | Critical | api/__init__.py, settings.py | Small | 1 |
| H1 | High | domain/pipeline_state.py | Small | 2 |
| H2 | High | infrastructure/token_cache.py, application/pipeline.py | Small | 2 |
| H3 | High | application/event_bus/bus.py, api/__init__.py | Medium | 2 |
| H4 | High | infrastructure/redis/run_state.py, api/__init__.py | Small | 2 |
| M2 | Medium | api/auth_deps.py, application/orchestrator.py | Medium | 3 |
| M3 | Medium | application/flows/factory.py, domain/preset_registry.py | Trivial | 3 |
| M4 | Medium | hypergate/hyperagent.py | Small | 3 |
| O1 | Opt | infrastructure/llm/router.py | Small | 3 |
| O2 | Opt | hypergate/hyperagent.py | Trivial | 3 |
| O3 | Opt | domain/pipeline_state.py | Small | 3 |
| E1 | Enhancement | event_bus/bus.py, api/routes/health.py | Small | 4 |
| E2 | Enhancement | domain/preset_registry.py | Trivial | 4 |
| E3 | Enhancement | CLAUDE.md | Trivial | 4 |
| E4 | Enhancement | tests/unit/test_pipeline_state.py | Small | 4 |
| O4 | Enhancement | pytest.ini, .github/workflows/test.yml | Trivial | 4 |
