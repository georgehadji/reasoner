"""Tests for vs_calibration stage."""
from __future__ import annotations

import math

import pytest

from reasoner.phases.vs_calibration import (
    compute_vs_calibrated_confidence,
    extract_calibration_signals,
    VSCalibrationSignals,
)
from reasoner.phases.vs_generation import VSGenerationResult, GenerationCandidate
from reasoner.reasoner_verbalized_sampling import VSCandidate, compute_verbalized_entropy
from reasoner.reasoner_vs_constants import W_ENTROPY, W_SUPPORT, W_NLI, W_RANK
from reasoner.vs_config import VSFeatureFlags


class TestComputeVerbalizedEntropy:
    def test_uniform_distribution_entropy(self) -> None:
        candidates = [VSCandidate(text="a", probability=0.25) for _ in range(4)]
        entropy = compute_verbalized_entropy(candidates)
        assert entropy == pytest.approx(math.log(4), rel=0.01)

    def test_peaked_distribution_low_entropy(self) -> None:
        candidates = [VSCandidate(text="a", probability=0.99), VSCandidate(text="b", probability=0.01)]
        entropy = compute_verbalized_entropy(candidates)
        assert entropy < 0.1

    def test_zero_probabilities_ignored(self) -> None:
        candidates = [VSCandidate(text="a", probability=1.0), VSCandidate(text="b", probability=0.0)]
        entropy = compute_verbalized_entropy(candidates)
        assert entropy == pytest.approx(0.0, abs=0.01)


class TestCalibratedConfidence:
    def test_perfect_signals_near_one(self) -> None:
        signals = VSCalibrationSignals(entropy=0.0, support_ratio=1.0, nli_mean=1.0, rank_stability=1.0)
        conf = compute_vs_calibrated_confidence(signals)
        assert conf == pytest.approx(1.0, abs=0.01)

    def test_worst_signals_near_zero(self) -> None:
        signals = VSCalibrationSignals(entropy=1.0, support_ratio=0.0, nli_mean=0.0, rank_stability=0.0)
        conf = compute_vs_calibrated_confidence(signals)
        assert conf < 0.5

    def test_unit_interval_bounds(self) -> None:
        signals = VSCalibrationSignals(entropy=10.0, support_ratio=-5.0, nli_mean=-5.0, rank_stability=-5.0)
        conf = compute_vs_calibrated_confidence(signals)
        assert 0.0 <= conf <= 1.0

    def test_weights_sum_to_one(self) -> None:
        assert W_ENTROPY + W_SUPPORT + W_NLI + W_RANK == pytest.approx(1.0)


class TestExtractCalibrationSignals:
    async def test_feature_flag_bypass(self) -> None:
        flags = VSFeatureFlags.all_disabled()
        cand = GenerationCandidate(text="x", probability=1.0, selected=True)
        result = VSGenerationResult(candidates=[cand], selected=cand)
        signals = await extract_calibration_signals(result, flags)
        assert signals.entropy == 0.0
        assert signals.support_ratio == 1.0
        assert signals.nli_mean == 1.0
        assert signals.rank_stability == 1.0

    async def test_entropy_normalized(self) -> None:
        flags = VSFeatureFlags()
        candidates = [
            GenerationCandidate(text="a", probability=0.5, selected=False),
            GenerationCandidate(text="b", probability=0.5, selected=False),
        ]
        candidates[0].selected = True
        result = VSGenerationResult(candidates=candidates, selected=candidates[0])
        signals = await extract_calibration_signals(result, flags)
        assert 0.0 <= signals.entropy <= 1.0

    async def test_nli_mean_computed(self) -> None:
        flags = VSFeatureFlags()
        candidates = [
            GenerationCandidate(text="a", probability=0.5, nli_score=0.8, selected=False),
            GenerationCandidate(text="b", probability=0.5, nli_score=0.6, selected=False),
        ]
        candidates[0].selected = True
        result = VSGenerationResult(candidates=candidates, selected=candidates[0])
        signals = await extract_calibration_signals(result, flags)
        assert signals.nli_mean == pytest.approx(0.7, abs=0.01)

    async def test_regression_disabled_perfect_signals(self) -> None:
        flags = VSFeatureFlags.all_disabled()
        candidates = [
            GenerationCandidate(text="a", probability=0.1, selected=False),
            GenerationCandidate(text="b", probability=0.9, selected=True),
        ]
        result = VSGenerationResult(candidates=candidates, selected=candidates[1])
        signals = await extract_calibration_signals(result, flags)
        # When disabled, signals should be "perfect" defaults regardless of candidates
        assert signals.entropy == 0.0
        assert signals.nli_mean == 1.0
