"""Self-Refine: one model drafts, scores its own answer, revises until it scores 9/10."""

from __future__ import annotations

import json

import pytest

import reasoner.application.flows.self_refine as sr_flow
from reasoner.application.flows.factory import WorkflowFactory
from reasoner.application.flows.self_refine import (
    SelfRefineFlow,
    best_round,
    effective_score,
    next_round_fits,
    parse_score,
    stop_reason,
)
from reasoner.core.exceptions import AuthenticationError, PhaseError, ProviderError
from reasoner.domain.pipeline_state import PipelineState
from reasoner.hypergate.hyperagent import named_method
from reasoner.infrastructure.llm.registry import _vendor_of
from reasoner.presets import PRESETS, get_method_from_preset
from reasoner.quality.criteria import reset_phase_state


def _rnd(n: int, score: float, degraded: bool = False) -> dict:
    return {"round": n, "answer": f"a{n}", "flaws": [], "score": score, "degraded": degraded}


class _Scripted:
    """Answers draft/revise and evaluate calls in order; records the roles used."""

    def __init__(self, scores, severity="LOW", clock=None, step=0.0):
        self.scores = list(scores)
        self.severity = severity
        self.roles: list[str] = []
        self.drafts = 0
        self.prompts: list[str] = []  # draft/revise user prompts, in order
        self._clock, self._step = clock, step

    def log(self, *a, **k):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        self.roles.append(role)
        if self._clock:
            self._clock.now += self._step
        if "evaluator" in system_prompt:
            score = self.scores.pop(0)
            if score is None:
                return "not json at all", {"model": "m"}
            flaws = [{"flaw": f"flaw-{len(self.roles)}", "severity": self.severity}]
            return json.dumps({"flaws": flaws, "score": score}), {"model": "m"}
        self.prompts.append(user_prompt)
        self.drafts += 1
        key = "answer" if self.drafts == 1 else "revised_answer"
        return json.dumps({key: f"answer-{self.drafts}"}), {"model": "m"}


class _Clock:
    now = 1000.0

    def __call__(self):
        return self.now


@pytest.mark.parametrize(("raw", "expected"), [
    (9, 9.0), ("9/10", 9.0), ("8.5", 8.5), (95, 9.5), (10, 10.0),
    # just over 10 is an overshoot, not a percentage; 20-100 or an explicit % is
    (10.5, 10.0), (12, 10.0), (15, 10.0), (20, 2.0), (85, 8.5), ("85%", 8.5), ("8.5 %", 0.85),
    (-1, None), ("great", None), ({"a": 1}, None), (None, None), (True, None),
    (float("nan"), None),
])
def test_parse_score(raw, expected):
    assert parse_score(raw) == expected


def test_serious_flaw_caps_a_score_at_the_target():
    assert effective_score(9.5, [{"severity": "HIGH"}]) == pytest.approx(8.9)
    assert effective_score(9.5, [{"severity": "med"}]) == pytest.approx(8.9)
    assert effective_score(9.5, [{"severity": "LOW"}]) == 9.5
    assert effective_score(9.5, []) == 9.5
    assert effective_score(7.0, [{"severity": "HIGH"}]) == 7.0


def test_stop_reason():
    assert stop_reason([]) == ""
    assert stop_reason([_rnd(1, 6), _rnd(2, 9.0)]) == "target_reached"
    assert stop_reason([_rnd(1, 6), _rnd(2, 8.9)]) == ""
    assert stop_reason([_rnd(1, 6), _rnd(2, 0, True), _rnd(3, 0, True)]) == "evaluator_unavailable"
    assert stop_reason([_rnd(i, 5 + i * 0.1) for i in range(1, 6)]) == "max_rounds_reached"
    # a degraded round never counts as the target, whatever its placeholder score
    assert stop_reason([_rnd(1, 10, True)]) == ""
    assert stop_reason([_rnd(1, 6), _rnd(2, 7), _rnd(3, 7), _rnd(4, 6.5)]) == "no_improvement"


def test_best_round_prefers_real_rounds():
    rounds = [_rnd(1, 7), _rnd(2, 8), _rnd(3, 0, True)]
    assert best_round(rounds)["round"] == 2
    assert best_round([_rnd(1, 0, True)])["round"] == 1
    assert best_round([]) is None


@pytest.mark.asyncio
async def test_loop_runs_until_the_score_reaches_nine():
    services = _Scripted([6, 8, 9.2])
    state = PipelineState(problem="p")

    await SelfRefineFlow()._run_loop(state, services)

    sr = state.self_refine_state
    assert [r["score"] for r in sr["rounds"]] == [6, 8, 9.2]
    assert sr["target_reached"] is True and sr["stop_reason"] == "target_reached"
    assert best_round(sr["rounds"])["answer"] == "answer-3"
    # one model throughout: every loop call runs under the same routing role
    assert set(services.roles) == {"expert_1"}


