# Architecture Audit Remediation Plan

**Source:** ARCH-AUDIT-V2 Report (2026-07-05)  
**Project:** Reasoner v2.3  
**Status:** ✅ Phase 1 complete | 🔄 Phase 2 complete | ⬜ Phase 3 (FIX-1 pending)  
**Epistemic protocol:** Every claim follows EGFV — assertions cite source file:line

---

## 1. Severity Summary

| ID | Severity | Finding | Effort | Files |
|----|----------|---------|--------|-------|
| **F-3** | P1 | Module hot-reload (`_ensure_fresh_preset_service()`) breaks inline interpreters | Medium | `api/streaming.py`, `domain/preset_registry.py` |
| **F-1** | P2 | Two parallel phase-execution paths diverge | Large | `application/flows/runner.py`, `application/flows/phase_lifecycle.py` |
| **F-2** | P2 | Fire-and-forget `create_task` swallows exceptions | Small | `hypergate/hyperagent.py` |
| **F-8a** | P2 | 402 credit exhaustion crashes pipeline with no degradation | Medium | `infrastructure/llm/base.py`, `application/pipeline.py` |
| **F-8b** | P2 | Redis runtime fail-open vs startup hard-fail inconsistency | Small | `api/__init__.py` |
| **F-7** | P2 | Test coverage gaps in services + flows | Large | `tests/` |
| **F-5** | P3 | Stale synthesis comments (🇺🇸 OpenAI → 🇨🇳 Zhipu) | Trivial | `domain/preset_registry.py` |
| **F-6** | P3 | Dead `.claude/worktrees/` directories | Trivial | `.claude/worktrees/` |

---

## 2. Fix Plan

### FIX-3: Replace `_ensure_fresh_preset_service()` with DI-based invalidation (P1)

**File:** `api/streaming.py` + `domain/preset_registry.py`  
**Risk:** Medium — changes startup path in the critical SSE streaming endpoint  
**Approach:** The current approach deletes and re-imports Python modules (`del sys.modules[...]`; `importlib.reload()`) to ensure the preset registry is fresh for the first pipeline run. This is inherently unsafe for inline interpreters.

**Replacement:** Add a `PresetRegistry.reload()` method that resets the internal cache (`_get_preset_cache` / `_list_presets_cache`) without touching module state. The streaming entry point calls `reload()` instead of `_ensure_fresh_preset_service()`. This is safe for all consumers because:
- Only the registry's internal `_CACHE` dict is cleared
- No modules are deleted or re-imported
- Existing references (e.g., imported `get_preset` function) remain valid

```
Step 1: Add reload() classmethod to PresetRegistry or reset_cache() function to preset_registry.py
  - Clears _get_preset_cache and _list_presets_cache (LRU caches)
  - Safe: no sys.modules manipulation

Step 2: Replace _ensure_fresh_preset_service() call in api/streaming.py
  - Remove: del sys.modules + importlib.reload
  - Replace: PresetRegistry.reset_cache() or get_preset_service().refresh()

Step 3: Verify — run pipeline via streaming endpoint, confirm preset resolves correctly
```

**Verification:**
```bash
pytest tests/test_api_gate.py -v   # SSE entry point tests
pytest tests/integration/test_preset_pipeline.py -v -k "budget"   # Live pipeline through SSE
```

---

### FIX-1: Consolidate Dual Phase-Execution Paths (P2)

**Files:** `application/flows/runner.py`, `application/flows/phase_lifecycle.py`  
**Risk:** High — touches the core pipeline execution loop for every method  
**Approach:** The two paths (`WorkflowRunner.run_phase` and `PhaseLifecycleManager.execute_phase`) share the same logic: retry loop, timeout, quality evaluation, event publishing. Consolidate into a single `PhaseExecutor` class that both consumers call.

```
Step 1: Create application/flows/phase_executor.py
  - Single PhaseExecutor class with execute(phase_fn, state, services) -> PhaseRunResult
  - Merges: retry logic, timeout, quality eval (PhaseMonitor), event publishing
  - Both WorkflowRunner and PhaseLifecycleManager delegate to PhaseExecutor

Step 2: Refactor WorkflowRunner.run_phase() to use PhaseExecutor
  - Replace inline retry/timeout/quality blocks with PhaseExecutor.execute()
  - Verify: all flow tests pass (multi_perspective, debate, research, article, writing, coding)

Step 3: Refactor PhaseLifecycleManager.execute_phase() to use PhaseExecutor
  - Same replacement
  - Verify: SSE streaming path still emits correct phase events

Step 4: Remove duplicate logic from PhaseLifecycleManager
  - Delete methods that are now handled by PhaseExecutor

Step 5: Verify full suite
  - pytest tests/ -m "not slow and not integration"
  - pytest tests/integration/test_preset_pipeline.py -v -k "budget"
```

