"""Proves pipeline.py actually emits what run_metering.extract_run_cost reads.

test_run_metering.py proves the metering module's own logic in isolation with
hand-built frame strings. It cannot catch a drift between that string shape and
what api/execution/pipeline.py really puts on the wire -- the two could
disagree silently. This exercises the real SSE frame construction through
run_stream(), the same harness test_api_phase_errors.py uses, and feeds the
real frames through extract_run_cost.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from reasoner.api import RunRequest, run_stream
from reasoner.application.services.run_metering import extract_run_cost

pytestmark = pytest.mark.unit


class FakeProvider:
    def __init__(self, model="fake"):
        self.model = model

    async def complete_with_retry(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        return "fake"


class FakeRouter:
    def __init__(self):
        self.calls = []
        self._primary = FakeProvider()
        self.primary = self._primary
        self.routing_table = {r: self._primary for r in [
            "constructive", "destructive", "systemic", "minimalist",
            "classification", "decomposition", "deep_read", "perspectives",
            "critique", "stress_testing", "synthesis",
        ]}
        self.cascading_routing = {}
        self.fallback_table = {}
        self.verbose = False
        self.run_id = ""
        self.preset_id = ""
        self.method = ""

    def get(self, role):
        return self._primary

    async def call(self, role, system_prompt, user_prompt, **kwargs):
        self.calls.append((role, system_prompt, user_prompt))
        return "{}", {"model": "fake", "input_tokens": 100, "output_tokens": 100}

    def describe(self):
        return {"[primary]": "fake"}


def _parse_sse(line: str) -> dict:
    return json.loads(line.removeprefix("data: ").strip())


@pytest.fixture(autouse=True)
def _preflight_env(monkeypatch):
    """Same wiring test_api_phase_errors.py needs -- see its docstring for why
    each of these three is required to reach real phase execution."""
    import reasoner.api.execution.pipeline as execution
    import reasoner.application.orchestrator as orch
    from reasoner.core.ports.model_registry_port import set_model_registry_port
    from reasoner.infrastructure.llm.registry import RegistryAdapter

    set_model_registry_port(RegistryAdapter())
    monkeypatch.setattr(execution, "check_run_allowed", lambda *a, **k: None)

    class _NoopGate:
        def __init__(self, *args, **kwargs):
            pass

        async def decide(self, *args, **kwargs):
            return None

    monkeypatch.setattr(orch, "HyperGateAgent", _NoopGate)


@pytest.mark.asyncio
async def test_phase_complete_frames_carry_a_cost_extract_run_cost_can_read():
    """The regression this guards: pipeline.py's phase_complete payload and
    run_metering's parser drifting apart silently. Every phase_complete frame
    from a real run must have a `total_cost_usd` extract_run_cost accepts."""
    req = RunRequest(problem="test cost on phase frames", preset="multi-perspective-budget")

    with patch("reasoner.llm.ProviderRouter.from_model_ids", return_value=FakeRouter()):
        raw_lines = [line async for line in run_stream(req)]

    events = [_parse_sse(line) for line in raw_lines if line.startswith("data:")]
    phase_completes = [e for e in events if e.get("type") == "phase_complete"]

    assert phase_completes, "the fixture run produced no phase_complete frames at all"
    for event in phase_completes:
        assert "total_cost_usd" in event, event
        assert isinstance(event["total_cost_usd"], (int, float))
        assert not isinstance(event["total_cost_usd"], bool)

    # extract_run_cost must actually accept the real frame string, not just a
    # dict that happens to have the right key -- re-serialised through the
    # module's own event() wrapper the way the real stream does.
    from reasoner.api.sse_utils import _event

    real_frame = _event(phase_completes[0])
    parsed = extract_run_cost(real_frame)
    # extract_run_cost returns None for a zero cost by design (the fixture
    # router's fake pricing may legitimately price at $0), so only assert
    # equality when there was something to extract.
    if phase_completes[0]["total_cost_usd"] > 0:
        assert parsed == phase_completes[0]["total_cost_usd"]
    else:
        assert parsed is None


@pytest.mark.asyncio
async def test_running_cost_on_phase_frames_never_decreases():
    """The running total is cumulative across the run. A phase frame reporting
    a smaller total_cost_usd than an earlier one would make a policy of
    'bill the latest seen figure' bill less than what was actually spent."""
    req = RunRequest(problem="test monotonic cost", preset="multi-perspective-budget")

    with patch("reasoner.llm.ProviderRouter.from_model_ids", return_value=FakeRouter()):
        raw_lines = [line async for line in run_stream(req)]

    events = [_parse_sse(line) for line in raw_lines if line.startswith("data:")]
    costs = [e["total_cost_usd"] for e in events if e.get("type") == "phase_complete"]

    assert costs == sorted(costs)
