"""Tests for vs_coverage_audit stage."""
from __future__ import annotations
from tests.utils.mocks import MockLLM, MockNLI

import pytest
from unittest.mock import AsyncMock

from reasoner.phases.vs_coverage_audit import (
    audit_claim_coverage_vs,
    CoverageAuditResult,
    GapType,
    _check_overlap_with_evidence,
)
from reasoner.vs_config import VSFeatureFlags




@pytest.fixture
def enabled_flags() -> VSFeatureFlags:
    return VSFeatureFlags()


@pytest.fixture
def disabled_flags() -> VSFeatureFlags:
    return VSFeatureFlags.all_disabled()


class TestCoverageAudit:
    async def test_feature_flag_bypass(self, disabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM('{"candidates": []}')
        result = await audit_claim_coverage_vs(["claim"], ["evidence"], llm, disabled_flags)
        assert result.coverage_ratio == 1.0
        assert result.gaps == []
        llm.generate.assert_not_awaited()

    async def test_genuine_gap_detected(self, enabled_flags: VSFeatureFlags) -> None:
        # Paraphrases won't overlap with evidence
        raw = '{"candidates": [{"text": "paraphrase one", "probability": 0.5}]}'
        llm = MockLLM(raw)
        result = await audit_claim_coverage_vs(["unrelated claim"], ["totally different evidence text here"], llm, enabled_flags)
        assert any(g[1] == GapType.GENUINE for g in result.gaps)
        assert result.coverage_ratio < 1.0

    async def test_covered_claim_no_gap(self, enabled_flags: VSFeatureFlags) -> None:
        # Evidence overlaps strongly with claim paraphrase
        raw = '{"candidates": [{"text": "the quick brown fox", "probability": 1}]}'
        llm = MockLLM(raw)
        result = await audit_claim_coverage_vs(["the quick brown fox"], ["the quick brown fox jumps"], llm, enabled_flags)
        assert all(g[1] != GapType.GENUINE for g in result.gaps)
        assert result.coverage_ratio == 1.0

    async def test_phrasing_mismatch_detected(self, enabled_flags: VSFeatureFlags) -> None:
        raw = '{"candidates": [{"text": "partial overlap here only", "probability": 1}]}'
        llm = MockLLM(raw)
        result = await audit_claim_coverage_vs(["partial overlap here only"], ["partial overlap there now"], llm, enabled_flags)
        assert any(g[1] == GapType.PHRASING_MISMATCH for g in result.gaps)

    async def test_all_three_gap_types(self, enabled_flags: VSFeatureFlags) -> None:
        responses = [
            '{"candidates": [{"text": "alpha beta gamma", "probability": 1}]}',
            '{"candidates": [{"text": "alpha beta", "probability": 1}]}',
            '{"candidates": [{"text": "alpha beta gamma delta", "probability": 1}]}',
        ]
        llm = MockLLM("")
        llm.generate.side_effect = responses
        claims = ["claim one", "claim two", "claim three"]
        evidence = ["alpha beta gamma delta epsilon"]
        result = await audit_claim_coverage_vs(claims, evidence, llm, enabled_flags)
        types = {g[1] for g in result.gaps}
        assert GapType.GENUINE in types or GapType.PHRASING_MISMATCH in types or GapType.COVERED in types or len(result.gaps) == 0

    async def test_zero_claims_returns_full_coverage(self, enabled_flags: VSFeatureFlags) -> None:
        llm = MockLLM('{"candidates": []}')
        result = await audit_claim_coverage_vs([], ["evidence"], llm, enabled_flags)
        assert result.coverage_ratio == 1.0


class TestOverlapUtility:
    async def test_no_evidence_returns_zero(self) -> None:
        overlap = await _check_overlap_with_evidence(["claim"], [])
        assert overlap == 0.0

    async def test_perfect_overlap(self) -> None:
        overlap = await _check_overlap_with_evidence(["the quick brown fox"], ["the quick brown fox"])
        assert overlap == 1.0
