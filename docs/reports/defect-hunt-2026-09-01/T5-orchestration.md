# T5 — Pipeline Orchestration · Autonomous Defect-Hunt Protocol V7

Worktree `.worktrees/defect-hunt`, branch `chore/defect-hunt-t3`. Date 2026-09-01/02.
Surface: `application/pipeline.py`, `application/orchestrator.py`, `application/flows/**`,
`application/handlers/**`. (`application/mixins/**` does not exist — see §Phase 1.)

Audit budget: 12 candidates. **budget_spent = 12.**

---

## Phase 1 — Defect-surface map

**Assertions about the map**

- **[VF]** `application/mixins/` does not exist in this tree. The tier brief and
  `CLAUDE.md` §3.2 both list it; `ls src/reasoner/application/` returns
  `commands/ event_bus/ flows/ handlers/ ports/ queries/ services/` only. The mixin
  cleanup (c7f3104) moved that logic to standalone `(state, services)` flow functions.
  **Map correction, not a code defect.**
- **[VF]** There is exactly one shared phase-execution shape on the non-SSE path, and it
  is not the one the architecture documents. `WorkflowStrategy.execute` → 
  `services.run_phase(step, state)` → `PipelineWorkflowServices.run_phase`, which
  delegates to `WorkflowRunner` **only if `self._runner is not None`**. It is always
  `None` here (D2), so the real executor is the three-line fallback
  `await step.fn(state, self); return True`.
- **[VF]** Two independent emitters produce `EventType.PIPELINE_COMPLETED` with
  different payload construction: `application/pipeline.py:530` (bus only) and
  `application/handlers/handlers.py:216` (bus **and** event store). Only the second is
  persisted, and it was the wrong one.
- **[VF]** `application/flows/pipeline_flow.py::execute_phases_dag` has no production
  caller — `tests/test_pipeline_flow_dag.py` is its only importer. DEAD.
- **[VF]** Invariant (c) — Phase-2 blindness — holds structurally, not by accident:
  `run_perspectives_phase` accumulates into a local `PhaseOutput` and only writes
  `state.candidates.extend(...)` **after** `asyncio.gather` returns, in both the
  parallel and sequential branches. `perspective_prompt(state, p_name)` therefore
  cannot see a sibling in either branch, including the hallucination-regeneration
  retry.

**Hunt queue (likelihood × blast radius × reachability)**

| # | Region | Class | Reachability |
|---|--------|-------|--------------|
| R1 | `pipeline.py:487-495` run/dispatch | 1 state-machine, 3 error-path | REACHABLE from main.py, headless.ask(), api/streaming.py |
| R2 | `handlers.py:213-224` completion event | 6 contract, 5 type | REACHABLE from all three entry points |
| R3 | `flows/runner.py` run_phase / _handle_phase_error | 3, 6 | DEAD (consequence of R1) |
| R4 | `flows/cognitive_phases.py` ToT | 4 invariant-(a), 5 boundary | REACHABLE (tot-* presets) |
| R5 | `flows/*.py` strategy `execute()` loops | 1 state-machine | REACHABLE, but `critical` is inert while R1 stands |
| R6 | `flows/perspective_phases.py` gather | 2 concurrency | REACHABLE |
| R7 | `flows/delphi_phases.py`, `jury_phases.py` | 5 boundary | REACHABLE |
| R8 | `flows/pipeline_flow.py::execute_phases_dag` | 1 | DEAD |
| R9 | `orchestrator.py::preflight` | 3 | REACHABLE |
| R10 | `flows/iterative_critique_phases.py::check_convergence` | 5 | REACHABLE |

---

## Phase 2 — Suspicion generation

**D1** — On every completed run, `handlers.py:216-224` builds `PIPELINE_COMPLETED` from
attributes `PipelineMeta` does not define, violating the payload contract that
`PipelineAggregate._apply_pipeline_completed` and `ResumePipelineCommandHandler` consume.
Class 6 (contract) + 5 (type). Severity HIGH — silently wrong persisted record, not a crash.
Innocence path: `PipelineMeta` might define `total_tokens`/`total_duration`; `state.core.final_solution` might be a string.

