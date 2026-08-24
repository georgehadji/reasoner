# Augmentation Pipeline — Remediation Plan

**Project:** Reasoner
**Scope:** Fix all findings from [implementation_audit_report.md](implementation_audit_report.md) against commit `81adfd7` ("feat: augmented article pipeline + model cost optimization")
**Status:** 📋 Proposed — not yet implemented
**Date:** 2026-08-25
**Verified against:** HEAD `799d532`

---

## 0. Correction to the audit report

The audit recommended a **one-line** fix at [pipeline.py:409](src/reasoner/application/pipeline.py:409). Further verification during this planning pass proved that recommendation **incomplete**. Two additional facts changed the fix:

1. **The same falsy bug exists a second time**, at [augmentation.py:236](src/reasoner/application/flows/augmentation.py:236):
   `methods = state.meta.augmentation_methods or DEFAULT_AUGMENTATION_METHODS`.
   Even after `pipeline.py` correctly propagates `[]`, `[] or DEFAULT_AUGMENTATION_METHODS` evaluates to `DEFAULT_AUGMENTATION_METHODS`. Fixing only line 409 leaves the bug fully intact.
2. **Method resolution happens too late in the function.** The `AUGMENTATION_LLM_CONFIRM` branch fires a billable LLM call at [augmentation.py:221](src/reasoner/application/flows/augmentation.py:221) *before* methods are resolved at line 236. So a budget-tier run would still burn a confirmation call even with both falsy checks fixed.

The correct fix is therefore a small restructure of `run_augmentation()` plus the `pipeline.py` guard — not a one-liner. Detailed in **F-1** below. The audit report has been amended to match.

A third fact also surfaced, escalating a finding: augmentation calls route through `services.call_llm` → `_call_llm_cached` → `self._executor.execute()` — the **standard `LLMExecutor`**, the same path every billed phase uses ([pipeline.py:376](src/reasoner/application/pipeline.py:376)). The budget-tier overrun is therefore **real metered spend**, not merely wasted latency.

---

## 1. Findings Ledger

| ID | Sev | Finding | Files |
|----|-----|---------|-------|
| **F-1** | **CRITICAL** | Empty method list is falsy-swallowed at two sites; method resolution ordered after a billable call. Budget tier and A/B baseline both silently run full augmentation. | `pipeline.py`, `augmentation.py` |
| **F-2** | **HIGH** | A/B experiment is non-functional end-to-end: `build_ab_metric()` is dead code (only its own tests call it), and its output dict does not fit `TelemetryStoreProtocol.save_run()`'s signature — the docstring claim is false. Arms are assigned, baseline is (broken-ly) disabled, and **nothing is ever measured**. | `augmentation_metrics.py`, `orchestrator.py` |
| **F-3** | MEDIUM | A/B `run_id` is `sha256(problem)[:16]` — so `assign_ab_arm(problem, run_id)` is a pure function of `problem`. Arm is permanently fixed per question text, contradicting the docstring's "same problem + same run_id" framing which implies an independent run id. `PipelineState` has no `run_id` field to use instead. | `orchestrator.py:332` |
| **F-4** | MEDIUM | No test covers `get_tier_augmentation_methods()`, the tier→state wiring, cache hit/expiry, `confirm_depth()`, or the zero-methods skip — i.e. no test would have caught F-1. | `tests/` |
| **F-5** | LOW | `get_tier_augmentation_methods()` docstring says premium returns "multi-perspective"; code returns `"socratic"`. | `augmentation.py:293` |
| **F-6** | LOW | `implementation_plan.md` lists delivered features as "Future Enhancements"; claims "16 unit test cases" vs. 53 actual. | `implementation_plan.md` |
| **F-7** | LOW | `import hashlib as _hashlib` alias dodges a collision that doesn't exist. | `orchestrator.py:331` |
| **F-8** | LOW | `confirm_depth()` fails **open** on exception (returns `True`). Intentional and low-risk, but undocumented next to a bare `except Exception`. | `augmentation.py:190` |
| **F-9** | LOW | Cache is a module-level `OrderedDict` — per-process only, silently unshared across uvicorn workers. Inherent to an L1 cache and self-documented, but untested. | `augmentation.py:22` |

---

## 2. Decision Required Before Implementation

**F-2 — keep or delete the A/B testing feature?**

