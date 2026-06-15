<!-- Generated: 2026-06-15 | Files scanned: 385 | Token estimate: ~700 -->

# Data Models — Reasoner

> Domain models, events, database schemas, and type systems.

## PipelineState (~60 fields)

**Canonical state model** in `domain/pipeline_state.py`

### Core Execution Fields

```python
@dataclass
class PipelineState:
    # Input
    problem: str
    enhanced_problem: str
    
    # Classification (Phase 0 output)
    task_type: TaskType | None  # RESEARCH, CODING, MATH, ANALYSIS, CREATIVE, etc.
    task_type_rationale: str
    language: str  # Detected language
    complexity: str | None  # simple, medium, complex
    
    # Decomposition (Phase 1 output)
    decomposition: Decomposition | None
    
    # Generation (Phase 2 output)
    candidates: list[SolutionCandidate]
    
    # Critique (Phase 3 output)
    scores: list[CritiqueScore]
    top_candidates: list[SolutionCandidate]
    
    # Stress Testing (Phase 4 output)
    stress_results: list[StressTestResult]
    
    # Synthesis (Phase 5 output)
    final_solution: FinalSolution | None
    
    # Errors
    errors: list[str]
    attachments: list[dict[str, Any]]
```

### Sub-Container Models

```python
@dataclass
class MethodState:
    """Generic container for method-specific phase data."""
    data: dict[str, Any] = field(default_factory=dict)
    # Access: method_state.get("debate") → dict | {}
    # Set: method_state.set("debate", {...})

@dataclass
class CostTrackingState:
    total_cost_usd: float = 0.0
    phase_costs: dict[str, float] = field(default_factory=dict)
    detailed_token_usage: dict[str, dict[str, int]] = field(default_factory=dict)
    phase_costs_by_key: dict[str, float] = field(default_factory=dict)

@dataclass
class ConversationState:
    """Multi-turn conversation context."""
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    conversation_id: str = ""
    turn_number: int = 1
    previous_synthesis: str = ""
    agent_model: str | None = None

@dataclass
class PipelineCore:
    """Fields every phase reads during execution."""
    problem: str = ""
    enhanced_problem: str = ""
    task_type: TaskType | None = None
    language: str = "English"
    complexity: str | None = None
    decomposition: Decomposition | None = None
    candidates: list[SolutionCandidate] = field(default_factory=list)
    # ... more fields

@dataclass
class PipelineMeta:
    """Metadata: write-only during execution, read-only after."""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    phase_logs: list[str] = field(default_factory=list)
    phase_tokens: dict[str, dict[str, int]] = field(default_factory=dict)
    phase_durations: dict[str, float] = field(default_factory=dict)
```

### Critical Invariants

- **Method-specific state uses dict, never direct subscript:** Always use `.get(method)`, enables `--resume` with older state files
- **All LLM responses parsed via `parsing.extract_json()`:** Never direct `json.loads()`
- **Costs tracked cumulatively:** `phase_costs` dict, total updated after each LLM call
- **Immutable after Phase 5:** State is frozen, only read for postflight tasks

## Domain Types

### Core Types (`domain/core_types.py`)

```python
@dataclass
class SolutionCandidate:
    """A perspective/solution generated in Phase 2."""
    perspective_type: PerspectiveType  # constructive, destructive, systemic, minimalist
    content: str
    source_model: str
    reasoning_depth: str | None
    confidence: float  # 0-1

@dataclass
class CritiqueScore:
    """Critique score (Phase 3)."""
    candidate_id: str | int
    score: float  # 0-10
    rationale: str
    scorer_model: str
    scoring_method: str

@dataclass
class StressTestResult:
    """Stress test scenario outcome (Phase 4)."""
    scenario_type: ScenarioType  # optimal, constraint_violation, adversarial
    description: str
    outcome: str
    resilience_score: float  # 0-1

@dataclass
class FinalSolution:
    """Synthesis output (Phase 5)."""
    solution: str
    epistemic_label: ClaimLabel  # VERIFIED, HYPOTHESIS, UNKNOWN
    confidence: float  # 0-1
    action_blueprint: list[str]  # Actionable steps
    sources: list[str]  # Citations (if applicable)
    meta_cognition: str  # Reasoning about confidence

@dataclass
class Decomposition:
    """Phase 1 decomposition output."""
    sub_problems: list[str]
    failure_modes: list[str]
    key_assumptions: list[str]

@dataclass
class GenerationCandidate:
    """ORCHESTRATED method specific."""
    perspective_type: PerspectiveType
    content: str
    source_model: str

@dataclass
class CriticScore:
    """ORCHESTRATED method specific."""
    candidate_index: int
    score: float
    feedback: str

@dataclass
class VerificationResult:
    """ORCHESTRATED method specific."""
    is_verified: bool
    confidence: float
    evidence: str

@dataclass
class MetaEvaluation:
    """ORCHESTRATED method specific."""
    overall_confidence: float
    reasoning_quality: str
    epistemic_assessment: str
```

