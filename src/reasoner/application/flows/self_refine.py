"""Self-Refine -- draft, self-score, revise, until the model scores its answer 9/10.

One model (routing role ``expert_1``) drafts an answer, evaluates it with a
0-10 score and a flaw list, and revises against its own flaws until the score
reaches ``SR_TARGET_SCORE``. The loop is bounded: a round limit, a plateau
check, the phase time budget, and a run of unusable self-evaluations.

The score is self-reported. Two guards keep it from being a rubber stamp: the
evaluator lists flaws before it scores, and ``effective_score`` caps a score at
just under the target if a HIGH or MED flaw sits next to it. Synthesis is told
the score is the model's own claim, and the final answer says so in
``open_questions``.

Stop reasons: ``target_reached``, ``evaluator_unavailable``,
``max_rounds_reached``, ``no_improvement``, ``time_budget`` and ``llm_error``
(a provider call failed after at least one round had finished).

Finished rounds are never thrown away. Each one is appended to state as soon as
it completes, the loop phase is non-critical, and synthesis works from the best
round in state, so a provider failure or a phase timeout mid-loop still yields
the best answer reached. The loop also continues from rounds already in state
(``--resume``); a quality-gate retry starts clean through
``quality.criteria.reset_phase_state``.

State lives in ``state.self_refine_state`` (``MethodState.data["self_refine"]``).
"""

from __future__ import annotations

import math
import time
from typing import Any

import reasoner.phases.self_refine as sr_phases
from reasoner.application.flows.base import PhaseStep, WorkflowServices, WorkflowStrategy
from reasoner.application.flows.synthesis_phase import finalize_solution
from reasoner.application.services.serializers import _ser_5, _ser_synthesis
from reasoner.core.constants_limits import (
    SR_MAX_CONSECUTIVE_DEGRADED,
    SR_MAX_ROUNDS,
    SR_TARGET_SCORE,
    SR_TIME_BUDGET_FRACTION,
    get_phase_timeout,
    get_token_budget,
)
from reasoner.core.degrade import degraded
from reasoner.core.exceptions import PhaseError, is_run_fatal
from reasoner.domain.pipeline_state import PipelineState
from reasoner.parsing import extract_json

# Module-level so tests can drive a fake clock.
_clock = time.monotonic

_LOOP_PHASE = "Self-Refine Loop"
_ROLE = "expert_1"  # drafts, scores and revises: the method is one model judging itself
_SERIOUS = {"HIGH", "MED", "MEDIUM"}
_PLACEHOLDER_FLAW = {
    "flaw": "Self-evaluation was unavailable; re-check the answer for errors and gaps",
    "severity": "MED",
}


def parse_score(value: Any) -> float | None:
    """A 0-10 score from whatever shape the model returned, or None if unusable.

    Accepts numbers and strings like "9", "9/10" or "85%". A bare number from
    20 to 100 is read as a percentage; one just over 10 (10.5, 15) is an
    overshoot and caps at 10 -- reading 10.5 as 1.05 would call a near-perfect
    answer terrible. Anything else (a dict, a word, a negative) is None, not 0:
    an unreadable score must not look like a very bad one.
    """
    if isinstance(value, bool):
        return None
    percent = False
    if isinstance(value, str):
        value = value.split("/")[0].strip()
        percent = value.endswith("%")
        value = value.rstrip("%").strip()
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(score) or score < 0:
        return None
    if percent or 20 <= score <= 100:
        score /= 10
    return min(score, 10.0)


def effective_score(raw: float, flaws: list[dict], target: float = SR_TARGET_SCORE) -> float:
    """Cap a score at just under the target when its own flaw list contradicts it."""
    serious = any(str(f.get("severity", "")).strip().upper() in _SERIOUS for f in flaws)
    return min(raw, target - 0.1) if serious and raw >= target else raw


