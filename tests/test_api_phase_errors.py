"""
Regression tests for API stream phase error handling (BUG-003).
Uses fakes — no OPENROUTER_API_KEY required.
"""

import json
from unittest.mock import patch

import pytest

from reasoner.api import RunRequest, run_stream


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
        self.fallback_table = {}
        self.verbose = False
        self.run_id = ""
        self.preset_id = ""
        self.method = ""

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


@pytest.fixture(autouse=True)
def _preflight_env(monkeypatch):
    """Give run_stream the startup wiring it normally gets from the app.

    These tests call run_stream() directly, so no lifespan runs. Without the
    registry port injected, preflight raised "ModelRegistryPort not injected"
    and the stream emitted a single generic `error` -- the run never reached
    the phases these tests patch, which is why they saw zero phase_error
    events regardless of what was patched.

    HyperGate is stubbed for the same reason it matters here: it builds its
    own LLM clients, so patching ProviderRouter.from_model_ids never reached
    it and it spent its full 10s budget on real network calls.
    """
    import reasoner.api.execution.pipeline as execution
    import reasoner.application.orchestrator as orch
    from reasoner.core.ports.model_registry_port import set_model_registry_port
    from reasoner.infrastructure.llm.registry import RegistryAdapter

    set_model_registry_port(RegistryAdapter())

    # Unauthenticated runs resolve to the free tier, whose per-run cost limit
    # rejects multi-perspective-budget outright. These tests are about phase
    # error propagation, not billing, so let the run through.
    monkeypatch.setattr(execution, "check_run_allowed", lambda *a, **k: None)

    class _NoopGate:
        def __init__(self, *args, **kwargs):
            pass

        async def decide(self, *args, **kwargs):
            return None

    monkeypatch.setattr(orch, "HyperGateAgent", _NoopGate)


@pytest.mark.asyncio
async def test_critical_phase_error_halts_pipeline():
    """
    If a critical phase like Critique & Pruning raises an exception,
    the stream should emit a phase_error event and stop before Synthesis.

    Critique & Pruning is the only critical=True step in MultiPerspectiveFlow
    (application/flows/multi_perspective.py) — Decomposition is no longer a
    pipeline phase (classification/decomposition moved into HyperGate
    preflight), so it can't be used to test critical-phase halting anymore.
    """
    req = RunRequest(problem="test critical error", preset="multi-perspective-budget")

    fake_router = FakeRouter()

    with patch("reasoner.llm.ProviderRouter.from_model_ids", return_value=fake_router):
        with patch(
            "reasoner.application.flows.multi_perspective.run_critique_phase",
            side_effect=ValueError("simulated critique failure"),
        ):
            events = []
            async for line in run_stream(req):
                if line.startswith("data:"):
                    events.append(_parse_sse(line))

    # Should report the phase error
    phase_errors = [e for e in events if e.get("type") == "phase_error"]
    assert len(phase_errors) == 1
    assert "ValueError: simulated critique failure" in phase_errors[0]["error"]

    # Synthesis must NOT have been attempted
    synthesis_completes = [
        e for e in events
        if e.get("type") == "phase_complete" and e.get("name") == "Synthesis"
    ]
    assert len(synthesis_completes) == 0


@pytest.mark.asyncio
async def test_non_critical_phase_error_continues_pipeline():
    """
    If a non-critical phase like Stress Testing raises an exception,
    the stream should emit a phase_error event and continue to Synthesis.

    Deep Read isn't part of MultiPerspectiveFlow's phase list (it's a
    method-specific step, not wired for multi-perspective-budget), and
    Synthesis/Context Vetting are no longer ReasonerPipeline methods — the
    strategy calls the standalone run_synthesis_phase/run_context_vetting_phase
    functions instead. Context Vetting itself is currently dead code in
    api/execution/pipeline.py (defined but never invoked), so no patch is
    needed for it.
    """
    req = RunRequest(problem="test non-critical error", preset="multi-perspective-budget")

    fake_router = FakeRouter()

    with patch("reasoner.llm.ProviderRouter.from_model_ids", return_value=fake_router):
        # Patch Stress Testing to blow up, but leave everything else intact.
        # We also short-circuit Synthesis so it doesn't need real LLM data.
        # Short-circuit network-dependent helpers so the test finishes quickly.
        with patch(
            "reasoner.application.flows.multi_perspective.run_stress_test_phase",
            side_effect=RuntimeError("simulated stress test failure"),
        ):
            with patch(
                "reasoner.application.flows.multi_perspective.run_synthesis_phase",
                return_value=None,
            ):
                with patch(
                    "reasoner.application.orchestrator.PipelineOrchestrator._recall_neuro_context",
                    return_value=[],
                ):
                    events = []
                    async for line in run_stream(req):
                        if line.startswith("data:"):
                            events.append(_parse_sse(line))

    # Stress Testing phase error should be reported
    phase_errors = [e for e in events if e.get("type") == "phase_error"]
    assert len(phase_errors) == 1
    assert "RuntimeError: simulated stress test failure" in phase_errors[0]["error"]

    # Synthesis should still complete because Deep Read is non-critical
    synthesis_completes = [
        e for e in events
        if e.get("type") == "phase_complete" and e.get("name") == "Synthesis"
    ]
    assert len(synthesis_completes) == 1
