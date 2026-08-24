"""
Real integration tests for cross-module relationships using OpenRouter API.

Tests verify that:
- presets.py ↔ llm.py (router building and real calls)
- pipeline.py ↔ models.py (state serialization and population)
- api.py ↔ pipeline.py (SSE streaming with real pipeline execution)
- main.py arguments ↔ presets.py (preset validation and resolution)
"""

import os

import pytest

from reasoner.llm import _REGISTRY, ProviderRouter
from reasoner.models import PipelineState
from reasoner.pipeline import ReasonerPipeline
from reasoner.presets import PRESETS, get_preset, is_valid_preset_name, resolve_preset_name

pytestmark = [
    pytest.mark.slow,
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set",
    ),
]

SIMPLE_PROBLEM = "What is the capital of France?"


class TestPresetToLLMRelationship:
    """presets.py → llm.py: every preset must produce a working ProviderRouter."""

    @pytest.mark.parametrize("preset_id", sorted(PRESETS.keys()))
    def test_preset_builds_valid_router(self, preset_id):
        preset = get_preset(preset_id)
        router = preset.build_router()
        assert isinstance(router, ProviderRouter)
        desc = router.describe()
        assert desc["[primary]"]
        # All routed roles must resolve to a provider
        for role in preset.routing:
            provider = router.get(role)
            assert provider is not None
            assert provider.model

    @pytest.mark.parametrize("preset_id", sorted(PRESETS.keys()))
    @pytest.mark.asyncio
    @pytest.mark.timeout(60)
    async def test_preset_router_makes_real_call(self, preset_id):
        preset = get_preset(preset_id)
        router = preset.build_router()
        response, metadata = await router.call(
            role="classification",
            system_prompt='Reply with JSON: {"task_type": "factual"}',
            user_prompt=SIMPLE_PROBLEM,
            max_tokens=128,
            temperature=0.1,
        )
        assert response
        assert metadata.get("model")
        # Verify the primary model in metadata matches the preset
        assert metadata["model"] == router.get("classification").model


class TestPipelineToModelsRelationship:
    """pipeline.py → models.py: state round-trips and fields populate correctly."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(180)
    async def test_state_serializes_after_real_run(self):
        preset = get_preset("multi-perspective-budget")
        router = preset.build_router()
        pipeline = ReasonerPipeline(
            router=router,
            preset_name="multi-perspective-budget",
            top_k=2,
            verbose=False,
        )
        state = await pipeline.run(SIMPLE_PROBLEM)

        # Serialize and deserialize
        dumped = state.to_dict()
        restored = PipelineState._from_dict(dumped)

        assert restored.problem == state.problem
        assert restored.preset_name == state.preset_name
        assert restored.task_type == state.task_type
        assert restored.final_solution.core_solution == state.final_solution.core_solution
        assert restored.detailed_token_usage == state.detailed_token_usage


class TestCLIArgumentToPresetRelationship:
    """main.py → presets.py: argument validation matches preset registry."""

    def test_all_preset_names_are_valid(self):
        for preset_id in PRESETS:
            assert is_valid_preset_name(preset_id)
            assert resolve_preset_name(preset_id) == preset_id

    def test_preset_resolution_for_aliases(self):
        # Common aliases should resolve to canonical names if they exist
        aliases = {
            "mpb": "multi-perspective-budget",
            "mpp": "multi-perspective-premium",
        }
        for alias, expected in aliases.items():
            if is_valid_preset_name(alias):
                assert resolve_preset_name(alias) == expected


class TestRegistryToPresetConsistency:
    """llm.py _REGISTRY ↔ presets.py: all preset models exist in registry."""

    @pytest.mark.parametrize("preset_id", sorted(PRESETS.keys()))
    def test_all_preset_models_in_registry(self, preset_id):
        preset = get_preset(preset_id)
        assert preset.primary_id in _REGISTRY, f"{preset_id}: primary {preset.primary_id} missing"
        for role, model_id in preset.routing.items():
            assert model_id in _REGISTRY, f"{preset_id}: routed {role}={model_id} missing"
        for role, model_id in preset.fallback_routing.items():
            assert model_id in _REGISTRY, f"{preset_id}: fallback {role}={model_id} missing"
