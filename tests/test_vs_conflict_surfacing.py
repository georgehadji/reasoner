"""Tests for vs_conflict_surfacing stage."""
from __future__ import annotations
from tests.utils.mocks import MockLLM, MockNLI

import pytest
from unittest.mock import AsyncMock

from reasoner.phases.vs_conflict_surfacing import (
    surface_cross_candidate_conflicts,
    CrossCandidateConflict,
)
from reasoner.phases.vs_generation import GenerationCandidate
from reasoner.vs_config import VSFeatureFlags




@pytest.fixture
def sample_candidates() -> list[GenerationCandidate]:
    return [
        GenerationCandidate(text="The sky is blue. Water is wet.", probability=0.7),
        GenerationCandidate(text="The sky is green. Water is wet.", probability=0.3),
    ]


class TestConflictSurfacing:
    async def test_feature_flag_bypass(self, sample_candidates: list[GenerationCandidate]) -> None:
        result = await surface_cross_candidate_conflicts(sample_candidates, MockNLI(), VSFeatureFlags.all_disabled())
        assert result == []

    async def test_empty_candidates(self) -> None:
        result = await surface_cross_candidate_conflicts([], MockNLI(), VSFeatureFlags())
        assert result == []

    async def test_recommendation_types(self, sample_candidates: list[GenerationCandidate]) -> None:
        # Low NLI scores trigger contradictions for all claims
        nli = MockNLI([0.1, 0.1, 0.1, 0.1])
        result = await surface_cross_candidate_conflicts(sample_candidates, nli, VSFeatureFlags())
        recs = {c.recommendation for c in result}
        assert len(recs) > 0
        assert all(r in {"HUMAN_REVIEW", "FLAG", "MONITOR"} for r in recs)

    async def test_sorted_by_priority_then_support(self, sample_candidates: list[GenerationCandidate]) -> None:
        nli = MockNLI([0.1, 0.1, 0.1, 0.1])
        result = await surface_cross_candidate_conflicts(sample_candidates, nli, VSFeatureFlags())
        for i in range(len(result) - 1):
            a, b = result[i], result[i + 1]
            assert (a.conflict_priority, a.support_ratio) >= (b.conflict_priority, b.support_ratio)

    async def test_zero_llm_calls(self, sample_candidates: list[GenerationCandidate]) -> None:
        nli = MockNLI([0.1])
        # _extract_claims is called with llm_client=None, so no LLM calls
        result = await surface_cross_candidate_conflicts(sample_candidates, nli, VSFeatureFlags())
        # Just verify it runs without needing an LLM mock
        assert isinstance(result, list)

    async def test_regression_disabled_empty_list(self, sample_candidates: list[GenerationCandidate]) -> None:
        result = await surface_cross_candidate_conflicts(sample_candidates, MockNLI(), VSFeatureFlags.all_disabled())
        assert result == []
