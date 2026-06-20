# Plan: Verbalized Sampling for Code Generation

## Problem

Code generation in Reasoner is single-pass: the LLM receives the spec and produces code directly. Models are not instructed to reason first, and no reasoning mode (`include_reasoning`) is enabled at the provider level. This produces:

- **Lower-quality code** — the model has no structured opportunity to consider architecture, edge cases, error handling, or security before writing
- **More generation-phase retries** — because initial output is lower quality
- **Inconsistent results** — between models that support reasoning and those that don't

Models that support reasoning (`deepseek-v3`, `qwen3.7-plus`, `qwen3.7-max`, `gemini-3.5-flash`, `ring-2.6-1t`, `stepfun-3.7-flash`) would benefit from a `<think>` → `<output>` two-phase generation pattern, where the reasoning output is stripped before parsing.

## Design

### Phase split: Think → Output

```
┌─────────────────────────────────────────────────┐
│  System prompt: <think> reason about:            │
│  - Architecture & component boundaries            │
│  - Edge cases & error paths                       │
│  - Security boundaries & input validation         │
│  - Testability & interface contracts              │
│  </think>                                        │
│  Then produce the final output in the required    │
│  format (JSON for spec, raw code for generation)  │
└─────────────────────────────────────────────────┘
```

The model writes its reasoning inside `<think>...</think>` tags, then its output after. The parser already strips `<think>` tags (`_strip_reasoning_tags()` in `core/parsing.py`), so no new parsing code is needed.

### Feature flag

```python
# settings.py
CODING_VERBALIZED_SAMPLING: bool = os.getenv(
    "CODING_VERBALIZED_SAMPLING", "true"
).lower() == "true"
```

Defaults `true` because:
- The parser already handles `<think>` stripping (added in B-31 fix)
- Reasoning output is invisible to the user after parsing
- Only adds latency (not cost) for models that bill reasoning tokens separately — and those are premium-tier models where quality matters more than speed

### Which phases get it

| Phase | Reasoning focus | Output format |
|-------|----------------|---------------|
| **Spec** (Phase 2) | Architecture, file boundaries, dependency graph, error strategy, security | JSON |
| **Generate** (Phase 3) | Edge cases, type contracts, input validation, error propagation, async safety, testing hooks | Raw code |
| **Review** (Phase 4) | Security audit, code quality check, test coverage gaps, anti-pattern detection | JSON |
| **Tests** (Phase 5) | Coverage strategy, edge-case enumeration, mock boundaries | Raw code |
| **Assemble** (Phase 6) | Integration surface, deployment readiness, documentation completeness | JSON |

### Prompts to update

**File:** `src/reasoner/phases/coding.py`

Add a helper function that prefixes the system prompt with the reasoning instruction:

```python
def _with_reasoning(system_prompt: str, focus: str) -> str:
    """Prefix a system prompt with verbalized-sampling instruction."""
    return (
        f"<think>\n"
        f"Before producing your output, reason step-by-step about: {focus}.\n"
        f"Consider edge cases, error handling, security, and testability.\n"
        f"Be concise — no more than 5-10 sentences of reasoning.\n"
        f"</think>\n\n"
        f"{system_prompt}"
    )
```

Then wrap each system prompt:

```python
CODING_SPEC_SYSTEM = _with_reasoning(
    "You are an elite software architect...",
    focus="architecture, file boundaries, dependencies, and error strategy",
)

CODING_GENERATE_SYSTEM = _with_reasoning(
    "You are a senior software engineer...",
    focus="edge cases, type contracts, input validation, error propagation, and async safety",
)
```

### Provider-level: enable reasoning tokens

**File:** `src/reasoner/infrastructure/llm/registry.py`

For models that support `include_reasoning`, add the parameter to their `extra_body`:

```python
"deepseek-v3": {
    "model": "deepseek/deepseek-v3.2",
    "extra_body": {"include_reasoning": True},
},
```

But this should be selective — only coding-capable models, and only when verbalized sampling is enabled. Better approach: add reasoning parameters dynamically in the router or the `call_llm` flow rather than hardcoding in the registry.

**Alternative — router-level injection:** In `_call_with_circuit_breaker` or the `ProviderRouter.call()` method, check if the role is a coding phase and add `include_reasoning: true` to the request body. This avoids modifying the registry and keeps reasoning scoped to coding.

### Parser: already ready

`extract_json_any()` in `core/parsing.py` calls `_strip_reasoning_tags()` as its second step (line ~108). This strips `<think>...</think>` and `<reasoning>...</reasoning>` before JSON extraction. For raw code output (not JSON), the `<think>` content is embedded in the response text — but the coding phases use `_safe_extract_json` or direct text extraction, so the `<think>` content will be present in the raw output unless stripped.

**For Generate and Tests phases (raw code output):** These produce code, not JSON. The `<think>` tags would appear in the generated file content. Fix: use `_strip_reasoning_tags()` on the raw response before storing it as file content. Add a utility function:

```python
def strip_reasoning_from_code(raw_code: str) -> str:
    """Strip <think> blocks from generated code before writing to file."""
    import re
    return re.sub(r"<think>[\s\S]*?</think>", "", raw_code).strip()
```

### Integration with existing CodeExecutorPort