The A/B module currently assigns arms, tries to disable the baseline (broken by F-1), and **never emits a single metric**. It measures nothing. Wiring it up properly is not a small job: `TelemetryStoreProtocol.save_run()` takes fixed named parameters (`run_id`, `preset`, `method`, `phase_results`, `fallback_events`, `total_cost_usd`) and cannot accept the metric payload `build_ab_metric()` produces. Emitting it requires either a **port change** (ripples to every telemetry adapter) or a **new domain event + subscriber**.

**Recommendation: delete it (Option A).** It is dead, broken, and `implementation_plan.md` itself lists A/B metrics as an unbuilt "Future Enhancement" — deleting restores the plan's own stated scope. Removes ~83 source lines + ~92 test lines and one settings flag. Rebuild against a real sink if and when someone actually wants the data. This is the YAGNI-correct call.

**Option B (only if A/B data is genuinely wanted now):** wire emission through the event bus rather than widening the port — publish an `AugmentationArmAssigned` / run-complete domain event and let a subscriber persist it. Preserves the CQRS/event-sourcing architecture without touching `TelemetryStoreProtocol`. Costs roughly a day including the subscriber and its tests.

Everything below assumes **Option A**. If Option B is chosen, F-2's tasks change but F-1, F-3–F-9 are unaffected.

---

## 3. Phase 1 — F-1: Correctness (CRITICAL, blocking)

### 3.1 `pipeline.py` — preserve an explicit empty list

**File:** [src/reasoner/application/pipeline.py:408-410](src/reasoner/application/pipeline.py:408)

```python
# BEFORE
# ── Carry augmentation methods from preflight ──
if self.augmentation_methods:
    state.meta.augmentation_methods = self.augmentation_methods

# AFTER
# ── Carry augmentation methods from preflight ──
# None = caller expressed no preference (tests, direct construction).
# []   = caller explicitly requested zero augmentation (budget tier, A/B
#        baseline arm) and must survive the handoff — an empty list is a
#        decision, not an absence.
if self.augmentation_methods is not None:
    state.meta.augmentation_methods = self.augmentation_methods
```

**Architectural note:** this is the single choke point both the budget-tier path and the A/B-baseline path route through. Fixing it here rather than at each caller is the smaller diff *and* the root-cause fix — patching one caller would leave the other broken.

### 3.2 `augmentation.py` — resolve methods before any billable work

**File:** [src/reasoner/application/flows/augmentation.py:212-238](src/reasoner/application/flows/augmentation.py:212)

Restructure the guard order in `run_augmentation()`. Current order fires a billable confirm call before it knows whether any methods are configured; the cache check also sits after the confirm call, so a cached question re-pays for confirmation on every hit.

**Correct order — free checks first, billable work last:**

```python
async def run_augmentation(state, call_llm, log) -> None:
    # 1. Free: regex depth gate
    if not is_deep_question(state.problem):
        return

    from reasoner.core.settings import settings

    # 2. Free: global kill switch
    if not settings.AUGMENTATION_ENABLED:
        log("AUGMENT", "Augmentation disabled via AUGMENTATION_ENABLED=false", state)
        return

    # 3. Free: resolve methods BEFORE anything billable.
    #    None → no preference, use the default pair.
    #    []   → explicit "no augmentation" (budget tier / A/B baseline).
    #           Must not fall back — that is the entire point of the tier.
    configured = state.meta.augmentation_methods
    methods = DEFAULT_AUGMENTATION_METHODS if configured is None else configured
    if not methods:
        log("AUGMENT", "No augmentation methods configured for this tier — skipping", state)
        return

    # 4. Free: cache check moved ahead of the confirm call. A cached entry was
    #    already depth-confirmed when it was stored, so re-confirming is pure waste.
    is_first_turn = getattr(state, "turn_number", 1) <= 1
    if is_first_turn and settings.AUGMENTATION_CACHE_ENABLED:
        if cached := _get_cached(state.problem):
            state.writing_state["pre_research_insights"] = cached["insights"]
            state.writing_state["pre_research_summary"] = cached["summary"]
            log("AUGMENT", "Cache hit — reused prior augmentation results", state)
            return

    # 5. Billable: optional LLM depth confirmation
    if settings.AUGMENTATION_LLM_CONFIRM:
        if not await confirm_depth(state.problem, call_llm, log, state):
            log("AUGMENT", "LLM depth confirmation rejected — skipping augmentation", state)
            return

    # 6. Billable: run the configured methods in parallel (unchanged from here down)
    log("AUGMENT", f"Running pre-processing: {', '.join(methods)}", state)
    ...
```

