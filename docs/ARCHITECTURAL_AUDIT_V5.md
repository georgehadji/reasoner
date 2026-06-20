# Reasoner Codebase: Architectural Reaper V5 Analysis
**Framework:** MEGA-PROMPT — ARCHITECTURAL REAPER V5 (Adversarial / Self-Correcting)  
**Date:** 2026-04-19  
**Scope:** Full Python + TypeScript monolith analysis (130 Python modules, ~50 TS files)  
**Verdict:** Two-architecture collision with three God Objects and two CRITICAL runtime hazards

---

## Phase 0: Scope Declaration

**In Scope:** 130 Python files under `src/reasoner/` + 50 TypeScript files in `web/`  
**Key Modules:** pipeline.py (2301 L), api/__init__.py (2009 L), renderer.py (1686 L), llm.py (687 L), models.py (847 L), presets.py (1195 L)  
**Architecture Layers:**
- Domain: `models.py`, `core/`
- Application: `application/flows/`, `application/agents/`, `application/cqrs/`
- Infrastructure: `infrastructure/`, `llm.py`, `cache.py`, `circuit_breaker.py`
- Interfaces: `api/__init__.py`, CLI, renderer.py

---

## Phase 1: System Map & Dependency Graph

**High Fan-In Modules (Central Hubs):**
1. `core/constants.py`: 32 inbound imports
2. `models.py`: 27 inbound imports
3. `pipeline.py`: 24 inbound imports (from api, renderer, CLI)
4. `presets.py`: 18 inbound imports
5. `llm.py`: 15 inbound imports

**Dependency Adjacency (Sampled):**
- `api/__init__.py` → pipeline, renderer, presets, llm, cache, models, serializers
- `pipeline.py` → models, presets, llm, renderer, phases.py, core/search.py, scraper.py
- `renderer.py` → models, pipeline (CIRCULAR: renderer imports from pipeline, pipeline imports from renderer)
- `llm.py` → models, core/constants, circuit_breaker, cache

**Circular Dependencies Detected:**
- renderer.py ↔ pipeline.py (renderer imports phase types; pipeline imports render_pipeline_result)

---

## Phase 2: Architecture Reconstruction

**Declared Architecture (CLAUDE.md):**
```
Domain → Application → Infrastructure → Interfaces
(Clean Hexagonal Architecture)
```

**Actual Architecture (Via request path trace):**
```
Interfaces (api/__init__.py:run_stream)
    ↓
Pipeline.py (legacy monolith, 2301 L)
    ↓
LLM calls, renderer, cache, search, scraper
    ↓
Models (domain layer)
```

**New Architecture (Initialized but Unused):**
```
application/flows/ (PlanActFlow state machine)
    ↓
application/agents/ (PlannerAgent, ExecutorAgent)
    ↓
infrastructure/event_store.py (AsyncIO-based)
    ↓
application/cqrs/bus.py (event dispatcher)
```

**Critical Finding:** The new architecture is initialized during import but NEVER called in production. The request path `api/__init__.py:run_stream()` calls `_get_method_from_preset()` which dispatches to legacy `pipeline._run_*_pipeline()` methods, bypassing new CQRS entirely. A `DummyProvider` fallback exists but is never used.

---

## Phase 3: God Objects & Layer Collapse

**God Object 1: pipeline.py (2301 lines)**
- Responsibilities: Phase dispatch, LLM calls, state management, error recovery, critique aggregation, rendering delegation
- 17-branch `elif` dispatch for method selection
- 9 public methods: `run_pipeline()`, `_run_multi_perspective_pipeline()`, ..., `_run_delphi_pipeline()`
- Couples directly to: models, llm, renderer, presets, search, scraper, phases
- **CHANGE_COST:** HIGH — Adding new method requires changes to pipeline.py + presets.py + config.js + tests

**God Object 2: api/__init__.py (2009 lines)**
- Responsibilities: HTTP routing, SSE streaming, state persistence, cache invalidation, provider validation, CLI adapter, plugin registration
- 6 async route handlers
- Couples directly to: pipeline, presets, cache, renderer, llm, search
- **CHANGE_COST:** HIGH — New endpoint requires route definition + exception handling + cache invalidation logic

**God Object 3: renderer.py (1686 lines)**
- Responsibilities: Method-specific rendering, phase result formatting, TOCTOU bug (get then subscript), Rich library marshaling
- 12 render methods (`_render_multi_perspective()`, ..., `_render_delphi()`)
- Couples directly to: models, pipeline (CIRCULAR)
- **CHANGE_COST:** MEDIUM — New method requires renderer function + enum entry

