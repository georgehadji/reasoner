"""HyperGate routing endpoint — POST /api/gate.

Runs HyperGate on a problem WITHOUT executing the pipeline. Lets the UI
show (or ask about) the selected reasoning method before committing to a
full run. Shares HyperGateAgent's own L1/L2 cache, so a subsequent
/api/run call for the same problem does not re-pay the HyperGate LLM cost.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from reasoner.api.auth_deps import require_csrf
from reasoner.api.schemas import RunRequest
from reasoner.application.services.gate_service import decide_route

router = APIRouter()


@router.post("/api/gate")
async def gate_decision(
    req: RunRequest,
    csrf_checked=Depends(require_csrf),
):
    """Return HyperGate's routing decision for a problem, without running it."""
    return await decide_route(req.problem, req.preset)
