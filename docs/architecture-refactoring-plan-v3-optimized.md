# REASONER v3.0 — Architecture Refactoring Plan (Optimized)

**Status**: Evaluated and optimized from the [v1 plan](./architecture-refactoring-plan-v3.md)  
**Target**: Raise Overall Architecture Score from 5.8 → 9.0 / 10  
**Estimated effort**: 6–8 engineer-weeks across 4 phases (down from 8–10)  
**Key optimization**: Removed forced CQRS indirection, simplified state unification, merged redundant steps, cut aspirational Phase 4 items

---

## Evaluation of the Original Plan

### What was correct

| Element | Assessment |
|---------|------------|
| Phased approach (Foundation → Structural → Deep → Excellence) | Correct sequencing |
| Phase 1 as low-risk, zero-behavioral-change foundation | Highest-leverage first step |
| Discovery that WorkflowRunner already exists and just needs wiring | Good leverage of existing code |
| Verification gates per phase as grep-able assertions | Concrete and CI-enforceable |
| Independent rollback per phase | Correct risk management |

### What needed optimization

| Issue | Severity | Fix |
|-------|----------|-----|
| **Forced CQRS handler indirection** — `RunPipelineCommandHandler` is a thin wrapper that internally creates `ReasonerPipeline` and calls `.run()`. Forcing every call through this path adds a layer with zero behavioral benefit in a single-process system. | HIGH | Keep CQRS handlers available for async/distributed use cases. PipelineOrchestrator calls ReasonerPipeline directly. Eliminate Step 3.1 as a mandatory step; make it optional/async-only. |
| **State unification overestimates 2-day effort** — PipelineState has 50+ property aliases, 300+ lines of backward-compat migration code in `__init__` and `_from_dict`, and complex `to_context_dict` serialization. Full replacement with PipelineAggregate in 2 days is unrealistic. | HIGH | Incremental approach: keep PipelineState canonical, add event emission to mutations. PipelineAggregate used for replay/resume only. This achieves auditability without full rewrite. |
| **DI Container duplicates FastAPI** — FastAPI already has `Depends()`, `app.state`, and lifespan. Adding a `Container` class creates two parallel DI mechanisms. | MEDIUM | Extend FastAPI's built-in DI. Add `get_event_bus`, `get_event_store` as FastAPI dependencies using `app.state`. Drop the Container class. |
| **Decomposition + import migration split across phases** — Step 2.1 decomposes models.py but keeps old imports; Step 3.4 updates importers. The intermediate state (decomposed files with old paths) causes confusion. | MEDIUM | Merge into one atomic step: decompose + update all importers in the same commit. |
| **Phase 4 is aspirational** — 2 weeks for 80% coverage + 3 days OTel + 1 day logging + 2 days security + 2 days scalability + 2 days provider tests = 4.5 weeks of work in a Phase budgeted at 3–4 weeks. | HIGH | Cut to essentials: testing coverage (highest leverage), structured logging (cheap, high observability gain), OTel (defer basic spans to a fast-follow). Defer Anthropic provider, Redis queue, load test to a separate v3.1 initiative. |
| **No frontend compatibility verification** — The SSE event structure consumed by `ui-next/` must remain identical across all refactoring. | MEDIUM | Add SSE snapshot tests to Phase 2 and 3 gates. |
| **No concrete migration automation** — "Scripted migration" for 105 files is mentioned but not specified. | MEDIUM | Provide an actual AST-based migration script using Python's `ast` module. |
| **No list of what NOT to change** — Risk of over-refactoring components that are already well-built. | LOW | Add "Preserved Components" section. |

---

## Optimized Plan

### Phase Structure

```
Phase 1 (W1-2):     Foundation — docs, env, init extraction, LLMPort, import-lint
                    Score: 5.8 → 6.8

Phase 2 (W3-4):     Structural — models decomposition + import migration (atomic),
                    wire streaming to WorkflowRunner, split constants,
                    fix throwaway PipelineState usage
                    Score: 6.8 → 7.5

Phase 3 (W5-6):     Event Sourcing Lite — add event emission to PipelineState,
                    PipelineAggregate for replay/resume, DI via FastAPI Depends(),
                    SSE snapshot tests
                    Score: 7.5 → 8.3

Phase 4 (W7-8):     Hardening — 80%+ test coverage, structured logging,
                    security consolidation, CI hardening
                    Score: 8.3 → 9.0
```

