"""PipelineOrchestrator — single entry point for pipeline execution.

Used by: api/streaming.py (SSE), main.py (CLI), tests.
Handles:
  - preflight:  HyperGate routing, preset resolution, router construction, neuro recall
  - execute:    Pipeline.run() via ReasonerPipeline
  - postflight: Neuro learn, history save, event persistence
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from reasoner.application.flows.augmentation import get_tier_augmentation_methods
from reasoner.application.ports.service_protocols import (
    NeuroClientProtocol,
    PipelineServiceProtocol,
    PresetServiceProtocol,
    SearchServiceProtocol,
    TelemetryStoreProtocol,
)
from reasoner.core.constants import DEFAULT_CLI_PRESET, GATE_TIMEOUT_SECONDS
from reasoner.core.ports.model_registry_port import get_model_registry_port
from reasoner.domain.pipeline_state import PipelineState
from reasoner.hypergate import HyperGateAgent
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.phases._shared import is_article_request
from reasoner.pipeline import ReasonerPipeline
from reasoner.presets import get_preset_price_tier

logger = logging.getLogger(__name__)


@dataclass
class PreflightDecision:
    """Result of the preflight phase — determines pipeline routing."""
    action: str                         # "direct" | "web_search" | "pipeline"
    router: ProviderRouter
    effective_preset_name: str
    auto_selected_method: str | None = None
    augmentation_methods: list[str] | None = None
    gate_confidence: float | None = None
    gate_reasoning: str | None = None
    gate_alternatives: list[dict] | None = None
    recalled_chunks: list[dict] = field(default_factory=list)
    problem: str = ""
    conversation_history: list[dict] | None = None
    previous_synthesis: str = ""
    turn_number: int = 1


class PipelineOrchestrator:
    """Single entry point for pipeline execution.

    Three-phase lifecycle:
      1. preflight(req, initial_state) → PreflightDecision
      2. execute(decision, initial_state) → PipelineState
      3. postflight(state, req, user_id) → None

    Callers can interleave custom phases (SSE streaming) between
    preflight and postflight.
    """

    def __init__(
        self,
        preset_service: PresetServiceProtocol,
        pipeline_service: PipelineServiceProtocol,
        search_service: SearchServiceProtocol | None = None,
        neuro_client: NeuroClientProtocol | None = None,
        telemetry_store: TelemetryStoreProtocol | None = None,
        adaptive_routing: Any = None,  # AdaptiveRoutingService
    ) -> None:
        self.preset_service = preset_service
        self.pipeline_service = pipeline_service
        self.search_service = search_service
        self._neuro_client = neuro_client  # Injected or None (lazy fallback)
        self._telemetry_store = telemetry_store
        self._adaptive_routing = adaptive_routing

    async def preflight(
        self,
        req: Any,
        initial_state: PipelineState | None = None,
        user_id: str | None = None,
    ) -> PreflightDecision:
        """Resolve preset, build router, run HyperGate, perform neuro recall.

        Returns a PreflightDecision that guides whether to run a direct
        answer, web search, or full pipeline.
        """
        raw_preset = getattr(req, "preset", None) or DEFAULT_CLI_PRESET
        gate_preset_name, is_auto, auto_tier = self.preset_service.resolve(raw_preset)

        agent_model = getattr(initial_state, "agent_model", None) if initial_state else None
        custom_routing = getattr(req, "routing", None)

        # ── ACR Telemetry + Run ID ──
        run_id = str(__import__("uuid").uuid4())

        effective_preset_name, router = self.preset_service.build_router(
            gate_preset_name,
            custom_routing=custom_routing,
            agent_model=agent_model,
            telemetry=self._telemetry_store,
            run_id=run_id,
        )

        # ── ACR Adaptive Routing ──
        _acr_applied = False
        if self._adaptive_routing is not None and self._adaptive_routing.mode != "shadow":
            try:
                registry_port = get_model_registry_port()
                # Registry aliases, not served model strings: ACR returns and
                # the allowlist checks aliases, and two aliases can share one
                # served model.
                static = dict(router.routing_ids)
                static.setdefault("primary", router.primary_id)
                roles = list(static)

                plan = await self._adaptive_routing.select_routing_plan(
                    roles,
                    static,
                    static_fallbacks=router.fallback_routing_ids,
                    preset_id=gate_preset_name,
                )
                reroute = {
                    r: m for r, m in plan.routing.items()
                    if m and r != "primary" and registry_port.contains(m)
                }
                fallbacks = {
                    r: m for r, m in plan.fallbacks.items()
                    if m and registry_port.contains(m)
                }
                if reroute:
                    acr_primary = plan.routing.get("primary") or router.primary_id
                    router = ProviderRouter.from_model_ids(
                        primary_id=(
                            acr_primary if registry_port.contains(acr_primary)
                            else router.primary_id
                        ),
                        routing=reroute,
                        fallback_routing=fallbacks or None,
                        cascading_routing=router.cascading_routing_ids or None,
                        telemetry=self._telemetry_store,
                        run_id=run_id,
                        preset_id=gate_preset_name,
                        method=gate_preset_name,
                    )
                    _acr_applied = True
                    logger.info(
                        "ACR %s: applied for '%s' (%d roles, %d fallbacks)",
                        self._adaptive_routing.mode, gate_preset_name,
                        len(reroute), len(fallbacks),
                    )
            except Exception as exc:
                logger.warning("ACR routing failed, using preset: %s", exc)

        # P1.9: Short-circuit preflight if spend cap prevents any LLM spend
        try:
            from reasoner.core.settings import settings
            cap = settings.SPEND_CAP_PER_RUN_USD
            if cap > 0 and cap < 0.001:
                logger.warning(
                    "Per-run spend cap of $%.4f is too low for any pipeline — returning direct-action fallback",
                    cap,
                )
                return PreflightDecision(
                    action="direct",
                    router=router,
                    effective_preset_name=effective_preset_name,
                    problem=getattr(req, "problem", ""),
                )
        except Exception:
            pass

        # E4: Attach a fallback-event buffer to the router at construction time.
        # Even if execute() is not called (streaming/main paths), events are captured.
        _fallback_buffer: list[dict] = []
        import time as _time
        def _record_fallback(role: str, intended: str, actual: str, reason: str) -> None:
            _fallback_buffer.append({
                "role": role, "intended": intended,
                "actual": actual, "reason": reason,
                "ts": _time.time(),
            })
        router.on_fallback = _record_fallback
        # Store the buffer on the router so callers can extract it
        router._fallback_buffer = _fallback_buffer

        # ── Neuro Recall + HyperGate (independent budgets, run concurrently) ──
        # Recall is enrichment; the gate decides whether we spend money at all.
        # They must not share a budget: recall is an HTTP self-call, so when it
        # stalls it used to eat the whole window, leave gate_decision_fb None and
        # silently fall back to the *most expensive* path (a full pipeline) — even
        # for a prompt the gate would have answered directly in microseconds.
        recalled_chunks: list[dict[str, Any]] = []
        gate_decision_fb: Any | None = None  # fallback capture

        async def _run_neuro_recall():
            nonlocal recalled_chunks
            if getattr(req, "no_cache", False):
                return
            conversation_id = (
                getattr(initial_state, "conversation_id", None)
                if initial_state else None
            )
            try:
                recalled_chunks = await self._recall_neuro_context(
                    req.problem, agent_id=conversation_id, owner=user_id
                )
            except Exception as exc:
                logger.debug("Neuro recall failed: %s", exc)

        async def _run_hypergate():
            nonlocal gate_decision_fb
            if not getattr(req, "force_pipeline", False):
                # Override HyperGate router: grok-4.5 for primary, gemini-flash-lite for sub-agents
                from reasoner.infrastructure.llm.router import ProviderRouter
                registry = get_model_registry_port()
                hypergate_routing = dict(router.routing_table)
                hypergate_routing["hypergate_subagent"] = registry.get_provider("gemini-flash-lite")
                hypergate_router = ProviderRouter(
                    primary=registry.get_provider("grok-4.5"),
                    routing_table=hypergate_routing,
                    fallback_table=router.fallback_table,
                    cascading_routing=router.cascading_routing,
                    verbose=router.verbose,
                    run_id=router.run_id,
                    preset_id=f"hypergate-{router.preset_id}",
                    method=router.method,
                )
                gate = HyperGateAgent(hypergate_router)
                gate_decision_fb = await gate.decide(req.problem)

        _gate_timeout = max(GATE_TIMEOUT_SECONDS * 2, 5.0)
        _neuro_recall_timeout = settings.NEURO_RECALL_TIMEOUT_SECONDS

        async def _guard(coro, label: str, timeout: float) -> None:
            """Run one preflight task under its own budget; never raise."""
            try:
                await asyncio.wait_for(coro, timeout=timeout)
            except TimeoutError:
                logger.warning(
                    "Preflight %s exceeded %.0fs; continuing without it.",
                    label,
                    timeout,
                )
            except Exception as exc:
                logger.warning("Preflight %s failed: %s", label, exc)

        # gather() so total preflight is max(recall, gate), not their sum. A
        # stalled recall can no longer cost the gate its budget.
        await asyncio.gather(
            _guard(_run_neuro_recall(), "neuro recall", _neuro_recall_timeout),
            _guard(_run_hypergate(), "HyperGate", _gate_timeout),
        )

        if gate_decision_fb is None and not getattr(req, "force_pipeline", False):
            # Gate produced nothing (stalled or errored) — keep the existing
            # conservative behaviour and run the full pipeline.
            logger.warning("HyperGate produced no decision. Falling back to default pipeline.")

        decision = PreflightDecision(
            action="pipeline",
            router=router,
            effective_preset_name=effective_preset_name,
            recalled_chunks=recalled_chunks,
            problem=req.problem,
        )

        # ── Act on HyperGate decision (or fallback) ──
        if gate_decision_fb is not None:
            # Carry augmentation methods from gate decision (depth-detected pre-processing)
            decision.augmentation_methods = (
                gate_decision_fb.augmentation_methods
                if gate_decision_fb.action == "pipeline"
                else None
            )
            decision.gate_confidence = gate_decision_fb.confidence
            decision.gate_reasoning = gate_decision_fb.reasoning
            decision.gate_alternatives = gate_decision_fb.alternatives

            if gate_decision_fb.action == "direct":
                decision.action = "direct"
                history = getattr(initial_state, "conversation_history", None)
                decision.conversation_history = history
                decision.previous_synthesis = getattr(initial_state, "previous_synthesis", "")
                decision.turn_number = getattr(initial_state, "turn_number", 1)
                return decision

            if gate_decision_fb.action == "web_search":
                decision.action = "web_search"
                return decision

            # Auto-method: rebuild router with gate-selected method (skip if ACR already applied)
            if is_auto and gate_decision_fb.method and not custom_routing and not _acr_applied:
                effective_preset_name, router = self.preset_service.build_auto_router(
                    gate_decision_fb.method,
                    auto_tier,
                    agent_model=agent_model,
                    telemetry=self._telemetry_store,
                    run_id=run_id,
                )
                decision.router = router
                decision.effective_preset_name = effective_preset_name
                decision.auto_selected_method = gate_decision_fb.method

        # ── Article detection ──
        # Only auto-detect when the preset didn't specify a method.
        # Explicit presets (coding-budget, debate-budget, etc.) must not
        # be overridden by pattern-matching on the user's prompt.
        if is_auto and is_article_request(req.problem):
            decision.auto_selected_method = "writing"

        # ── Tier-appropriate augmentation methods ──
        # Gate decisions carry augmentation_methods=None by default.
        # Fill in tier-specific defaults so Budget users pay zero extra cost
        # and Premium users get the full multi-method pre-processing.
        if decision.action == "pipeline" and not decision.augmentation_methods:
            tier = get_preset_price_tier(decision.effective_preset_name)
            decision.augmentation_methods = get_tier_augmentation_methods(tier)

        return decision

    async def _recall_neuro_context(
        self, problem: str, agent_id: str | None = None, owner: str | None = None
    ) -> list[dict]:
        """Fetch relevant past context from Neuro memory."""
        from reasoner.core.ports.memory_port import get_memory_port

        port = get_memory_port()
        if port is None:
            return []
        try:
            return await port.recall(
                problem, agent_id=agent_id, max_results=5, owner=owner
            )
        except Exception as exc:
            logger.debug("Neuro recall failed: %s", exc)
        return []

    def create_pipeline(
        self,
        decision: PreflightDecision,
        initial_state: PipelineState | None = None,
        **pipeline_kwargs: Any,
    ) -> ReasonerPipeline:
        """Build a ReasonerPipeline from a PreflightDecision."""
        return self.pipeline_service.create_pipeline(
            router=decision.router,
            preset_name=decision.effective_preset_name,
            initial_state=initial_state,
            augmentation_methods=decision.augmentation_methods,
            **pipeline_kwargs,
        )

    async def execute(
        self,
        decision: PreflightDecision,
        initial_state: PipelineState | None = None,
        **pipeline_kwargs: Any,
    ) -> PipelineState:
        """Run the pipeline with the given decision. Returns final state."""
        pipeline = self.create_pipeline(decision, initial_state=initial_state, **pipeline_kwargs)
        state = initial_state or PipelineState(
            problem=decision.problem,
            preset_name=decision.effective_preset_name,
        )
        if decision.recalled_chunks:
            state.neuro_context = decision.recalled_chunks

        # E4: Replay fallback events captured during preflight into state
        _fallback_buffer = getattr(decision.router, "_fallback_buffer", [])
        if _fallback_buffer:
            state.meta.fallback_events.extend(_fallback_buffer)
            _fallback_buffer.clear()

        return await pipeline.run(decision.problem)

    async def postflight(
        self,
        state: PipelineState,
        req: Any,
        user_id: str | None = None,
        run_id: str | None = None,
    ) -> None:
        """Neuro learn and history persistence after pipeline completes."""
        # ── Neuro Persist ──
        try:
            from reasoner.core.ports.memory_port import get_memory_port

            port = get_memory_port()
            synthesis_text = ""
            if state.final_solution:
                synthesis_text = getattr(state.final_solution, "core_solution", "") or ""
            if not synthesis_text:
                synthesis_text = getattr(state, "previous_synthesis", "")

            if port is not None and synthesis_text:
                await port.learn(
                    prompt=getattr(req, "problem", ""),
                    response=synthesis_text,
                    agent_id=getattr(state, "conversation_id", None),
                    owner=user_id,
                    metadata={
                        "preset": getattr(state, "preset_name", ""),
                        "type": "pipeline",
                        "method": getattr(state.meta, "method", None),
                        "total_cost_usd": round(state.cost_state.total_cost_usd, 6),
                        "phase_costs": dict(state.cost_state.phase_costs),
                        "phase_durations": {k: round(v, 2) for k, v in state.meta.phase_durations.items()},
                        "quality_history": state.meta.quality_history[-10:],
                        "fallback_events": getattr(state.meta, "fallback_events", []),
                    },
                )
        except Exception as exc:
            logger.debug("Neuro persist failed: %s", exc)

        # ── Telemetry Persist (E2) ──
        if self._telemetry_store and run_id:
            try:
                # Build phase telemetry from canonical cost/duration/quality dicts
                phase_results: list[dict] = []
                phase_keys = set(state.cost_state.phase_costs_by_key.keys()) | set(state.meta.phase_durations.keys())
                for phase_key in sorted(phase_keys):
                    phase_results.append({
                        "phase_name": phase_key,
                        "cost_usd": state.cost_state.phase_costs_by_key.get(phase_key, 0.0),
                        "duration_ms": int(state.meta.phase_durations.get(phase_key, 0.0) * 1000),
                        "retries_used": int(state.cost_state.phase_costs_by_key.get(f"{phase_key}_retries", 0)),
                        "quality_score": None,
                        "quality_passed": None,
                        "models": list(state.cost_state._phase_models_by_key.get(phase_key, [])),
                    })
                await self._telemetry_store.save_run(
                    run_id=run_id,
                    preset=getattr(state, "preset_name", ""),
                    method=getattr(state.meta, "method", None),
                    phase_results=phase_results,
                    fallback_events=getattr(state.meta, "fallback_events", []),
                    total_cost_usd=state.cost_state.total_cost_usd,
                )
            except Exception as exc:
                logger.debug("Telemetry persist failed: %s", exc)

    async def stream_direct_answer(
        self,
        decision: PreflightDecision,
    ):
        """Stream a direct LLM answer — used by SSE entry point."""
        # Implementation in streaming.py via _stream_direct_answer
        raise NotImplementedError(
            "stream_direct_answer is handled by streaming.py's SSE layer"
        )

    async def stream_web_search(
        self,
        decision: PreflightDecision,
    ):
        """Stream web search results — used by SSE entry point."""
        # Implementation in streaming.py via _stream_web_search_results
        raise NotImplementedError(
            "stream_web_search is handled by streaming.py's SSE layer"
        )
