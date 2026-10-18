# Iterative-Critique & Multi-Perspective — Gap Remediation Plan

**Date:** 2026-10-18
**Status:** Draft for review
**Branch target:** `fix/method-flow-gaps`
**Scope:** the 13 gaps found while writing build specs for the `iterative-critique` and
`multi-perspective` methods. Six are in Iterative Critique (IC-1..6), seven in
Multi-Perspective (MP-1..7). MP-7 lives in shared synthesis and therefore touches every
method that uses `run_synthesis_phase`.

**Related:** [`ensemble-diversity-measurement.md`](ensemble-diversity-measurement.md) fixed
the same unrouted-`expert_N` bug for Delphi (D0). IC-1 is the same fix for Iterative
Critique. [`watermark-removal-integration.md`](watermark-removal-integration.md) §5.5 reuses
the synthesis citation check, and MP-7 must keep that contract (§2, MP-7).

Nothing here changes the Dependency Rule (CLAUDE.md §1). Every change stays inside the
layer that already owns the code: prompts in `phases/`, flow logic in
`application/flows/`, value objects in `domain/`, limits in `core/constants_limits.py`,
routing in `domain/preset_registry.py`.

---

## 0. Verified findings

Each row was read out of the tree on 2026-10-18. "Evidence" is where to look first.

| ID | Gap | Severity | Evidence |
|----|-----|----------|----------|
| IC-1 | Generator (`expert_1`) and critic (`expert_2`) are unrouted in both IC presets, so `ProviderRouter.resolve()` falls back to `primary_id` and both run on **one model** (`grok-4.3` budget, `gpt-5` premium). The method's cross-lab premise does not hold. `BlocDiversityConstraint` already lists `expert_1`/`expert_2` as generator roles (`bloc_diversity.py:22-31`), but it can't check roles a preset never routes. | **High — live bug** | `domain/preset_registry.py:1081-1110`, `infrastructure/llm/router.py:350-355` |
| MP-1 | If all four perspectives fail, `run_perspectives_phase` returns normally with `candidates=[]`. The quality gate (`_check_perspectives`) fails, retries once (`PHASE_RETRY_BUDGETS["Perspectives"] = 1`), then the runner treats the exhausted gate as a completion (`runner.py:269-274`). Critique and stress testing skip, and synthesis runs on nothing. `critical=True` never fires because no exception is raised. | **High — live bug** | `application/flows/perspective_phases.py:252-254`, `application/flows/runner.py:262-288`, `quality/criteria.py:63` |
| IC-5 | Model-authored `answer` / `previous_answer` are interpolated raw into the critic, revision and synthesis prompts. This breaks the "model-authored text is wrapped" invariant (CLAUDE.md §5). | **High — invariant** | `phases/iterative_critique.py` (`critic_evaluation_prompt`, `generator_revision_prompt`, `synthesis_prompt`) |
| IC-4 | A critic parse failure produces a synthetic round (all 5.0, flaw "Critic produced malformed JSON"). Three in a row satisfy both `score_converged` and `stalemate_detected`, so the loop reports convergence it never reached. | Medium | `application/flows/iterative_critique_phases.py` (`_llm_critic_round`, `check_convergence`) |
| IC-2 | `run_generator_phase` returns only the answer string. `flaw_responses`, `changes_summary`, `key_claims`, `confidence` and the serving model are discarded, so `AdversarialRound.changes_summary`, `revised_answer`, `generator_model` and `critic_model` are always empty. Synthesis always sees `changes: ""`. | Medium | `iterative_critique_phases.py` (`run_generator_phase`, `AdversarialRound`) |
| MP-3 | `SolutionCandidate.model_used` is always `""`. `call_llm` already returns the serving model in `metadata["model"]` (`infrastructure/llm/executor.py:583`), but the phase discards it (`raw, _ = ...`). Diversity cannot be audited after the run. | Medium | `perspective_phases.py` (`_get_perspective`) |
| MP-4 | Stress results carry no candidate reference, and `recovery_path` is parsed but never requested by the prompt, so it is always `""`. | Medium | `phases/multi_perspective.py` (`stress_test_prompt`), `perspective_phases.py` (`run_stress_test_phase`), `domain/core_types.py:219` |
| IC-3 | `REJECT` is treated like `REVISE`: a fundamentally wrong answer is patched rather than regenerated. | Medium | `application/flows/iterative_critique.py` (`_run_debate_loop`) |
| MP-2 | After the critique retry budget is spent with no scores, the first two candidates become `top_candidates` unranked, and nothing downstream knows. | Medium | `perspective_phases.py` (`run_critique_phase` except branch), `quality/criteria.py:85` (`_check_critique`) |
| IC-6 | IC synthesis fills only `core_solution`: no claim labels, action blueprint, open questions, evidence or promotion rules, unlike every method that uses the shared synthesis. | Medium | `iterative_critique_phases.py` (`run_synthesis_phase`) vs `flows/synthesis_phase.py` |
| MP-7 | The citation-integrity check only **logs** a URL that is not in context. The fabricated link still reaches the user. Shared code, so this affects every method. | Medium | `flows/synthesis_phase.py` (citation integrity block) |
| MP-5 | Evidence search runs on every run, including `complexity == "simple"`. It borrows `ARTICLE_RETRIEVAL_PLAN_SYSTEM`, and its results bypass source vetting (`vetted_context` stays empty on this path). | Low | `perspective_phases.py` (`run_multi_perspective_research_phase`), `flows/search_phases.py:103` |
| MP-6 | `top_k = 2` and the candidate cap `8` are magic numbers inside the phase. | Low | `perspective_phases.py` (`run_critique_phase`) |