@pytest.mark.asyncio
async def test_a_high_score_beside_a_serious_flaw_does_not_stop_the_loop():
    services = _Scripted([9.5, 9.5, 9.5, 9.5, 9.5], severity="HIGH")
    state = PipelineState(problem="p")

    await SelfRefineFlow()._run_loop(state, services)

    sr = state.self_refine_state
    assert sr["target_reached"] is False
    assert sr["rounds"][0]["capped"] is True and sr["rounds"][0]["raw_score"] == 9.5
    assert len(sr["rounds"]) > 1  # never accepted on the first capped round


@pytest.mark.asyncio
async def test_unreachable_target_stops_at_the_round_limit_with_the_best_answer():
    services = _Scripted([5, 6, 7, 7.5, 8])
    state = PipelineState(problem="p")

    await SelfRefineFlow()._run_loop(state, services)

    sr = state.self_refine_state
    assert sr["stop_reason"] == "max_rounds_reached" and sr["target_reached"] is False
    best = best_round(sr["rounds"])
    assert best["round"] == 5 and best["score"] == 8


@pytest.mark.asyncio
async def test_unusable_evaluations_end_the_loop_without_claiming_success():
    services = _Scripted([None, None])
    state = PipelineState(problem="p")

    await SelfRefineFlow()._run_loop(state, services)

    sr = state.self_refine_state
    assert sr["stop_reason"] == "evaluator_unavailable" and sr["target_reached"] is False
    best = best_round(sr["rounds"])
    assert best["degraded"] and best["score"] is None and best["answer"]


@pytest.mark.asyncio
async def test_no_first_draft_fails_the_phase():
    class _Bad(_Scripted):
        async def call_llm(self, *a, **k):
            return "nope", {}

    with pytest.raises(PhaseError):
        await SelfRefineFlow()._run_loop(PipelineState(problem="p"), _Bad([]))


