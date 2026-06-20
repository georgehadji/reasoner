# Architecture Score 9/10 — Remediation Plan v2

**Audit:** ARCH-AUDIT-V2, 2026-06-07 (this session)
**Baseline score:** 5 / 10 — Early Production
**Target score:** > 9 / 10 — Production
**Scope:** `src/reasoner/` Python backend only
**Prior plan:** `tasks/ARCHITECTURE_SCORE_9_PLAN.md` (2026-06-06, score 6/10)

---

## Already resolved since prior audit

The following items from `ARCHITECTURE_SCORE_9_PLAN.md` are confirmed resolved and do not appear below:

| Item | Evidence |
|------|----------|
| `sys.modules` mutation in `streaming.py` | `grep sys.modules api/streaming.py` → 0 matches |
| `api/__init__.py` module-level `global` statements | `grep ^global api/__init__.py` → 0 matches |
| `domain/preset_core.py` → infrastructure import | `grep infrastructure domain/preset_core.py` → 0 matches |
| `core/protocol.py` → infrastructure import | Confirmed clean |
| `application/handlers/handlers.py` → api import | Confirmed clean |
| `application/flows/__init__.py` circular api.serializers import | Commented out |
| HyperGate unbounded `asyncio.gather()` — Semaphore added | `grep Semaphore hypergate/hyperagent.py` → match found |

---

## Scoring gap: 5 → 9

To reach 9/10 every CRITICAL and HIGH finding must be eliminated; MEDIUM findings reduced to ≤ 1 low-propagation residual.

| Severity | Open count | Required at 9+ |
|----------|-----------|----------------|
| CRITICAL | 1 | 0 |
| HIGH | 4 | 0 |
| MEDIUM | 5 | ≤ 1 |
| Scaling defects | 1 | 0 |

---

## Sprint 0 — Emergency patches (< 1 day, ≤ 5 lines each)

Production crash risks. Fix before any other sprint.

---

### 0-A: `asyncio.run()` inside async context  `[OPEN from prior plan]`

**File:** `src/reasoner/infrastructure/search/discovery.py`
**Evidence:** `grep asyncio.run discovery.py` → 2 matches

**Problem:** `asyncio.run(old.close())` is called from a class method reachable from an async code path. Under uvicorn the event loop is always running. `asyncio.run()` in a running loop raises `RuntimeError: This event loop is already running`.

**Fix:**
```python
# BEFORE
asyncio.run(old.close())

# AFTER — schedule on running loop; fallback for CLI/test context
try:
    loop = asyncio.get_running_loop()
    loop.create_task(old.close())
except RuntimeError:
    asyncio.run(old.close())
```

**Acceptance criteria:**
- [ ] `grep -n "asyncio\.run(" src/reasoner/infrastructure/search/discovery.py` returns 0 matches
- [ ] No `RuntimeError: This event loop is already running` in uvicorn logs under any request path
- [ ] Existing search/discovery tests pass

---

### 0-B: Blocking `fitz.open()` inside async upload handler  `[NEW]`

**File:** `src/reasoner/uploader.py:169`
**Evidence:** `grep fitz.open uploader.py` → 1 match

**Problem:** `fitz.open()` (PyMuPDF) is a synchronous blocking call. If `uploader.py` is reached from a FastAPI endpoint, it blocks the entire uvicorn event loop for the duration of PDF parsing.

**Fix:**
```python
# BEFORE
doc = fitz.open(stream=content, filetype="pdf")

# AFTER — offload to thread pool
import asyncio
doc = await asyncio.to_thread(fitz.open, stream=content, filetype="pdf")
```

Apply the same pattern to any other synchronous I/O in `uploader.py` (file reads, writes) if they appear in async functions.

**Acceptance criteria:**
- [ ] `grep -n "fitz\.open" src/reasoner/uploader.py` shows calls only inside `asyncio.to_thread()`
- [ ] PDF upload endpoint does not block other concurrent requests during processing
- [ ] Upload integration test passes