### Corrected non-findings

- **MP-1 is not a missing quality gate.** `_check_perspectives` does catch empty candidates. The gap is that the runner deliberately treats an exhausted gate as a completion, because "`critical` governs execution failure, not a score" (`runner.py:269-274`). That policy is correct and stays. The fix is to make zero candidates an *execution* failure (§2, MP-1), not to change the runner.
- **The bloc table in `perspective_phases.py` is a duplicate, not a separate source of truth.** `core/ports/model_registry_port.py:51` already exposes `bloc_of()`, and `infrastructure/llm/registry.py:740` and `application/services/adaptive_routing.py:338` have their own. MP-3 deletes the flow's local copy rather than extending it.

---

## 1. Design principles applied

| Module | Paradigm / pattern | Why here |
|--------|-------------------|----------|
| `domain/` (round and candidate value objects) | Immutable **value objects** (frozen dataclasses). New fields carry defaults. | Domain stays dependency-free. Defaults keep `--resume` working with older state files (CLAUDE.md §5 key invariants). |
| Convergence and verdict logic | **Functional core**: pure functions over value objects. The loop in `IterativeCritiqueFlow` is the imperative shell. | Unit-testable without mocks, and deterministic. `check_convergence` already is this, so extend it rather than replace it. |
| Verdict → next action | Explicit **state machine**: `Verdict` enum → `NextStep` enum via one lookup table. | Removes the implicit "everything that isn't ACCEPT is REVISE" branch that caused IC-3. |
| Flows | Existing **Strategy** (`WorkflowStrategy.get_phases`) + `PhaseStep`. No new flow class. | Runner, retries and observers stay single-sourced (`runner.resolve_phases`). |
| Synthesis post-processing | Extract a shared **pure finaliser** used by both synthesis paths (DRY; Template Method at function level). | IC-6 and MP-7 then share one parser, one promotion-rule call and one citation policy instead of two diverging copies. |
| Model metadata, bloc lookup | **Hexagonal port**: `get_model_registry_port().bloc_of()` from `core/ports`. | `application → core/ports` is allowed (`.importlinter` contract 2); a hard-coded vendor table is not needed. |
| Prompts | Prompt builders stay in `phases/`. All model and web text goes through `_wrap_external_content()`. | Propagation-resistance invariant (`tests/test_mind_virus_resistance.py`). |
| Tunables | Named constants in `core/constants_limits.py`. | Matches `PHASE_RETRY_BUDGETS`, `TRUNCATION` and the other limits. No per-preset config (YAGNI). |
| Swallowed failures | `core.degrade.degraded()` + a `phase_warning` event. | One existing, observable mechanism for "we continued, but worse". |

---

## 2. Work packages

Order is by severity first, then by dependency. Each package lists files, change,
pattern, tests and the acceptance criterion.

### PR 1 — correctness and safety (IC-1, MP-1, IC-5, IC-4)

#### IC-1 — Route generator and critic to different labs

