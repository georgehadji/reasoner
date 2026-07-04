# Implementation Audit Report — Article Pipeline Upgrade

**Audited commit:** `c5097b0` (main)  
**Audit date:** 2026-07-03  
**Plan reference:** `docs/article-pipeline-upgrade-plan.md`  
**Scope:** 7 files changed across prompts, phase functions, flow orchestration, and presets

---

## 1. Executive Summary

The 9-phase article pipeline was implemented across 7 files. **5 of 6 plan steps are complete.** The core architecture — new prompts, new phase functions, ArticleFlow restructuring, and preset routing — is in place and passes validation. However, **4 plan items were partially implemented or missed**, and **2 existing functions are now dead code.** The claim ledger enhancement to the verify prompt has a structural issue that will likely cause JSON parse failures. No tests were written.

**Overall assessment:** APPROVED WITH CORRECTIONS — the implementation is functional but requires cleanup of dead code, fixing the verify prompt JSON structure, and completing the Phase 1 source_metadata enhancement before production use.

---

## 2. Plan Compliance Matrix

| Plan Item | Status | Evidence | Notes |
|---|---|---|---|
| **Step 1: New prompts** | ✅ Complete | `article.py:175-537` — 6 system prompts + 6 prompt functions | All 6 named prompts match plan spec to within reasonable prompt-design latitude |
| **Step 2: New phase functions** | ✅ Complete | `article_phases.py:167-293` — 5 new async functions | All 5 named functions match plan spec |
| **Step 3: ArticleFlow struct.** | ✅ Complete | `article.py:30-45` — 9 PhaseSteps | Matches plan's PhaseStep list exactly |
| **Step 4: Preset routing** | ✅ Complete | `preset_registry.py:660-676` — 5 new budget roles, 7 new/updated premium roles | Both presets validate, all roles in `_KNOWN_ROUTING_ROLES` |
| **Step 5: Methods doc** | ✅ Complete | `methods_and_presets.md:67-110` — updated tables | Budget 8→12 roles, premium 11→14 roles |
| **Step 6: Verification** | ⚠️ Partial | Preset validator passes (exit 0). No unit/integration tests run. | `scripts/validate_presets.py` was silent (0 exit), but no test suite was run. Plan says "run pytest tests/unit/test_article_*.py" — not done. |
| **Phase 1 source_metadata** | ❌ Missing | Search for `source_metadata` in `article_phases.py` — zero matches | Plan said "Extract and store structured source metadata (author, date, publisher)." Not implemented. |
| **Phase 4 claim_ledger storage** | ⚠️ Partial | Verify prompt enhanced (`article.py:163-170`), but phase function NOT enhanced | The prompt asks for `claim_ledger` JSON, but `run_article_adversarial_verify_phase` doesn't store/parse it. It only stores `verification` (the parent object). |
| **Retry loop for audit** | ❌ Missing | `article_phases.py:268-293` — stores `passes_audit` but never acts on it | Plan says "1 retry if audit score below threshold." Not implemented. |
| **skip_* config flags** | ❌ Missing | No skip flags exist | Plan's risk mitigation: "Add `skip_*` config flags for opt-out." Not implemented. |
| **ArticleFlow.execute()** | ✅ Complete | `article.py:47-52` — iterates phases and calls `services.run_phase` | Some phases used `await` vs the original which also awaited — functionally equivalent. |
| **Argument map injection** | ✅ Complete | `article.py:78-90` — `argument_block` injected between style_block and Assignment | Correct position per plan spec |
| **Outline output fields** | ✅ Complete | `article_phases.py:185-192` — stores `argument_map`, `outline`, `suggested_title`, `total_word_count` | Matches plan spec |
| **Structural critique output** | ✅ Complete | `article_phases.py:214-219` — stores `structural_critique` with `overall_rigor_score` | Matches plan spec |
| **Editorial audit output** | ✅ Complete | `article_phases.py:287-291` — stores `editorial_audit` with `passes_audit`, `audit_score` | Matches plan spec JSON output fields |

