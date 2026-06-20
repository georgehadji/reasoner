# Strategy B: Component Extraction Plan

**Status:** Planning  
**Effort Estimate:** 96 person-days (2 engineers × 3 weeks, or 4 engineers × 1.5 weeks)  
**Risk:** MEDIUM — new component layer added, legacy path preserved  
**Goal:** Extract service layers from God Objects, reduce `CHANGE_COST` for new features from ~57 to ~15 person-hours

---

## Context from Audit + Exploration

### Current State
- `pipeline.py` (2301 L) — `ARAPipeline` with 17-branch `elif` dispatch, hard-coded phase sequences
- `renderer.py` (1686 L) — 16 method-specific renderers + `MethodType` enum dispatch
- `api/__init__.py` (2009 L) — 40 endpoints, 3 middleware classes, auth deps, streaming logic
- `presets.py` (1195 L) — `PipelinePreset` dataclass, PRESETS dict, routing validation
- `NewARAPipeline` exists in `infrastructure/llm/new_pipeline.py` but is **dead code**
- CQRS commands/handlers/queries/event_bus exist but are barely wired

### Problem
Adding a new reasoning method requires touching:
1. `pipeline.py` — add `_run_new_method_pipeline()` + branch in `run()`
2. `presets.py` — add preset config + routing
3. `renderer.py` — add `_render_new_method()` + branch in `render_pipeline_result()`
4. `api/__init__.py` — add phase list in `run_stream()` + serializer mapping
5. `serializers.py` — add `_ser_*` for new phases
6. `config.js` (frontend) — add preset option
7. Tests

**CHANGE_COST = 57 person-hours** per new method.

---

## Strategy B Architecture Target

```
Interfaces (api/)
    ├── routers/          ← FastAPI route modules (thin)
    ├── dependencies.py   ← auth, rate limiting
    ├── middleware.py     ← SecurityHeaders, MemoryLimit, RequestTimeout
    └── streaming.py      ← run_stream orchestration

Application (application/)
    ├── controllers/
    │   └── pipeline_controller.py  ← replaces api/__init__.py:run_stream core
    ├── services/
    │   ├── search_service.py       ← discovery client, search, vetting
    │   ├── renderer_service.py     ← render strategy registry
    │   └── preset_service.py       ← preset resolution, router building
    └── flows/
        └── pipeline_flow.py        ← phase sequence registry + dispatcher

Domain (models/, core/)
    ├── models.py
    └── constants.py

Infrastructure (infrastructure/)
    ├── llm/ports.py, llm.py
    ├── persistence/event_store.py
    └── cache.py
```

**Principle:** Extract layers without rewriting legacy logic. Legacy `ARAPipeline` remains the execution engine; new controllers/services wrap it.

---

## Phase 1: Pipeline Flow Controller (Week 1, Days 1-3)

### Goal
Replace the 17-branch `elif` dispatch in `ARAPipeline.run()` with a **phase sequence registry**.

### 1.1 Create `application/flows/pipeline_flow.py`

```python
"""Phase sequence registry and dispatcher for reasoning methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Awaitable, Protocol

from reasoner.models import PipelineState


class PhaseFn(Protocol):
    async def __call__(self, state: PipelineState) -> None: ...


@dataclass(frozen=True)
class PhaseStep:
    num: int | float
    name: str
    fn: PhaseFn
    serializer: Callable[[PipelineState], dict]
    critical: bool = False


class PipelineFlow:
    """Registry that maps method names to ordered phase sequences."""

    def __init__(self) -> None:
        self._sequences: dict[str, list[PhaseStep]] = {}

    def register(self, method: str, steps: list[PhaseStep]) -> None:
        if method in self._sequences:
            raise ValueError(f"Method '{method}' already registered")
        self._sequences[method] = steps

    def get_sequence(self, method: str) -> list[PhaseStep]:
        return self._sequences.get(method, self._sequences.get("multi-perspective", []))

    @property
    def methods(self) -> set[str]:
        return set(self._sequences.keys())
```

