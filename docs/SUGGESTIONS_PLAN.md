# Suggestions Implementation Plan

**Generated:** 2026-06-10  
**Scope:** 9 items across 4 sprints derived from post-Nemotron-integration review  
**Estimated total effort:** ~2 days

---

## Guiding Principles

1. **Correctness before features** — bug fixes in Sprint 1 before any new functionality.
2. **Surgical changes** — each edit touches only the file(s) responsible for the problem.
3. **Feature flags** — any new runtime behavior is gated by an env var so it can be enabled incrementally.
4. **Tests before merge** — every sprint item ends with at least one unit test that would have caught the issue.
5. **No side effects on existing paths** — changes must not alter behavior when the new feature is disabled.

---

## Sprint 1: Bug Fixes (30 min total)

Two defects introduced in the Nemotron integration. Fix these before any other work.

---

### S1-A — `rerank_memory_chunks()` silently skips Nemotron when Cohere is disabled

**File:** `src/reasoner/core/rerank.py:354`  
**Effort:** 5 min

#### Root Cause

`rerank_memory_chunks()` has an independent early-exit guard at line 354:

```python
if not settings.COHERE_RERANK_ENABLED:
    return chunks
```

This check fires **before** `rerank_documents()` is called. Since `rerank_documents()` contains the `NEMOTRON_RERANK_ENABLED` check, but `rerank_memory_chunks()` returns before ever reaching it, setting `COHERE_RERANK_ENABLED=false` and `NEMOTRON_RERANK_ENABLED=true` leaves neuro memory chunks entirely un-reranked — contradicting the feature's intent.

#### Fix

The guard should pass through when either reranker is active:

```python
# Before (line 354):
if not settings.COHERE_RERANK_ENABLED:
    return chunks

# After:
if not settings.COHERE_RERANK_ENABLED and not settings.NEMOTRON_RERANK_ENABLED:
    return chunks
```

#### Test

```python
# tests/unit/test_rerank.py

from unittest.mock import patch, AsyncMock
import pytest
from reasoner.core import rerank as rerank_module


@pytest.mark.asyncio
async def test_memory_chunks_uses_nemotron_when_cohere_disabled(monkeypatch):
    """rerank_memory_chunks() must not skip Nemotron when COHERE_RERANK_ENABLED=False."""
    monkeypatch.setattr(rerank_module.settings, "COHERE_RERANK_ENABLED", False)
    monkeypatch.setattr(rerank_module.settings, "NEMOTRON_RERANK_ENABLED", True)

    nemotron_mock = AsyncMock(return_value=[{"content": "doc2"}, {"content": "doc1"}])
    with patch.object(rerank_module, "rerank_via_nemotron", nemotron_mock):
        class FakeChunk:
            def __init__(self, t): self.content = t; self.source = "s"
        chunks = [FakeChunk("doc1"), FakeChunk("doc2")]
        result = await rerank_module.rerank_memory_chunks("query", chunks)

    nemotron_mock.assert_awaited_once()
```

---

### S1-B — `import math` inside a hot function

**File:** `src/reasoner/core/rerank.py:220`  
**Effort:** 2 min

#### Root Cause

`_score_document_nemotron()` contains `import math` (line 220) inside the function body. This is a performance anti-pattern: Python resolves imports on every invocation, even though the module is cached in `sys.modules`. The function is called once per document per rerank batch — up to 100 times per vetting phase — amplifying the overhead.

#### Fix

Add `import math` to the module-level imports at the top of `rerank.py` (line 9 group, alongside `import asyncio`):

```python
# Add to module-level imports (line 9 area):
import math
```

Remove the inline `import math` at line 220.

#### Test

```python
def test_rerank_module_imports_math_at_module_level():
    """math must be imported at module level, not inside a hot function."""
    import inspect
    import ast
    import reasoner.core.rerank as mod
    src = inspect.getsource(mod._score_document_nemotron)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names]
            assert "math" not in names, (
                "_score_document_nemotron must not import math inline — use module-level import"
            )
```

---

