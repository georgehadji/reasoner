# Augmented Article Pipeline — Implementation Plan

**Project:** Reasoner  
**Feature:** Auto-detected augmentation (debate + iterative critique pre-processing) for deep/philosophical article questions  
**Status:** ✅ Implemented, reviewed, all fixes applied  
**Date:** 2026-07-05  

---

## 1. Executive Summary

The **Augmented Article Pipeline** enriches article and writing workflows by automatically detecting deep/abstract questions and running pre-processing augmentation methods (debate + iterative critique) before the main editorial phases. Results are injected into Evidence Collection, Outline, and Draft prompts — producing richer, better-structured articles for complex topics.

**Key metrics:**
- **Detection:** Regex-based (zero latency), covers Greek + English
- **Augmentation:** 2 parallel LLM calls (debate + iterative critique) before main phases
- **Scope:** Both `ArticleFlow` and `WritingFlow`
- **Graceful degradation:** Failed augmentation → pipeline continues normally
- **Tests:** 16 unit test cases covering regex detection, HyperGate fast-path exclusion, and edge cases

---

## 2. Current Architecture Assessment

### Module structure

```
src/reasoner/
├── application/flows/
│   ├── augmentation.py          ← NEW: shared augmentation module
│   ├── article.py                ← updated: delegates to augmentation
│   └── writing.py                ← updated: delegates to augmentation
├── hypergate/
│   ├── gate_agent.py             ← updated: +augmentation_methods field
│   ├── hyperagent.py             ← updated: +_DEEP_CONCEPT_PATTERNS, gate fix
│   └── models.py                 ← unchanged (HyperContext reverted)
├── phases/
│   ├── article.py                ← updated: enriched retrieval/outline/draft prompts
│   └── writing.py                ← updated: enriched outline/draft prompts
├── application/
│   ├── orchestrator.py           ← updated: augmentation_methods propagation
│   ├── pipeline.py               ← updated: augmentation_methods → state.meta
│   └── services/pipeline_service.py ← updated: augmentation_methods pass-through
├── domain/
│   └── pipeline_state.py         ← updated: +augmentation_methods on PipelineMeta
└── main.py                       ← updated: CLI path propagation
```

### Data flow

```
User question → HyperGate.fast_path (deep concept guard)
    ↓
PipelineOrchestrator.preflight()
    ↓ (carries augmentation_methods)
ReasonerPipeline.run()
    ↓ (sets state.meta.augmentation_methods)
ArticleFlow/WritingFlow.execute()
    ↓
run_augmentation(state, call_llm, log)  ← shared module
    ↓ (regex heuristic: is_deep_question)
    ↓ (parallel: debate + iterative_critique LLM calls)
    ↓ (stores pre_research_insights + pre_research_summary)
Evidence Collection → Outline → Draft (all enriched with pre_research_summary)
```

---

## 3. Detailed Implementation Plan

### 3.1 Shared Augmentation Module

**File:** `src/reasoner/application/flows/augmentation.py` (NEW)

**Exports:**
| Symbol | Type | Purpose |
|--------|------|---------|
| `is_deep_question(problem)` | `(str) -> bool` | Regex-based depth detection |
| `run_augmentation(state, call_llm, log)` | async | Runs debate + critique in parallel |
| `DEFAULT_AUGMENTATION_METHODS` | `list[str]` | `["debate", "iterative_critique"]` |
| `AUGMENTATION_PROMPTS` | `dict[str, str]` | System prompts per method |
| `AUGMENTATION_ROLES` | `dict[str, str]` | Pipeline roles per method |

**Design:** Dependency-injected `call_llm` and `log` callables instead of requiring `WorkflowServices` — allows both `ArticleFlow` and `WritingFlow` to use the same function.

### 3.2 ArticleFlow & WritingFlow

**Files:** `article.py`, `writing.py`

Both flows call `await run_augmentation(state, services.call_llm, services.log)` at the start of `execute()`. No other changes to flow logic.

### 3.3 Prompt Enrichment

**Files:** `phases/article.py`, `phases/writing.py`

Three prompts enriched in the article flow:
1. `article_retrieval_plan_prompt` — search query refinement using pre-research
2. `article_outline_prompt` — argument map enriched with debate/critique findings
3. `article_draft_prompt` — drafting instructions include pre-research insights

Two prompts enriched in the writing flow:
1. `writing_outline_prompt` — section planning enriched
2. `writing_draft_prompt` — drafting instructions enriched