### 1.2 Create `application/flows/__init__.py`

Export `PipelineFlow`, `PhaseStep`, plus a factory that builds the default registry from the existing hard-coded sequences.

### 1.3 Build `DefaultFlowRegistry` factory

```python
def build_default_flow_registry(pipeline: ARAPipeline) -> PipelineFlow:
    """
    Build a flow registry backed by an ARAPipeline instance.
    Each step binds to the corresponding _phase_* method on the pipeline.
    """
    from reasoner.api.serializers import _ser_0, _ser_1, _ser_1_5, _ser_2, _ser_3, _ser_4, _ser_5

    flow = PipelineFlow()

    # Universal phases (classification, decomposition, vetting)
    universal = [
        PhaseStep(0, "Classification", pipeline._phase_0_classification, _ser_0, critical=True),
        PhaseStep(1, "Decomposition",  pipeline._phase_1_decomposition, _ser_1, critical=True),
    ]

    # Method-specific sequences
    flow.register("multi-perspective", universal + [
        PhaseStep(1.5, "Deep Read",       pipeline._phase_deep_read,      _ser_1_5),
        PhaseStep(2,   "Perspectives",    pipeline._phase_2_perspectives, _ser_2),
        PhaseStep(3,   "Critique & Pruning", pipeline._phase_3_critique,  _ser_3, critical=True),
        PhaseStep(4,   "Stress Testing",  pipeline._phase_4_stress_test,  _ser_4),
        PhaseStep(5,   "Synthesis",       pipeline._phase_synthesis,      _ser_5, critical=True),
    ])

    flow.register("debate", universal + [
        PhaseStep(2, "Opening",      pipeline._phase_debate_opening,      _ser_2),
        PhaseStep(3, "Rebuttal",     pipeline._phase_debate_rebuttal,     _ser_3),
        PhaseStep(4, "Cross-Examine", pipeline._phase_debate_cross_examine, _ser_4),
        PhaseStep(5, "Judge",        pipeline._phase_debate_judge,        _ser_5, critical=True),
    ])

    # ... etc for all 17 methods
    return flow
```

### 1.4 Refactor `ARAPipeline.run()` to use `PipelineFlow`

**Before (lines 323-363):**
```python
method = self._get_method_from_preset()
if method == "debate": await self._run_debate_pipeline(state)
elif method == "jury": await self._run_jury_pipeline(state)
# ... 15 more branches
```

**After:**
```python
method = self._get_method_from_preset()
flow = build_default_flow_registry(self)
sequence = flow.get_sequence(method)

for step in sequence:
    await step.fn(state)
```

The `_run_*_pipeline()` methods can be **deprecated** (kept for backward compat but not called from `run()`).

### 1.5 Update `api/__init__.py:run_stream()` phase builder

**Current:** Hard-coded `if/elif` block (lines 632-684) that assembles `phases` list.

**Target:** Use `PipelineFlow` to get the phase sequence, then iterate.

```python
from reasoner.application.flows import build_default_flow_registry, PhaseStep

flow = build_default_flow_registry(pipeline)
sequence = flow.get_sequence(pipeline._get_method_from_preset())
phases: list[tuple[int | float, str, Callable, Callable]] = [
    (step.num, step.name, step.fn, step.serializer) for step in sequence
]
```

This **eliminates** the duplicate phase-list construction in `api/__init__.py`.

### Validation
- [ ] All existing pipeline tests pass
- [ ] New method can be added by registering a sequence (1 file touch instead of 5)
- [ ] Coverage on `application/flows/` ≥90%

---

## Phase 2: Renderer Service (Week 1, Days 4-5)

### Goal
Replace renderer.py's 16-branch `elif` with a strategy registry.

### 2.1 Create `application/services/renderer_service.py`