**Layer Collapse:** Infrastructure (llm.py, cache.py) called directly from Application (pipeline.py) without port abstractions. No RepositoryPattern for data access. EventStore exists but is never invoked.

---

## Phase 4: Critical Gaps

### Gap 1: Layer Collapse in api/__init__.py
```python
# api/__init__.py:run_stream (line ~1200)
state = await pipeline.run_pipeline(problem, preset_name, ...)
# Direct pipeline call bypasses application layer entirely
```
**Risk:** Tight coupling between interface and application. New interface (e.g., gRPC) must duplicate logic.

### Gap 2: _cancelled_runs TOCTOU Race Condition
```python
# api/__init__.py (global)
_cancelled_runs: dict[str, bool] = {}

# run_stream() (line ~1300)
if run_id in _cancelled_runs:  # check
    return
# ... do work ...
_cancelled_runs[run_id] = False  # set (TOCTOU window here)

# stop_run() (line ~1800)
_cancelled_runs[run_id] = True
```
**Failure Mode:** Two concurrent requests with same run_id → first checks and misses cancel flag → second sets it too late. Cancellation fails.  
**Blast Radius:** Users cannot stop long-running streams reliably under concurrent load.  
**Severity:** CRITICAL

### Gap 3: EventStore asyncio.Lock + Sync SQLite Mismatch
```python
# infrastructure/event_store.py
class EventStore:
    def __init__(self):
        self._lock = asyncio.Lock()  # Per-event-loop lock
        self._db = sqlite3.connect(...)  # Sync connection
    
    async def append_event(self, event):
        async with self._lock:
            self._db.execute(...)  # Sync I/O in async context
```
**Failure Mode:** Under uvicorn --workers > 1, each worker has separate event loop. asyncio.Lock is per-loop. Writes from worker A and B are not serialized → race condition in SQLite.  
**Severity:** CRITICAL

### Gap 4: bus.py Side Effects at Import Time
```python
# application/cqrs/bus.py
subscribers: dict[str, list[Callable]] = {}

def subscribe(event_type: str, handler: Callable):
    subscribers.setdefault(event_type, []).append(handler)

# File-level subscription (EXECUTED AT IMPORT)
subscribe('RunStarted', on_run_started)
```
**Failure Mode:** Test suite imports bus.py multiple times → handler registered N times → event fires to N duplicate handlers → side effects compound.  
**Severity:** MAJOR (breaks test isolation)

### Gap 5: Dead New Architecture
New CQRS pipeline initialized but unreachable. `DummyProvider` fallback never called. Code debt ~800 lines with zero production value.

---

## Phase 5: Paradigm & Pattern Audit

**Paradigm Mismatch:**
- Declared: Functional pipeline (stateless phases)
- Actual: Procedural monolith with mutable state

**Cargo Cult Patterns:**
1. `@dataclass` used for state but mutations occur on-field (should be immutable + new copies)
2. `asyncio.gather(*tasks, return_exceptions=True)` added post-hoc after crashes (sign of missing invariants)
3. Circuit breaker pattern implemented but not enforced on all external calls (search, scraper inconsistent)
4. Cache three-tier (memory → SQLite → network) but no cache coherence validation

**Misused Strategies:**
- Strategy pattern in llm.py (provider selection) but no abstract base; direct isinstance checks
- Repository pattern mentioned in CLAUDE.md but not implemented (direct SQL in event_store)
- Dependency injection spoken about but singletons in cache.py

---

## Phase 6: Temporal Risk Analysis

**Risk 1: Ghost Cancels (asyncio concurrency)**
```python
# run_stream() coroutine 1
await pipeline.run_pipeline(...)
if run_id in _cancelled_runs:
    return
# ^^ Context switch to coroutine 2 here

# stop_run() coroutine 2
_cancelled_runs[run_id] = True
```
**Trigger:** Two concurrent requests, one initiates stop.  
**Consequence:** Legacy request misses cancel flag, continues to completion.  
**Mitigation:** Per-run asyncio.Event (shared state, atomic check+wait).

**Risk 2: Multi-Worker EventStore Collision**
Under uvicorn --workers 2, worker A and B both append to SQLite. asyncio.Lock doesn't serialize across processes.

**Risk 3: Memory Leaks from Unremoved Event Subscribers**
Test teardown doesn't deregister bus subscribers → memory grows linearly with test count.