---

## Sprint 1 — Root layer migration (2–3 days)  `[NEW — CRITICAL]`

The single highest-leverage change available. `src/reasoner/` root contains 8,247 lines across 30+ modules with no layer assignment. Every module in every layer imports from them, creating an ungoverned shared kernel that bypasses all hexagonal boundaries.

---

### 1-A: Assign each root module to its correct layer

**Current `__root__` inventory and target destinations:**

| File | Lines | Target layer | Rationale |
|------|-------|-------------|-----------|
| `reasoner_persuasion_defense.py` | 1,092 | `security/` | Security-domain logic |
| `parsing.py` | 607 | `core/` | Pure parsing utilities, no I/O |
| `uploader.py` | 534 | `infrastructure/` | External file I/O |
| `token_cache.py` | 388 | `infrastructure/cache/` | Infrastructure caching |
| `circuit_breaker.py` | 352 | `infrastructure/` | Infra resilience pattern |
| `rate_limiter.py` | 421 | `infrastructure/` | Infra resilience pattern |
| `auth.py` | 376 | `infrastructure/auth/` | Infra auth adapter |
| `logging_utils.py` | 343 | `core/` | Pure utility, no deps |
| `sanitization.py` | 301 | `core/` or `security/` | Pure transform, no I/O |
| `exceptions.py` | 264 | `core/` | Domain exception hierarchy |
| `scraper.py` | 239 | `infrastructure/` | External HTTP I/O |
| `gate_agent.py` | 219 | `infrastructure/` or `hypergate/` | Agent adapter |
| `metrics.py` | 159 | `infrastructure/` or `core/` | Observability |
| `server_check.py` | 159 | `infrastructure/` | External service check |
| `pricing.py` | 150 | `domain/` | Domain pricing logic |
| `presets.py` | 148 | `domain/` | Preset lookup shim |
| `suggestions.py` | 143 | `application/services/` | Application logic |
| `widgets.py` | 593 | `infrastructure/widgets/` | External widget adapters |
| `renderer.py` | 56 | `infrastructure/` or `core/` | Output rendering |
| `models.py` | 49 | Keep as backward-compat shim | Already a re-export |
| `phases.py` | 31 | Keep as backward-compat shim | Already a re-export |
| `clients.py` | 30 | `infrastructure/` | External client shim |
| `pipeline_owner.py` | 41 | `domain/` or `core/` | Domain concept |
| `start_all.py` | 476 | `scripts/` (top-level, not package) | Dev tooling, not src |
| `main.py` | 411 | Keep at root (CLI entry point) | Entry point stays |
| `ara_*.py` (3 files) | 0 | Delete — empty files | Dead code |

**Migration procedure per module (repeat for each):**

1. Move file to target directory.
2. Add re-export shim at old path for backward compatibility:
   ```python
   # src/reasoner/parsing.py  (shim)
   from reasoner.core.parsing import *  # noqa: F401, F403
   ```
3. Run tests. Fix any import that cannot be shimmed.
4. After all modules are moved, delete shims one by one (confirm no imports remain).

**Do not move all at once.** Move in dependency order: modules with fewest imports first.

**Recommended order:**
1. `exceptions.py` → `core/` (no local deps)
2. `logging_utils.py` → `core/` (no local deps)
3. `sanitization.py` → `core/` (no local deps)
4. `parsing.py` → `core/` (imports exceptions)
5. `metrics.py` → `infrastructure/`
6. `circuit_breaker.py` → `infrastructure/`
7. `rate_limiter.py` → `infrastructure/`
8. `auth.py` → `infrastructure/auth/`
9. `token_cache.py` → `infrastructure/cache/`
10. `scraper.py` → `infrastructure/`
11. `uploader.py` → `infrastructure/`
12. `widgets.py` → `infrastructure/widgets/`
13. `pricing.py` → `domain/`
14. `pipeline_owner.py` → `domain/`
15. `reasoner_persuasion_defense.py` → `security/`
16. `suggestions.py` → `application/services/`
17. `gate_agent.py` → `hypergate/` or `infrastructure/`
18. `server_check.py` → `infrastructure/`
19. `renderer.py` → `infrastructure/`
20. `ara_*.py` → delete

