"""HyperGate routing decision, shared by the HTTP and MCP adapters.

Moved out of api/routes/gate.py -- that handler was pure logic wrapped in a
CSRF dependency, and the MCP tool needs the identical decision without any
HTTP coupling. One implementation; both adapters call it.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from reasoner.application.services.preset_service import PresetService
from reasoner.core.constants import (
    HYPERGATE_CACHE_ENABLED,
    HYPERGATE_CACHE_TTL_SECONDS,
    HYPERGATE_METHOD_THRESHOLD,
    HYPERGATE_TOTAL_BUDGET_SECONDS,
)
from reasoner.core.ports.model_registry_port import get_model_registry_port
from reasoner.core.ports.shared_cache_port import get_shared_cache_port
from reasoner.domain.preset_core import build_auto_preset
from reasoner.hypergate import GateDecision, HyperGateAgent
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.presets import get_preset_price_tier

logger = logging.getLogger(__name__)


# ── HyperGate per-role routing (W4) ───────────────────────────────────
#
# One role per sub-agent instead of one shared role. Two reasons, both measured
# on 2026-08-29 (docs/plans/gate-and-registry-remediation.md W4):
#
# 1. Contention. `ministral-14b` answers a single sub-agent prompt in 1.47-1.92s
#    when probed alone, but averaged 5.86s in the running app (93.83s / 16 calls
#    from this deployment's own reasoner_llm_call_duration_seconds). The five
#    Phase-1 agents fire concurrently via asyncio.gather and every one of them
#    resolved the same role, therefore the same provider and the same upstream
#    endpoint. The gate's parallelism was defeating itself.
#
# 2. Capability. The measurements below ran all five sub-agent system prompts
#    against each candidate; the verdict is simply whether the reply parsed.
#
#        ministral-14b   5/5 parsed   1.92s   mistralai (EU)
#        laguna-s-2.1    5/5 parsed   1.88s   poolside  (US)
#        gpt-4o-mini     5/5 parsed   1.81s   openai    (US)
#        grok-4.3        5/5 parsed   4.64s   x-ai      (US)  -- 2.4x slower
#        ministral-3b    4/5 parsed   0.97s   fastest; fails direct_detector
#        laguna-xs-2.1   4/5 parsed   1.20s   fails method_classifier
#        gemma-4-31b     2/5 parsed   --      emits -1 for string fields
#        qwen3.6-flash   0/5 parsed   --      returns ""
#        qwen3.5-flash   0/5 parsed   --      returns -1.0000000000000002e+308
#
#    The two cheapest models each fail exactly one job. A per-role table can use
#    them for the four jobs they pass; a single shared role could not, and had
#    to pay for the strongest model on the easiest task.
#
# qwen3.5-flash is what the shared role was configured with, and it never ran:
# sub-agents resolved the role and then called role="primary", so grok-4.5
# answered instead and the broken config was invisible. It is broken at every
# max_tokens tried (80/256/1024/4096) -- on a plain prose prompt it replies
# "Thinking Process:" followed by a numbered plan -- i.e. reasoning.exclude does
# not suppress its narration, and under the response_format JSON contract
# that narration collapses to a degenerate float. Not a token-budget problem.
#
# grok-4.5 is gone from the primary slot for the same kind of reason, measured
# on this deployment's own histogram: 16.1s mean over 10 calls with 6 failures,
# against a 6s per-attempt timeout. Nothing in the repo ever justified it.
_HYPERGATE_ROLE_MODELS: dict[str, str] = {
    # -- the five that run concurrently in Phase 1 --
    # No two share a served model, which is the whole point: five parallel
    # calls now reach five distinct models across three vendors.
    "hypergate_language": "ministral-3b",     # trivial task, fastest verified
    "hypergate_complexity": "laguna-xs-2.1",  # passes; second vendor
    "hypergate_direct": "gpt-4o-mini",        # third vendor; ministral-3b fails this
    "hypergate_web": "laguna-s-2.1",          # passes; distinct from complexity
    "hypergate_method": "ministral-14b",      # hardest task, needs 5/5 model
    # -- Phase 2, runs alone after Phase 1 has returned --
    # Sharing gpt-4o-mini with hypergate_direct is deliberate and safe: the
    # tie-breaker only fires once Phase 1 is complete, so the two are never in
    # flight together and cannot contend.
    "hypergate_tiebreak": "gpt-4o-mini",
    # -- the default BaseSubAgent.ROLE --
    # Only ImageModelSelector still uses it, invoked on its own from
    # api/routes/images.py, so its overlap with hypergate_method is likewise
    # never concurrent.
    "hypergate_subagent": "ministral-14b",
}

# Fallbacks are NOT optional and are NOT derivable. _resolve_fallback consults
# fallback_table["primary"] only when the failing provider *is* the router
# primary; for any other role it falls through to the primary provider itself.
# Every role therefore needs its own entry or it silently inherits the primary.
#
# Two constraints on each value, both asserted in tests/test_hypergate.py:
#   * a different vendor than the role's primary model, per the project's
#     cross-lab convention -- a fallback sharing an upstream with the model
#     that just failed is not a fallback;
#   * never the router primary itself, which is what an absent entry would
#     silently give you.
# Only 5/5-parsing models appear here: a fallback firing on a job its model
# cannot do turns a slow failure into a wrong answer.
_HYPERGATE_ROLE_FALLBACKS: dict[str, str] = {
    "hypergate_language": "laguna-s-2.1",     # mistralai -> poolside
    "hypergate_complexity": "gpt-4o-mini",    # poolside  -> openai
    "hypergate_direct": "laguna-s-2.1",       # openai    -> poolside
    "hypergate_web": "gpt-4o-mini",           # poolside  -> openai
    "hypergate_method": "gpt-4o-mini",        # mistralai -> openai
    "hypergate_tiebreak": "laguna-s-2.1",     # openai    -> poolside
    "hypergate_subagent": "gpt-4o-mini",      # mistralai -> openai
}

# The router primary. Roles resolve through the tables above, so this is only
# reached for a role nobody declared; it stays on the strongest verified model.
_HYPERGATE_PRIMARY: str = "ministral-14b"


def build_hypergate_router(base: ProviderRouter) -> ProviderRouter:
    """Derive HyperGate's router from a preset's router.

    Single definition, called by both gate paths (this module's decide_route
    for /api/gate and the MCP tool, and PipelineOrchestrator's preflight).
    It used to be copy-pasted into both; they drifted, and only one of the two
    received the fallback fix, so the pipeline preflight kept failing in the way
    /api/gate had already been fixed for.

    Every role in _HYPERGATE_ROLE_MODELS is populated here together with its
    fallback -- see those tables for which model answers which sub-agent and
    why. ``fallback_table["primary"]`` stays for the primary role itself, whose
    rule is the mirror image: primary cannot fall back to itself, and candidates
    are deduped by served model, so without an explicit entry a timeout there is
    structurally unrecoverable.
    """
    registry = get_model_registry_port()

    routing = dict(base.routing_table)
    for role, model_id in _HYPERGATE_ROLE_MODELS.items():
        routing[role] = registry.get_provider(model_id)

    fallback = dict(base.fallback_table)
    for role, model_id in _HYPERGATE_ROLE_FALLBACKS.items():
        fallback[role] = registry.get_provider(model_id)
    fallback["primary"] = registry.get_provider("gpt-4o-mini")

    return ProviderRouter(
        primary=registry.get_provider(_HYPERGATE_PRIMARY),
        routing_table=routing,
        fallback_table=fallback,
        cascading_routing=base.cascading_routing,
        verbose=base.verbose,
        run_id=base.run_id,
        preset_id=f"hypergate-{base.preset_id}",
        method=base.method,
    )


# ── L2 gate decision cache (W5) ───────────────────────────────────────
#
# Lives here, not in HyperGateAgent, for the reason its own stub comment gave
# before it was deleted: hypergate/ sits below application/ and must not reach
# for a cache backend itself. The application layer may consume SharedCachePort,
# so this is the lowest place the wiring is legal.
#
# The key must carry a routing identity, not just the problem text. A gate
# verdict is a function of the problem AND of which models answered it, and W4
# made the second half real -- the roles now resolve to five different models
# across three vendors, and any of those can be re-pointed. A bare sha256 of the
# problem would serve the old configuration's verdict for an hour after a model
# swap. There is precedent in this repo: the LLM cache bug fixed on 2026-08-26
# was exactly a key that ignored part of the request (the system prompt), and it
# presented as byte-identical output from a deliberate A/B.
_GATE_CACHE_PREFIX = "gate:v1:"


def routing_fingerprint(router: ProviderRouter) -> str:
    """Digest the (role, served model) pairs this router will actually use.

    Served model, not alias: aliases route cross-vendor, so two aliases can name
    the same upstream model and two identical-looking aliases can differ. Only
    the gate's own roles plus the primary are digested -- the rest of the
    inherited routing table has no bearing on a gate decision, and including it
    would evict the whole cache on any unrelated preset edit.
    """
    parts = [
        f"{role}={getattr(router.resolve(role), 'model', '?')}"
        for role in sorted(_HYPERGATE_ROLE_MODELS)
    ]
    parts.append(f"primary={getattr(router.resolve_primary(), 'model', '?')}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _is_cacheable(decision: GateDecision) -> bool:
    """Whether *decision* is confident enough to persist for an hour.

    The same two conditions HyperGateAgent.decide applied before its (dead)
    cache write, rewritten only to fold the empty-reasoning case. A verdict
    that is degraded -- low confidence, or reasoning mentioning a fallback --
    is a statement about one bad minute upstream, not about the problem, and
    must never outlive it.
    """
    return decision.confidence >= HYPERGATE_METHOD_THRESHOLD and (
        "fallback" not in (decision.reasoning or "").lower()
    )


async def run_gate_cached(gate: HyperGateAgent, problem: str) -> GateDecision:
    """Run *gate* on *problem*, reading and writing the shared L2 cache.

    Every cache interaction degrades to a miss: no port injected, an unreachable
    backend, a stored payload that no longer validates against GateDecision. The
    cache is an optimisation and may never be the reason a request fails.
    """
    cache = get_shared_cache_port() if HYPERGATE_CACHE_ENABLED else None
    key = ""
    if cache is not None:
        key = (
            f"{_GATE_CACHE_PREFIX}{hashlib.sha256(problem.encode()).hexdigest()}"
            f":{routing_fingerprint(gate.router)}"
        )
        try:
            raw = await cache.get(key)
            if raw:
                decision = GateDecision.model_validate(raw)
                logger.debug("HyperGate cache hit key=%s", key[:40])
                return decision
        except Exception as exc:
            logger.debug("HyperGate cache lookup failed (%s): %s", key[:40], exc)

    decision = await gate.decide(problem)

    if cache is not None and _is_cacheable(decision):
        try:
            await cache.set(
                key, decision.model_dump(mode="json"), ttl=HYPERGATE_CACHE_TTL_SECONDS
            )
        except Exception as exc:
            logger.debug("HyperGate cache store failed (%s): %s", key[:40], exc)

    return decision


async def decide_route(problem: str, preset: str) -> dict[str, Any]:
    """Return HyperGate's routing decision for *problem*, without running it.

    Each candidate (top pick + alternatives) is resolved to a concrete preset
    name via build_auto_preset(), so a caller can re-submit with that preset
    + force_pipeline=true to lock in a specific method without re-invoking
    HyperGate. The decision goes through the shared L2 cache (run_gate_cached),
    so a following run on the same problem and the same routing does not re-pay
    the HyperGate LLM cost. Until W5 this docstring claimed that while the cache
    it named was two stub methods returning None.

    The whole decision is bounded by HYPERGATE_TOTAL_BUDGET_SECONDS. Before
    this, /api/gate awaited gate.decide() with no ceiling at all -- measured
    30,189ms on one complex prompt (docs/plans/gate-and-registry-remediation.md
    W3). PipelineOrchestrator's preflight has its own separate timeout around
    the same call (orchestrator.py's `_guard`); this is the equivalent for the
    HTTP/MCP path, which had none.
    """
    preset_service = PresetService()
    raw_preset = preset or "auto-budget"
    gate_preset_name, is_auto, auto_tier = preset_service.resolve(raw_preset)
    tier = auto_tier if is_auto else get_preset_price_tier(gate_preset_name)
    _effective_preset_name, router_instance = preset_service.build_router(gate_preset_name)

    gate = HyperGateAgent(build_hypergate_router(router_instance))
    try:
        decision = await asyncio.wait_for(
            run_gate_cached(gate, problem), timeout=HYPERGATE_TOTAL_BUDGET_SECONDS
        )
    except TimeoutError:
        from reasoner.infrastructure.metrics import HYPERGATE_BUDGET_EXCEEDED_TOTAL

        HYPERGATE_BUDGET_EXCEEDED_TOTAL.inc()
        logger.warning(
            "HyperGate exceeded total budget of %.0fs; falling back to pipeline.",
            HYPERGATE_TOTAL_BUDGET_SECONDS,
        )
        # Same conservative verdict HyperGateAgent._synthesize's own Step 5
        # hard-fallback produces on total sub-agent failure -- a budget timeout
        # and "every sub-agent came back empty" should look identical to the
        # caller, both being "we could not get a confident answer in time".
        decision = GateDecision(
            action="pipeline",
            method="multi_perspective",
            confidence=0.0,
            reasoning=(
                f"HyperGate exceeded total budget of "
                f"{HYPERGATE_TOTAL_BUDGET_SECONDS:.0f}s, fallback to pipeline"
            ),
        )

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


__all__ = ["build_hypergate_router", "decide_route", "run_gate_cached"]
