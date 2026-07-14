"""Tests for vs_generation stage — strategy behaviors and fallback."""
from __future__ import annotations
from tests.utils.mocks import MockLLM, MockNLI

import pytest
from unittest.mock import AsyncMock

from reasoner.phases.vs_generation import (
    generate_with_vs,
    VSGenerationConfig,
    VSGenerationResult,
    GenerationStrategy,
    GenerationCandidate,
)
from reasoner.exceptions import ProviderError
from reasoner.vs_config import VSFeatureFlags, VSDeploymentProfile






@pytest.fixture
def enabled_flags() -> VSFeatureFlags:
    return VSFeatureFlags()


@pytest.fixture
def disabled_flags() -> VSFeatureFlags:
    return VSFeatureFlags.all_disabled()


CANDIDATES_JSON = '{"candidates": [{"text": "A", "probability": 0.6}, {"text": "B", "probability": 0.3}, {"text": "C", "probability": 0.1}]}'


class TestBestVerifiable:
    async def test_nli_ordering_correct(self, enabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        nli = MockNLI()
        nli.score_entailment.side_effect = [0.9, 0.5, 0.1]  # A high, B medium, C low
        config = VSGenerationConfig(strategy=GenerationStrategy.BEST_VERIFIABLE, profile=VSDeploymentProfile.MAX_ACCURACY)
        result = await generate_with_vs("Q", config, llm, nli, enabled_flags)
        assert result.selected.text == "A"
        assert result.selected.nli_score == pytest.approx(0.9)

    async def test_nli_budget_respected(self, enabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        nli = MockNLI()
        config = VSGenerationConfig(strategy=GenerationStrategy.BEST_VERIFIABLE, profile=VSDeploymentProfile.LATENCY_SENSITIVE)
        result = await generate_with_vs("Q", config, llm, nli, enabled_flags)
        # LATENCY_SENSITIVE budget = 1 NLI call
        assert nli.score_entailment.await_count == 1

    async def test_fallback_to_first_when_no_nli(self, enabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        nli = MockNLI()
        nli.score_entailment.side_effect = Exception("fail")
        config = VSGenerationConfig(strategy=GenerationStrategy.BEST_VERIFIABLE, profile=VSDeploymentProfile.LATENCY_SENSITIVE)
        result = await generate_with_vs("Q", config, llm, nli, enabled_flags)
        assert result.selected.text == "A"


class TestEnsemble:
    async def test_max_probability_wins(self, enabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        nli = MockNLI()
        config = VSGenerationConfig(strategy=GenerationStrategy.ENSEMBLE)
        result = await generate_with_vs("Q", config, llm, nli, enabled_flags)
        assert result.selected.text == "A"
        assert result.selected.probability == pytest.approx(0.6)


class TestTopProbability:
    async def test_first_candidate_by_probability(self, enabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        nli = MockNLI()
        config = VSGenerationConfig(strategy=GenerationStrategy.TOP_PROBABILITY)
        result = await generate_with_vs("Q", config, llm, nli, enabled_flags)
        assert result.selected.text == "A"


class TestFallback:
    async def test_l1_retry_on_provider_error(self, enabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        llm.generate.side_effect = [ProviderError("fail"), CANDIDATES_JSON]
        nli = MockNLI()
        config = VSGenerationConfig()
        result = await generate_with_vs("Q", config, llm, nli, enabled_flags)
        assert llm.generate.await_count == 2
        assert isinstance(result, VSGenerationResult)

    async def test_l2_simplified_prompt_on_second_failure(self, enabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        llm.generate.side_effect = [ProviderError("fail"), ProviderError("fail2"), CANDIDATES_JSON]
        nli = MockNLI()
        config = VSGenerationConfig()
        result = await generate_with_vs("Q", config, llm, nli, enabled_flags)
        assert llm.generate.await_count == 3

    async def test_l3_direct_fallback_on_third_failure(self, enabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM("Direct answer")
        llm.generate.side_effect = [ProviderError("f1"), ProviderError("f2"), ProviderError("f3"), "Direct answer"]
        nli = MockNLI()
        config = VSGenerationConfig()
        result = await generate_with_vs("Q", config, llm, nli, enabled_flags)
        assert result.selected.text == "Direct answer"
        assert result.selected.probability == 1.0


class TestFeatureFlag:
    async def test_disabled_returns_single_direct_candidate(self, disabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM("Direct output")
        nli = MockNLI()
        config = VSGenerationConfig()
        result = await generate_with_vs("Q", config, llm, nli, disabled_flags)
        assert len(result.candidates) == 1
        assert result.candidates[0].selected is True
        assert result.candidates[0].text == "Direct output"
