"""Every phase and subagent call is told today's date.

Live run, 2026-11-10: asked about "the elections to be held in Greece next
May", the iterative-critique generator planned for a May 2024 election that
never existed. No prompt in phases/, flows/ or subagents/ carried the date, so
"next May", "this year" and "recent" resolved against each model's training
cutoff, and a model with an older cutoff argued from an older calendar.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

import reasoner.phases._shared as shared
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases._shared import with_current_date
from reasoner.subagents.base import PhaseSubAgent

_DAY = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def _frozen_day(monkeypatch):
    monkeypatch.setattr(shared, "_today", lambda: _DAY)


def test_appends_the_date_after_the_prompt():
    out = with_current_date("PHASE PROMPT")
    assert out.startswith("PHASE PROMPT")
    assert "2026-11-10" in out
    # The point of the line: relative dates resolve against it.
    assert "next" in out.lower() and "training" in out.lower()


@pytest.mark.asyncio
async def test_workflow_services_call_carries_the_date():
    from reasoner.application.flows.services import PipelineWorkflowServices

    seen: dict = {}

    class _FakePipeline:
        async def _call_llm_cached(self, **kwargs):
            seen.update(kwargs)
            return ("{}", {})

    services = PipelineWorkflowServices.__new__(PipelineWorkflowServices)
    services._pipeline = _FakePipeline()
    services._runner = None

    await services.call_llm(
        role="expert_1", system_prompt="PHASE PROMPT", user_prompt="u",
        state=PipelineState(problem="q"),
    )
    assert "2026-11-10" in seen["system_prompt"]
    assert "PHASE PROMPT" in seen["system_prompt"]


class _Agent(PhaseSubAgent):
    AGENT_NAME = "date_probe"
    ROLE = "synthesis"
    MAX_TOKENS = 64

    def _build_prompt(self, state):
        return ("SUBAGENT PROMPT", "u")

    def _parse_result(self, raw):
        return {"answer": raw, "confidence": 1.0, "rationale": ""}


@pytest.mark.asyncio
async def test_subagent_call_carries_the_date():
    router = AsyncMock()
    router.call.return_value = ("ok", {"model": "m"})

    await _Agent().execute(PipelineState(problem="date probe"), router)

    system_prompt = router.call.call_args.kwargs["system_prompt"]
    assert "2026-11-10" in system_prompt
    assert "SUBAGENT PROMPT" in system_prompt
