# Plan: Retire `PhaseOutput` — close the half-built immutability migration

**Status:** Draft, awaiting decision · **Date:** 2026-09-12
**Branch context:** `refactor/delete-dag-phase-executor` @ `78e6e48`, based on `studio-adopt` @ `0235e4d`.
**Bucket:** follow-on to *Phase G — Delete* of
[architecture-score-9-remediation-2026-09-09.md](architecture-score-9-remediation-2026-09-09.md).
**Resolves:** item 4.3 of
[architecture-score-9-remediation-plan.md](architecture-score-9-remediation-plan.md).

---

## 0. Why this exists now

`78e6e48` deleted `application/flows/pipeline_flow.py::execute_phases_dag`, the dead DAG
phase executor. That function was the **only** caller of `PhaseOutput.apply_to()`. The
reducer did not become dead in that commit — it became *visibly* dead. This plan decides
what happens to the abstraction it belonged to, rather than leaving a domain class whose
central method is unreachable.

Item 4.3 of the score-9 plan already anticipated this and set the constraint:

> Either finish the migration and delete the flag, or formally retire `PhaseOutput` and
> document `PipelineState` as intentionally mutable. **Do not leave it half-built** — a
> half-finished abstraction misrepresents the actual update model to every reader.

---

## 1. What is true today

All claims below were verified against the working tree at `78e6e48`.

### 1.1 The class

`[VERIFIED]` `PhaseOutput` is declared at `domain/pipeline_state.py:196-238`. It has 11
delta fields plus `mutated_in_place: bool = False` (`:211`), and one method,
`apply_to(state) -> None` (`:213`), whose first statement is
`if self.mutated_in_place: return`.

`[VERIFIED]` `apply_to()` has **zero callers** in `src/`, `tests/`, `scripts/` or `sdk/`.

### 1.2 The single construction site

`[VERIFIED]` `PhaseOutput` is constructed exactly once in the entire repository, at
`application/flows/perspective_phases.py:185`:

```python
output = PhaseOutput(candidates=[], errors=[], mutated_in_place=True)
```

It uses **2 of its 12 fields**, passes `mutated_in_place=True` (permanently disabling the
reducer), serves as a **local accumulator** for the duration of the function, is drained
manually into the state at `:238-239`:

```python
state.candidates.extend(output.candidates)
state.errors.extend(output.errors)
```

…and is then returned at `:240` into a void. `run_perspectives_phase` is annotated
`-> None` (`:86`), so the `return` statement contradicts its own signature.

**In other words: `PhaseOutput` is not used as a delta anywhere. It is used as a mutable
two-field bag with ten unused fields and a dead method attached.**

### 1.3 Nothing consumes a phase's return value

`[VERIFIED]` All three phase executors discard it:

| Executor | Call site |
|---|---|
| SSE driver | `api/execution/pipeline.py:301` — `await fn(state, _services)` |
| `WorkflowRunner` | `application/flows/runner.py:168` — `await asyncio.wait_for(fn(state, self.services, **kwargs), timeout=timeout)` |
| Services fallback | `application/flows/services.py:99` — `await step.fn(state, self, **kwargs)` |

`[VERIFIED]` Every other phase function in `application/flows/` mutates `state` in place
and returns `None`. Phase 2 is the sole deviation, and the deviation is cosmetic.

### 1.4 The two write paths are equivalent

`[VERIFIED]` `apply_to()` writes `state.core.candidates`; `perspective_phases` writes
`state.candidates`. These are the same list: `candidates` and `errors` are
`PipelineField("core")` descriptors at `pipeline_state.py:366` and `:372`. There is no
behavioural difference between the reducer and the manual drain — only an unreachable one.

### 1.5 The abstraction is an active trap

This is the strongest argument against leaving it in place.

`[VERIFIED]` `docs/plans/sycophancy-mitigation.md:400` — a **live, unshipped plan** —
instructs a future implementer to, in `flows/decomposition_phase.py`, "call
`_parse_premises` and return `PhaseOutput(premises=...)`", with `:206-207` adding the
matching `apply_to` branch.

Written as specified, against today's executors, **the premises would silently vanish** —
no executor applies the return. That is bit-for-bit the defect
`tests/test_perspectives_reach_state.py` was written to prevent: Phase 2 spent tokens,
built a delta, returned it, and `state.candidates` stayed empty, so Phase 3 hit
`if not state.candidates: return` and the UI rendered "No content for this phase".

Keeping `PhaseOutput` keeps that trap armed for the next author who trusts the docstring.

### 1.6 Six documents describe a pattern that does not exist

`[VERIFIED]` the following describe `PhaseOutput` as live, load-bearing, or as the rule:

| Location | Claim | Reality |
|---|---|---|
| `REASONER_COMPLETE_SYSTEM_DOCUMENTATION.md:1402` | "**Rule**: No mutation of PipelineState except via PhaseOutput reducers" | False for every phase in the codebase |
| `REASONER_COMPLETE_SYSTEM_DOCUMENTATION.md:39` | "Sequential reducers (`PhaseOutput.apply_to()`) transform state deterministically" | The reducer is unreachable |
| `remediation-status-report.md:110-111` | "✅ Used in parallel perspectives / ✅ Used in pipeline flow reducer" | The second is deleted; the first is an accumulator with the reducer disabled |
| `remediation-plan-v2-9.5.md:91-119` | Open item 1.4: extend `PhaseOutput` to 6+ more parallel sites | Direct conflict with score-9 item 4.3 |
| `ARCHITECTURE_REMEDIATION_PLAN.md:119` | Proposes introducing the `StateTransition` discipline | Was introduced, then abandoned unfinished |
| `.claude/skills/map-domain/SKILL.md:17` | Lists `PhaseOutput` among the state model's sub-containers | It is not a state container |

Phase G's stated deliverable includes "five false documentation claims." This is a sixth
cluster in the same family.

---

## 2. Decision

### Option A — Retire `PhaseOutput` *(recommended)*

Delete the class, the reducer and the flag. Replace the one construction site with two
plain local lists. Record the update model in an ADR: `PipelineState` is **intentionally
mutable**, and the phase contract is `async (state, services) -> None`.

### Option B — Finish the migration

Make the executors apply returns; convert phase functions to return deltas.

Rejected for this bucket. Cost and risk, both verified:

- Three executors must change, including the retry/timeout path at `runner.py:168`. Today
  a phase that times out mid-flight has already written its partial results to `state`;
  under a delta model it would write nothing. That is a **behavioural change to the
  degradation contract**, not a refactor, and it interacts with the per-phase retry budget.
- ~30 phase functions across `application/flows/` would need converting, or the codebase
  carries two contracts indefinitely — which is the present condition, restated.
- `PhaseOutput` covers only `core` fields. Phases writing `method_state`, `meta`, or
  `remainder` (most of them) cannot express themselves as a `PhaseOutput` at all, so the
  migration cannot actually complete without a much larger delta type.

Option B may be right eventually. It is a multi-week workstream with its own plan, not a
Phase G deletion. If it is ever undertaken, it should start from a clean contract rather
than from a decade-old flag.

### Option C — Leave it

Explicitly forbidden by item 4.3. Also refuted by §1.5: this is not inert dead code, it is
a documented instruction to write a bug.

**Recommendation: Option A.**

---

## 3. Constraints any implementation must respect

1. **Dependency rule.** `PhaseOutput` lives in `domain/`. `[VERIFIED]` it is imported by
   exactly one application module and re-exported by nothing — not `models.py`, not
   `domain/__init__.py`, not `sdk/`. Deleting it touches no port, adapter, or API surface.

2. **Phase-2 blindness — do not linearise the write.** `[VERIFIED]` Phase-2 generators
   must not see each other; this is one of the four propagation-resistance invariants in
   CLAUDE.md §5 and is enforced by
   `tests/test_mind_virus_resistance.py::TestPhaseTwoGeneratorsAreBlind`, which asserts
   the string `"candidates"` does not appear in `inspect.getsource(perspective_prompt)`.

   The accumulator must therefore remain an **accumulator**: collect locally, write to
   `state` **once, after** the `gather` (parallel branch) or after the loop (sequential
   branch) completes. `[INFERENCE]` The sequential branch is where this matters most — it
   builds each prompt after the previous candidate exists, so an incremental write would
   remove the structural barrier and leave only the prompt-level test standing. That
   branch is reachable in production via `python main.py --sequential`. Do not "simplify"
   by appending to `state.candidates` inside either loop.

3. **Behaviour is fixed by test, not by shape.** `[VERIFIED]`
   `tests/test_perspectives_reach_state.py` asserts *outcomes* — `state.candidates`
   populated, Phase 3 not skipping, failures landing in `state.errors` — never the
   `PhaseOutput` type. Option A passes it unchanged. That is the safety proof for this
   refactor; do not weaken those tests to accommodate it.

4. **Ruff ratchet is exact-equality.** `scripts/ruff_ratchet.py` scopes to
   `ruff check src/` and fails both above and below `--max`. Re-run after the deletion and
   update the constant in **both** `.github/workflows/test.yml` and `scripts/ci-local.sh`,
   following the comment convention already in those files.

5. **Do not rewrite dated reports.**
   `docs/reports/defect-hunt-2026-09-01/T5-orchestration.md` and
   `docs/architecture-audit-2026-09-09.md` are point-in-time records. They were accurate
   when written. Leave them; the ADR supersedes them.