- **Files:** `domain/preset_registry.py` (both `iterative-critique-*` presets), `tests/test_preset_validation.py`.
- **Change:** add `expert_1` (generator) and `expert_2` (critic) to both presets' `routing`. Constraints:
  1. `bloc_of(expert_1) != bloc_of(expert_2)`.
  2. Both differ from `synthesis` and from each other (the same uniqueness rule the Delphi panel follows, `preset_registry.py:422-440`).
  3. Prices come from `PRICING_DB`, not registry comments (the Delphi comment records a ~7x discrepancy).
  4. Premium generator ≥ budget generator on the house intelligence index.
  - Candidate aliases already registered and priced for D0: `gpt-oss-120b` (US), `ministral-3b` (EU), `mimo-v2.5` (CN). Final picks: `[INPUT REQUIRED: product-owner choice of IC generator/critic models per tier]`.
- **Pattern:** declarative config. No code change. Once the roles are routed, `BlocDiversityConstraint` already enforces its rules on them.
- **Test:** `test_adversarial_roles_are_cross_bloc` in `tests/test_preset_validation.py`, driven by a table `{"iterative-critique": [("expert_1", "expert_2")]}`. For every preset of each listed method it resolves both roles (falling back to `primary_id`, as the router does) and asserts different blocs via the model-registry port. Debate can join later by adding a row.
- **Accept:** the test fails on today's registry and passes after the change.

#### MP-1 — Zero perspectives is an execution failure

- **Files:** `application/flows/perspective_phases.py`, `tests/test_perspectives_reach_state.py`.
- **Change:** after the deferred write (keep it after the loop — the blindness invariant), `raise PhaseError("All perspectives failed: ...", phase=2, phase_name="Perspectives")` when `new_candidates` is empty. Include the collected `new_errors` in the message. One surviving candidate is valid: continue, and emit a `phase_warning` that ranking is meaningless with n=1.
- **Pattern:** fail fast at the boundary. Uses the existing `core.exceptions.PhaseError`. The runner's `critical=True` path (`runner.py:241-256`) then aborts the run, as designed.
- **Check first:** what `is_retryable(PhaseError)` returns (`core/exceptions.py:251`). If False, the runner aborts without the retry it gives a provider error. Decide whether a retry is wanted (§6, Q2); it costs four more calls.
- **Tests:**
  1. All four perspectives raise: the phase raises `PhaseError` and `state.errors` carries all four messages.
  2. One survives: no raise, one candidate, one warning.
  3. The existing "candidates reach state" and mind-virus blindness tests still pass.
- **Accept:** a run with every perspective failing ends with a phase error event and no synthesis call.

#### IC-5 — Wrap model-authored text

- **Files:** `phases/iterative_critique.py`, `tests/test_mind_virus_resistance.py`.
- **Change:** in `critic_evaluation_prompt`, `generator_revision_prompt` and `synthesis_prompt`, pass `answer`, `previous_answer`, the round snippets and the best answer through `_wrap_external_content()`. Wrap the critic's `flaws_identified` JSON in the revision prompt too: it is model-authored.
- **Pattern:** reuse the existing shared wrapper (`phases/_shared.py:165`). No new helper.
- **Test:** a new case in `test_mind_virus_resistance.py` builds each of the three prompts with an answer containing the wrapper's closing delimiter and a fake "System:" instruction. It asserts the text appears only inside the wrapper and that the delimiter was neutralised.
- **Accept:** the test passes, and the prompts contain no raw model text outside a wrapper.

#### IC-4 — Degraded rounds never count toward convergence

- **Files:** `application/flows/iterative_critique_phases.py`, `core/constants_limits.py`, `tests/test_iterative_critique_score_shapes.py`.
- **Change:**
  1. Add `degraded: bool = False` to `AdversarialRound`. The synthetic parse-failure round sets it, and so does the generator parse-failure path (see IC-2).
  2. `check_convergence` filters `degraded` rounds out before the `score_converged` and `stalemate_detected` windows. `critic_accepted` cannot come from a degraded round, since a synthetic round is never ACCEPT.
  3. New constant `IC_MAX_CONSECUTIVE_DEGRADED = 2`. On reaching it, stop with reason `critic_unavailable`, record through `degraded("ic.critic", ...)` and emit a `phase_warning`.
- **Pattern:** functional core. `check_convergence` stays a pure function of the round list.
- **Tests:**
  1. Three degraded rounds: no `score_converged` or `stalemate_detected`; stops with `critic_unavailable` after two.
  2. Degraded rounds interleaved with real ones: the windows only see real rounds.
- **Accept:** tests pass. Existing shape tests are unchanged.

### PR 2 — data fidelity (IC-2, MP-3, MP-4)