**D2** — `pipeline.py:492-495` constructs `WorkflowRunner` over a runner-less
`PipelineWorkflowServices` and binds the runner-aware one to an unused local, so
`WorkflowRunner.run_phase` never executes and the strategy runs through the bare
fallback. Class 1 + 3. Severity HIGH. Innocence path: `WorkflowRunner.run` might inject
itself into the services it is handed.

**D3** — `pipeline.py:530` sums `t.get("total", 0)` over `state.phase_tokens`, whose
entries are written as `{"input": N, "output": M}`. Class 6. Severity MEDIUM.

**D4** — `cognitive_phases.py:214` `state.tot_state["current_path"].append(best)` is a
direct subscript on a method-specific dict — invariant (a). Class 4.

**D5** — `cognitive_phases.py:163` `dps[len(state.tot_state.get("current_path", []))]`
can IndexError. Class 5.

**D6** — `iterative_critique_phases.py:59-60` `max(scores)` on a possibly-empty list. Class 5.

**D7** — `runner.py` exception-retry branch omits `reset_phase_state`, unlike the
quality-retry branch: a retried phase could double-write. Class 1.

**D8** — `orchestrator.py:212` imports `settings` inside a `try/except Exception: pass`,
then uses it unconditionally at line 285 → potential `UnboundLocalError`. Class 3.

**D9** — `delphi_phases.py:171` `stats.get(...)` where `aggregated_stats` may have been
set to a non-dict by the LLM fallback at line 94. Class 5.

**D10** — `jury.py:70-76` declares `critical=True` on "Critic Pool" but discards
`run_phase`'s return value, so the flag has no effect. Class 1/6.

**D11** — `pipeline_flow.py:105-112`: a non-critical phase failure never enters
`completed`, so a dependent phase makes `ready` empty and the next loop raises
`RuntimeError("Circular dependency detected")` — a misdiagnosis. Class 1.

**D12** — Resume divergence: `--resume` re-enters `pipeline.run` from the top with a
populated state, and `run_perspectives_phase` / `run_jury_generate_phase` **append**
rather than replace, so a resumed run carries duplicate candidates. Class 1.

---

## Phase 3 — Proof of defect

Harness: `tests/test_completion_event_contract.py`. The LLM is faked at
`ProviderRouter.call` (transport boundary), reusing the shape of
`tests/test_e2e_budget_presets_mock.py`. **No live API call was made.**

### D1 — FIRED

```
AssertionError: solution['core_solution'] must be the synthesis text,
                got FinalSolution
AssertionError: assert 0 > 0.0        # total_duration_seconds
```

Innocence attempt: **NO-DEFENSE-FOUND.** `PipelineMeta` (`domain/pipeline_state.py:153-171`)
defines `phase_tokens, phase_durations, phase_models, phase_results, quality_hints,
quality_history, fallback_events, preset_name, method, augmentation_methods,
context_quality, provenance_report` — no `total_tokens`, no `total_duration`, so both
`getattr(..., default)` calls return their default forever. `PipelineCore.final_solution`
is `FinalSolution | None`, not `str`. `PipelineAggregate._apply_pipeline_completed`
(`core/aggregates/pipeline.py:229-231`) assigns `solution` and `total_tokens` verbatim,
and `ResumePipelineCommandHandler.handle` returns `synthesis["core_solution"]` to the
caller as `previous_synthesis`. `event_store.save_events` serialises with
`json.dumps(asdict(event), default=str)`, so this does not raise — it silently persists a
nested dict where a string belongs. **Verdict: CONFIRMED.**

### D2 — FIRED

Instrumented probe (`WorkflowRunner.run_phase` + `EventBus.publish` spies) over a full
`multi-perspective-budget` run:

```
RUNNER_RUN_PHASE_CALLS: []
PUBLISHED: ['pipeline_started', 'llm_generation_completed' ×10, 'pipeline_completed']
PHASE_TOKENS: {}
PHASE_DURATIONS: {'_phase_fusion': 0.047, '_phase_post_synthesis_verify': 0.0}
CURRENT_PHASE_KEY: '<unset>'
```