def stop_reason(rounds: list[dict], *, target: float = SR_TARGET_SCORE,
                max_rounds: int = SR_MAX_ROUNDS) -> str:
    """Why the loop ends after these rounds, or "" to run another. Pure."""
    if not rounds:
        return ""
    last = rounds[-1]
    if not last["degraded"] and last["score"] >= target:
        return "target_reached"
    trailing = 0
    for r in reversed(rounds):
        if not r["degraded"]:
            break
        trailing += 1
    if trailing >= SR_MAX_CONSECUTIVE_DEGRADED:
        return "evaluator_unavailable"
    if len(rounds) >= max_rounds:
        return "max_rounds_reached"
    real = [r["score"] for r in rounds if not r["degraded"]]
    if len(real) >= 3 and max(real[-2:]) <= real[-3]:
        return "no_improvement"
    return ""


def best_round(rounds: list[dict]) -> dict | None:
    """Highest-scoring real round (latest on a tie); the last round if none is real."""
    real = [r for r in rounds if not r["degraded"]]
    if real:
        return max(real, key=lambda r: (r["score"], r["round"]))
    return rounds[-1] if rounds else None


def next_round_fits(durations: list[float], elapsed: float, budget: float) -> bool:
    """Whether one more round, as slow as the slowest so far, fits the budget. Pure.

    The slowest round, not the average: one slow round is enough for the phase
    timeout to cancel the phase.
    """
    return not durations or elapsed + max(durations) <= budget


