"""
Regression tests for API stream phase error handling (BUG-003).
Uses fakes — no OPENROUTER_API_KEY required.
"""

import json
import pytest
from unittest.mock import patch

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
        self.primary = self._primary
        self.routing_table = {r: self._primary for r in [
            "constructive", "destructive", "systemic", "minimalist",
            "classification", "decomposition", "deep_read", "perspectives",
            "critique", "stress_testing", "synthesis",
        ]}
        self.cascading_routing = {}

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


@pytest.mark.asyncio
async def test_critical_phase_error_halts_pipeline():
    """
    If a critical phase like Decomposition raises an exception,
    the stream should emit a phase_error event and stop before Synthesis.
    """
    req = RunRequest(problem="test critical error", preset="multi-perspective-budget")

    fake_router = FakeRouter()

    with patch("reasoner.llm.ProviderRouter.from_model_ids", return_value=fake_router):
        # Phases are PhaseStep entries on a WorkflowStrategy now; "Critique & Pruning"
        # is the critical step in MultiPerspectiveFlow.
        with patch(
            "reasoner.application.flows.multi_perspective.run_critique_phase",
            side_effect=ValueError("simulated decomposition failure"),
        ):
            events = []
            async for line in run_stream(req):
                if line.startswith("data:"):
                    events.append(_parse_sse(line))

    # Should report the phase error
    phase_errors = [e for e in events if e.get("type") == "phase_error"]
    assert len(phase_errors) == 1
    assert "ValueError: simulated decomposition failure" in phase_errors[0]["error"]

    # Synthesis must NOT have been attempted
    synthesis_completes = [
        e for e in events
        if e.get("type") == "phase_complete" and e.get("name") == "Synthesis"
    ]
    assert len(synthesis_completes) == 0


@pytest.mark.asyncio
async def test_non_critical_phase_error_continues_pipeline():
    """
    If a non-critical phase like Deep Read raises an exception,
    the stream should emit a phase_error event and continue to Synthesis.
    """
    req = RunRequest(problem="test non-critical error", preset="multi-perspective-budget")

    fake_router = FakeRouter()

    with patch("reasoner.llm.ProviderRouter.from_model_ids", return_value=fake_router):
        # Patch Deep Read to blow up, but leave everything else intact.
        # We also short-circuit Synthesis so it doesn't need real LLM data.
        # Short-circuit network-dependent helpers so the test finishes quickly.
        # "Evidence Search" is the non-critical PhaseStep that opens
        # MultiPerspectiveFlow; deep read is no longer a step in this flow.
        with patch(
            "reasoner.application.flows.multi_perspective.run_multi_perspective_research_phase",
            side_effect=RuntimeError("simulated deep read failure"),
        ):
            with patch(
                "reasoner.pipeline.ReasonerPipeline._phase_synthesis",
                return_value=None,
            ):
                    # Neuro recall moved to the orchestrator.
                    with patch(
                        "reasoner.application.orchestrator.PipelineOrchestrator._recall_neuro_context",
                        return_value=[],
                    ):
                        events = []
                        async for line in run_stream(req):
                            if line.startswith("data:"):
                                events.append(_parse_sse(line))

    # Deep Read phase error should be reported
    phase_errors = [e for e in events if e.get("type") == "phase_error"]
    assert len(phase_errors) == 1
    assert "RuntimeError: simulated deep read failure" in phase_errors[0]["error"]

    # Synthesis should still complete because Deep Read is non-critical
    synthesis_completes = [
        e for e in events
        if e.get("type") == "phase_complete" and e.get("name") == "Synthesis"
    ]
    assert len(synthesis_completes) == 1