Zero `phase_started` / `phase_completed` / `phase_failed` events. `phase_tokens` empty —
`LLMExecutor._accumulate_tokens` (`executor.py:818`) keys it off `_current_phase_key`,
which only `WorkflowRunner.run_phase:70` and `api/execution/pipeline.py:364` set.

Innocence attempt: **NO-DEFENSE-FOUND.** `WorkflowRunner.run` is
`return await strategy.execute(state, self.services)` — it hands over the services it was
constructed with, which are the runner-less ones. `WorkflowRunner` is instantiated in
exactly one place in the entire repo (`pipeline.py:492`).

**Corroboration [VF]:** wiring it up (patch applied and then reverted) fails on the very
first phase with

```
TypeError: PhaseStarted.__init__() got an unexpected keyword argument 'phase_number'
```

`PhaseStarted` has only `phase_name` and `config`; `PhaseFailed` has only `phase_name`,
`error`, `retry_count` (no `is_fatal`); and `EventType.PHASE_QUALITY_CHECKED` /
`EventType.PHASE_RETRIED` do not exist in any of the event enums. `WorkflowRunner.run_phase`
and `_handle_phase_error` have therefore **never executed**. **Verdict: CONFIRMED.**

### D3 — FIRED

Probe above: `phase_tokens` entries are `{"input": N, "output": M}`. Grep of every writer
(`executor.py:821-823`, `subagents/base.py:199-201`, `runner.py:75`) confirms no `"total"`
key is ever written; `serializers.py:1056` independently sums `input`+`output`, which is
the canonical shape. Innocence: **NO-DEFENSE-FOUND.** **Verdict: CONFIRMED.**

### D4 — CLEARED

`state.tot_state["current_path"]` is written by `run_tot_decompose_phase` (line 159) and
read by subscript only in `run_tot_evaluate_phase` (line 214). If decompose did not run
or failed, `run_tot_generate_phase` returns early on `decision_points` being empty and
`run_tot_evaluate_phase` returns early on `current_candidates` being empty, so line 214 is
unreachable without a preceding decompose. `--resume` re-enters `pipeline.run` from the
top, so decompose always re-runs and re-seeds `current_path = []`.
Trigger → DID-NOT-FIRE. Innocence → CODE-INNOCENT (early-return guards).
**Verdict: CLEARED.** Style note only: it is the sole read-subscript on a method-state
dict in the whole tier (the other 7 hits are same-function writes), so it is worth
converting on cosmetic grounds, not correctness.

### D5 — CLEARED

`dps[len(current_path)]` needs `len(current_path) >= len(dps)`. `ToTFlow.get_phases`
runs Decompose → Generate exactly once, and Decompose sets `current_path = []`
immediately after `decision_points`. Innocence → CODE-INNOCENT. **Verdict: CLEARED.**
(Would become reachable if the ToT loop were ever made iterative — noted for R4.)

### D6 — CLEARED

`max(scores)` is empty only if all of the last three `AdversarialRound`s have
`critic_score is None`. `run_critic_phase` returns a `CriticDimensionScore` on both its
success and its malformed-JSON branches, and it is the only producer of rounds.
Innocence → CODE-INNOCENT. **Verdict: CLEARED.** (The `if r.critic_score else 0.0` arm
inside that comprehension is dead — the trailing `if r.critic_score is not None` already
filters — but that is redundancy, not a defect.)

### D7 — INDETERMINATE

Real asymmetry (quality retries call `reset_phase_state`, exception retries do not), but
the containing function has never executed (D2). No executable trigger exists while D2
stands. **Verdict: INDETERMINATE — blocked on D2.**

### D8 — CLEARED

`from reasoner.core.settings import settings` is the first statement of the `try`, and
`reasoner.core.settings` is already in `sys.modules` by the time `preflight` runs (it is
imported at `application/pipeline.py:56` module scope, which `orchestrator.py:31` pulls in).
An import that cannot fail cannot leave the name unbound. **Verdict: CLEARED.**

### D9 — INDETERMINATE

`run_delphi_aggregation_phase` line 94 assigns `state.delphi_state["aggregated_stats"] =
data` straight from `extract_json`, which can return a list; `run_delphi_dissent_phase`
line 171 then calls `.get` on it. Reaching it needs an LLM to return a JSON array from
`DELPHI_AGGREGATION_SYSTEM` **and** fewer than two numeric round-1 estimates **and**
non-convergence. I could not construct that without asserting model behaviour, which is
not an executable trigger. **Verdict: INDETERMINATE.**

