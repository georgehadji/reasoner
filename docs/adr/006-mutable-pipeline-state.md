# ADR-006: `PipelineState` is Intentionally Mutable

**Status:** Accepted · **Date:** 2026-09-12
**Context:** Records an update model the codebase has always had in practice, and retires the abstraction that claimed otherwise.
**Supersedes:** the `PhaseOutput` / `StateTransition` delta discipline proposed in `ARCHITECTURE_REMEDIATION_PLAN.md` §C1 and item 1.4 of `remediation-plan-v2-9.5.md` (both at the repo root).
**Closes:** item 4.3 of `docs/plans/architecture-score-9-remediation-plan.md`.

## Context

A `PhaseOutput` dataclass was added to `domain/pipeline_state.py` to make phase functions
return typed deltas that a sequential reducer would apply to `PipelineState`, eliminating
concurrent-write hazards in parallel phases. The migration was never completed, and the
half-built result misrepresented the codebase to every reader:

- `PhaseOutput` was constructed in exactly **one** place —
  `application/flows/perspective_phases.py` — using 2 of its 12 fields.
- That one construction passed `mutated_in_place=True`, whose only effect was to make
  `apply_to()` return immediately. The reducer was disabled at its sole call site.
- The phase then wrote its results into `state` by hand and returned the object anyway,
  from a function annotated `-> None`.
- **All three** phase executors discard a phase function's return value:
  `api/execution/pipeline.py` (SSE driver), `application/flows/runner.py`
  (`WorkflowRunner`), and `application/flows/services.py` (services fallback).
- The only code that ever called `apply_to()` was `execute_phases_dag`, a fourth,
  production-dead phase executor, deleted in `78e6e48`.

The abstraction was not merely unused — it actively misled. `tests/test_perspectives_reach_state.py`
exists because Phase 2 once built a `PhaseOutput`, returned it, and had it dropped: Phase 3
hit `if not state.candidates: return`, skipped with zero tokens, and the UI rendered "No
content for this phase" after the run had already paid for every perspective. Documents
across the repo continued to describe the delta pattern as the rule, and at least one live
plan (`docs/plans/sycophancy-mitigation.md`) instructed a future implementer to return a
`PhaseOutput` from a new phase — which would have reproduced that defect exactly.

The choice was to finish the migration or to retire it. Finishing it is a far larger change
than it appears: it alters the degradation contract (a phase that times out mid-flight today
has already written its partial results; under a delta model it would write nothing), and
`PhaseOutput` covers only `core` fields, so the majority of phases — which write
`method_state`, `meta`, or `remainder` — could not be expressed in it at all.

## Decision

**`PipelineState` is a mutable object, threaded explicitly through every phase.**

1. The phase contract is `async def run_*_phase(state, services, ...) -> None`. Phases
   mutate `state` directly and return nothing. Executors do not inspect return values.
2. There is no reducer and no delta type. `PhaseOutput`, `apply_to()` and
   `mutated_in_place` are deleted.
3. **Parallel phases accumulate into local variables and write to `state` once, after
   joining.** This is a requirement, not a style preference — see below.
4. State is read and written through the flat `PipelineField` descriptors
   (`state.candidates`) or the containers they alias (`state.core.candidates`). These are
   the same objects.

### The constraint that survives the retirement

Rule 3 is load-bearing for a security invariant, not just for concurrency.

Phase-2 generators must not see each other's output. This is one of the four
propagation-resistance properties in `CLAUDE.md` §5: a separate topology is what limits
propagation between models, and converting Phase 2 to a fully-connected topology is the
single most damaging change available in the perspectives path.

Blindness is enforced at the prompt by
`tests/test_mind_virus_resistance.py::TestPhaseTwoGeneratorsAreBlind`, which asserts that
`perspective_prompt` does not reference `candidates` at all. The deferred write is the
second, structural half: because `run_perspectives_phase` accumulates locally and extends
`state.candidates` only after the loop completes, a sibling's output is not reachable
through `state` while any perspective is still being prompted. That matters most on the
**sequential** branch (`python main.py --sequential`), which builds each prompt after the
previous candidate already exists.

Appending to `state.candidates` inside either loop would remove that barrier and leave the
invariant resting on a single test of one function's source text.

## Consequences

**Positive:**
- The code now says what it does. A reader of any phase function sees one update model.
- A documented instruction to write a known bug is removed from the repo.
- One domain class, one dead method and a permanently-true flag are gone; `PipelineState`
  drops an abstraction that never applied to it.

**Negative:**
- The "functional core, imperative shell" target in score-9 item 4.3 is **abandoned, not
  achieved**. This ADR closes that item by choosing the other branch it offered.
- Concurrent-write safety in parallel phases now rests on the accumulate-then-write
  convention rather than on a type. The convention is enforced by review, by this ADR, and
  by the comment at the head of `run_perspectives_phase` — not by the compiler.
- If a future phase needs a genuine delta (for replay, speculative execution, or
  transactional rollback), it starts from scratch rather than from an existing seam. That
  is the correct trade: the existing seam did not work, and its presence implied a
  guarantee that was never delivered.

## Compliance

- `grep -rn "PhaseOutput" src/` must return nothing. In `tests/`, the only permitted
  mention is the historical docstring in `tests/test_perspectives_reach_state.py`.
- `tests/test_perspectives_reach_state.py` guards the behaviour (candidates reach
  `PipelineState`; Phase 3 does not skip; failures land in `state.errors`). It asserts
  outcomes, never a type, and must not be weakened to accommodate a future refactor.
- `tests/test_mind_virus_resistance.py::TestPhaseTwoGeneratorsAreBlind` guards the
  blindness invariant at the prompt.
- `[UNKNOWN]` No automated gate currently prevents a new zero-caller abstraction of this
  kind from being added. A ratcheted dead-code pass over `src/` is proposed as the fitness
  function in `docs/plans/phaseoutput-retirement-2026-09-12.md` §P-5 and is **not yet
  implemented**.