**Verification:**
```bash
pytest tests/test_article_pipeline.py -v
pytest tests/test_e2e_budget_presets_mock.py -v
```

---

### FIX-2: Add Error Handler to Fire-and-Forget Tasks (P2)

**File:** `hypergate/hyperagent.py:138`  
**Risk:** Low — the task is optional (L2 cache write); failures are already non-critical  
**Approach:** Wrap `create_task` with a small wrapper that logs exceptions at WARNING level instead of silently swallowing them.

```
Step 1: Add helper function in hypergate/hyperagent.py (or utils):
  def _safe_create_task(coro, name: str):
      task = asyncio.create_task(coro, name=name)
      task.add_done_callback(lambda t: 
          logger.warning("Background task '%s' failed: %s", name, t.exception())
          if t.exception() and not t.cancelled() else None
      )
      return task

Step 2: Replace asyncio.create_task(self._set_l2_cache(...)) with _safe_create_task
Step 3: Scan for other fire-and-forget create_task calls in the codebase:
  grep -rn "create_task" src/reasoner/ — apply same pattern to all

Step 4: Verify — existing HyperGate tests pass
  pytest tests/test_hypergate.py -v
```

---

### FIX-8a: Graceful Degradation on 402 Credit Exhaustion (P2)

**Files:** `infrastructure/llm/base.py`, `application/pipeline.py`  
**Risk:** Medium — changes error handling in the LLM call chain  
**Approach:** Catch `APIStatusError` with code 402 at the LLM provider level. Instead of crashing the pipeline, return a `[CREDIT_EXHAUSTED]` marker. The pipeline collects these markers and returns partial results with a warning.

```
Step 1: In infrastructure/llm/base.py, extend the retry/failure logic:
  - Catch openai.APIStatusError with code 402
  - Log WARNING with model name and remaining credits
  - Return a special sentinel string "[CREDIT_EXHAUSTED: {model_name}]"
  - Do NOT retry 402 errors (they won't recover without adding credits)

Step 2: In PhaseExecutor (or WorkflowRunner), handle the sentinel:
  - If phase returns "[CREDIT_EXHAUSTED...]", mark phase as WARNED (not FAILED)
  - Add to state.errors: "Phase {name} skipped: credit limit reached for {model}"
  - Continue pipeline with remaining phases (partial results)

Step 3: In the final synthesis, if credit_exhausted markers exist:
  - Append a notice to the output: "⚠️ Some phases were skipped due to API credit limits."
  - Return partial synthesis (what was completed before exhaustion)

Step 4: Verify — simulate 402 with a mock LLM provider
  pytest tests/test_end_to_end_edge_cases.py -v -k "credit"
```

---

### FIX-8b: Consistent Redis Failure Mode (P2)

**File:** `api/__init__.py:65`  
**Risk:** Low — changes production startup behavior  
**Approach:** The startup Redis probe is mandatory in production (hard fail). The runtime circuit breaker is fail-open. This inconsistency means the app refuses to start without Redis, but silently ignores Redis failures once running. Choose one policy:

**Decision:** Fail-closed everywhere. If Redis is critical enough to block startup, runtime failures should also deny requests. OR: soften startup to warn-and-continue (fail-open everywhere). The current mixed mode is the worst option.

**Recommendation:** Soften startup to warn-only in production. Redis is used for rate limiting and caching — neither is critical for correct pipeline operation (the rate limiter has an in-memory fallback).

```
Step 1: In api/__init__.py:65, change the Redis probe from hard-fail to WARNING:
  - Keep the probe (it surfaces config issues)
  - Replace raise RuntimeError with logger.warning + sentry capture
  - Add a health check endpoint /health that reports Redis status

Step 2: Ensure all Redis consumers already handle None/offline gracefully:
  - Rate limiter: already has in-memory fallback (RATE_LIMITER_REDIS_FAILURE_MODE)
  - Circuit breaker: already fail-open
  - Event store: defaults to SQLite when no DATABASE_URL
  - HyperGate L2 cache: already wrapped in try/except

Step 3: Verify — run pipeline with Redis intentionally unreachable
  REDIS_URL=redis://nonexistent:6379 python -m reasoner.main --problem "test" --preset article-budget
```

---

### FIX-7: Test Coverage Gaps (P2)

**Files:** `tests/` (new)  
**Risk:** Low — additive, no production code changes  
**Approach:** Add focused smoke tests for untested modules.