**Acceptance criteria:**
- [ ] `python -c "from pathlib import Path; p=Path('src/reasoner'); mods=[f for f in p.iterdir() if f.suffix=='.py' and f.stem not in ('__init__','models','phases','main','pipeline')]; assert len(mods)==0, mods"` passes
- [ ] `src/reasoner/__root__` layer (as measured by prior audit) reports < 100 lines
- [ ] All existing tests pass after each individual move
- [ ] `grep -rn "from reasoner\." src/reasoner/` imports are consistent with new paths

---

### 1-B: Delete dead empty files  `[NEW — trivial]`

**Files:** `src/reasoner/ara_persuasion_defense.py`, `src/reasoner/ara_verbalized_sampling.py`, `src/reasoner/ara_vs_constants.py`
**Evidence:** All three are 0-byte files.

Simply delete them. Check for any imports first:
```bash
grep -rn "ara_persuasion\|ara_verbalized\|ara_vs_constants" src/
```

**Acceptance criteria:**
- [ ] Three files deleted
- [ ] No remaining imports of them anywhere

---

## Sprint 2 — Remaining layer violations (1 day)

Eliminates the four confirmed cross-layer import violations.

---

### 2-A: `core/search.py` → infrastructure import  `[OPEN from prior plan]`

**File:** `src/reasoner/core/search.py`
**Evidence:** `grep infrastructure core/search.py` → 1 match (`from reasoner.infrastructure.llm.registry import build_provider`)

**Problem:** `core/` must be dependency-free outward. `DiscoveryClient` pulls an LLM provider directly from the registry.

**Fix:** Constructor injection.

```python
# BEFORE — core/search.py reaches into infrastructure
class DiscoveryClient:
    def __init__(self, ...):
        from reasoner.infrastructure.llm.registry import build_provider
        self._provider = build_provider(...)

# AFTER — provider injected at the construction site
class DiscoveryClient:
    def __init__(self, ..., llm_provider=None):
        self._provider = llm_provider  # None = AI-reranking disabled gracefully
```

**Construction site** (wherever `DiscoveryClient` is instantiated, likely `application/services/search_service.py`):
```python
from reasoner.infrastructure.llm.registry import build_provider
provider = build_provider(role="deep_read")
client = DiscoveryClient(..., llm_provider=provider)
```

**Acceptance criteria:**
- [ ] `grep -rn "from reasoner.infrastructure" src/reasoner/core/` → 0 matches
- [ ] `DiscoveryClient` can be instantiated in a test without any infrastructure import in scope
- [ ] Search integration tests pass

---

### 2-B: `infrastructure/billing/webhooks.py` → `application/services/billing_service`  `[NEW]`

**File:** `src/reasoner/infrastructure/billing/webhooks.py`
**Evidence:** `from reasoner.application.services.billing_service import BillingService`

**Problem:** Infrastructure layer imports a concrete application service, reversing the dependency rule. Webhooks should emit domain events; the service layer subscribes to them.

**Fix:** Convert to event-driven dispatch.

```python
# BEFORE — webhooks.py calls service directly
from reasoner.application.services.billing_service import BillingService

async def handle_stripe_webhook(request: Request):
    ...
    service = BillingService(...)
    await service.activate_subscription(customer_id, tier)

# AFTER — webhooks.py emits a domain event
from reasoner.core.events.domain_events import make_event, EventType
from reasoner.application.event_bus.bus import get_event_bus

async def handle_stripe_webhook(request: Request):
    ...
    bus = get_event_bus()
    await bus.publish(make_event(
        EventType.SUBSCRIPTION_ACTIVATED,
        data={"customer_id": customer_id, "tier": tier},
    ))
```