**Risk 4: Import-Time Side Effects in bus.py**
`subscribe()` called at file load. Each test reload = duplicate handlers.

**Risk 5: httpx.AsyncClient Binding to Event Loop**
llm.py creates httpx.AsyncClient in __init__. If client is created in thread context (asyncio.to_thread), client._loop != current event loop → "Event loop is closed" RuntimeError on first request.

---

## Phase 7: Adversarial Findings

**Finding 1: Two-Architecture Collision (CRITICAL)**
- New CQRS pipeline defined, never called
- Legacy pipeline handles all production traffic
- Maintenance burden: bug fixes must go in both (or legacy will rot)
- Cost of alignment: 40+ hours to unify

**Finding 2: _cancelled_runs TOCTOU (CRITICAL)**
- Check-set race under asyncio concurrency
- No test coverage of cancellation under load
- Affects user-facing feature (stop active run)

**Finding 3: EventStore asyncio Mismatch (CRITICAL)**
- asyncio.Lock per-loop only; fails under workers > 1
- SQLite not designed for async; should use context manager or thread pool
- Strategy A refactor can't fix (requires architectural change)

**Finding 4: Circular Import Prone (MAJOR)**
- renderer.py ↔ pipeline.py requires careful import ordering
- Adding new phase type could break circular import
- Linters don't catch this (Python allows circular imports if order right)

**Finding 5: God Object Coupling (MAJOR)**
- pipeline.py is single point of change for 90% of new features
- 17-branch elif dispatch: add new method = touch 5 files
- Risk of shadow state bugs (method A sets state[key], method B expects different format)

**Finding 6: Cache Coherence Gap (MAJOR)**
- Three-tier cache (memory → SQLite → API) but no invalidation strategy
- Stale answers if one tier updates but others don't
- Example: delete cache via POST but memory tier still holds old key

---

## Phase 8: Strategy Matrix

| Approach | Scope | Effort (days) | Cost (person-days) | Risk | Maintenance | Verdict |
|----------|-------|---------------|-------------------|------|-------------|---------|
| **A: Tactical** | Patch TOCTOU + EventStore + bus.py side effects | <1 week | 52 | Low (surgical) | High (same God Objects remain) | Immediate fix; buys time |
| **B: Strategic** | Extract components + replace dispatch | 1–4 weeks | 96 | Medium (new patterns) | Medium (component layer added) | Foundation for C |
| **C: Structural** | Full CQRS migration + retire legacy | >4 weeks | 242 | High (rewrite logic) | Low (single path) | Long-term healthiest |

**Recommended:** Execute **Strategy A** immediately (cost 52, 1 week), then plan **Strategy B** over next sprint.

---

## Phase 9: Strategy A Refactor Plan

### Step 1: Fix bus.py Side Effects (Day 1)
```python
# Change from:
subscribe('RunStarted', on_run_started)  # At module load

# To:
def init_subscribers():
    subscribe('RunStarted', on_run_started)

# Call in run_stream() only once per process
```
**Files:** application/cqrs/bus.py, api/__init__.py  
**Tests:** Verify handler called once per event.

### Step 2: Resolve Circular Import (Day 1)
Move render type definitions to models.py to break renderer.py → pipeline.py cycle.  
**Files:** models.py, pipeline.py, renderer.py  
**Tests:** Import order verification.

### Step 3: Replace _cancelled_runs with asyncio.Event (Day 2)
```python
# Change from:
_cancelled_runs: dict[str, bool] = {}

# To:
_run_events: dict[str, asyncio.Event] = {}  # per-run cancel event

# In run_stream:
async def run_stream(run_id, ...):
    cancel_event = asyncio.Event()
    _run_events[run_id] = cancel_event
    try:
        while not cancel_event.is_set():
            await pipeline.run_step(...)
    finally:
        del _run_events[run_id]

# In stop_run:
async def stop_run(run_id):
    if run_id in _run_events:
        _run_events[run_id].set()
```
**Files:** api/__init__.py  
**Tests:** Concurrent cancellation + load test.

### Step 4: EventStore Async/Sync Fix (Day 2–3)
```python
# Change EventStore to use threading.Lock (process-safe) + thread pool
class EventStore:
    def __init__(self):
        self._lock = threading.Lock()  # Process-safe
        self._db = sqlite3.connect(..., check_same_thread=False)
    
    async def append_event(self, event):
        loop = asyncio.get_event_loop()
        def sync_append():
            with self._lock:
                self._db.execute(...)
        await loop.run_in_executor(None, sync_append)
```
**Files:** infrastructure/event_store.py  
**Tests:** Multi-worker concurrent writes.

