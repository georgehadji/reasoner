"""MP-5: Evidence Search is skipped when pointless, uses its own prompt, and vets.

It used to run on every request (even "simple" ones), borrowed the article
method's retrieval-plan prompt, and handed raw search hits straight to the
perspectives and synthesis with no vetting.
"""
from __future__ import annotations

import json

import pytest

import reasoner.phases as phases
from reasoner.application.flows import perspective_phases
from reasoner.application.flows.multi_perspective import MultiPerspectiveFlow
from reasoner.application.flows.perspective_phases import run_multi_perspective_research_phase
from reasoner.domain.pipeline_state import PipelineState


def _step_names(complexity):
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.complexity = complexity
    return [p.name for p in MultiPerspectiveFlow().get_phases(state)]


def test_simple_problems_skip_evidence_and_stress():
    names = _step_names("simple")
    assert "Evidence Search" not in names
    assert "Stress Testing" not in names
    assert names[0] == "Perspectives"


@pytest.mark.parametrize("complexity", ["medium", "complex", "unknown", None])
def test_other_problems_keep_evidence_search_first(complexity):
    names = _step_names(complexity)
    assert names[0] == "Evidence Search"
    assert "Stress Testing" in names


class _Client:
    async def search(self, query, num_results=5, **kwargs):
        return [
            {"title": "good " + query, "url": "https://ok.example/" + query, "snippet": "solid"},
            {"title": "spam " + query, "url": "https://spam.example/" + query, "snippet": "x"},
        ]


class _Services:
    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    def log(self, *a, **k):
        pass

    async def call_llm(self, role, system_prompt, user_prompt, state=None, **kwargs):
        self.calls.append((role, system_prompt, user_prompt))
        if role == "context_vetting":
            # Flag every second item of the batch (index 1 is the spam hit).
            flagged = [{"index": 1, "flags": ["low quality"]}]
            return json.dumps({"flagged": flagged}), {}
        return json.dumps({"queries": ["q1"]}), {}


@pytest.fixture
def _client(monkeypatch):
    async def _get(*a, **k):
        return _Client(), "fake"

    monkeypatch.setattr(perspective_phases, "get_search_client_for_method", _get)


@pytest.mark.asyncio
async def test_evidence_uses_its_own_prompt_not_the_article_one(_client):
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.preset_name = "multi-perspective-budget"
    services = _Services()

    await run_multi_perspective_research_phase(state, services)

    role, system, _ = services.calls[0]
    assert role == "primary"
    assert system == phases.MP_EVIDENCE_PLAN_SYSTEM
    assert system != phases.ARTICLE_RETRIEVAL_PLAN_SYSTEM


@pytest.mark.asyncio
async def test_results_are_vetted_and_flagged_sources_removed(_client):
    state = PipelineState(problem="Should we migrate to Postgres?")
    state.preset_name = "multi-perspective-budget"
    services = _Services()

    await run_multi_perspective_research_phase(state, services)

    assert any(role == "context_vetting" for role, _, _ in services.calls)
    assert state.vetted_context, "vetting produced nothing"
    assert all("spam" not in r["title"] for r in state.vetted_context)
    # The blind perspectives read web_discovery_results: it must be the vetted set.
    assert state.web_discovery_results == state.vetted_context
    assert all(r.get("summary") for r in state.vetted_context)
