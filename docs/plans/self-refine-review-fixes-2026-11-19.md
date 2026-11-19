# Self-Refine review fixes — plan

Date: 2026-11-19. Branch: `feat/self-refine-method` (PR #248). Source: `/code-review` (high) of the PR diff, 8 findings, all in `src/reasoner/application/flows/self_refine.py`.

## Ground truth (checked before planning)

- `WorkflowServices.call_llm` is typed `-> tuple[str, dict]` and never returns `None`. Provider failures **raise**. The `if result is None: raise RuntimeError(...)` in `_call` (line 125) is dead code; the real failure in finding 1 is an exception escaping `_call`, not a `None`.
- `FlowRunner.run_phase` (`flows/runner.py:168-280`): on a quality-gate retry it calls `quality.criteria.reset_phase_state(name, state)`, which looks the phase up in the `_RESET` table. `"Self-Refine Loop"` has no entry, which is why the flow clears its own state with `sr.clear()`. On an exception retry nothing is reset. A `TimeoutError` on a `critical=True` phase ends the run.
- There is no phase-skip resume in the runner: `--resume` re-enters phases from the top, so a phase that starts by clearing its state throws resumed work away.
- `is_run_fatal(exc)` (`core/exceptions.py:322`) marks errors that must end the run (empty credits, rejected key). `core/degrade.degraded()` is the house way to record a degradation.
- `IterativeCritiqueFlow` (the closest sibling) runs its loop phase with `critical=False` and has the same average-pace time-budget check (`iterative_critique.py:59-73`).
- `best_answer` / `best_score` / `best_round` are read only by `flows/self_refine.py`, `phases/self_refine.py` (`synthesis_prompt`, line 108) and `tests/test_self_refine.py`. No serializer or UI reads them.

## Architecture constraints

- `application/flows/` stays free of `infrastructure/` imports (import-linter contract 2). All new imports come from `core/` or `quality/`.
- Pure decision logic stays as module-level pure functions (`parse_score`, `effective_score`, `stop_reason`, `best_round`) so it stays unit-testable without an LLM. The flow class keeps only orchestration and I/O.
- Method state stays in `MethodState.data["self_refine"]`, read with `.get()`.
- Reset-on-retry belongs in the `_RESET` table in `quality/criteria.py`, the existing registry for exactly this, not inside the flow.
- Ratchets must not rise: ruff 2053, bandit 90, silent-failure 91, import-linter contract 2 at 50 exceptions.

## Fix order

The findings interact. Fixes 1, 5 and 8 together define how the loop survives failure, so they land first and in one commit. The rest are independent.

### Commit 1 — the loop never loses finished rounds (findings 1, 5, 8)

**F1. A failed LLM call mid-loop discards finished rounds** (line 126).
Root cause: any exception in round ≥2 escapes `_run_loop`, and the phase is `critical=True`, so the run dies with a usable answer in state.

- `_call`: delete the dead `None` check.
- `_run_loop`: wrap each round's `_draft` + `_evaluate` in one `try/except Exception as exc`.
  - Re-raise if `is_run_fatal(exc)`. Credits and auth failures must still stop the run.
  - Re-raise if no round has finished yet. Round 1 has nothing to fall back to, which keeps today's `PhaseError` behaviour.
  - Otherwise record through `degraded("self_refine.round", None, exc=exc, state=state, detail=f"round {n}")`, set `reason = "llm_error"`, and break. Stop, don't retry: the provider just failed, and the next round would most likely fail the same way.
- Add `"llm_error"` to the stop reasons documented in the module docstring.
- Narrow except: only around the two LLM calls, not around the bookkeeping. Note the expected silent-failure-ratchet effect; the `degraded()` call keeps it a reported degradation, not a silent one.

**F8. The time-budget check can overshoot the phase timeout** (line 182).
Root cause: the next round is estimated at the *average* pace, and one slow round is enough to hit `asyncio.wait_for`.

- Add a pure helper `next_round_fits(durations: list[float], elapsed: float, budget: float) -> bool` that estimates the next round as `max(durations)`, not the mean. Store each round's duration in its round dict (`"seconds"`), so the helper stays pure and the data shows up in state.
- `IterativeCritiqueFlow` has the identical average-pace check. Put the helper in `application/flows/base.py`, next to `WorkflowStrategy`, and point both flows at it. One rule, one place. If that widens the PR too far, keep it in `self_refine.py` and file the iterative-critique switch as a follow-up; decide at implementation time by diff size.
- Defence in depth for the case the estimate still misses: write the `best_*` results after **every** round (see F6), and change the loop phase to `critical=False`, as `IterativeCritiqueFlow` does. A timeout then keeps the rounds already in state and synthesis still runs. Synthesis gets a guard: no rounds means `PhaseError("Self-refine produced no rounds")`, so a run with nothing to synthesise still fails loudly.

**F5. `sr.clear()` wipes state on resume and retry** (line 168).
Root cause: the flow does the runner's job. Reset-on-retry is the job of `reset_phase_state`.

- Add `"Self-Refine Loop": lambda s: s.self_refine_state.clear()` to `_RESET` in `quality/criteria.py`. Quality-gate retries keep starting clean, now through the shared mechanism.
- `_run_loop`: drop `sr.clear()`. Initialise missing keys with `sr.setdefault(...)` and continue from `sr.get("rounds", [])`. A resumed state, or an exception retry after F1, continues from its last finished round instead of paying for every round again. Round numbering continues from `len(rounds) + 1`.
- If the stored `stop_reason` is already terminal (`target_reached`, `max_rounds_reached`, and so on), return immediately: the loop finished, so resume should not run more rounds.

### Commit 2 — the revision input is honest (findings 2, 3)

**F3. Each revision builds on the last round, not the best** (line 188).
Fix: `prev = best_round(rounds)` instead of `rounds[-1]`. This is one call to the existing pure helper. `best_round` already prefers real rounds over degraded ones, which also covers most of F2. `stop_reason`'s `no_improvement` check still reads the raw score sequence, so a revision that scores below the best still counts toward the plateau.

**F2. After a degraded round the model is told it scored 0/10** (line 144).
Root cause: the round dict stores `score: 0.0` for "unknown", and `revision_prompt` prints it.

- In the round dict, store `"score": None` for a degraded round, not `0.0`. `None` is what the module already means by "unusable" (`parse_score`'s docstring says an unreadable score must not look like a very bad one). `stop_reason` and `best_round` already filter on `degraded` before reading `score`, so they need no change. Check `tests/test_self_refine.py` for fixtures that rely on `0.0`.
- `phases/self_refine.revision_prompt`: change `score: float` to `score: float | None`. When the score is `None`, print "YOUR PREVIOUS ANSWER (self-score unavailable)" instead of a number. Prompt text stays in `phases/`, so the change keeps the module boundary.
- After F3, `prev` is only a degraded round when **every** round so far is degraded. That is the one case the placeholder flaw is still for.

### Commit 3 — parsing and cleanup (findings 4, 6, 7)

**F4. 10.5 parses as 1.05** (line 67).
Fix: treat a value as a percentage only when it is clearly on a 0–100 scale. The rule becomes `if 10 < score <= 100 and score >= 20`: anything up to 20 is an overshoot and caps at 10, anything from 20 to 100 is read as a percentage. Cleaner alternative: honour an explicit `%` in string input (`"85%"`) and otherwise cap numbers above 10 at 10. Pick the second if no recorded model output uses bare 11–100 numbers. Add parametrised cases for 10.5, 15, 85, `"85%"` and `"9/10"`.

**F6. The best round is computed twice** (line 238).
Fix: one source. Persist only `sr["best_round"]` (the round number), written after every round per F8. Synthesis and `synthesis_prompt` look the round up by number. `best_score` and `best_answer` stop being separate keys. `synthesis_prompt(state, sr, best)` takes the round dict and reads `best["answer"]` and `best["score"]`, so drop its separate `best_answer` parameter. Update the tests that assert on `best_answer` / `best_score`.

**F7. `score != score`** (line 65).
Fix: `math.isnan(score)`.

## Tests (`tests/test_self_refine.py`, using the existing fake-clock + fake-services pattern)

1. Round 3 `call_llm` raises a provider error → the loop stops with `llm_error`, keeps rounds 1–2, `best_round` is 2, synthesis runs.
2. Round 2 raises a run-fatal error → it propagates.
3. Round 1 raises → `PhaseError` / propagates (unchanged).
4. Scores 8.5 then 7.0 → round 3's `revision_prompt` receives the 8.5 answer and its flaws.
5. A degraded round 2 after a real round 1 → round 3 revises round 1. With every round degraded, the prompt says "self-score unavailable" and contains no "0/10".
6. `parse_score`: 10.5 → 10, 85 → 8.5 (or per the chosen rule), NaN → None.
7. Resume: state with 2 finished rounds and no stop reason → the loop starts at round 3. A state with `stop_reason="target_reached"` → no LLM calls.
8. Quality retry: `reset_phase_state("Self-Refine Loop", state)` empties `self_refine_state`.
9. Budget: durations `[30, 150]` at elapsed 180 and budget 216 → the next round does not fit (the max estimate), where the mean (90) would have allowed it.
10. Timeout safety: `best_round` is set after round 1, before round 2 starts.

## Verification

```
python -m pytest tests/test_self_refine.py tests/test_arch_uncertainty_mixin_migration.py tests/test_hypergate.py -q
python -m pytest tests/ -q -m "not slow and not integration" -n auto --dist loadscope
lint-imports
ruff check src/reasoner/application/flows/self_refine.py src/reasoner/phases/self_refine.py src/reasoner/quality/criteria.py
```

Plus the ratchet scripts (ruff, bandit, silent-failure) at or below their current counts.

After the commits land, re-call `ReportFindings` with each of the 8 findings marked `fixed` (or `skipped`, with the reason). Push to PR #248; Auto-fix watches CI.

## Out of scope

- A live-model run to measure cost and how often the loop reaches 9/10. It is still unmeasured, and these fixes don't change that.
- Moving `IterativeCritiqueFlow` to the shared budget helper, if F8 keeps the helper local.