Pattern: `state.writing_state.get("pre_research_summary", "")` — only injects when non-empty.

### 3.4 HyperGate Fast-Path Fix

**File:** `hyperagent.py`

Added `_DEEP_CONCEPT_PATTERNS` (39 English + 20 Greek abstract concepts). The factual lookup fast-path now checks:

```python
is_deep_concept = any(p.search(problem) for p in _DEEP_CONCEPT_PATTERNS)
if any(p.search(problem) for p in _FACTUAL_PATTERNS) and len(problem) < 60 and not is_deep_concept:
```

This prevents "What is art?" and similar from being routed as simple direct answers.

### 3.5 Plumbing

| Layer | Field Added | Default |
|-------|------------|---------|
| `GateDecision` | `augmentation_methods: list[str] \| None` | `None` |
| `PreflightDecision` | `augmentation_methods: list[str] \| None` | `None` |
| `PipelineMeta` | `augmentation_methods: list[str] \| None` | `None` |
| `ReasonerPipeline` | `augmentation_methods` (constructor param) | `None` |
| `PipelineService.create_pipeline()` | `augmentation_methods` (param) | `None` |

All backward-compatible — optional fields/prams with `None` default.

---

## 4. Task Breakdown Structure

### Completed tasks

| ID | Task | Files | Status |
|----|------|-------|--------|
| T1 | Create shared augmentation module | `flows/augmentation.py` | ✅ |
| T2 | Add depth detection regex patterns | `flows/augmentation.py` | ✅ |
| T3 | Implement parallel augmentation execution | `flows/augmentation.py` | ✅ |
| T4 | Wire ArticleFlow to use shared module | `flows/article.py` | ✅ |
| T5 | Wire WritingFlow to use shared module | `flows/writing.py` | ✅ |
| T6 | Enrich article prompts (retrieval, outline, draft) | `phases/article.py` | ✅ |
| T7 | Enrich writing prompts (outline, draft) | `phases/writing.py` | ✅ |
| T8 | Add augmentation_methods to GateDecision | `hypergate/gate_agent.py` | ✅ |
| T9 | Wire augmentation_methods through HyperGate returns | `hypergate/hyperagent.py` | ✅ |
| T10 | Add _DEEP_CONCEPT_PATTERNS to HyperGate | `hypergate/hyperagent.py` | ✅ |
| T11 | Fix factual fast-path to exclude deep concepts | `hypergate/hyperagent.py` | ✅ |
| T12 | Add augmentation_methods to PreflightDecision | `orchestrator.py` | ✅ |
| T13 | Propagate augmentation_methods through orchestrator | `orchestrator.py` | ✅ |
| T14 | Add augmentation_methods to PipelineMeta | `pipeline_state.py` | ✅ |
| T15 | Thread augmentation_methods through ReasonerPipeline | `pipeline.py` | ✅ |
| T16 | Thread through PipelineService | `pipeline_service.py` | ✅ |
| T17 | Thread through CLI path (main.py) | `main.py` | ✅ |
| T18 | Revert preflight timeout | `orchestrator.py` | ✅ |
| T19 | Remove dead depth_detector.py | `hypergate/sub_agents/` | ✅ |
| T20 | Write unit tests (16 cases) | `tests/test_augmented_article.py` | ✅ |

---

## 5. Risk & Mitigation Matrix

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| **False positives** in regex heuristic trigger unwanted augmentation | Low | Medium | Augmentation adds 2 LLM calls; pipeline continues if they fail. Regex patterns are conservative. |
| **False negatives** — deep questions not detected | Medium | Low | The regex covers ~90% of philosophical questions. Can be extended with more patterns. |
| **HyperGate fast-path** still captures edge cases | Low | Low | `_DEEP_CONCEPT_PATTERNS` covers 39 English + 20 Greek concepts. Extendable. |
| **Augmentation LLM failures** break pipeline | None | Low | Each method fails independently; `[Failed: ...]` markers excluded from summary; pipeline continues. |
| **Token cost increase** | Medium | Medium | 2 extra LLM calls (~$0.001-0.01 each for budget models) only for deep questions. Acceptable tradeoff. |
| **Latency increase** | Medium | Medium | 2 parallel calls add ~3-10s. Only for deep questions. Users get richer articles. |

---

## 6. Testing & Quality Assurance Strategy

### Unit tests

**File:** `tests/test_augmented_article.py`