### D10 — CONFIRMED (latent, blocked on D2)

`JuryFlow.execute` is `await services.run_phase(step, state)` with the result discarded,
while the same file marks "Critic Pool" `critical=True`. Every sibling flow that declares
a critical step (`MultiPerspectiveFlow`, `DebateFlow`, `ResearchFlow`, `WritingFlow`,
`CodingFlow`, `BrainstormingFlow`, `DelphiFlow`) checks the return value. Innocence →
NO-DEFENSE-FOUND for the contract, but the flag is inert for **all** flows today because
the fallback executor always returns `True` (D2). **Verdict: CONFIRMED, unfixed — it and
D2 must land together.**

### D11 — CLEARED BY UNREACHABILITY

The logic bug is real: after a non-critical failure the phase never enters `completed`, so
the next iteration finds `ready == []` and raises `RuntimeError("Circular dependency
detected among: ...")` — a wrong diagnosis for a phase failure. But
`execute_phases_dag` has no production caller. **Verdict: CLEARED (DEAD CODE).** Fix it
if and when it is wired.

### D12 — INDETERMINATE

`--resume` (`src/reasoner/main.py:205`) loads the state file and passes it as
`initial_state` to a fresh `pipeline.run`, which replays every phase.
`run_perspectives_phase` ends with `state.candidates.extend(...)`, so a resumed state's
existing candidates survive and are added to. Whether "resume continues the run" or
"resume replays it" is the intended semantics is not documented anywhere I could find, so
I cannot call this a defect rather than a design choice. `run_critique_phase` caps
`state.candidates` at 8 and takes the top 2, which bounds the damage.
**Verdict: INDETERMINATE — needs a product decision, flagged for the owner.**

---

## Phase 4 — Triage inventory

| Candidate | Trigger | Innocence | Evidence basis | Status |
|---|---|---|---|---|
| D1 completion-event payload | FIRED | NO-DEFENSE-FOUND | Executed test + field-list inspection | **CONFIRMED — FIXED** |
| D2 WorkflowRunner bypassed | FIRED | NO-DEFENSE-FOUND | Executed probe (0 run_phase calls, 0 PHASE_* events, empty phase_tokens) | **CONFIRMED — NOT FIXED** |
| D3 `phase_tokens` "total" key | FIRED | NO-DEFENSE-FOUND | Executed probe + exhaustive writer grep | **CONFIRMED — FIXED** |
| D4 ToT `current_path` subscript | DID-NOT-FIRE | CODE-INNOCENT | Guard trace | CLEARED |
| D5 ToT decision-point index | DID-NOT-FIRE | CODE-INNOCENT | Phase-order trace | CLEARED |
| D6 IC empty `max()` | DID-NOT-FIRE | CODE-INNOCENT | Producer trace | CLEARED |
| D7 retry without state reset | no trigger | — | Blocked by D2 | INDETERMINATE |
| D8 `settings` unbound | DID-NOT-FIRE | CODE-INNOCENT | Import-order trace | CLEARED |
| D9 Delphi non-dict stats | no trigger | — | Requires asserting model behaviour | INDETERMINATE |
| D10 Jury inert `critical` | latent | NO-DEFENSE-FOUND | Source comparison across 8 flows | CONFIRMED, blocked on D2 |
| D11 DAG false circular-dep | n/a | UNREACHABLE | Caller grep — tests only | CLEARED (dead) |
| D12 resume duplicates state | n/a | — | Intent undocumented | INDETERMINATE |

---

## Phase 5 — Fix design

### FIX 1 — D1 (applied) · `application/handlers/handlers.py`

