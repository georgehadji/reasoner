# AI Orchestrator Architecture Audit Report

## 1. Executive Summary

- **Overall Architecture Score**: 4/10
- **Architectural Maturity Level**: Ad-Hoc / Drifting (Incomplete transition to Clean Architecture)
- **Primary Risks**: 
  - **Maintainability Paralysis**: The core orchestrator (`pipeline.py`) is a "God Object" tightly coupled via 15+ inheritance mixins, making it extremely fragile.
  - **Domain Leakage**: The domain model is anemic and heavily coupled to global state (`models.py` Shared Kernel).
  - **Testing Friction**: Infrastructure logic is embedded within core business logic, complicating testability and mock boundaries.
- **Critical Violations**: 
  - Severe Hexagonal Architecture boundary violations (Domain importing Infrastructure).
  - Massive Shared Kernel (`models.py`) imported in over 85 locations spanning all architectural layers.
- **Refactor Urgency Assessment**: **High / Immediate**. The current structural drift threatens the long-term scalability of the orchestrator. Adding new reasoning methods or modifying the state schema will cause cascading failures across the system.

---

## 2. Intended vs Actual Architecture

### Intended Architecture
According to `ARCHITECTURE_MINDMAP.md` and repository conventions (`src/reasoner/` structure), the intended target architecture is **Hexagonal DDD (Domain-Driven Design) + CQRS + Event Sourcing + Mixin Composition**.
The system aims to cleanly separate Domain, Application, Infrastructure, and API layers to ensure business logic is isolated from external I/O and frameworks.

### Actual Architecture
The system suffers from **Structural Drift** and functions largely as a **Hidden Monolith**. While the directory structure (`api/`, `application/`, `core/`, `domain/`, `infrastructure/`) suggests Clean Architecture, the actual implementation bypasses these boundaries.
Top-level shims (`pipeline.py`, `models.py`, `llm.py`) act as central gravity wells, creating a monolithic structure disguised by modular folders. The domain is not pure, and infrastructure leaks deep into core logic.

---

## 3. Architecture Compliance Matrix

| Module / Component | Intended Pattern | Actual Implementation | Violations | Severity |
| :--- | :--- | :--- | :--- | :--- |
| **Pipeline Orchestrator** | CQRS / Event-Driven | God Object w/ multiple inheritance (15+ Mixins) | Hidden Monolith, Tight Coupling | **CRITICAL** |
| **State Models** | Encapsulated Domain Models | Global Shared Kernel (`models.py`) | Anemic Domain, Broad Coupling (85+ imports) | **CRITICAL** |
| **Search / Discovery** | Infrastructure Port/Adapter | Core Service (`core/search.py`) | Infrastructure Leakage (`httpx` in Core) | High |
| **Preset Configuration** | Pure Domain Entity | Domain Entity (`domain/preset_core.py`) | Boundary Violation (Imports `ProviderRouter` from LLM Inf.) | High |
| **Subagents** | Independent Domain Services | Directly coupled to `PipelineState` | Shared-State Risk, Context Leakage | Medium |
| **LLM Adapters** | Hexagonal Infrastructure | Infrastructure + Top-Level Shim | Shim Indirection, Leaky Abstractions | Medium |

---

## 4. Dependency Analysis

The static analysis and graphify checks reveal several severe dependency boundary violations:

- **Boundary Violations (Domain → Infrastructure)**: 
  The core principle of Clean Architecture is that inner layers (Domain) do not depend on outer layers (Infrastructure). However, `src/reasoner/domain/preset_core.py` directly imports `ProviderRouter` from `reasoner.llm` (the infrastructure LLM router).
- **Layer Leaks (Core → Infrastructure I/O)**: 
  `src/reasoner/core/search.py` manages network calls via `httpx.AsyncClient` directly, rather than defining an interface in `Core` and implementing it in `Infrastructure`.