---

## Preserved Components (Do NOT Refactor)

These components are architecturally sound as-is. Changes would be cosmetic:

| Component | Why Preserve |
|-----------|-------------|
| `ProviderRouter` + circuit breaker + fallback chain | Well-architected; layered retry is production-grade |
| `EventBus` + dead-letter + backpressure | Fully implemented; used correctly for observability |
| `EventStore` + thread-pool isolation | Correct async patterns; proper snapshot support |
| `WorkflowFactory` + 20 strategies | Clean strategy pattern; no changes needed |
| `HyperGateAgent` + 6 sub-agents | Properly structured parallel agents; LRU caching |
| `PhaseMonitor` + quality judging | Well-integrated; correct tier-based thresholds |
| `core/protocol.py` (Phase, PhaseConfig, PhaseResult) | Clean frozen dataclasses; no changes needed |
| `exceptions.py` exception hierarchy | Proper taxonomy with retryable classification |
| `core/events/domain_events.py` event types | Well-designed frozen dataclasses; factory function |

---

## Phase 1: Foundation (Week 1–2) — Score 5.8 → 6.8

### Step 1.1 — Update AGENTS.md (30 min)

Same as original plan. Remove mixin references, update CQRS/ES claims to reflect current state.

### Step 1.2 — Consolidate Environment Reading (2 hrs)

Same as original plan. Route all `os.environ`/`os.getenv` through `core/settings.py`.

**Verification**: `grep -r "os\.environ\|os\.getenv" src/reasoner/ --include="*.py" | grep -v "core/settings.py"` returns zero.

### Step 1.3 — Extract `api/__init__.py` Endpoints (3 hrs)

Same as original plan. Target: `< 250 lines`.

### Step 1.4 — Create `LLMPort` Protocol + Clean Up `_universal.py` (1 hr)

**Part A**: Create `core/ports/llm_port.py` — same as original plan Step 1.4.

**Part B**: Fix throwaway `PipelineState` in `_universal.py` (NEW — discovered during evaluation):

```python
# Before (phases/_universal.py, lines 35, 40, 67):
lang_instruction = get_language_instruction(PipelineState(problem="", language=language))

# After: pass language directly, or create a lightweight context object
lang_instruction = get_language_instruction(language=language)
```

Also update `get_language_instruction` signature to accept `language: str` instead of `PipelineState`.

### Step 1.5 — Add CI Import-Lint Gate (1 hr)

Same as original plan. But with relaxed rule for `application/`:

```python
FORBIDDEN_IMPORTS = {
    "core": ["reasoner.infrastructure", "reasoner.api"],
    "domain": ["reasoner.infrastructure", "reasoner.api"],
    "application": ["reasoner.api"],
    # application CAN import infrastructure — that's the ports & adapters pattern
}
```

**Note**: The original plan had `"application": ["reasoner.api"]` which is correct. But it also had `"core": ["reasoner.application"]` removed — core importing from application would be an inward dependency violation and shouldn't happen anyway.

---

## Phase 2: Structural Realignment (Week 3–4) — Score 6.8 → 7.5

### Step 2.1 — Decompose models.py + Migrate All Importers (ATOMIC — 2 days)

**Key change from original**: Merge Steps 2.1 and 3.4 into one atomic operation. No intermediate state.

**Migration script** (`scripts/migrate_imports.py`):

