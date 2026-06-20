# Debate Pipeline Fix Plan

Identified from a live `debate-budget` run on 2026-06-11. Seven fixes across five architectural layers.

---

## Fix 1 — Circular import (already applied)

**File:** `src/reasoner/core/search.py`

**Root cause:** `searxng_adapter.py` imports from `core/search.py`; `core/search.py` had a module-level re-export of `DiscoveryClient` from `infrastructure/search/discovery.py`; `discovery.py` imports `SearXNGAdapter` from `searxng_adapter.py`. Cycle: `searxng_adapter → core/search → discovery → searxng_adapter`.

**Fix:** Converted the module-level `from reasoner.infrastructure.search.discovery import ...` to a lazy `__getattr__` resolver. The re-exports only materialise when first accessed, after `discovery.py` is fully initialised.

**Status:** Applied. The CLI was crashing before a single pipeline phase ran.

**Regression test to add:** A cold import test (`python -c "from reasoner.application.pipeline import ReasonerPipeline"`) in the test suite to ensure the cycle stays dead.

---

## Fix 2 — Replace `seed-2.0-mini` in `debate-budget`

**File:** `src/reasoner/domain/preset_registry.py`

**Root cause:** `seed-2.0-mini` (ByteDance) consistently saturates the 120s timeout. In testing, Round 1 completed in exactly 120s; Rounds 2 and 3 (rebuttal and cross-examination) timed out and fell back to `gemini-flash-lite`. The debate arena output confirmed it: Model A (proposition) showed as `google/gemini-3.1-flash-lite`, not the intended debater.

**Fix:**
```python
"constructive": "mistral-small",    # was: "seed-2.0-mini"
```

**Rationale for Mistral Small:**
- Different training lineage from all other debate-budget models: Qwen (destructive), GLM (judge), DeepSeek (decomposition/synthesis) — preserves cross-lab diversity.
- Already present in the preset under `stress_testing`, so it is a known-working model on this OpenRouter account.
- Typical latency well under 30s.

Update the `notes` array: remove the stale seed-2.0-mini comment and add the Mistral rationale.

---

## Fix 3 — Update `debate-budget` primary model

**File:** `src/reasoner/domain/preset_registry.py`

**Root cause:** `primary_id: "gemini-flash-lite"` maps to `google/gemini-3.1-flash-lite`. The `multi-perspective-budget` preset was already upgraded to `gemini-flash` but `debate-budget` was missed. HyperGate runs all 5 sub-agents against the primary, so this model's knowledge cutoff and latency affect every request before the pipeline even starts.

**Fix:**
```python
"primary_id": "gemini-flash",    # was: "gemini-flash-lite"
```

---

## Fix 4 — Debate judge prompt: explicit `CritiqueScore` schema

**File:** `src/reasoner/phases/debate.py`

**Root cause:** `debate_judge_prompt()` ends with:
```python
f'Output JSON: {{"scores": ..., "verdict_rationale": "..."}}'
```
The `...` is a Python ellipsis rendered as the literal string `"..."` in the prompt — no schema. GLM-5.1 invented its own structure (a dict keyed by side letter rather than a list), which caused `_parse_critique_scores` to fail on every entry with `string indices must be integers, not 'str'`. Both judge scores were dropped and the output table showed `Judge: ?`.

**Compounding issue:** `CritiqueScore.perspective` must be one of `constructive | destructive | systemic | minimalist` (validated by `PerspectiveRegistry.coerce`). The debate uses sides "A" and "B". The prompt must instruct the model to map A → `"constructive"` and B → `"destructive"` so the domain parser receives vocabulary it recognises.

**Fix to `debate_judge_prompt()`:** Replace the open-ended `...` with a fully-specified schema:

```python
def debate_judge_prompt(state: PipelineState) -> str:
    return (
        f'{get_language_instruction(state)}\n\n'
        f'Debate Transcript:\n{json.dumps(state.debate_rounds, indent=2)}\n\n'
        f'Score both sides and declare a winner.\n\n'
        f'IMPORTANT: Use exactly "constructive" for Side A (proposition) '
        f'and "destructive" for Side B (opposition) as the perspective field.\n\n'
        f'Output JSON:\n'
        f'{{\n'
        f'  "scores": [\n'
        f'    {{\n'
        f'      "perspective": "constructive",\n'
        f'      "logical_consistency": <float 0-10>,\n'
        f'      "evidence_support": <float 0-10>,\n'
        f'      "failure_resilience": <float 0-10>,\n'
        f'      "feasibility": <float 0-10>,\n'
        f'      "bias_flags": ["<flag if any>"],\n'
        f'      "steel_man": "<strongest point in favour of this side>"\n'
        f'    }},\n'
        f'    {{\n'
        f'      "perspective": "destructive",\n'
        f'      "logical_consistency": <float 0-10>,\n'
        f'      "evidence_support": <float 0-10>,\n'
        f'      "failure_resilience": <float 0-10>,\n'
        f'      "feasibility": <float 0-10>,\n'
        f'      "bias_flags": ["<flag if any>"],\n'
        f'      "steel_man": "<strongest point in favour of this side>"\n'
        f'    }}\n'
        f'  ],\n'
        f'  "winner": "A" | "B" | "DRAW",\n'
        f'  "verdict_rationale": "<concise reasoning>"\n'
        f'}}'
    )
```