When verbalized sampling is enabled AND the code executor (#1) is available, the reasoning output has additional value: the model's stated edge cases and test strategies can be extracted as `validation_commands` for the PlanContract (#5).

```python
# In coding_phases.py, after generation:
if reasoning_output and state.coding_state.get("contract"):
    # Extract stated test strategies from reasoning as validation commands
    state.coding_state["contract"].validation_commands.extend(
        extract_validation_commands_from_reasoning(reasoning_output)
    )
```

### File changes

| File | Change |
|------|--------|
| `src/reasoner/phases/coding.py` | Add `_with_reasoning()` helper; wrap all 5 system prompts; add `strip_reasoning_from_code()` |
| `src/reasoner/application/flows/coding_phases.py` | Strip reasoning from raw code output in generate/tests phases |
| `src/reasoner/core/settings.py` | Add `CODING_VERBALIZED_SAMPLING` flag |
| `src/reasoner/core/parsing.py` | Export `_strip_reasoning_tags()` as a public `strip_reasoning_tags()` function |

### Verification

```bash
# 1. Coding spec prompt includes <think> instruction
python -c "
from reasoner.phases.coding import CODING_SPEC_SYSTEM
assert '<think>' in CODING_SPEC_SYSTEM and '</think>' in CODING_SPEC_SYSTEM
print('PASS')
"

# 2. Reasoning is stripped from generated code
python -c "
from reasoner.phases.coding import strip_reasoning_from_code
code = '<think>consider error handling</think>\nimport os\ndef main(): pass'
assert 'import os' in strip_reasoning_from_code(code)
assert '<think>' not in strip_reasoning_from_code(code)
print('PASS')
"

# 3. End-to-end: disable flag → prompts unchanged
python -c "
import os; os.environ['CODING_VERBALIZED_SAMPLING'] = 'false'
from reasoner.core.settings import settings
assert settings.CODING_VERBALIZED_SAMPLING == False
print('PASS')
"
```

### Effort

**S** — 4 files modified, ~80 lines added. Parser already handles reasoning tags. No new infrastructure required.

---

## Architectural Compliance Audit

Checked against the 9 principles from `CODE_AS_HARNESS_ENHANCEMENT_PLAN.md §1`:

| # | Principle | Verdict | Rationale |
|---|-----------|---------|-----------|
| 1 | **Hexagonal DDD** — Domain depends on nothing outward | ✅ PASS | All changes are in `phases/coding.py` (prompts), `settings.py` (flags), and `flows/coding_phases.py` (response processing). Zero domain-layer changes. Prompt utilities never import domain; domain never sees `<think>` tags. |
| 2 | **CQRS** — Reads are Queries, writes are Commands | ✅ PASS | No new state. Verbalized sampling is a prompt-engineering concern — it modifies how the LLM is asked to produce output, not how the output is stored or routed. |
| 3 | **Event sourcing** — New observable facts are domain events | ✅ PASS | No new events needed. The reasoning output is an intermediate artifact — it's stripped before storage (by `_strip_reasoning_tags()`). If future observability is needed, the stripped reasoning can be logged as a debug event, but that's out of scope. |
| 4 | **State invariants** — `.get()`-safe dicts, all-default dataclasses | ✅ PASS | No state changes. Coding method-state already uses `dict[str, Any]` with `.get()` access. `strip_reasoning_from_code()` returns a clean string — it never touches state. |
| 5 | **No magic numbers** — All in constants files | ✅ PASS | `CODING_VERBALIZED_SAMPLING` is a `settings.py` env-var flag — follows the exact pattern of `CQRS_BYPASS_STREAMING`, `EXEC_SANDBOX_ENABLED`, `TOKEN_DYNAMIC_BUDGETS`, etc. |
| 6 | **Parsing discipline** — All through `extract_json()` + tolerant helpers | ✅ PASS | `_strip_reasoning_tags()` already exists in `parsing.py` and is called by `extract_json_any()` (line ~108). Exporting it as `strip_reasoning_tags()` for direct use by code-generation phases is a re-export, not a new parser. |
| 7 | **Security** — Sandbox, no network, allowlist, HITL | ✅ PASS | `<think>` content comes from the LLM, not user input. The parser strips it before storage. No new attack surface. |
| 8 | **Tiering & flags** — Opt-in via feature flag or `get_preset_price_tier` | ✅ PASS | `CODING_VERBALIZED_SAMPLING` defaults `true` with env-var override. Reasoning tokens add ~30% cost for models that bill them separately — acceptable because (a) it's opt-out, (b) code quality gains offset retry costs, (c) budget presets can disable it. |
| 9 | **Living docs** — Update `ARCHITECTURE_MINDMAP.md`, `AGENTS.md` | ⚠️ PENDING | Should add a note that coding phases now support verbalized sampling via `<think>` instructions. |

### Dependency direction check

```
settings.py (flag)        ← no imports from phases
phases/coding.py (prompts)  → reads settings.CODING_VERBALIZED_SAMPLING ✅ (downward: phases → core)
flows/coding_phases.py       → imports phases + core.parsing ✅ (downward: flows → phases + core)
core/parsing.py              → no new imports ✅
```

### Byte-identical budget path

When `CODING_VERBALIZED_SAMPLING=false`: prompts are unchanged from v3.x — the `<think>` instruction is never prepended. Budget runs produce exactly the same bytes as before. ✅

### `--resume` safety

No state schema changes. No new dataclass, no new fields on `PipelineState` or `coding_state`. Resumed coding runs will see no difference — the prompts are reconstructed at call time, not stored. ✅