Register a `BillingService` subscriber in `api/lifespan.py` startup (or `api/__init__.py`):
```python
bus.subscribe(EventType.SUBSCRIPTION_ACTIVATED, billing_service.on_subscription_activated)
```

**Acceptance criteria:**
- [ ] `grep -n "from reasoner.application.services" src/reasoner/infrastructure/billing/webhooks.py` → 0 matches
- [ ] `EventType.SUBSCRIPTION_ACTIVATED` (or equivalent) exists in `core/events/domain_events.py`
- [ ] Billing integration test confirms subscription activates after webhook fires

---

### 2-C: `infrastructure/llm/executor.py` → `application/event_bus/bus`  `[NEW]`

**File:** `src/reasoner/infrastructure/llm/executor.py`
**Evidence:** Import graph shows `from reasoner.application.event_bus.bus` (1 match)

**Problem:** Infrastructure adapter imports the concrete application event bus rather than an `EventPublisher` port. Ports for auth and billing exist; the bus lacks one.

**Fix:** Define an `EventPublisher` protocol in `core/ports/` and inject it.

**Step 1** — add to `src/reasoner/core/ports/__init__.py` (or new file `event_port.py`):
```python
from typing import Protocol, runtime_checkable
from reasoner.core.events.domain_events import DomainEvent

@runtime_checkable
class EventPublisher(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...
```

**Step 2** — update `executor.py`:
```python
# BEFORE
from reasoner.application.event_bus.bus import get_event_bus

class LLMExecutor:
    async def execute(self, ...):
        bus = get_event_bus()
        await bus.publish(...)

# AFTER — accept publisher at construction
from reasoner.core.ports.event_port import EventPublisher

class LLMExecutor:
    def __init__(self, ..., event_publisher: EventPublisher | None = None):
        self._publisher = event_publisher

    async def execute(self, ...):
        if self._publisher:
            await self._publisher.publish(...)
```

**Step 3** — inject in construction site (wherever `LLMExecutor` is created — likely `application/orchestrator.py` or `infrastructure/llm/router.py`):
```python
from reasoner.application.event_bus.bus import get_event_bus
executor = LLMExecutor(..., event_publisher=get_event_bus())
```

**Acceptance criteria:**
- [ ] `grep -n "from reasoner.application" src/reasoner/infrastructure/llm/executor.py` → 0 matches
- [ ] `LLMExecutor` unit-testable without any application imports in scope
- [ ] `EventPublisher` protocol exists in `core/ports/`

---

## Sprint 3 — Execution path consolidation (2 days)  `[OPEN from prior plan]`

Two execution paths currently exist: `api/streaming.py` orchestrates directly alongside `application/orchestrator.py`. The CQRS `RunPipelineCommandHandler` exists but is not the primary entry point.

---

### 3-A: Route `api/routes/context.py` through `PipelineOrchestrator`

**File:** `src/reasoner/api/routes/context.py`
**Evidence:** `grep ReasonerPipeline api/routes/context.py` → match found

**Problem:** `context.py` constructs `ReasonerPipeline` directly, bypassing quota enforcement, neuro recall, event persistence, and history tracking.

**Fix:** Delegate to `PipelineOrchestrator`.
```python
# context.py — AFTER
from reasoner.application.orchestrator import PipelineOrchestrator

async def run_with_context(req: ContextAnalysisRequest, ...):
    # Keep existing URL validation (security boundary — do not remove)
    _validate_urls(req.urls)

    run_req = RunRequest(
        problem=_build_problem_with_context(req),
        preset=req.preset,
        top_k=req.top_k,
    )
    orchestrator = _build_orchestrator(preset_service, pipeline_service)
    decision = await orchestrator.preflight(run_req)
    state = await orchestrator.execute(decision)
    await orchestrator.postflight(state, run_req, user_id=user.id if user else None)
    return _serialize_context_result(state)
```

