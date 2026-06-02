# Comprehensive Architectural Refactoring Plan

Based on the **AI Orchestrator Architecture Audit Report** and the **God-Node Decoupling Plan**.

## 1. Goal
Transition from a "Hidden Monolith" with a God Object orchestrator and massive Shared Kernel to a clean **Hexagonal Domain-Driven Design (DDD)** architecture.

## 2. Phase 1: Stop the Bleeding (Dependency Inversion)
**Objective**: Fix the most egregious boundary violations where Domain/Core layers depend on Infrastructure.

### 1.1 Search Infrastructure Extraction
- **Problem**: `src/reasoner/core/search.py` is tightly coupled to `httpx` and `SearXNG`.
- **Action**:
    - Define a `SearchServicePort` (Protocol) in `src/reasoner/core/search.py`.
    - Create `src/reasoner/infrastructure/search/searxng_adapter.py` implementing the port.
    - Inject the adapter into the core search logic.

### 1.2 Preset Domain Purity
- **Problem**: `src/reasoner/domain/preset_core.py` imports `ProviderRouter` from infrastructure.
- **Action**:
    - Remove `ProviderRouter` dependency.
    - Move model validation logic to an Application-layer service or use a pure model registry.

### 1.3 LLM Infrastructure Relocation
- **Problem**: `src/reasoner/llm.py` acts as a top-level shim.
- **Action**:
    - Move `llm.py` contents to `src/reasoner/infrastructure/llm/router.py`.
    - Update all imports to use the new path (or provide a temporary shim in `llm.py` with deprecation warnings).

## 3. Phase 2: Shattering the Shared Kernel (models.py)
**Objective**: Break the 1700-line `models.py` file and the `PipelineState` god object.

### 2.1 Decouple PipelineState
- Follow **Phase 2 & 4** of `tasks/god-node-decoupling-plan.md`.
- Introduce `MethodState` dict wrapper to remove 19 named fields from `PipelineState`.
- Split `PipelineState` into `PipelineCore`, `PipelineMeta`, and `PipelineRemainder`.

### 2.2 Layer-Specific Schemas
- Create `src/reasoner/api/schemas.py` for Pydantic request/response models.
- Create `src/reasoner/domain/models.py` for pure domain entities.
- Implement mappers to convert between Domain Entities, Application State, and API DTOs.

## 4. Phase 3: Kill the God Object (Orchestrator Refactor)
**Objective**: Replace the 15+ inheritance mixins in `pipeline.py` with a composition-based Strategy pattern.

### 3.1 Transition to Flow Strategies
- Move logic from `src/reasoner/application/mixins/` to `src/reasoner/application/flows/`.
- Create a `WorkflowStrategy` interface.
- Implement specific strategies: `MultiPerspectiveFlow`, `DebateFlow`, `ScientificFlow`, etc.

### 3.2 Thin Orchestrator
- Refactor `ReasonerPipeline` to be a lightweight engine.
- Instead of inheriting from mixins, it should accept a `WorkflowStrategy` and call `.execute(state)`.

## 5. Phase 4: Event-Driven Choreography
**Objective**: Finalize the event-sourcing architecture.

### 4.1 Typed Event Enums
- Follow **Phase 3** of `tasks/god-node-decoupling-plan.md`.
- Split `EventType` into `PipelineEventType`, `WidgetEventType`, `MemoryEventType`, and `SaaSEventType`.

### 4.2 Decoupled Event Handlers
- Ensure all non-core logic (logging, token tracking, notification) happens in Event Handlers, not within the Pipeline execution flow.

## 6. Implementation Schedule & Risk
| Phase | Complexity | Risk | Priority |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Medium | Low | **Immediate** |
| **Phase 2** | High | High | **High** |
| **Phase 3** | Very High | High | **Medium** |
| **Phase 4** | Medium | Medium | **Low** |

## 7. Verification Strategy
- **Unit Tests**: Existing tests must pass after each phase.
- **Integration Tests**: Run `main.py` with various presets to ensure E2E functionality.
- **Dependency Check**: Use `graphify` or `ruff` to verify that no new boundary violations are introduced.