```diff
+def _completion_payload(state: PipelineState, *, started_at: float) -> dict[str, Any]:
+    import time as _time
+    fs = getattr(state, "final_solution", None)
+    tokens = sum(
+        t.get("input", 0) + t.get("output", 0)
+        for t in (state.phase_tokens or {}).values()
+    )
+    return {
+        "solution": {"core_solution": getattr(fs, "core_solution", "") or "" if fs else ""},
+        "total_tokens": {"total": tokens},
+        "total_duration_seconds": max(_time.monotonic() - started_at, 0.0),
+        "phases_completed": len(state.phase_results or []),
+    }
@@ RunPipelineCommandHandler.handle
+        import time as _time
+        _started_at = _time.monotonic()
@@
-                solution={"core_solution": getattr(state.core, "final_solution", "") if hasattr(state, "core") else ""},
-                total_tokens={"total": getattr(state.meta, "total_tokens", 0)} if hasattr(state, "meta") else {},
-                total_duration_seconds=getattr(state.meta, "total_duration", 0) if hasattr(state, "meta") else 0,
-                phases_completed=len(getattr(state.meta, "phase_results", []) if hasattr(state, "meta") else []),
+                **_completion_payload(state, started_at=_started_at),
```

**Causal justification:** the mechanism is "read a field the object does not have, and
pass the container where the text is expected". Extracting one helper that reads only
fields that exist removes both, at the single point where the persisted event is built.
The `hasattr` guards were load-bearing for nothing — `state` is always a `PipelineState`
here, and the descriptor aliases (`state.final_solution`, `state.phase_tokens`,
`state.phase_results`) are the documented access path.

**Risk:** LOW. The event is write-only in the completion path; the only readers
(`PipelineAggregate`, `ResumePipelineCommandHandler`, telemetry) already assume the
shape now produced. 26 lines, one new module-level function + one call site.

### FIX 2 — D3 (applied) · `application/pipeline.py:530`

```diff
-        total_tokens = sum(t.get("total", 0) for t in state.phase_tokens.values())
+        total_tokens = sum(
+            t.get("input", 0) + t.get("output", 0) for t in state.phase_tokens.values()
+        )
```

**Causal justification:** the key summed does not exist in the written shape. Risk: LOW.

**Fix interaction:** FIX 1 and FIX 2 compute the same quantity in two modules. They are
deliberately not shared: a helper would have to live in `domain/pipeline_state.py` (out of
this tier) or force `application/pipeline.py` to import from `application/handlers`,
which inverts the current direction. One expression duplicated is the cheaper debt.

### D2 + D10 — NOT APPLIED · `[REQUIRES HUMAN REVIEW: cross-boundary mechanism]`

The wiring itself is three lines, but it cannot land alone: it switches on a
retry/timeout/quality layer that has never run, and that layer crashes on its first
statement. Full diff:

```diff
--- a/src/reasoner/application/pipeline.py
+++ b/src/reasoner/application/pipeline.py
@@ ReasonerPipeline.run
             strategy = self.flow_factory.get_strategy(method)
-            runner = WorkflowRunner(PipelineWorkflowServices(self))
-            services = PipelineWorkflowServices(self, runner=runner)
-
+            services = PipelineWorkflowServices(self)
+            runner = WorkflowRunner(services)
+            # The strategy reaches run_phase through the services the runner
+            # hands it, so those services must be the ones holding the runner.
+            services._runner = runner
             await runner.run(strategy, state)

--- a/src/reasoner/application/flows/runner.py
+++ b/src/reasoner/application/flows/runner.py
@@ run_phase
         start_evt = make_event(
             EventType.PHASE_STARTED,
             aggregate_id=state.conversation_id or "unknown",
             version=1,
             phase_name=name,
-            phase_number=num
+            config={"phase_number": num},        # PhaseStarted has no phase_number field
         )
@@
-                quality_evt = make_event(
-                    EventType.PHASE_QUALITY_CHECKED, ...
-                )
-                await self.bus.publish(quality_evt)
+                # EventType.PHASE_QUALITY_CHECKED does not exist. Either add it to
+                # PipelineEventType + PIPELINE_EVENT_CLASSES (core/events, out of
+                # this tier) or drop the event and keep the existing log line.
@@
-                    retry_evt = make_event(
-                        EventType.PHASE_RETRIED, ...
-                    )
+                    retry_evt = make_event(
+                        EventType.RETRY_ATTEMPTED,   # this one exists
+                        aggregate_id=state.conversation_id or "unknown",
+                        version=1,
+                        phase_name=name,
+                        attempt=attempt + 1,
+                        reason=quality_result.reason,
+                    )
@@ _handle_phase_error
         fail_evt = make_event(
             EventType.PHASE_FAILED,
             aggregate_id=state.conversation_id or "unknown",
             version=1,
             phase_name=name,
             error=message,
-            is_fatal=is_fatal,               # PhaseFailed has no is_fatal field
         )

--- a/src/reasoner/application/flows/jury.py
+++ b/src/reasoner/application/flows/jury.py
@@ JuryFlow.execute
         for step in self.get_phases(state):
-            await services.run_phase(step, state)
+            success = await services.run_phase(step, state)
+            if not success and step.critical:
+                break
         return state
```

