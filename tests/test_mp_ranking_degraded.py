"""MP-2: an unranked fallback must be visible.

When the scorer returned nothing usable, run_critique_phase fell back to the
first two candidates and only appended to state.errors. Synthesis then received
them as the "top" candidates with no sign they were never scored.
"""
from __future__ import annotations

import json

import pytest

from reasoner.application.flows.perspective_phases import run_critique_phase
from reasoner.domain.core_types import SolutionCandidate
from reasoner.domain.pipeline_state import PipelineState
from reasoner.models import PerspectiveRegistry
from reasoner.phases._universal import synthesis_prompt


class _Services:
    def __init__(self, reply: str):
        self.reply = reply

    def log(self, *a, **k):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        return self.reply, {"model": "m"}


def _state() -> PipelineState:
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.language = "English"
    state.candidates = [
        SolutionCandidate(
            perspective=PerspectiveRegistry.coerce(p), content=f"{p} plan",
            key_insights=[], model_used="",
        )
        for p in ("constructive", "destructive", "systemic")
    ]
    return state


def _warnings(state) -> list[str]:
    return [e["message"] for e in state.pending_events if e.get("type") == "phase_warning"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply", ["not json", json.dumps({"scores": []})], ids=["garbled", "empty"]
)
async def test_unusable_scorer_output_degrades_visibly(reply):
    state = _state()

    await run_critique_phase(state, _Services(reply))

    assert state.ranking_degraded is True
    assert len(state.top_candidates) == 2
    assert any("not independently ranked" in w for w in _warnings(state))
    assert any(d.startswith("mp.critique") for d in state.degradations)
    assert "RANKING NOTE" in synthesis_prompt(state)


@pytest.mark.asyncio
async def test_a_good_scoring_clears_the_flag_and_adds_no_note():
    state = _state()
    state.ranking_degraded = True  # left over from an earlier failed attempt
    good = json.dumps({"scores": [
        {"perspective": "constructive", "logical_consistency": 9, "feasibility": 9,
         "novelty": 9, "completeness": 9},
    ]})

    await run_critique_phase(state, _Services(good))

    assert state.ranking_degraded is False
    assert "RANKING NOTE" not in synthesis_prompt(state)


def test_older_state_without_the_field_defaults_false():
    assert PipelineState(problem="p").ranking_degraded is False
