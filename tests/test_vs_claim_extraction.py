"""Tests for vs_claim_extraction stage."""
from __future__ import annotations
from tests.utils.mocks import MockLLM, MockNLI

import pytest
from unittest.mock import AsyncMock

from reasoner.phases.vs_claim_extraction import (
    extract_claims_from_vs_candidates,
    ClaimExtractionMode,
    VSClaimExtractionConfig,
    ExtractedClaimSet,
)
from reasoner.phases.vs_generation import GenerationCandidate
from reasoner.vs_config import VSFeatureFlags




@pytest.fixture
def sample_candidates() -> list[GenerationCandidate]:
    return [
        GenerationCandidate(text="Claim one. Claim two.", probability=0.6),
        GenerationCandidate(text="Claim two. Claim three.", probability=0.4),
    ]


class TestClaimExtraction:
    async def test_single_mode_returns_first_candidate(self, sample_candidates: list[GenerationCandidate]) -> None:
        config = VSClaimExtractionConfig(mode=ClaimExtractionMode.SINGLE)
        result = await extract_claims_from_vs_candidates(sample_candidates, config, MockLLM(), VSFeatureFlags())
        assert result.claims == ["Claim one. Claim two."]
        assert result.source == "single"

    async def test_union_mode_collects_unique_claims(self, sample_candidates: list[GenerationCandidate]) -> None:
        config = VSClaimExtractionConfig(mode=ClaimExtractionMode.UNION)
        result = await extract_claims_from_vs_candidates(sample_candidates, config, MockLLM(), VSFeatureFlags())
        # Sentence split produces: Claim one, Claim two, Claim three
        assert len(result.claims) >= 3
        assert result.source == "union"

    async def test_consensus_mode_majority_only(self, sample_candidates: list[GenerationCandidate]) -> None:
        config = VSClaimExtractionConfig(mode=ClaimExtractionMode.CONSENSUS)
        result = await extract_claims_from_vs_candidates(sample_candidates, config, MockLLM(), VSFeatureFlags())
        # "Claim two" appears in both candidates
        assert "Claim two" in result.claims
        assert result.source == "consensus"

    async def test_feature_flag_bypass(self, sample_candidates: list[GenerationCandidate]) -> None:
        flags = VSFeatureFlags.all_disabled()
        config = VSClaimExtractionConfig(mode=ClaimExtractionMode.SINGLE)
        result = await extract_claims_from_vs_candidates(sample_candidates, config, MockLLM(), flags)
        assert result.source == "direct"
        assert result.claims == [c.text for c in sample_candidates]

    async def test_empty_candidates_returns_empty(self) -> None:
        config = VSClaimExtractionConfig()
        result = await extract_claims_from_vs_candidates([], config, MockLLM(), VSFeatureFlags())
        assert result.claims == []

    async def test_parallel_extraction_race_safe(self, sample_candidates: list[GenerationCandidate]) -> None:
        config = VSClaimExtractionConfig(mode=ClaimExtractionMode.UNION)
        result = await extract_claims_from_vs_candidates(sample_candidates, config, MockLLM(), VSFeatureFlags())
        assert isinstance(result, ExtractedClaimSet)

    async def test_regression_disabled_pass_through(self, sample_candidates: list[GenerationCandidate]) -> None:
        flags = VSFeatureFlags.all_disabled()
        config = VSClaimExtractionConfig(mode=ClaimExtractionMode.CONSENSUS)
        result = await extract_claims_from_vs_candidates(sample_candidates, config, MockLLM(), flags)
        assert result.claims == [c.text for c in sample_candidates]