@pytest.mark.asyncio
async def test_slow_rounds_stop_inside_the_time_budget(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(sr_flow, "_clock", clock)
    services = _Scripted([5, 6, 7, 8], clock=clock, step=60.0)  # 120s a round, 240s phase
    state = PipelineState(problem="p")

    await SelfRefineFlow()._run_loop(state, services)

    sr = state.self_refine_state
    assert sr["stop_reason"] == "time_budget"
    assert len(sr["rounds"]) == 1


def test_method_is_registered_end_to_end():
    assert isinstance(WorkflowFactory().get_strategy("self-refine"), SelfRefineFlow)
    assert get_method_from_preset("self-refine-budget") == "self_refine"
    assert get_method_from_preset("self-refine-western-premium") == "self_refine"
    assert named_method("use the self-refine method on this") == "self_refine"
    steps = SelfRefineFlow().get_phases(PipelineState())
    assert [s.name for s in steps] == ["Self-Refine Loop", "Synthesis"]
    # loop non-critical keeps finished rounds on failure; synthesis fails the run
    assert steps[0].critical is False and steps[1].critical is True


class _FailsOnCall(_Scripted):
    """_Scripted that raises *exc* on the given 1-based call."""

    def __init__(self, scores, fail_on, exc):
        super().__init__(scores)
        self.calls, self.fail_on, self.exc = 0, fail_on, exc

    async def call_llm(self, *a, **k):
        self.calls += 1
        if self.calls == self.fail_on:
            raise self.exc
        return await super().call_llm(*a, **k)


@pytest.mark.asyncio
async def test_a_provider_failure_mid_loop_keeps_the_finished_rounds():
    # calls: draft1 eval1 draft2 eval2 draft3 <- fails
    services = _FailsOnCall([6, 8, 9], fail_on=5, exc=ProviderError("upstream 503"))
    state = PipelineState(problem="p")

    await SelfRefineFlow()._run_loop(state, services)

    sr = state.self_refine_state
    assert sr["stop_reason"] == "llm_error" and sr["target_reached"] is False
    assert [r["round"] for r in sr["rounds"]] == [1, 2]
    assert best_round(sr["rounds"])["answer"] == "answer-2"
    assert any("self_refine.round" in str(d) for d in state.degradations)


@pytest.mark.asyncio
async def test_a_run_fatal_error_mid_loop_still_ends_the_run():
    services = _FailsOnCall([6, 8], fail_on=3, exc=AuthenticationError("bad key"))
    with pytest.raises(AuthenticationError):
        await SelfRefineFlow()._run_loop(PipelineState(problem="p"), services)


@pytest.mark.asyncio
async def test_a_failure_in_round_one_propagates():
    services = _FailsOnCall([], fail_on=1, exc=ProviderError("down"))
    with pytest.raises(ProviderError):
        await SelfRefineFlow()._run_loop(PipelineState(problem="p"), services)


@pytest.mark.asyncio
async def test_revision_builds_on_the_best_round_not_the_last():
    services = _Scripted([8.5, 7.0, 9.0])
    await SelfRefineFlow()._run_loop(PipelineState(problem="p"), services)

    # round 3 revises round 1's answer (8.5), not round 2's regression (7.0)
    assert "answer-1" in services.prompts[2] and "8.5/10" in services.prompts[2]


@pytest.mark.asyncio
async def test_an_unusable_evaluation_is_never_shown_to_the_model_as_zero():
    services = _Scripted([None, 9.0])
    state = PipelineState(problem="p")
    await SelfRefineFlow()._run_loop(state, services)

    assert state.self_refine_state["rounds"][0]["score"] is None
    assert "self-score unavailable" in services.prompts[1]
    assert "0/10" not in services.prompts[1]


@pytest.mark.asyncio
async def test_resume_continues_from_rounds_in_state():
    state = PipelineState(problem="p")
    state.self_refine_state["rounds"] = [
        {**_rnd(1, 6), "answer": "answer-1"}, {**_rnd(2, 7), "answer": "answer-2"},
    ]
    services = _Scripted([9.0])

    await SelfRefineFlow()._run_loop(state, services)

    sr = state.self_refine_state
    assert [r["round"] for r in sr["rounds"]] == [1, 2, 3]
    assert sr["stop_reason"] == "target_reached" and services.drafts == 1


@pytest.mark.asyncio
async def test_resume_of_a_finished_loop_makes_no_calls():
    state = PipelineState(problem="p")
    state.self_refine_state["rounds"] = [_rnd(1, 9.5)]
    services = _Scripted([])

    await SelfRefineFlow()._run_loop(state, services)

    assert services.roles == []
    assert state.self_refine_state["stop_reason"] == "target_reached"


def test_a_quality_retry_starts_the_loop_clean():
    state = PipelineState(problem="p")
    state.self_refine_state["rounds"] = [_rnd(1, 6)]
    reset_phase_state("Self-Refine Loop", state)
    assert state.self_refine_state == {}


def test_next_round_is_budgeted_at_the_slowest_round():
    assert next_round_fits([], 0.0, 10.0)
    # the mean (90s) would fit, 70 + 90 <= 216; the slowest (150s) does not
    assert not next_round_fits([30.0, 150.0], 70.0, 216.0)
    assert next_round_fits([30.0, 50.0], 70.0, 216.0)


class _FallsBack(_Scripted):
    """_Scripted whose router answers from model "fb" from the given 1-based call on."""

    def __init__(self, scores, from_call):
        super().__init__(scores)
        self.calls, self.from_call = 0, from_call

    async def call_llm(self, *a, **k):
        self.calls += 1
        text, _ = await super().call_llm(*a, **k)
        return text, {"model": "fb" if self.calls >= self.from_call else "m"}


@pytest.mark.asyncio
async def test_a_fallback_after_round_one_ends_the_loop_without_mixing_scores():
    # calls: draft1 eval1 draft2 eval2 draft3(fb) eval3(fb)
    services = _FallsBack([6, 7, 9.5], from_call=5)
    state = PipelineState(problem="p")
    await SelfRefineFlow()._run_loop(state, services)

    sr = state.self_refine_state
    assert sr["stop_reason"] == "model_changed" and sr["target_reached"] is False
    assert [r["round"] for r in sr["rounds"]] == [1, 2]  # the fallback's 9.5 is dropped


@pytest.mark.asyncio
async def test_a_round_scored_by_another_model_is_not_a_self_score():
    # draft1 on "m", eval1 on "fb": round 1's score is discarded, then the loop
    # stops because round 2 runs on "fb", not round 1's "m".
    services = _FallsBack([9.5, 9.5], from_call=2)
    state = PipelineState(problem="p")
    await SelfRefineFlow()._run_loop(state, services)

    sr = state.self_refine_state
    assert sr["rounds"][0]["degraded"] is True and sr["rounds"][0]["score"] is None
    assert sr["stop_reason"] == "model_changed"


@pytest.mark.parametrize("pid", [p for p in PRESETS if p.startswith("self-refine-")])
def test_the_grader_falls_back_off_its_own_lab_and_off_synthesis(pid):
    preset = PRESETS[pid]
    fallback = preset.fallback_routing.get("expert_1")
    assert fallback, f"{pid}: expert_1 has no fallback"
    labs = {_vendor_of(preset.routing["expert_1"]), _vendor_of(preset.routing["synthesis"])}
    assert _vendor_of(fallback) not in labs


@pytest.mark.asyncio
async def test_synthesis_without_rounds_fails_loudly():
    with pytest.raises(PhaseError):
        await SelfRefineFlow()._run_synthesis(PipelineState(problem="p"), _Scripted([]))
