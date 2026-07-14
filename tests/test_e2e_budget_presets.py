"""
Real end-to-end tests focused on budget presets with live OpenRouter API calls.

These tests are adversarial by design: they exercise each budget preset with
varying top_k, source types, and problem complexity to surface hangs, rate-limit
issues, and provider-specific failures.

Run with: python -m pytest tests/test_e2e_budget_presets.py -v --run-slow
"""

import os

import pytest
import asyncio

from reasoner.application.services.preset_service import PresetService
from reasoner.pipeline import ReasonerPipeline
from reasoner.presets import PRESETS, get_preset

pytestmark = [
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set",
    ),
]

SIMPLE_PROBLEM = "What is the capital of France and why is it historically significant?"
COMPLEX_PROBLEM = (
    "Analyze the trade-offs between monolithic and microservices architectures "
    "for a high-throughput fintech payment system. Consider latency, consistency, "
    "deployment velocity, and operational cost."
)

# All budget presets across every method
BUDGET_PRESETS = sorted(
    [pid for pid in PRESETS if pid.endswith("-budget")]
)

# A subset of budget presets for quick smoke tests
SMOKE_BUDGET_PRESETS = [
    "multi-perspective-budget",
    "iterative-critique-budget",
    "debate-budget",
    "research-budget",
]

# Shared preset service — constructs the ProviderRouter the same way the
# orchestrator does in production (PipelinePreset itself is intentionally a
# domain-pure dataclass with no build_router method).
_PRESET_SERVICE = PresetService()


def build_router(preset_id: str):
    """Build a (preset_name, router) tuple via the application-layer service.

    Mirrors the real production path (PipelineOrchestrator.preflight →
    PresetService.build_router), so an e2e failure here reflects a real
    production failure, not a test-time shortcut.
    """
    return _PRESET_SERVICE.build_router(preset_id)


class TestBudgetPresetSmoke:
    """Quick smoke tests to verify budget presets can make real API calls."""

    @pytest.mark.parametrize("preset_id", SMOKE_BUDGET_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_smoke_runs_to_completion(self, preset_id):
        _, router = build_router(preset_id)
        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(SIMPLE_PROBLEM)

        assert state.problem == SIMPLE_PROBLEM
        assert state.preset_name == preset_id
        assert state.task_type is not None
        assert state.decomposition is not None
        assert state.final_solution is not None
        assert len(state.final_solution.core_solution) > 10

        critical_errors = [e for e in state.errors if "Pipeline processing error" in e]
        assert not critical_errors, f"Critical errors for {preset_id}: {critical_errors}"


class TestBudgetPresetAdversarial:
    """Adversarial tests designed to stress budget presets."""

    @pytest.mark.parametrize("preset_id", BUDGET_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_all_budget_presets_run(self, preset_id):
        """Every budget preset should complete a simple problem."""
        _, router = build_router(preset_id)
        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(SIMPLE_PROBLEM)

        assert state.final_solution is not None
        assert state.final_solution.core_solution
        assert len(state.final_solution.core_solution) > 10

    @pytest.mark.parametrize("preset_id", ["multi-perspective-budget", "research-budget"])
    @pytest.mark.asyncio
    @pytest.mark.timeout(240)
    async def test_complex_problem_with_high_topk(self, preset_id):
        """Higher top_k with a complex problem should still complete."""
        _, router = build_router(preset_id)
        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=4,
            parallel_perspectives=True,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(COMPLEX_PROBLEM)

        assert state.final_solution is not None
        assert state.final_solution.core_solution
        critical_errors = [e for e in state.errors if "Pipeline processing error" in e]
        assert not critical_errors

    @pytest.mark.parametrize("preset_id", ["multi-perspective-budget", "debate-budget"])
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_sequential_mode(self, preset_id):
        """Sequential perspective execution should not deadlock."""
        _, router = build_router(preset_id)
        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=False,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(SIMPLE_PROBLEM)

        assert state.final_solution is not None
        assert state.final_solution.core_solution

    @pytest.mark.parametrize("preset_id", ["scientific-budget", "research-budget"])
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_academic_source_type(self, preset_id):
        """Academic source type should work for research-oriented presets."""
        _, router = build_router(preset_id)
        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
            source_type="academic",
        )
        state = await pipeline.run(SIMPLE_PROBLEM)

        assert state.final_solution is not None
        assert state.final_solution.core_solution


class TestBudgetPresetTokenTracking:
    """Verify token usage is tracked across budget presets."""

    @pytest.mark.parametrize("preset_id", SMOKE_BUDGET_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(120)
    async def test_token_usage_is_non_negative(self, preset_id):
        _, router = build_router(preset_id)
        pipeline = ReasonerPipeline(
            router=router,
            preset_name=preset_id,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
            source_type="general",
        )
        state = await pipeline.run(SIMPLE_PROBLEM)
        total = sum(t.get("total", 0) for t in state.detailed_token_usage.values())
        assert total >= 0
        assert state.detailed_token_usage


class TestBudgetPresetRouterBuilding:
    """Verify all budget preset routers can be built and described."""

    @pytest.mark.parametrize("preset_id", BUDGET_PRESETS)
    def test_all_budget_presets_build_router(self, preset_id):
        _, router = build_router(preset_id)
        desc = router.describe()
        assert "[primary]" in desc
        assert desc["[primary]"]
