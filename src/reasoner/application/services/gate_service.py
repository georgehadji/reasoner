"""HyperGate routing decision, shared by the HTTP and MCP adapters.

Moved out of api/routes/gate.py -- that handler was pure logic wrapped in a
CSRF dependency, and the MCP tool needs the identical decision without any
HTTP coupling. One implementation; both adapters call it.
"""

from __future__ import annotations

from typing import Any

from reasoner.application.services.preset_service import PresetService
from reasoner.core.constants import HYPERGATE_METHOD_THRESHOLD
from reasoner.core.ports.model_registry_port import get_model_registry_port
from reasoner.domain.preset_core import build_auto_preset
from reasoner.hypergate import HyperGateAgent
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.presets import get_preset_price_tier


async def decide_route(problem: str, preset: str) -> dict[str, Any]:
    """Return HyperGate's routing decision for *problem*, without running it.

    Each candidate (top pick + alternatives) is resolved to a concrete preset
    name via build_auto_preset(), so a caller can re-submit with that preset
    + force_pipeline=true to lock in a specific method without re-invoking
    HyperGate. Shares HyperGateAgent's own L1/L2 cache, so a following run on
    the same problem does not re-pay the HyperGate LLM cost.
    """
    preset_service = PresetService()
    raw_preset = preset or "auto-budget"
    gate_preset_name, is_auto, auto_tier = preset_service.resolve(raw_preset)
    tier = auto_tier if is_auto else get_preset_price_tier(gate_preset_name)
    _effective_preset_name, router_instance = preset_service.build_router(gate_preset_name)

    # Override HyperGate router: grok-4.5 for primary, gemini-flash-lite for sub-agents
    registry = get_model_registry_port()
    hypergate_routing = dict(router_instance.routing_table)
    hypergate_routing["hypergate_subagent"] = registry.get_provider("qwen3.5-flash")
    # _resolve_fallback's rule is "explicit > primary > none". Since primary
    # IS grok-4.5 here, a timed-out grok-4.5 call can never fall back to
    # itself — without an explicit "primary" entry this table inherits from
    # router_instance has none, so every grok-4.5 timeout was unrecoverable
    # (confidence 0.0, "all sub-agents failed"). gpt-4o-mini is fast and
    # cross-lab (OpenAI vs. xAI), matching the project's cross-lab fallback
    # convention.
    hypergate_fallback_table = dict(router_instance.fallback_table)
    hypergate_fallback_table["primary"] = registry.get_provider("gpt-4o-mini")
    hypergate_router = ProviderRouter(
        primary=registry.get_provider("grok-4.5"),
        routing_table=hypergate_routing,
        fallback_table=hypergate_fallback_table,
        cascading_routing=router_instance.cascading_routing,
        verbose=router_instance.verbose,
        run_id=router_instance.run_id,
        preset_id=f"hypergate-{router_instance.preset_id}",
        method=router_instance.method,
    )

    gate = HyperGateAgent(hypergate_router)
    decision = await gate.decide(problem)

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


__all__ = ["decide_route"]