```python
"""AST-based migration: update all importers of reasoner.models to new domain paths."""
import ast
import pathlib
import sys

BASE = pathlib.Path("src/reasoner")

# Mapping: old import path → new import path
TYPE_MIGRATIONS = {
    "PipelineState": "reasoner.domain.pipeline_state",
    "PipelineCore": "reasoner.domain.pipeline_state",
    "PipelineMeta": "reasoner.domain.pipeline_state",
    "PipelineRemainder": "reasoner.domain.pipeline_state",
    "MethodState": "reasoner.domain.pipeline_state",
    "CostTrackingState": "reasoner.domain.pipeline_state",
    "ConversationState": "reasoner.domain.pipeline_state",
    "SolutionCandidate": "reasoner.domain.core_types",
    "CritiqueScore": "reasoner.domain.core_types",
    "StressTestResult": "reasoner.domain.core_types",
    "FinalSolution": "reasoner.domain.core_types",
    "MetaCognitiveAudit": "reasoner.domain.core_types",
    "Decomposition": "reasoner.domain.core_types",
    "SubProblem": "reasoner.domain.core_types",
    "Assumption": "reasoner.domain.core_types",
    "GenerationCandidate": "reasoner.domain.orchestration_types",
    "CriticScore": "reasoner.domain.orchestration_types",
    "CriticDimensionScore": "reasoner.domain.orchestration_types",
    "VerificationResult": "reasoner.domain.orchestration_types",
    "MetaEvaluation": "reasoner.domain.orchestration_types",
    "TaskType": "reasoner.domain.enums",
    "ScenarioType": "reasoner.domain.enums",
    "ClaimLabel": "reasoner.domain.enums",
    "PerspectiveType": "reasoner.domain.enums",
    "PerspectiveRegistry": "reasoner.domain.enums",
}

class ImportMigrator(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        if node.module == "reasoner.models":
            # Group names by their new module
            groups: dict[str, list[ast.alias]] = {}
            for alias in node.names:
                new_module = TYPE_MIGRATIONS.get(alias.name)
                if new_module:
                    groups.setdefault(new_module, []).append(alias)
                else:
                    # Keep in models.py (e.g., backward-compat re-exports)
                    groups.setdefault("reasoner.models", []).append(alias)

            if len(groups) == 1 and "reasoner.models" in groups:
                return node  # No change needed

            # Return multiple import statements, one per new module
            # (ast.unparse handles this in Python 3.9+)
            return node  # Simplified — in practice use libcst for multi-statement output

        return node

def main():
    for py_file in BASE.rglob("*.py"):
        if "site-packages" in str(py_file) or "__pycache__" in str(py_file):
            continue
        # ... apply migrator
```

**Files created**:
- `domain/pipeline_state.py` (~500 lines)
- `domain/orchestration_types.py` (~150 lines)
- `domain/core_types.py` (~300 lines)
- `domain/enums.py` (~100 lines)

**Files modified**:
- `models.py` — reduced to re-exports + serialization methods (~200 lines)
- 105 importer files — updated via script

**Verification**:
- `grep "from reasoner.models import" src/reasoner/ --include="*.py" | grep -v "models.py"` returns zero
- All existing tests pass
- `models.py` < 300 lines

### Step 2.2 — Wire streaming.py to WorkflowRunner (1.5 days)

Same as original plan Step 2.3. Key change: streaming.py delegates phase execution to the existing `WorkflowRunner.run_phase()`.

**Implementation note**: The WorkflowRunner already has retry, timeout, quality, and event publishing. The SSE callback pattern from the original plan is correct.

**Additional fix**: Move `_run_phase_with_keepalive` from streaming.py into WorkflowRunner as a configurable option:

```python
class WorkflowRunner:
    def __init__(self, services, monitor=None, 
                 sse_callback=None, keepalive_interval: float = 15.0):
        ...
```

**`api/streaming.py` after refactor** (target: < 350 lines):
- Pre-flight: HyperGate decision, preset resolution, neuro recall → `PipelineOrchestrator.preflight()`
- Execute: Phase loop with SSE callbacks → `WorkflowRunner.run(strategy, state)`
- Post-flight: Neuro learn, history save, event persistence → `PipelineOrchestrator.postflight()`
- Remaining in streaming.py: SSE framing (`_event()`), `_sse()` adapter, `run_stream_cached()` wrapper

**Verification**: `api/streaming.py` < 400 lines. `grep "async def.*phase" api/streaming.py` returns zero.

### Step 2.3 — Split core/constants.py (0.5 day)

Same as original plan Step 2.4.

### Step 2.4 — Create PipelineOrchestrator (1 day — NEW, replaces original Step 3.1)