#### IC-2 — Keep what the generator returns

- **Files:** `application/flows/iterative_critique_phases.py`, `application/flows/iterative_critique.py`, `phases/iterative_critique.py` (`_get_best_answer`), `application/services/serializers.py` (`_ser_5`, if it renders rounds).
- **Change:**
  1. A new frozen value object `GeneratorOutput(answer, key_claims, flaw_responses, changes_summary, confidence, model, degraded)`. `run_generator_phase` returns it, reading `model` from the `call_llm` metadata.
  2. The loop copies those fields onto round n. Round n's answer *is* the revision of round n−1, so a separate `revised_answer` is redundant: keep the field for resume compatibility, stop writing it, and make `_get_best_answer` use `answer`.
  3. Set `critic_model` from the critic call's metadata (the JEV path already sets it).
  4. Add `flaw_responses: list[dict] = field(default_factory=list)` to `AdversarialRound`.
  5. Synthesis then receives real `changes` and can see which flaws the generator rejected (DISAGREE).
- **Pattern:** value object at the phase boundary instead of a bare `str`.
- **Resume:** all new fields have defaults. Older state files load unchanged.
- **Tests:**
  1. A generator stub returning the full revision JSON: the round carries `changes_summary`, `flaw_responses` and `generator_model`.
  2. A stub returning malformed JSON: `degraded=True` and the previous answer is kept.
- **Accept:** a two-round run's synthesis prompt shows a non-empty `changes`.

#### MP-3 — Record the serving model; one bloc source

- **Files:** `application/flows/perspective_phases.py`.
- **Change:**
  1. `_get_perspective` keeps the metadata (`raw, meta = ...`) and sets `model_used=meta.get("model", "")`.
  2. Replace the local `_US/_CN/_EU` table and `_bloc()` with `get_model_registry_port().bloc_of()`.
  3. The pre-run diversity warning stays (it predicts from routing). Add a post-run check over the actual `model_used` values: fallbacks can collapse diversity even when routing was diverse.
- **Pattern:** hexagonal port instead of a duplicated table (one source of truth).
- **Tests:**
  1. `model_used` is populated from the stub metadata.
  2. The post-run warning fires when two perspectives fell back to the same model.
  3. The bloc warning still fires for an all-US routing.
- **Accept:** the local vendor table is gone. `rg "_CN = \{" src/reasoner/application/flows` finds nothing.

#### MP-4 — Stress results reference their candidate

- **Files:** `phases/multi_perspective.py` (`stress_test_prompt`), `perspective_phases.py` (`run_stress_test_phase`), `domain/core_types.py` (`StressTestResult`), `application/services/serializers.py` (`_ser_4`), `ui-next/src/lib/types` (only if the UI types `stress_results`).
- **Change:**
  1. The prompt schema becomes `{"stress_tests": [{"perspective", "scenario", "survival_rate", "failure_mode", "recovery_path"}]}`, with one entry per candidate × scenario.
  2. `StressTestResult` gains `perspective: str = ""` (default for resume).
  3. The parser coerces `perspective` through `PerspectiveRegistry.coerce` and drops entries naming a perspective not in `top_candidates`.
- **Pattern:** prompt contract + defensive parse, the same style as `_parse_critique_scores` (`core/parsing.py:686`).
- **Tests:** a stub with two candidates × three scenarios yields six results with the correct perspectives. An unknown perspective is dropped. A missing `recovery_path` gives `""`.
- **Accept:** the serializer output shows a per-candidate survival rate.

### PR 3 — behaviour (IC-3, MP-2, MP-5, MP-6)

#### IC-3 — REJECT regenerates, REVISE patches

- **Files:** `application/flows/iterative_critique.py`, `application/flows/iterative_critique_phases.py`, `phases/iterative_critique.py`.
- **Change:**
  1. Add `Verdict` (ACCEPT/REVISE/REJECT) and `NextStep` (STOP/REVISE/REGENERATE) enums, mapped by a single dict. An unknown verdict string is treated as REVISE, the current behaviour.
  2. On REGENERATE, the generator runs the *initial* prompt plus a wrapped "rejected approach" block: the rejected answer's approach summary and the critic's flaws, framed as pitfalls to avoid. Without that block, a fresh run would likely reproduce the rejected answer.
  3. Count REGENERATE rounds against `MAX_ROUNDS` like any other round.
