# REASONER v3.0 — Architecture Excellence Refactoring Plan

**Target**: Raise Overall Architecture Score from 5.8 → 9.0 / 10  
**Baseline**: [Architecture Audit 2026-06-02](./architecture-audit-2026-06-02.md)  
**Estimated total effort**: 8–10 engineer-weeks across 4 phases  
**Risk level**: Moderate — the system works today; changes are structural, not behavioral

---

## Table of Contents

1. [Target State: What 9/10 Looks Like](#1-target-state-what-910-looks-like)
2. [Gap Analysis: Score-by-Score Delta](#2-gap-analysis-score-by-score-delta)
3. [Phase 1: Foundation (Week 1–2) — Score 5.8 → 7.0](#3-phase-1-foundation-week-12)
4. [Phase 2: Structural Realignment (Week 3–4) — Score 7.0 → 8.0](#4-phase-2-structural-realignment-week-34)
5. [Phase 3: Deep Integration (Week 5–6) — Score 8.0 → 8.7](#5-phase-3-deep-integration-week-56)
6. [Phase 4: Excellence & Hardening (Week 7–10) — Score 8.7 → 9.0](#6-phase-4-excellence--hardening-week-710)
7. [Migration Sequencing & Risk Matrix](#7-migration-sequencing--risk-matrix)
8. [Verification Gates Per Phase](#8-verification-gates-per-phase)
9. [Rollback Plan](#9-rollback-plan)
10. [Scorecard — Before & After](#10-scorecard--before--after)

---

## 1. Target State: What 9/10 Looks Like

A 9/10 architecture is not "perfect" — it's *provably correct* in its core patterns, with every module importable in isolation, every boundary enforced by static analysis, and nothing left to "aspirational documentation."

| Dimension | 5.8 (Today) | 9.0 (Target) |
|-----------|-------------|--------------|
| **Layered Architecture** | API leaks into infrastructure; core reads env | All imports follow `api → application → domain → core`. Zero infrastructure imports from core/domain. Settings is the SINGLE env reader. |
| **CQRS / Event Sourcing** | Dual-state split; handlers unused | PipelineAggregate is canonical state. All mutations go through commands→events→aggregate. EventStore is the persistence backbone. PipelineState is a read-model projection. |
| **Hexagonal / Ports** | Good LLM port; streaming bypasses services | Every external boundary has a port interface. DI container wires adapters. No `import infrastructure` from application/ or api/ (only through ports). |
| **Composition** | 20 strategies in factory; phase loop duplicated | PhaseExecutor is a single service used by CLI, SSE, and tests. Pre/post phases are composable middleware. Every phase has consistent lifecycle hooks. |
| **Infrastructure Quality** | ProviderRouter excellent; 15+ env bypasses | Zero `os.environ` outside settings.py. Multi-provider implementations with shared contract tests. Connection pools with health checks and graceful degradation. |
| **API Design** | 1067-line init; 1133-line streaming | Every endpoint in its own route file. `__init__.py` < 150 lines. `streaming.py` < 350 lines (pure SSE I/O adapter). Controllers < 30 lines. |
| **Testing** | Solid pytest config; aspirational CI | 80%+ line coverage. Architectural fitness functions (dependency rule enforced in CI). Integration tests for event sourcing replay, LLM fallback chain, phase execution. Provider contract tests. |
| **Observability** | Prometheus + Sentry + Langfuse subscriber | OpenTelemetry spans across every async boundary. Structured JSON logging with correlation IDs. Pre-built Grafana dashboard. SLO-defined alerts (p95 latency, error rate). |
| **Security** | Auth/CSRF/rate-limit present but scattered | Threat model documented. All security concerns centralized in `security/` module. Dependency scanning in CI. Auth scopes verified by middleware, not per-endpoint. |
| **Dependency Health** | models.py 1648 lines, 105 importers | models.py < 500 lines. No file imported by > 40 files. Shared kernel explicit (`reasoner.shared`) with version. Import-lint gate in CI. |

---

## 2. Gap Analysis: Score-by-Score Delta

### Layered Architecture: 5 → 9 (+4)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| `api/streaming.py` imports infrastructure directly | Streaming contains orchestration that belongs in application/ | Extract `PipelineOrchestrator` into application/; streaming becomes pure SSE adapter |
| `core/search.py` reads `os.environ` | Search module was written before Settings singleton existed | Route through `settings.SEARXNG_URL` |
| 15+ files bypass `settings.py` | Historical accretion; no lint rule enforcing it | Add all missing env vars to Settings; add import-lint rule |
| `application/flows/base.py` imports `ProviderRouter` | WorkflowServices protocol couples to infrastructure type | Create `LLMPort` protocol in core/; ProviderRouter implements it |
| `api/__init__.py` contains endpoints | Endpoints accreted in init instead of routes/ | Move each endpoint to its own route file |

### CQRS / Event Sourcing: 4 → 9 (+5)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| PipelineState and PipelineAggregate coexist | Handlers were built aspirational but never wired | Make PipelineAggregate the canonical state; PipelineState becomes a read projection |
| Commands/queries never instantiated | CQRS scaffolding built before pipeline was ready | Wire `RunPipelineCommand` → `RunPipelineCommandHandler` → `ReasonerPipeline` |
| EventStore not called from pipeline.py | Pipeline.py predates event sourcing infrastructure | Have pipeline publish events; EventStore subscribers persist them |
| Event bus used for logging only, not domain state | Events are side-channel observability, not source of truth | Subscribe domain handlers (state projection, neuro learn, history) to events |

### Hexagonal / Ports: 6 → 9 (+3)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| No DI container | FastAPI Depends() is used but singletons are global | Create a proper DI container or use FastAPI's dependency system consistently |
| WorkflowServices protocol uses concrete infrastructure type | Protocol was pragmatic but leaks the abstraction | Define `LLMPort` in core/ports/ |
| Global singletons everywhere | Convenience pattern, not architectural | Replace with DI; keep lazy init but inject via constructor |

### Composition: 7 → 9 (+2)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| Phase execution duplicated in streaming.py | `WorkflowRunner.run_phase()` exists but streaming.py has its own loop | Have streaming.py delegate to WorkflowRunner |
| Pre/post phases hardcoded in pipeline.py | `run()` has fixed sequence: enhance→fusion→strategy→post-verify | Make pre/post phases a composable middleware chain on the strategy |
| Phase lifecycle inconsistent | Some phases have retry; some don't; some have quality; some don't | Standardize via PhaseStep with mandatory lifecycle hooks |

### Infrastructure Quality: 7 → 9 (+2)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| 15+ env bypasses | No lint rule; accretion | Add all vars to Settings; add CI check |
| OpenAiCompatibleProvider is the only concrete adapter | Pragmatic; other providers go through OpenRouter | Add at least one direct provider (Anthropic) with shared contract tests |
| `_run_state_manager` global | Convenience | Inject via constructor or DI |

### API Design: 5 → 9 (+4)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| `__init__.py` 1067 lines | Endpoints added inline over time | Move each endpoint to routes/; keep only app factory in init |
| `streaming.py` 1133 lines | Orchestration mixed with SSE I/O | Extract PipelineOrchestrator; streaming becomes < 350 lines |
| Controllers contain business logic | FastAPI route handlers call pipeline directly | Thin controllers that delegate to application services |

### Testing: 5 → 9 (+4)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| Coverage below 70% | Unknown exact figure; CI gate is 60% | Achieve 80%+ via targeted test writing |
| No architectural fitness functions | No tooling to enforce dependency rules | Add `pytest-archunit` or custom import-lint test |
| No contract tests for providers | Only OpenAiCompatibleProvider exists | Add contract test base class; each provider implements it |
| No integration tests for event sourcing | Event store exists but untested at integration level | Add event sourcing replay tests; snapshot tests |

### Observability: 5 → 9 (+4)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| No distributed tracing | Ad-hoc log-based phase tracking | Add OpenTelemetry with auto-instrumentation + manual spans |
| Logging is `logger.info()` not structured | Standard Python logging, not JSON | Add `structlog` or JSON formatter; correlation IDs on all logs |
| No SLO/SLI definitions | No formal reliability targets | Define SLOs: p95 latency < 30s, error rate < 1%, availability > 99.5% |
| Langfuse subscriber untested in CI | Subscriber exists but not verified | Add integration test with Langfuse mock |

### Security: 6 → 9 (+3)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| No threat model | Security is reactive, not designed | Document threat model (STRIDE); add to docs/ |
| Auth checks scattered across endpoints | Some endpoints call `_require_auth_if_legacy_disabled`; some don't | Centralize in middleware or a single dependency |
| No dependency scanning | requirements.txt has no vuln scanning | Add `pip-audit` or `safety` to CI |
| CSRF secret read directly from env | `api/csrf.py` reads `os.environ["CSRF_SECRET"]` | Route through settings |

### Dependency Health: 5 → 9 (+4)

| Gap | Root Cause | Fix |
|-----|-----------|-----|
| models.py 1648 lines, 105 importers | Accumulated types, serialization, migration code | Split into domain/pipeline_state.py, domain/types.py, domain/serialization.py |
| core/constants.py mixed concerns | System prompts + limits + model aliases + image gen config | Split into core/constants_limits.py, core/constants_prompts.py, core/constants_models.py |
| No import-lint in CI | No tooling | Add import-lint or custom pytest that verifies layer rules |

---

## 3. Phase 1: Foundation (Week 1–2) — Score 5.8 → 7.0

**Goal**: Fix the documentation, consolidate configuration, extract the God Functions. Zero behavioral changes.

### Step 1.1 — Update AGENTS.md (30 min)

**File**: `AGENTS.md`

Changes:
- Remove "14 mixins" claim; replace with "20 WorkflowStrategy implementations in `application/flows/`"
- Update CQRS section from "Separate command and query handlers" to "Commands and queries defined as message types in `application/commands/` and `application/queries/`; CQRS handlers in `application/handlers/` are wired for the v3 migration"
- Update Event Sourcing section from "Pipeline state derived from domain events" to "Domain events and EventBus are operational for observability; full event-sourced state management targeted for v3.0"
- Remove `application/mixins/` from directory listing
- Add `application/flows/` directory with its 31-file structure

**Verification**: `grep_files` for "mixins" in AGENTS.md returns zero matches.

### Step 1.2 — Consolidate Environment Reading (2 hrs)

**Objective**: All `os.environ`/`os.getenv` calls route through `core/settings.py`.

**Files to change**:

| File | Current | Change |
|------|---------|--------|
| `core/settings.py` | Missing several env vars | Add properties: `APP_URL`, `ENVIRONMENT`, `UVICORN_WORKERS`, `METRICS_ALLOWED_IPS`, `CSRF_SECRET` (already exists as `CSRF_SECRET`), `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `SENTRY_DSN`, `STRIPE_SECRET_KEY`, `ENABLE_LEGACY_API_KEY`, `DB_POOL_SIZE` |
| `core/search.py` | `os.environ.get("SEARXNG_URL")` | Replace with `settings.SEARXNG_URL` |
| `api/__init__.py` | 10+ `os.environ` calls | Replace all with `settings.*` |
| `api/billing_router.py` | `os.environ.get("APP_URL")` | Replace with `settings.APP_URL` |
| `api/csrf.py` | `os.environ.get("CSRF_SECRET")` | Replace with `settings.CSRF_SECRET` |
| `api/dependencies.py` | `os.environ.get("ENVIRONMENT")`, `os.environ.get("DB_POOL_SIZE")` | Replace with `settings.*` |
| `api/sentry.py` | `os.environ.get("SENTRY_DSN")`, `os.environ.get("ENVIRONMENT")` | Replace with `settings.*` |
| `auth.py` | `os.environ.get("ADMIN_API_KEY")` | Replace with `settings.ADMIN_API_KEY` |
| `application/event_bus/bus.py` | `os.environ.get("LANGFUSE_PUBLIC_KEY")` etc. | Replace with `settings.*` |
| `application/flows/search_phases.py` | `os.getenv("REASONER_DEEP_READ_LLM")` | Replace with `settings.REASONER_DEEP_READ_LLM` |

**Verification**: `grep_files` for `os\.environ|os\.getenv` outside `core/settings.py` returns zero matches in `src/reasoner/`.

### Step 1.3 — Extract `api/__init__.py` Endpoints into Routes (3 hrs)

**Objective**: `api/__init__.py` drops from 1067 → ~200 lines. Each endpoint gets its own file.

**New files**:

| New File | Content from `__init__.py` |
|----------|---------------------------|
| `api/routes/health.py` | `GET /api/health` endpoint (~120 lines) |
| `api/routes/feedback.py` | `POST /api/feedback`, `GET /api/admin/feedback-stats` |
| `api/routes/errors.py` | `POST /api/error-report`, `GET /api/admin/errors` |
| `api/routes/estimate.py` | `POST /api/estimate` |
| `api/routes/csrf_token.py` | `POST /api/csrf` (already partially in csrf.py; consolidate) |

**`api/__init__.py` after refactor**:
```python
"""FastAPI application factory."""
from fastapi import FastAPI
from contextlib import asynccontextmanager

def create_app() -> FastAPI:
    app = FastAPI(title="Reasoner v3.0", lifespan=lifespan)
    register_middleware(app)
    register_routes(app)
    return app

# Keep: lifespan, CORS setup, middleware registration, Sentry init
# Move: ALL endpoint definitions to routes/
```

**Verification**: `api/__init__.py` < 250 lines. `grep_files "@app\.(get|post|delete|put)" api/__init__.py` returns only root `/` endpoint or zero.

### Step 1.4 — Create `LLMPort` Protocol in core/ (1 hr)

**Objective**: Decouple `application/flows/base.py` from `infrastructure/llm/router.py`.

**New file**: `core/ports/llm_port.py`
```python
"""Port interface for LLM access — implementable by any provider router."""
from __future__ import annotations
from typing import Protocol, runtime_checkable, Any

@runtime_checkable
class LLMPort(Protocol):
    """Port for LLM communication. ProviderRouter implements this."""
    
    async def call(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = ...,
        temperature: float = ...,
        timeout_seconds: float | None = ...,
    ) -> tuple[str, dict[str, Any]]: ...
    
    def get(self, role: str) -> Any: ...
```

**File change**: `application/flows/base.py`
```python
# Before:
from reasoner.infrastructure.llm.router import ProviderRouter

# After:
from reasoner.core.ports.llm_port import LLMPort
```

**Verification**: `grep_files "from reasoner.infrastructure" application/flows/base.py` returns zero matches.

### Step 1.5 — Add CI Import-Lint Gate (1 hr)

**Objective**: Prevent future layer violations from merging.

**New file**: `tests/architecture/test_layer_boundaries.py`
```python
"""Architectural fitness functions — enforce dependency direction."""
import ast
import pytest
from pathlib import Path

FORBIDDEN_IMPORTS = {
    "core": ["reasoner.infrastructure", "reasoner.api", "reasoner.application"],
    "domain": ["reasoner.infrastructure", "reasoner.api"],
    "application": ["reasoner.api"],  # application can import infrastructure via ports
}

def get_imports(file_path: Path) -> list[str]:
    """Extract all 'from reasoner.X import' statements from a Python file."""
    tree = ast.parse(file_path.read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports

@pytest.mark.parametrize("layer,forbidden", FORBIDDEN_IMPORTS.items())
def test_layer_boundaries(layer, forbidden):
    """Verify no file in {layer}/ imports from forbidden modules."""
    base = Path("src/reasoner") / layer
    violations = []
    for py_file in base.rglob("*.py"):
        for imp in get_imports(py_file):
            if any(imp.startswith(f) for f in forbidden):
                violations.append(f"{py_file.relative_to(base.parent)}: imports {imp}")
    assert not violations, f"Layer violations:\n" + "\n".join(violations)
```

**Verification**: This test passes in CI.

---

## 4. Phase 2: Structural Realignment (Week 3–4) — Score 7.0 → 8.0

**Goal**: Decompose the monolith files, unify the dual state, wire the existing WorkflowRunner.

### Step 2.1 — Decompose `models.py` (1.5 days)

**Objective**: Reduce from 1648 lines to < 500 lines. Split into domain sub-modules.

**New files**:

| New File | Content | ~Lines |
|----------|---------|--------|
| `domain/pipeline_state.py` | `PipelineState` + `PipelineCore` + `PipelineMeta` + `PipelineRemainder` + `MethodState` + `CostTrackingState` + `ConversationState` + property aliases | ~500 |
| `domain/orchestration_types.py` | `GenerationCandidate`, `CriticScore`, `CriticDimensionScore`, `VerificationResult`, `MetaEvaluation` | ~150 |
| `domain/core_types.py` | `SolutionCandidate`, `CritiqueScore`, `StressTestResult`, `FinalSolution`, `MetaCognitiveAudit`, `Decomposition`, `SubProblem`, `Assumption` | ~300 |
| `domain/enums.py` | `ScenarioType`, `TaskType` (move from `domain/models.py`), `ClaimLabel`, `PerspectiveType` | ~100 |
| `models.py` (remaining) | Re-exports from domain/ sub-modules for backward compatibility; `PipelineState.save()`, `.load()`, `._from_dict()` | ~250 |

**Migration strategy**:
1. Create new files with the extracted types
2. Add re-exports in models.py: `from reasoner.domain.pipeline_state import PipelineState`
3. Phase 2 only: keep models.py as compatibility shim
4. Phase 3: update all 105 importers to use new paths

**Verification**: All existing tests pass. `models.py` < 500 lines.

### Step 2.2 — Unify State: Make PipelineAggregate Canonical (2 days)

**Objective**: Eliminate the dual-state split. PipelineAggregate becomes the single source of truth.

**Decision**: PipelineAggregate should be the canonical state because:
- It already has proper event sourcing infrastructure (events, apply(), replay)
- The EventStore already persists events
- PipelineState's property aliases (50+ of them) are backward-compat debt we want to shed

**Implementation plan**:

1. **Extend PipelineAggregate** to cover all fields currently in PipelineState:
   ```python
   class PipelineAggregate(Aggregate):
       # Add missing state: enhanced_problem, neuro_context, conversation_state, etc.
   ```

2. **Create a read-model projection** from PipelineAggregate:
   ```python
   class PipelineStateReadModel:
       """Read-optimized projection of PipelineAggregate for SSE serialization."""
       @classmethod
       def from_aggregate(cls, aggregate: PipelineAggregate) -> "PipelineStateReadModel":
           ...
   ```

3. **Update ReasonerPipeline.run()** to:
   - Accept a `PipelineAggregate` (or create one)
   - Record events through the aggregate (not mutate PipelineState directly)
   - Return a `PipelineStateReadModel` for backward-compatible serialization

4. **Wire event publishing**: Every phase mutation publishes a domain event through the EventBus.

5. **Deprecate PipelineState direct mutation**: Add `DeprecationWarning` when code mutates PipelineState directly.

**Files changed**:
- `core/aggregates/pipeline.py` — extend PipelineAggregate with missing fields
- `pipeline.py` — switch from PipelineState to PipelineAggregate
- `api/streaming.py` — use PipelineStateReadModel for SSE; route through PipelineAggregate via orchestrator
- `models.py` — mark PipelineState as deprecated, re-export from domain/pipeline_read_model.py

**Verification**:
- `grep_files "PipelineState\(" src/reasoner/` returns zero hits (all uses go through PipelineAggregate or factory)
- EventStore has entries for every phase in an integration test run
- Pipeline can be resumed from EventStore replay

### Step 2.3 — Wire streaming.py to WorkflowRunner (1.5 days)

**Objective**: Eliminate the duplicated phase execution loop. `streaming.py` delegates to `WorkflowRunner`.

**Current state**: Two phase execution loops exist:
1. `application/flows/runner.py:WorkflowRunner.run_phase()` — has retry, timeout, quality, event publishing
2. `api/streaming.py:run_stream()` — has its own ad-hoc loop with retry, timeout, quality, SSE yield, keepalive

**Target**: `streaming.py` calls `WorkflowRunner.run_phase()` and wraps the result in SSE events.

**Implementation**:

1. **Extend WorkflowRunner** to support SSE streaming callbacks:
   ```python
   class WorkflowRunner:
       def __init__(self, services, monitor=None, sse_callback=None):
           self.sse_callback = sse_callback  # async callable: (event_dict) -> None
   ```

2. **Move phase lifecycle from streaming.py into WorkflowRunner**:
   - Phase start/fail/complete event emission
   - Keepalive during long phases (move to runner with configurable interval)
   - Quality check and retry logic (already in runner!)

3. **Extract `HyperGate` + preset resolution into `PipelineOrchestrator`**:
   - New service: `application/orchestrator.py`
   - Handles: HyperGate decision, preset resolution, router construction, neuro recall
   - `streaming.py` calls orchestrator → gets back a configured pipeline + strategy → passes to WorkflowRunner

**`api/streaming.py` after refactor** (target: < 350 lines):
```python
async def run_stream(req: RunRequest, ...) -> AsyncGenerator[str, None]:
    orchestrator = PipelineOrchestrator(preset_service, pipeline_service)
    
    # Phase 1: Pre-flight (HyperGate, preset, neuro recall)
    decision = await orchestrator.preflight(req)
    if decision.action == "direct":
        async for chunk in orchestrator.stream_direct_answer(decision):
            yield _sse(chunk)
        return
    
    # Phase 2: Execute
    runner = WorkflowRunner(services, sse_callback=lambda ev: yield _sse(ev))
    state = await runner.run(strategy, initial_state)
    
    # Phase 3: Post-flight (neuro learn, history save)
    await orchestrator.postflight(state)
```

**Verification**: `api/streaming.py` < 400 lines. `grep_files "async def.*phase" api/streaming.py` returns zero (no phase execution logic remains in SSE layer).

### Step 2.4 — Split core/constants.py (0.5 day)

**Objective**: Separate concerns — limits vs prompts vs model aliases.

**New files**:

| New File | Content |
|----------|---------|
| `core/constants_limits.py` | Timeouts, TruncationLimits, token budgets, retry budgets, phase timeouts, defaults |
| `core/constants_prompts.py` | GATE_SYSTEM_PROMPT, ANALYTICAL_SYSTEM_PROMPT, CREATIVE_SYSTEM_PROMPT, image gen prompts |
| `core/constants_models.py` | MODEL_* aliases, IMAGE_GEN_* config, model-related constants |

**`core/constants.py`** becomes a re-export compatibility shim:
```python
from reasoner.core.constants_limits import *
from reasoner.core.constants_prompts import *
from reasoner.core.constants_models import *
```

**Verification**: All existing tests pass (imports still resolve via `constants.py`).

---

## 5. Phase 3: Deep Integration (Week 5–6) — Score 8.0 → 8.7

**Goal**: Wire CQRS handlers, complete event sourcing, add proper DI, update all 105 importers.

### Step 3.1 — Wire CQRS Handlers into Pipeline (2 days)

**Objective**: The pipeline actually goes through CQRS handlers instead of calling `ReasonerPipeline.run()` directly.

**Implementation**:

1. **Create `PipelineOrchestrator`** (if not done in Phase 2):
   ```python
   class PipelineOrchestrator:
       async def execute(self, command: RunPipelineCommand) -> PipelineStateReadModel:
           handler = RunPipelineCommandHandler(event_bus, event_store)
           aggregate = await handler.handle(command)
           read_model = PipelineStateReadModel.from_aggregate(aggregate)
           return read_model
   ```

2. **Update API endpoints** to use orchestrator:
   ```python
   # Before:
   pipeline = pipeline_service.create_pipeline(router=router, ...)
   state = await pipeline.run(problem, method)
   
   # After:
   command = RunPipelineCommand(problem=req.problem, preset=req.preset, ...)
   state = await orchestrator.execute(command)
   ```

3. **Update CLI** (`main.py`) to use same path.

**Verification**: 
- `grep_files "ReasonerPipeline\(.*\)" src/reasoner/api/` returns zero (API doesn't instantiate pipeline directly)
- `grep_files "RunPipelineCommand" src/reasoner/api/streaming.py` returns a match (orchestrator creates command)

### Step 3.2 — Complete Event Sourcing (2 days)

**Objective**: Every state transition goes through events. EventStore is the persistence backbone.

**Implementation**:

1. **Add missing event types** for all state transitions:
   - `PromptEnhanced` (when prompt enhancement succeeds)
   - `NeuroContextRecalled` (already exists as MemoryRecalled)
   - `WebDiscoveryCompleted`
   - `ContextVettingCompleted`

2. **Update PipelineAggregate._apply_event()** to handle all event types

3. **Create event-sourced subscribers** (move logic from streaming.py into event handlers):
   - `NeuroLearnHandler`: subscribes to `PipelineCompleted` → persists to Neuro
   - `HistorySaveHandler`: subscribes to `PipelineCompleted` → saves history entry
   - `StateProjectionHandler`: subscribes to all pipeline events → updates PipelineStateReadModel

4. **Remove direct mutation of PipelineState** everywhere.

**Verification**:
- Integration test: run pipeline → replay from EventStore → assert identical state
- `grep_files "state\.\w+\s*=" src/reasoner/pipeline.py` returns zero or only through aggregate.record_event()

### Step 3.3 — Proper Dependency Injection (1.5 days)

**Objective**: Replace global singletons with constructor injection.

**Implementation**:

1. **Create `Container` class** using FastAPI's dependency system or a lightweight container:
   ```python
   class Container:
       """Application composition root."""
       def __init__(self, settings: Settings):
           self.settings = settings
           self._event_bus: EventBus | None = None
           self._event_store: EventStore | None = None
       
       @property
       def event_bus(self) -> EventBus:
           if self._event_bus is None:
               self._event_bus = EventBus()
           return self._event_bus
       
       @property
       def event_store(self) -> EventStore:
           if self._event_store is None:
               self._event_store = EventStore()
           return self._event_store
   ```

2. **Replace global access**:
   - `get_event_bus()` → `container.event_bus`
   - `get_event_store()` → `container.event_store`
   - `_run_state_manager` → `container.run_state_manager`

3. **Wire in FastAPI lifespan**:
   ```python
   async def lifespan(app: FastAPI):
       container = Container(settings)
       app.state.container = container
       # ... startup
       yield
       # ... shutdown
   ```

**Verification**: No module-level global singletons accessed outside of `Container`. All tests can create isolated containers.

### Step 3.4 — Update All Importers to New Domain Paths (1 day)

**Objective**: 105 files that import from `reasoner.models` migrate to new domain sub-modules.

**Scripted migration**:
```python
# Migration map
MIGRATIONS = {
    "from reasoner.models import PipelineState": "from reasoner.domain.pipeline_state import PipelineState",
    "from reasoner.models import SolutionCandidate": "from reasoner.domain.core_types import SolutionCandidate",
    "from reasoner.models import TaskType": "from reasoner.domain.enums import TaskType",
    # ... etc for all types
}
```

**Verification**: `grep_files "from reasoner.models import" src/reasoner/` returns zero matches (only backward-compat re-exports in models.py itself remain).

---

## 6. Phase 4: Excellence & Hardening (Week 7–10) — Score 8.7 → 9.0

**Goal**: Testing coverage, observability, security hardening, scalability foundations.

### Step 4.1 — Achieve 80%+ Test Coverage (2 weeks)

**Strategy**: Target the lowest-coverage, highest-risk areas first.

1. **Event sourcing tests** (highest priority):
   - `tests/test_event_sourcing.py`: Full pipeline run → event replay → state equality
   - `tests/test_event_store.py`: Concurrent writes, snapshot creation, aggregate reconstruction
   - `tests/test_aggregate.py`: PipelineAggregate.apply() for every event type

2. **Provider contract tests**:
   - `tests/contracts/test_llm_provider.py`: Abstract test class
   - Each provider extends it: `TestOpenAiCompatibleProvider(BaseProviderContract)`

3. **Integration tests**:
   - `tests/integration/test_pipeline_e2e.py`: Mock LLM responses, verify full phase sequence
   - `tests/integration/test_fallback_chain.py`: Verify ProviderRouter fallback when primary fails
   - `tests/integration/test_cancellation.py`: Verify cancel_event stops pipeline mid-phase

4. **Architecture fitness functions** (from Phase 1, Step 1.5): Extend with more rules.

**Verification**: `coverage report` shows > 80% line coverage. CI gate changed from 60% fail to 80% fail.

### Step 4.2 — OpenTelemetry Tracing (3 days)

**Implementation**:

1. **Install**: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-exporter-otlp`

2. **Add manual spans** at key boundaries:
   - `PipelineOrchestrator.execute()` → span "pipeline.run"
   - Each phase execution → span "phase.{name}"
   - Each LLM call → span "llm.call" with attributes (model, role, tokens)
   - Each Neuro recall/learn → span "neuro.{operation}"
   - EventStore persistence → span "event_store.save"

3. **Correlation IDs**: Generate at pipeline start; propagate through all spans.

**Verification**: Traces visible in Jaeger (dev) or Grafana Tempo (prod). Every pipeline run produces a complete trace.

### Step 4.3 — Structured Logging (1 day)

**Implementation**:

1. **Add `structlog`**: Replace `logging.getLogger(__name__)` with structured loggers.
   ```python
   import structlog
   logger = structlog.get_logger()
   logger.info("phase_completed", phase=name, duration=duration, tokens=tokens)
   ```

2. **JSON formatter in production**: `structlog.dev.ConsoleRenderer` in dev; `structlog.processors.JSONRenderer` in prod.

**Verification**: All log output in production is valid JSON with `correlation_id`, `phase`, and `timestamp` fields.

### Step 4.4 — Security Hardening (2 days)

1. **Threat model document**: `docs/security/threat-model.md` (STRIDE methodology)
2. **Dependency scanning in CI**: Add `pip-audit` step that fails on HIGH/CRITICAL CVEs
3. **Centralize auth**: Single `require_auth` dependency; remove scattered `_require_auth_if_legacy_disabled` calls
4. **Add content security policy review**: Verify CSP header coverage

### Step 4.5 — Scalability Foundation (2 days)

1. **Redis-backed phase queue**: For multi-worker, phases can be dispatched to workers via Redis lists
2. **Document horizontal scaling path**: `docs/operations/scaling.md`
3. **Load test baseline**: `scripts/load_test.py` with locust or k6

### Step 4.6 — Provider Contract Tests + Second Provider (2 days)

1. **Add Anthropic direct provider**: `infrastructure/llm/providers/anthropic_direct.py`
2. **Shared contract test**: Both providers pass the same test suite
3. **Provider health check**: Each provider exposes health status

---

## 7. Migration Sequencing & Risk Matrix

```
Phase 1 (W1-2)     Phase 2 (W3-4)      Phase 3 (W5-6)      Phase 4 (W7-10)
─────────────────────────────────────────────────────────────────────────────
1.1 AGENTS.md ───┐
1.2 Env consol   │
1.3 Extract init  ├──► 2.1 Decomp models ──► 3.1 Wire CQRS ──► 4.1 80% coverage
1.4 LLMPort       │    2.2 Unify state         3.2 Event Sourcing  4.2 OTel tracing
1.5 Import-lint CI┘    2.3 Wire runner         3.3 DI Container    4.3 Struct logging
                        2.4 Split constants    3.4 Update importers 4.4 Security
                                                                    4.5 Scalability
                                                                    4.6 Provider tests
```

### Risk Matrix

| Step | Risk | Probability | Impact | Mitigation |
|------|------|-------------|--------|------------|
| 2.2 Unify state | State migration breaks serialization | Medium | High | Keep PipelineState as backward-compat read model; phased deprecation |
| 2.3 Wire runner | SSE keepalive behavior changes | Medium | Medium | Extract keepalive into runner with identical timing |
| 3.2 Event sourcing | Event replay produces different state | Low | High | Integration test comparing direct vs replayed state |
| 3.3 DI Container | Test isolation broken by shared container | Medium | Medium | Container is created per-test; reset helpers exist |
| 3.4 Update importers | 105 files touched; regression risk | Medium | Medium | Scripted migration; full test suite pass required |
| 4.2 OTel tracing | Performance overhead from tracing | Low | Medium | Sampling in production; span processor batching |

---

## 8. Verification Gates Per Phase

### Phase 1 Gate
- [ ] `grep_files "mixins" AGENTS.md` returns zero
- [ ] `grep_files "os\.environ\|os\.getenv" src/reasoner/` returns only `core/settings.py`
- [ ] `api/__init__.py` < 250 lines
- [ ] `grep_files "@app\.(get|post)" api/__init__.py` returns ≤ 1 (root endpoint only or zero)
- [ ] `grep_files "from reasoner.infrastructure" application/flows/base.py` returns zero
- [ ] `pytest tests/architecture/test_layer_boundaries.py` passes in CI
- [ ] All existing tests pass
- [ ] Pipeline runs end-to-end (manual smoke test)

### Phase 2 Gate
- [ ] `models.py` < 500 lines
- [ ] `api/streaming.py` < 400 lines
- [ ] `grep_files "PipelineState\(" src/reasoner/pipeline.py` returns zero
- [ ] EventStore has entries for pipeline integration test
- [ ] Pipeline can resume from EventStore replay
- [ ] `grep_files "async def.*phase" api/streaming.py` returns zero
- [ ] All existing tests pass

### Phase 3 Gate
- [ ] `grep_files "ReasonerPipeline\(.*\)" src/reasoner/api/` returns zero
- [ ] Integration test: run → replay from EventStore → assert identical read model
- [ ] `grep_files "get_event_bus\(\)" src/reasoner/api/` returns zero (all through DI)
- [ ] `grep_files "from reasoner.models import" src/reasoner/` returns zero (except models.py compat shim)
- [ ] All existing tests pass

### Phase 4 Gate
- [ ] Coverage > 80% (verified in CI)
- [ ] OTel traces visible in Jaeger/Grafana
- [ ] All logs are structured JSON in production mode
- [ ] `pip-audit` passes in CI
- [ ] Threat model exists in `docs/security/threat-model.md`
- [ ] Provider contract tests pass for both OpenAI and Anthropic
- [ ] Load test: 10 concurrent pipelines complete without errors

---

## 9. Rollback Plan

Each phase is independently revertible:

- **Phase 1**: Pure refactoring, no behavioral change. Revert by `git revert`.
- **Phase 2**: State unification is the riskiest change. Keep `PipelineState` as a backward-compat read model. If event sourcing causes issues, revert to PipelineState direct mutation while keeping the decomposed file structure.
- **Phase 3**: CQRS handler wiring can be toggled via feature flag (`USE_CQRS_HANDLERS` env var, default true). If handlers cause issues, set to false and pipeline falls back to direct `ReasonerPipeline.run()`.
- **Phase 4**: Additive only (tests, tracing, logging). No rollback needed — can be deployed incrementally.

---

## 10. Scorecard — Before & After

| Dimension | Before | After Phase 1 | After Phase 2 | After Phase 3 | After Phase 4 (Target) |
|-----------|--------|---------------|---------------|---------------|------------------------|
| Layered Architecture | 5 | 6 | 7 | 8 | **9** |
| CQRS / Event Sourcing | 4 | 4 | 6 | 8 | **9** |
| Hexagonal / Ports | 6 | 7 | 7 | 8 | **9** |
| Composition / Strategy | 7 | 7 | 8 | 9 | **9** |
| Infrastructure Quality | 7 | 8 | 8 | 8 | **9** |
| API Design | 5 | 7 | 8 | 9 | **9** |
| Testing Architecture | 5 | 6 | 6 | 7 | **9** |
| Observability | 5 | 5 | 5 | 6 | **9** |
| Security | 6 | 7 | 7 | 8 | **9** |
| Dependency Health | 5 | 6 | 7 | 8 | **9** |
| **Overall** | **5.8** | **6.3** | **6.9** | **7.9** | **9.0** |

### Score progression rationale

- **Phase 1 → 6.3**: Documentation fixed (+0.1 API design), env consolidated (+0.2 infra, +0.1 layered), init extracted (+0.2 API), LLMPort created (+0.1 hexagonal), import-lint added (+0.1 dependency). Weighted average: ~+0.5.
- **Phase 2 → 6.9**: models decomposed (+0.2 dependency), state unified (+0.2 CQRS, +0.1 layered), runner wired (+0.1 composition, +0.2 API), constants split (+0.1 dependency). Weighted average: ~+0.6.
- **Phase 3 → 7.9**: CQRS wired (+0.5 CQRS), event sourcing complete (+0.3 CQRS), DI container (+0.2 hexagonal, +0.1 layered), importers updated (+0.2 dependency). Weighted average: ~+1.0.
- **Phase 4 → 9.0**: Coverage 80%+ (+0.5 testing), OTel tracing (+0.5 observability), structured logging (+0.3 observability), security hardening (+0.3 security), scalability foundation (+0.2 infra), provider tests (+0.2 infra, +0.2 testing). Weighted average: ~+1.1.

---

*Plan authored 2026-06-02. To be reviewed and scheduled with engineering team.*
