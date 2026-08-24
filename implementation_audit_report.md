# Implementation Audit Report — Augmented Article Pipeline

**Plan:** [implementation_plan.md](implementation_plan.md) (dated 2026-07-05, status claimed: "✅ Implemented, reviewed, all fixes applied")
**Code changes reviewed:** commit [`81adfd7`](https://github.com) — *"feat: augmented article pipeline + model cost optimization"* (2026-07-06)
**Current HEAD:** `799d532` (156 commits ahead of the reviewed commit; verified the code paths below are unchanged since)
**Auditor:** Claude Code, static + executable verification (no live LLM calls made)
**Audit date:** 2026-08-24

---

## 1. Executive Summary

The feature is **functionally present and mostly matches the plan's plumbing** (T1–T17, T19 all verified in code). Tests exist, pass (62/62), and the architecture stays within the project's hexagonal layering.

However, the audit found **one CRITICAL correctness bug** that silently defeats two of the feature's own headline design goals stated in the commit message: *"Budget users pay zero extra cost"* and the A/B test's baseline arm. An empty list (`[]`, meaning "explicitly zero augmentation methods") is treated as falsy in [pipeline.py:409](src/reasoner/application/pipeline.py:409), so it's discarded in favor of the 2-method default. This was reproduced with executable evidence (Section 6). No test exists that would have caught it — the test suite covers regex detection and A/B math in isolation, but never exercises the tier→pipeline→state wiring where the bug lives.

The audit also found that **the plan document itself is stale relative to the code it describes**: Appendix B lists per-tier config, env toggles, caching, and A/B testing as "Future Enhancements — not done," yet the very commit that produced this text also implemented all four. The plan was not updated to reflect delivered scope, undermining its value as a compliance record.

**Verdict: APPROVED WITH CHANGES** — the core feature works and is architecturally sound, but the cost-gating bug must be fixed before this can be considered "premium users pay for augmentation, budget users don't" (a stated cost-control invariant), and the plan doc should be reconciled with actual scope.

---

## 2. Plan Compliance Matrix

| Plan Item | Status | Evidence | Notes |
|---|---|---|---|
| T1 Shared augmentation module | ✅ Complete | [augmentation.py](src/reasoner/application/flows/augmentation.py) exists, 301 lines | |
| T2 Depth detection regex | ✅ Complete | `_DEEP_QUESTION_PATTERNS`, `is_deep_question()` — [augmentation.py:74-158](src/reasoner/application/flows/augmentation.py:74) | 9 patterns, Greek+English |
| T3 Parallel augmentation execution | ✅ Complete | `asyncio.gather(*tasks)` — [augmentation.py:260](src/reasoner/application/flows/augmentation.py:260) | |
| T4 Wire ArticleFlow | ✅ Complete | `await run_augmentation(...)` at top of `execute()` — [article.py](src/reasoner/application/flows/article.py) diff | |
| T5 Wire WritingFlow | ✅ Complete | Same call in [writing.py](src/reasoner/application/flows/writing.py) diff | |
| T6 Enrich article prompts (retrieval/outline/draft) | ✅ Complete | All 3 prompts inject `pre_research_summary` gated on non-empty — [phases/article.py](src/reasoner/phases/article.py) diff | |
| T7 Enrich writing prompts (outline/draft) | ✅ Complete | Same pattern in [phases/writing.py](src/reasoner/phases/writing.py) diff | |
| T8 `augmentation_methods` on `GateDecision` | ✅ Complete | [gate_agent.py](src/reasoner/hypergate/gate_agent.py) diff, field added | |
| T9 Wire through HyperGate returns | ✅ Complete | All 4 `GateDecision` construction sites updated — [hyperagent.py](src/reasoner/hypergate/hyperagent.py) diff | Field is always `None` from HyperGate now (see §4) |
| T10 `_DEEP_CONCEPT_PATTERNS` | ✅ Complete | [hyperagent.py](src/reasoner/hypergate/hyperagent.py) diff, 2 patterns (39 EN concepts in one regex, 17 GR) | Plan claims "39 English + 20 Greek" as *concept count*, not pattern count — consistent phrasing, verified by counting alternatives in the compiled regex |
| T11 Factual fast-path exclusion fix | ✅ Complete | `and not is_deep_concept` guard — [hyperagent.py](src/reasoner/hypergate/hyperagent.py) diff | Covered by `test_deep_concepts_bypass_factual_fastpath` (5 cases, passing) |
| T12 `augmentation_methods` on `PreflightDecision` | ✅ Complete | [orchestrator.py:44](src/reasoner/application/orchestrator.py:44) | |
| T13 Propagate through orchestrator | ✅ Complete | [orchestrator.py:275-334](src/reasoner/application/orchestrator.py:275) | Also carries A/B override (out-of-plan, see §4) |
| T14 `augmentation_methods` on `PipelineMeta` | ✅ Complete | [pipeline_state.py:147](src/reasoner/domain/pipeline_state.py:147) | Proper dataclass field, not a dict — `.get()` invariant doesn't apply here |
| T15 Thread through `ReasonerPipeline` | ⚠️ **Partial — has a bug** | [pipeline.py:106,120,409](src/reasoner/application/pipeline.py:106) | Constructor param and instance attr wired correctly; the *transfer into state* at line 409 is broken for empty lists — see §6 |
| T16 Thread through `PipelineService` | ✅ Complete | [pipeline_service.py](src/reasoner/application/services/pipeline_service.py) diff | |
| T17 Thread through CLI (`main.py`) | ✅ Complete | [main.py:254](src/reasoner/main.py:254) `augmentation_methods=preflight.augmentation_methods` | |
| T18 Revert preflight timeout | ❓ **Unverifiable (HYPOTHESIS)** | No timeout-related change appears anywhere in commit `81adfd7`'s diff | If a value was bumped and reverted to its original within the same uncommitted working session, the net diff is legitimately empty — can't be disproven from history. Flagged, not scored as a defect. |
| T19 Delete `depth_detector.py` | ✅ Complete | File absent at HEAD; zero remaining references to `DepthDetector`/`depth_detector` anywhere in `src/` or `tests/` | Clean removal, no dead imports |
| T20 Unit tests (plan says "16 cases") | ⚠️ **Partial / plan inaccurate** | [test_augmented_article.py](tests/test_augmented_article.py) has 10 test functions / **53** parametrized cases, not 16 — the plan's own §6 breakdown table sums to 53, contradicting its own §1 "16 unit test cases" headline | See §5 for coverage gap analysis |
| Appendix B "Future": env toggle | ✅ **Already delivered, mislabeled as future** | `AUGMENTATION_ENABLED` etc. — [settings.py](src/reasoner/core/settings.py) diff | |
| Appendix B "Future": per-tier config | ✅ **Already delivered, mislabeled as future, and buggy** | `get_tier_augmentation_methods()` — [augmentation.py:289-300](src/reasoner/application/flows/augmentation.py:289) | Delivered beyond plan's described "Budget → debate only; Premium → debate+jury" (actual: budget=0, premium=4 methods). See §6 for the bug. |
| Appendix B "Future": caching | ✅ **Already delivered, mislabeled as future** | L1 LRU+TTL cache — [augmentation.py:22-67](src/reasoner/application/flows/augmentation.py:22) | Untested (no test file covers cache hit/expiry) |
| Appendix B "Future": A/B metrics | ✅ **Already delivered, mislabeled as future** | [augmentation_metrics.py](src/reasoner/application/services/augmentation_metrics.py), tested in [test_augmentation_metrics.py](tests/test_augmentation_metrics.py) (9 cases, passing) | Baseline arm is silently defeated by the same bug as budget tier — see §6 |
| Out-of-scope (bundled in same commit) | ℹ️ Present, not in plan | Model routing swaps: `grok-4.20`→`grok-4.3` alias, `gpt-5.5`→`glm-5.2` synthesis role across 19 presets — [preset_registry.py](src/reasoner/domain/preset_registry.py), [registry.py](src/reasoner/infrastructure/llm/registry.py), [constants_models.py](src/reasoner/core/constants_models.py), [harness_guard.py](src/reasoner/application/services/harness_guard.py) diffs | Unrelated to the augmented-article feature; correctly backward-compat aliased. Not a defect, but conflates two unrelated changes in one commit, complicating this very audit. |

---

## 3. Architecture Compliance Assessment

- **Dependency direction:** `augmentation.py` (application layer) imports only `domain.pipeline_state` and, lazily, `core.settings` — no infrastructure imports. `augmentation_metrics.py` (application/services) is dependency-free except `core.settings`. Both respect the Dependency Rule in [CLAUDE.md §1](CLAUDE.md).
- **`PipelineMeta.augmentation_methods`** is a genuine dataclass field (`list[str] | None`), not a `dict[str, Any]` catch-all — the project's "always `.get()`, never subscript" invariant applies to the dict-typed method-state fields, not to this. No violation.
- **Design-injected callables:** `run_augmentation(state, call_llm, log)` takes `call_llm`/`log` as parameters instead of requiring a `WorkflowServices` object, exactly as planned in §3.1 — this is a deliberate decoupling so both `ArticleFlow` and `WritingFlow` can share it without a common base beyond `WorkflowStrategy`. Reasonable, matches plan.
- **HyperGate opacity contract:** `_DEEP_CONCEPT_PATTERNS` and the new fast-path guard live entirely in regex/Python, never exposed to an LLM prompt — consistent with "real method names are never exposed to LLMs."
- **No import-linter contract changes** were needed or made; nothing in this diff touches the one documented exception (`domain/preset_core.py`).
- **Deviation from plan's own architecture note:** §3.5 of the plan describes `GateDecision.augmentation_methods` as a real signal path ("HyperGate Fast-Path Fix" implies HyperGate participates in the decision). In the actual code, the local variable `augmentation_methods` in `hyperagent.py` is declared once as `None` and never reassigned before any `GateDecision(...)` construction — it is **always `None`** in practice (confirmed by inspection of every call site in the diff). The comment left in the code — *"Depth detection moved to ArticleFlow (regex-based, no LLM overhead)"* — is accurate and explains why, but the plan's file manifest (§2, "hyperagent.py ← updated: +_DEEP_CONCEPT_PATTERNS, gate fix") undersells that this field is now vestigial plumbing on the HyperGate side; all real selection happens in `orchestrator.py` via tier lookup. Not a defect — just worth noting the field exists on `GateDecision` for a future use case that isn't wired yet (dead-but-harmless optionality, consistent with the plan's own backward-compat philosophy).