**Acceptance criteria:**
- [ ] `grep -n "ReasonerPipeline" src/reasoner/api/routes/context.py` → 0 matches
- [ ] Context endpoint enforces quota (integration test)
- [ ] Context endpoint writes history entry (integration test)

---

### 3-B: Wire `RunPipelineCommandHandler` as the single command entry point

**Current state:** `streaming.py` calls `PipelineOrchestrator` directly. `RunPipelineCommandHandler` exists but is bypassed.

**Target:** `streaming.py` → `RunPipelineCommandHandler` → `PipelineOrchestrator`

**Phase 3-B-1 (additive):** Make `RunPipelineCommandHandler` delegate to `PipelineOrchestrator`:
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

**Phase 3-B-2:** Update `streaming.py` to use the handler:
```python
handler = RunPipelineCommandHandler(
    orchestrator=PipelineOrchestrator(preset_service=..., pipeline_service=...),
    event_store=get_event_store(),
)
command = RunPipelineCommand(problem=req.problem, preset=req.preset, ...)
state = await handler.handle(command)
```

**Acceptance criteria:**
- [ ] Exactly **one** code path constructs and runs `ReasonerPipeline` from the API layer
- [ ] `grep -rn "PipelineOrchestrator\|ReasonerPipeline" src/reasoner/api/` shows only `streaming.py` → handler path
- [ ] All 17 method presets pass E2E test via the new single path

---

## Sprint 4 — Domain God Object decomposition (2–3 days)  `[NEW — HIGH]`

`domain/pipeline_state.py` at 2,062 lines with 153 methods violates the single-responsibility principle and creates high coupling across serializers, handlers, and all 17 flows.

---

### 4-A: Extract serialization logic from `PipelineState`

**Problem:** `domain/pipeline_state.py` contains serialization methods (`.to_dict()`, `.to_json()`, merge helpers, snapshot logic) that belong in the application layer, not the domain.

**Target:** `PipelineState` should be a pure data container — fields and field-level accessors only. No serialization, no merge, no history tracking.

**Step 1** — identify all methods in `PipelineState` that perform I/O or format transformation:
```bash
grep -n "def.*dict\|def.*json\|def.*serialize\|def.*snapshot\|def.*to_\|def.*from_" \
  src/reasoner/domain/pipeline_state.py
```

**Step 2** — move those methods to `application/services/state_serializer.py` (a new, properly named service):
```python
# application/services/state_serializer.py
from reasoner.domain.pipeline_state import PipelineState

def to_dict(state: PipelineState) -> dict: ...
def from_snapshot(data: dict) -> PipelineState: ...
def merge_followup(base: PipelineState, update: dict) -> PipelineState: ...
```

**Step 3** — update all callers to use `state_serializer` functions instead of methods on `state`.

**Step 4** — move history/audit tracking methods from `PipelineState` to `core/aggregates/pipeline.py` (event-sourced aggregate owns history).

**Target:** `domain/pipeline_state.py` ≤ 600 lines after extraction.

**Acceptance criteria:**
- [ ] `domain/pipeline_state.py` ≤ 600 lines
- [ ] No I/O or format-transformation methods remain on `PipelineState`
- [ ] `application/services/state_serializer.py` owns all serialization
- [ ] `test_models_split.py` and `test_pipeline_resume.py` pass

---

### 4-B: Extract method-specific state helpers into flow base classes

**Problem:** 153 methods on `PipelineState` includes method-specific accessors (e.g., `get_debate_rounds()`, `set_jury_state()`, etc.) that each flow should own.

