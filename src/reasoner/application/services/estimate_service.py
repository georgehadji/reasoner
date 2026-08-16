"""Cost/duration estimation, shared by the HTTP and MCP adapters.

Moved out of api/routes/estimate.py -- that handler was pure arithmetic
wrapped in a CSRF dependency. One implementation; both adapters call it.
"""

from __future__ import annotations

from typing import Any


async def estimate_cost(problem: str, preset: str) -> dict[str, Any]:
    """Estimate tokens, cost, and duration for a run, without executing it."""
    from reasoner.application.services.preset_service import PresetService
    from reasoner.infrastructure.llm.registry import _REGISTRY
    from reasoner.presets import get_preset_price_tier
    from reasoner.pricing import calculate_model_cost

    preset_service = PresetService()
    raw_preset = preset or "auto-budget"
    gate_preset_name, _is_auto, _auto_tier = preset_service.resolve(raw_preset)
    tier = get_preset_price_tier(gate_preset_name)

    prompt_tokens = len(problem.split()) + 50
    num_phases = 8
    tokens_per_phase_input = 1000 if tier == "premium" else 500
    tokens_per_phase_output = 1500 if tier == "premium" else 800

    estimated_input = prompt_tokens + (num_phases * tokens_per_phase_input)
    estimated_output = num_phases * tokens_per_phase_output

    primary_id = _REGISTRY.get(gate_preset_name, {}).get(
        "primary", "openrouter/openai/gpt-4o-mini"
    )
    estimated_cost = calculate_model_cost(primary_id, estimated_input, estimated_output)

    base_duration = 8 if tier == "budget" else 20
    estimated_duration = base_duration + (len(problem.split()) / 50)

    return {
        "estimated_tokens_input": estimated_input,
        "estimated_tokens_output": estimated_output,
        "estimated_cost_usd": round(estimated_cost, 4),
        "estimated_duration_seconds": round(estimated_duration, 1),
        "preset": gate_preset_name,
        "tier": tier,
    }


__all__ = ["estimate_cost"]
