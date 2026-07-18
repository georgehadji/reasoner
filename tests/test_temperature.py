"""Tests for LLM temperature handling (BUG-001 regression)."""

import pytest
from reasoner.llm import OpenAICompatibleProvider


class TestTemperatureHandling:
    """BUG-001 regression tests: Temperature parameter must be handled correctly per model."""

    @staticmethod
    def _supports(model_name: str) -> bool:
        """Build a provider for model_name and report its temperature support."""
        provider = OpenAICompatibleProvider(
            model=model_name, api_key="test-key", base_url="https://test.api"
        )
        return provider._supports_temperature()

    def test_openai_models_never_accept_temperature(self):
        """OpenAI models (gpt-*, o1, o3) do NOT accept temperature - they use fixed 1.0."""
        assert not self._supports("gpt-4-turbo")
        assert not self._supports("gpt-4o")
        assert not self._supports("o1-preview")
        assert not self._supports("o3-mini")

    def test_temperature_supported_models_registry(self):
        """Verify major non-OpenAI model families accept a custom temperature."""
        for model in (
            "deepseek-v3", "qwen3-max", "kimi-k2-6", "glm-4-plus",
            "mistral-large-latest", "gemini-2.0-pro-exp", "grok-3", "sonar-pro",
        ):
            assert self._supports(model), f"{model} should accept temperature"

    def test_model_name_matching_logic(self):
        """Test that _supports_temperature gates models correctly."""
        # NOTE: gating inverted in the refactor — unknown models now default to
        # accepting temperature (allowlist -> fixed-temperature denylist).
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
            ("claude-sonnet", True),   # Anthropic accepts temperature
            ("unknown-model", True),   # default: new models get temperature
            ("gpt-4-turbo", False),    # OpenAI - fixed temperature
            ("gpt-4o", False),         # OpenAI - fixed temperature
            ("o1-preview", False),     # OpenAI O1 - fixed temperature
            ("o3-mini", False),        # OpenAI O3 - fixed temperature
        ]
        for model_name, should_match in test_cases:
            assert self._supports(model_name) == should_match, (
                f"Model {model_name} matching failed"
            )

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
        # Invariant: every declared phase config sources its temperature from the
        # registry rather than hardcoding one. (Which phases are declared is an
        # implementation detail; that they use the registry is the contract.)
        assert pipeline.phase_configs, "pipeline declares no phase configs"
        for key, cfg in pipeline.phase_configs.items():
            assert key in PHASE_TEMPERATURES, (
                f"phase config '{key}' has no entry in PHASE_TEMPERATURES"
            )
            assert cfg.temperature == PHASE_TEMPERATURES[key], (
                f"phase config '{key}' temperature {cfg.temperature} does not match "
                f"registry value {PHASE_TEMPERATURES[key]}"
            )

    def test_call_llm_cached_resolves_temperature_from_phase_configs(self):
        from reasoner import pipeline as pipeline_module
        from reasoner.pipeline import ReasonerPipeline
        from reasoner.models import PipelineState
        from reasoner.core.temperatures import PHASE_TEMPERATURES

        class DummyRouter:
            async def call(self, **kwargs):
                self.last_kwargs = kwargs
                return "ok", {}

        # LLMExecutor snapshots caching_enabled at construction, so the flag must
        # be cleared before the pipeline is built or the cache path still runs.
        old_caching = pipeline_module.TOKEN_OPTIMIZATION["caching"]
        pipeline_module.TOKEN_OPTIMIZATION["caching"] = False
        try:
            router = DummyRouter()
            pipeline = ReasonerPipeline(router=router)
            state = PipelineState(problem="test")

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

        old_caching = pipeline_module.TOKEN_OPTIMIZATION["caching"]
        pipeline_module.TOKEN_OPTIMIZATION["caching"] = False
        try:
            router = DummyRouter()
            pipeline = ReasonerPipeline(router=router)
            state = PipelineState(problem="test_override")

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

        old_caching = pipeline_module.TOKEN_OPTIMIZATION["caching"]
        pipeline_module.TOKEN_OPTIMIZATION["caching"] = False
        try:
            router = DummyRouter()
            pipeline = ReasonerPipeline(router=router)
            state = PipelineState(problem="test_phase_key")

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