**Assessment: Compliant.** No layering violations found.

---

## 4. Code Quality Findings

| Severity | Area | Finding |
|---|---|---|
| Medium | `pipeline.py:409` | See §6 — falsy-empty-list bug. Root cause of the critical correctness issue. |
| Low | `orchestrator.py:326-334` | A/B test wiring does `from ... import should_disable_augmentation_for_ab` and `import hashlib as _hashlib` **inside** the function body rather than at module top. This matches an existing local-import pattern already present in `augmentation.py` (avoiding a settings-import cycle at module load time), so it's consistent with the codebase's established style rather than a one-off smell — but the `_hashlib` alias specifically exists only to dodge a name collision with a module-level `hashlib` import that doesn't actually exist in `orchestrator.py`; the alias is unnecessary and could just be `import hashlib`. Cosmetic only. |
| Low | `augmentation.py:190-192` | `confirm_depth()` swallows all exceptions and fails **open** (returns `True`, trusting the regex). This matches the plan's stated "graceful degradation" philosophy for augmentation *execution* failures, but here it fails open on the *gate* — worth a one-line comment confirming this is intentional (LLM-confirm being a quality filter, not a safety gate, so failing open is low-risk), since a silent broad `except Exception` next to a security-adjacent gate normally warrants scrutiny per this repo's own security checklist. Not flagged as a defect; flagged for documentation. |
| Low | `augmentation.py` | Cache (`_aug_cache`) is a bare module-level `OrderedDict`, not protected by a lock. Safe under Python's single-threaded asyncio cooperative model (no `await` between the dict mutations in `_get_cached`/`_set_cache`), but will silently fail to share entries across separate worker processes if the app is ever deployed with multiple uvicorn workers — this is inherent to "L1 in-memory" caches and is explicitly labeled as such in the module's own docstring, so this is a known, accepted limitation rather than an oversight. |
| Info | `preset_registry.py`, `registry.py`, `constants_models.py`, `harness_guard.py` | Model-routing changes bundled into this commit are clean, backward-compatible alias swaps (old model ID routes to the new model's API endpoint). Correct, but orthogonal to the plan under review — see the "out-of-scope" row in §2. |
| Info | Prompt injection surface | All `pre_research_summary` injections into `article.py`/`writing.py` prompts go through `_wrap_external_content()` (delimiter-fencing), consistent with the existing pattern used for search-result injection elsewhere in the same files. No new sanitization gap introduced. |

No SOLID/DRY/KISS violations of note — `run_augmentation` is a single well-scoped function, the five augmentation prompts are declared as simple string constants keyed by method name (no premature strategy-pattern abstraction), and the module avoids introducing a class where a function sufficed.

---

## 5. Testing & Coverage Assessment

**Ran:** `pytest tests/test_augmented_article.py tests/test_augmentation_metrics.py -q` → **62 passed, 0 failed** (verified directly, this session).

Covered:
- Regex depth detection (37 parametrized deep/shallow cases, Greek + English)
- HyperGate fast-path exclusion (10 cases)
- Augmentation config completeness (prompts exist for every method, roles are valid strings)
- A/B arm assignment determinism and metric payload shape (9 cases)

**Not covered — and this is where the bug in §6 lives, undetected:**
- `get_tier_augmentation_methods()` itself — no test asserts `get_tier_augmentation_methods("budget") == []`, `("premium")` returns the 4-method list, or the default-tier single-method list.
- `ReasonerPipeline.run()`'s transfer of `self.augmentation_methods` into `state.meta.augmentation_methods` — no test constructs a pipeline with `augmentation_methods=[]` and asserts the state reflects "no augmentation," which is exactly the path that's broken.
- `run_augmentation()` end-to-end (mocked `call_llm`) — no test verifies that a deep question with `state.meta.augmentation_methods = []` actually skips LLM calls, nor that the cache hit path (`_get_cached`) returns without calling `call_llm`.
- `confirm_depth()` — no test for the LLM-confirm gate (success or failure path).
- `should_disable_augmentation_for_ab()`'s actual effect on a run when `AUGMENTATION_AB_TEST=true` — tests only check the arm-assignment math and the off-by-default no-op case, never the on-and-assigned-baseline case feeding back into `decision.augmentation_methods`.

**Regression:** No existing tests appear to have broken (I did not run the full suite due to time cost of ~150+ files at 120s+ per background run at the time of writing; the two directly-relevant files pass cleanly and the diff to shared files — `orchestrator.py`, `pipeline.py`, `hyperagent.py` — is additive except for the one-line factual fast-path condition, which has direct test coverage confirming both directions still work).

**Manual verification step in plan (§6):** unexecuted by this audit — requires live API keys and was explicitly out of scope for a static/offline review. Flagged as HYPOTHESIS: plan claims "Expected log: `[AUGMENT] Running pre-processing: debate, iterative_critique`" — plausible given the code, not independently confirmed against a live run.

---

## 6. Risk & Regression Analysis — Primary Finding

### CRITICAL: Budget-tier and A/B-baseline augmentation is not actually disabled

**Files:** [pipeline.py:409](src/reasoner/application/pipeline.py:409), [orchestrator.py:322-334](src/reasoner/application/orchestrator.py:322), [augmentation.py:236](src/reasoner/application/flows/augmentation.py:236)

**Mechanism:**
1. `orchestrator.py:324` computes `decision.augmentation_methods = get_tier_augmentation_methods("budget")` → `[]` (intentional: budget tier should get zero augmentation, per the code's own comment "Budget users pay zero extra cost").
2. That `[]` is threaded through `PipelineService.create_pipeline(augmentation_methods=[])` → `ReasonerPipeline.__init__(augmentation_methods=[])` → `self.augmentation_methods = []`.
3. In `ReasonerPipeline.run()`, line 409: `if self.augmentation_methods: state.meta.augmentation_methods = self.augmentation_methods`. Since `[]` is falsy in Python, this branch is skipped, and `state.meta.augmentation_methods` is left at its dataclass default, `None`.
4. In `run_augmentation()`, line 236: `methods = state.meta.augmentation_methods or DEFAULT_AUGMENTATION_METHODS` → `None or ["debate", "iterative_critique"]` → the 2-method default is used.

**Net effect:** a deep question routed to a **budget** preset still triggers 2 extra LLM calls (debate + iterative_critique) — the exact cost the tiering was built to avoid, per the commit's own stated goal ("Per-tier augmentation: budget=0, standard=1, premium=4 methods" / code comment "Fill in tier-specific defaults so Budget users pay zero extra cost").

The identical bug **also defeats the A/B test's baseline arm**: `orchestrator.py:334` sets `decision.augmentation_methods = []` to force the baseline (unaugmented) condition for a fair comparison — but that `[]` is swallowed by the same falsy-check, so a run assigned to "baseline" for measurement purposes still runs augmentation. This silently invalidates any A/B comparison collected while `AUGMENTATION_AB_TEST=true`, since both arms end up augmented whenever the question is regex-flagged as deep.

**Reproduced with executable evidence** (this session, not simulated in prose):

```
tier=budget -> []
state.meta.augmentation_methods after pipeline.run() = None
methods actually used for a BUDGET-tier deep question = ['debate', 'iterative_critique']
```

**Root cause, not symptom:** the bug is in the one shared choke point (`pipeline.py:409`) that both the budget-tier path and the A/B-baseline path route through — fixing it there fixes both call sites at once; patching only one caller would leave the other broken.

**Fix:** see [augmentation_remediation_plan.md §3](augmentation_remediation_plan.md).

> **Correction (2026-08-25):** this section originally recommended a single-line `is not None` change at `pipeline.py:409`. That recommendation was **incomplete**. Follow-up verification found the identical falsy bug a second time at [augmentation.py:236](src/reasoner/application/flows/augmentation.py:236) (`state.meta.augmentation_methods or DEFAULT_AUGMENTATION_METHODS` — `[] or X` is `X`), so fixing line 409 alone leaves the defect fully intact. Additionally, the `AUGMENTATION_LLM_CONFIRM` branch issues a billable LLM call *before* methods are resolved, so zero-cost budget runs also require reordering the guards. The complete fix is a small restructure of `run_augmentation()` plus the `pipeline.py` guard, specified in the remediation plan.

**Severity escalation:** augmentation calls route through `services.call_llm` → `_call_llm_cached` → `self._executor.execute()` ([pipeline.py:376](src/reasoner/application/pipeline.py:376)) — the same `LLMExecutor` every billed phase uses. The budget-tier overrun is therefore **real metered spend**, not merely wasted latency.

### Other risks

| Severity | Description |
|---|---|
| Low | Plan-vs-code drift (§2, Appendix B rows) means anyone reading `implementation_plan.md` as a spec for "what this system currently does" will underestimate the delivered surface (env toggles, caching, A/B testing, jury/socratic methods) and might duplicate work or miss the extra `AUGMENTATION_*` settings when reasoning about cost/config. |
| Low | No caching test coverage — a future refactor of `_get_cached`/`_set_cache` (e.g., changing the TTL check or eviction order) has no regression net. |
| None found | No security issues: no new user-input trust boundary crossed without existing `sanitize_for_prompt()`/`_wrap_external_content()` conventions; no secrets; no SQL/path/command surfaces touched. |
| None found | No backward-compatibility issues: every new field defaults to `None`/`False` per the plan's stated approach, verified in each diff. |

---

## 7. Required Corrections

| Severity | File | Issue | Recommendation |
|---|---|---|---|
| **CRITICAL** | [pipeline.py:409](src/reasoner/application/pipeline.py:409) + [augmentation.py:236](src/reasoner/application/flows/augmentation.py:236) | `if self.augmentation_methods:` and `... or DEFAULT_AUGMENTATION_METHODS` each treat an explicit empty list as "no override," silently re-enabling the 2-method default for budget-tier and A/B-baseline runs. Billed via the standard `LLMExecutor`, so this is real metered spend. | Fix **both** sites and move method resolution ahead of the billable `AUGMENTATION_LLM_CONFIRM` call. Full specification in [augmentation_remediation_plan.md §3](augmentation_remediation_plan.md). |
| **HIGH** | [augmentation_metrics.py](src/reasoner/application/services/augmentation_metrics.py) | `build_ab_metric()` is dead code (only its own tests call it) and its payload does not fit `TelemetryStoreProtocol.save_run()`'s fixed signature — the module docstring's emission claim is false. The A/B experiment assigns arms and measures **nothing**. | Delete the module (recommended — it is listed as an unbuilt "future enhancement" in the plan anyway), or wire emission via the event bus. See [remediation plan §2 and §4](augmentation_remediation_plan.md). |
| Medium | [tests/test_augmented_article.py](tests/test_augmented_article.py) | No test exercises `get_tier_augmentation_methods()` or the tier→state wiring where the bug above lives — this class of regression will recur silently otherwise. | Add: (a) unit test asserting `get_tier_augmentation_methods("budget") == []`, `"premium"` returns 4 methods, default returns `["debate"]`; (b) a test constructing `ReasonerPipeline(augmentation_methods=[])` and asserting `state.meta.augmentation_methods == []` after `.run()` (not `None`). |
| Low | [implementation_plan.md](implementation_plan.md) Appendix B / §1 | Plan lists delivered features (env toggles, per-tier config, caching, A/B testing) as "Future Enhancements," and its executive summary claims "16 unit test cases" while its own §6 table sums to 53 (63 including the undocumented A/B metrics test file). | Update the plan doc to reflect actual delivered scope, or mark it explicitly superseded/historical so it isn't mistaken for a current spec. |
| Low | [src/reasoner/application/flows/augmentation.py](src/reasoner/application/flows/augmentation.py) (cache) | No test coverage for `_get_cached`/`_set_cache` TTL expiry or LRU eviction. | Add a small unit test with a monkeypatched `time.time()` or short TTL to exercise expiry, and one exercising eviction past `AUGMENTATION_CACHE_MAX_ENTRIES`. |

---

## 8. Final Verdict

## APPROVED WITH CHANGES

The feature is architecturally sound, its plumbing matches the plan (T1–T17, T19 all verified), and its own tests pass. It must not ship to a cost-sensitive budget tier in its current state: the tier-gating bug in [pipeline.py:409](src/reasoner/application/pipeline.py:409) means "budget users pay zero extra cost" is currently false, and it also invalidates the A/B experiment the same commit introduced. The fix is a one-line, low-risk change with an obvious regression test to pair with it. The plan document should also be reconciled with the actual delivered scope before being treated as a source of truth.
