# Adaptive Capability Router (ACR) — Implementation Plan

**Date:** 2026-07-08
**Status:** Draft
**Scope:** Transform Reasoner's static preset→model routing into a closed-loop adaptive system

---

## 0. Current State Analysis

### What Exists

| Component | Location | Status |
|-----------|----------|--------|
| Model whitelist (131 models) | `infrastructure/llm/registry.py` `_MODEL_WHITELIST` | Routing keys only, no capability metadata |
| Provider router | `infrastructure/llm/router.py` `ProviderRouter` | Static role→model, fallback chain |
| Preset registry | `domain/preset_registry.py` (48 presets) | Hand-curated routing tables |
| Cross-bloc diversity | `registry.py` `bloc_of()` + `_VENDOR_BLOC` | Enforced at preset validation time |
| Circuit breaker | `infrastructure/circuit_breaker.py` | Per-model open/close |
| Concurrency limiter | `router.py` `_get_llm_semaphore()` | Per-model semaphores |
| Multi-provider fallback | `router.py` `_try_direct_fallback()` | anthropic→openai→google chain |
| Prometheus metrics | `infrastructure/metrics.py` | Basic counters + histograms (no per-role quality) |
| Telemetry port | `core/ports/telemetry_port.py` `TelemetryStorePort` | Defined but stores run-level, not call-level |
| LLM port | `core/ports/llm_port.py` `LLMPort` | `ProviderRouter` implements this |

### Architecture Constraints

- **Hexagonal DDD**: New components must respect domain→application→infrastructure layering
- **Domain purity**: Domain layer has no infrastructure imports (known violation: `preset_core.py` → `registry`)
- **Port/adapter pattern**: All new infrastructure must implement core ports
- **Cross-bloc invariant**: Synthesis bloc ≠ scoring bloc; generators span ≥2 blocs
- **Backward compatibility**: Existing presets must continue working; ACR is opt-in initially

### What's Missing (Gap Summary)

1. **No per-call telemetry** — can't learn which model performs best for which role
2. **No capability metadata** — models are opaque routing keys, no structured attributes
3. **No utility function** — selection is declarative (preset says "use model X for role Y"), not computed
4. **No adaptive learning** — routing doesn't improve from experience
5. **No constraint solver** — bloc diversity is validated at preset-creation time, not at selection time

---

## 1. Design Principles

### 1.1 Separation of Concerns

```
Capabilities ≠ Constraints

Capabilities: what a model CAN do (reasoning, legal, creativity, coding...)
  → Scored via benchmarks + telemetry
  → Used for RANKING (cosine similarity, weighted dot product)

Constraints: what a model COSTS or LIMITS (price, latency, context window, availability)
  → Hard filters applied BEFORE ranking
  → Never mixed into the capability vector
```

### 1.2 Build on Measurement, Not Opinion

No hand-assigned capability scores (9.8, 9.6, etc.). All capability values derive from:
1. Benchmark results (L7) — periodic, controlled evaluation
2. Production telemetry (L5) — real-world performance signals
3. Static facts (context window, tool support) — from provider APIs

### 1.3 Constraint Preservation

