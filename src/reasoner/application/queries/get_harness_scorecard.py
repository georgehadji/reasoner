"""GetHarnessScorecardQuery — CQRS read query for harness-level metrics.

A read-only query that returns a HarnessScorecard without side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reasoner.application.services.scorecard_service import ScorecardService
from reasoner.domain.harness_metrics import HarnessScorecard


@dataclass
class GetHarnessScorecardQuery:
    """Query to retrieve harness scorecard metrics.

    Args:
        window_days: Number of days of telemetry to aggregate. Default 7.
    """
    window_days: int = 7


async def handle_get_harness_scorecard(
    query: GetHarnessScorecardQuery,
) -> HarnessScorecard:
    """Handle GetHarnessScorecardQuery — delegates to ScorecardService."""
    service = ScorecardService()
    return await service.get_scorecard(window_days=query.window_days)
