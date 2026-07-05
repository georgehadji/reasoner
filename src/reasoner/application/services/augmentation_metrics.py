"""Augmentation A/B quality metrics.

When AUGMENTATION_AB_TEST=true, randomly assigns pipeline runs to
augmented vs. baseline arms and emits quality metrics through the
telemetry pipeline for later analysis.

Design:
  - 50/50 random split (deterministic by problem hash for reproducibility)
  - Lightweight: one hash + one log call per pipeline run
  - Off by default — zero overhead when disabled
  - Emits via the existing TelemetryStoreProtocol
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Public API ────────────────────────────────────────────────────────


def assign_ab_arm(problem: str, run_id: str) -> str:
    """Deterministically assign this run to 'augmented' or 'baseline' arm.

    Uses the first hex digit of sha256(problem + run_id) — even hex → augmented,
    odd → baseline. This gives an even 50/50 split and is reproducible for
    debugging (same problem + same run_id → same arm).
    """
    seed = hashlib.sha256(f"{problem}|{run_id}".encode()).hexdigest()
    return "augmented" if int(seed[0], 16) % 2 == 0 else "baseline"


def build_ab_metric(
    arm: str,
    problem: str,
    run_id: str,
    preset: str | None,
    state_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build a telemetry-ready metric payload for an A/B test run.

    Args:
        arm: 'augmented' or 'baseline'
        problem: Original user question
        run_id: Unique pipeline run identifier
        preset: Preset name used
        state_summary: Dict with keys: article_length, source_count,
                       claim_count, phase_count, total_cost_usd

    Returns:
        Dict suitable for emission via TelemetryStoreProtocol.save_run()
    """
    return {
        "experiment": "augmentation_ab_v1",
        "arm": arm,
        "problem_hash": hashlib.sha256(problem.encode()).hexdigest()[:16],
        "run_id": run_id,
        "preset": preset,
        "metrics": {
            "article_length_chars": state_summary.get("article_length", 0),
            "source_count": state_summary.get("source_count", 0),
            "claim_count": state_summary.get("claim_count", 0),
            "phase_count": state_summary.get("phase_count", 0),
            "total_cost_usd": state_summary.get("total_cost_usd", 0),
        },
    }


def should_disable_augmentation_for_ab(problem: str, run_id: str) -> bool:
    """Return True if this run is assigned to the BASELINE arm.

    When True, the orchestrator should set augmentation_methods=[]
    so the pipeline runs without pre-processing, enabling fair comparison.
    """
    from reasoner.core.settings import settings
    if not settings.AUGMENTATION_AB_TEST:
        return False
    arm = assign_ab_arm(problem, run_id)
    logger.debug("A/B test: run %s → arm '%s'", run_id, arm)
    return arm == "baseline"
