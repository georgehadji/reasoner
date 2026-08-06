"""Telemetry API routes — read-only harness metrics."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from reasoner.application.handlers import (
    GetHarnessScorecardQuery,
    handle_get_harness_scorecard,
)
from reasoner.api.auth_deps import optional_auth
from reasoner.domain.saas import User

router = APIRouter()


@router.get("/api/telemetry/scorecard")
async def get_scorecard(
    window_days: int = Query(default=7, ge=1, le=365, description="Days of telemetry to aggregate"),
    user: User | None = Depends(optional_auth),
) -> dict:
    """Return harness-level scorecard metrics for the last N days.

    Read-only aggregate telemetry: cost, duration, quality pass rate,
    fallback rate per preset/phase. No PII, no run-level detail.
    """
    try:
        query = GetHarnessScorecardQuery(window_days=window_days)
        scorecard = await handle_get_harness_scorecard(query)
        return scorecard.to_dict()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Scorecard unavailable: {exc}",
        ) from exc