- **Pattern:** state machine (enum + transition table) in the functional core.
- **Tests:**
  1. A REJECT round makes the next generator call use `GENERATOR_INITIAL_SYSTEM` with the pitfalls block, not the revision prompt.
  2. The transition table covers all three verdicts plus an unknown one.
- **Accept:** tests pass. A REVISE path is unchanged.

#### MP-2 — An unranked fallback is visible

- **Files:** `application/flows/perspective_phases.py`, `domain/pipeline_state.py`, `phases/_universal.py` (`synthesis_prompt`).
- **Change:**
  1. In the critique except-branch, route through `degraded("mp.critique", ...)`, set `state.ranking_degraded = True` (new field, default `False`) and emit a `phase_warning`.
  2. `synthesis_prompt` adds one line when `ranking_degraded` is set: the candidates were not independently scored, so do not present any as "top-ranked".
  3. The runner's existing gate retry stays the first line of defence. This only changes what happens after it is exhausted.
- **Pattern:** explicit degradation (existing `degraded()` + event) instead of a silent fallback.
- **Test:** malformed scorer output on both attempts → `ranking_degraded` is True, a warning event is present, and the synthesis prompt carries the note.
- **Accept:** there is no unranked-but-silent path.

#### MP-5 — Evidence search: skip when pointless, vet when used, own prompt

- **Files:** `application/flows/multi_perspective.py`, `application/flows/perspective_phases.py`, `phases/multi_perspective.py`, `flows/search_phases.py` (reuse only).
- **Change:**
  1. `get_phases` adds the `1.5 Evidence Search` step only when `state.complexity != "simple"` — the same condition already used for stress testing.
  2. A dedicated `MP_EVIDENCE_PLAN_SYSTEM` / `mp_evidence_plan_prompt` in `phases/multi_perspective.py` replaces the borrowed article prompt. Same output schema (`{queries[]}`), so the parser is unchanged.
  3. Pass the results through the existing batch vetting used by `run_context_vetting_phase` (`search_phases.py:103`, `cot_detection_batch_prompt`) and populate `vetted_context`. Reuse the existing function; don't fork it. If it can't be called standalone, extract its batch-vet core into a module-level function in `search_phases.py` first, as a pure refactor commit.
- **Pattern:** reuse over duplication; a conditional step in the existing Strategy.
- **Cost note:** vetting adds one batch LLM call per non-simple run, and skipping simple runs removes 1 LLM call + 3 searches. Measure the net effect on the budget preset with `benchmarks/measure_pipeline.py` before merging.
- **Tests:** a simple-complexity state has no 1.5 step. A non-simple state's evidence results land in `vetted_context`, with flagged sources removed.
- **Accept:** tests pass. The budget run's cost delta is recorded in the PR description.

#### MP-6 — Named limits

- **Files:** `core/constants_limits.py`, `perspective_phases.py`.
- **Change:** add `MP_TOP_K = 2` and `MP_CANDIDATE_CAP = 8` and use them in `run_critique_phase`. No behaviour change.
- **Test:** none needed (trivial). Existing tests cover the behaviour.

### PR 4 — shared synthesis contract (IC-6, MP-7)

#### Step 0 — Extract the finaliser (pure refactor, its own commit)

- **Files:** `application/flows/synthesis_phase.py`.
- **Change:** move everything after the LLM call in `run_synthesis_phase` into `finalize_solution(raw: str, state: PipelineState, services) -> FinalSolution`. That covers prose extraction and fallbacks, the artifact scrub, claim labels, evidence + `apply_promotion_rules`, blueprint sanitising, the provenance report and the citation policy. `run_synthesis_phase` calls it.
- **Pattern:** Template Method at function level. The prompt varies per method; finalisation is shared.
- **Test:** `test_synthesis_fixes.py` and `test_synthesis_hyperagent.py` pass unchanged. That is the proof the refactor is behaviour-neutral.

#### IC-6 — IC synthesis uses the shared contract

- **Files:** `phases/iterative_critique.py` (`SYNTHESIS_SYSTEM`, `synthesis_prompt`), `iterative_critique_phases.py` (`run_synthesis_phase`).
- **Change:**
  1. The IC synthesis prompt keeps its debate-trail context (rounds, convergence reason, flaw responses from IC-2, best answer).
  2. It adopts the shared output format: `[SOLUTION]…[/SOLUTION]` + JSON with `critical_insights, action_blueprint, open_questions, claim_labels, evidence, sources, meta_audit`.
  3. Compose the system prompt from `phases._universal.SYNTHESIS_SYSTEM` plus an IC-specific paragraph. Don't copy the universal text.
  4. `run_synthesis_phase` calls `finalize_solution()`.
