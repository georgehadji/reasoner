"""
Real end-to-end pipeline tests using actual OpenRouter API.

These tests exercise ReasonerPipeline.run() with live LLM calls.
Run with: python -m pytest tests/test_e2e_real_pipeline.py -v --run-slow
"""

import os
import pytest
import asyncio

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

METHOD_PRESETS = [
    ("multi_perspective", "multi-perspective-budget"),
    ("iterative", "iterative-budget"),
    ("debate", "debate-budget"),
    ("scientific", "scientific-budget"),
    ("socratic", "socratic-budget"),
    ("research", "research-budget"),
    ("jury", "jury-budget"),
    ("pre_mortem", "pre-mortem-budget"),
    ("bayesian", "bayesian-budget"),
    ("dialectical", "dialectical-budget"),
    ("analogical", "analogical-budget"),
    ("delphi", "delphi-budget"),
]




class TestRealPipelineMethods:
    @pytest.mark.parametrize("method, preset_id", METHOD_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_method_runs_to_completion(self, method, preset_id):
        preset = get_preset(preset_id)
        router = preset.build_router()
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
        assert state.final_solution.core_solution
        assert len(state.final_solution.core_solution) > 10

        critical_errors = [e for e in state.errors if "Pipeline processing error" in e]
        assert not critical_errors, f"Critical errors for {method}: {critical_errors}"

        # Method-specific state should be populated (may be empty if LLM returns malformed data,
        # but the attribute must exist for a completed run)
        if method == "debate":
            assert state.debate_rounds is not None
        elif method == "iterative":
            assert state.scores is not None
        elif method == "jury":
            assert state.generation_candidates is not None
        elif method == "pre_mortem":
            assert state.pre_mortem_state is not None
        elif method == "bayesian":
            assert state.bayesian_state is not None
        elif method == "dialectical":
            assert state.dialectical_state is not None
        elif method == "analogical":
            assert state.analogical_state is not None
        elif method == "delphi":
            assert state.delphi_state is not None

    @pytest.mark.parametrize("method, preset_id", METHOD_PRESETS)
    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_method_tracks_tokens(self, method, preset_id):
        preset = get_preset(preset_id)
        router = preset.build_router()
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
        assert total >= 0, f"Expected non-negative token usage for {method}"
        assert state.detailed_token_usage


class TestRealPresetRouterBuilding:
    @pytest.mark.parametrize("preset_id", sorted(PRESETS.keys()))
    def test_all_presets_build_router(self, preset_id):
        preset = get_preset(preset_id)
        router = preset.build_router()
        desc = router.describe()
        assert "[primary]" in desc
        assert desc["[primary]"]

    @pytest.mark.parametrize("preset_id", sorted(PRESETS.keys()))
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_all_presets_can_make_real_call(self, preset_id):
        preset = get_preset(preset_id)
        router = preset.build_router()
        response, metadata = await router.call(
            role="classification",
            system_prompt="You are a helpful assistant. Reply with valid JSON only.",
            user_prompt='{"task": "classify", "problem": "What is 2+2?"}',
            max_tokens=256,
            temperature=0.3,
        )
        assert response
        assert metadata.get("model")
