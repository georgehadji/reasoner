"""Cost estimate endpoint — POST /api/estimate.

Estimates tokens, cost, and duration for a pipeline run without executing it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from reasoner.api.auth_deps import require_csrf
from reasoner.api.schemas import RunRequest
from reasoner.application.services.estimate_service import estimate_cost as _estimate_cost

router = APIRouter()


@router.post("/api/estimate")
async def estimate_cost(
    req: RunRequest,
    csrf_checked=Depends(require_csrf),
):
    """Estimate tokens, cost, and duration for a pipeline run."""
    return await _estimate_cost(req.problem, req.preset)
