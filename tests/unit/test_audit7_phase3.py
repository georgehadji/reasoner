"""Audit 7 phase 3: run-fatal errors in fan-out phases, discarded cost, the quality judge."""

from __future__ import annotations

import pytest

from reasoner.application.flows.base import require_survivors
from reasoner.core.exceptions import PhaseError, ProviderCreditsExhaustedError, ProviderError
from reasoner.domain.pipeline_state import PipelineState

pytestmark = pytest.mark.unit


# ── finding 4 ───────────────────────────────────────────────────────────────


def test_a_run_fatal_failure_is_re_raised_even_when_other_calls_survived():
    credits = ProviderCreditsExhaustedError("402 out of credit")

    with pytest.raises(ProviderCreditsExhaustedError):
        require_survivors(
            ["one answer"], [str(credits)], phase=2, phase_name="Generation Pool", causes=[credits]
        )


def test_non_fatal_failures_still_raise_phase_error_only_when_nothing_survived():
    boom = ProviderError("transient")

    require_survivors(["ok"], [str(boom)], phase=2, phase_name="X", causes=[boom])
    with pytest.raises(PhaseError, match="All X calls failed"):
        require_survivors([], [str(boom)], phase=2, phase_name="X", causes=[boom])


@pytest.mark.asyncio
async def test_debate_opening_propagates_a_402_when_one_side_survives(monkeypatch):
    from reasoner.application.flows import debate_phases

    class _Services:
        def __init__(self):
            self.calls = 0

        def log(self, *a, **k):
            pass

        async def call_llm(self, **kw):
            self.calls += 1
            if kw["role"] == "destructive":
                raise ProviderCreditsExhaustedError("402")
            return '{"content": "ok"}', {}

    state = PipelineState(problem="p")
    with pytest.raises(ProviderCreditsExhaustedError):
        await debate_phases.run_debate_opening_phase(state, _Services())


# ── finding 15 ──────────────────────────────────────────────────────────────


def test_discarded_cost_is_added_to_the_estimate_not_hidden_by_it():
    from reasoner.infrastructure.llm.pricing_resolver import call_cost_usd, get_pricing

    meta = {
        "model": "gpt-4o-mini", "cost_usd": 0.0, "input_tokens": 1100, "output_tokens": 600,
        "discarded_cost_usd": 0.01, "discarded_input_tokens": 100, "discarded_output_tokens": 100,
    }
    own = get_pricing("gpt-4o-mini").calculate_cost(1000, 500)

    assert call_cost_usd(meta) == pytest.approx(own + 0.01)


def test_the_router_carries_discarded_cost_under_its_own_key():
    """Covered end to end by tests/test_audit9_llm.py::test_f3_empty_attempt_cost_carried_forward."""
    from reasoner.infrastructure.llm.pricing_resolver import call_cost_usd

    own_only = {"model": "gpt-4o-mini", "cost_usd": 0.25, "discarded_cost_usd": 0.5}
    assert call_cost_usd(own_only) == pytest.approx(0.75)


# ── finding 6 ───────────────────────────────────────────────────────────────


def test_every_quality_judge_tier_is_the_western_gate_model():
    from reasoner.core.constants import QUALITY_JUDGE_MODELS
    from reasoner.infrastructure.llm.registry import _REGISTRY

    assert set(QUALITY_JUDGE_MODELS.values()) == {"ministral-14b"}
    assert "mistral" in _REGISTRY["ministral-14b"]["model"]  # Mistral: EU


def test_the_judge_reply_parses_when_fenced():
    from reasoner.quality.monitor import _parse_judge_response

    raw = 'Sure:\n```json\n{"score": 7.5, "passed": true, "reason": "ok"}\n```'
    assert _parse_judge_response(raw)["score"] == 7.5
    assert _parse_judge_response("no json here") is None


@pytest.mark.asyncio
async def test_the_judge_cost_lands_on_the_run(monkeypatch):
    from reasoner.infrastructure.llm.router import ProviderRouter
    from reasoner.quality.monitor import PhaseMonitor

    class _Judge:
        async def call(self, *a, **k):
            return '{"score": 8, "passed": true}', {"cost_usd": 0.004}

    monkeypatch.setattr(ProviderRouter, "from_model_ids", staticmethod(lambda *_: _Judge()))
    monitor = PhaseMonitor(router=None, preset_name="debate-western-budget")
    state = PipelineState(problem="p")
    from reasoner.quality.criteria import PhaseQualityResult

    rule = PhaseQualityResult(passed=False, score=0.0, reason="r", suggestions=[])

    out = await monitor._llm_judge("Perspectives", state, rule)

    assert out.passed and state.total_cost_usd == pytest.approx(0.004)
    assert state.phase_costs["quality_judge"] == pytest.approx(0.004)