- **Shared-State Risks (The Shared Kernel Anti-Pattern)**:
  `src/reasoner/models.py` contains the `PipelineState` and `TaskType` which are imported across **85 different files** spanning `api/`, `application/`, `core/`, `phases/`, and `subagents/`. This makes `models.py` a bottleneck for changes and prevents independent module compilation/testing.
- **Circular Dependencies & Temporal Coupling**:
  The orchestrator (`pipeline.py`) depends on application mixins (e.g., `perspective_mixin.py`), but those mixins frequently import types or state directly back from the pipeline context, resulting in tight cyclical feedback loops.

---

## 5. AI Orchestrator Specific Review

- **Agent Orchestration Model**: Heavy reliance on a centralized God Object (`ReasonerPipeline`). Every reasoning method (Debate, Delphi, Scientific) is bound into the orchestrator via Python mixins. This makes the orchestrator too large and creates a fragile inheritance hierarchy.
- **Context Propagation**: Context is centrally managed via a gigantic `PipelineState` object rather than being scoped to the specific needs of individual subagents or phases. This risks unintended state mutation.
- **Message/Event Architecture**: While event sourcing is partially implemented (`PipelineAggregate`), the orchestrator itself operates largely imperatively via massive procedural mixin calls rather than pure event-driven choreography.
- **Concurrency Model**: The orchestrator handles parallel execution fairly well internally, but the structural coupling makes adding new async patterns or isolated tool execution environments highly complex.

---

## 6. Architectural Anti-Patterns Detected

1. **The God Object / Hidden Monolith**: `pipeline.py` handles configuration, state management, event emitting, and execution flow for 17 different reasoning methodologies.
2. **The Everything Bagel (Shared Database Coupling / Shared Kernel)**: `models.py` is an almost 1700-line file that houses the entire system's DTOs. It acts as an anemic data model globally accessible and mutable by any layer.
3. **Infrastructure Leakage**: Core and Domain modules contain direct references to HTTP clients, LLM routing logic, and third-party specific configurations.
4. **Premature Abstraction vs. Underengineering**: There is a complex `core/protocol.py` defining Phase boundaries, but the actual implementation skips these boundaries and relies on inherited mixins in the main pipeline object.

---

## 7. Refactoring Roadmap

### Phase 1: Immediate Fixes (Stop the Bleeding)
- **Dependency Inversion for Search**: Move `httpx` logic out of `core/search.py` and into `infrastructure/search/`. Create a `DiscoveryPort` interface in `core`.
- **Domain Purity**: Remove `ProviderRouter` references from `domain/preset_core.py`. Domain logic should only evaluate preset rules; routing execution belongs in the Application/Infrastructure layers.

### Phase 2: High-Impact Improvements (Break the Shared Kernel)
- **Shatter `models.py`**: Decompose the massive `models.py` into layer-specific models:
  - `domain/models.py` (Core domain logic)
  - `api/schemas.py` (Request/Response DTOs - *partially exists but needs enforcement*)
  - `application/state.py` (Pipeline state tracking)
- Implement mapping functions between these layers instead of passing `PipelineState` directly from the API to the Subagents.

### Phase 3: Long-Term Architecture Evolution (Kill the God Object)
- **De-Mixin the Orchestrator**: Transition `ReasonerPipeline` from an inheritance-based monolith (using 15+ mixins) to a **Composition-based Flow Engine**.
- Move logic from `application/mixins/` into self-contained `Workflow` or `Strategy` classes in `application/flows/` that implement a common interface. The Orchestrator should only call `.execute(state)` on the respective strategy.

---

## 8. Confidence Assessment

- **Verified Findings**: High confidence in the Shared Kernel violation (`models.py`), the Infrastructure Leakage (`search.py` and `preset_core.py`), and the Pipeline God Object pattern. These were verified directly via static code analysis (grep).
- **HYPOTHESIS Findings**: Medium confidence regarding the precise execution flow of the event bus vs the procedural mixin calls, as deeper runtime tracing would be required to evaluate performance bottlenecks.
- **Areas Lacking Sufficient Evidence**: Performance profiling of the shared state lock contention during highly parallel phase execution (e.g., Debate/Jury multi-agent phases).
