# God-Node Decoupling — Implementation Plan

Date: 2026-05-08
Author: SRE Analysis
Status: Draft

---

## Summary

The knowledge graph analysis identified 3 architectural bottleneck nodes (god objects)
with disproportionately high edge counts:

| God Node | Current Edges | Target After Decoupling | Current Files |
|---|---|---|---|
| `PipelineState` | 267 | ~76 (across 5 containers) | `models.py`, 30+ mixins/renderers |
| `EventType` | 164 | ~41 (4 sub-enums) | `domain_events.py`, event bus, handlers |
| `PerspectiveType` | 111 | ~28 (registry-based) | `models.py`, 4 mixins, 2 renderers |

Each phase is designed to be **safe, revertible, and independently testable.**
Zero consumer changes required — backward-compatible property aliases surface
the new internals transparently.

---

## Phase 0: Consumer Map

### PipelineState consumers (30+ files)
- `api/` — serializers.py, streaming.py, routes/context.py
- `application/flows/` — pipeline_flow.py
- `application/mixins/` — article_pipeline, brainstorming, coding, cognitive, debate,
  delphi, dialectical, jury, perspective, recovery, research, search, writing, _protocol
- `application/services/renderers/` — all 12 method renderers
- `application/event_bus/` — handlers
- `application/handlers/` — handlers.py

### EventType consumers (4 files)
- `api/streaming.py` — event creation in all pipeline phases
- `core/events/domain_events.py` — enum + EVENT_CLASSES map
- `application/event_bus/bus.py` — subscription + dispatch
- `application/handlers/handlers.py` — event generation

### PerspectiveType consumers (6 files)
- `application/mixins/article_pipeline.py` — `PerspectiveType.CONSTRUCTIVE`
- `application/mixins/coding_pipeline.py` — `PerspectiveType.CONSTRUCTIVE`
- `application/mixins/cognitive_mixin.py` — `PerspectiveType.CONSTRUCTIVE` (5 locations)
- `application/mixins/perspective_mixin.py` — `PerspectiveType(p_name)` coercion
- `application/mixins/writing_mixin.py` — `PerspectiveType.CONSTRUCTIVE`
- `application/services/renderers/_render_debate.py` — CONSTRUCTIVE/DESTRUCTIVE comparison
- `application/services/renderers/_shared.py` — import
- `core/perspectives.py` — documentation reference

---

## Phase 1: PerspectiveType → Runtime Registry

**Goal:** Make perspectives extensible without enum changes.
**Risk:** Low (6 files, fast enum, no serialization).
**Time:** 2 hours.

### Step 1.1 — Add `PerspectiveRegistry` class

File: `src/reasoner/models.py`

```python
from functools import lru_cache

class PerspectiveRegistry:
    """Runtime-validatable registry of perspective types.

    Enum constants remain for backward compat, but validation
    is deferred to the registry so new perspectives can be
    registered at startup without modifying the enum.
    """
    _known: dict[str, str] = {
        "constructive": "Constructive analysis",
        "destructive":   "Destructive critique",
        "systemic":      "Systemic view",
        "minimalist":    "Minimalist approach",
    }

    @classmethod
    def register(cls, name: str, description: str) -> None:
        """Register a new perspective at runtime."""
        cls._known[name] = description

    @classmethod
    @lru_cache(maxsize=64)
    def validate(cls, value: str) -> bool:
        return value.lower() in cls._known

    @classmethod
    def coerce(cls, value: str) -> PerspectiveType | str:
        """Coerce to enum if possible, otherwise return the registered string."""
        try:
            return PerspectiveType(value)
        except ValueError:
            if cls.validate(value):
                return value
            raise ValueError(f"Unknown perspective: {value}")

    @classmethod
    def list_all(cls) -> list[str]:
        return list(cls._known.keys())
```

### Step 1.2 — Add `__post_init__` to `SolutionCandidate` + `CritiqueScore`

```python
@dataclass
class SolutionCandidate:
    # ... existing fields unchanged
    def __post_init__(self):
        if isinstance(self.perspective, str):
            self.perspective = PerspectiveRegistry.coerce(self.perspective)
```

### Step 1.3 — Update `_parse_critique_scores` in `parsing.py`

Change:
```python
perspective=PerspectiveType(s["perspective"])
```
To:
```python
perspective=PerspectiveRegistry.coerce(s["perspective"])
```

### Step 1.4 — Tests