---

## 4. Steps

### P-1 · Domain — delete the dead reducer

- Delete `PhaseOutput` entirely: `pipeline_state.py:196-238` (class, all 11 delta fields,
  `mutated_in_place`, `apply_to`).
- Remove any import that becomes unused as a result. `[HYPOTHESIS]` Likely none — the
  candidate/score types are `PipelineCore` fields too — but confirm with
  `ruff check src/reasoner/domain/pipeline_state.py`.

### P-2 · Application — replace the accumulator

In `run_perspectives_phase` (`perspective_phases.py`):

- Delete the local import at `:179` and the comment block at `:180-184`.
- Replace `:185` with two plain locals:

  ```python
  # Accumulate locally and write once after the loop. Phase-2 generators must
  # not see each other (CLAUDE.md §5; tests/test_mind_virus_resistance.py
  # ::TestPhaseTwoGeneratorsAreBlind), and the deferred write is the structural
  # half of that guarantee — especially on the sequential branch, which builds
  # each prompt after the previous candidate exists.
  new_candidates: list[SolutionCandidate] = []
  new_errors: list[str] = []
  ```

- Rewrite the ~14 `output.candidates.append(...)` / `output.errors.append(...)` sites to
  the new locals. Mechanical; no control-flow changes.
- Keep the single deferred drain at `:238-239`, retargeted to the new locals.
- Delete `return output` at `:240`. The function is already annotated `-> None`; this makes
  the signature honest.

### P-3 · ADR — record the update model

New file `docs/adr/006-mutable-pipeline-state.md`, following the house format of
`docs/adr/001-hexagonal-architecture.md` (`# ADR-NNN: Title`, **Status** · **Date**,
Context, Decision, Consequences).

It must state plainly:

- **Decision:** `PipelineState` is a mutable object threaded explicitly through every
  phase. The phase contract is `async def run_*_phase(state, services, ...) -> None`.
  Phases mutate `state` directly. There is no reducer and no delta type.
- **Why the alternative was rejected** — §2 Option B, including the timeout/partial-write
  behaviour change and the `core`-only coverage limit.
- **The constraint that survives the retirement:** parallel phases accumulate locally and
  write once after joining. Name Phase-2 blindness as the reason, and cite the test.
- **Consequences (negative, stated honestly):** the "functional core, imperative shell"
  target in score-9 item 4.3 is abandoned, not achieved. Concurrent-write safety now rests
  on the accumulate-then-write convention rather than on a type. That convention is
  enforced by review and by the fitness function in P-5, not by the compiler.

### P-4 · Disarm the trap — amend the sycophancy plan

This is the step that prevents recurrence, and it must not be skipped.

In `docs/plans/sycophancy-mitigation.md`:

- §2.2 (`:195-215`) — item 3 of the "registered in three places" list currently says to add
  `PhaseOutput.premises` and an `apply_to` branch. Replace with: register in `_CORE_FIELDS`
  and as a `PipelineField("core")` descriptor only. Two places, not three.
- §W2 (`:334`) — "**Pattern:** Value Object + defensive parser + `PhaseOutput` delta + new
  `PhaseStep`" → drop the delta; the pattern is Value Object + defensive parser + direct
  state write + new `PhaseStep`.
- §2c (`:400`) — "call `_parse_premises` and return `PhaseOutput(premises=...)`" → "call
  `_parse_premises` and write `state.core.premises.extend(...)` directly; the phase
  contract returns `None` and every executor discards returns (ADR-006)."

### P-5 · Fitness function — stop the next one · **DEFERRED, not done**

> **Status 2026-09-12: deliberately deferred.** P-1 through P-4 and P-6 are implemented and
> verified. This step is not. Two reasons, both stated so it cannot lapse quietly:
>
> - `vulture` is not installed and this checkout has no virtualenv — baselining it would
>   mean installing into the user's global interpreter for a gate that, per the pilot
>   requirement below, would not be enforced for a week regardless.
> - Shipping a ratchet whose baseline count was never actually produced would be a gate in
>   name only. The `[UNKNOWN]` below is genuinely unknown and has to be measured first.
>
> **Consequence, stated plainly:** nothing currently prevents the next zero-caller
> abstraction from being added. ADR-006 §Compliance records the same gap. This is the one
> item from this plan still outstanding.


Phase G's stated fitness function is a ratcheted dead-code gate. Scope it so it would have
caught **this** case, which a plain import-graph check would not: `apply_to` was reachable
by name from a test, so it looked alive.

- `[INFERENCE]` The minimum viable gate is a `vulture` pass over `src/` with a ratcheted
  whitelist, run against `src/` only and excluding `tests/` from the reachability roots —
  a symbol whose only caller is a test is dead for this purpose. `[VERIFIED]` `vulture` is
  **not** currently in `requirements-dev.txt` or `pyproject.toml`; adding it is part of
  this step.