```python
"""Method-specific rendering strategy registry."""

from __future__ import annotations

from typing import Callable, Protocol

from reasoner.models import PipelineState


class RenderStrategy(Protocol):
    def __call__(self, state: PipelineState) -> None: ...


class RendererService:
    def __init__(self) -> None:
        self._strategies: dict[str, RenderStrategy] = {}

    def register(self, method: str, renderer: RenderStrategy) -> None:
        self._strategies[method] = renderer

    def render(self, method: str, state: PipelineState) -> None:
        strategy = self._strategies.get(method, self._strategies.get("multi-perspective"))
        strategy(state)

    @property
    def methods(self) -> set[str]:
        return set(self._strategies.keys())
```

### 2.2 Extract render functions from `renderer.py`

Move each `_render_*()` function to `application/services/renderers/`:
```
application/services/renderers/
  __init__.py
  multi_perspective.py   ← _render_multi_perspective
  debate.py              ← _render_debate
  research.py            ← _render_research
  jury.py                ← _render_jury
  scientific.py          ← _render_scientific
  socratic.py            ← _render_socratic
  ... (one per method)
```

Each file exports a `render(state: PipelineState) -> None` function.

### 2.3 Create `application/services/renderers/__init__.py`

Builds and exports a singleton `renderer_service`:

```python
from .multi_perspective import render as render_multi_perspective
from .debate import render as render_debate
# ... etc

renderer_service = RendererService()
renderer_service.register("multi-perspective", render_multi_perspective)
renderer_service.register("debate", render_debate)
# ... etc
```

### 2.4 Refactor `renderer.py`

Replace the 16-branch dispatch with:

```python
def render_pipeline_result(state: PipelineState) -> None:
    from .application.services.renderers import renderer_service
    method = _method_type(state.preset_name)
    renderer_service.render(method.value, state)
    _render_cost_summary(state)
```

Keep `renderer.py` as a thin compatibility shim. All rendering logic lives in `application/services/renderers/`.

### Validation
- [ ] All renderers produce identical output (snapshot tests)
- [ ] `renderer_service.methods` covers all 16 methods
- [ ] Coverage on `application/services/renderers/` ≥80%

---

## Phase 3: Search Service (Week 2, Days 1-3)

### Goal
Encapsulate all search/discovery logic into a single service.

### Current Scatter
- `core/search.py` — `get_discovery_client()`, `reset_discovery_client()`
- `pipeline.py` — `_phase_deep_read()`, `_phase_context_vetting()` call search directly
- `api/__init__.py` — `_stream_web_search_results()`, `/api/search` route
- `NewARAPipeline` — has its own research loops

### 3.1 Create `application/services/search_service.py`

```python
"""Encapsulates web discovery, search, and context vetting."""

from __future__ import annotations

from typing import Any

from reasoner.models import PipelineState
from reasoner.core.search import get_discovery_client


class SearchService:
    """Service for web search, discovery, and context vetting."""

    async def vet_context(
        self,
        state: PipelineState,
        source_type: str | None = None,
        domain: str | None = None,
    ) -> None:
        """Run context vetting (web search) and attach results to state."""
        # Extracted from ARAPipeline._phase_context_vetting
        ...

    async def deep_read(
        self,
        state: PipelineState,
        source_type: str | None = None,
        domain: str | None = None,
    ) -> None:
        """Run deep read for research or knowledge-dense problems."""
        # Extracted from ARAPipeline._phase_deep_read
        ...

    async def search(
        self,
        query: str,
        source_type: str | None = None,
        num_results: int = 10,
        smart: bool = False,
    ) -> list[dict[str, Any]]:
        """Standalone search (for /api/search route)."""
        # Extracted from api/__init__.py:_stream_web_search_results
        ...

    async def close(self) -> None:
        """Close discovery client."""
        from reasoner.core.search import reset_discovery_client
        reset_discovery_client()
```

### 3.2 Refactor `ARAPipeline` to accept `SearchService`

```python
class ARAPipeline:
    def __init__(
        self,
        router: ProviderRouter,
        search_service: SearchService | None = None,
        ...
    ):
        self.router = router
        self.search_service = search_service or SearchService()
```