---

## 3. Architecture Compliance

### ✅ Pass

| Check | Evidence |
|---|---|
| **No new `_KNOWN_ROUTING_ROLES` keys** | `article_humanize`, `article_critic`, `article_revise`, `article_verifier`, `article_sot_skeleton` all present in `preset_core.py:85-99` |
| **PhaseStep serializers** | Uses `_ser_2`, `_ser_3`, `_ser_4`, `_ser_5` — matches existing patterns in WritingFlow and other flows |
| **Prompt function signature** | All follow `def article_*_prompt(state: PipelineState) -> str` — consistent with existing |
| **Phase function signature** | All follow `async def run_article_*_phase(state: PipelineState, services: WorkflowServices) -> None` |
| **State is stored in `writing_state`** | All new state reads/writes use `state.writing_state[...]` — consistent with existing article phases |
| **Logging convention** | All use `services.log("WRITING", ...)` — consistent with existing |
| **Error handling** | JSON parse errors caught with `try/except Exception`, errors appended to `state.errors` — matches existing pattern |
| **Import style** | `from reasoner.application.flows.article_phases import (...)` — matches existing module organization |
| **No circular imports** | ArticleFlow imports from article_phases, which imports from phases.article — clean top-down dependency |

### ⚠️ Concerns

| Issue | Severity | Detail |
|---|---|---|
| **Phase numbering gap** | Low | Plan says Phase 1-9 with PhaseStep(1..10). Implementation starts at `PhaseStep(2, "Evidence Collection"...)`. This skips Phase 1. The existing code started at 2 because Phase 1 is the classification/fusion pre-phase that runs before any method-specific flow. This is architecturally correct — the numbering matches existing conventions in `MultiPerspectiveFlow` and `WritingFlow`. |
| **`article_phases.py` module scope** | Low | The file now contains both ArticleFlow and WritingFlow shared functions (`_parse_sonar_citations`). This was already the case before the change. No regression. |

---

## 4. Code Quality Findings

### 🔴 Defects (should be fixed)

| # | Severity | File | Line | Issue | Recommendation |
|---|---|---|---|---|---|
| D1 | **P1** | `phases/article.py` | 163-170 | **Split JSON block in verify prompt.** The prompt asks the model to output TWO separate JSON objects: one for `verified_claims` + `metrics` + `gaps`, then ANOTHER for `claim_ledger`. Models will either emit one object and truncate the second, or merge them unpredictably. `extract_json()` will fail on two-object output. | Merge `claim_ledger` as a key INSIDE the main JSON object: `"claim_ledger": [{...}]` as a sibling of `"verified_claims"`. |
| D2 | **P2** | `article_phases.py` | 159 | **Dead code: `run_article_refine_phase`.** This function is defined but has zero callers — it was removed from `article.py` imports but not deleted from `article_phases.py`. | Delete the function and its references (or document it as legacy with a comment). |
| D3 | **P2** | `phases/article.py` | ~177 | **Dead code: `ARTICLE_REFINE_SYSTEM` + `article_refine_prompt`.** These are referenced only by `run_article_refine_phase` (dead code). The `ARTICLE_REFINE_SYSTEM` constant and `article_refine_prompt` function have no callers. | Delete or document as legacy. |

### 🟡 Improvements (should consider)