- Adopt the same **exact-equality ratchet** semantics as `scripts/ruff_ratchet.py` so the
  count cannot silently drift upward, and site the constant in the same two files.
- `[UNKNOWN]` Whether `vulture`'s false-positive rate on this codebase (heavy use of
  descriptors, dynamic `PipelineField`, `getattr`-driven method state) is low enough to
  gate CI. Pilot it advisory-only for one week before making it blocking.

This step is separable. If it is deferred, say so explicitly in the commit rather than
letting it lapse silently.

### P-6 · Documentation — correct the six false claims

Per the table in §1.6. Each becomes a pointer to ADR-006:

1. `REASONER_COMPLETE_SYSTEM_DOCUMENTATION.md:1402` — replace the false "Rule" with the
   real one: state is mutated in place; parallel phases accumulate locally and write once.
2. `REASONER_COMPLETE_SYSTEM_DOCUMENTATION.md:39` and the `class PhaseOutput` listing at
   `:1090` — remove.
3. `remediation-status-report.md:109-112,234,265` — mark C1 **closed by retirement**, not
   "40% partial". A closed-as-rejected item is a finished item.
4. `remediation-plan-v2-9.5.md:91-119,295,357` — mark item 1.4 **superseded by
   ADR-006**. Its concurrency concern is real and is now addressed by the
   accumulate-then-write convention, not by a delta type; say that rather than deleting the
   item.
5. `ARCHITECTURE_REMEDIATION_PLAN.md:119` — annotate as historical; the discipline was
   attempted and retired.
6. `.claude/skills/map-domain/SKILL.md:17` — drop `PhaseOutput` from the sub-container
   list. **Do not run `check_skill_maps.py --update`.** `[VERIFIED 2026-09-12]` 8 maps are
   already out of date from unrelated `ui-next/` drift; re-baselining would sweep all of it
   into this commit. The baseline tracks files added and removed, and this change removes a
   class, not a file — so it does not make any map stale. The pre-existing drift is
   separate work.
7. `docs/plans/architecture-score-9-remediation-plan.md:191` — mark item 4.3 **resolved**,
   pointing at ADR-006.
8. `tests/test_perspectives_reach_state.py:1-19` — the module docstring is the best
   description of this defect class in the repo; keep it, and update the mechanism
   sentences. Note: its cited line numbers (`pipeline.py:241`, `runner.py:94`,
   `services.py:60`) have **all drifted** and are now `:301`, `:168`, `:99`.
9. `docs/plans/CONTEXT.md` — add an entry for this plan file, per directory convention.

---

## 5. Verification

Run via **PowerShell**. The rtk Bash wrapper misreports pytest results.

```powershell
python -m pytest tests/test_perspectives_reach_state.py tests/test_mind_virus_resistance.py tests/test_pipeline_flow.py tests/test_flows_one_loop.py -q
python -m pytest tests/architecture/ -q
python -m pytest tests/ -q -m "not slow and not integration" -n auto --dist loadscope
python scripts/ruff_ratchet.py --max <current>
```

Acceptance:

- `tests/test_perspectives_reach_state.py` — **3 passed, unmodified**. This is the
  load-bearing check: it proves the behaviour survived the abstraction.
- `TestPhaseTwoGeneratorsAreBlind` — 2 passed.
- Fast lane shows **no new failures** against the `studio-adopt` baseline. `[VERIFIED]`
  that baseline currently carries **14 pre-existing failures** (synthesis /
  multi-perspective / e2e clusters), reproduced on a pristine worktree at `0235e4d`.
  Compare test IDs, not counts.
- `grep -rn "PhaseOutput" src/` returns nothing; in `tests/` only the historical docstring
  in `test_perspectives_reach_state.py` remains.
- Ruff ratchet passes at the new exact count, updated in both files.

---

## 6. Scope boundaries

**In scope:** the `PhaseOutput` class, its one construction site, the ADR, the six
documentation corrections, the sycophancy-plan amendment.

**Out of scope, deliberately:**

- Converting any other phase to any other contract.
- The `state._current_phase_key` ambient-coupling finding (score-9 item H-2) — adjacent,
  separately tracked.
- The concurrency-ceiling findings in `docs/architecture-audit-2026-09-09.md:335-345`.
- Option B in any form.

**`[HYPOTHESIS]` Residual risk.** Retiring the type removes the last *typed* statement of
intent about how parallel phases write state, leaving a convention in a comment and an ADR.
P-5 exists because of this. If P-5 is dropped, the honest description of the outcome is
"we deleted a dead abstraction and wrote down what we actually do" — which is still an
improvement on a half-built one, but is not a safety mechanism. Do not describe it as one.
