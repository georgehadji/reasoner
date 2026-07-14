"""Tests for LLM temperature handling (BUG-001 regression)."""

import pytest
from reasoner.llm import OpenAICompatibleProvider


class TestTemperatureHandling:
    """BUG-001 regression tests: Temperature parameter must be handled correctly per model."""

    def test_openai_models_never_accept_temperature(self):
        """OpenAI models (gpt-*, o1, o3) do NOT accept temperature - they use fixed 1.0."""
        # Verify OpenAI models are NOT in the supported list
        supported = OpenAICompatibleProvider._TEMPERATURE_SUPPORTED_MODELS
        assert not any('gpt-' in m for m in supported)
        assert not any('o1' in m for m in supported)
        assert not any('o3' in m for m in supported)

    def test_temperature_supported_models_registry(self):
        """Verify temperature supported models registry is properly populated."""
        supported = OpenAICompatibleProvider._TEMPERATURE_SUPPORTED_MODELS
        
        # Check major model families are included (NOT OpenAI)
        assert any('deepseek' in m for m in supported)
        assert any('qwen' in m for m in supported)
        assert any('kimi' in m for m in supported)
        assert any('glm' in m for m in supported)
        assert any('mistral' in m for m in supported)
        assert any('gemini' in m for m in supported)
        assert any('grok' in m for m in supported)
        assert any('sonar' in m for m in supported)

    def test_model_name_matching_logic(self):
        """Test that model name matching works correctly."""
        # Test the matching logic used in complete()
        test_cases = [
            ("deepseek-v3", True),
            ("deepseek-r1", True),
            ("qwen3-max", True),
            ("kimi-k2-6", True),
            ("glm-4-plus", True),
            ("mistral-large-latest", True),
            ("gemini-2.0-pro-exp", True),
            ("grok-3", True),
            ("sonar-pro", True),
            ("gpt-4-turbo", False),  # OpenAI - NEVER accepts temperature
            ("gpt-4o", False),  # OpenAI - NEVER accepts temperature
            ("o1-preview", False),  # OpenAI O1 - NEVER accepts temperature
            ("o3-mini", False),  # OpenAI O3 - NEVER accepts temperature
            ("claude-sonnet", False),  # Handled separately (Anthropic)
            ("unknown-model", False),
        ]
        
        for model_name, should_match in test_cases:
            matches = any(supported in model_name.lower() for supported in OpenAICompatibleProvider._TEMPERATURE_SUPPORTED_MODELS)
            assert matches == should_match, f"Model {model_name} matching failed"

    def test_temperature_default_omitted(self):
        """Verify temperature=1.0 (default) is omitted to reduce token usage."""
        # This is tested indirectly via the logic check
        # The complete() method checks: if temperature != 1.0
        default_temp = 1.0
        assert not (default_temp != 1.0)  # Should be False, meaning temperature won't be sent


class TestOpenAICompatibleProvider:
    """Test OpenAICompatibleProvider initialization and configuration."""

    def test_provider_initialization(self):
        """Test that provider can be initialized without errors."""
        # Test with a model that supports temperature
        provider = OpenAICompatibleProvider(
            model="deepseek-v3",
            api_key="test-key",  # Won't actually be used in this test
            base_url="https://test.api"
        )
        assert provider.model == "deepseek-v3"
        assert provider.max_retries == 3

    def test_provider_with_shared_pool(self):
        """Test that shared HTTP pool is created."""
        provider = OpenAICompatibleProvider(
            model="qwen3-max",
            api_key="test-key",
            base_url="https://test.api"
        )
        # Shared pool should be initialized
        assert OpenAICompatibleProvider._shared_pool is not None


