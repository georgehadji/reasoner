"""Provider error types survive the router, and a spend-cap stop is a failure."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from reasoner.application.flows.base import PhaseStep
from reasoner.core.exceptions import ProviderCreditsExhaustedError, is_run_fatal
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm import executor as executor_mod
from reasoner.infrastructure.llm.ports import DegradedLLMResponse
from reasoner.infrastructure.llm.router import ProviderRouter

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_a_402_reaches_the_runner_as_a_run_fatal_error(monkeypatch):
    """The router used to keep only str(exc), so the executor raised a bare
    RuntimeError and is_run_fatal never saw the 402: a run out of credit ground
    through every phase and reported success."""
    from reasoner.core.settings import settings

    monkeypatch.setattr(settings, "MULTI_PROVIDER_FALLBACK_ENABLED", False)

    async def out_of_credit(self, *a, **kw):
        raise ProviderCreditsExhaustedError("402 insufficient credits")

    monkeypatch.setattr(ProviderRouter, "_attempt_call_and_record", out_of_credit)
    raw, _ = await ProviderRouter(primary=MagicMock(model="m")).call("primary", "s", "u")

    assert isinstance(raw, DegradedLLMResponse)
    with pytest.raises(ProviderCreditsExhaustedError) as caught:
        executor_mod._raise_provider_cause(raw)
    assert is_run_fatal(caught.value)


def test_a_degraded_response_without_a_provider_cause_is_left_alone():
    executor_mod._raise_provider_cause(DegradedLLMResponse(error="timed out"))


@pytest.mark.asyncio
async def test_a_spend_cap_stop_fails_the_run_instead_of_skipping_silently():
    """Skipping with True ended the run with no synthesis and `errors: []`, so
    it was recorded as completed and its empty answer was cached."""
    from reasoner.application.flows.runner import WorkflowRunner

    ran = []

    async def phase(state, services):
        ran.append(True)

    state = PipelineState(problem="p")
    state._spend_cap_exceeded = True
    state.spend_cap_hit = "per_run"
    runner = WorkflowRunner(services=MagicMock(), monitor=MagicMock())

    ok = await runner.run_phase(PhaseStep(5.0, "Synthesis", phase, lambda s: {}), state)

    assert ok is False and not ran
    assert state._run_fatal is True
    assert any("per_run spend cap" in e for e in state.errors)
