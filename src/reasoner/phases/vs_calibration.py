"""VS Calibration stage — OutputCalibrationStage."""
from __future__ import annotations

import math

from pydantic import BaseModel

from reasoner.phases.vs_generation import VSGenerationResult
from reasoner.reasoner_verbalized_sampling import VSCandidate
from reasoner.reasoner_verbalized_sampling import compute_verbalized_entropy as _compute_entropy
from reasoner.reasoner_vs_constants import (
    W_ENTROPY,
    W_NLI,
    W_RANK,
    W_SUPPORT,
)
from reasoner.vs_config import VSFeatureFlags


class VSCalibrationSignals(BaseModel):
    entropy: float
    support_ratio: float
    nli_mean: float
    rank_stability: float


def compute_vs_calibrated_confidence(signals: VSCalibrationSignals) -> float:
    """Weighted calibration score in [0, 1]."""
    raw = (
        W_ENTROPY * (1.0 - min(signals.entropy, 1.0)) +
        W_SUPPORT * min(max(signals.support_ratio, 0.0), 1.0) +
        W_NLI * min(max(signals.nli_mean, 0.0), 1.0) +
        W_RANK * min(max(signals.rank_stability, 0.0), 1.0)
    )
    return float(min(max(raw, 0.0), 1.0))


async def extract_calibration_signals(
    generation_result: VSGenerationResult,
    flags: VSFeatureFlags,
) -> VSCalibrationSignals:
    if not flags.calibration:
        return VSCalibrationSignals(
            entropy=0.0,
            support_ratio=1.0,
            nli_mean=1.0,
            rank_stability=1.0,
        )

    candidates = [
        VSCandidate(text=c.text, probability=c.probability)
        for c in generation_result.candidates
    ]
    entropy = _compute_entropy(candidates)
    # Normalize entropy to [0,1] using max entropy = ln(k)
    k = len(candidates)
    normalized_entropy = entropy / math.log(k) if k > 1 else 0.0

    nli_scores = [c.nli_score or 0.0 for c in generation_result.candidates]
    nli_mean = sum(nli_scores) / len(nli_scores) if nli_scores else 0.0

    return VSCalibrationSignals(
        entropy=normalized_entropy,
        support_ratio=1.0,
        nli_mean=nli_mean,
        rank_stability=1.0,
    )