class SelfRefineFlow(WorkflowStrategy):
    """Self-score loop: one model drafts, scores itself and revises until 9/10."""

    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        # The loop is non-critical so a timeout or provider failure keeps the
        # rounds already in state; synthesis is critical and fails the run
        # when there is no round at all to synthesise.
        return [
            PhaseStep(3, _LOOP_PHASE, self._run_loop, _ser_5),
            PhaseStep(4, "Synthesis", self._run_synthesis, _ser_synthesis, critical=True),
        ]

    async def _call(self, services: WorkflowServices, state: PipelineState, system: str,
                    user: str, budget_key: str) -> tuple[dict | None, str]:
        """One JSON call to the self-refine model. (None, model) when unparseable."""
        raw, meta = await services.call_llm(
            role=_ROLE, system_prompt=system, user_prompt=user, state=state,
            max_tokens=get_token_budget(budget_key),
        )
        model = (meta or {}).get("model", "")
        try:
            data = extract_json(raw)
        except Exception as exc:  # noqa: BLE001 - a malformed reply is a degraded round
            services.log("SR_ERROR", f"JSON parse failed: {exc}", state)
            return None, model
        return (data if isinstance(data, dict) else None), model

    async def _draft(self, services: WorkflowServices, state: PipelineState,
                     previous: dict | None) -> tuple[str, str]:
        """The draft (round 1) or the revision of *previous*. "" when unusable."""
        if previous is None:
            system, user = sr_phases.GENERATOR_SYSTEM, sr_phases.generator_prompt(state)
        else:
            system = sr_phases.REVISION_SYSTEM
            user = sr_phases.revision_prompt(
                state, previous["answer"], previous["flaws"], previous["score"]
            )
        data, model = await self._call(services, state, system, user, "self_refine_generate")
        answer = (data or {}).get("revised_answer") or (data or {}).get("answer") or ""
        return (answer if isinstance(answer, str) and answer.strip() else ""), model

    async def _evaluate(
        self, services: WorkflowServices, state: PipelineState, answer: str, round_num: int,
    ) -> tuple[float | None, list[dict], float | None]:
        """(effective score, flaws, raw score). Score is None when unusable."""
        data, _ = await self._call(
            services, state, sr_phases.EVALUATOR_SYSTEM,
            sr_phases.evaluator_prompt(state, answer, round_num, SR_TARGET_SCORE),
            "self_refine_evaluate",
        )
        raw = parse_score((data or {}).get("score"))
        if raw is None:
            return None, [], None
        flaws_in = (data or {}).get("flaws")
        flaws = [f for f in flaws_in if isinstance(f, dict)] if isinstance(flaws_in, list) else []
        return effective_score(raw, flaws), flaws, raw

    async def _run_round(self, services: WorkflowServices, state: PipelineState,
                         prev: dict | None, n: int) -> dict:
        """Draft (or revise *prev*) and self-evaluate: one round's record."""
        answer, model = await self._draft(services, state, prev)
        if not answer:
            if prev is None:
                raise PhaseError("Self-refine produced no first draft",
                                 phase=3, phase_name=_LOOP_PHASE)
            answer = prev["answer"]  # keep what we have; the round counts as degraded
            score, flaws, raw = None, [], None
        else:
            score, flaws, raw = await self._evaluate(services, state, answer, n)
        is_degraded = score is None
        if is_degraded:
            flaws = (prev["flaws"] if prev else []) or [_PLACEHOLDER_FLAW]
        return {
            # A degraded round has no score, not a score of 0: "unknown" must
            # never reach the model, or the trail, as "very bad".
            "round": n, "answer": answer, "model": model, "flaws": flaws,
            "score": score, "raw_score": raw,
            "capped": raw is not None and score is not None and score < raw,
            "degraded": is_degraded,
        }

    async def _run_loop(self, state: PipelineState, services: WorkflowServices) -> None:
        sr = state.self_refine_state
        sr.setdefault("target", SR_TARGET_SCORE)
        rounds: list[dict] = sr.setdefault("rounds", [])

        # Continues from rounds already in state (a resumed run). The phase
        # timeout cancels the phase, so each round is appended the moment it
        # finishes, and the loop stops before a round that would not fit.
        started = _clock()
        budget = get_phase_timeout(_LOOP_PHASE) * SR_TIME_BUDGET_FRACTION
        reason = stop_reason(rounds)
        while not reason:
            n = len(rounds) + 1
            durations = [r["seconds"] for r in rounds if "seconds" in r]
            if not next_round_fits(durations, _clock() - started, budget):
                reason = "time_budget"
                services.log("SR", f"Stopped after round {len(rounds)}: the next round "
                                   f"would not fit the phase limit", state)
                break
            services.log("SR", f"--- Round {n}/{SR_MAX_ROUNDS} ---", state)
            # Revise the best answer so far, not the latest: a round that
            # regressed must not become the base of the next one.
            prev = best_round(rounds)
            round_start = _clock()
            try:
                record = await self._run_round(services, state, prev, n)
            except Exception as exc:
                # Round 1 has nothing to fall back to, and a run-fatal error
                # (credits, auth) fails every later call too: both propagate.
                if prev is None or is_run_fatal(exc):
                    raise
                reason = degraded("self_refine.round", "llm_error", exc=exc, state=state,
                                  detail=f"stopped at round {n}, keeping {len(rounds)} rounds")
                break
            record["seconds"] = _clock() - round_start
            rounds.append(record)
            shown = "unavailable" if record["degraded"] else f"{record['score']:g}"
            services.log("SR", f"Round {n}: self-score {shown}", state)
            reason = stop_reason(rounds)

        sr["stop_reason"] = reason
        sr["target_reached"] = reason == "target_reached"

    async def _run_synthesis(self, state: PipelineState, services: WorkflowServices) -> None:
        sr = state.self_refine_state
        # Derived from the rounds, the one source: it holds even when the loop
        # phase timed out before recording a stop reason.
        best = best_round(sr.get("rounds", []))
        if best is None:
            raise PhaseError("Self-refine produced no rounds to synthesise",
                             phase=4, phase_name="Synthesis")
        services.log("SR", "Synthesizing the refined answer", state)
        raw, _ = await services.call_llm(
            role="synthesis",
            system_prompt=sr_phases.SYNTHESIS_SYSTEM,
            user_prompt=sr_phases.synthesis_prompt(state, sr, best),
            state=state,
        )
        solution = finalize_solution(raw, state, services)

        extra = ["The quality score is the model's own assessment of its answer, "
                 "not independent verification."]
        if not sr.get("target_reached"):
            extra.append(f"The model did not reach {SR_TARGET_SCORE:g}/10 "
                         f"({sr.get('stop_reason') or 'loop interrupted'}); "
                         f"the answer is unsettled.")
            extra += [f"Unresolved self-identified flaw: {f.get('flaw')}"
                      for f in best["flaws"] if f.get("flaw")]
        known = {q.strip().lower() for q in solution.open_questions}
        solution.open_questions += [q for q in extra if q.strip().lower() not in known]
        state.final_solution = solution
