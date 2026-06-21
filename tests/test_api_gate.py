"""API integration tests for the GateAgent in the SSE stream."""

import json
import pytest
from unittest.mock import AsyncMock, patch

from reasoner.api import run_stream, RunRequest


class FakeProvider:
    def __init__(self, model="fake"):
        self.model = model

    async def complete_with_retry(self, system_prompt, user_prompt, max_tokens=2048, temperature=0.7):
        return "fake"


class FakeRouter:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []
        self._primary = FakeProvider()

    def get(self, role):
        return self._primary

    async def call(self, role, system_prompt, user_prompt, **kwargs):
        self.calls.append((role, system_prompt, user_prompt))
        return self.responses.get(role, "{}"), {"model": "fake", "input_tokens": 10, "output_tokens": 10}

    def describe(self):
        return {"[primary]": "fake"}


def _parse_sse(line: str) -> dict:
    """Strip 'data: ' prefix and parse JSON."""
    return json.loads(line.removeprefix("data: ").strip())


@pytest.fixture
def valid_run_payload():
    return {
        "problem": "Explain quantum computing in simple terms.",
        "preset": "multi-perspective-budget",
    }


# ─────────────────────────────────────────────────────────────────────
# Force pipeline
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_force_pipeline_skips_gate(valid_run_payload):
    """When force_pipeline=True, the gate should never be instantiated."""
    req = RunRequest(**valid_run_payload, force_pipeline=True)
    fake_router = FakeRouter()

    with patch("reasoner.application.orchestrator.HyperGateAgent") as mock_gate_cls:
        mock_gate_cls.return_value.decide = AsyncMock(return_value=None)
        with patch("reasoner.llm.ProviderRouter.from_model_ids", return_value=fake_router):
            with patch("reasoner.pipeline.ReasonerPipeline._phase_0_classify", return_value=None):
                events = []
                async for line in run_stream(req):
                    if line.startswith("data:"):
                        events.append(_parse_sse(line))
    mock_gate_cls.assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# Direct answer stream
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_direct_answer_stream_format(valid_run_payload):
    """When HyperGateAgent decides 'direct', the SSE should contain a virtual single-phase pipeline."""
    req = RunRequest(**valid_run_payload)
    from reasoner.gate_agent import GateDecision
    fake_decision = GateDecision(action="direct", method=None, confidence=0.95, reasoning="Simple factual question")
    fake_router = FakeRouter()

    with patch("reasoner.application.orchestrator.HyperGateAgent") as mock_gate_cls:
        mock_gate = mock_gate_cls.return_value
        mock_gate.decide = AsyncMock(return_value=fake_decision)

        with patch("reasoner.llm.ProviderRouter.from_model_ids", return_value=fake_router):
            with patch.object(fake_router, "call", new_callable=AsyncMock) as mock_call:
                mock_call.return_value = ("Quantum computing uses qubits.", {"input_tokens": 12, "output_tokens": 34})
                events = []
                async for line in run_stream(req):
                    if line.startswith("data:"):
                        events.append(_parse_sse(line))

    types = [e.get("type") for e in events]
    assert "start" in types
    assert "phase_start" in types
    assert "phase_complete" in types
    assert "done" in types

    phase_start = next(e for e in events if e.get("type") == "phase_start")
    assert phase_start["name"] == "Direct Response"

    phase_complete = next(e for e in events if e.get("type") == "phase_complete")
    assert phase_complete["data"]["solution"] == "Quantum computing uses qubits."
    assert phase_complete["data"]["tokens"]["input"] == 12
    assert phase_complete["data"]["tokens"]["output"] == 34

    done = next(e for e in events if e.get("type") == "done")
    assert done["errors"] == []
    assert done["total_tokens"]["total"] == 46


# ─────────────────────────────────────────────────────────────────────
# Pipeline fallback on gate failure
# ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_failure_falls_back_to_pipeline(valid_run_payload):
    """When HyperGateAgent raises unexpectedly, run_stream should fall back to pipeline."""
    req = RunRequest(**valid_run_payload)
    fake_router = FakeRouter()

    with patch("reasoner.application.orchestrator.HyperGateAgent") as mock_gate_cls:
        mock_gate = mock_gate_cls.return_value
        mock_gate.decide = AsyncMock(side_effect=RuntimeError("unexpected"))

        with patch("reasoner.llm.ProviderRouter.from_model_ids", return_value=fake_router):
            with patch("reasoner.pipeline.ReasonerPipeline._phase_0_classify", return_value=None):
                events = []
                async for line in run_stream(req):
                    if line.startswith("data:"):
                        events.append(_parse_sse(line))

    types = [e.get("type") for e in events]
    assert "done" in types
    done = next(e for e in events if e.get("type") == "done")
    assert done["errors"]  # non-empty error list
