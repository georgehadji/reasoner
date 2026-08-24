"""Tests for vs_decomposition stage."""
from __future__ import annotations

import pytest

from reasoner.phases.vs_decomposition import (
    DecompositionVSConfig,
    decompose_with_vs,
)
from reasoner.vs_config import VSFeatureFlags
from tests.utils.mocks import MockLLM


@pytest.fixture
def enabled_flags() -> VSFeatureFlags:
    return VSFeatureFlags()


@pytest.fixture
def disabled_flags() -> VSFeatureFlags:
    return VSFeatureFlags.all_disabled()


class TestDecomposition:
    async def test_sort_by_probability_descending(self, enabled_flags: VSFeatureFlags) -> None:
        raw = '{"candidates": [{"text": "C", "probability": 0.1}, {"text": "A", "probability": 0.9}, {"text": "B", "probability": 0.5}]}'
        llm = MockLLM(raw)
        config = DecompositionVSConfig(top_n=3)
        result = await decompose_with_vs("Q", config, llm, enabled_flags)
        assert result.sub_queries == ["A", "B", "C"]
        assert result.source == "vs"

    async def test_top_n_limits_results(self, enabled_flags: VSFeatureFlags) -> None:
        raw = '{"candidates": [{"text": "A", "probability": 0.9}, {"text": "B", "probability": 0.8}, {"text": "C", "probability": 0.7}]}'
        llm = MockLLM(raw)
        config = DecompositionVSConfig(top_n=2)
        result = await decompose_with_vs("Q", config, llm, enabled_flags)
        assert len(result.sub_queries) == 2
        assert result.sub_queries == ["A", "B"]

    async def test_validation_top_n_le_k(self) -> None:
        from reasoner.reasoner_vs_constants import VS_K_DECOMPOSITION
        with pytest.raises(ValueError):
            DecompositionVSConfig(top_n=VS_K_DECOMPOSITION + 1)

    async def test_retry_on_parse_failure_then_success(self, enabled_flags: VSFeatureFlags) -> None:
        responses = ["bad json", '{"candidates": [{"text": "OK", "probability": 1}]}']
        llm = MockLLM("")
        llm.generate.side_effect = responses
        config = DecompositionVSConfig()
        result = await decompose_with_vs("Q", config, llm, enabled_flags)
        assert result.sub_queries == ["OK"]
        assert llm.generate.await_count == 2

    async def test_final_fallback_to_direct_after_retries(self, enabled_flags: VSFeatureFlags) -> None:
        from reasoner.reasoner_vs_constants import VS_PARSE_MAX_RETRIES
        responses = ["bad json"] * (VS_PARSE_MAX_RETRIES + 1)
        llm = MockLLM("")
        llm.generate.side_effect = responses
        config = DecompositionVSConfig()
        result = await decompose_with_vs("Q", config, llm, enabled_flags)
        assert result.source == "direct"
        assert result.sub_queries == ["Q"]

    async def test_feature_flag_bypass(self, disabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM('{"candidates": []}')
        config = DecompositionVSConfig()
        result = await decompose_with_vs("Q", config, llm, disabled_flags)
        assert result.source == "direct"
        llm.generate.assert_not_awaited()

    async def test_vs_metadata_populated(self, enabled_flags: VSFeatureFlags) -> None:
        raw = '{"candidates": [{"text": "A", "probability": 1}]}'
        llm = MockLLM(raw)
        config = DecompositionVSConfig()
        result = await decompose_with_vs("Q", config, llm, enabled_flags)
        assert "k_used" in result.vs_metadata
        assert "top_n" in result.vs_metadata