File: `tests/test_perspective_registry.py`

```
test_known_perspectives_validate()      — constructive, destructive pass
test_runtime_registered_perspective()   — "financial" registered → validates
test_unknown_perspective_rejected()     — "nonexistent" fails validation
test_enum_still_works()                 — PerspectiveType.CONSTRUCTIVE still valid
test_coerce_runtime_perspective()       — coerce returns string for registered-only
```

### Rollback
Delete `PerspectiveRegistry` class. Restore `PerspectiveType(s["perspective"])`.
Enum values unchanged. **Full revert: 1 `git revert` commit.**

### Verification Gate
```bash
python -m pytest tests/test_perspective_registry.py -v  # new tests
python -m pytest -x -q --timeout=30 -n auto               # full suite, no regressions
```

---

## Phase 2: MethodState Dict Wrapper — Eliminate 19 Named Fields

**Goal:** Replace 19 method-specific fields on `PipelineState` with a single
`dict[str, Any]`. New methods added via `state.method_state["new"] = {}` —
no dataclass field additions.
**Risk:** Medium (30+ consumers, property aliases absorb the change).
**Time:** 4 hours.

### Step 2.1 — Add `MethodState` Container

File: `src/reasoner/models.py`

```python
@dataclass
class MethodState:
    """Generic container for method-specific phase data.

    Replace 19 named PipelineState fields (jury_guidelines, debate_rounds,
    scientific_state, ...) with a single dict indexed by method name.
    """
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, method: str) -> dict[str, Any]:
        v = self.data.get(method)
        return v if isinstance(v, dict) else {}

    def set(self, method: str, state: dict[str, Any]) -> None:
        self.data[method] = state
```

In `PipelineState.__init__`:
```python
method_state: MethodState = field(default_factory=MethodState)
```

### Step 2.2 — Add Backward-Compatible Property Aliases

For each of the 19 method fields, add a `@property` / `@.setter` pair
that transparently delegates to `self.method_state`.

Mapping:

| Field Name | Method Key | Data Key |
|---|---|---|
| `jury_guidelines` | `jury` | `guidelines` |
| `debate_rounds` | `debate` | `rounds` |
| `scientific_state` | `scientific` | (entire value) |
| `socratic_state` | `socratic` | (entire value) |
| `jury_weighted_ranking` | `jury` | `weighted_ranking` |
| `pre_mortem_state` | `pre_mortem` | (entire value) |
| `bayesian_state` | `bayesian` | (entire value) |
| `dialectical_state` | `dialectical` | (entire value) |
| `analogical_state` | `analogical` | (entire value) |
| `delphi_state` | `delphi` | (entire value) |
| `cove_state` | `cove` | (entire value) |
| `sot_state` | `sot` | (entire value) |
| `tot_state` | `tot` | (entire value) |
| `pot_state` | `pot` | (entire value) |
| `self_discover_state` | `self_discover` | (entire value) |
| `writing_state` | `writing` | (entire value) |
| `coding_state` | `coding` | (entire value) |
| `brainstorming_state` | `brainstorming` | (entire value) |
| `cross_language_state` | `cross_language` | (entire value) |

Example (applies pattern to all 19):
```python
@property
def debate_rounds(self) -> list[dict[str, Any]]:
    return self.method_state.data.get("debate", {}).get("rounds", [])

@debate_rounds.setter
def debate_rounds(self, value: list[dict[str, Any]]) -> None:
    self.method_state.data.setdefault("debate", {})["rounds"] = value

@property
def scientific_state(self) -> dict[str, Any]:
    return self.method_state.data.get("scientific", {})

@scientific_state.setter
def scientific_state(self, value: dict[str, Any]) -> None:
    self.method_state.data["scientific"] = value
```

### Step 2.3 — Simplify `to_context_dict`

Before: 19 manual fields. After: iterate `self.method_state.data`:

```python
context.update(
    {f"{k}_state" if k != "debate" else "debate_rounds": v
     for k, v in self.method_state.data.items() if v}
)
```

### Step 2.4 — Simplify `_from_dict`

Before: 19 `data.setdefault(...)` lines. After: single migration pass:

```python
_METHOD_KEYS = ['jury_guidelines', 'debate_rounds', 'scientific_state',
    'socratic_state', 'jury_weighted_ranking', 'pre_mortem_state',
    'bayesian_state', 'dialectical_state', 'analogical_state',
    'delphi_state', 'cove_state', 'sot_state', 'tot_state', 'pot_state',
    'self_discover_state', 'writing_state', 'coding_state',
    'brainstorming_state', 'cross_language_state']

if 'method_state' not in data:
    raw = {}
    for key in _METHOD_KEYS:
        val = data.pop(key, None)
        if val is not None and val != [] and val != {}:
            method_name = key.replace('_state', '').replace('_rounds', '')
            raw[method_name] = val
    if raw:
        data['method_state'] = {'data': raw}
```

### Step 2.5 — Tests

File: `tests/test_method_state.py`

```
test_method_state_bayesian()          — set bayesian_state, read via property + method_state.get
test_method_state_debate_rounds()     — set debate_rounds, verify alias
test_method_state_default_empty()     — unset property returns empty dict/list
test_method_state_new_method()        — method_state.set("new_method", {...}) works
test_load_old_state_file()            — _from_dict with old-format JSON
test_to_context_dict_no_methods()     — context dict doesn't include empty method_state
```

### Rollback
Remove `MethodState` class. Remove property aliases. Restore named fields.
**Full revert: 1 `git revert` commit.**

### Verification Gate
```bash
python -m pytest tests/test_method_state.py -v
python -m pytest -x -q --timeout=30 -n auto
```

---

## Phase 3: EventType Split

**Goal:** Monolithic 17-variant enum → 4 type-safe sub-enums. Event bus
subscriptions become type-safe.
**Risk:** Medium (4 files, event infrastructure).
**Time:** 3 hours.

### Step 3.1 — Add 4 Sub-Enums

File: `src/reasoner/core/events/domain_events.py`

```python
class PipelineEventType(str, Enum):
    PIPELINE_STARTED = "pipeline_started"
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    PHASE_FAILED = "phase_failed"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"
    PERSPECTIVE_GENERATED = "perspective_generated"
    CANDIDATE_SCORED = "candidate_scored"
    STRESS_TEST_COMPLETED = "stress_test_completed"
    RETRY_ATTEMPTED = "retry_attempted"
    CONTEXT_FETCHED = "context_fetched"
    CONTEXT_VETTED = "context_vetted"
    SOURCE_ADDED = "source_added"
    ERROR_OCCURRED = "error_occurred"

class WidgetEventType(str, Enum):
    WIDGET_DETECTED = "widget_detected"
    WIDGET_EXECUTED = "widget_executed"
    WIDGET_FAILED = "widget_failed"

class MemoryEventType(str, Enum):
    MEMORY_STORED = "memory_stored"
    MEMORY_RECALLED = "memory_recalled"

class SaaSEventType(str, Enum):
    USER_REGISTERED = "user_registered"
    USER_LOGGED_IN = "user_logged_in"
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    QUOTA_EXCEEDED = "quota_exceeded"
    QUOTA_RESET = "quota_reset"
    QUERY_LOGGED = "query_logged"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SUCCEEDED = "payment_succeeded"
```

### Step 3.2 — Keep `EventType` as Backward-Compatible Union

```python
# Union type for backward compatibility
_AllEventType = PipelineEventType | WidgetEventType | MemoryEventType | SaaSEventType

# Old import path still resolves
EventType = PipelineEventType  # import from here

# For consumers that need to handle all types:
ALL_EVENT_TYPES = {
    e.value: e for e in (
        list(PipelineEventType) + list(WidgetEventType) +
        list(MemoryEventType) + list(SaaSEventType)
    )}
```

### Step 3.3 — Update Event Bus for Typed Subscriptions

File: `src/reasoner/application/event_bus/bus.py`

```python
def subscribe(
    self,
    event_type: _AllEventType,
    handler: EventHandler,
) -> None:
    self._handlers[event_type].append(handler)
```

### Step 3.4 — Update `EVENT_CLASSES` Map

```python
PIPELINE_EVENT_CLASSES: dict[PipelineEventType, type[DomainEvent]] = { ... }
WIDGET_EVENT_CLASSES: dict[WidgetEventType, type[DomainEvent]] = { ... }
MEMORY_EVENT_CLASSES: dict[MemoryEventType, type[DomainEvent]] = { ... }
SAAS_EVENT_CLASSES: dict[SaaSEventType, type[DomainEvent]] = { ... }

# Shorthand backward compat:
EVENT_CLASSES = {**PIPELINE_EVENT_CLASSES, **WIDGET_EVENT_CLASSES,
                 **MEMORY_EVENT_CLASSES, **SAAS_EVENT_CLASSES}
```