**Objective**: Single entry point for pipeline execution, used by both CLI and SSE.

```python
# application/orchestrator.py
class PipelineOrchestrator:
    """Single entry point for pipeline execution.
    
    Used by: api/streaming.py (SSE), main.py (CLI), tests.
    """
    
    def __init__(self, preset_service, pipeline_service):
        self.preset_service = preset_service
        self.pipeline_service = pipeline_service
    
    async def preflight(self, req: RunRequest) -> PreflightDecision:
        """HyperGate routing, preset resolution, neuro recall."""
        ...
    
    async def execute(self, decision: PreflightDecision, state) -> PipelineState:
        """Run the pipeline and return final state."""
        pipeline = self.pipeline_service.create_pipeline(...)
        return await pipeline.run(problem=decision.problem, method=decision.method)
    
    async def postflight(self, state: PipelineState):
        """Neuro learn, history save, cost tracking."""
        ...
```

**Key design decision**: PipelineOrchestrator calls `ReasonerPipeline.run()` directly — NOT through CQRS handlers. This avoids the indirection identified during evaluation. The CQRS handlers (`RunPipelineCommandHandler`, etc.) remain available for async/distributed use cases but are not forced into the hot path.

**Verification**:
- `grep "ReasonerPipeline(" src/reasoner/api/` returns zero
- Both `api/streaming.py` and `main.py` use `PipelineOrchestrator`

---

## Phase 3: Event Sourcing Lite (Week 5–6) — Score 7.5 → 8.3

### Step 3.1 — Add Event Emission to PipelineState (2 days — REPLACES original Step 2.2)

**Key change from original**: Instead of full PipelineAggregate replacement (high risk, 2-day estimate unrealistic), take an incremental approach.

**Implementation**:

1. **Add `_emit_event` method to PipelineState**:
   ```python
   class PipelineState:
       _event_bus: EventBus | None = None
       
       def wire_event_bus(self, bus: EventBus):
           self._event_bus = bus
       
       def _emit(self, event_type, **kwargs):
           if self._event_bus:
               event = make_event(event_type, ...)
               asyncio.create_task(self._event_bus.publish(event))
   ```

2. **Emit events on key state transitions** (not every mutation — only meaningful ones):
   - `problem` setter → `PIPELINE_STARTED`
   - Phase start → `PHASE_STARTED`
   - Phase complete → `PHASE_COMPLETED`
   - Phase error → `PHASE_FAILED`
   - Pipeline done → `PIPELINE_COMPLETED`

3. **Create EventStore subscriber** that persists events on publish:
   ```python
   async def persist_events_handler(event: DomainEvent):
       store = get_event_store()
       await store.save_events([event])
   
   bus.subscribe_all(persist_events_handler)
   ```

4. **PipelineAggregate remains for replay/resume only** — no change to its implementation:
   ```python
   async def resume_pipeline(aggregate_id: str) -> PipelineState:
       events = await event_store.get_events(aggregate_id)
       aggregate = PipelineAggregate(aggregate_id)
       aggregate.load_from_history(events)
       return PipelineState.from_aggregate(aggregate)
   ```

This approach:
- Achieves auditability (all state transitions in EventStore)
- Enables resume (replay from events)
- Maintains backward compatibility (PipelineState API unchanged)
- Avoids full rewrite risk
- Takes 2 days instead of 4–5

**Verification**:
- Integration test: run pipeline → check EventStore has events → replay → assert state matches
- SSE snapshot test: captured SSE events from before/after refactoring are identical

### Step 3.2 — FastAPI-Native Dependency Injection (1 day — REPLACES original Step 3.3)

**Key change from original**: No separate `Container` class. Use FastAPI's built-in DI.