**`[CONSTRAINT-FORCED ESCALATION]`** — two functions in `runner.py`, plus `pipeline.py`,
plus `jury.py`, plus (for the quality event) `core/events/domain_events.py`, which is
outside this tier.

**Why it was not applied.** Three reasons, in order of weight:

1. It flips real runtime behaviour for every CLI and headless run: per-phase timeouts
   (`get_phase_timeout`) can now abort a phase, and `PhaseMonitor` can now retry a phase —
   which re-issues its LLM calls and, when the rule check fails, adds an LLM-judge call.
   That is a cost and latency decision, not a bug fix.
2. Verifying it means re-running the preset matrix with the quality gate live. The
   `-budget` mock matrix is green today with the runner **off**; it proves nothing about
   the runner **on**.
3. Half of it (the `runner.py` event repairs) is currently dead code, so applying that
   half alone is unverifiable churn.

Instead: a `KNOWN DEFECT` comment sits at `pipeline.py:492` naming this report, and
`tests/test_completion_event_contract.py::TestWorkflowRunnerWiring::test_runner_executes_phases`
is an `xfail` tripwire that flips to XPASS the moment someone wires it.

### Also observed, no fix

- `tests/test_pipeline_flow_dag.py` covers `execute_phases_dag`, which nothing calls.
  Either delete the module or wire it; the coverage is currently paying for dead code.
- `CLAUDE.md` §3.2 lists `application/mixins/`, which does not exist.

---

## Phase 6 — Self-review (RAR)

### FIX 1

| Vector | Result |
|---|---|
| Boundary | `test_token_sum_boundary_no_phases`, `test_solution_boundary_no_final_solution`, `test_token_sum_boundary_malformed_phase_entry` — empty `phase_tokens`, missing `final_solution`, half-written `{"input": 5}` entries (the shape `runner.py:75` writes on a spend-cap skip). All pass. **FIX HOLDS [VF]** |
| Invalid input | `getattr(fs, "core_solution", "") or ""` also absorbs a `FinalSolution` whose `core_solution` is `None`; `(state.phase_tokens or {})` absorbs the `None` that `PipelineField.__get__` special-cases. **FIX HOLDS [VF]** |
| State (resumed / older file) | The payload reads only `final_solution`, `phase_tokens`, `phase_results` — all `field(default_factory=…)` on `PipelineCore`/`PipelineMeta` and re-seeded by `_ensure_fields_initialized` on a partial deserialise. **FIX HOLDS [VF]** |
| Regression | `tests/test_e2e_budget_presets_mock.py` 25 passed; `test_aggregates.py`, `test_cqrs_parity.py`, `test_domain_events.py`, `test_event_types.py`, `test_stop_pipeline_handler.py`, `test_pipeline_flow_dag.py` 44 passed. No preset behaves differently — the change is confined to event construction. **FIX HOLDS [VF]** |
| Concurrency | `_completion_payload` is a pure read of a state no longer being mutated (all phases have returned). No shared mutable state, no `await`. **FIX HOLDS [VF]** |
| New defect | `_started_at` uses `time.monotonic()`, matching `pipeline.run`; it cannot go backwards, and `max(…, 0.0)` is belt-and-braces. The `**kwargs` splat into `make_event` supplies exactly the four `PipelineCompleted` fields — a typo would `TypeError` immediately and does not (test passes). **FIX HOLDS [VF]** |

### FIX 2

