# Root Cause Analysis: Greek Article Request Decomposition Timeout

## Incident Summary

**Input:** `γράψε ένα άρθρο για τις νεώτερες εξελίξεις στον τομέα της δυναμικής αστρονομίας`
(Write an article about the latest developments in dynamic astronomy)

**Preset:** `writing-budget`

**Failure:** Phase 1 "Decomposition" timed out after 30.0s
- Tokens: 903 in · 1,827 out · 2,730 total
- Model: `google/gemini-2.5-flash-lite`
- Duration: ~30.7s before timeout cancellation

---

## Problem 1: CRITICAL — `streaming.py` bypasses article detection entirely

**Location:** `src/reasoner/api/streaming.py` lines 491-499

The API streaming path **never calls `pipeline.run()`**. Instead, it manually constructs the phase sequence:

```python
async def decompose_and_vet(state: PipelineState):
    await pipeline._phase_1_decompose(state)          # ALWAYS runs
    await pipeline._phase_context_vetting(state, ...)  # ALWAYS runs

phases = [
    (0, "Classification", pipeline._phase_0_classify, _ser_0),
    (1, "Decomposition", decompose_and_vet, _ser_1),   # Hardcoded generic
    ...
]
```

Meanwhile, `pipeline.run()` has article detection logic:

```python
# pipeline.py:324-330
from reasoner.application.mixins.article_pipeline import is_article_request
if is_article_request(state.problem):
    state.task_type = TaskType.TECHNICAL
    state.decomposition = ["article workflow"]   # Skips generic decomp
    state.method = "writing"
```

**Impact:** The article detection in `pipeline.run()` is **dead code** for all API requests. Every article request goes through generic decomposition regardless of language.

---

## Problem 2: PRIMARY — `is_article_request()` is English-only

**Location:** `src/reasoner/application/mixins/article_pipeline.py` lines 43-78

```python
_WRITING_INDICATORS = [
    r"\b(write|draft|compose|author|create)\b.*\b(article|essay|blog|report|paper|explainer)\b",
    r"\barticle\b.*\b(about|on)\b",
]
```

These regex patterns match **only English words**. The Greek input contains:
- `γράψε` = write
- `άρθρο` = article  
- `για` = for/about

None of these match `\barticle\b` or `\b(write|draft|...)\b`. Even if `streaming.py` used `pipeline.run()`, article detection would fail for Greek.

**The code does have Greek patterns** for `_PAPER_INDICATORS` and `_THESIS_INDICATORS` (lines 51-60), but `_WRITING_INDICATORS` — the primary article detector — has **zero non-English patterns**.

---

## Problem 3: SEMANTIC MISMATCH — Generic decomposition on creative writing

**Location:** `src/reasoner/phases/_universal.py` lines 48-62

When article detection fails, the request flows through `_phase_1_decompose` which uses:

```python
DECOMPOSITION_SYSTEM = "Decompose problem into sub-problems. JSON only."

def decomposition_prompt(state: PipelineState) -> str:
    return f'''{get_language_instruction(state)}
Problem: {state.problem}
Decompose.

JSON: {{"causal_chain": [...], "assumptions": [...], "failure_modes": [...], "critical_sources": [...]}}
Rules: Max 5 steps. Surface assumptions with rationale.'''
```

The prompt asks for **causal chains, assumptions, failure modes, and critical sources** — a fully analytical decomposition framework. But the user asked to **write an article about dynamic astronomy**. 

This is a category error: the model is being asked to analytically decompose a creative writing request. The resulting confusion causes:
- Excessive token generation (1,827 output tokens vs 1,024 budget)
- Longer generation time (>30s for a "flash-lite" model)
- Poor-quality decomposition that doesn't serve the article pipeline

---

## Problem 4: TOKEN BUDGET NOT ENFORCED

**Location:** `src/reasoner/infrastructure/llm/executor.py`

`_phase_1_decompose` passes `max_tokens=get_token_budget("decomposition")` = **1,024 tokens**.

However, the API reports **1,827 output tokens** — 78% over budget. This suggests:
1. The `max_tokens` parameter is not being correctly passed through the router to the provider
2. OR `gemini-2.5-flash-lite` via OpenRouter doesn't respect `max_tokens` for this role
3. OR the token count includes something other than generated tokens

Regardless, the model generates far more than requested, contributing to the timeout.

---

## Problem 5: PHASE TIMEOUT COVERS BOTH DECOMPOSITION + VETTING

**Location:** `src/reasoner/api/streaming.py` lines 491-493

```python
async def decompose_and_vet(state: PipelineState):
    await pipeline._phase_1_decompose(state)           # LLM call + parsing
    await pipeline._phase_context_vetting(state, ...)   # Additional work
```

The 30-second timeout covers **both** decomposition and context vetting. If decomposition alone takes 28s, vetting has only 2s remaining. This bundling makes timeouts more likely.

---

## Fix Priority Matrix

| Priority | Problem | Fix Location | Effort |
|----------|---------|-------------|--------|
| **P0** | streaming.py bypasses article detection | `streaming.py`: add article detection before phase construction | 30 min |
| **P0** | is_article_request() English-only | `article_pipeline.py`: add Greek + multilingual patterns | 20 min |
| **P1** | Semantic mismatch for writing requests | `streaming.py`: skip generic decomposition when method=writing | 15 min |
| **P1** | max_tokens not enforced | `executor.py` or `router.py`: audit max_tokens propagation | 45 min |
| **P2** | Decompose+vett bundled timeout | `streaming.py`: split into separate phases or increase timeout | 15 min |

---

## Recommended Fix: Unified Article Detection in streaming.py

```python
# In streaming.py, before building phases:
from reasoner.application.mixins.article_pipeline import is_article_request

if is_article_request(state.problem):
    state.task_type = TaskType.TECHNICAL
    state.decomposition = ["article workflow"]
    state.method = "writing"
    logger.info("Article request detected in streaming path — skipping generic decomposition")
```

And add Greek writing indicators:

```python
_WRITING_INDICATORS = [
    # English
    r"\b(write|draft|compose|author|create)\b.*\b(article|essay|blog|report|paper|explainer)\b",
    r"\barticle\b.*\b(about|on)\b",
    # Greek (γράψε = write, άρθρο = article, έκθεση = essay)
    r"\b(γράψε|γράψτε|συντάξε|συντάξτε|δημιούργησε|δημιουργήστε)\b.*\b(άρθρο|έκθεση|αναφορά|κείμενο|paper)\b",
    r"\b(άρθρο|έκθεση)\b.*\b(για|σχετικά\s+με|πάνω\s+σε)\b",
]
```

---

## Verification Steps

1. Send Greek article request through UI
2. Confirm Phase 1 shows "Decompose Topic" (article pipeline) not "Decomposition" (generic)
3. Confirm total pipeline duration < 30s for decomposition phase
4. Confirm article pipeline generates actual article output