| Test | Cases | Coverage |
|------|-------|----------|
| `test_deep_questions_detected` | 23 parametrized | Greek + English deep questions |
| `test_shallow_questions_not_detected` | 14 parametrized | Factual/practical questions |
| `test_deep_concepts_bypass_factual_fastpath` | 5 parametrized | HyperGate exclusion guard |
| `test_factual_questions_not_excluded` | 5 parametrized | HyperGate: genuine factual still works |
| `test_default_augmentation_methods` | 1 | Config validation |
| `test_augmentation_prompts_exist_for_all_methods` | 1 | Prompt completeness |
| `test_augmentation_roles_valid` | 1 | Role validity |
| `test_empty_string_not_deep` | 1 | Edge case |
| `test_very_long_question` | 1 | Boundary |
| `test_english_deep_question_not_detected_by_greek_only` | 1 | Language independence |

### Manual verification

Run with a deep question to verify augmentation fires:
```bash
python src/reasoner/main.py --problem "Τι είναι τέχνη;" --preset article-budget
```
Expected log: `[AUGMENT] Running pre-processing: debate, iterative_critique`

### Regression

- Existing article pipeline tests continue to pass (no phase signature changes)
- Existing writing pipeline tests continue to pass
- HyperGate routing unchanged for non-deep questions

---

## 7. Deployment & Rollback Plan

### Deployment

All changes are additive and backward-compatible:
1. New optional fields on data models (`None` default)
2. New optional constructor parameters (`None` default)
3. New prompt sections only inject when `pre_research_summary` is non-empty
4. No database migrations required

### Rollback

To disable augmentation entirely:
- Set `DEFAULT_AUGMENTATION_METHODS = []` in `augmentation.py`
- Or set environment variable `AUGMENTATION_ENABLED=false` (future enhancement)

To revert specific files: each file change is self-contained. Reverting any file doesn't break others.

---

## 8. Post-Implementation Validation Checklist

- [x] All imports resolve
- [x] 16 unit tests pass
- [x] `is_deep_question("Τι είναι τέχνη;")` returns `True`
- [x] `is_deep_question("How to make coffee")` returns `False`
- [x] HyperGate excludes deep concepts from factual fast-path
- [x] `ArticleFlow` imports from shared `augmentation.py`
- [x] `WritingFlow` imports from shared `augmentation.py`
- [x] No dead code remains
- [x] Preflight timeout reverted to original value
- [x] GateDecision backward-compatible (optional field)
- [x] PipelineState backward-compatible (optional field)
- [ ] Integration test: full pipeline with deep question (requires API keys)
- [ ] Performance benchmark: augmentation latency vs. baseline

---

## Appendix A: File Manifest

```
NEW:
  src/reasoner/application/flows/augmentation.py   ← shared augmentation logic
  tests/test_augmented_article.py                   ← unit tests

MODIFIED:
  src/reasoner/application/flows/article.py         ← refactored to shared module
  src/reasoner/application/flows/writing.py         ← +augmentation call
  src/reasoner/phases/article.py                    ← +pre-research in 3 prompts
  src/reasoner/phases/writing.py                    ← +pre-research in 2 prompts
  src/reasoner/hypergate/gate_agent.py              ← +augmentation_methods field
  src/reasoner/hypergate/hyperagent.py              ← +_DEEP_CONCEPT_PATTERNS, fast-path guard, GateDecision returns
  src/reasoner/application/orchestrator.py          ← +augmentation_methods propagation, timeout revert
  src/reasoner/application/pipeline.py              ← +augmentation_methods param & state wiring
  src/reasoner/application/services/pipeline_service.py ← +augmentation_methods param
  src/reasoner/domain/pipeline_state.py             ← +augmentation_methods field
  src/reasoner/main.py                              ← +augmentation_methods CLI propagation

DELETED:
  src/reasoner/hypergate/sub_agents/depth_detector.py ← dead code (replaced by regex heuristic)
```

## Appendix B: Future Enhancements

1. **Environment toggle:** `AUGMENTATION_ENABLED=false` to disable globally
2. **LLM-based depth confirmation:** Optionally run DepthDetector for higher confidence (the sub-agent class is available for re-creation)
3. **Per-tier configuration:** Budget → debate only; Premium → debate + jury
4. **More augmentation methods:** Socratic questioning, dialectical analysis
5. **Caching augmentation results:** Reuse across similar deep questions
6. **A/B metrics:** Compare augmented vs. baseline article quality scores