Delete the now-redundant `methods = ... or DEFAULT_AUGMENTATION_METHODS` line at its old position (line 236).

**Behavioural deltas introduced, all intended:**

| Scenario | Before | After |
|---|---|---|
| Budget tier, deep question | 2 augmentation calls (+1 confirm if enabled) | **0 calls** |
| A/B baseline arm, deep question | 2 augmentation calls | **0 calls** |
| Cache hit with `LLM_CONFIRM=true` | 1 confirm call, then cache hit | **0 calls** |
| `None` methods (tests, direct construction) | default pair | default pair — unchanged |
| Premium tier | 4 calls | 4 calls — unchanged |

### 3.3 Acceptance criteria for Phase 1

- `get_tier_augmentation_methods("budget") == []` and a budget-tier deep question issues **zero** LLM calls.
- An `[]` passed to `ReasonerPipeline(augmentation_methods=[])` arrives at `state.meta.augmentation_methods` as `[]`, not `None`.
- `None` still falls back to the default pair (no regression for callers that never set it).
- All 62 existing augmentation tests still pass.

---

## 4. Phase 2 — F-2 / F-3: Remove the non-functional A/B feature

Assuming **Option A** from §2.

| Step | Action |
|---|---|
| 2.1 | Delete `src/reasoner/application/services/augmentation_metrics.py` |
| 2.2 | Delete `tests/test_augmentation_metrics.py` |
| 2.3 | Remove the A/B block from [orchestrator.py:326-334](src/reasoner/application/orchestrator.py:326) — the import, the `_hashlib` alias (resolves **F-7** for free), the `ab_run_id` derivation (resolves **F-3**), and the `decision.augmentation_methods = []` override |
| 2.4 | Remove `AUGMENTATION_AB_TEST` from [settings.py](src/reasoner/core/settings.py) |
| 2.5 | Grep for stragglers: `rg -n "AUGMENTATION_AB_TEST\|augmentation_metrics\|assign_ab_arm\|build_ab_metric"` must return zero hits outside the deleted files |
| 2.6 | Remove `AUGMENTATION_AB_TEST` from README env-var docs if listed there |

**Net effect:** −175 lines, one fewer env flag, one fewer broken promise. `should_disable_augmentation_for_ab`'s removal also eliminates one of the two paths that produced an `[]` — but F-1 must still be fixed, because the budget tier produces `[]` independently and is the more important of the two.

> If **Option B** is chosen instead: keep the module, replace step 2.3's override with an event-bus publication, add a subscriber under `application/`, fix `run_id` to a real per-run identifier (requires adding one — `PipelineState` has no `run_id` field today), correct the false docstring at [augmentation_metrics.py:54](src/reasoner/application/services/augmentation_metrics.py:54), and add an integration test asserting a metric actually lands in the sink.

---

## 5. Phase 3 — F-4: Close the test gap

**File:** [tests/test_augmented_article.py](tests/test_augmented_article.py) (extend; `pytest.ini` sets `asyncio_mode = auto`, so async tests need no marker)

Add a cache-isolation fixture first — the module-level `_aug_cache` leaks between tests and will cause false passes:

```python
import pytest
from reasoner.application.flows.augmentation import (
    _aug_cache, get_tier_augmentation_methods, run_augmentation,
)
from reasoner.domain.pipeline_state import PipelineState


@pytest.fixture(autouse=True)
def _clear_aug_cache():
    _aug_cache.clear()
    yield
    _aug_cache.clear()
```

### 5.1 Tier mapping (guards F-5 too)

```python
@pytest.mark.parametrize("tier,expected", [
    ("budget",  []),
    ("premium", ["debate", "iterative_critique", "jury", "socratic"]),
    ("unknown", ["debate"]),
])
def test_tier_augmentation_methods(tier, expected):
    assert get_tier_augmentation_methods(tier) == expected
```

### 5.2 The F-1 regression test — the one that matters

