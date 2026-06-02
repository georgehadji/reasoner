"""Cost estimate endpoint — POST /api/estimate.

Estimates tokens, cost, and duration for a pipeline run without executing it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from reasoner.api.schemas import RunRequest
from reasoner.api.auth_deps import require_csrf
from reasoner.core.settings import settings

router = APIRouter()


@router.post("/api/estimate")
async def estimate_cost(
    req: RunRequest,
    csrf_checked=Depends(require_csrf),
):
    """Estimate tokens, cost, and duration for a pipeline run."""
    from reasoner.pricing import calculate_model_cost, get_pricing
    from reasoner.presets import get_preset_price_tier
    from reasoner.application.services.preset_service import PresetService

    _preset_service = PresetService()
    raw_preset = req.preset or "auto-budget"
    gate_preset_name, _is_auto, _auto_tier = _preset_service.resolve(raw_preset)
    tier = get_preset_price_tier(gate_preset_name)

    prompt_tokens = len(req.problem.split()) + 50
    num_phases = 8
    tokens_per_phase_input = 1000 if tier == "premium" else 500
    tokens_per_phase_output = 1500 if tier == "premium" else 800

    estimated_input = prompt_tokens + (num_phases * tokens_per_phase_input)
    estimated_output = num_phases * tokens_per_phase_output

    from reasoner.infrastructure.llm.registry import _REGISTRY
    primary_id = _REGISTRY.get(gate_preset_name, {}).get(
        "primary", "openrouter/openai/gpt-4o-mini"
    )
    estimated_cost = calculate_model_cost(primary_id, estimated_input, estimated_output)

    base_duration = 8 if tier == "budget" else 20
    estimated_duration = base_duration + (len(req.problem.split()) / 50)

    return {
        "estimated_tokens_input": estimated_input,
        "estimated_tokens_output": estimated_output,
        "estimated_cost_usd": round(estimated_cost, 4),
        "estimated_duration_seconds": round(estimated_duration, 1),
        "preset": gate_preset_name,
        "tier": tier,
    }
