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
from reasoner.application.services.preset_service import PresetService
from reasoner.core.constants import HYPERGATE_METHOD_THRESHOLD
from reasoner.domain.preset_core import build_auto_preset
from reasoner.hypergate import HyperGateAgent
from reasoner.presets import get_preset_price_tier

router = APIRouter()


@router.post("/api/gate")
async def gate_decision(
    req: RunRequest,
    csrf_checked=Depends(require_csrf),
):
    """Return HyperGate's routing decision for a problem, without running it.

    Each candidate (top pick + alternatives) is resolved to a concrete preset
    name via build_auto_preset(), so the client can re-submit /api/run with
    that preset + force_pipeline=true to lock in a specific method without
    re-invoking HyperGate.
    """
    preset_service = PresetService()
    raw_preset = req.preset or "auto-budget"
    gate_preset_name, is_auto, auto_tier = preset_service.resolve(raw_preset)
    tier = auto_tier if is_auto else get_preset_price_tier(gate_preset_name)
    _effective_preset_name, router_instance = preset_service.build_router(gate_preset_name)

    gate = HyperGateAgent(router_instance)
    decision = await gate.decide(req.problem)

    def _with_preset(method: str | None) -> str | None:
        return build_auto_preset(method, tier) if method else None

    alternatives = [
        {**alt, "preset": _with_preset(alt.get("method"))}
        for alt in (decision.alternatives or [])
    ]

    return {
        "action": decision.action,
        "method": decision.method,
        "preset": _with_preset(decision.method) if decision.action == "pipeline" else None,
        "confidence": decision.confidence,
        "reasoning": decision.reasoning,
        "complexity": decision.complexity,
        "alternatives": alternatives,
        "needs_confirmation": (
            decision.action == "pipeline"
            and decision.confidence < HYPERGATE_METHOD_THRESHOLD
        ),
    }