- **Additional requirement:** flaws the critic raised and the final round still lists go into `open_questions` or are labelled `HYPOTHESIS` / `UNKNOWN`. A debate that ends on `max_rounds_reached` must not read as settled.
- **Test:** a stubbed IC run yields a `FinalSolution` with claim labels and a blueprint. A model-sourced `VERIFIED` comes out as `HYPOTHESIS` (promotion rules applied).
- **Accept:** IC output is structurally identical to multi-perspective output.

#### MP-7 — Enforce citation integrity (all methods)

- **Files:** `application/flows/synthesis_phase.py` (inside `finalize_solution`).
- **Change:**
  1. A URL in prose that is not in `vetted_context ∪ web_discovery_results ∪` Prism citations ∪ URLs in `state.problem` is unlinked. Markdown `[title](url)` becomes `title [citation removed: not in retrieved sources]`, and a bare URL is removed.
  2. The `sources` array loses the same URLs.
  3. Removals are counted in `state.meta.provenance_report["citations_removed"]` and emit one `phase_warning`.
- **Pattern:** pure function `enforce_citations(text, allowed_urls) -> (text, removed)`. Unit-test it in isolation.
- **Watermark contract:** Layer B's egress rewrite rejects a rewrite that drops a citation present before it (`watermark-removal-integration.md` §5.5). Enforcement runs in synthesis, *before* Layer B, so the rewrite only ever sees allowed URLs and the contract still holds. Keep the order.
- **Tests:**
  1. Fabricated URL removed, allowed URL kept, user-supplied URL kept, trailing-slash variants match.
  2. `test_synthesis_fixes.py` still passes.
- **Accept:** no method can return a link that is not in its context.

---

## 3. Sequencing

```
PR1 (IC-1, MP-1, IC-5, IC-4)  →  PR2 (IC-2, MP-3, MP-4)  →  PR3 (IC-3, MP-2, MP-5, MP-6)
                                       │
                                       └──→  PR4 (step 0 → IC-6 → MP-7)   [IC-6 needs IC-2's flaw_responses]
```

- PR1 items are independent of each other and can land in any order.
- PR4 step 0 is behaviour-neutral and can land any time. IC-6 must follow IC-2.
- MP-7 changes output for **every** method. Land it last and alone, so a regression is easy to bisect.

## 4. Cross-cutting checks for every PR

- **Gates:** `python -m pytest tests/ -m "not slow and not integration" -n auto --dist loadscope` green, `lint-imports` green (no new `application → infrastructure` imports; this plan uses only `core/ports`), `tests/architecture/test_layer_boundaries.py` green.
- **Resume:** every new state or dataclass field has a default, and new dict access uses `.get()`.
- **Parsing:** `extract_json()` only. No `json.loads` on LLM output.
- **Maps:** run `scripts/check_skill_maps.py`. No new files are planned, so no map should go stale.
- **Docs:** update `docs/METHOD_COMPARISON.md` (IC REJECT behaviour, MP stress output) and the IC section of `docs/methods_and_presets.md` with the new roles.

## 5. Out of scope

- Changing the runner's "an exhausted gate is a completion" policy (`runner.py:269-274`). It is correct; MP-1 works with it.
- Per-preset overrides for `MP_TOP_K` or IC round limits. Nothing requests them.
- Adding Debate to the cross-bloc pair test. IC-1's table makes it a one-row follow-up.
- JEV behaviour. IC-4's degraded flag applies only to the LLM critic's synthetic round. JEV's own failure path already returns `None` and falls through to the LLM critic.

## 6. Open questions

1. IC-1 model picks per tier — PR 1 ships provisional picks, still `[INPUT REQUIRED: product owner]`: budget `gpt-oss-120b` (US) generator / `mimo-v2.5` (CN) critic; premium `qwen3.7-max` (CN) generator / `mistral-medium-3-5` (EU) critic. Prices are from PRICING_DB. "Premium generator >= budget generator" was judged from price and lab positioning, not measured against an intelligence index.
2. MP-1: resolved in PR 1 — `PhaseError` inherits `retryable = False` from `ReasonerError`, so the runner aborts immediately. No retry of the four perspective calls.
3. MP-5: is one extra vetting call per non-simple budget run acceptable? Decide after the benchmark.