```python
# api/dependencies.py

async def get_event_bus(request: Request) -> EventBus:
    """FastAPI dependency: provides the shared EventBus."""
    if not hasattr(request.app.state, "event_bus"):
        from reasoner.application.event_bus.bus import EventBus
        request.app.state.event_bus = EventBus()
        await request.app.state.event_bus.start()
    return request.app.state.event_bus

async def get_event_store(request: Request) -> EventStore:
    """FastAPI dependency: provides the shared EventStore."""
    if not hasattr(request.app.state, "event_store"):
        from reasoner.infrastructure.persistence.event_store import EventStore
        request.app.state.event_store = EventStore()
    return request.app.state.event_store

async def get_run_state_manager(request: Request):
    """FastAPI dependency: provides the RunStateManager."""
    if not hasattr(request.app.state, "run_state"):
        from reasoner.infrastructure.redis.run_state import RunStateManager
        request.app.state.run_state = RunStateManager()
    return request.app.state.run_state
```

**Usage in endpoints**:
```python
@app.post("/api/run")
async def run_pipeline(
    req: RunRequest,
    event_bus: EventBus = Depends(get_event_bus),
    event_store: EventStore = Depends(get_event_store),
    ...
):
    state = PipelineState(problem=req.problem)
    state.wire_event_bus(event_bus)
    ...
```

**Remove global singletons** (keep lazy init functions for non-FastAPI contexts like CLI):
```python
# event_bus/bus.py — keep get_event_bus() for CLI usage
# But api/ code uses Depends(get_event_bus) instead
```

**Verification**:
- `grep "get_event_bus()" src/reasoner/api/` returns zero (all through Depends)
- `grep "get_event_store()" src/reasoner/api/` returns zero

### Step 3.3 — SSE Snapshot Tests (1 day — NEW)

**Objective**: Guarantee the SSE event structure consumed by the frontend doesn't change during refactoring.

```python
# tests/snapshots/test_sse_events.py

SNAPSHOT_DIR = Path("tests/snapshots/sse")

@pytest.mark.parametrize("method", ["multi_perspective", "debate", "research", "writing"])
async def test_sse_event_structure_matches_snapshot(method):
    """Verify SSE event structure hasn't changed for each method."""
    with mock_llm_responses(method):
        events = []
        async for chunk in run_stream(RunRequest(problem="test", preset=f"{method}-budget")):
            if chunk.startswith("data: "):
                events.append(json.loads(chunk[6:]))

    snapshot_file = SNAPSHOT_DIR / f"{method}.json"
    # On first run: write snapshot
    if not snapshot_file.exists():
        snapshot_file.write_text(json.dumps(events, indent=2))
        pytest.skip("Snapshot created")

    expected = json.loads(snapshot_file.read_text())

    # Compare structure (types, keys) — not content
    for i, (actual, expect) in enumerate(zip(events, expected)):
        assert actual.get("type") == expect.get("type"), f"Event {i}: type mismatch"
        if "data" in expect:
            assert set(actual.get("data", {}).keys()) == set(expect["data"].keys()), \
                f"Event {i}: data keys mismatch"
```

**Verification**: These tests pass after every refactoring step.

---

## Phase 4: Hardening (Week 7–8) — Score 8.3 → 9.0

**Key change from original**: Cut scope to essentials only. Deferred items moved to v3.1.

### Step 4.1 — Achieve 80%+ Test Coverage (1.5 weeks)

Same as original but with tighter focus:

1. **Event sourcing tests** (highest priority, 3 days):
   - `tests/test_event_emission.py`: Verify events are emitted on state transitions
   - `tests/test_event_replay.py`: Run pipeline → replay from EventStore → state equality
   - `tests/test_resume.py`: Pipeline can be resumed from stored events

2. **Architecture fitness functions** (1 day):
   - Extend `test_layer_boundaries.py` from Phase 1
   - Add `test_no_circular_imports.py`
   - Add `test_file_size_limits.py` (models.py < 300, api/__init__.py < 300, streaming.py < 400)

3. **Integration tests** (3 days):
   - `tests/integration/test_pipeline_e2e.py`: Mock LLM, verify phase sequence
   - `tests/integration/test_fallback_chain.py`: ProviderRouter fallback behavior
   - `tests/integration/test_cancellation.py`: Cancel mid-pipeline

**Deferred to v3.1**: Provider contract tests (need second provider first), full E2E with real LLM.

### Step 4.2 — Structured Logging (1 day)

Same as original Step 4.3.