---

## Fix 5 — Richer `DEBATE_JUDGE_SYSTEM` prompt

**File:** `src/reasoner/phases/debate.py`

**Root cause:** The current system prompt is one line with no rubric and no output format constraint:
```
"You are an analytical assistant. Evaluate the debate and render a verdict. Output ONLY valid JSON."
```
No mention of the debate sides, what the scoring dimensions mean, or what the output structure should look like. This is why GLM-5.1 invented its own schema.

**Fix:** Replace with a detailed system prompt that specifies:
- Role: neutral judge, not a participant
- Scoring rubric matching `CritiqueScore` field semantics:
  - `logical_consistency`: soundness and internal coherence of the argument
  - `evidence_support`: quality and strength of supporting evidence
  - `failure_resilience`: ability to withstand counterarguments
  - `feasibility`: practical applicability of the proposed solution
- Side mapping instruction: Side A (proposition) → `"constructive"`, Side B (opposition) → `"destructive"`
- Hard format constraint: output ONLY the JSON object, no markdown fences, no surrounding text

This belongs in `phases/debate.py` alongside `DEBATE_OPENING_SYSTEM`, `DEBATE_REBUTTAL_SYSTEM`, and `DEBATE_CROSS_SYSTEM` — all debate prompt strings live in this module.

---

## Fix 6 — Defensive type guard in `_parse_critique_scores`

**File:** `src/reasoner/core/parsing.py`

**Root cause:** `_parse_critique_scores` iterates over `raw_scores` assuming it is always a `list[dict]`. When the judge returns a dict (e.g. `{"A": {...}, "B": {...}}`), iterating yields string keys, and `s["perspective"]` fails with `string indices must be integers, not 'str'`.

Fix 4 prevents GLM-5.1 from making this mistake, but any future judge model swap could produce the same shape. The parser is in the `core` layer — a pure data-coercion adapter with no LLM calls or business logic. Defensive normalisation of unexpected-but-interpretable input belongs here.

**Fix:** Add a type guard before the loop:

```python
def _parse_critique_scores(raw_scores: list[dict]) -> list[CritiqueScore]:
    if isinstance(raw_scores, dict):
        # LLM returned a keyed dict instead of a list — coerce to list of values
        raw_scores = list(raw_scores.values())
    if not isinstance(raw_scores, list):
        logger.warning(
            "CritiqueScore input is not a list (%s) — skipping",
            type(raw_scores).__name__,
        )
        return []
    # ... existing loop unchanged
```

---

## Fix 7 — Empty-rounds guard in `run_debate_judge_phase`

**File:** `src/reasoner/application/flows/debate_phases.py`

**Root cause:** `run_debate_judge_phase` sends `state.debate_rounds` to the LLM unconditionally. If all prior rounds failed (all models timed out, opening statements empty, etc.), the judge receives an empty transcript and produces meaningless or malformed scores.

**Precedent:** `run_debate_rebuttal_phase` already guards against missing opening statements before proceeding. The judge phase should apply the same pattern.

**Fix:**

```python
async def run_debate_judge_phase(state: PipelineState, services: WorkflowServices) -> None:
    if not state.debate_rounds:
        msg = "Debate judging skipped: no rounds in transcript"
        services.log("DEBATE", msg, state)
        state.errors.append(msg)
        return
    services.log("DEBATE", "Round 3: Judging", state)
    # ... existing code unchanged
```

---

## Verification checklist

After applying all fixes:

1. **Import regression:** `python -c "from reasoner.application.pipeline import ReasonerPipeline"` exits with code 0.
2. **Preset check:** `python -c "from reasoner.domain.preset_registry import PRESETS; p = PRESETS['debate-budget']; print(p.primary_id, p.routing['constructive'])"` prints `gemini-flash mistral-small`.
3. **Parser unit tests:** Call `_parse_critique_scores({"A": {}, "B": {}})` and `_parse_critique_scores("bad")` — both return `[]` without raising.
4. **End-to-end debate:** `python main.py --problem "..." --preset debate-budget`. Expected outcomes:
   - No 120s timeouts
   - `state.scores` non-empty (judge scores populated)
   - Judge row in output table shows `z-ai/glm-5.1`, not `?`
   - Wall time under 3 minutes (vs 467s before fixes)

---

## Summary

| # | Status | Layer | File | Change |
|---|--------|-------|------|--------|
| 1 | ✅ Applied | Core | `core/search.py` | Lazy `__getattr__` for discovery re-exports |
| 2 | Pending | Preset data | `domain/preset_registry.py` | `constructive: mistral-small` (was seed-2.0-mini) |
| 3 | Pending | Preset data | `domain/preset_registry.py` | `primary_id: gemini-flash` (was gemini-flash-lite) |
| 4 | Pending | Phase prompt | `phases/debate.py` | Explicit `CritiqueScore` schema in judge user prompt |
| 5 | Pending | Phase prompt | `phases/debate.py` | Richer `DEBATE_JUDGE_SYSTEM` with scoring rubric |
| 6 | Pending | Core parsing | `core/parsing.py` | Dict-to-list guard in `_parse_critique_scores` |
| 7 | Pending | App flow | `application/flows/debate_phases.py` | Empty-rounds guard in judge phase |
