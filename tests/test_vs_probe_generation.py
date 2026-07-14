"""Tests for vs_probe_generation stage."""
from __future__ import annotations
from tests.utils.mocks import MockLLM, MockNLI

import pytest
from unittest.mock import AsyncMock

from reasoner.phases.vs_probe_generation import (
    generate_probes_with_vs,
    ProbeGenerationConfig,
    ProbeSet,
    DOMAIN_PROBE_TEMPLATES,
    _semantic_distance,
)
from reasoner.reasoner_verbalized_sampling import VSMode
from reasoner.vs_config import VSFeatureFlags




@pytest.fixture
def enabled_flags() -> VSFeatureFlags:
    return VSFeatureFlags()


@pytest.fixture
def disabled_flags() -> VSFeatureFlags:
    return VSFeatureFlags.all_disabled()


class TestSemanticDistance:
    def test_identical_strings_distance_zero(self) -> None:
        assert _semantic_distance("hello", "hello") == pytest.approx(0.0, abs=0.01)

    def test_completely_different_distance_near_one(self) -> None:
        assert _semantic_distance("abc", "xyz") > 0.8


class TestTemplateRendering:
    def test_radiology_template_contains_radiologist(self) -> None:
        tpl = DOMAIN_PROBE_TEMPLATES["radiology"]
        assert "radiologist" in tpl.lower()

    def test_legal_template_contains_legal(self) -> None:
        tpl = DOMAIN_PROBE_TEMPLATES["legal"]
        assert "legal" in tpl.lower()

    def test_aerospace_template_contains_engineer(self) -> None:
        tpl = DOMAIN_PROBE_TEMPLATES["aerospace"]
        assert "engineer" in tpl.lower()


class TestProbeGeneration:
    async def test_feature_flag_bypass_returns_direct(self, disabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM('{"candidates": []}')
        config = ProbeGenerationConfig()
        result = await generate_probes_with_vs("What is AI?", config, llm, disabled_flags)
        assert result.source == "direct"
        assert result.probes == ["What is AI?"]
        llm.generate.assert_not_awaited()

    async def test_identity_filter_removes_duplicates(self, enabled_flags: VSFeatureFlags) -> None:
        raw = '{"candidates": [{"text": "What is AI?", "probability": 0.5}, {"text": "Different", "probability": 0.5}]}'
        llm = MockLLM(raw)
        config = ProbeGenerationConfig()
        result = await generate_probes_with_vs("What is AI?", config, llm, enabled_flags)
        assert "What is AI?" not in result.probes
        assert "Different" in result.probes

    async def test_fallback_to_standard_when_too_few_probes(self, enabled_flags: VSFeatureFlags) -> None:
        # First call returns only duplicates; second call (STANDARD) returns valid ones
        responses = [
            '{"candidates": [{"text": "What is AI?", "probability": 1}]}',
            '{"candidates": [{"text": "Probe A", "probability": 0.5}, {"text": "Probe B", "probability": 0.5}]}',
        ]
        llm = MockLLM("")
        llm.generate.side_effect = responses
        config = ProbeGenerationConfig()
        result = await generate_probes_with_vs("What is AI?", config, llm, enabled_flags)
        assert len(result.probes) >= 2
        assert result.source == "vs_tail"

    async def test_tail_threshold_filtering(self, enabled_flags: VSFeatureFlags) -> None:
        raw = '{"candidates": [{"text": "Very different probe here", "probability": 0.5}]}'
        llm = MockLLM(raw)
        config = ProbeGenerationConfig()
        result = await generate_probes_with_vs("AI", config, llm, enabled_flags)
        assert all(_semantic_distance(p, "AI") >= 0.15 for p in result.probes)

    async def test_vs_metadata_populated(self, enabled_flags: VSFeatureFlags) -> None:
        raw = '{"candidates": [{"text": "Probe 1", "probability": 1}]}'
        llm = MockLLM(raw)
        config = ProbeGenerationConfig(domain="radiology")
        result = await generate_probes_with_vs("Q", config, llm, enabled_flags)
        assert "vs_probe_domain" in result.vs_metadata
        assert "vs_probe_count" in result.vs_metadata

    async def test_regression_disabled_identical_to_pre_vs(self, disabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM('{"candidates": []}')
        config = ProbeGenerationConfig()
        result = await generate_probes_with_vs("Q", config, llm, disabled_flags)
        assert result == ProbeSet(probes=["Q"], source="direct")