| Vector | Result |
|---|---|
| Boundary | Empty `phase_tokens` → `sum(())` = 0, unchanged from before. **FIX HOLDS [VF]** |
| Invalid input | Entries are always dicts (only three writers, all dict literals); `.get(…, 0)` covers a partially-written entry. **FIX HOLDS [VF]** |
| State (resumed) | `phase_tokens` has a `default_factory` and `PipelineField.__get__` returns `{}` when it is `None`. **FIX HOLDS [VF]** |
| Regression | Same suites as FIX 1. The value only ever moves 0 → real; nothing branches on it. **FIX HOLDS [VF]** |
| Concurrency | Read-only, post-run. **FIX HOLDS [VF]** |
| New defect | None: the expression is the same one `serializers.py:1056` already uses. **FIX HOLDS [VF]** |

No FIX BREAKS. No revision cycles were needed.

---

## Phase 7 — Tests

`tests/test_completion_event_contract.py` (new, 9 tests):

- proof-of-defect ×3: `test_solution_carries_synthesis_text_not_the_container`,
  `test_duration_is_measured_not_zero`, `test_total_tokens_reflect_actual_usage` — the
  first two fail on the pre-fix tree with `got FinalSolution` and `assert 0 > 0.0`.
- boundary ×3: `test_token_sum_boundary_no_phases`,
  `test_solution_boundary_no_final_solution`, `test_token_sum_boundary_malformed_phase_entry`.
- second-emitter contract ×1: `TestPipelineRunCompletionEvent::test_bus_event_total_tokens_nonzero`.
- no-regression ×1: `TestNoRegression::test_run_still_completes_with_a_synthesis`
  (synthesis produced, aggregate `status == "completed"`, exactly
  `[PIPELINE_STARTED, PIPELINE_COMPLETED]` persisted, no `PIPELINE_FAILED`).
- D2 tripwire ×1: `TestWorkflowRunnerWiring::test_runner_executes_phases`, `xfail`.

```
8 passed, 1 xfailed in 148.27s
```

Regression suites:

```
tests/test_e2e_budget_presets_mock.py ................  25 passed in 128.05s
tests/test_aggregates.py tests/test_cqrs_parity.py tests/test_domain_events.py
tests/test_event_types.py tests/test_stop_pipeline_handler.py
tests/test_pipeline_flow_dag.py ......................  44 passed in 96.33s
```

Gates:

```
lint-imports --verbose      Contracts: 1 kept, 0 broken.
```

---

## Phase 8 — Verdict, coverage and residual risk

**Confirmed by severity**

- HIGH — D2 `application/pipeline.py:492-495`: the `WorkflowRunner` is bypassed on every
  non-SSE run. NOT FIXED, `[REQUIRES HUMAN REVIEW]`.
- HIGH — D1 `application/handlers/handlers.py:216-224`: `PIPELINE_COMPLETED` carried the
  `FinalSolution` container instead of the synthesis text, and 0 tokens / 0 seconds.
  FIXED.
- MEDIUM — D3 `application/pipeline.py:530`: summed a `"total"` key `phase_tokens` never
  carries. FIXED.
- MEDIUM — D10 `application/flows/jury.py:70-76`: `critical=True` is inert. NOT FIXED,
  must land with D2.

**Cleared:** 5 (D4, D5, D6, D8, D11). **Indeterminate:** 3 (D7, D9, D12).

**Surface audited**

`pipeline.py` (full), `orchestrator.py` (full), `handlers/handlers.py` (full),
`flows/`: `base`, `factory`, `runner`, `services`, `pipeline_flow`, `multi_perspective`,
`perspective_phases`, `synthesis_phase`, `cognitive`, `cognitive_phases` (ToT/SoT/CoVE
regions), `debate`, `jury`, `jury_phases`, `delphi`, `delphi_phases`, `research`,
`writing`, `coding`, `brainstorming`, `iterative_critique`, `iterative_critique_phases`,
`augmentation`, `search_phases` (deep-read region only).