**Implementation**:
```python
# logging_utils.py — add structured logging setup
import structlog

def setup_logging(environment: str):
    if environment == "production":
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.JSONRenderer(),
            ],
        )
    else:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.dev.ConsoleRenderer(),
            ],
        )
```

**Migration**: Replace `logger.info(f"...")` with `logger.info("event_name", key=value)` in top 20 most-logged files. Not a full migration — just the hot path (pipeline, streaming, router).

### Step 4.3 — Security Consolidation (2 days)

Same as original Step 4.4 but with tighter scope:

1. **Centralize auth**: Single `require_auth` FastAPI dependency
2. **Dependency scanning in CI**: Add `pip-audit` step
3. **Threat model**: `docs/security/threat-model.md` (STRIDE, 1 page)

**Deferred to v3.1**: CSP review (already has SecurityHeadersMiddleware), full penetration testing.

### Step 4.4 — CI Hardening (1 day)

1. **Change coverage gate**: 60% fail → 80% fail, 80% warn → 90% warn
2. **Add import-lint to CI**: Run `test_layer_boundaries.py` on every PR
3. **Add pip-audit to CI**: Fail on HIGH/CRITICAL CVEs
4. **Fix CI legacy references**: Update `self-healing-ci.yml` to use current module paths (it references `health_check.py`, `circuit_breaker.py`, `pipeline.py` → `ARAPipeline` — all legacy paths)

### Deferred to v3.1

| Item | Reason |
|------|--------|
| OpenTelemetry tracing | Requires infrastructure (collector, Jaeger/Grafana); adds dependency. Basic spans are cheap but full integration needs ops work. |
| Anthropic direct provider | Only valuable with contract tests; contract tests need OTel/monitoring first. |
| Redis-backed phase queue | Requires multi-worker deployment first; single-worker is sufficient for current scale. |
| Load test baseline | Needs production-like environment; premature without multi-worker. |
| Grafana dashboard | Depends on OTel + structured logging being in place. |

---

## Migration Sequencing (Optimized)

```
Phase 1 (W1-2)          Phase 2 (W3-4)           Phase 3 (W5-6)          Phase 4 (W7-8)
──────────────────────────────────────────────────────────────────────────────────────
1.1 AGENTS.md ───┐
1.2 Env consol    │
1.3 Extract init   ├──► 2.1 Decomp + migrate ──► 3.1 Event emission ──► 4.1 80% coverage
1.4 LLMPort + fix  │    2.2 Wire runner             3.2 FastAPI DI         4.2 Struct logging
1.5 Import-lint CI ┘    2.3 Split constants         3.3 SSE snapshots      4.3 Security
                         2.4 PipelineOrchestrator                           4.4 CI hardening
```

---

## Risk Matrix (Optimized)

| Step | Risk | Probability | Impact | Mitigation |
|------|------|-------------|--------|------------|
| 2.1 Decomp + migrate | 105 files touched; import errors | Medium | Medium | AST-based script with dry-run; full test suite; atomic commit |
| 2.2 Wire runner | SSE keepalive timing changes | Medium | Medium | Identical keepalive interval in WorkflowRunner; SSE snapshot tests |
| 3.1 Event emission | Events fire but not persisted | Low | Medium | Integration test verifies EventStore has entries after run |
| 3.2 FastAPI DI | Circular dependency with lifespan | Low | Low | Lazy init in Depends() avoids import-time resolution |

---

## Verification Gates (Optimized)

### Phase 1 Gate
- [ ] `grep "mixins" AGENTS.md` returns zero
- [ ] `grep -r "os\.environ\|os\.getenv" src/reasoner/ --include="*.py" | grep -v settings.py` returns zero
- [ ] `api/__init__.py` < 250 lines
- [ ] `grep "@app\.(get|post)" api/__init__.py` returns ≤ 1
- [ ] `grep "from reasoner.infrastructure" application/flows/base.py` returns zero
- [ ] `pytest tests/architecture/test_layer_boundaries.py` passes
- [ ] `PipelineState(problem="", language=` does not appear in `_universal.py`
- [ ] All existing tests pass