```
Step 1: tests/test_augmentation_metrics.py (NEW — 4 tests)
  - test_assign_ab_arm_deterministic: same input → same arm
  - test_assign_ab_arm_split: even/odd distribution
  - test_build_ab_metric_structure: correct metric keys
  - test_should_disable_augmentation_for_ab: env toggle gates correctly

Step 2: tests/test_phase_executor.py (NEW — 6 tests)
  - test_execute_success: phase completes, event published
  - test_execute_retry: quality fail → retry → success
  - test_execute_timeout: asyncio.wait_for triggers, phase marked failed
  - test_execute_critical_fail: critical phase failure stops pipeline
  - test_execute_non_critical_continue: non-critical failure continues
  - test_execute_credit_exhausted: 402 sentinel → partial result + warning

Step 3: tests/test_registry.py (NEW — 3 tests)
  - test_all_preset_ids_valid: every preset resolves without exception
  - test_all_model_keys_in_registry: every routing model key exists in LLM registry
  - test_lab_diversity_preserved: every premium preset has ≥ 4 distinct labs

Step 4: Extend existing test files (2 tests each)
  - tests/test_hypergate.py: +test_l2_cache_failure_graceful, +test_fire_and_forget_exception
  - tests/test_cqrs_parity.py: +test_pipeline_service_handles_augmentation_methods

Step 5: Verify
  pytest tests/test_augmentation_metrics.py tests/test_phase_executor.py tests/test_registry.py -v
```

---

### FIX-5: Stale Synthesis Comments (P3)

**File:** `domain/preset_registry.py`  
**Risk:** None — comment-only change  
**Approach:** Bulk replace `"🇺🇸 OpenAI — cross-bloc final voice"` with `"🇨🇳 Zhipu — cross-bloc final voice, $0.95/$3.00"` in all synthesis lines.

```
python -c "
import re
path = 'src/reasoner/domain/preset_registry.py'
with open(path) as f: content = f.read()
content = re.sub(
    r'\"synthesis\": \"glm-5\.2\",\s+# 🇺🇸 OpenAI.*',
    '\"synthesis\": \"glm-5.2\",              # 🇨🇳 Zhipu — cross-bloc final voice, \$0.95/\$3.00 (was gpt-5.5)',
    content
)
with open(path, 'w') as f: f.write(content)
"
```

---

### FIX-6: Dead Worktrees (P3)

**Files:** `.claude/worktrees/`  
**Risk:** None — deletes stale session data  
**Approach:** Prune git worktrees and remove directories.

```bash
git worktree prune
rm -rf .claude/worktrees/agent-a4c618c7 .claude/worktrees/agent-ac1f84a2 \
       .claude/worktrees/agent-ad6a6db7 .claude/worktrees/agent-ae2a64f7 \
       .claude/worktrees/agent-aeaed081 .claude/worktrees/agent-afad94bc \
       .claude/worktrees/gallant-darwin-030a85
```

**Verification:** `ls .claude/worktrees/` should be empty or contain only active worktrees.

---

## 3. Execution Order

```
Phase 1 (Safe, fast wins — same day):
  ├─ FIX-2:  Fire-and-forget error handler (2 lines, 1 file)
  ├─ FIX-5:  Stale comments (1 command)
  ├─ FIX-6:  Dead worktrees (1 command)
  └─ FIX-8b: Consistent Redis mode (3 lines, 1 file)

Phase 2 (Medium effort, high value — next day):
  ├─ FIX-3:  Replace module hot-reload (3 files, < 50 lines)
  └─ FIX-8a: 402 graceful degradation (2 files, ~80 lines)

Phase 3 (Large effort, structural — next sprint):
  ├─ FIX-1:  Consolidate phase-execution paths (4 files, ~200 lines)
  └─ FIX-7:  Test coverage (5 new test files, ~400 lines)
```

---

## 4. Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| FIX-1 breaks existing flows | All 24 method strategies pass `test_e2e_budget_presets_mock.py` before merge |
| FIX-3 breaks SSE streaming | Run `test_integration_preset_pipeline.py` against live backend |
| FIX-8a incorrectly catches 402 | Mock provider returns 402; verify pipeline produces partial result not crash |
| FIX-8b makes production Redis-less | Verify in-memory rate limiter handles production load before deploying |

---

## 5. Completion Checklist

- [ ] FIX-2: `_safe_create_task` helper applied to all `create_task` calls
- [ ] FIX-5: All 19 synthesis comments updated
- [ ] FIX-6: Stale worktree directories deleted
- [ ] FIX-8b: Redis probe changed from hard-fail to WARNING
- [ ] FIX-3: `reload()` method replaces `_ensure_fresh_preset_service()`
- [ ] FIX-8a: 402 → `[CREDIT_EXHAUSTED]` sentinel → partial results
- [ ] FIX-1: `PhaseExecutor` class consolidates both execution paths
- [ ] FIX-7: 13+ new tests across 4 modules
- [ ] All existing tests pass (53 augmented + full suite)
- [ ] Live pipeline test: `python -m reasoner.main --problem "test" --preset article-budget`
