"""PR 5 of docs/plans/audit-remediation-2-2026-10-20.md: FLOW-1, 3, 4, 6 to 11.

Each test names the register row it pins. They drive the phase functions with
a scripted ``services`` object, so no model is called.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from reasoner.application.flows.base import PhaseStep
from reasoner.core.exceptions import PhaseError, RateLimitError
from reasoner.core.parsing import coerce_list, coerce_verdict
from reasoner.domain.pipeline_state import PipelineState

pytestmark = pytest.mark.asyncio


class _Services:
    """call_llm answers from *reply(role, user_prompt)*; every call is recorded."""

    def __init__(self, reply):
        self._reply = reply
        self.calls: list[tuple[str, str]] = []
        self.router = None

    async def call_llm(self, *, role, system_prompt, user_prompt, state, **kwargs):
        self.calls.append((role, user_prompt))
        out = self._reply(role, user_prompt)
        if isinstance(out, Exception):
            raise out
        return out, {"model": f"model-for-{role}"}

    def log(self, *args, **kwargs):
        pass


def _state(**kw) -> PipelineState:
    return PipelineState(problem=kw.pop("problem", "Should we migrate to Postgres?"), **kw)


# ── FLOW-1: a recovered retry is a success ─────────────────────────────


async def test_critical_phase_that_recovers_on_retry_completes():
    from reasoner.application.flows.runner import WorkflowRunner

    attempts = []

    async def flaky(state, services):
        attempts.append(1)
        if len(attempts) == 1:
            raise RateLimitError("slow down")

    class _Pass:
        async def evaluate(self, name, state, attempt=1):
            return SimpleNamespace(score=9.0, passed=True, reason="ok", suggestions=[])

    runner = WorkflowRunner(_Services(lambda *_: "{}"), monitor=_Pass())
    state = _state()
    step = PhaseStep(2, "Perspectives", flaky, lambda s: {}, critical=True)
    with patch("reasoner.application.flows.runner.asyncio.sleep", return_value=None):
        assert await runner.run_phase(step, state) is True
    assert len(attempts) == 2
    assert "Phase 2: Perspectives" in state.phase_durations


# ── FLOW-3: a fan-out that produced nothing raises ─────────────────────


async def test_all_jury_generators_failing_raises():
    from reasoner.application.flows.jury_phases import run_jury_generate_phase

    services = _Services(lambda role, _: RuntimeError(f"{role} down"))
    with pytest.raises(PhaseError, match="Generation Pool"):
        await run_jury_generate_phase(_state(), services)


async def test_all_delphi_experts_failing_raises_and_round_1_is_critical():
    from reasoner.application.flows.delphi import DelphiFlow
    from reasoner.application.flows.delphi_phases import run_delphi_round1_phase

    with pytest.raises(PhaseError, match="Round 1 Estimates"):
        await run_delphi_round1_phase(_state(), _Services(lambda *_: RuntimeError("down")))
    steps = {s.name: s for s in DelphiFlow().get_phases(_state())}
    assert steps["Round 1 Estimates"].critical


# ── FLOW-4: null lists from the model ──────────────────────────────────


@pytest.mark.parametrize("value,expected", [
    (None, []), ("", []), ("one", ["one"]), (["a", "b"], ["a", "b"]),
    (("a",), ["a"]), ({"k": 1}, [{"k": 1}]),
])
def test_coerce_list(value, expected):
    assert coerce_list(value) == expected


async def test_scientific_test_phase_skips_with_no_hypotheses():
    from reasoner.application.flows.dialectical_phases import run_scientific_test_phase
    from reasoner.phases.scientific import scientific_test_prompt

    services = _Services(lambda *_: "{}")
    state = _state()
    state.scientific_state["hypotheses"] = None
    await run_scientific_test_phase(state, services)
    assert services.calls == []
    assert scientific_test_prompt(_state())  # no KeyError on a fresh state


async def test_untested_hypothesis_has_no_posterior():
    from reasoner.application.flows.dialectical_phases import run_scientific_test_phase

    state = _state()
    state.scientific_state["hypotheses"] = [{"id": "H1"}, {"id": "H2"}]
    reply = json.dumps({"test_results": [{"hypothesis_id": "H1", "result": "SUPPORTED"}]})
    await run_scientific_test_phase(state, _Services(lambda *_: reply))
    by_id = {h["id"]: h for h in state.scientific_state["hypotheses"]}
    assert by_id["H1"]["posterior_probability"] == 1.0
    assert by_id["H2"]["posterior_probability"] is None


# ── FLOW-6: ToT expands every decision point ───────────────────────────


async def test_tot_builds_a_path_over_every_decision_point():
    from reasoner.application.flows import cognitive_phases as tot
    from reasoner.phases.tot import tot_backtrack_prompt

    state = _state(problem="Pick a database for the ledger")
    state.tot_state["decision_points"] = [{"id": f"dp{i}"} for i in range(1, 5)]
    state.tot_state["current_path"] = []
    n = {"eval": 0}

    def reply(role, prompt):
        if role == "tot_generate":
            return json.dumps({"candidates": ["x", "y"]})
        n["eval"] += 1
        return json.dumps({"evaluations": [{"candidate": "x", "score": 8}],
                           "best_candidate": f"step-{n['eval']}"})

    services = _Services(reply)
    await tot.run_tot_generate_phase(state, services)
    await tot.run_tot_evaluate_phase(state, services)

    assert state.tot_state["current_path"] == ["step-1", "step-2", "step-3", "step-4"]
    assert len(state.tot_state["evaluations"]) == 4
    assert "Pick a database for the ledger" in tot_backtrack_prompt(state)
    assert "Pick a database for the ledger" in services.calls[-1][1]


# ── FLOW-7: verdict normalisation ──────────────────────────────────────


@pytest.mark.parametrize("raw", ["Accept", " accept ", "ACCEPT"])
def test_verdict_is_normalised(raw):
    assert coerce_verdict(raw) == "ACCEPT"


async def test_mixed_case_accept_is_an_accept():
    from reasoner.application.flows.iterative_critique_phases import _llm_critic_round

    reply = json.dumps({"verdict": "Accept", "scores": {}, "flaws_identified": []})
    rnd = await _llm_critic_round(_state(), _Services(lambda *_: reply), "answer", 1)
    assert rnd.verdict == "ACCEPT"


# ── FLOW-8: translate-out is all or nothing ────────────────────────────


async def test_failed_translate_out_leaves_the_solution_untouched():
    from reasoner.application.pipeline import ReasonerPipeline
    from reasoner.domain.core_types import FinalSolution

    calls = {"n": 0}

    class _Translator:
        async def translate(self, text, target_lang, source_lang):
            calls["n"] += 1
            if calls["n"] == 1:
                return SimpleNamespace(degraded=False, text="ΜΕΤΑΦΡΑΣΗ", degraded_reason=None)
            return SimpleNamespace(degraded=True, text="", degraded_reason="down")

    state = _state()
    state.pivot_active = True
    state.output_language = "Greek"
    state.final_solution = FinalSolution(
        core_solution="original", critical_insights=["insight"], action_blueprint=[],
        open_questions=[], claim_labels={}, meta_audit=None,
    )
    fake_self = SimpleNamespace(router=None, _log=lambda *a, **k: None)
    with patch(
        "reasoner.infrastructure.translation.get_composite_translator",
        return_value=_Translator(),
    ):
        await ReasonerPipeline._phase_cross_language_translate_out(fake_self, state)

    assert state.final_solution.core_solution == "original"
    assert state.final_solution.critical_insights == ["insight"]


# ── FLOW-9: Prism keeps what it found when it times out ────────────────


async def test_prism_timeout_keeps_citations_already_collected():
    from reasoner.application.flows.prism_research import run_prism_research_phase

    n = {"plans": 0}
    hang = asyncio.Event()

    class _Svc(_Services):
        async def call_llm(self, **kwargs):
            n["plans"] += 1
            if n["plans"] == 1:
                return json.dumps({"action": "webSearch", "queries": ["q"]}), {}
            await hang.wait()

    class _Search:
        async def search(self, q, num_results, source_type):
            return [{"url": "https://example.org/a", "title": "A", "snippet": "s"}]

    state = _state()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            run_prism_research_phase(state, _Svc(None), _Search(), mode="balanced"), 0.5,
        )
    citations = state.method_state.get("prism")["citations"]
    assert [c["url"] for c in citations] == ["https://example.org/a"]


# ── FLOW-10: bounded fan-out ───────────────────────────────────────────


async def test_sot_solves_at_most_the_capped_number_of_subproblems():
    from reasoner.application.flows.cognitive_phases import run_sot_solve_phase
    from reasoner.core.constants_limits import MAX_SOT_SUBPROBLEMS

    state = _state()
    state.sot_state["sub_problems"] = [{"id": f"s{i}"} for i in range(40)]
    services = _Services(lambda *_: json.dumps({"solution": "ok"}))
    await run_sot_solve_phase(state, services)
    assert len(services.calls) == MAX_SOT_SUBPROBLEMS


async def test_coding_caps_files_and_drops_failed_ones():
    from reasoner.application.flows.coding_phases import run_coding_generate_phase
    from reasoner.core.constants_limits import MAX_CODING_FILES

    state = _state()
    files = [{"path": f"f{i}.py", "purpose": "p"} for i in range(40)]
    state.coding_state["files_to_generate"] = files

    def reply(role, prompt):
        return RuntimeError("boom") if "f0.py" in prompt else json.dumps({"content": "x = 1"})

    services = _Services(reply)
    await run_coding_generate_phase(state, services)
    assert len(services.calls) == MAX_CODING_FILES
    paths = [f["path"] for f in state.coding_state["generated_files"]]
    assert "f0.py" not in paths and len(paths) == MAX_CODING_FILES - 1
    assert not any("# Error" in f["content"] for f in state.coding_state["generated_files"])


async def test_coding_with_every_file_failing_raises():
    from reasoner.application.flows.coding_phases import run_coding_generate_phase

    state = _state()
    state.coding_state["files_to_generate"] = [
        {"path": "a.py", "purpose": "p"}, {"path": "b.py", "purpose": "p"},
    ]
    with pytest.raises(PhaseError, match="Code Generation"):
        await run_coding_generate_phase(state, _Services(lambda *_: RuntimeError("boom")))


# ── FLOW-11: model_used is a name, not the meta dict ───────────────────


async def test_jury_candidate_model_used_is_a_string():
    from reasoner.application.flows.jury_phases import run_jury_generate_phase

    state = _state()
    reply = json.dumps({"solution": "s", "confidence": 0.5, "key_claims": []})
    await run_jury_generate_phase(state, _Services(lambda *_: reply), gen_roles=["generator_1"])
    assert state.generation_candidates[0].model_used == "model-for-generator_1"


async def test_jury_critic_tolerates_extra_keys_and_records_its_model():
    """CriticScore(**data) raised on any key the model added, so every critic
    failed silently until FLOW-3 made an empty Critic Pool fatal."""
    from reasoner.application.flows.jury_phases import run_jury_critique_phase

    reply = json.dumps({
        "task_type": "hybrid", "ranking": ["generator_1"], "dissenting_note": None,
        "candidate_scores": {"generator_1": {"factuality": 8}},
    })
    state = _state()
    await run_jury_critique_phase(state, _Services(lambda *_: reply), critic_roles=["critic_1"])
    (score,) = state.critic_scores
    assert score.critic_model == "model-for-critic_1"
    assert score.ranking == ["generator_1"] and score.dissenting_note == ""