| # | Severity | File | Issue | Recommendation |
|---|---|---|---|---|
| I1 | P3 | `article_phases.py` | 249-265 | **No error handling in style_copy edit if style edit fails.** If `article_humanize` returns empty/malformed output, `state.writing_state["final_article"]` is set to that bad value, and the copy edit then receives it. The copy edit can't fix corrupted content. | Wrap style edit in try/except; if it fails, skip style and proceed to copy edit on the pre-style draft. |
| I2 | P3 | `article_phases.py` | 274-278 | **Final audit uses `article_verifier` without Sonar-aware detection.** The verify phase detects Sonar routing for live web search, but the audit phase doesn't. If `article_verifier` routes to Sonar, it won't get the live-web-aware prompt variant. | Add Sonar detection for audit, or accept that audit is pure evaluation (no web search needed). |
| I3 | P3 | `phases/article.py` | 78-90 | **Argument map block can be empty if `argument_map` key exists but has no `central_question`.** The guard `isinstance(argument_map, dict) and argument_map.get("central_question")` is correct — a dict with no central_question means the outline phase produced a partial output. The draft will still run. This is defensive and correct, but a `services.log` warning would help debugging. | Add a warning log when outline produces argument_map dict without central_question. |
| I4 | P3 | `article_phases.py` | 214 | **`overall_rigor_score` default is 0.5.** If `extract_json` fails, the structural critique defaults to a mid-range score. A failed structural critique should probably be surfaced more visibly — 0.5 could be misinterpreted as "everything is fine." | Default to 0.0 for better visibility of parse failures. |
| I5 | P3 | `phases/article.py` | 100-130 | **Claim ledger JSON field names: `status` vs plan spec `verification_status`.** The plan says `verification_status` field, the implementation uses `status`. And `source` vs `supporting_source`. | Rename to match plan or accept the discrepancy as intentional simplification. |

### ✅ Strengths

- **Graceful degradation everywhere.** Every new phase function catches `extract_json` failures and sets reasonable defaults — outline falls back to empty dict, critic defaults to 0.5 rigor, audit defaults to failed. No phase takes down the pipeline.
- **Argument map is optional.** The draft prompt's `argument_block` is guarded with `isinstance(argument_map, dict) and argument_map.get("central_question")` — if the outline phase fails or returns empty, the draft still produces output using the original prompt structure. This matches the plan's P1 mitigation for prompt regression.
- **Style edit preserves author voice.** The `ARTICLE_STYLE_EDIT_SYSTEM` explicitly instructs "preserve the author's original voice" and the prompt includes target publication matching — directly addresses the user's editorial methodology.
- **Critic has access to argument map and fact-check results.** The `article_critic_prompt` receives both `argument_map` (to check structural fidelity) and `verification` (to avoid re-flagging already-known factual issues). Good prompt design.

---

## 5. Testing & Coverage Assessment

| Test Type | Status | Detail |
|---|---|---|
| **Unit tests (new)** | ❌ None created | Plan says "run pytest tests/unit/test_article_*.py" but no such tests exist. No new tests were written for any of the 5 new phase functions, 6 new prompt functions, or the ArticleFlow restructuring. |
| **Integration tests** | ❌ None created | Plan doesn't specify integration tests but they would be needed to verify the 9-phase sequence end-to-end. |
| **Regression tests** | ⚠️ Not run | Plan Step 6 says run existing tests. Not executed. |
| **Preset validation** | ✅ Passes | `scripts/validate_presets.py` exits 0. Both article presets load and resolve all routing keys. |
| **Manual testing** | ❌ Not done | Plan says "Run an article with the budget preset and verify phase sequencing." Not executed. |
| **Edge-case coverage** | ⚠️ Untested | No tests for: empty sources, empty outline, failed critic, failed audit, all-unsupported claims, very long articles exceeding context windows |

---

## 6. Risk & Regression Analysis

### Regressions

| Risk | Severity | Detail |
|---|---|---|
| **Existing article presets changed** | P2 | `article-budget` and `article-premium` routing tables grew from 4-6 roles to 12-14. Any code that enumerates preset routing entries (e.g., serializers, renderers, cost calculators) must handle the new keys. No serializer changes were made — `_ser_2` through `_ser_5` reused unchanged. Safe. |
| **`run_article_refine_phase` removed from flow** | P1 | The old 5-phase flow's `Refine` step is now replaced by `Developmental Edit` + `Style + Copy Edit`. Any client code calling `run_article_refine_phase` directly will break. No internal callers found — safe. |
| **Phase timing/order** | P1 | The number of LLM calls increased from ~4 to ~9 per article. This changes article generation latency by ~2.25×. Existing timeout settings may need adjustment. |

