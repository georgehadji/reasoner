---
name: reasoner-pipeline
description: End-to-end guide for adding a new reasoning method to the Reasoner pipeline. Covers phases, PipelineState, presets, HyperGate routing, and the test to write.
trigger: /reasoner-pipeline
---

# Adding a Reasoning Method to Reasoner

Use this skill when adding a new reasoning method (e.g. a new `debate` variant, a new analytical method). It walks through every file that must change and in what order.

## What a "method" is

A method is a named reasoning strategy that runs after HyperGate routes the problem. There are currently 19 methods: `multi_perspective`, `debate`, `jury`, `research`, `scientific`, `socratic`, `pre_mortem`, `bayesian`, `dialectical`, `analogical`, `delphi`, `cove`, `sot`, `tot`, `pot`, `self_discover`, `writing`, `coding`, `brainstorming`.

Each method maps to:
- A **prompt module** in `src/reasoner/phases/<method_name>.py`
- A **routing key** or set of keys in `_KNOWN_ROUTING_ROLES` (`src/reasoner/domain/preset_core.py`)
- At least one **preset config** in `src/reasoner/domain/preset_registry.py`
- An entry in **HyperGate's tie-breaker** (`src/reasoner/hypergate/sub_agents/tie_breaker.py`)

## Step-by-step checklist

### 1. Write the phase prompt module

Create `src/reasoner/phases/<your_method>.py`. Model it on the simplest existing method:

```python
# src/reasoner/phases/your_method.py
"""Prompt strings for the YourMethod reasoning method."""

PHASE_0_SYSTEM = "..."   # Classification system prompt
PHASE_1_SYSTEM = "..."   # Decomposition system prompt
PHASE_2_SYSTEM = "..."   # Generation (perspectives) system prompt
PHASE_3_SYSTEM = "..."   # Critique system prompt
PHASE_4_SYSTEM = "..."   # Stress test system prompt
PHASE_5_SYSTEM = "..."   # Synthesis system prompt
```

Reference `src/reasoner/phases/_shared.py` for reusable building blocks (e.g. `EPISTEMIC_LABELS`, `ACTION_BLUEPRINT_FORMAT`).

### 2. Add routing role keys (if new roles needed)

Open `src/reasoner/domain/preset_core.py` and add any new role names to `_KNOWN_ROUTING_ROLES`:

```python
_KNOWN_ROUTING_ROLES: frozenset[str] = frozenset({
    # ... existing roles ...
    "your_method_step_1",
    "your_method_step_2",
})
```

Only add a new role if your method needs a model assigned to a phase role that doesn't already exist. Most methods reuse `constructive`, `destructive`, `scoring`, `synthesis`, etc.

### 3. Add presets (Budget + Premium minimum)

In `src/reasoner/domain/preset_registry.py`, add entries to `_PRESET_CONFIGS`. Always ship at minimum a Budget and a Premium preset:

```python
{
    "id": "your-method-budget",
    "name": "Your Method (Budget)",
    "description": "One-line description. Estimated cost: <$0.02.",
    "primary_id": "gemini-flash-lite",   # cheapest capable model
    "routing": {
        "classification": "gpt-5-mini",
        "decomposition": "deepseek-v3",
        "your_method_step_1": "mistral-small",
        "scoring": "qwen3.5-flash",
        "synthesis": "qwen3.7-max",
        # ... all roles your method uses
    },
    "fallback_routing": {
        # Same keys, swap to free/cheap models
        "your_method_step_1": "glm-4-air",
    },
    "notes": ["Phase 2: <lab diversity summary>"],
},
{
    "id": "your-method-premium",
    "name": "Your Method (Premium)",
    "description": "Premium tier. Estimated cost: $0.15–$0.30.",
    "primary_id": "claude-opus",
    "routing": { ... },
    "fallback_routing": { ... },
},
```

**Cross-lab diversity rule** (enforced by the CI `pr-architecture.yml`):
- Budget: ≥ 3 different labs in Phase 2 perspective roles
- Premium: ≥ 4 different labs in Phase 2 perspective roles
- Scorer must be from a different lab than the dominant Phase 2 generator

Labs available: Anthropic, OpenAI, Google, xAI, Perplexity, Mistral, DeepSeek, Qwen (Alibaba), Kimi (Moonshot), GLM (Zhipu), MiniMax, NVIDIA.

### 4. Register the method name in HyperGate

Open `src/reasoner/hypergate/sub_agents/tie_breaker.py` and add your method's snake_case name to `_VALID_METHODS`:

```python
_VALID_METHODS = {
    "debate", "scientific", ...
    "your_method",   # add here
}
```

Also update the system prompt string `_SYSTEM` to include your method in the list given to the LLM (the list after "specify the best method from this list:").

### 5. Wire the orchestrator

Open `src/reasoner/pipeline.py` (the `ReasonerPipeline` orchestrator). Find where existing methods dispatch to their phase modules:

```python
# Look for the method dispatch pattern, typically:
if state.method == "debate":
    from reasoner.phases.debate import PHASE_2_SYSTEM
    ...
```

Add your method to the same dispatch block.

### 6. Handle PipelineState (if method needs dedicated state)

If your method accumulates phase-specific data across steps, store it in `MethodState.data`:

```python
# In your phase handler:
method_state = state.method_state.get("your_method")
method_state["step_1_result"] = result
state.method_state.set("your_method", method_state)
```

**Do not add new top-level fields to PipelineState or its sub-containers** unless the data is needed by multiple methods. `MethodState.data` is the escape hatch for method-specific state. This keeps `--resume` compatibility clean.

### 7. Write the test

Create `tests/test_<your_method>.py`. At minimum, test:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_your_method_phase_2_builds_prompt():
    from reasoner.phases.your_method import PHASE_2_SYSTEM
    assert "your expected string" in PHASE_2_SYSTEM

@pytest.mark.asyncio
async def test_your_method_preset_valid():
    from reasoner.domain.preset_registry import _PRESET_CONFIGS
    budget = next(p for p in _PRESET_CONFIGS if p["id"] == "your-method-budget")
    assert "your_method_step_1" in budget["routing"]

def test_your_method_in_hypergate_valid_methods():
    from reasoner.hypergate.sub_agents.tie_breaker import _VALID_METHODS
    assert "your_method" in _VALID_METHODS
```

Run with:
```bash
PYTHONPATH=src pytest tests/test_your_method.py -v
```

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Adding roles to `routing` not in `_KNOWN_ROUTING_ROLES` | Add to `_KNOWN_ROUTING_ROLES` first |
| All Phase 2 roles from same lab | Diversify — ≥3 labs for Budget |
| Scorer from same lab as dominant generator | Use a different-lab model for `scoring` |
| Storing method state in new top-level PipelineState fields | Use `MethodState.data["your_method"]` |
| Forgetting HyperGate tie-breaker registration | Method will never be selected by auto-routing |
| Calling LLM response via `json.loads()` directly | Always use `parsing.extract_json()` |