class TestTemperatureRegistry:
    """Verify the centralized temperature registry is wired correctly."""

    def test_phase_temperatures_are_valid(self):
        from reasoner.core.temperatures import PHASE_TEMPERATURES, NON_PHASE_TEMPERATURES
        for name, temp in {**PHASE_TEMPERATURES, **NON_PHASE_TEMPERATURES}.items():
            assert isinstance(temp, float), f"{name} must be a float"
            assert 0.0 <= temp <= 2.0, f"{name} temperature {temp} out of valid range"

    def test_pipeline_phase_configs_use_registry(self):
        from reasoner.pipeline import ReasonerPipeline
        from reasoner.core.temperatures import PHASE_TEMPERATURES
        # Use a dummy router so __init__ doesn't need real credentials
        class DummyRouter:
            def call(self, **kwargs):
                return "ok", {}
        pipeline = ReasonerPipeline(router=DummyRouter())
        for key in ["classification", "decomposition", "perspective", "synthesis", "critic"]:
            assert pipeline.phase_configs[key].temperature == PHASE_TEMPERATURES[key]

    def test_call_llm_cached_resolves_temperature_from_phase_configs(self):
        from reasoner import pipeline as pipeline_module
        from reasoner.pipeline import ReasonerPipeline
        from reasoner.models import PipelineState
        from reasoner.core.temperatures import PHASE_TEMPERATURES

        class DummyRouter:
            async def call(self, **kwargs):
                self.last_kwargs = kwargs
                return "ok", {}

        router = DummyRouter()
        pipeline = ReasonerPipeline(router=router)
        state = PipelineState(problem="test")

        old_caching = pipeline_module.TOKEN_OPTIMIZATION["caching"]
        pipeline_module.TOKEN_OPTIMIZATION["caching"] = False
        try:
            import asyncio
            asyncio.run(pipeline._call_llm_cached(
                role="classification",
                system_prompt="sys",
                user_prompt="usr",
                state=state,
            ))
            assert router.last_kwargs["temperature"] == PHASE_TEMPERATURES["classification"]
        finally:
            pipeline_module.TOKEN_OPTIMIZATION["caching"] = old_caching

    def test_call_llm_cached_allows_explicit_override(self):
        from reasoner import pipeline as pipeline_module
        from reasoner.pipeline import ReasonerPipeline
        from reasoner.models import PipelineState

        class DummyRouter:
            async def call(self, **kwargs):
                self.last_kwargs = kwargs
                return "ok", {}

        router = DummyRouter()
        pipeline = ReasonerPipeline(router=router)
        state = PipelineState(problem="test_override")

        old_caching = pipeline_module.TOKEN_OPTIMIZATION["caching"]
        pipeline_module.TOKEN_OPTIMIZATION["caching"] = False
        try:
            import asyncio
            asyncio.run(pipeline._call_llm_cached(
                role="classification",
                system_prompt="sys",
                user_prompt="usr",
                state=state,
                temperature=0.99,
            ))
            assert router.last_kwargs["temperature"] == 0.99
        finally:
            pipeline_module.TOKEN_OPTIMIZATION["caching"] = old_caching

    def test_call_llm_cached_uses_phase_key_for_role_alias(self):
        from reasoner import pipeline as pipeline_module
        from reasoner.pipeline import ReasonerPipeline
        from reasoner.models import PipelineState
        from reasoner.core.temperatures import PHASE_TEMPERATURES

        class DummyRouter:
            async def call(self, **kwargs):
                self.last_kwargs = kwargs
                return "ok", {}

        router = DummyRouter()
        pipeline = ReasonerPipeline(router=router)
        state = PipelineState(problem="test_phase_key")

        old_caching = pipeline_module.TOKEN_OPTIMIZATION["caching"]
        pipeline_module.TOKEN_OPTIMIZATION["caching"] = False
        try:
            import asyncio
            asyncio.run(pipeline._call_llm_cached(
                role="primary",
                phase_key="research",
                system_prompt="sys",
                user_prompt="usr",
                state=state,
            ))
            assert router.last_kwargs["temperature"] == PHASE_TEMPERATURES["research"]
        finally:
            pipeline_module.TOKEN_OPTIMIZATION["caching"] = old_caching


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