## Sprint 2: Context Vetting Semantic Reranking (1–2 hours)

---

### S2 — Wire Nemotron/Cohere semantic reranking into the context vetting phase

**Files:** `src/reasoner/application/flows/search_phases.py`, `src/reasoner/core/settings.py`  
**Effort:** ~1 hour

#### Background

`run_context_vetting_phase()` in `search_phases.py` currently sorts results using a BM25+freshness heuristic (lines 244–253):

```python
current_results.sort(
    key=lambda r: (
        _bm25_score(problem_for_rank, r) * 0.8
        + r.get("freshness_score", 0.5) * 0.2
    ),
    reverse=True,
)
state.web_discovery_results = current_results
services.log("VETTING", "Applied BM25 + freshness re-ranking to search results.", state)
```

BM25 is a bag-of-words model — it has no semantic understanding. A result about "CUDA memory optimization" would score poorly against a query phrased as "GPU RAM efficiency" despite being the most relevant document. Nemotron Rerank VL (free, already integrated) is a cross-encoder that understands query-document semantic similarity and would directly improve the quality of context passed to Phase 2 and beyond.

The insertion point is **after** the BM25 sort (which serves as a cheap pre-filter) and **before** `vet_results()` (which applies LLM-based CoT vetting to the top results). This keeps the pipeline cost-efficient: BM25 narrows from N candidates to a manageable set, Nemotron then semantically ranks those, and CoT vetting reviews only the highest-scoring results.

#### New Setting

Add to `src/reasoner/core/settings.py`, in the Rerank section (after `NEMOTRON_RERANK_CONCURRENCY`):

```python
# When enabled, semantic reranking (Cohere/Nemotron) is applied to web search results
# in the context vetting phase after BM25 pre-filtering. Off by default to preserve
# existing pipeline behaviour until validated.
SEMANTIC_RERANK_VETTING: bool = os.getenv("SEMANTIC_RERANK_VETTING", "false").lower() in ("1", "true", "yes")
# Maximum results to submit to the semantic reranker in vetting (cost guard).
SEMANTIC_RERANK_VETTING_TOP_N: int = int(os.getenv("SEMANTIC_RERANK_VETTING_TOP_N", "15"))
```

#### Code Change

In `search_phases.py`, replace the block at lines 244–254:

```python
# Before:
if current_results:
    problem_for_rank = disambiguated_problem or state.problem
    current_results.sort(
        key=lambda r: (
            _bm25_score(problem_for_rank, r) * 0.8
            + r.get("freshness_score", 0.5) * 0.2
        ),
        reverse=True,
    )
    state.web_discovery_results = current_results
    services.log("VETTING", "Applied BM25 + freshness re-ranking to search results.", state)
```

```python
# After:
if current_results:
    problem_for_rank = disambiguated_problem or state.problem
    # Stage 1: BM25 + freshness — cheap lexical pre-filter.
    current_results.sort(
        key=lambda r: (
            _bm25_score(problem_for_rank, r) * 0.8
            + r.get("freshness_score", 0.5) * 0.2
        ),
        reverse=True,
    )
    services.log("VETTING", "Applied BM25 + freshness pre-ranking to search results.", state)

    # Stage 2: Semantic reranking — cross-encoder scores query-document relevance.
    # Gated by SEMANTIC_RERANK_VETTING; falls back gracefully on any error.
    if settings.SEMANTIC_RERANK_VETTING:
        from reasoner.core.rerank import rerank_documents
        try:
            top_n = settings.SEMANTIC_RERANK_VETTING_TOP_N
            current_results = await rerank_documents(
                problem_for_rank,
                current_results,
                top_n=min(top_n, len(current_results)),
            )
            services.log(
                "VETTING",
                f"Semantic reranking applied (top {len(current_results)} results retained).",
                state,
            )
        except Exception as rerank_exc:
            services.log("VETTING", f"Semantic reranking failed ({rerank_exc}) — BM25 order retained.", state)

    state.web_discovery_results = current_results
```

#### Design Decisions