### Step 3.5 — Update `make_event`

Accept any sub-type:
```python
def make_event(
    event_type: _AllEventType,
    aggregate_id: str,
    version: int,
    **kwargs: Any
) -> DomainEvent:
    ...
```

### Step 3.6 — Tests

File: `tests/test_event_types.py`

```
test_pipeline_only_subscription()     — widget event not dispatched to pipeline handler
test_saas_only_subscription()         — pipeline event not dispatched to SaaS handler
test_old_EventType_import_still_works() — `from ...domain_events import EventType`
test_backward_compat_value_comparison() — `EventType.PIPELINE_STARTED.value` still correct
test_event_classes_populated()        — all 4 registries have correct entries
test_make_event_with_sub_type()       — creates correct DomainEvent subclass
```

### Rollback
Restore monolithic `EventType`. Remove 4 sub-enums. Keep union alias.
**Full revert: 1 `git revert` commit.**

### Verification Gate
```bash
python -m pytest tests/test_event_types.py -v
python -m pytest -x -q --timeout=30 -n auto
```

---

## Phase 4: PipelineState → Core + Meta Aggregate Split

**Goal:** 55-field god object → 3 specialized containers.
**Risk:** High (30+ callers, largest change).
**Time:** 8 hours.
**Dependencies:** Phase 2 (MethodState) must be complete.

### Step 4.1 — Define `PipelineCore`

Fields that every phase reads:

```
problem, enhanced_problem, task_type, language, complexity,
decomposition, candidates, scores, top_candidates,
stress_results, final_solution, errors, attachments
```

### Step 4.2 — Define `PipelineMeta`

Fields that are write-only during execution, read-only after:

```
phase_logs, phase_tokens, phase_durations, phase_models,
phase_results, quality_hints, quality_history,
started_at, preset_name, method, context_quality
```

### Step 4.3 — Define `PipelineRemainder`

Fields that don't fit cleanly into core or meta:

```
neuro_context, reflexion_memory, web_discovery_results,
vetted_context, pending_events,
neuro_context, reflexion_memory,
synthesis_subagent_outputs, critique_subagent_outputs,
decomposition_subagent_outputs, enhancement_subagent_outputs,
search_subagent_outputs
```

### Step 4.4 — Rebuild `PipelineState`

```python
@dataclass
class PipelineState:
    core: PipelineCore
    method_state: MethodState = field(default_factory=MethodState)
    meta: PipelineMeta = field(default_factory=PipelineMeta)
    remainder: PipelineRemainder = field(default_factory=PipelineRemainder)
    cost_state: CostTrackingState = field(default_factory=CostTrackingState)
    conversation_state: ConversationState = field(default_factory=ConversationState)
    pending_events: list[dict[str, Any]] = field(default_factory=list)

    # ~35 property aliases for backward compat
    @property
    def problem(self) -> str: return self.core.problem
    @problem.setter
    def problem(self, value: str): self.core.problem = value
    # ... repeat for all moved fields
```

### Step 4.5 — Migration: Zero Consumer Changes (Phase A)

All 35 moved fields have `@property` / `@setter` aliases on `PipelineState`.
Existing code like `state.candidates` and `state.phase_logs` continues working.
The aliases transparently delegate to `self.core.candidates` /
`self.meta.phase_logs`.

### Step 4.6 — Migration: Consumer Refactoring (Phase B)

Convert callers one phase at a time, min 1 phase per commit:

1. `perspective_mixin.py` — uses `state.candidates`, `state.decomposition`
2. `debate_mixin.py` — uses `state.debate_rounds` (alias to method_state)
3. `jury_mixin.py` — uses `state.generation_candidates`, `state.critic_scores`
4. ... (one commit per mixin file)

After migrating a consumer, it can accept `PipelineCore` instead of
`PipelineState`, reducing its coupling to the full object.

### Step 4.7 — Migration: Alias Deprecation (Phase C)

Add `warnings.warn("state.candidates is deprecated, use state.core.candidates")`
when aliases are accessed. Schedule removal for v2.3.

### Step 4.8 — Tests

File: `tests/test_pipeline_state_split.py`