**Fix:** Move per-method accessors into the corresponding flow class:
```python
# BEFORE — in domain/pipeline_state.py
def get_debate_rounds(self) -> list: ...
def set_debate_round(self, round: dict) -> None: ...

# AFTER — in application/flows/debate.py
class DebateFlow:
    @staticmethod
    def get_rounds(state: PipelineState) -> list:
        return state.method_state.get("debate").get("rounds", [])

    @staticmethod
    def set_round(state: PipelineState, round: dict) -> None:
        data = state.method_state.get("debate")
        data["rounds"] = [*data.get("rounds", []), round]
        state.method_state.set("debate", data)
```

**Acceptance criteria:**
- [ ] Method-specific accessors removed from `PipelineState`
- [ ] Each flow file owns its own state accessors
- [ ] `PipelineState` method count ≤ 30 (field accessors, core transitions only)

---

## Sprint 5 — Configuration extraction (1 day)  `[NEW — MEDIUM]`

Two large files are configuration data masquerading as Python code.

---

### 5-A: `domain/preset_registry.py` → structured config (1,916 lines)

**Problem:** 1,916 lines of Python that is really data: `PipelinePreset` initialization with model lists, routing configs, and tier assignments. Zero top-level classes or functions — one giant literal.

**Fix:** Extract preset definitions to `config/presets.toml` (or YAML/JSON). Keep `preset_registry.py` as a 50-line loader:

```toml
# config/presets/debate-budget.toml
[preset]
name = "debate-budget"
method = "debate"
tier = "budget"

[roles]
opening = ["google/gemma-3-27b-it", "meta-llama/llama-3.1-8b-instruct"]
rebuttal = ["anthropic/claude-haiku-4-5"]
judge = ["deepseek/deepseek-chat"]

[limits]
max_tokens = 4096
temperature = 0.7
```

```python
# domain/preset_registry.py — AFTER (loader only)
import tomllib
from pathlib import Path
from reasoner.domain.preset_core import PipelinePreset

def _load_presets() -> dict[str, PipelinePreset]:
    config_dir = Path(__file__).parent.parent.parent / "config" / "presets"
    result = {}
    for f in config_dir.glob("*.toml"):
        with open(f, "rb") as fh:
            data = tomllib.load(fh)
        result[data["preset"]["name"]] = PipelinePreset(**data)
    return result

PRESETS = _load_presets()
```

**Acceptance criteria:**
- [ ] `domain/preset_registry.py` ≤ 80 lines
- [ ] All 42 presets load correctly from config files
- [ ] `python main.py --list-presets` shows all presets
- [ ] Adding a new preset requires only a new `.toml` file, no Python changes

---

### 5-B: `application/services/serializers.py` → named serializers (1,075 lines)

**Problem:** `_ser_0` through `_ser_5` are function names that encode phase number as identifier. This means adding a phase or modifying serialization output requires reading 1,075 lines to find the right `_ser_N` function.

**Fix:** Split into per-method serializer modules inside `application/serializers/`:

```
application/serializers/
├── __init__.py         (registry: phase_num → serializer)
├── classification.py   (_ser_0 equivalent)
├── decomposition.py    (_ser_1 equivalent)
├── perspectives.py     (_ser_2 equivalent)
├── critique.py         (_ser_3 equivalent)
├── stress_test.py      (_ser_4 equivalent)
├── synthesis.py        (_ser_5 + _ser_synthesis equivalent)
├── writing.py          (_ser_writing_* equivalents)
└── base.py             (_get_v, _is_* helpers)
```

Each file is ≤ 150 lines. The registry in `__init__.py` maps phase identifiers to the correct serializer.

**Acceptance criteria:**
- [ ] `application/services/serializers.py` deleted or replaced by redirect shim
- [ ] Each file in `application/serializers/` ≤ 150 lines
- [ ] SSE output unchanged — `test_sse_events.py` passes

---

## Sprint 6 — Rate limiter production hardening (< 1 day)  `[OPEN from prior plan]`