### Models (`domain/models.py`)

```python
class TaskType(str, Enum):
    RESEARCH = "research"
    CODING = "coding"
    MATH = "math"
    ANALYSIS = "analysis"
    CREATIVE = "creative"
    BRAINSTORMING = "brainstorming"
    STRATEGIC = "strategic"
    # ... more types

class ClaimLabel(str, Enum):
    VERIFIED = "verified"
    HYPOTHESIS = "hypothesis"
    UNKNOWN = "unknown"

class PerspectiveType(str, Enum):
    CONSTRUCTIVE = "constructive"
    DESTRUCTIVE = "destructive"
    SYSTEMIC = "systemic"
    MINIMALIST = "minimalist"

class ScenarioType(str, Enum):
    OPTIMAL = "optimal"
    CONSTRAINT_VIOLATION = "constraint_violation"
    ADVERSARIAL = "adversarial"

class PerspectiveRegistry:
    """Registry of available perspectives by method."""
    # Maps method name → list of perspective types
```

## Domain Events

**Location:** `core/events/domain_events.py`

### Event Types (18 total)

**Pipeline Lifecycle:**
- `PIPELINE_STARTED` — Execution begins
- `PHASE_STARTED` — Phase N begins
- `PHASE_COMPLETED` — Phase N finishes, state snapshot saved
- `PHASE_FAILED` — Phase N fails, error logged
- `PIPELINE_COMPLETED` — Full pipeline done
- `PIPELINE_FAILED` — Pipeline error, recovery queued

**Reasoning Operations:**
- `PERSPECTIVE_GENERATED` — Perspective I generated
- `CANDIDATE_SCORED` — Candidate scored 0-10
- `STRESS_TEST_COMPLETED` — Stress test scenario done
- `CONTEXT_FETCHED` — RAG context retrieved
- `CONTEXT_VETTED` — Context validated
- `SOURCE_ADDED` — Research source cited
- `LLM_GENERATION_COMPLETED` — LLM call completed
- `RESEARCH_STEP_EMITTED` — Research sub-step done
- `RESEARCH_CITATIONS_READY` — Sources ready

**Widget & Memory:**
- `WIDGET_DETECTED`, `WIDGET_EXECUTED`, `WIDGET_FAILED`
- `MEMORY_STORED`, `MEMORY_RECALLED`

**SaaS & Billing:**
- `USER_REGISTERED`, `USER_LOGGED_IN`
- `SUBSCRIPTION_CREATED`, `SUBSCRIPTION_UPDATED`, `SUBSCRIPTION_CANCELLED`
- `QUERY_LOGGED`, `QUOTA_EXCEEDED`, `QUOTA_RESET`
- `PAYMENT_SUCCEEDED`, `PAYMENT_FAILED`

### Event Structure

```python
@dataclass(frozen=True)
class DomainEvent:
    event_type: PipelineEventType | WidgetEventType | MemoryEventType | SaaSEventType
    timestamp: datetime
    aggregate_id: str  # Pipeline ID or user ID
    data: dict[str, Any]
    
    # Optional
    user_id: str | None = None
    session_id: str | None = None
    causation_id: str | None = None  # Parent event
```

### Event Factory

```python
def make_event(
    event_type: str,
    aggregate_id: str,
    data: dict[str, Any],
    user_id: str | None = None
) -> DomainEvent:
    """Create a domain event with automatic timestamp."""
    return DomainEvent(
        event_type=PipelineEventType(event_type),
        timestamp=datetime.now(timezone.utc),
        aggregate_id=aggregate_id,
        data=data,
        user_id=user_id
    )
```

## Database Schemas

### SQLite (Event Store)