```
test_property_alias_read()            — state.problem == state.core.problem
test_property_alias_write()           — state.problem = "x" → state.core.problem == "x"
test_core_only_serialization()        — PipelineCore serializes to dict
test_meta_only_serialization()        — PipelineMeta serializes to dict
test_remainder_only_serialization()   — PipelineRemainder serializes to dict
test_full_roundtrip()                 — PipelineState → dict → PipelineState
test_core_only_phase_accepts_core()   — Phase function accepts PipelineCore, not PipelineState
test_backward_compat_solution_getter() — state.synthesis still returns dict
```

### Rollback
Remove `PipelineCore`, `PipelineMeta`, `PipelineRemainder` dataclasses.
Restore all fields back to `PipelineState` directly. Remove property aliases.
**Full revert: 1 `git revert` commit.**

### Verification Gate
```bash
python -m pytest -x -q --timeout=30 -n auto
# Verify full pipeline run:
python main.py --problem "test" --preset multi-perspective-budget --top-k 2 --sequential
```

---

## Rollback Instructions

Each phase produces exactly one atomic commit:

```bash
git log --oneline -5
# abc1234 Phase 4: PipelineState Core/Meta split
# def5678 Phase 3: EventType split
# ghi9012 Phase 2: MethodState dict wrapper
# jkl3456 Phase 1: PerspectiveType registry
# mno7890 Phase 0: Consumer map

# Rollback all:
git revert abc1234 def5678 ghi9012 jkl3456

# Rollback single Phase:
git revert ghi9012  # e.g., Phase 2 only
```

No `--force` pushes. No history rewrite. Each commit is independently
revertible because each phase preserves backward compatibility via
property aliases.

---

## Dependency Graph

```
Phase 1 (PerspectiveRegistry) ──── no deps ──── 2h
     │
     ├─── Phase 2 (MethodState) ─── depends on Phase 1 ─── 4h
     │        │
     │        └─── Phase 4 (Core/Meta split) ─── depends on Phase 2 ─── 8h
     │
     └─── Phase 3 (EventType split) ─── no deps ─── 3h

Total: 17 hours (parallelizable: P1 + P3 together, then P2, then P4)
```

## Implementation Checklist

### Phase 1 — PerspectiveRegistry

- [ ] Add `PerspectiveRegistry` class to `models.py`
- [ ] Add `__post_init__` to `SolutionCandidate` + `CritiqueScore`
- [ ] Update `_parse_critique_scores` in `parsing.py`
- [ ] Update `perpective_mixin.py` coercion
- [ ] Write `tests/test_perspective_registry.py` (5 tests)
- [ ] Run: `pytest -x -q -n auto` — all pass

### Phase 2 — MethodState

- [ ] Add `MethodState` dataclass to `models.py`
- [ ] Add 19 property alias pairs to `PipelineState`
- [ ] Simplify `to_context_dict` to iterate `method_state.data`
- [ ] Simplify `_from_dict` with migration pass
- [ ] Remove empty `setdefault()` lines from `_from_dict`
- [ ] Write `tests/test_method_state.py` (6 tests)
- [ ] Run: `pytest -x -q -n auto` — all pass

### Phase 3 — EventType

- [ ] Add `PipelineEventType` enum
- [ ] Add `WidgetEventType` enum
- [ ] Add `MemoryEventType` enum
- [ ] Add `SaaSEventType` enum
- [ ] Keep `EventType` = `PipelineEventType` as backward compat
- [ ] Split `EVENT_CLASSES` into 4 registries
- [ ] Update `make_event` signature
- [ ] Update `bus.py` subscription typing
- [ ] Write `tests/test_event_types.py` (6 tests)
- [ ] Run: `pytest -x -q -n auto` — all pass

### Phase 4 — PipelineState Split

- [ ] Define `PipelineCore` dataclass
- [ ] Define `PipelineMeta` dataclass
- [ ] Define `PipelineRemainder` dataclass
- [ ] Rebuild `PipelineState` with 5 sub-objects
- [ ] Add 35 property alias pairs
- [ ] Update `to_dict()` to serialize sub-objects
- [ ] Update `_from_dict()` to reconstruct sub-objects
- [ ] Update `save()` / `load()` for new layout
- [ ] Migrate 1 mixin per commit (14 commits)
- [ ] Deprecation warnings on aliases
- [ ] Write `tests/test_pipeline_state_split.py` (8 tests)
- [ ] Run: `pytest -x -q -n auto` — all pass
- [ ] Smoke: `python main.py --problem "test" --preset multi-perspective-budget`
