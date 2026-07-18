"""Regression tests: neuro recall must never starve HyperGate routing.

Preflight used to run neuro recall and HyperGate *sequentially inside one
shared timeout*. Recall goes first and is an HTTP self-call, so whenever it
stalled the gate never ran, gate_decision_fb stayed None, and preflight fell
back to action="pipeline" — the most expensive path. A 5-character "hello"
would fan out to a full multi-model pipeline.

Recall is enrichment; the gate decides whether to spend money at all. These
tests pin that a slow/failing recall cannot change the routing decision.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _orchestrator():
    from reasoner.application.orchestrator import PipelineOrchestrator
    from reasoner.application.services.preset_service import PresetService
    from reasoner.application.services.pipeline_service import PipelineService

    return PipelineOrchestrator(PresetService(), PipelineService())


def _command(problem: str = "hello"):
    """preflight() reads its input via getattr, so a namespace is enough here
    and keeps these tests decoupled from the Command dataclass signature."""
    return SimpleNamespace(
        problem=problem,
        preset="multi-perspective-budget",
        top_k=2,
        routing=None,
        no_cache=False,
        force_pipeline=False,
    )


class _FakeGate:
    """Stands in for HyperGateAgent — returns `direct` with no LLM call."""

    def __init__(self, *args, **kwargs):
        pass

    async def decide(self, problem: str):
        from reasoner.hypergate.gate_agent import GateDecision

        return GateDecision(
            action="direct",
            confidence=1.0,
            reasoning="Very short prompt, assumed direct",
            complexity="simple",
        )


@pytest.fixture
def _no_providers():
    """Keep preflight from building real LLM providers."""
    mock_provider = MagicMock()
    with patch(
        "reasoner.infrastructure.llm.registry.build_provider", return_value=mock_provider
    ), patch(
        "reasoner.infrastructure.llm.router.build_provider", return_value=mock_provider
    ):
        yield


@pytest.fixture
def _dev_env():
    from reasoner.core.settings import settings

    original = settings.ENVIRONMENT
    settings.ENVIRONMENT = "development"
    yield
    settings.ENVIRONMENT = original


@pytest.mark.asyncio
async def test_slow_neuro_recall_does_not_starve_gate(_no_providers, _dev_env):
    """A recall that outlives its budget must not downgrade routing to pipeline.

    The gate answers `direct` instantly. Before the fix, recall's stall consumed
    the shared budget and preflight fell back to "pipeline".
    """
    orch = _orchestrator()

    async def _slow_recall(*args, **kwargs):
        await asyncio.sleep(30)
        return []

    with patch.object(
        type(orch), "_recall_neuro_context", new=_slow_recall
    ), patch("reasoner.application.orchestrator.HyperGateAgent", _FakeGate):
        decision = await orch.preflight(_command("hello"))

    assert decision.action == "direct"
    assert decision.recalled_chunks == []


@pytest.mark.asyncio
async def test_failing_neuro_recall_does_not_starve_gate(_no_providers, _dev_env):
    """A recall that raises must not affect routing either."""
    orch = _orchestrator()

    async def _boom_recall(*args, **kwargs):
        raise RuntimeError("neuro down")

    with patch.object(
        type(orch), "_recall_neuro_context", new=_boom_recall
    ), patch("reasoner.application.orchestrator.HyperGateAgent", _FakeGate):
        decision = await orch.preflight(_command("hello"))

    assert decision.action == "direct"
    assert decision.recalled_chunks == []


@pytest.mark.asyncio
async def test_fast_recall_still_populates_chunks(_no_providers, _dev_env):
    """The happy path must keep working: recalled context reaches the decision."""
    orch = _orchestrator()
    chunks = [{"text": "remembered context"}]

    async def _fast_recall(*args, **kwargs):
        return chunks

    with patch.object(
        type(orch), "_recall_neuro_context", new=_fast_recall
    ), patch("reasoner.application.orchestrator.HyperGateAgent", _FakeGate):
        decision = await orch.preflight(_command("hello"))

    assert decision.action == "direct"
    assert decision.recalled_chunks == chunks


@pytest.mark.asyncio
async def test_gate_timeout_still_falls_back_to_pipeline(_no_providers, _dev_env):
    """Preserve existing semantics: if the *gate* stalls, we still run the pipeline."""
    orch = _orchestrator()

    class _StalledGate:
        def __init__(self, *args, **kwargs):
            pass

        async def decide(self, problem: str):
            await asyncio.sleep(30)

    async def _fast_recall(*args, **kwargs):
        return []

    with patch.object(
        type(orch), "_recall_neuro_context", new=_fast_recall
    ), patch("reasoner.application.orchestrator.HyperGateAgent", _StalledGate):
        decision = await orch.preflight(_command("hello"))

    assert decision.action == "pipeline"