---

### 6-A: Enforce Redis rate limiter in multi-worker deployments

**File:** `src/reasoner/core/settings.py`
**Evidence:** `RATE_LIMITER_MODE` present with no production default enforcement

**Problem:** In-memory rate limiter is per-process. Multi-worker uvicorn (common in production) means rate limiting is effectively per-worker, allowing clients to exceed limits by spreading requests.

**Fix:**

**Step 1** — add `is_multi_worker` property to `Settings`:
```python
@property
def is_multi_worker(self) -> bool:
    import os
    return int(os.getenv("WEB_CONCURRENCY", "1")) > 1
```

**Step 2** — add startup assertion in `api/lifespan.py` (or `api/__init__.py` startup block):
```python
if settings.is_multi_worker and settings.RATE_LIMITER_MODE.lower() != "redis":
    raise RuntimeError(
        "RATE_LIMITER_MODE must be 'redis' when WEB_CONCURRENCY > 1. "
        "Set RATE_LIMITER_MODE=redis in your environment."
    )
```

**Step 3** — update `.env.example`:
```bash
# Required in production multi-worker deployments
RATE_LIMITER_MODE=redis
WEB_CONCURRENCY=4
```

**Acceptance criteria:**
- [ ] Starting with `WEB_CONCURRENCY=4` and `RATE_LIMITER_MODE=memory` raises `RuntimeError` at startup
- [ ] `RATE_LIMITER_MODE=redis` documented as production default in `.env.example`
- [ ] `test_rate_limiter_concurrency.py` passes

---

## Sprint 7 — CQRS completion and event sourcing integrity (2 days)  `[OPEN from prior plan]`

---

### 7-A: Event store wired for all pipeline executions

**Current state:** Events are published to the in-memory bus but the `EventStore` is not consistently subscribed across all execution paths.

**Fix:** In `RunPipelineCommandHandler.handle()` (after Sprint 3-B), subscribe the event store to all phase events for the duration of the run:

```python
async def handle(self, command: RunPipelineCommand) -> PipelineState:
    async def _persist(event: DomainEvent) -> None:
        await self.event_store.save_events([event])

    unsub = await bus.subscribe(EventType.PHASE_COMPLETED, _persist)
    try:
        state = await self._orchestrator.execute(decision)
    finally:
        unsub()
    return state
```

**Acceptance criteria:**
- [ ] Every pipeline execution produces a complete event sequence in the event store
- [ ] `test_event_persistence_completeness.py` covers all `EventType` variants

---

### 7-B: `PipelineAggregate` replay covers all event types

**File:** `src/reasoner/core/aggregates/pipeline.py`

Extend `PipelineAggregate.apply()` to cover every `EventType` emitted during a pipeline run. This enables `--resume` from event log rather than state snapshot JSON.

**Acceptance criteria:**
- [ ] `test_aggregates.py` covers all `EventType` variants with round-trip fidelity
- [ ] `python main.py --resume <run_id>` reconstructs state from event log without a snapshot file

---

## Score projection per sprint

| Sprint | CRITICAL fixed | HIGH fixed | MEDIUM fixed | Projected score |
|--------|---------------|-----------|-------------|----------------|
| Baseline (today) | — | — | — | **5 / 10** |
| After Sprint 0 | 0 | +1 (blocking) | — | 5.5 |
| After Sprint 1 | +1 (__root__) | — | — | **6.5** |
| After Sprint 2 | — | +2 (billing, executor) | — | 7 |
| After Sprint 3 | — | +1 (dual path) | — | 7.5 |
| After Sprint 4 | — | +1 (PipelineState) | — | 8 |
| After Sprint 5 | — | — | +2 (registry, serializers) | 8.5 |
| After Sprint 6 | — | — | +1 (rate limiter) | 8.5 |
| After Sprint 7 | — | — | +1 (CQRS) | **9+ / 10** |