Phase methods now call `self.search_service.vet_context(state)` instead of direct search code.

### 3.3 Refactor `api/__init__.py` search routes

`/api/search` and `_stream_web_search_results` delegate to `SearchService.search()`.

### Validation
- [ ] Search routes return identical results
- [ ] Deep Read phase produces identical state mutations
- [ ] Discovery client is closed properly on shutdown

---

## Phase 4: API Router Extraction (Week 2, Days 4-5 + Week 3, Days 1-2)

### Goal
Split `api/__init__.py` into focused router modules.

### 4.1 Create `api/dependencies.py`

Extract:
- `get_client_id()`
- `check_rate_limit()`
- `require_auth()`
- `optional_auth()`

### 4.2 Create `api/middleware.py`

Extract:
- `SecurityHeadersMiddleware`
- `MemoryLimitMiddleware`
- `RequestTimeoutMiddleware`

### 4.3 Create `api/routers/` modules

| Module | Routes | Lines Extracted |
|--------|--------|-----------------|
| `uploads.py` | POST/GET/DELETE upload | ~47 |
| `legacy_widgets.py` | weather, stock, calc, discover | ~73 |
| `keys.py` | GET/POST key status/validation | ~125 |
| `pipelines.py` | GET/DELETE pipeline events | ~65 |
| `websocket.py` | /ws, /ws/pipeline, stats | ~60 |
| `history.py` | GET/DELETE history | ~74 |
| `context.py` | POST /api/run-with-context | ~100 |
| `widgets.py` | suggestions, execute, list, detect | ~79 |

### 4.4 Refactor `api/__init__.py`

After extraction, `api/__init__.py` should contain only:
- FastAPI app initialization + middleware registration
- Import and `include_router()` for all sub-routers
- `run_stream()` + `run_followup_stream()` + `run_stream_cached()` (the core pipeline stream)
- `/api/run`, `/api/run-followup`, `/api/search`, `/api/stop`, `/api/cache`
- Health and root endpoints
- Startup/shutdown events

**Target size:** ~800 lines (down from 2009)

### Validation
- [ ] All existing API tests pass
- [ ] No route regressions (hit every endpoint with a smoke test)
- [ ] `api/__init__.py` < 1000 lines

---

## Phase 5: Preset Service (Week 3, Days 3-4)

### Goal
Encapsulate preset resolution and router building.

### 5.1 Create `application/services/preset_service.py`

```python
"""Preset resolution, routing validation, and router construction."""

from __future__ import annotations

import os
from reasoner.presets import get_preset, PipelinePreset
from reasoner.llm import ProviderRouter, _REGISTRY


class PresetService:
    """Encapsulates all preset-related logic."""

    def resolve_preset_name(self, raw_preset: str, is_auto: bool, auto_tier: str) -> str:
        """Resolve 'auto-budget' → 'multi-perspective-budget' etc."""
        ...

    def filter_routing(self, routing: dict[str, str], primary_id: str) -> dict[str, str]:
        """Drop roles whose API key env var is missing."""
        ...

    def build_router(
        self,
        preset: PipelinePreset,
        agent_model: str | None = None,
    ) -> ProviderRouter:
        """Build a ProviderRouter from a preset, with optional agent override."""
        ...

    def build_auto_router(
        self,
        method: str,
        tier: str,
        agent_model: str | None = None,
    ) -> ProviderRouter:
        """Build router for auto-selected method."""
        ...
```

### 5.2 Refactor `api/__init__.py`

Replace inline preset resolution + `_filter_routing` + router construction with:

```python
from reasoner.application.services.preset_service import PresetService

_preset_service = PresetService()

# In run_stream:
preset_name = _preset_service.resolve_preset_name(raw_preset, is_auto, auto_tier)
preset = get_preset(preset_name)
router = _preset_service.build_router(preset, agent_model=initial_state.agent_model if initial_state else None)
```

