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


def build_hypergate_router(base: ProviderRouter) -> ProviderRouter:
    """Derive HyperGate's router from a preset's router.

    Single definition, called by both gate paths (this module's decide_route
    for /api/gate and the MCP tool, and PipelineOrchestrator's preflight).
    It used to be copy-pasted into both; they drifted, and only one of the two
    received the fallback fix below, so the pipeline preflight kept failing in
    the way /api/gate had already been fixed for.

    Routing, and why each entry has to be here:

    * ``hypergate_subagent`` is the role every BaseSubAgent calls. It carries
      the real gate workload: five of these run in parallel per request, each
      emitting <=128 tokens, with the user waiting on the result.
    * ``fallback_routing["hypergate_subagent"]`` is NOT optional. _resolve_fallback
      only consults ``fallback_table["primary"]`` when the failing provider *is*
      the router's primary; for any other role it falls through to the primary
      provider itself. Without this entry a failing sub-agent would retry on
      ``primary`` -- measured at a 16.1s mean and a 6/10 failure rate against a
      6s timeout -- turning the slowest model in the chain into the safety net
      for the fastest.
    * ``fallback_table["primary"]`` stays for the primary role itself, whose
      rule is the mirror image: primary cannot fall back to itself, and
      candidates are deduped by served model, so without an explicit entry a
      timeout there is structurally unrecoverable.

    Model choice, measured 2026-08-29 by running all five sub-agent system
    prompts against each candidate and checking whether the reply parsed
    (verdict / slowest of the five):

        ministral-14b   5/5 parsed   1.92s   EU   <- chosen
        laguna-s-2.1    5/5 parsed   1.88s   --
        gpt-4o-mini     5/5 parsed   1.81s   US   <- chosen as fallback
        grok-4.3        5/5 parsed   4.64s   US
        ministral-3b    4/5 parsed   0.97s        fails direct_detector
        laguna-xs-2.1   4/5 parsed   1.20s        fails method_classifier
        gemma-4-31b     2/5 parsed   --           emits -1 for string fields
        qwen3.6-flash   0/5 parsed   --           returns ""
        qwen3.5-flash   0/5 parsed   --           returns -1.0000000000000002e+308

    qwen3.5-flash is what this role was configured with, and it never ran:
    sub-agents resolved the role and then called role="primary", so grok-4.5
    answered instead and the broken config was invisible. It is broken at every
    max_tokens tried (80/256/1024/4096) -- on a plain prose prompt it replies
    "Thinking Process:\\n1. **Analyze the Request:**...", i.e. reasoning.exclude
    does not suppress its narration, and under the response_format JSON contract
    that narration collapses to a degenerate float. Not a token-budget problem.

    grok-4.5 is gone from the primary slot for the same kind of reason, measured
    on this deployment's own histogram: 16.1s mean over 10 calls with 6 failures,
    against a 6s per-attempt timeout. Nothing in the repo ever justified it.

    Speed was not the deciding axis -- laguna-xs-2.1 is the fastest candidate and
    is rejected, because it is a coding-specialised model and returns "" for the
    one genuinely hard job here, picking among ~16 opaque method letters.
    Correctness first, then latency.
    """
    registry = get_model_registry_port()
    routing = dict(base.routing_table)
    routing["hypergate_subagent"] = registry.get_provider("ministral-14b")

    fallback = dict(base.fallback_table)
    fallback["hypergate_subagent"] = registry.get_provider("gpt-4o-mini")
    fallback["primary"] = registry.get_provider("gpt-4o-mini")

    return ProviderRouter(
        primary=registry.get_provider("ministral-14b"),
        routing_table=routing,
        fallback_table=fallback,
        cascading_routing=base.cascading_routing,
        verbose=base.verbose,
        run_id=base.run_id,
        preset_id=f"hypergate-{base.preset_id}",
        method=base.method,
    )


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

    gate = HyperGateAgent(build_hypergate_router(router_instance))
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