- **Import is local** (`from reasoner.core.rerank import rerank_documents` inside the `if` block) to avoid adding a module-level circular-import risk between `search_phases` and `core/rerank`. Since this path is only taken when `SEMANTIC_RERANK_VETTING=true`, the import cost is paid once per vetting phase, not at module load.
- **`top_n` cap** prevents submitting hundreds of results to the reranker. The default of 15 ensures we're ranking a manageable set while keeping rate-limit pressure low.
- **Exception wrapper** preserves the existing BM25 order on failure — the vetting phase must never block the pipeline.
- **`rerank_documents()` already contains all backend logic** — it routes to Cohere, Nemotron fallback, or no-op depending on settings. No logic duplication.

#### Tests

```python
# tests/unit/test_search_phases_rerank.py

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from reasoner.application.flows.search_phases import run_context_vetting_phase


@pytest.mark.asyncio
async def test_vetting_applies_semantic_reranking_when_enabled(monkeypatch):
    """When SEMANTIC_RERANK_VETTING=True, rerank_documents is called after BM25."""
    from reasoner.core import settings as _settings
    monkeypatch.setattr(_settings.settings, "SEMANTIC_RERANK_VETTING", True)
    monkeypatch.setattr(_settings.settings, "SEMANTIC_RERANK_VETTING_TOP_N", 5)

    rerank_mock = AsyncMock(return_value=[{"url": "a", "snippet": "ranked"}])
    with patch("reasoner.core.rerank.rerank_documents", rerank_mock):
        # ... set up minimal state and services mocks, call run_context_vetting_phase
        pass  # full setup omitted for brevity — test the call assertion

    rerank_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_vetting_skips_semantic_reranking_when_disabled(monkeypatch):
    """When SEMANTIC_RERANK_VETTING=False, rerank_documents is never called."""
    from reasoner.core import settings as _settings
    monkeypatch.setattr(_settings.settings, "SEMANTIC_RERANK_VETTING", False)

    rerank_mock = AsyncMock()
    with patch("reasoner.core.rerank.rerank_documents", rerank_mock):
        pass  # call vetting phase

    rerank_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_vetting_degrades_gracefully_on_rerank_failure(monkeypatch):
    """If semantic reranking raises, BM25 order is preserved and no exception propagates."""
    from reasoner.core import settings as _settings
    monkeypatch.setattr(_settings.settings, "SEMANTIC_RERANK_VETTING", True)

    with patch("reasoner.core.rerank.rerank_documents", AsyncMock(side_effect=RuntimeError("API down"))):
        # Phase must complete without raising
        pass  # assert state.vetted_context is populated (BM25 fallback)
```

---

## Sprint 3: New Free Models (30 min)

---

### S3 — Add `nvidia/llama-3.1-nemotron-nano-8b-v1:free` and `meta-llama/llama-3.3-70b-instruct:free`

**File:** `src/reasoner/infrastructure/llm/registry.py`  
**Effort:** 10 min for additions, ~20 min for preset wiring assessment

#### Background

Both models are on OpenRouter's free tier. Adding them increases cross-lab diversity in Budget presets at zero marginal cost. Specifically:

| Model | Lab | Strengths | Ideal roles |
|-------|-----|-----------|-------------|
| `nvidia/llama-3.1-nemotron-nano-8b-v1:free` | NVIDIA | Reasoning, instruction following, small + fast | Classification, decomposition, minimalist perspective in Phase 2 |
| `meta-llama/llama-3.3-70b-instruct:free` | Meta | Strong instruction following, multilingual, 70B quality at 0 cost | Synthesis, scoring, systemic perspective |

Cross-lab diversity rule: Phase 2 Budget presets should use ≥3 different labs. Currently Budget presets lean heavily on Google + Mistral + Zhipu. Nemotron Nano (NVIDIA) and Llama 3.3 70B (Meta) fill two lab slots not yet represented in Budget presets.

#### Registry Additions

In `src/reasoner/infrastructure/llm/registry.py`, add to the NVIDIA section:

```python
# NVIDIA (via OpenRouter)
"nvidia-nemotron-rerank-vl": {"model": "nvidia/llama-nemotron-rerank-vl-1b-v2:free"},
"nvidia-nemotron-nano-8b":   {"model": "nvidia/llama-3.1-nemotron-nano-8b-v1:free"},
```

Add a new Meta section immediately after the Laguna section (after line 105):

```python
# Meta
"llama-3.3-70b": {"model": "meta-llama/llama-3.3-70b-instruct:free"},
```

#### Naming Conventions

- `nvidia-nemotron-nano-8b` — matches the NVIDIA namespace prefix already established by `nvidia-nemotron-super` and `nvidia-nemotron-rerank-vl`.
- `llama-3.3-70b` — matches the codebase's model-family + size convention (e.g., `mistral-small`, `qwen3.5-27b`).

#### Preset Wiring Assessment

Before wiring into presets, read the existing Budget preset routing in `preset_registry.py` to identify which roles currently use the fewest distinct labs. The recommended starting points are:

**`nvidia-nemotron-nano-8b`** for the `minimalist` role in `multi-perspective-budget` — currently assigned to `ministral-3b` (Mistral, same lab as `mistral-small` in `destructive`). Replacing with NVIDIA adds a fourth lab to Phase 2.

**`llama-3.3-70b`** for the `scoring` role in `multi-perspective-budget` — currently `qwen3.5-flash` (Alibaba). Meta as scorer adds cross-lab independence from the Qwen synthesis model. Note: the scorer and synthesis model should ideally be from different ecosystems, and `qwen3.7-max` is the synthesis model — keeping scoring on Meta/Llama strengthens this invariant.

Confirm these assignments by verifying the scoring model is from a different ecosystem than the synthesis model in each preset where they are applied.

#### Tests

```python
# tests/unit/test_registry.py

from reasoner.infrastructure.llm.registry import _MODEL_WHITELIST, _REGISTRY


def test_new_models_in_whitelist():
    assert "nvidia-nemotron-nano-8b" in _MODEL_WHITELIST
    assert "llama-3.3-70b" in _MODEL_WHITELIST


def test_new_models_in_registry():
    assert "nvidia-nemotron-nano-8b" in _REGISTRY
    assert "llama-3.3-70b" in _REGISTRY


def test_new_models_route_through_openrouter():
    assert _REGISTRY["nvidia-nemotron-nano-8b"]["cls"] == "openrouter"
    assert _REGISTRY["llama-3.3-70b"]["cls"] == "openrouter"


def test_new_models_correct_openrouter_ids():
    assert _REGISTRY["nvidia-nemotron-nano-8b"]["model"] == "nvidia/llama-3.1-nemotron-nano-8b-v1:free"
    assert _REGISTRY["llama-3.3-70b"]["model"] == "meta-llama/llama-3.3-70b-instruct:free"
```

---

## Sprint 4: Documentation & Structural Cleanup (45 min)

---

### S4-A — Document `ArticleFlow` as the 20th method in CLAUDE.md

**Files:** `CLAUDE.md`, `src/reasoner/domain/preset_registry.py`  
**Effort:** 20 min

#### Background

`WorkflowFactory` (factory.py line 58) registers `"article": ArticleFlow`. Investigation confirms this is a **fully-implemented, production-quality 20th method** with:

- A dedicated strategy class at `src/reasoner/application/flows/article.py`
- Phase implementations in `src/reasoner/application/flows/article_phases.py`
- 4 distinct phases: Retrieve Sources → Draft → Adversarial Verify → Refine → Synthesis

It is NOT dead code. The current confusion arises because `api/streaming.py:399–405` detects article requests via `is_article_request()` and overrides `state.method = "writing"` before dispatch — meaning article requests are silently routed to `WritingFlow` even though `ArticleFlow` exists. This is a latent routing bug, separate from the documentation task here.

#### CLAUDE.md Update

In the Reasoning Methods table in `CLAUDE.md`, add a row for Article after Writing:

```markdown
| **Article** | Structured article workflow: source retrieval, LLM drafting, adversarial verification, and iterative refinement |
```

Also update the preset count if the prose references a hardcoded number.

#### Preset Pair

`ArticleFlow` currently has no Budget/Premium preset pair in `preset_registry.py`. Add them in `_PRESET_CONFIGS`:

```python
# ── Article ─────────────────────────────────────────────────────────
{
    "id": "article-budget",
    "name": "Article (Budget)",
    "description": "4-phase article pipeline: source retrieval, drafting, adversarial verification, "
                   "and iterative refinement. Budget tier — fast and cost-effective.",
    "primary_id": "gemini-flash-lite",
    "routing": {
        "classification": "gpt-5-mini",
        "decomposition": "deepseek-v3",
        "constructive": "gemini-flash-lite",
        "destructive": "mistral-small",
        "systemic": "glm-5.1",
        "minimalist": "nvidia-nemotron-nano-8b",
        "scoring": "llama-3.3-70b",
        "synthesis": "qwen3.7-max",
    },
    "fallback_routing": {
        "classification": "glm-4-air",
        "decomposition": "glm-4-air",
        "constructive": "qwen3-plus",
        "destructive": "deepseek-v3",
        "systemic": "qwen3-plus",
        "minimalist": "glm-4-air",
        "scoring": "qwen3.5-flash",
        "synthesis": "qwen3.6-plus",
    },
    "method": "article",
    "price_tier": "budget",
},
{
    "id": "article-premium",
    "name": "Article (Premium)",
    "description": "4-phase article pipeline with premium models for high-quality long-form output.",
    "primary_id": "claude-sonnet",
    "routing": {
        "classification": "gpt-5-mini",
        "decomposition": "gpt-5",
        "constructive": "claude-sonnet",
        "destructive": "gpt-5",
        "systemic": "gemini-pro",
        "minimalist": "mistral-large-3",
        "scoring": "grok-3",
        "synthesis": "claude-sonnet",
    },
    "fallback_routing": {
        "classification": "gemini-flash-lite",
        "decomposition": "deepseek-v3",
        "constructive": "gpt-5",
        "destructive": "claude-sonnet",
        "systemic": "grok-3",
        "minimalist": "deepseek-v3",
        "scoring": "gemini-pro",
        "synthesis": "gpt-5",
    },
    "method": "article",
    "price_tier": "premium",
},
```

**Note:** Verify the exact field names (`method`, `price_tier`) against the existing preset dicts in `_PRESET_CONFIGS` before inserting — match the schema exactly.

#### Routing Bug Note

Also fix `api/streaming.py:399–405` to route article requests to `method="article"` instead of `method="writing"`:

```python
# Before (streaming.py ~400):
if is_article_request(state.problem):
    state.task_type = TaskType.TECHNICAL
    state.decomposition = ["article workflow"]
    state.method = "writing"          # ← wrong
    auto_selected_method = "writing"  # ← wrong

# After:
if is_article_request(state.problem):
    state.task_type = TaskType.TECHNICAL
    state.decomposition = ["article workflow"]
    state.method = "article"
    auto_selected_method = "article"
```

#### Tests

```python
def test_article_preset_pair_exists():
    from reasoner.domain.preset_registry import PRESETS
    assert "article-budget" in PRESETS
    assert "article-premium" in PRESETS

def test_article_preset_methods():
    from reasoner.domain.preset_registry import PRESETS
    assert PRESETS["article-budget"].method == "article"
    assert PRESETS["article-premium"].method == "article"
```

---

### S4-B — Replace stale preset count comment with a runtime assertion

**File:** `src/reasoner/domain/preset_registry.py:14`  
**Effort:** 5 min

#### Background

Line 14 says `"# Declarative configuration for all 24 presets (2 per method)."`. After adding the Article pair, the actual count will be larger. The comment will never be accurate.

#### Fix

Replace the comment and add a module-level assertion after the `PRESETS` dict is built:

```python
# Line 14 — replace:
# Declarative configuration for all 24 presets (2 per method).

# With:
# Declarative preset configurations — one Budget and one Premium entry per method.
```

After the line that builds `PRESETS` from `_PRESET_CONFIGS` (find it — it's the dict comprehension at the bottom of the file), add:

```python
# Invariant: presets must be paired (one Budget + one Premium per method).
assert len(PRESETS) % 2 == 0, (
    f"Expected an even number of presets (Budget+Premium pairs), "
    f"got {len(PRESETS)}. Add a matching preset to restore pairing. "
    f"Preset IDs: {sorted(PRESETS)}"
)
```

This fires at module import time — a misconfigured list fails loudly during startup rather than silently at runtime.

#### Test

```python
def test_preset_count_is_even():
    from reasoner.domain.preset_registry import PRESETS
    assert len(PRESETS) % 2 == 0, f"Odd preset count: {len(PRESETS)}"


def test_every_method_has_budget_and_premium():
    from reasoner.domain.preset_registry import PRESETS
    by_method: dict[str, list[str]] = {}
    for pid, preset in PRESETS.items():
        method = getattr(preset, "method", None) or ""
        by_method.setdefault(method, []).append(pid)
    for method, ids in by_method.items():
        tiers = {p.split("-")[-1] for p in ids}
        assert "budget" in tiers, f"Method '{method}' missing budget preset"
        assert "premium" in tiers, f"Method '{method}' missing premium preset"
```

---

### S4-C — Update CLAUDE.md Known Violations

**File:** `CLAUDE.md`  
**Effort:** 5 min

#### Changes

1. **Remove** the `domain/preset_core.py` violation entry (the import was removed; the violation no longer exists).
2. **Add** the streaming CQRS bypass as a tracked, flagged violation with its feature flag:

```markdown
**Known violations:**
- `api/streaming.py` routes pipeline execution directly through `PipelineOrchestrator` rather
  than `RunPipelineCommandHandler`. This is intentional for SSE latency reasons and is controlled
  by the `CQRS_BYPASS_STREAMING` feature flag (default `true`). Migration plan: `docs/ENHANCEMENT_PLAN.md` §C1.
- `application/flows/__init__.py` circular dependency with `api/serializers.py` was resolved by
  removing the import (currently commented out at the top of the file).
```

---

## Sprint 5: Performance — PipelineState Setter Loop (H1)

**File:** `src/reasoner/domain/pipeline_state.py`  
**Effort:** ~1 hour

---

### S5 — Remove 67 redundant `import dataclasses` loops from property setters

#### Background

Every property setter in `PipelineState` (67 setters, confirmed by grep) contains the following O(n_fields) loop:

```python
# Repeated verbatim inside every setter:
import dataclasses
for f in dataclasses.fields(self):
    if not hasattr(self, f.name):
        if f.default_factory is not dataclasses.MISSING:
            object.__setattr__(self, f.name, f.default_factory())
        elif f.default is not dataclasses.MISSING:
            object.__setattr__(self, f.name, f.default)
```

This loop:
1. Re-imports `dataclasses` on every setter call (no-op at runtime but unnecessary name resolution on every call).
2. Calls `dataclasses.fields(self)` which walks the class's `__dataclass_fields__` dict — O(n_fields) per invocation.
3. Is called for **every attribute assignment** across all 67 properties throughout an entire pipeline run (hundreds of writes per run).

The loop's intent is to initialize missing fields on deserialized/resumed state objects. However, for fully-initialized instances (the normal case), all fields are already set by `__init__` / `__post_init__` — the loop is pure overhead.

`dc_fields` is already imported at the top of the file (line 12):
```python
from dataclasses import dataclass, field, asdict, fields as dc_fields
```
So the per-setter `import dataclasses` is doubly redundant.

#### Implementation

**Step 1** — Add `_ensure_fields_initialized()` to `PipelineState` as a new method. Place it immediately after `__post_init__()`:

```python
def _ensure_fields_initialized(self) -> None:
    """Initialize any dataclass fields that are missing on deserialized / resumed instances.

    Called from property setters. For fully-initialized instances (the normal path),
    the _initialized guard makes this a no-op — O(1) instead of O(n_fields).

    The full scan only runs once per deserialized instance: the first setter call
    that triggers on a partially-loaded state object.
    """
    if getattr(self, '_initialized', False):
        return
    for f in dc_fields(self):
        if not hasattr(self, f.name):
            if f.default_factory is not dataclasses.MISSING:
                object.__setattr__(self, f.name, f.default_factory())
            elif f.default is not dataclasses.MISSING:
                object.__setattr__(self, f.name, f.default)
    object.__setattr__(self, '_initialized', True)
```

**Note:** `dc_fields` is already in scope at module level. The `dataclasses.MISSING` sentinel reference needs `import dataclasses` which is also already present via `from dataclasses import dataclass, field, asdict, fields as dc_fields` — but `MISSING` is not re-exported by that import. Add it explicitly:

```python
# Update line 12:
from dataclasses import dataclass, field, asdict, fields as dc_fields, MISSING as _DC_MISSING
```

Then use `_DC_MISSING` instead of `dataclasses.MISSING` in `_ensure_fields_initialized()` to avoid needing the module reference.

**Step 2** — At the very end of `__init__`, after `self.__post_init__()`, set the initialized flag:

```python
# End of __init__, after self.__post_init__():
object.__setattr__(self, '_initialized', True)
```

**Step 3** — Replace every occurrence of the 7-line loop in all 67 setters with a single method call. This is a mechanical, safe transformation — the method does exactly what the loop does, with the same semantics:

```python
# Every setter currently ends with:
import dataclasses
for f in dataclasses.fields(self):
    if not hasattr(self, f.name):
        if f.default_factory is not dataclasses.MISSING:
            object.__setattr__(self, f.name, f.default_factory())
        elif f.default is not dataclasses.MISSING:
            object.__setattr__(self, f.name, f.default)

# Replace with:
self._ensure_fields_initialized()
```

Use a sed-based replacement or a Python script to make this transformation uniform across all 67 occurrences rather than editing manually. A script approach is more reliable and leaves no stale copies:

```python
# scripts/fix_state_setters.py
import re
import pathlib

PATH = pathlib.Path("src/reasoner/domain/pipeline_state.py")
src = PATH.read_text(encoding="utf-8")

OLD_BLOCK = (
    "\n        # v3.1: Initialize dataclass fields with defaults that weren't explicitly set\n"
    "        import dataclasses\n"
    "        for f in dataclasses.fields(self):\n"
    "            if not hasattr(self, f.name):\n"
    "                if f.default_factory is not dataclasses.MISSING:\n"
    "                    object.__setattr__(self, f.name, f.default_factory())\n"
    "                elif f.default is not dataclasses.MISSING:\n"
    "                    object.__setattr__(self, f.name, f.default)"
)
NEW_BLOCK = "\n        self._ensure_fields_initialized()"

count = src.count(OLD_BLOCK)
assert count >= 60, f"Expected ≥60 occurrences, found {count}. Check the pattern."
patched = src.replace(OLD_BLOCK, NEW_BLOCK)
PATH.write_text(patched, encoding="utf-8")
print(f"Replaced {count} occurrences.")
```

Run: `python scripts/fix_state_setters.py` then verify the diff looks correct before committing.

**Step 4** — Verify `PipelineState.load()` (the deserialization path for `--resume`). Check that it either:
- Does NOT call `object.__setattr__(self, '_initialized', True)` before all fields are populated (so the first setter call after load will still trigger the full scan), OR
- Explicitly calls `state._ensure_fields_initialized()` after loading is complete.

The correct behavior is the latter — call `_ensure_fields_initialized()` explicitly at the end of `load()` so the flag is set cleanly before any user code accesses the state.

#### Tests

```python
# tests/unit/test_pipeline_state_performance.py

from reasoner.domain.pipeline_state import PipelineState


def test_initialized_flag_is_set_after_init():
    state = PipelineState(problem="test")
    assert getattr(state, '_initialized', False) is True


def test_ensure_fields_is_noop_after_init():
    """For a fully-initialized instance, _ensure_fields_initialized must not walk dc_fields."""
    state = PipelineState(problem="test")
    # Patch dc_fields to count calls
    import reasoner.domain.pipeline_state as mod
    call_count = 0
    original = mod.dc_fields

    def counting_dc_fields(cls):
        nonlocal call_count
        call_count += 1
        return original(cls)

    mod.dc_fields = counting_dc_fields
    try:
        state.problem = "changed"
        state.language = "French"
        state.task_type_rationale = "test rationale"
    finally:
        mod.dc_fields = original

    assert call_count == 0, (
        f"dc_fields was called {call_count} times on a fully-initialized state. "
        "The _initialized guard is not working."
    )


def test_ensure_fields_runs_once_on_partial_state():
    """On a resumed/partial state (no _initialized flag), the scan runs once then stops."""
    state = PipelineState(problem="test")
    object.__setattr__(state, '_initialized', False)  # simulate partial state

    import reasoner.domain.pipeline_state as mod
    call_count = 0
    original = mod.dc_fields

    def counting_dc_fields(cls):
        nonlocal call_count
        call_count += 1
        return original(cls)

    mod.dc_fields = counting_dc_fields
    try:
        state.problem = "changed"       # triggers scan once, sets _initialized = True
        state.language = "French"       # no-op scan
        state.task_type_rationale = "x" # no-op scan
    finally:
        mod.dc_fields = original

    assert call_count == 1, (
        f"dc_fields was called {call_count} times. Expected exactly 1 (first setter only)."
    )


def test_resume_compatibility():
    """State round-tripped through save/load must be fully functional after reload."""
    import tempfile, pathlib
    state = PipelineState(problem="test resume", preset_name="multi-perspective-budget")
    state.language = "French"
    state.task_type_rationale = "test"

    with tempfile.TemporaryDirectory() as d:
        path = str(pathlib.Path(d) / "state.json")
        state.save(path)
        loaded = PipelineState.load(path)

    assert loaded.problem == "test resume"
    assert loaded.language == "French"
    # Setters must work on the loaded state without errors
    loaded.language = "English"
    assert loaded.language == "English"
```

---

## Execution Order Summary

| # | ID | File(s) | Effort | Sprint |
|---|----|---------|--------|--------|
| 1 | S1-A | `core/rerank.py:354` | 5 min | 1 |
| 2 | S1-B | `core/rerank.py:220` | 2 min | 1 |
| 3 | S2 | `flows/search_phases.py`, `settings.py` | ~1 hr | 2 |
| 4 | S3 | `infrastructure/llm/registry.py` | 10 min | 3 |
| 5 | S4-A | `CLAUDE.md`, `preset_registry.py`, `streaming.py` | 20 min | 4 |
| 6 | S4-B | `preset_registry.py` | 5 min | 4 |
| 7 | S4-C | `CLAUDE.md` | 5 min | 4 |
| 8 | S5 | `domain/pipeline_state.py`, `scripts/fix_state_setters.py` | ~1 hr | 5 |

**Total:** ~3.5 hours of implementation + tests.

## Rollback Notes

- **S1-A, S1-B** — pure bug fixes, no behavioral change in the normal path.
- **S2** — fully gated by `SEMANTIC_RERANK_VETTING=false` (default). Zero impact on existing deployments until explicitly enabled.
- **S3** — adding registry entries only; existing presets are unchanged. No impact until presets are updated.
- **S4-A** — the `streaming.py` article routing fix changes behavior for article-detected prompts. If the writing method is preferred, revert only that line and keep the preset additions.
- **S4-B** — the `assert` runs at import time. If any preset configuration is wrong it blocks startup. This is the intended failure mode — fail loudly rather than silently serve broken presets.
- **S5** — backward-compatible with `--resume` via the `_initialized` flag guard. Test `test_resume_compatibility` must pass before merging.