### Phase 2 Gate
- [ ] `models.py` < 300 lines
- [ ] `grep "from reasoner.models import" src/reasoner/ --include="*.py" | grep -v models.py` returns zero
- [ ] `api/streaming.py` < 400 lines
- [ ] `grep "async def.*phase" api/streaming.py` returns zero
- [ ] `grep "ReasonerPipeline(" src/reasoner/api/` returns zero
- [ ] Both `streaming.py` and `main.py` import `PipelineOrchestrator`
- [ ] SSE snapshot tests pass (or snapshots created on first run)
- [ ] All existing tests pass

### Phase 3 Gate
- [ ] Integration test: run pipeline → EventStore has events → replay → state matches
- [ ] `grep "get_event_bus()" src/reasoner/api/` returns zero
- [ ] `grep "get_event_store()" src/reasoner/api/` returns zero
- [ ] SSE snapshot tests pass (no structural changes)
- [ ] All existing tests pass

### Phase 4 Gate
- [ ] Coverage > 80% (CI enforced)
- [ ] `pip-audit` passes in CI (no HIGH/CRITICAL CVEs)
- [ ] `import-lint` passes in CI
- [ ] File size limits enforced: models.py < 300, api/__init__.py < 300, streaming.py < 400
- [ ] `docs/security/threat-model.md` exists
- [ ] Structured logs emit valid JSON in production mode
- [ ] All existing tests pass

---

## Scorecard — Before & After (Optimized)

| Dimension | Before | Phase 1 | Phase 2 | Phase 3 | Phase 4 (Target) |
|-----------|--------|---------|---------|---------|-------------------|
| Layered Architecture | 5 | 7 | 7 | 8 | **9** |
| CQRS / Event Sourcing | 4 | 4 | 5 | 7 | **8** |
| Hexagonal / Ports | 6 | 7 | 8 | 8 | **9** |
| Composition / Strategy | 7 | 7 | 9 | 9 | **9** |
| Infrastructure Quality | 7 | 8 | 8 | 8 | **9** |
| API Design | 5 | 7 | 9 | 9 | **9** |
| Testing Architecture | 5 | 6 | 7 | 8 | **9** |
| Observability | 5 | 5 | 5 | 6 | **8** |
| Security | 6 | 7 | 7 | 8 | **9** |
| Dependency Health | 5 | 6 | 8 | 9 | **9** |
| **Overall** | **5.8** | **6.8** | **7.5** | **8.3** | **9.0** |

**Note on CQRS/ES scoring**: The optimized plan caps CQRS/Event Sourcing at 8/10 (not 9). Full event sourcing with PipelineAggregate as canonical state would require 4–5 days of high-risk work. The incremental approach (event emission + replay/resume) achieves 80% of the value at 40% of the risk. Full event sourcing is a v3.1 candidate.

**Note on Observability scoring**: Caps at 8/10. Full OTel tracing with Grafana dashboards and SLO alerts is deferred to v3.1. Structured logging + existing Prometheus/Sentry/Langfuse reach 8/10.

---

## What's Different from the Original Plan

| Original Plan | Optimized Plan | Rationale |
|---------------|----------------|-----------|
| Forced CQRS handler indirection (Step 3.1) | PipelineOrchestrator calls ReasonerPipeline directly; handlers remain for async use | Handler is a thin wrapper — indirection adds no value in single-process |
| Full PipelineAggregate replacement (2 days) | Incremental event emission + PipelineAggregate for replay only (2 days) | Original estimate was unrealistic; incremental approach achieves 80% of benefit |
| Container class for DI (1.5 days) | FastAPI Depends() extension (1 day) | FastAPI already has DI; adding Container duplicates it |
| Decomposition + import migration in separate phases | Atomic single-step (merged) | Intermediate state causes confusion |
| Phase 4: 4.5 weeks of aspirational work | Phase 4: 2 weeks of essentials only | Unrealistic scope; deferred items to v3.1 |
| No SSE compatibility verification | SSE snapshot tests in Phase 3 | Frontend consumes these events; structure must be stable |
| No concrete migration automation | AST-based migration script provided | 105 files need systematic migration, not manual edits |
| No "preserved components" list | Explicit list of what NOT to change | Prevents over-refactoring of well-built components |

---

*Plan evaluated and optimized 2026-06-02.*
