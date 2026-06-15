"""EvolutionAgent — orchestrates the five-stage evolution loop (#4).

Paper grounding: §3.5.2 (observe→diagnose→propose→evaluate→promote).

Invoked by run_healing.py (CI cron) — NEVER inline in a user request.
Mutations target declarative config only; never mutate live state.

Five governed stages:
  1. Observe — consume HarnessScorecard over a window
  2. Diagnose — rank harness components by waste/failure
  3. Propose — emit HarnessMutation change-contracts with invariants
  4. Evaluate — replay against held-out problems (or heuristic eval)
  5. Promote — regression-free wins, auditable, HITL for cost/safety
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from reasoner.core.evolution_constants import EVOLUTION_MAX_MUTATIONS_PER_RUN
from reasoner.domain.harness_metrics import (
    HarnessMutation,
    HarnessScorecard,
    PromotionRecord,
)

logger = logging.getLogger(__name__)


class EvolutionAgent:
    """Orchestrates the five-stage harness evolution loop.

    Usage (from run_healing.py CI cron):
        agent = EvolutionAgent()
        results = await agent.evolve(window_days=7)
        # results is a list of PromotionRecords (promoted or rejected)
    """

    def __init__(self) -> None:
        self._scorecard = None
        self._diagnosis = None
        self._guard = None
        self._replay = None
        self._promotion = None

    def _lazy_init(self) -> None:
        """Lazy-init all services to avoid circular imports at module level."""
        from reasoner.application.services.scorecard_service import ScorecardService
        from reasoner.application.services.harness_diagnosis import HarnessDiagnosisService
        from reasoner.application.services.harness_guard import check_mutation_invariants
        from reasoner.application.services.harness_replay import HarnessReplayService
        from reasoner.application.services.promotion_service import PromotionService

        self._scorecard = ScorecardService()
        self._diagnosis = HarnessDiagnosisService()
        self._guard = check_mutation_invariants
        self._replay = HarnessReplayService(scorecard_service=self._scorecard)
        self._promotion = PromotionService()

    async def evolve(
        self,
        window_days: int = 7,
        max_mutations: int = EVOLUTION_MAX_MUTATIONS_PER_RUN,
    ) -> list[PromotionRecord]:
        """Execute the full five-stage evolution loop.

        Args:
            window_days: Days of telemetry to analyse.
            max_mutations: Maximum mutations to attempt per run.

        Returns:
            List of PromotionRecords — one per mutation attempt.
        """
        self._lazy_init()

        # ── Stage 1: Observe ──
        logger.info("Evolution stage 1/5: Observing telemetry (%d days)", window_days)
        scorecard = await self._scorecard.get_scorecard(window_days=window_days)
        if not scorecard.presets:
            logger.info("No telemetry data available — skipping evolution")
            return []

        # ── Stage 2: Diagnose ──
        logger.info("Evolution stage 2/5: Diagnosing harness waste")
        report = self._diagnosis.diagnose(scorecard)
        if not report.has_findings:
            logger.info("No harness issues diagnosed — nothing to evolve")
            return []

        # ── Stage 3: Propose ──
        logger.info("Evolution stage 3/5: Proposing mutations (%d findings)", len(report.findings))
        mutations = self._propose_mutations(report, max_mutations)
        if not mutations:
            logger.info("No viable mutations proposed")
            return []

        # ── Stage 4: Evaluate ──
        logger.info("Evolution stage 4/5: Evaluating %d mutations", len(mutations))
        results = []
        for mutation in mutations:
            result = await self._replay.evaluate(mutation, window_days=window_days)
            results.append((mutation, result))

        # ── Stage 5: Promote ──
        logger.info("Evolution stage 5/5: Promoting regression-free wins")
        records: list[PromotionRecord] = []
        for mutation, result in results:
            record = await self._promotion.attempt_promotion(mutation, result)
            if record.status == "promoted":
                logger.info("PROMOTED: %s (%s)", record.mutation.target, record.status)
            elif record.status == "requires_human_approval":
                logger.warning(
                    "HITL REQUIRED: %s (risk_tier=%s)",
                    record.mutation.target,
                    record.mutation.risk_tier,
                )
            else:
                logger.info("REJECTED: %s (%s)", record.mutation.target, record.status)
            records.append(record)

        return records

    def _propose_mutations(self, report, max_mutations: int) -> list[HarnessMutation]:
        """Generate HarnessMutations from diagnosis findings."""
        mutations: list[HarnessMutation] = []

        for finding in report.findings[:max_mutations]:
            target = f"preset:{finding.preset}.{finding.phase}" if finding.phase else f"preset:{finding.preset}"

            risk_tier = "safe"
            if finding.metric == "cost":
                risk_tier = "cost"
            elif finding.metric == "latency" and finding.severity == "high":
                risk_tier = "safety"

            mutations.append(HarnessMutation(
                target=target,
                component="preset" if finding.preset else "routing",
                failure_mode=f"{finding.metric}_issue",
                predicted_effect=f"Resolve {finding.metric} issue: {finding.suggestion[:80]}",
                invariant_preserved="cross-lab diversity maintained",
                rollback=f"Revert preset {finding.preset} to previous routing config",
                risk_tier=risk_tier,
            ))

        return mutations