### Technical Debt Introduced

| Debt | Severity | Detail |
|---|---|---|
| Dead code in article_phases.py | P3 | `run_article_refine_phase` and its associated `ARTICLE_REFINE_SYSTEM` + `article_refine_prompt` are orphaned |
| Dead code in phases/article.py | P3 | `ARTICLE_REFINE_SYSTEM` and `article_refine_prompt` have zero callers |
| No test coverage | P2 | Entire new pipeline is untested |
| Verify prompt JSON splitting | P1 | The two-JSON-object verify prompt is a latent bug |

### Backward Compatibility

| Check | Status |
|---|---|
| Existing preset validation | ✅ Passes |
| Existing phase function signatures preserved | ✅ `run_article_retrieve_sources_phase` and `run_article_adversarial_verify_phase` unchanged |
| Existing state fields preserved | ✅ `writing_state["final_article"]`, `["verification"]`, `["retrieved_sources"]`, `["metrics"]` all still used |
| New state fields added | ✅ `["argument_map"]`, `["outline"]`, `["suggested_title"]`, `["total_word_count"]`, `["structural_critique"]`, `["editorial_audit"]` — these are additive, no migration needed |

---

## 7. Required Corrections

| # | Severity | File | Issue | Recommendation |
|---|---|---|---|---|
| **C1** | **P1** | `phases/article.py:163-170` | Split JSON block in verify prompt will cause parse failures | Merge `claim_ledger` as a key inside the main JSON object. Change the prompt to: `'Output JSON: {"verified_claims": [...], "metrics": {...}, "gaps": [...], "high_risk_sentences": [...], "claim_ledger": [...]}'` |
| **C2** | **P2** | `article_phases.py:159-167` | Dead code: `run_article_refine_phase` | Delete the function |
| **C3** | **P2** | `phases/article.py:177-228` | Dead code: `ARTICLE_REFINE_SYSTEM` + `article_refine_prompt` | Delete both (only referenced by dead `run_article_refine_phase`) |
| **C4** | **P2** | `article_phases.py:150-156` | Verify phase doesn't extract `claim_ledger` | After C1 fix, add: `state.writing_state["claim_ledger"] = data.get("claim_ledger", [])` |
| **C5** | **P3** | `article_phases.py:214` | Default `overall_rigor_score` is misleading at 0.5 | Change default to `0.0` |
| **C6** | **P3** | `article_phases.py:249-265` | No error handling if style edit produces empty output | Wrap in try/except; on failure, copy-edit the pre-style draft |

### Optional / Enhancement

| # | Filename | Detail |
|---|---|---|
| E1 | `phases/article.py:130-140` | Implement Phase 1 `source_metadata` (author, date, publisher) extraction from search results |
| E2 | `article_phases.py:268-293` | Implement audit retry loop (re-run developmental edit if `passes_audit` is false, max 1 retry) |
| E3 | Tests | Write unit tests for `article_outline_prompt`, `article_critic_prompt`, all phase functions |
| E4 | `article_phases.py:249` | Add Sonar detection for audit phase (matching verify phase pattern) |

---

## 8. Final Verdict

### APPROVED WITH CORRECTIONS

**Rationale:** The implementation correctly realizes the plan's editorial pipeline architecture — all 9 phases, all 6 new prompts, all phase functions, and all preset routing changes are in place and pass validation. The architecture is clean, error handling is defensive, and backward compatibility is preserved.

**Blocking issues (must fix before prod):**
1. **C1** — The split-JSON verify prompt will cause parse failures on the claim ledger (P1)
2. **C2-C3** — Dead code should be removed to avoid confusion (P2)

**Should fix before prod:**
3. **C4** — Extract and store `claim_ledger` in the verify phase
4. **C5-C6** — Defaults and error handling improvements

**Should do next sprint:**
5. **E1-E4** — source_metadata, retry loop, tests