### Validation
- [ ] All presets resolve correctly
- [ ] Router construction produces identical routing tables
- [ ] Missing API key filtering works identically

---

## Phase 6: Integration & Wiring (Week 3, Day 5)

### 6.1 Wire new services into `run_stream()`

```python
async def run_stream(req: RunRequest, ...) -> AsyncGenerator[str, None]:
    # ... run_id, cancel event ...

    # Preset resolution → router building
    preset_service = PresetService()
    preset_name = preset_service.resolve_preset_name(raw_preset, is_auto, auto_tier)
    preset = get_preset(preset_name)
    router = preset_service.build_router(preset, agent_model=...)

    # Gate agent decision
    if not req.force_pipeline:
        gate = HyperGateAgent(router)
        decision = await gate.decide(req.problem)
        # ... direct/web_search/ rebuild router for auto-method

    # Pipeline execution
    pipeline = ARAPipeline(
        router=router,
        search_service=SearchService(),
        ...
    )

    # Phase sequence from Flow Controller
    flow = build_default_flow_registry(pipeline)
    sequence = flow.get_sequence(method)

    for step in sequence:
        # ... SSE streaming logic ...
        await step.fn(state)
```

### 6.2 Smoke test full pipeline
Run each preset through the API and verify identical SSE output.

### 6.3 Run full test suite
503 tests must still pass.

---

## Effort Breakdown

| Phase | Scope | Files Touched | Person-Days |
|-------|-------|---------------|-------------|
| 1. Pipeline Flow Controller | Phase sequence registry + refactor run() | pipeline.py, application/flows/*, api/__init__.py | 16 |
| 2. Renderer Service | Extract 16 renderers to strategy registry | renderer.py, application/services/renderers/* | 12 |
| 3. Search Service | Encapsulate discovery/search/vetting | pipeline.py, api/__init__.py, application/services/search_service.py | 16 |
| 4. API Router Extraction | Split api/__init__.py into routers | api/__init__.py, api/routers/*, api/middleware.py, api/dependencies.py | 24 |
| 5. Preset Service | Encapsulate preset resolution | presets.py, api/__init__.py, application/services/preset_service.py | 12 |
| 6. Integration & Tests | Wire services, smoke tests, fix regressions | all above + tests | 16 |
| **Total** | | | **96** |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Refactor breaks SSE streaming | Keep `run_stream()` logic intact; only extract phase-list construction |
| Renderer output changes | Snapshot tests before/after; diff pixel-perfect markdown output |
| Search client lifecycle bugs | `SearchService.close()` called in FastAPI shutdown event; add try/finally in tests |
| Route 404s after extraction | Smoke test script that hits every endpoint |
| Performance regression | Benchmark a single pipeline run before/after; target <5% variance |

---

## Rollback Plan

If critical issues found:
1. `api/__init__.py` — can be restored from git (all extraction is additive)
2. `pipeline.py` — `_run_*_pipeline()` methods kept as stubs; `run()` can be reverted to direct dispatch
3. `renderer.py` — render functions kept as re-exports from new modules

---

## Success Criteria

1. **api/__init__.py < 1000 lines** (was 2009)
2. **pipeline.py < 1500 lines** (was 2301)
3. **renderer.py < 200 lines** (was 1686)
4. **Adding a new method touches ≤3 files** (was 5-7)
5. **All 503 existing tests pass**
6. **New test coverage:** application/services/* ≥70%, application/flows/* ≥90%
7. **No performance regression** (>5% threshold)

---

## Recommended Execution Order

Execute **Phase 1 → Phase 2 → Phase 5 → Phase 3 → Phase 4 → Phase 6**.

This order minimizes cross-file churn:
- Phase 1 (Flow Controller) and Phase 2 (Renderer) are independent
- Phase 5 (Preset Service) unlocks cleaner Phase 3 (Search) and Phase 4 (API)
- Phase 4 (API extraction) is highest-risk, so it goes last after services are proven

**Next Action:** Approve Strategy B, pick Phase 1 start date, allocate 2 engineers.