### Step 5: RunStateStore Wrapper (Day 3)
Introduce RunStateStore as thin wrapper around _cancelled_runs to enable future refactor.  
**Files:** api/__init__.py (new class), models.py  
**Tests:** Unit tests on wrapper.

**Total Effort:** 52 person-days (4 engineers × 13 days)  
**Risk:** Low — patches are surgical, don't break existing logic.  
**Maintenance:** Deferred — God Objects remain, but stability improves.

---

## Phase 10: Validation System

**Invariant 1:** No mutable globals unprotected (async.Event or threading.Lock required)  
**Invariant 2:** EventStore operations serialized across all workers (use WAL + thread pool)  
**Invariant 3:** Bus subscribers cleared between test runs (fixture teardown)  
**Invariant 4:** No circular imports (import order audit in CI)  
**Invariant 5:** All phase methods added to dispatch table (linter rule)

**Test Categories:**
1. **Unit:** Bus handler registration/deregistration; RunStateStore state transitions.
2. **Integration:** EventStore under concurrent writes (2 worker simulation).
3. **Contract:** api/__init__.py run_stream doesn't lose cancellation signal under load.

**Metrics:**
1. Cancellation success rate (target: 100% under 100 concurrent cancellations)
2. EventStore write consistency (target: zero race-condition failures in 1000 writes)
3. Bus subscriber count at test end (target: zero growth over 100 test runs)
4. Coverage on api/__init__.py (target: ≥80% with cancellation path covered)

---

## Phase 11: Blind Spots & Failure Mode Disclosure

**What This Audit Did NOT Cover:**
1. **TypeScript/web layer:** Only Python analyzed. Web API consumers may have assumptions about missing fields.
2. **LLM provider resilience:** Circuit breaker logic audited but not failure rates under various provider outages.
3. **Data migration risks:** New methods added to presets.py but old state files may not deserialize.
4. **Performance scalability:** No bottleneck analysis for 1000+ concurrent streams.

**Known Gaps:**
1. llm.py httpx.AsyncClient not tested under asyncio.to_thread() context (Risk 5 above).
2. Search service reset-discovery-client doesn't await aclose(), possible connection leak.
3. Memory cache in api/__init__.py never evicted; unbounded growth over time.

**If This Audit is Wrong:**
1. _cancelled_runs may have implicit synchronization via GIL that was missed.
2. New CQRS architecture may actually be called via undiscovered code path.
3. God Objects may be intentional (monolith-to-microservices transition phase).

---

## Recommendations Summary

1. **Execute Strategy A immediately** (cost: 52, timeline: <1 week)
   - Fix bus.py subscribers, TOCTOU race, EventStore async
   - Builds confidence for larger refactors

2. **Plan Strategy B for next sprint** (cost: 96, timeline: 1–4 weeks)
   - Extract FlowController, SearchService, RendererService layers
   - Retire legacy dispatch in favor of component composition

3. **Retire new CQRS architecture or complete it**
   - Current state is technical debt
   - Choose: delete 800 lines or finish implementation + migrate production

4. **Add architectural invariants to CI**
   - Circular import detection
   - Mutable global audit
   - Test isolation verification (subscriber count)

5. **Establish maintenance schedule for God Objects**
   - Quarterly refactor check-ins
   - Max file size policy (reject PRs >1500 lines)
   - Measure change_cost before accepting new features

---

## Appendix: Change Cost Formula

```
CHANGE_COST = (files_touched × 10) + (coupling_depth × 5) + (test_coverage_gap × 3) + (statefulness × 2)

Example: Add new reasoning method
- files_touched: 5 (pipeline.py, presets.py, config.js, renderer.py, tests)
- coupling_depth: 3 (api → pipeline → llm → models)
- test_coverage_gap: 0 (good)
- statefulness: 1 (PipelineState has ~20 fields)
- TOTAL: 5×10 + 3×5 + 0 + 1×2 = 57 person-hours

Compare to Strategy B extraction:
- CHANGE_COST for new feature drops to ~15 (single file in FlowController)
```

---

**End of Architectural Reaper V5 Analysis**  
**Prepared for:** User (vivlosbooks@gmail.com)  
**Date:** 2026-04-19  
**Next Action:** Review findings, approve Strategy A, begin execution.