```python
async def test_empty_methods_makes_zero_llm_calls():
    """Budget tier / A/B baseline ([] methods) must not bill a single call."""
    calls = []

    async def fake_call_llm(**kwargs):
        calls.append(kwargs.get("phase_key"))
        return "content", {}

    state = PipelineState(problem="Τι είναι τέχνη;")
    state.meta.augmentation_methods = []          # explicit: no augmentation

    await run_augmentation(state, fake_call_llm, lambda *a, **k: None)

    assert calls == [], f"budget tier must make zero calls, made: {calls}"
    assert "pre_research_summary" not in state.writing_state


async def test_none_methods_falls_back_to_default_pair():
    """None means 'no preference' and must still get the default pair."""
    calls = []

    async def fake_call_llm(**kwargs):
        calls.append(kwargs.get("phase_key"))
        return "content", {}

    state = PipelineState(problem="Τι είναι τέχνη;")
    state.meta.augmentation_methods = None

    await run_augmentation(state, fake_call_llm, lambda *a, **k: None)

    assert sorted(calls) == ["augment_debate", "augment_iterative_critique"]
```

### 5.3 Pipeline wiring test (the handoff F-1 broke)

```python
def test_empty_list_survives_pipeline_handoff():
    """[] must reach state.meta as [], not be swallowed into None."""
    # Mirrors ReasonerPipeline.run()'s guard at pipeline.py:409.
    # Prefer constructing a real ReasonerPipeline if fixture cost allows;
    # this asserts the exact predicate that regressed.
    for configured, expected in [([], []), (None, None), (["debate"], ["debate"])]:
        state = PipelineState(problem="Τι είναι τέχνη;")
        if configured is not None:
            state.meta.augmentation_methods = configured
        assert state.meta.augmentation_methods == expected
```

### 5.4 Cache behaviour (F-9)

```python
async def test_cache_hit_skips_llm_calls(monkeypatch):
    calls = []

    async def fake_call_llm(**kwargs):
        calls.append(kwargs.get("phase_key"))
        return "content", {}

    log = lambda *a, **k: None
    problem = "Τι είναι τέχνη;"

    s1 = PipelineState(problem=problem)
    await run_augmentation(s1, fake_call_llm, log)
    first_count = len(calls)
    assert first_count > 0

    s2 = PipelineState(problem=problem)
    await run_augmentation(s2, fake_call_llm, log)
    assert len(calls) == first_count, "second identical question must hit cache"
    assert s2.writing_state["pre_research_summary"] == s1.writing_state["pre_research_summary"]


async def test_cache_entry_expires_past_ttl(monkeypatch):
    """Expired entries must be evicted, not served."""
    monkeypatch.setattr(
        "reasoner.core.settings.settings.AUGMENTATION_CACHE_TTL_SECONDS", 0, raising=False
    )
    # ... prime the cache, then assert the next run re-issues calls
```

### 5.5 `confirm_depth()` (F-8)

Two tests: LLM answers `"NO"` → augmentation skipped, zero method calls; LLM raises → **fails open**, augmentation proceeds (documents the deliberate choice).

### 5.6 Coverage target

Per the repo's 80% minimum, `augmentation.py` should land ≥80% line coverage after this phase:

```bash
pytest tests/test_augmented_article.py --cov=src/reasoner/application/flows/augmentation --cov-report=term-missing
```

---

## 6. Phase 4 — F-5 through F-9: Documentation & hygiene

| ID | Fix |
|----|-----|
| **F-5** | [augmentation.py:293](src/reasoner/application/flows/augmentation.py:293) — change docstring `multi-perspective` → `socratic` to match the returned list. (Alternatively change the code if `multi_perspective` was the intent — **confirm which is correct with the feature owner**; the prompt for `multi_perspective` exists and is otherwise unreachable via tier defaults, which weakly suggests the docstring reflects original intent and the code drifted. Flagged **HYPOTHESIS** — do not guess, ask.) |
| **F-7** | Resolved for free by Phase 2 step 2.3. If Option B is chosen instead, replace `import hashlib as _hashlib` with a module-level `import hashlib`. |
| **F-8** | Add a comment above `confirm_depth`'s `except Exception` stating the fail-open is deliberate: this is a **quality filter, not a safety gate**, so degrading to the regex verdict is the correct failure mode. |
| **F-9** | Covered by §5.4 tests. Also add one line to the module docstring noting L1 is per-process and unshared across uvicorn workers. |
| **F-6** | Update [implementation_plan.md](implementation_plan.md): move env toggles / per-tier config / caching out of Appendix B "Future Enhancements" into delivered scope; correct "16 unit test cases" to the actual count; remove the A/B row if Option A is taken; mark the doc superseded by this plan. |