**Events Table:**
```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    user_id TEXT,
    timestamp DATETIME NOT NULL,
    data JSONB NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX (aggregate_id, timestamp)
);
```

**Snapshots Table:**
```sql
CREATE TABLE snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aggregate_id TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL,
    state JSONB NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX (aggregate_id)
);
```

### PostgreSQL (Optional, Production)

**Query Audit Logs:**
```sql
CREATE TABLE query_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    conversation_id TEXT,
    problem TEXT,
    preset_id TEXT,
    cost_usd DECIMAL(10, 4),
    tokens_used INTEGER,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX (user_id, created_at)
);
```

**User Settings:**
```sql
CREATE TABLE user_settings (
    user_id TEXT PRIMARY KEY,
    subscription_tier TEXT,  -- free, starter, pro, enterprise
    quota_monthly INTEGER,
    quota_remaining INTEGER,
    last_quota_reset TIMESTAMP,
    preferences JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**API Keys:**
```sql
CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,  -- Hashed for security
    name TEXT,
    last_used TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    revoked_at TIMESTAMP,
    INDEX (user_id)
);
```

## Preset Configuration

**Location:** `domain/preset_registry.py`

```python
@dataclass
class PipelinePreset:
    id: str  # e.g., "debate-budget"
    name: str  # e.g., "Debate (Budget)"
    description: str
    primary_id: str  # Default model
    routing: dict[str, str]  # role → model name
    fallback_routing: dict[str, str]  # role → fallback model
    tier: str  # budget, premium, balanced, experimental
    notes: list[str]  # Implementation notes
    
    # Optional parameters
    top_k: int = 2
    parallel_perspectives: bool = True
    enhance_prompt: bool = True
    skip_stress_test: bool = False
    skip_deep_read: bool = False
```

### Routing Roles

| Role | Purpose | Default (Budget) |
|------|---------|------------------|
| `prompt_enhancement` | Clarity rewrite | Gemini Flash Lite |
| `classification` | Task type detection | GPT-5-mini |
| `decomposition` | Sub-problem breakdown | DeepSeek V3 |
| `constructive` | Positive perspective | Gemini Flash Lite |
| `destructive` | Critical perspective | Mistral Small |
| `systemic` | Systems-thinking | GLM-5.1 |
| `minimalist` | Concise perspective | Ministral-3B |
| `scoring` | Independent critique | Qwen 3.5-Flash |
| `stress_testing` | Adversarial scenarios | Mistral Small |
| `synthesis` | Final integration | Qwen 3.7-Max |

## TypeScript Interfaces (Frontend)

```typescript
interface Message {
  id: string
  conversationId: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  phase?: number
  metadata?: Record<string, any>
}

interface Phase {
  number: 0 | 1 | 2 | 3 | 4 | 5
  name: string
  status: 'pending' | 'running' | 'completed' | 'error'
  duration?: number
  output?: Record<string, any>
  error?: string
}

interface Preset {
  id: string
  name: string
  method: string
  tier: 'budget' | 'premium' | 'balanced' | 'experimental'
  estimatedCost: number
  description: string
}

interface PipelineState {
  problem: string
  enhancedProblem: string
  taskType: string | null
  language: string
  complexity: 'simple' | 'medium' | 'complex' | null
  phases: Phase[]
  finalSolution?: {
    solution: string
    epistemicLabel: 'VERIFIED' | 'HYPOTHESIS' | 'UNKNOWN'
    confidence: number
    actionBlueprint: string[]
  }
  cost: number
  totalTokens: number
  startedAt: Date
  completedAt?: Date
}

interface Quota {
  monthly: number
  remaining: number
  resetDate: Date
  tier: 'free' | 'starter' | 'pro' | 'enterprise'
}
```

## Key Invariants

1. **Immutability:** State never mutated in-place, always new object on update
2. **Event ordering:** Events append-only, ordered by timestamp
3. **Cost accumulation:** Costs tracked per phase, summed at end
4. **State versioning:** Snapshots periodically saved for fast recovery
5. **Type safety:** All domain objects have explicit types (Pydantic models or TypeScript interfaces)

## Validation Rules

**Input Validation:**
- `problem`: 1-50,000 characters
- `preset`: Must exist in registry
- `task_type`: Must be valid TaskType enum value

**Phase Outputs:**
- `candidates`: At least 1 per phase 2
- `scores`: At most 1 per candidate
- `final_solution`: Required before phase 5 complete
