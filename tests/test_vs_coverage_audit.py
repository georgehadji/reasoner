"""Tests for vs_coverage_audit stage."""
from __future__ import annotations

import pytest

from reasoner.phases.vs_coverage_audit import (
    GapType,
    _check_overlap_with_evidence,
    audit_claim_coverage_vs,
)
from reasoner.vs_config import VSFeatureFlags
from tests.utils.mocks import MockLLM


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

    async def test_both_gap_types_coexist_in_one_audit(
        self, enabled_flags: VSFeatureFlags
    ) -> None:
        """One audit must be able to classify claims into different buckets.

        This replaces a test named `test_all_three_gap_types` whose assertion
        was `GENUINE in types or PHRASING_MISMATCH in types or COVERED in
        types or len(result.gaps) == 0`. GapType has exactly three members, so
        a non-empty `gaps` satisfied one of the first three and an empty one
        satisfied the fourth: the assertion could not fail. Its inputs in fact
        produced `gaps == []`, exercising none of the three.

        Three claims against one evidence sentence of five words:
          - "zeta eta"          -> 0/2 overlap  -> GENUINE
          - "alpha beta zeta"   -> 2/3 = 0.67   -> PHRASING_MISMATCH
          - "alpha beta gamma"  -> 3/3 = 1.0    -> no gap recorded
        """
        responses = [
            '{"candidates": [{"text": "zeta eta", "probability": 1}]}',
            '{"candidates": [{"text": "alpha beta zeta", "probability": 1}]}',
            '{"candidates": [{"text": "alpha beta gamma", "probability": 1}]}',
        ]
        llm = MockLLM("")
        llm.generate.side_effect = responses
        claims = ["claim one", "claim two", "claim three"]
        evidence = ["alpha beta gamma delta epsilon"]

        result = await audit_claim_coverage_vs(claims, evidence, llm, enabled_flags)

        assert {g[1] for g in result.gaps} == {
            GapType.GENUINE,
            GapType.PHRASING_MISMATCH,
        }
        assert result.gaps[0] == ("claim one", GapType.GENUINE)
        assert result.gaps[1] == ("claim two", GapType.PHRASING_MISMATCH)
        # Only GENUINE gaps reduce coverage: 1 of 3 claims.
        assert result.coverage_ratio == pytest.approx(2 / 3)

    async def test_covered_is_never_emitted_as_a_gap(
        self, enabled_flags: VSFeatureFlags
    ) -> None:
        """GapType.COVERED is unreachable, and that is the intended design.

        audit_claim_coverage_vs branches only on `overlap < 0.5` (GENUINE) and
        `overlap < 0.9` (PHRASING_MISMATCH); a fully covered claim appends
        nothing, because a covered claim is not a gap. Pinned so that the
        unused enum member is a documented fact rather than a loose end that
        invites someone to "fix" the audit by emitting it.
        """
        llm = MockLLM('{"candidates": [{"text": "alpha beta gamma", "probability": 1}]}')

        result = await audit_claim_coverage_vs(
            ["fully covered claim"], ["alpha beta gamma"], llm, enabled_flags
        )

        assert result.gaps == []
        assert GapType.COVERED not in {g[1] for g in result.gaps}

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