ACR must preserve and extend existing invariants:
- Cross-bloc diversity (synthesis ≠ scoring bloc, generators ≥2 blocs)
- Circuit breaker state (don't select models with open circuits)
- Concurrency limits (don't overload rate-limited providers)
- Budget ceilings (preset tier determines cost ceiling)

### 1.4 Progressive Adoption

ACR is additive, not destructive:
- Phase 1–2: Collect data alongside static routing (shadow mode)
- Phase 3–4: ACR proposes, presets dispose (advisory mode)
- Phase 5+: ACR selects, constraints validate (adaptive mode)
- Presets remain as override/fallback for deterministic control

---

## 2. Architecture

### 2.1 Component Map

```
                                    ┌─────────────────────┐
                                    │   Benchmark Engine   │  L7
                                    │ (periodic eval jobs) │
                                    └─────────┬───────────┘
                                              │ writes
                                              ▼
┌─────────────────────┐           ┌─────────────────────┐
│  Static Model Facts │──────────▶│  Capability Registry │  L1
│ (context, tools,    │           │ (static + dynamic    │
│  vision, streaming) │           │  per-model profiles) │
└─────────────────────┘           └─────────┬───────────┘
                                            │ provides vectors
                                            ▼
┌─────────────────────┐           ┌─────────────────────┐
│  Task Requirements  │──────────▶│  Adaptive Router     │  L2+L3+L4
│ (per-role capability │           │ (match + score)      │
│  weight vectors)    │           └──────┬──────┬────────┘
└─────────────────────┘                  │      │
                                  ranked │      │ constraints
                                  list   │      │
                                         ▼      ▼
                              ┌──────────────────────────┐
                              │   Constraint Checker      │
                              │ (bloc diversity, budget,  │
                              │  circuit state, concurrency│
                              └──────────┬───────────────┘
                                         │ validated selection
                                         ▼
                              ┌──────────────────────────┐
                              │   ProviderRouter (existing)│
                              │ (call, fallback, circuit) │
                              └──────────┬───────────────┘
                                         │ call result
                                         ▼
                              ┌──────────────────────────┐
                              │   Call Telemetry Collector │  L5
                              │ (per-call quality signals) │
                              └──────────┬───────────────┘
                                         │ feedback
                                         ▼
                              ┌──────────────────────────┐
                              │   Online Learning Engine  │  L6
                              │ (Thompson Sampling /      │
                              │  Bayesian weight updates) │
                              └──────────┬───────────────┘
                                         │ updates
                                         ▼
                              ┌──────────────────────────┐
                              │   Capability Registry     │  L1
                              │ (dynamic attrs updated)  │  (closed loop)
                              └──────────────────────────┘
```

### 2.2 Layer Mapping (Hexagonal)

| ACR Component | Architecture Layer | Reason |
|---------------|-------------------|--------|
| `ModelCapabilities` (value object) | `domain/` | Pure data, no deps |
| `TaskRequirement` (value object) | `domain/` | Pure data, no deps |
| `RoutingConstraint` (protocol) | `core/ports/` | Abstract constraint interface |
| `CapabilityRegistryPort` | `core/ports/` | Port for capability lookup |
| `AdaptiveRouterPort` | `core/ports/` | Port for model selection |
| `TelemetryCollectorPort` | `core/ports/` | Port for call-level telemetry (extends existing `TelemetryStorePort`) |
| `CapabilityRegistry` (impl) | `infrastructure/llm/` | Adapter: reads/writes capability profiles |
| `AdaptiveRouter` (impl) | `infrastructure/llm/` | Adapter: utility scoring + selection |
| `ConstraintChecker` (impl) | `infrastructure/llm/` | Adapter: bloc/budget/circuit validation |
| `CallTelemetryCollector` (impl) | `infrastructure/telemetry/` | Adapter: persists per-call signals |
| `OnlineLearningEngine` (impl) | `infrastructure/learning/` | Adapter: Thompson Sampling / Bayesian updates |
| `BenchmarkEngine` (impl) | `infrastructure/benchmarks/` | Adapter: runs eval suites |
| `AdaptiveRoutingService` | `application/services/` | Orchestrates registry→router→constraints→selection |

---

## 3. Implementation Phases

### Phase 1: Call-Level Telemetry (L5) — Foundation

**Goal:** Instrument every LLM call with structured quality signals. This is the prerequisite for everything else — without measurement data, the learning loop has nothing to learn from.

**Duration:** 1 sprint

#### 1.1 Domain: Call Telemetry Event

```python
# domain/telemetry.py
@dataclass(frozen=True)
class LLMCallTelemetry:
    """Per-call telemetry event — immutable value object."""
    call_id: str                    # UUID
    run_id: str                     # Pipeline run ID
    timestamp: datetime
    # Identity
    model_id: str                   # e.g. "claude-sonnet"
    role: str                       # e.g. "constructive", "scoring"
    preset_id: str                  # e.g. "multi-perspective-budget"
    method: str                     # e.g. "multi-perspective"
    phase: int                      # 0-5
    # Performance
    latency_ms: float               # Wall-clock time
    input_tokens: int
    output_tokens: int
    cost_usd: float
    # Quality (available signals)
    success: bool                   # Non-empty, parseable response
    json_valid: bool | None         # If JSON was expected, did it parse?
    is_fallback: bool               # Was this a fallback call?
    fallback_reason: str | None     # "timeout", "error", "empty"
    circuit_state: str              # "closed", "half_open", "open"
    # Phase-specific quality (filled post-phase)
    critique_score: float | None    # Phase 3 critique score (0-10)
    stress_test_pass: bool | None   # Phase 4 pass/fail
    # Bloc metadata
    vendor: str
    bloc: str                       # "US", "CN", "EU", "OTHER"
```

#### 1.2 Core: Telemetry Collector Port

```python
# core/ports/telemetry_port.py (extend existing)
@runtime_checkable
class CallTelemetryPort(Protocol):
    """Per-call telemetry collection for adaptive routing."""

    async def record_call(self, event: LLMCallTelemetry) -> None: ...

    async def query_model_role_stats(
        self, model_id: str, role: str, window_hours: int = 168
    ) -> ModelRoleStats: ...

    async def query_role_leaderboard(
        self, role: str, window_hours: int = 168, limit: int = 10
    ) -> list[ModelRoleStats]: ...
```

#### 1.3 Infrastructure: SQLite Telemetry Store

```python
# infrastructure/telemetry/call_telemetry_store.py
class SQLiteCallTelemetryStore:
    """Persists per-call telemetry to SQLite for adaptive routing analytics."""

    TABLE = "llm_call_telemetry"

    async def record_call(self, event: LLMCallTelemetry) -> None: ...
    async def query_model_role_stats(...) -> ModelRoleStats: ...
    async def query_role_leaderboard(...) -> list[ModelRoleStats]: ...
```

Schema:
```sql
CREATE TABLE IF NOT EXISTS llm_call_telemetry (
    call_id       TEXT PRIMARY KEY,
    run_id        TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    model_id      TEXT NOT NULL,
    role          TEXT NOT NULL,
    preset_id     TEXT NOT NULL,
    method        TEXT NOT NULL,
    phase         INTEGER NOT NULL,
    latency_ms    REAL NOT NULL,
    input_tokens  INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd      REAL NOT NULL,
    success       INTEGER NOT NULL,
    json_valid    INTEGER,
    is_fallback   INTEGER NOT NULL DEFAULT 0,
    fallback_reason TEXT,
    circuit_state TEXT NOT NULL,
    critique_score REAL,
    stress_test_pass INTEGER,
    vendor        TEXT NOT NULL,
    bloc          TEXT NOT NULL
);

CREATE INDEX idx_telemetry_model_role ON llm_call_telemetry(model_id, role);
CREATE INDEX idx_telemetry_timestamp ON llm_call_telemetry(timestamp);
CREATE INDEX idx_telemetry_role ON llm_call_telemetry(role);
```

#### 1.4 Integration: Instrument ProviderRouter.call()

Modify `ProviderRouter.call()` to emit `LLMCallTelemetry` after every call (success or failure). The telemetry collector is injected via constructor — optional, so existing code paths without ACR continue working.

```python
class ProviderRouter:
    def __init__(
        self,
        primary: BaseLLMProvider,
        routing_table: dict[str, BaseLLMProvider] | None = None,
        fallback_table: dict[str, BaseLLMProvider] | None = None,
        verbose: bool = False,
        cascading_routing: dict[str, list[str]] | None = None,
        on_fallback: "None | (str, str, str, str) -> None" = None,
        telemetry: CallTelemetryPort | None = None,  # NEW — opt-in
    ) -> None:
```

#### 1.5 Prometheus Metrics Extension

Add to `infrastructure/metrics.py`:

```python
LLM_CALL_DURATION = Histogram(
    "reasoner_llm_call_duration_seconds",
    "Per-call LLM latency by model and role",
    ["model", "role", "preset"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

LLM_CALL_SUCCESS = Counter(
    "reasoner_llm_call_success_total",
    "Successful LLM calls by model and role",
    ["model", "role"],
)

LLM_CALL_FAILURE = Counter(
    "reasoner_llm_call_failure_total",
    "Failed LLM calls by model and role",
    ["model", "role", "reason"],
)

LLM_CALL_COST = Counter(
    "reasoner_llm_call_cost_usd_total",
    "Cumulative cost by model and role",
    ["model", "role"],
)
```

#### 1.6 Tests

- Unit: `tests/unit/test_call_telemetry.py` — telemetry event creation, stats aggregation
- Integration: `tests/integration/test_telemetry_store.py` — SQLite read/write/query
- Verify existing `ProviderRouter` tests still pass with `telemetry=None`

#### 1.7 Deliverables

- [ ] `domain/telemetry.py` — `LLMCallTelemetry`, `ModelRoleStats` value objects
- [ ] `core/ports/telemetry_port.py` — `CallTelemetryPort` protocol (extend existing file)
- [ ] `infrastructure/telemetry/call_telemetry_store.py` — SQLite implementation
- [ ] `infrastructure/llm/router.py` — instrument `call()` with optional telemetry
- [ ] `infrastructure/metrics.py` — new per-call Prometheus metrics
- [ ] Tests: unit + integration
- [ ] Migration: `migrations/006_call_telemetry.sql`

---

### Phase 2: Capability Registry (L1) — Model Profiles

**Goal:** Enrich `_MODEL_WHITELIST` with structured capability metadata derived from provider documentation and known benchmarks. No hand-assigned subjective scores.

**Duration:** 1 sprint

#### 2.1 Domain: Model Capability Profile

```python
# domain/model_capabilities.py
@dataclass(frozen=True)
class ModelConstraints:
    """Hard limits — used for filtering, not ranking."""
    max_context_tokens: int
    cost_per_1k_input_usd: float
    cost_per_1k_output_usd: float
    supports_tools: bool
    supports_vision: bool
    supports_streaming: bool
    supports_json_mode: bool
    supports_temperature: bool         # o-series doesn't
    vendor: str                         # "anthropic", "openai", etc.
    bloc: str                           # "US", "CN", "EU", "OTHER"

@dataclass(frozen=True)
class ModelCapabilities:
    """Measured capability scores (0.0–1.0 normalized).
    All values from benchmarks or telemetry — never hand-assigned."""
    scores: dict[str, float]           # e.g. {"reasoning": 0.92, "coding": 0.88}
    source: str                        # "benchmark_v1", "telemetry_7d", "combined"
    measured_at: datetime
    sample_count: int                  # How many datapoints back this profile

@dataclass(frozen=True)
class ModelProfile:
    """Complete model profile: identity + constraints + capabilities."""
    model_id: str
    constraints: ModelConstraints
    capabilities: ModelCapabilities | None   # None = no data yet (cold start)
```

#### 2.2 Core: Capability Registry Port

```python
# core/ports/capability_registry_port.py
@runtime_checkable
class CapabilityRegistryPort(Protocol):
    """Read/write model capability profiles."""

    def get_profile(self, model_id: str) -> ModelProfile | None: ...
    def get_all_profiles(self) -> dict[str, ModelProfile]: ...
    def update_capabilities(
        self, model_id: str, capabilities: ModelCapabilities
    ) -> None: ...
    def get_models_satisfying(
        self, constraints: TaskConstraints
    ) -> list[ModelProfile]: ...
```

#### 2.3 Infrastructure: Registry Implementation

```python
# infrastructure/llm/capability_registry.py
class CapabilityRegistry:
    """In-memory capability registry backed by JSON file for persistence.

    Bootstrap from _MODEL_WHITELIST static facts + benchmark results file.
    Dynamic capabilities updated by telemetry and online learning.
    """
```

Storage: `~/.reasoner/acr/capability_profiles.json`

#### 2.4 Enrich _MODEL_WHITELIST

Extend each entry with constraint metadata. Extract from the existing inline comments (cost, context window) into structured fields:

```python
# Current:
"claude-sonnet": {"model": "anthropic/claude-sonnet-5"},  # $2/$10 per M, 1M ctx

# Enriched:
"claude-sonnet": {
    "model": "anthropic/claude-sonnet-5",
    "constraints": {
        "max_context": 1_000_000,
        "cost_input_per_m": 2.0,
        "cost_output_per_m": 10.0,
        "supports_tools": True,
        "supports_vision": True,
        "supports_json_mode": True,
        "supports_temperature": True,
    },
},
```

This is a mechanical extraction — the cost/context data is already in comments. Move it to structured fields.

#### 2.5 Deliverables

- [ ] `domain/model_capabilities.py` — `ModelConstraints`, `ModelCapabilities`, `ModelProfile`
- [ ] `core/ports/capability_registry_port.py` — `CapabilityRegistryPort` protocol
- [ ] `infrastructure/llm/capability_registry.py` — in-memory + JSON persistence
- [ ] `infrastructure/llm/registry.py` — enrich `_MODEL_WHITELIST` with constraint metadata
- [ ] Script: `scripts/extract_model_constraints.py` — one-time extraction of cost/context from comments
- [ ] Tests: unit (profile creation, constraint filtering)

---

### Phase 3: Task Requirements & Utility Scorer (L3 + L4) — Selection Logic

**Goal:** Define what each pipeline role needs and compute a utility score for model selection.

**Duration:** 1–2 sprints

#### 3.1 Domain: Task Requirement

```python
# domain/task_requirements.py
@dataclass(frozen=True)
class TaskConstraints:
    """Hard filters — model must satisfy ALL to be eligible."""
    min_context_tokens: int = 0
    max_cost_per_1k_output_usd: float = float("inf")
    max_latency_p95_ms: float = float("inf")
    requires_tools: bool = False
    requires_vision: bool = False
    requires_temperature: bool = True    # Excludes o-series by default
    excluded_blocs: frozenset[str] = frozenset()
    excluded_models: frozenset[str] = frozenset()

@dataclass(frozen=True)
class TaskRequirement:
    """What a pipeline role needs — capability weights + hard constraints."""
    role: str                              # e.g. "constructive", "scoring"
    capability_weights: dict[str, float]   # e.g. {"reasoning": 0.8, "creativity": 0.6}
    constraints: TaskConstraints
    priority: float = 1.0                  # Higher = more important to get right
```

#### 3.2 Default Role Requirements

Define requirement vectors for each of the 70+ `_KNOWN_ROUTING_ROLES`. Group by category:

```python
# application/services/role_requirements.py
_ROLE_REQUIREMENTS: dict[str, TaskRequirement] = {
    # ── Perspective generation (Phase 2) ──
    "constructive": TaskRequirement(
        role="constructive",
        capability_weights={"reasoning": 0.7, "creativity": 0.8, "writing": 0.6},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    "destructive": TaskRequirement(
        role="destructive",
        capability_weights={"reasoning": 0.9, "critical_thinking": 0.9, "writing": 0.5},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Scoring (Phase 3) ──
    "scoring": TaskRequirement(
        role="scoring",
        capability_weights={"reasoning": 0.9, "consistency": 0.9, "json_output": 0.8},
        constraints=TaskConstraints(requires_temperature=True),
    ),
    # ── Synthesis (Phase 5) ──
    "synthesis": TaskRequirement(
        role="synthesis",
        capability_weights={"reasoning": 0.9, "writing": 0.9, "long_context": 0.7},
        constraints=TaskConstraints(min_context_tokens=32_000),
    ),
    # ... (all 70+ roles)
}
```

#### 3.3 Application: Utility Scorer

```python
# application/services/utility_scorer.py
class UtilityScorer:
    """Computes utility U(model, task) for model selection.

    U(m, t) = α · capability_match(m, t)
            + β · quality_history(m, t.role)
            + γ · reliability(m)
            - δ · cost_normalized(m)
            - ε · latency_normalized(m)

    Weights α,β,γ,δ,ε are configurable per preset tier:
      - Budget: δ,ε weighted high (cost/latency matter most)
      - Premium: α,β weighted high (quality matters most)
    """

    def __init__(
        self,
        registry: CapabilityRegistryPort,
        telemetry: CallTelemetryPort,
        weights: ScoringWeights | None = None,
    ) -> None: ...

    def score(
        self, model: ModelProfile, requirement: TaskRequirement
    ) -> float: ...

    def rank_models(
        self,
        candidates: list[ModelProfile],
        requirement: TaskRequirement,
    ) -> list[tuple[ModelProfile, float]]: ...
```

#### 3.4 Capability Match Function

```python
def capability_match(
    model_caps: dict[str, float],
    task_weights: dict[str, float],
) -> float:
    """Weighted dot product (not cosine similarity).

    Cosine similarity treats all dimensions equally and only measures
    direction. Weighted dot product lets task requirements emphasize
    specific capabilities — a task that needs reasoning=0.9 and
    creativity=0.2 will strongly prefer models with high reasoning
    regardless of their creativity score.

    Returns 0.0–1.0 normalized.
    """
    if not task_weights:
        return 0.5  # No requirement = neutral score

    total_weight = sum(task_weights.values())
    if total_weight == 0:
        return 0.5

    score = sum(
        weight * model_caps.get(dim, 0.0)
        for dim, weight in task_weights.items()
    )
    return score / total_weight
```

**Design note:** Weighted dot product, not cosine similarity. Cosine measures directional alignment and ignores magnitude — a model scoring 0.3 on everything would have perfect cosine similarity with any uniform requirement vector, despite being mediocre. Weighted dot product penalizes low absolute scores on important dimensions.

#### 3.5 Scoring Weights by Tier

```python
# domain/scoring_weights.py
@dataclass(frozen=True)
class ScoringWeights:
    """Tunable weights for the utility function."""
    capability: float = 0.35       # α
    quality_history: float = 0.30  # β
    reliability: float = 0.15     # γ
    cost_penalty: float = 0.10    # δ
    latency_penalty: float = 0.10  # ε

BUDGET_WEIGHTS = ScoringWeights(
    capability=0.20, quality_history=0.20, reliability=0.15,
    cost_penalty=0.25, latency_penalty=0.20,
)

PREMIUM_WEIGHTS = ScoringWeights(
    capability=0.35, quality_history=0.35, reliability=0.15,
    cost_penalty=0.08, latency_penalty=0.07,
)
```

#### 3.6 Deliverables

- [ ] `domain/task_requirements.py` — `TaskConstraints`, `TaskRequirement`
- [ ] `domain/scoring_weights.py` — `ScoringWeights`, tier presets
- [ ] `application/services/role_requirements.py` — default requirement vectors for all roles
- [ ] `application/services/utility_scorer.py` — `UtilityScorer` with weighted dot product
- [ ] Tests: unit (scoring edge cases, normalization, tie-breaking)

---

### Phase 4: Constraint Checker — Preserving Invariants

**Goal:** Validate model assignments against hard constraints (bloc diversity, budget ceiling, circuit state) AFTER utility scoring.

**Duration:** 1 sprint

#### 4.1 Core: Constraint Protocol

```python
# core/ports/routing_constraint_port.py
@runtime_checkable
class RoutingConstraintPort(Protocol):
    """A constraint that can accept or reject a role→model assignment."""

    def validate(
        self,
        proposed: dict[str, str],   # role → model_id
        preset: PipelinePreset,
    ) -> list[ConstraintViolation]: ...

@dataclass(frozen=True)
class ConstraintViolation:
    constraint_name: str
    role: str
    model_id: str
    reason: str
    severity: Literal["hard", "soft"]  # hard = must fix, soft = warning
```

#### 4.2 Constraint Implementations

```python
# infrastructure/llm/constraints/
├── __init__.py
├── bloc_diversity.py          # Existing invariant: synthesis≠scoring bloc, ≥2 generator blocs
├── budget_ceiling.py          # Total estimated cost ≤ preset tier budget
├── circuit_state.py           # Skip models with open circuit breakers
├── concurrency.py             # Avoid models near concurrency limit
└── no_repeat_lab.py           # Max 60% of roles from one lab (configurable)
```

**Bloc diversity constraint** (extracted from existing preset validation):
```python
class BlocDiversityConstraint:
    """Enforce cross-bloc diversity in model assignments.

    Rules (from Buyl et al., npj AI 2026):
    1. synthesis bloc ≠ scoring bloc
    2. perspective/debate generator roles span ≥2 blocs
    3. No single bloc holds >2 generator roles
    """
```

#### 4.3 Constraint Resolver

```python
# application/services/constraint_resolver.py
class ConstraintResolver:
    """Applies constraints to ranked model lists, finding the best valid assignment.

    Algorithm:
    1. Start with top-utility model for each role
    2. Check all constraints
    3. If violations exist, swap violated role to next-best model
    4. Re-check constraints (max 10 iterations)
    5. If no valid assignment found, fall back to preset's static routing
    """
```

#### 4.4 Deliverables

- [ ] `core/ports/routing_constraint_port.py` — `RoutingConstraintPort`, `ConstraintViolation`
- [ ] `infrastructure/llm/constraints/` — 5 constraint implementations
- [ ] `application/services/constraint_resolver.py` — resolver with backtracking
- [ ] Tests: unit (each constraint), integration (resolver with multiple constraints)

---

### Phase 5: Adaptive Router Service — Orchestration

**Goal:** Wire everything together into an `AdaptiveRoutingService` that sits between `PipelineOrchestrator` and `ProviderRouter`.

**Duration:** 1–2 sprints

#### 5.1 Application: AdaptiveRoutingService

```python
# application/services/adaptive_routing.py
class AdaptiveRoutingService:
    """Orchestrates adaptive model selection for pipeline runs.

    Modes:
    - SHADOW: Logs what ACR would select alongside static preset routing.
              No impact on actual routing. Used for validation.
    - ADVISORY: ACR selects, but preset overrides win on conflict.
    - ADAPTIVE: ACR selects, constraints validate, preset is fallback only.
    """

    def __init__(
        self,
        registry: CapabilityRegistryPort,
        scorer: UtilityScorer,
        resolver: ConstraintResolver,
        telemetry: CallTelemetryPort,
        mode: Literal["shadow", "advisory", "adaptive"] = "shadow",
    ) -> None: ...

    async def select_routing_table(
        self,
        preset: PipelinePreset,
        roles: list[str],
    ) -> dict[str, str]:
        """Select optimal model for each role.

        Returns:
            role → model_id mapping (same shape as preset.routing)
        """
        # 1. Get requirements for each role
        requirements = [get_requirement(role) for role in roles]

        # 2. For each role, get eligible models (constraint filtering)
        for req in requirements:
            candidates = self.registry.get_models_satisfying(req.constraints)

            # 3. Score each candidate
            ranked = self.scorer.rank_models(candidates, req)

        # 4. Resolve constraints across the full assignment
        assignment = self.resolver.resolve(ranked_per_role, preset)

        # 5. Apply mode logic
        if self.mode == "shadow":
            self._log_shadow_comparison(assignment, preset.routing)
            return preset.routing  # Use static routing
        elif self.mode == "advisory":
            return self._merge_advisory(assignment, preset.routing)
        else:
            return assignment
```

#### 5.2 Integration Point: PipelineOrchestrator

```python
# application/orchestrator.py — modify build_router() to optionally use ACR
class PipelineOrchestrator:
    async def _build_router(self, preset: PipelinePreset, state: PipelineState) -> ProviderRouter:
        """Build the ProviderRouter, optionally with ACR-selected routing."""
        if self.adaptive_routing and self.adaptive_routing.mode != "shadow":
            roles = list(preset.routing.keys())
            adaptive_table = await self.adaptive_routing.select_routing_table(preset, roles)
            # Merge: ACR selections + preset fallbacks
            merged_routing = {**preset.routing, **adaptive_table}
        else:
            merged_routing = preset.routing
        # ... existing ProviderRouter construction
```

#### 5.3 Configuration

```python
# core/settings.py — add ACR settings
class Settings(BaseSettings):
    # ... existing settings ...

    # ACR (Adaptive Capability Router)
    ACR_ENABLED: bool = False
    ACR_MODE: Literal["shadow", "advisory", "adaptive"] = "shadow"
    ACR_EXPLORATION_RATE_BUDGET: float = 0.15     # 15% explore for budget presets
    ACR_EXPLORATION_RATE_PREMIUM: float = 0.05    # 5% explore for premium presets
    ACR_TELEMETRY_DB: str = "~/.reasoner/acr/telemetry.db"
    ACR_PROFILES_PATH: str = "~/.reasoner/acr/capability_profiles.json"
    ACR_BENCHMARK_WARMUP_CALLS: int = 50          # Min calls before model enters adaptive pool
```

#### 5.4 API: ACR Admin Endpoints

```python
# api/routes/admin.py — extend with ACR management
@router.get("/admin/acr/status")
async def acr_status(): ...          # Current mode, model count, telemetry volume

@router.get("/admin/acr/leaderboard/{role}")
async def acr_leaderboard(role: str): ...   # Top models for a role

@router.get("/admin/acr/profile/{model_id}")
async def acr_profile(model_id: str): ...   # Model's capability profile

@router.post("/admin/acr/mode")
async def acr_set_mode(mode: str): ...      # Switch shadow/advisory/adaptive
```

#### 5.5 Deliverables

- [ ] `application/services/adaptive_routing.py` — `AdaptiveRoutingService`
- [ ] `application/orchestrator.py` — integration hook for ACR
- [ ] `core/settings.py` — ACR configuration fields
- [ ] `api/routes/admin.py` — ACR admin endpoints
- [ ] Tests: unit (mode logic, shadow vs adaptive), integration (end-to-end selection)

---

### Phase 6: Online Learning Engine (L6) — Closing the Loop

**Goal:** Automatically update model capability profiles based on production telemetry.

**Duration:** 1–2 sprints

#### 6.1 Thompson Sampling Implementation

```python
# infrastructure/learning/thompson_sampler.py
class ThompsonSampler:
    """Bayesian model selection with explore/exploit balance.

    Each (model, role) pair maintains a Beta distribution:
      Beta(α=successes+1, β=failures+1)

    Selection:
    1. Sample from each model's posterior
    2. Select model with highest sample
    3. New models have wide posteriors (α=1, β=1) → sampled more often

    This naturally handles:
    - Cold start: new models explored via posterior uncertainty
    - Convergence: proven models exploited as posterior narrows
    - Non-stationarity: decay old observations via sliding window
    """
```

#### 6.2 Quality Signal Aggregation

```python
# infrastructure/learning/quality_signals.py
class QualitySignalAggregator:
    """Converts raw telemetry into quality scores for learning.

    Signal hierarchy (by availability and cost):
    1. Completion success — every call, free
    2. JSON validity — every call expecting JSON, free
    3. Latency relative to peers — every call, free
    4. Phase-3 critique score — orchestrated pipelines, already computed
    5. Stress test pass rate — orchestrated pipelines, already computed
    6. LLM critic evaluation — sampled 10%, ~$0.002/eval
    7. User thumbs up/down — rare, high-value correction

    Composite score = weighted blend of available signals.
    """

    def compute_reward(self, telemetry: LLMCallTelemetry) -> float:
        """Convert a telemetry event into a 0.0–1.0 reward signal."""
        score = 0.0
        weight_sum = 0.0

        # Always available
        score += 0.3 * (1.0 if telemetry.success else 0.0)
        weight_sum += 0.3

        if telemetry.json_valid is not None:
            score += 0.15 * (1.0 if telemetry.json_valid else 0.0)
            weight_sum += 0.15

        # Phase-specific (when available)
        if telemetry.critique_score is not None:
            score += 0.35 * (telemetry.critique_score / 10.0)
            weight_sum += 0.35

        if telemetry.stress_test_pass is not None:
            score += 0.20 * (1.0 if telemetry.stress_test_pass else 0.0)
            weight_sum += 0.20

        return score / weight_sum if weight_sum > 0 else 0.5
```

#### 6.3 Learning Loop

```python
# infrastructure/learning/online_learner.py
class OnlineLearner:
    """Updates capability profiles from telemetry using Thompson Sampling.

    Runs as a background task — processes new telemetry in batches.
    Updates CapabilityRegistry with fresh capability scores.
    """

    async def process_batch(self, events: list[LLMCallTelemetry]) -> None:
        """Process a batch of telemetry events and update model profiles."""
        for event in events:
            reward = self.signal_aggregator.compute_reward(event)
            self.sampler.update(event.model_id, event.role, reward)

        # Periodically export updated profiles to registry
        if self._should_export():
            updated = self.sampler.export_capabilities()
            for model_id, caps in updated.items():
                self.registry.update_capabilities(model_id, caps)
```

#### 6.4 Exploration Budget

```python
# infrastructure/learning/exploration.py
class ExplorationPolicy:
    """Controls how much exploration vs exploitation.

    Budget presets: 15% explore (users accept cost-optimized routing)
    Premium presets: 5% explore (users paying more get less experimentation)
    Benchmark warmup: 50 calls minimum before model enters adaptive pool

    Exploration decreases automatically as posterior narrows (Thompson Sampling).
    This policy adds a hard floor to ensure minimum exploration.
    """
```

#### 6.5 Deliverables

- [ ] `infrastructure/learning/thompson_sampler.py` — Thompson Sampling with Beta posteriors
- [ ] `infrastructure/learning/quality_signals.py` — reward signal aggregation
- [ ] `infrastructure/learning/online_learner.py` — batch learning loop
- [ ] `infrastructure/learning/exploration.py` — exploration budget policy
- [ ] Background task registration in app startup
- [ ] Tests: unit (sampler convergence, reward computation), integration (full learning loop)

---

### Phase 7: Benchmark Engine (L7) — Capability Bootstrap

**Goal:** Periodic benchmark suites that establish baseline capability profiles for models, especially new ones with no production telemetry.

**Duration:** 2 sprints

#### 7.1 Benchmark Suite Design

```python
# infrastructure/benchmarks/
├── __init__.py
├── engine.py                  # BenchmarkEngine orchestrator
├── suites/
│   ├── reasoning.py           # Logic puzzles, multi-step inference
│   ├── coding.py              # Code generation + review tasks
│   ├── writing.py             # Composition quality, style adherence
│   ├── json_fidelity.py       # Structured output compliance
│   ├── long_context.py        # Needle-in-haystack, summarization
│   ├── multilingual.py        # Cross-language accuracy
│   ├── consistency.py         # Same prompt N times → variance
│   └── critical_thinking.py   # Argument analysis, fallacy detection
└── runner.py                  # Async benchmark runner with rate limiting
```

#### 7.2 Benchmark Lifecycle

```
Model added/updated in _MODEL_WHITELIST
         │
         ▼
   Benchmark warmup triggered (50 eval calls per suite)
         │
         ▼
   Results stored in capability_profiles.json
         │
         ▼
   Model enters adaptive selection pool
         │
   ┌─────┴──────────────────┐
   │  Periodic re-eval      │  (weekly cron or on model version change)
   │  ── detect capability  │
   │     drift              │
   └────────────────────────┘
```

#### 7.3 Cost Control

Benchmarks cost real money (LLM calls). Budget controls:

```python
BENCHMARK_BUDGET = {
    "per_model_warmup_usd": 2.00,       # Max $2 to bootstrap one model
    "weekly_reeval_usd": 5.00,           # Max $5/week for all re-evals
    "calls_per_suite": 10,               # 10 eval calls per suite per model
    "suites_per_model": 8,               # 8 suites = 80 calls total
    "use_cheapest_judge": True,          # Use budget model as benchmark judge
}
```

#### 7.4 Deliverables

- [ ] `infrastructure/benchmarks/engine.py` — `BenchmarkEngine` orchestrator
- [ ] `infrastructure/benchmarks/suites/` — 8 benchmark suites
- [ ] `infrastructure/benchmarks/runner.py` — async runner with rate limiting and cost caps
- [ ] CLI: `python main.py --benchmark <model_id>` — manual benchmark trigger
- [ ] Cron/scheduled task for periodic re-evaluation
- [ ] Tests: unit (suite scoring), integration (engine with mock LLM)

---

## 4. Migration Strategy

### 4.1 Progressive Rollout

```
Week 1-2:  Phase 1 — Telemetry (shadow, no routing impact)
Week 3-4:  Phase 2 — Registry enrichment (data only)
Week 5-7:  Phase 3 — Scorer + Requirements (shadow comparison logs)
Week 8-9:  Phase 4 — Constraints (validate existing presets)
Week 10-12: Phase 5 — Router service (shadow mode production)
Week 13-15: Phase 6 — Learning (accumulate data in shadow)
Week 16+:  Phase 7 — Benchmarks (bootstrap new models)

After 4+ weeks of shadow data:
  → Switch to ADVISORY mode (ACR suggests, preset overrides)
After 8+ weeks of advisory validation:
  → Switch to ADAPTIVE mode (ACR selects, constraints validate)
```

### 4.2 Rollback Plan

Each phase is independently revertable:
- **Phase 1**: Set `telemetry=None` in ProviderRouter constructor
- **Phase 2**: Registry enrichment is additive; old code ignores new fields
- **Phase 3-5**: Set `ACR_ENABLED=false` or `ACR_MODE=shadow`
- **Phase 6**: Stop background learning task; registry retains last-known-good profiles
- **Phase 7**: Benchmarks are independent jobs; stopping them has no runtime impact

### 4.3 Feature Flags

```python
# All ACR behavior gated behind settings:
ACR_ENABLED = False           # Master switch
ACR_MODE = "shadow"           # shadow | advisory | adaptive
ACR_TELEMETRY_ENABLED = True  # Can collect telemetry without routing changes
ACR_LEARNING_ENABLED = False  # Online learning separate from telemetry
ACR_BENCHMARKS_ENABLED = False # Benchmark engine separate from learning
```

---

## 5. Observability

### 5.1 Dashboards

- **ACR Shadow Comparison**: How often does ACR agree with preset routing? Which roles diverge most?
- **Model Leaderboard**: Per-role performance ranking over time
- **Exploration Budget**: How much exploration is happening? Is it converging?
- **Cost Impact**: Estimated cost difference if ACR had been active vs static routing

### 5.2 Alerts

- ACR selects a model that then fails → review constraint checker
- Exploration rate exceeds budget → throttle
- Model capability drift detected → trigger re-benchmark
- Learning loop stalled (no updates in 24h) → investigate

### 5.3 Logging

Every ACR decision logged with:
```json
{
    "event": "acr_selection",
    "mode": "shadow",
    "role": "constructive",
    "preset_model": "deepseek-v3",
    "acr_model": "qwen3.7-plus",
    "acr_score": 0.847,
    "preset_score": 0.791,
    "reason": "higher quality_history for constructive role",
    "constraints_passed": true
}
```

---

## 6. File Structure (Final)

```
src/reasoner/
├── domain/
│   ├── model_capabilities.py       # ModelConstraints, ModelCapabilities, ModelProfile
│   ├── task_requirements.py        # TaskConstraints, TaskRequirement
│   ├── scoring_weights.py          # ScoringWeights, tier presets
│   └── telemetry.py                # LLMCallTelemetry, ModelRoleStats
├── core/ports/
│   ├── capability_registry_port.py # CapabilityRegistryPort
│   ├── routing_constraint_port.py  # RoutingConstraintPort, ConstraintViolation
│   └── telemetry_port.py           # CallTelemetryPort (extend existing)
├── application/services/
│   ├── adaptive_routing.py         # AdaptiveRoutingService
│   ├── constraint_resolver.py      # ConstraintResolver
│   ├── role_requirements.py        # Default requirement vectors
│   └── utility_scorer.py           # UtilityScorer
├── infrastructure/
│   ├── llm/
│   │   ├── capability_registry.py  # CapabilityRegistry impl
│   │   └── constraints/            # 5 constraint implementations
│   ├── telemetry/
│   │   └── call_telemetry_store.py # SQLite telemetry store
│   ├── learning/
│   │   ├── thompson_sampler.py     # Thompson Sampling
│   │   ├── quality_signals.py      # Reward aggregation
│   │   ├── online_learner.py       # Batch learning loop
│   │   └── exploration.py          # Exploration budget
│   └── benchmarks/
│       ├── engine.py               # BenchmarkEngine
│       ├── runner.py               # Async runner
│       └── suites/                 # 8 benchmark suites
└── migrations/
    └── 006_call_telemetry.sql      # Telemetry table
```

---

## 7. Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Shadow agreement rate | >70% (ACR agrees with preset routing) | ACR logs |
| Quality improvement | +5% critique scores in advisory mode | A/B comparison |
| Cost reduction | -10% average cost in budget presets | Telemetry aggregation |
| Fallback rate | -20% (fewer fallbacks needed) | Prometheus counters |
| Cold start time | <80 benchmark calls to usable profile | Benchmark engine logs |
| Learning convergence | Posterior σ < 0.1 within 200 calls | Thompson Sampler stats |
| Zero regressions | All existing preset tests pass | CI gate |

---

## 8. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Telemetry volume overwhelms SQLite | Slow queries, disk growth | Retention policy: 30 days, vacuum weekly |
| Thompson Sampling oscillates (non-stationary) | Unstable routing | Sliding window (7 days), prior decay |
| Benchmark costs exceed budget | Unexpected spend | Hard per-model and per-week cost caps |
| ACR selects models that break cross-bloc invariant | Ideological bias in output | Constraint checker runs AFTER scoring, hard-blocks violations |
| Learning loop has insufficient signal | No convergence | Start with free signals only (success, latency, JSON validity); add expensive signals later |
| Model capability drift between benchmarks | Stale profiles | Weekly re-eval + telemetry drift detection |
| Exploration annoys premium users | Suboptimal results during explore | 5% explore ceiling for premium; warmup gate prevents truly untested models |

---

## 9. Dependencies

- **No new external dependencies** — Thompson Sampling, weighted dot product, Beta distribution all implementable with Python stdlib (`random`, `math`)
- **SQLite** — already used for event store; telemetry uses separate DB file
- **Prometheus** — already integrated; only new metric definitions
- **Existing infrastructure** — `circuit_breaker.py`, `bloc_of()`, `_VENDOR_BLOC` reused directly
