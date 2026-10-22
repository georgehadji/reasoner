"""HyperGate routing endpoint — POST /api/gate.

Runs HyperGate on a problem WITHOUT executing the pipeline. Lets the UI
show (or ask about) the selected reasoning method before committing to a
full run. Shares HyperGateAgent's own L1/L2 cache, so a subsequent
/api/run call for the same problem does not re-pay the HyperGate LLM cost.

Stays anonymous for the landing page, but an anonymous call costs up to five
LLM calls, so it counts against the same per-IP daily cap as an anonymous run
(docs/plans/audit-remediation-2-2026-10-20.md BIL-17).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from reasoner.api.auth_deps import require_csrf
from reasoner.api.client_ip import get_client_ip
from reasoner.api.dependencies import check_rate_limit, get_optional_user
from reasoner.api.schemas import RunRequest
from reasoner.application.services.anonymous_trial_policy import enforce_anonymous_trial_cap
from reasoner.application.services.gate_service import decide_route
from reasoner.core.constants_limits import GATE_ESTIMATED_COST_USD
from reasoner.domain.saas import User

router = APIRouter()


@router.post("/api/gate", dependencies=[Depends(check_rate_limit)])
async def gate_decision(
    req: RunRequest,
    request: Request,
    user: User | None = Depends(get_optional_user),
    csrf_checked=Depends(require_csrf),
):
    """Return HyperGate's routing decision for a problem, without running it."""
    if user is None:
        await enforce_anonymous_trial_cap(get_client_ip(request), GATE_ESTIMATED_COST_USD)
    return await decide_route(req.problem, req.preset)