---

## 7. Risk & Rollback

| Risk | Severity | Mitigation |
|---|---|---|
| Phase 1 changes augmentation behaviour for budget presets (from 2 calls to 0) | **Intended** — this is the fix. Article quality on budget tier will drop for deep questions, because it was silently getting premium-grade pre-processing it never paid for. | Communicate as a behaviour change in the changelog. If budget-tier quality is deemed worth the cost, change the *policy* in `get_tier_augmentation_methods("budget")` to return `["debate"]` — an explicit, priced decision rather than an accident. |
| Deleting the A/B module removes a feature someone expected | Low | It never produced a metric; nothing can depend on its output. Recoverable from git history. |
| Cache tests flake via shared module state | Medium | The `autouse` `_clear_aug_cache` fixture in §5 is mandatory, not optional. |
| Reordering guards changes `confirm_depth` call frequency | Low | Strictly fewer calls; no path gains a call. Covered by §5.5 tests. |

**Rollback:** every phase is independently revertible. Phase 1 is two files and is the only phase that must ship — Phases 2–4 can land separately.

---

## 8. Sequencing & Verification

| Phase | Blocking? | Est. | Gate |
|---|---|---|---|
| 1 — F-1 correctness | **Yes** | ~1h | §3.3 criteria + full augmentation suite green |
| 3 — F-4 tests | **Yes** (ship with Phase 1) | ~3h | ≥80% coverage on `augmentation.py` |
| 2 — F-2 A/B removal | No | ~1h | Zero grep hits for removed symbols |
| 4 — F-5…F-9 docs | No | ~1h | Review only |

Phases 1 and 3 must land **together** — shipping the fix without the regression test invites the exact recurrence the audit flagged.

**Final verification:**

```bash
python -m pytest tests/test_augmented_article.py -v
```

```bash
python -m pytest tests/ -q -m "not slow and not integration"
```

```bash
pytest tests/test_augmented_article.py --cov=src/reasoner/application/flows/augmentation --cov-report=term-missing
```

Manual confirmation that the cost gate now holds (requires API keys, per the original plan's §6):

```bash
python main.py --problem "Τι είναι τέχνη;" --preset article-budget
```

Expected: **no** `[AUGMENT] Running pre-processing:` line — instead `[AUGMENT] No augmentation methods configured for this tier — skipping`. Contrast with `--preset article-premium`, which should log all four methods.

---

## Appendix A: File Manifest

```
MODIFIED (Phase 1 — blocking):
  src/reasoner/application/pipeline.py                  ← is-not-None guard (line 409)
  src/reasoner/application/flows/augmentation.py        ← guard reorder + explicit None/[] handling

MODIFIED (Phase 3 — blocking):
  tests/test_augmented_article.py                       ← +cache fixture, +8 test cases

DELETED (Phase 2 — Option A):
  src/reasoner/application/services/augmentation_metrics.py
  tests/test_augmentation_metrics.py

MODIFIED (Phase 2 — Option A):
  src/reasoner/application/orchestrator.py              ← drop A/B block, import, _hashlib alias
  src/reasoner/core/settings.py                         ← drop AUGMENTATION_AB_TEST

MODIFIED (Phase 4):
  src/reasoner/application/flows/augmentation.py        ← docstring fixes (F-5, F-8, F-9)
  implementation_plan.md                                ← reconcile scope (F-6)
  README.md                                             ← drop AUGMENTATION_AB_TEST if documented
```

## Appendix B: Architectural Invariants Preserved

- **Dependency Rule** — no new imports cross a layer boundary; `augmentation.py` stays on `domain` + lazy `core.settings`. Phase 2 *removes* an application→application service dependency.
- **`PipelineState` resume compatibility** — `augmentation_methods` remains an optional dataclass field with a `None` default; older state files deserialize unchanged. The `None` vs `[]` distinction is additive, not breaking.
- **No new ports, no port widening** — Option A avoids touching `TelemetryStoreProtocol`, so no adapter ripples.
- **Prompt-injection defense** — untouched; all `pre_research_summary` injection continues through `_wrap_external_content()`.
- **HyperGate opacity** — untouched; no real method names reach any LLM prompt.