Residual −1: temporal coupling in `pipeline.run()` (implicit phase ordering is inherent to pipeline architectures; a full DAG scheduler would require a separate product-level decision) and mutable `PipelineState` (freezing it requires pervasive refactoring across 20+ strategy files with unclear payoff at current scale).

---

## Implementation order (dependency-aware)

```
Sprint 0-A  asyncio.run() fix              ← no dependencies
Sprint 0-B  fitz.open() async fix          ← no dependencies
      ↓
Sprint 1-A  __root__ migration             ← do in dependency order within sprint
Sprint 1-B  delete dead files              ← no dependencies
      ↓
Sprint 2-A  core/search.py injection       ← needs Sprint 1 (parsing moved to core/)
Sprint 2-B  billing/webhooks event-driven  ← needs Sprint 1 (event_bus accessible)
Sprint 2-C  executor EventPublisher port   ← needs core/ports/ established
      ↓
Sprint 3-A  context.py → orchestrator      ← needs Sprint 2 (orchestrator clean)
Sprint 3-B  CommandHandler as entry point  ← needs Sprint 3-A
      ↓
Sprint 4-A  PipelineState serialization    ← needs Sprint 1 (state_serializer location clear)
Sprint 4-B  method-specific accessors      ← needs Sprint 4-A
      ↓
Sprint 5-A  preset_registry → TOML        ← no structural dependency (safe to parallelize)
Sprint 5-B  serializers → modules          ← needs Sprint 4-A (state shape settled)
      ↓
Sprint 6-A  Redis rate limiter enforcement ← needs Sprint 1 (rate_limiter.py in infra/)
      ↓
Sprint 7-A  event store wiring            ← needs Sprint 3-B (single command path)
Sprint 7-B  aggregate replay              ← needs Sprint 7-A
```

---

## Test obligations per sprint

Each sprint must leave the full test suite green before the next begins.

| Sprint | New tests required |
|--------|-------------------|
| 0-A | Assert no `asyncio.run()` in any async request path |
| 0-B | Assert PDF upload does not block concurrent requests |
| 1-A | Import from new paths; shim backward-compat; no `__root__` Python modules |
| 2-A | `DiscoveryClient` instantiable without infrastructure imports |
| 2-B | Subscription activates after webhook event (event-driven integration test) |
| 2-C | `LLMExecutor` unit-testable without application imports |
| 3-A | Context endpoint enforces quota and writes history |
| 3-B | Single execution path test (all routes converge on `RunPipelineCommandHandler`) |
| 4-A | `PipelineState` serialization round-trip; `domain/pipeline_state.py` ≤ 600 lines |
| 5-A | All 42 presets load from TOML; `--list-presets` output unchanged |
| 5-B | SSE output unchanged; serializer files each ≤ 150 lines |
| 6-A | Multi-worker startup with memory limiter raises `RuntimeError` |
| 7-A | Complete event sequence persisted per pipeline run |
| 7-B | `--resume` from event log (no snapshot file) reconstructs state |

---

## Estimated effort

| Sprint | Description | Effort |
|--------|-------------|--------|
| 0 | 2 async patches | 2–4 hours |
| 1 | __root__ migration (30 modules) | 2–3 days |
| 2 | 3 layer violations | 1 day |
| 3 | Execution path consolidation | 2 days |
| 4 | PipelineState decomposition | 2–3 days |
| 5 | Config + serializer extraction | 1 day |
| 6 | Rate limiter enforcement | 2–4 hours |
| 7 | CQRS + event sourcing | 2 days |
| **Total** | | **10–13 engineer-days** |

Sprint 0 is prerequisite to any multi-worker production deployment. Sprint 1 is the highest-leverage single change — it removes the structural ambiguity that prevents all other boundaries from being enforced. Sprints 2–3 eliminate remaining coupling violations. Sprints 4–7 raise internal cohesion and operational robustness to production standard.
