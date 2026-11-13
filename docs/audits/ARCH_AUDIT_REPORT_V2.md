# Architecture Audit Report (V2.0)
**Project**: Reasoner
**Date**: 2026-06-24

## STEP 0: INPUT GATE
- [x] Full codebase
- [x] Primary entry point(s) identified (`asgi.py`, `src/reasoner/api/__init__.py`, `main.py`)
- [x] Architecture Decision Records / Docs (`ARCHITECTURE_REMEDIATION_PLAN.md`, `DESIGN.md`)
- [x] Dependency manifests (`requirements.txt`)
- [x] Deployment manifests (`Dockerfile`, `docker-compose.yml`)

## STEP 1: ARCHITECTURAL FINGERPRINTING

**DETECTED ARCHITECTURE: Layered / CQRS with Pipeline Orchestration** [VERIFIED]

**Evidence:**
1. **Strict Layering**: An `importlinter` contract enforces `api -> application | infrastructure -> core -> domain`. [VERIFIED] 
2. **CQRS Pattern**: Business logic is triggered via Command objects (e.g., `RunPipelineCommand`) and handled by `RunPipelineCommandHandler` in `application/handlers/handlers.py`. [VERIFIED]
3. **Pipeline Orchestration**: AI execution flows through a discrete phase-based pipeline (`ReasonerPipeline`) which applies typed deltas to an immutable `PipelineState`. [VERIFIED]
4. **Data Flow**: Async generator-based Server-Sent Events (SSE) streaming pushed through an `asyncio.Queue` injected into handlers. [VERIFIED]
5. **Configuration**: Centralized environment-aware settings via `reasoner.core.settings`. [VERIFIED]

## STEP 2: COMPLIANCE MATRIX

| Module | Detected Pattern | Intended Pattern | Drift | Violations | Severity | Evidence |
|--------|-----------------|-----------------|-------|------------|----------|----------|
| `domain.pipeline_state` | Pure Data Object | Pure Data Object | None | None | LOW | Serialization moved to `PipelineSerializationService`. [VERIFIED] |
| `api.streaming` | Thin Router/Dispatcher | Dispatcher | Low | None | LOW | Execution logic successfully extracted to `api.execution.*`. [VERIFIED] |
| `application.handlers` | CQRS Command Handler | CQRS | Low | Depends on `api` | MEDIUM | `.importlinter` exception list. [VERIFIED] |
| `hypergate` | Sub-agent Facade | Facade | None | None | LOW | Uses Redis L2 caching and parallel async gathering. [VERIFIED] |
| `infrastructure.llm` | Strategy/Adapter | Adapter | None | None | LOW | `ProviderRouter` wraps multi-provider fallback. [VERIFIED] |

## STEP 3: DEPENDENCY & COUPLING ANALYSIS

- **Circular Dependencies**: The historic circular dependency between `flows/__init__.py` and `api.serializers` was resolved. No active circular imports detected. [VERIFIED]
- **Layer Leaks**: 
  - `application.handlers.handlers -> reasoner.api` [VERIFIED]. CQRS handlers should not depend on presentation details.
  - `application.services.preset_service -> reasoner.infrastructure.llm.registry` [VERIFIED]. Application layer directly accessing infrastructure registry.
- **Shared Mutable State**: Eliminated. `PipelineState` uses delta-based state transitions (reducers) to safely handle concurrent perspective generation. [VERIFIED]
- **Tight Coupling Hotspots**: `application.pipeline` is heavily coupled to `infrastructure.llm.router` and `infrastructure.translation`, bypassing `ports` or `interfaces` in the core layer. [HYPOTHESIS]

## STEP 4: AI ORCHESTRATOR REVIEW

**ORCHESTRATION MODEL**
- Orchestration is centralized in `PipelineOrchestrator` and `ReasonerPipeline`.
- Routing logic is separated into `ProviderRouter` with explicit fallback chains (`anthropic` -> `openai` -> `google`). [VERIFIED]

**ASYNC AND CONCURRENCY**
- Async patterns are consistent. `asyncio.gather(..., return_exceptions=True)` is used for resilience in parallel sub-agent execution. [VERIFIED]
- Concurrent LLM calls are explicitly bounded by `_LLM_CONCURRENCY_SEMAPHORE` in the router to prevent socket exhaustion. [VERIFIED]

**STATE AND CONTEXT**
- Conversation state is explicitly tracked in `PipelineState.conversation_state`.
- Pipeline state is saved asynchronously to a Redis store (or Postgres) and reconstructed for follow-ups. [VERIFIED]

**FAILURE SEMANTICS**
- Circuit breakers protect failing LLM endpoints. [VERIFIED]
- Multi-provider fallback gracefully degrades from primary to backup models on timeouts or errors. [VERIFIED]

**SCALABILITY BOTTLENECKS**
- Orchestrator relies on an L2 Redis cache (`hypergate:{hash}`) and Postgres event store to prevent SQLite write-locks.
- The single point most likely to fail under 10x load is the SSE queue backpressure if client connections drop ungracefully. [HYPOTHESIS]

## STEP 5: ANTI-PATTERN DETECTION

- **Infrastructure Leakage into Application Layer** [VERIFIED] 
  - *Evidence*: `.importlinter` ignores list shows `reasoner.application.pipeline -> reasoner.infrastructure.llm.executor`.
  - *Severity*: MEDIUM.
- **Premature Orchestration Bypass** [FALSE]
  - Previously a "God module" anti-pattern in `api/streaming.py` bypassed CQRS handlers. This was explicitly destroyed during the architecture remediation.

## STEP 6: EXECUTIVE SUMMARY

**ARCHITECTURE SCORE: 9 / 10**
(Recently upgraded from 5.5 through rigorous remediation of layer boundaries, immutability, and transport decoupling.)

**MATURITY LEVEL**: Early Production

**PRIMARY RISKS**:
1. Application layer directly imports Infrastructure layer implementations (e.g., `llm.router`), bypassing Core abstraction ports.
2. Handlers have residual presentation-layer knowledge (`reasoner.api` imports).

**CRITICAL VIOLATIONS**:
None. (All CRITICAL severity issues were resolved in the recent remediation sprint).

**REFACTOR URGENCY**: Backlog
*Justification*: The core structural violations have been successfully eradicated. Remaining issues are explicit, localized technical debt documented in `.importlinter` that do not block scaling or correctness.

## STEP 7: REFACTORING ROADMAP

**IMMEDIATE**:
- None. The system is structurally sound for production deployment.

**HIGH-IMPACT (next sprint)**:
- **[Finding: Handlers depend on API]** → Refactor `RunPipelineCommandHandler` to decouple any SSE formatting logic. Move `_event` or DTO serialization completely out of the handler into the `PipelineExecutionService` or a dedicated API presenter. → *Outcome: Pure CQRS handlers.*

**LONG-TERM (architectural evolution)**:
- **[Finding: App depends on Infra]** → Introduce explicit `ILLMRouter` and `IPipelineExecution` interfaces in the `reasoner.core.ports` package. Have the Application layer rely on these ports, and inject the Infrastructure implementations at the FastAPI startup boundary.
- **Migration Sequence**: 
  1. Define ports in `core`. 
  2. Update `application` to type-hint against ports. 
  3. Wire dependencies in `api.dependencies`.
- **Risk**: Low, purely structural refactoring.