**NOT audited** — `flows/article.py`, `article_adapters.py`, `article_phases.py`,
`dialectical.py`, `dialectical_phases.py`, `prism_research.py`, `research_phases.py`,
`writing_phases.py`, `coding_phases.py`, `brainstorming_phases.py`,
`debate_phases.py`, `egress_rewrite_phase.py`, `language_probe_phase.py`, the bulk of
`search_phases.py`, and `application/handlers/` beyond `handlers.py`. `article_adapters.py`
(651 lines) is the single largest un-audited region and the only one with its own
adapter-layer state machine.

**Defect classes covered:** 1 state-machine (D2, D11, D12), 2 concurrency (D6 region;
`perspective_phases` gather reviewed and clean), 3 error paths (D1, D7, D8), 4 invariant-(a)
(D4 — exhaustive regex sweep of the tier), 5 boundary (D5, D9), 6 contract (D1, D3, D10).

**Clean-claim scope:** only that the two fixed defects no longer reproduce under the
executed tests, and that the five cleared candidates have a demonstrated guard. Nothing
here says the pipeline is correct — D2 means an entire declared robustness layer has never
run, so the non-SSE path's failure behaviour is largely uncharacterised.

**Highest-value next hunt:** `flows/article_adapters.py` + `article_phases.py`, then a
dedicated `--resume` round-trip hunt (`models.save` → `PipelineSerializationService._from_dict`
→ full replay) comparing a resumed run against a fresh one field by field.

### Invariants

- **(a) `.get()` not subscript on method-specific dicts — HOLDS.** A regex sweep of
  `application/**` for a *read* subscript on a `*_state` field returns 8 hits; 7 are
  format strings reading a key written two lines above in the same function
  (`article_phases.py:217-218`, `writing_phases.py:128-129`, `augmentation.py:296`, plus
  two docstring mentions). The eighth (`cognitive_phases.py:214`) is guarded by two
  upstream early returns — CLEARED under Phase 3b.
- **(b) `extract_json`, never `json.loads` — HOLDS** in this tier. The only `json.loads`
  in `application/**` outside T1/T2-owned files is `handlers.py:444`, reading the app's
  own on-disk history files, not an LLM response.
- **(c) Phase-2 generators blind to each other — HOLDS**, and structurally rather than by
  luck: `run_perspectives_phase` writes `state.candidates` only after `gather` returns,
  in both the parallel and sequential branches, so `perspective_prompt(state, …)` cannot
  observe a sibling.
- **(d) External text wrapped, never interpolated raw — HOLDS** on the paths audited.
  `_wrap_external_content` / `build_web_sources_block` are used in `phases/_universal.py`;
  attachment injection in `pipeline._build_attachment_context` uses explicit
  `[CONTENT START]/[CONTENT END]` markers.

### Repo-hazard report (no action taken)

**The ruff ratchet is now failing, and only part of it is mine.** `scripts/ruff_ratchet.py
--max 2249` reports `2243 violations … FAIL: below ratchet`. Measured by reverting only my
two files: baseline **2247** (already 2 below MAX before I touched anything — T3/T4 or
uncommitted worktree state), mine **-4** (FIX 1 replaced four over-length lines). Per the
brief I did not edit the constant. Whoever lands last must set the final number in **both**
`scripts/ci-local.sh:51` and `.github/workflows/test.yml`.

### Uncertainty acknowledgment

- **Most likely false positive:** D10. The `critical` flag is inert for every flow while
  D2 stands, so calling Jury's the outlier is a reading of intent from a source
  comparison, not from observed behaviour.
- **Defect most likely missed:** something in `article_adapters.py` — 651 lines of
  adapter-layer state transitions I did not open, reached by a preset family (writing /
  article) that is fully wired.
- **Needs runtime validation:** everything downstream of D2. Wiring the runner will
  surface how `PhaseMonitor`'s rules actually score real phase output, how often phases
  hit `get_phase_timeout`, and what the retry cost is per preset. None of that can be
  answered from the mock harness.
- **What static analysis cannot determine:** D9 and D12. D9 needs a model that returns a
  JSON array where an object is expected; D12 needs a documented answer to "does
  `--resume` continue or replay?".
- **Input that would most increase confidence:** one recorded production trace from each
  entry point (CLI, headless, SSE) with `phase_tokens`, `phase_durations` and the full
  event stream — that would settle D2's real blast radius and immediately confirm or kill
  D12.
