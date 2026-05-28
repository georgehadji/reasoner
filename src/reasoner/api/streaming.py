"""Core pipeline streaming logic — SSE generators for run, follow-up, cache, direct answer, and web search."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator

from reasoner.core.constants import (
    SSE_FLUSH_INTERVAL,
    TIMEOUTS,
    TRUNCATION,
    VALIDATION_TEST_MAX_TOKENS,
    get_phase_retry_budget,
    get_phase_timeout,
)
from reasoner.quality import PhaseMonitor, reset_phase_state
from reasoner.hypergate import HyperGateAgent
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.infrastructure.llm.registry import _REGISTRY
from reasoner.models import PipelineState, TaskType
from reasoner.pipeline import ReasonerPipeline
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.search_service import SearchService
from reasoner.exceptions import classify_error, is_retryable
from reasoner.presets import (
    build_auto_preset,
    get_method_from_preset,
    get_preset_tier,
    get_preset_price_tier,
)
from reasoner.phases._shared import build_followup_context, _wrap_user_input

from .cache import CACHE_DIR, _cache_key, _load_cache, _save_cache
from .history import HISTORY_DIR, HistoryEntry, _save_history_entry, _save_pipeline_owner
from reasoner.infrastructure.redis.run_state import _run_state_manager as _run_store
from reasoner.core.events.domain_events import make_event, EventType
from reasoner.infrastructure.persistence.event_store import get_event_store
from .schemas import FollowupRequest, RunRequest
from .serializers import (
    _event,
    _ser_0,
    _ser_1,
    _ser_1_5,
    _ser_5,
    _ser_synthesis,
)

logger = logging.getLogger(__name__)

# NOTE: We instantiate lazily inside run_stream so that preset module
# reloads (e.g. after editing preset_registry.py) are picked up by
# long-running processes.
_preset_service: PresetService | None = None


def _ensure_fresh_preset_service() -> PresetService:
    """Force-reload preset modules in case a long-running process has stale code."""
    global _preset_service
    import importlib
    import sys
    # Nuke all preset-related modules from sys.modules so they are re-imported fresh
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith(("reasoner.domain.preset", "reasoner.presets", "reasoner.application.services.preset_service")):
            del sys.modules[mod_name]
    # Re-import after eviction
    import reasoner.domain.preset_registry as _pr_mod  # type: ignore[no-redef]
    import reasoner.presets as _ps_mod  # type: ignore[no-redef]
    import reasoner.application.services.preset_service as _svc_mod  # type: ignore[no-redef]
    importlib.reload(_pr_mod)
    importlib.reload(_ps_mod)
    importlib.reload(_svc_mod)
    _preset_service = _svc_mod.PresetService()
    return _preset_service


def _get_phase_subagents(state: PipelineState, phase_name: str) -> list[dict[str, Any]]:
    """Return subagent outputs for a given phase name."""
    mapping = {
        "Decomposition": "decomposition_subagent_outputs",
        "Critique & Pruning": "critique_subagent_outputs",
        "Synthesis": "synthesis_subagent_outputs",
        "Deep Research": "search_subagent_outputs",
    }
    attr = mapping.get(phase_name)
    if attr:
        outputs = getattr(state, attr, [])
        if isinstance(outputs, list):
            return outputs
    return []


async def _emit_widget_event(
    widget_result: dict[str, Any],
) -> str:
    """Emit a widget event into the SSE stream.

    Usage: yield await _emit_widget_event({...})
    """
    return _event({
        "type": "widget",
        "data": {
            "widget_type": widget_result.get("widget_type", ""),
            "name": widget_result.get("name", ""),
            "result": widget_result.get("data", {}),
            "citations": widget_result.get("citations", []),
        },
    })


async def _broadcast_ws(run_id: str, payload: dict[str, Any]) -> None:
    """Broadcast an event to WebSocket subscribers for this run.

    Fire-and-forget: never blocks the SSE stream on WS delivery.
    """
    try:
        from reasoner.infrastructure.websocket import get_websocket_manager

        manager = get_websocket_manager()
        asyncio.create_task(manager.broadcast_event(payload, run_id))
    except Exception:
        logger.warning("WS broadcast failed for run %s", run_id, exc_info=True)


async def _persist_event(event) -> None:
    """Persist a domain event to the event store.

    Fire-and-forget: event-store failure must never break the stream.
    """
    try:
        store = get_event_store()
        await store.save_events([event])
    except Exception as e:
        logger.warning("EventStore persistence failed for event %s: %s", event.event_type.value, str(e), exc_info=True)


# Creative-writing model tiers with 2 fallbacks each.
# Format: (model_id, description)
_CREATIVE_MODELS_BUDGET: list[tuple[str, str]] = [
    ("kimi-k2-6", "Kimi K2.6 — 1T MoE, best value creative"),
    ("qwen3.6-plus", "Qwen 3.6 Plus — multilingual fallback"),
    ("mistral-large-3", "Mistral Large — European language fallback"),
]
_CREATIVE_MODELS_PREMIUM: list[tuple[str, str]] = [
    ("claude-sonnet", "Claude Sonnet — gold standard creative"),
    ("gpt-5", "GPT-5 — structured/academic fallback"),
    ("gemini-pro", "Gemini Pro — research-backed fallback"),
]

# Enhanced system prompt for creative writing with hallucination guards.
_CREATIVE_SYSTEM_PROMPT = (
    "You are an expert writer and creative assistant.\n"
    "\n"
    "WRITING PRINCIPLES:\n"
    "1. Produce well-structured, engaging, and original content.\n"
    "2. Follow the user's instructions precisely regarding tone, length, format, and style.\n"
    "3. Maintain a consistent voice and perspective throughout the piece.\n"
    "\n"
    "HALLUCINATION PREVENTION:\n"
    "1. If you include historical events, real people, statistics, or scientific claims, "
    "ensure they are accurate and widely accepted. Do NOT invent studies, citations, dates, or data.\n"
    "2. Clearly distinguish between factual claims and creative interpretation, opinion, or speculation.\n"
    "3. If you are uncertain about a fact, rephrase it as a general observation or omit it.\n"
    "4. Do NOT fabricate quotes, sources, or references.\n"
    "\n"
    "SELF-CORRECTION:\n"
    "Before finalizing, mentally review your draft for any unsupported factual claims. "
    "Replace dubious claims with safer, more general statements.\n"
)


async def _stream_direct_answer(
    router: ProviderRouter,
    problem: str,
    run_id: str,
    cancel_event: asyncio.Event | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    previous_synthesis: str = "",
    turn_number: int = 1,
    preset_name: str = "",
) -> AsyncGenerator[str, None]:
    """Stream a direct LLM answer as a virtual single-phase pipeline for UI compatibility."""
    yield _event({"type": "start"})

    if cancel_event and cancel_event.is_set():
        yield _event({"type": "cancelled", "message": "Pipeline stopped by user"})
        return

    yield _event({"type": "phase_start", "phase": 0, "name": "Direct Response"})
    phase_start = time.monotonic()

    # Build conversation context for follow-up turns
    context_block = build_followup_context(
        conversation_history,
        previous_synthesis=previous_synthesis[:2000],
        turn_number=turn_number,
    )
    if context_block:
        user_prompt = f"{context_block}\nCURRENT USER REQUEST:\n{_wrap_user_input(problem)}"
    else:
        user_prompt = _wrap_user_input(problem)

    # Choose system prompt and creative model based on task type and preset tier
    from reasoner.hypergate.hyperagent import _is_creative_writing
    is_creative = _is_creative_writing(problem)

    if is_creative:
        system_prompt = _CREATIVE_SYSTEM_PROMPT
        max_tokens = 4096
        temperature = 0.8
        tier = get_preset_price_tier(preset_name)
        creative_models = (
            _CREATIVE_MODELS_PREMIUM if tier == "premium" else _CREATIVE_MODELS_BUDGET
        )
    else:
        system_prompt = "You are an analytical assistant. Provide a clear, concise answer."
        max_tokens = 2048
        temperature = 0.7
        creative_models = []

    # ── LLM call with fallback chain ──
    response: str = ""
    meta: dict[str, Any] = {}
    last_error: Exception | None = None
    models_to_try: list[tuple[str, str]] = []

    # Resolve primary provider safely (handles test fakes without .primary)
    _primary_provider = getattr(router, "primary", None) or getattr(router, "_primary", None)
    _primary_model = getattr(_primary_provider, "model", "unknown") if _primary_provider else "unknown"

    if is_creative and creative_models:
        # Build fallback chain: try creative models first, then fall back to primary
        models_to_try = list(creative_models)
        models_to_try.append((_primary_model, "primary fallback"))
    else:
        models_to_try = [(_primary_model, "primary")]

    for model_id, reason in models_to_try:
        try:
            if model_id == _primary_model:
                # Use existing router (primary or routing table)
                response, meta = await router.call(
                    role="primary",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                from reasoner.infrastructure.llm.ports import DegradedLLMResponse
                if isinstance(response, DegradedLLMResponse):
                    logger.warning(
                        "Direct answer degraded with %s (%s): %s",
                        model_id, reason, response.error,
                    )
                    yield _event({
                        "type": "phase_warning",
                        "phase": 0,
                        "warning": response.error,
                    })
                    last_error = RuntimeError(response.error)
                    continue
            else:
                # Build a temporary provider for the creative model
                from reasoner.infrastructure.llm.registry import build_provider
                provider = build_provider(model_id)
                response = await provider.complete_with_retry(
                    system_prompt, user_prompt, max_tokens, temperature
                )
                meta = {"model": model_id, "input_tokens": 0, "output_tokens": 0}
            logger.info(
                "Direct answer succeeded with %s (%s) for creative=%s",
                model_id, reason, is_creative,
            )
            break
        except Exception as exc:
            last_error = exc
            logger.warning(
                "Direct answer failed with %s (%s): %s — trying next fallback",
                model_id, reason, exc,
            )
            continue
    else:
        # All fallbacks exhausted
        logger.error("Direct answer failed after all fallbacks: %s", last_error)
        if last_error and classify_error(last_error) == "auth":
            err_msg = (
                "OpenRouter API key is missing or invalid. "
                "Please set OPENROUTER_API_KEY in your .env or ui-next/.env.local file."
            )
        else:
            err_msg = f"{type(last_error).__name__ if last_error else 'Unknown'}: {str(last_error)[:120] if last_error else 'All models failed'}"
        yield _event({"type": "phase_error", "phase": 0, "error": err_msg})
        yield _event({
            "type": "done",
            "errors": [err_msg],
            "total_tokens": {"input": 0, "output": 0, "total": 0},
            "duration": time.monotonic() - phase_start,
        })
        return

    duration = time.monotonic() - phase_start
    data = {
        "solution": response,
        "tokens": {
            "input": meta.get("input_tokens", 0),
            "output": meta.get("output_tokens", 0),
        },
        "duration": duration,
    }
    yield _event({
        "type": "phase_complete",
        "phase": 0,
        "name": "Direct Response",
        "data": data,
    })

    total_input = meta.get("input_tokens", 0)
    total_output = meta.get("output_tokens", 0)
    yield _event({
        "type": "done",
        "errors": [],
        "total_tokens": {
            "input": total_input,
            "output": total_output,
            "total": total_input + total_output,
        },
        "duration": duration,
    })


_search_service = SearchService()


async def _stream_web_search_results(
    problem: str,
    run_id: str,
    num_results: int = 10,
    cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[str, None]:
    """Stream SearXNG web search results as a virtual single-phase pipeline."""
    async for chunk in _search_service.stream_web_search_results(
        problem, run_id, num_results=num_results, cancel_event=cancel_event
    ):
        yield chunk


async def _recall_neuro_context(problem: str, agent_id: str | None = None) -> list[dict[str, Any]]:
    """Fetch relevant past context from Neuro memory."""
    try:
        from reasoner.api.clients import get_neuro_client
        from reasoner.core.settings import settings

        client = get_neuro_client()
        resp = await client.post(
            f"{settings.internal_api_base_url}/neuro/recall",
            json={
                "prompt": problem,
                "agent_id": agent_id,
                "max_results": 5,
                "compression": "none",
            },
        )
        if resp.status_code == 200:
                data = resp.json()
                return [
                    {"content": c["content"], "source": c["source"], "relevance": c["relevance"]}
                    for c in data.get("chunks", [])
                ]
    except Exception as exc:
        logger.debug("Neuro recall failed, proceeding without memory: %s", exc)
    return []


async def run_stream(
    req: RunRequest,
    initial_state: PipelineState | None = None,
    user_id: str | None = None,
    preset_service: PresetService | None = None,
    pipeline_service: PipelineService | None = None,
) -> AsyncGenerator[str, None]:
    if preset_service is None:
        preset_service = _ensure_fresh_preset_service()
    if pipeline_service is None:
        from reasoner.application.services.pipeline_service import PipelineService
        pipeline_service = PipelineService()

    run_id = req.client_run_id or str(uuid.uuid4())
    event_version = 1
    state: PipelineState | None = None
    cancel_event = await _run_store.add(run_id, user_id=user_id)
    _save_pipeline_owner(run_id, user_id)
    try:
        # ── Neuro Recall ──
        recalled_chunks: list[dict[str, Any]] = []
        if not req.no_cache:
            conversation_id = initial_state.conversation_id if initial_state else None
            recalled_chunks = await _recall_neuro_context(req.problem, agent_id=conversation_id)
            if recalled_chunks:
                logger.info("Neuro recall returned %d chunks", len(recalled_chunks))
                yield _event({
                    "type": "recall_used",
                    "memory_count": len(recalled_chunks),
                    "memory_ids": [c.get("source", "") for c in recalled_chunks if c.get("source")],
                })
                # Emit domain event for neuro memory usage
                recall_evt = make_event(
                    EventType.MEMORY_RECALLED,
                    aggregate_id=run_id,
                    version=event_version,
                    query=req.problem,
                    chunks_found=len(recalled_chunks),
                    latency_ms=0.0
                )
                await _persist_event(recall_evt)
                event_version += 1

        raw_preset = req.preset or "auto-budget"
        preset_svc = _ensure_fresh_preset_service()
        gate_preset_name, is_auto, auto_tier = preset_svc.resolve(raw_preset)
        auto_selected_method: str | None = None

        agent_model = initial_state.agent_model if initial_state else None
        effective_preset_name, router = preset_svc.build_router(
            gate_preset_name,
            custom_routing=req.routing,
            agent_model=agent_model,
        )
        # DEBUG: log a few routing entries so we can verify presets are fresh
        # Defensive: test fakes may use _primary instead of primary (see _stream_direct_answer)
        _primary_for_log = getattr(router, "primary", None) or getattr(router, "_primary", None)
        _routing_table = getattr(router, "routing_table", {})
        logger.info(
            "Preset '%s' primary=%s sample_routing=%s",
            effective_preset_name,
            getattr(_primary_for_log, "model", "unknown") if _primary_for_log else "unknown",
            {k: _routing_table.get(k).model if _routing_table.get(k) else None for k in list(_routing_table)[:3]},
        )

        if not req.force_pipeline:
            gate = HyperGateAgent(router)
            decision = await gate.decide(req.problem)
            if decision.action == "direct":
                async for chunk in _stream_direct_answer(
                    router, req.problem, run_id, cancel_event,
                    conversation_history=initial_state.conversation_history if initial_state else None,
                    previous_synthesis=initial_state.previous_synthesis if initial_state else "",
                    turn_number=initial_state.turn_number if initial_state else 1,
                    preset_name=effective_preset_name,
                ):
                    yield chunk
                return
            if decision.action == "web_search":
                async for chunk in _stream_web_search_results(req.problem, run_id, cancel_event=cancel_event):
                    yield chunk
                return

            if is_auto and decision.method and not req.routing:
                preset_svc = _ensure_fresh_preset_service()
                effective_preset_name, router = preset_svc.build_auto_router(
                    decision.method,
                    auto_tier,
                    agent_model=agent_model,
                )
                auto_selected_method = decision.method

        pipeline = pipeline_service.create_pipeline(
            router=router,
            preset_name=effective_preset_name,
            top_k=req.top_k,
            parallel_perspectives=(not req.sequential) if "multi-perspective" not in effective_preset_name else True,
            source_type=req.source_type,
            domain=req.domain,
            enhance_prompt=req.enhance_prompt,
            complexity=getattr(req, "complexity", None),
            batch_critique_jury=getattr(req, "batch_critique_jury", False),
            initial_state=initial_state,
        )
        state = initial_state or PipelineState(problem=req.problem, preset_name=effective_preset_name)
        if recalled_chunks:
            state.neuro_context = recalled_chunks

        # --- BRAINSTORMING CONFIG: inject VS runtime parameters from preset metadata
        # before any phase runs so _phase_brainstorm_generate can read them.
        from reasoner.domain.preset_registry import PRESETS as _PRESETS
        _bs_preset = _PRESETS.get(effective_preset_name)
        if _bs_preset and _bs_preset.brainstorming_config:
            state.brainstorming_state["config"] = _bs_preset.brainstorming_config
            logger.debug(f"Injected brainstorming config: {_bs_preset.brainstorming_config}")

        # --- ARTICLE DETECTION: must happen BEFORE the start event so the frontend
        # receives auto_selected_method="writing" and renders the correct phase list.
        from reasoner.phases._shared import is_article_request
        if is_article_request(state.problem):
            state.task_type = TaskType.TECHNICAL
            state.decomposition = ["article workflow"]
            state.method = "writing"
            auto_selected_method = "writing"
            logger.info("Article request detected in stream — routing to writing method")

        logger.info(f"Pipeline start with routing: {router.describe()}")
        start_payload: dict = {"type": "start", "preset": effective_preset_name}
        if auto_selected_method:
            start_payload["auto_selected_method"] = auto_selected_method
        await _broadcast_ws(run_id, start_payload)
        yield _event(start_payload)

        # Persist pipeline start event
        start_evt = make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id=run_id,
            version=event_version,
            problem=req.problem,
            preset=effective_preset_name,
            method=get_method_from_preset(effective_preset_name) or "multi-perspective",
            options={"top_k": req.top_k, "source_type": req.source_type, "user_id": user_id},
        )
        await _persist_event(start_evt)
        event_version += 1

        if req.enhance_prompt and not state.enhanced_problem:
            try:
                await pipeline._phase_enhance_prompt(state)
                if state.enhanced_problem and state.enhanced_problem != state.problem:
                    yield _event({"type": "prompt_enhanced", "original": state.problem, "enhanced": state.enhanced_problem})
            except Exception as exc:
                logger.warning("Prompt enhancement failed, using original: %s", exc)
                state.enhanced_problem = state.problem

        # ── Context Vetting Serializer ───────────────────────────────────
        def _ser_context_vetting(state: PipelineState) -> dict:
            vetted = getattr(state, "vetted_context", None) or getattr(state, "web_discovery_results", None) or []
            return {
                "context_quality": getattr(state, "context_quality", "unknown"),
                "vetted_context": vetted[:10],
                "tokens": state.phase_tokens.get("Phase 1.25: Context Vetting", {"input": 0, "output": 0}),
            }

        from reasoner.application.flows.search_phases import run_context_vetting_phase
        from reasoner.application.flows.services import PipelineWorkflowServices
        _services = PipelineWorkflowServices(pipeline)

        async def _run_context_vetting(state: PipelineState):
            await run_context_vetting_phase(state, _services, source_type=req.source_type)

        from reasoner.application.flows.factory import WorkflowFactory
        flow_factory = WorkflowFactory()
        method = state.method or pipeline._get_method_from_preset()
        strategy = flow_factory.get_strategy(method)
        
        step_metadata: dict[str, dict[str, Any]] = {}
        if strategy:
            for step in strategy.get_phases(state):
                
                # Wrap the step function so that it accepts only (state)
                # and calls the strategy function with (state, _services)
                def make_wrapper(fn):
                    async def wrapper(state: PipelineState):
                        await fn(state, _services)
                    return wrapper
                    
                phases.append((step.num, step.name, make_wrapper(step.fn), step.serializer))
                step_metadata[step.name] = {"critical": step.critical}
        else:
            logger.error(f"No strategy found for method: {method}")

        last_phase_num = max(p[0] for p in phases) if phases else 5
        synthesis_phase_num = last_phase_num + 1
        if state.method != "writing":
            phases += [(synthesis_phase_num, "Synthesis", pipeline._phase_synthesis, _ser_synthesis)]

        _LEGACY_CRITICAL = {
            "Decomposition", "Perspectives", "Opening Statements",
            "Hypotheses", "Maieutic Questions", "Generation Pool",
            "Deep Research", "Retrieve Sources", "Adversarial Verify",
        }
        
        # Determine if a phase is critical:
        # 1. Is it explicitly marked critical in the Flow Registry?
        # 2. Is it in the legacy critical set?
        CRITICAL_PHASES = {
            name for _, name, _, _ in phases 
            if step_metadata.get(name, {}).get("critical") or name in _LEGACY_CRITICAL
        }

        _PHASE_ROLE_HINTS: dict[str, list[str]] = {
            "Classification": ["classification"],
            "Decomposition": ["decomposition"],
            "Deep Read": ["primary"],
            "Perspectives": ["constructive", "destructive", "systemic", "minimalist"],
            "Opening Statements": ["constructive", "destructive"],
            "Rebuttals": ["constructive", "destructive"],
            "Cross-Examination": ["systemic"],
            "Hypotheses": ["primary"],
            "Falsification Tests": ["scoring"],
            "Maieutic Questions": ["destructive"],
            "Dialectic Answers": ["constructive"],
            "Generation Pool": ["generator_1", "generator_2", "generator_3"],
            "Critic Pool": ["critic_1", "critic_2", "critic_3"],
            "Verification & Meta": ["verifier", "meta_evaluator"],
            "Deep Research": ["primary"],
            "Critique & Pruning": ["scoring"],
            "Stress Testing": ["stress_testing"],
            "Synthesis": ["synthesis"],
            # Article-specific roles
            "Decompose Topic": ["article_decompose"],
            "Retrieve Sources": ["primary"],
            "Extract Claims (CoVE)": ["article_claim_extract"],
            "Adversarial Verify": ["article_verifier"],
            "Synthesize (SoT)": ["article_synthesize"],
            "Pre-Mortem": ["article_pre_mortem"],
            "Journal Review": ["article_critic"],
            "Final Assembly": ["article_assemble"],
            "Humanize": ["article_humanize"],
        }

        def _get_phase_start_models(phase_name: str) -> list[str]:
            roles = _PHASE_ROLE_HINTS.get(phase_name, [])
            models: list[str] = []
            for role in roles:
                try:
                    provider = router.get(role)
                    if provider and hasattr(provider, "model") and provider.model and provider.model not in models:
                        models.append(provider.model)
                except Exception:
                    continue
            return models

        async def _run_phase_cancellable(
            coro_fn, state: PipelineState, timeout_seconds: float = 90.0
        ) -> bool:
            """Run a phase coroutine; cancel it if cancel_event fires or timeout expires.

            Returns True if cancelled by user, False if completed.
            Raises asyncio.TimeoutError if the phase exceeds timeout_seconds.
            """
            phase_task = asyncio.ensure_future(coro_fn(state))
            cancel_task = asyncio.ensure_future(cancel_event.wait())
            timeout_task = asyncio.ensure_future(asyncio.sleep(timeout_seconds))
            done, pending = await asyncio.wait(
                {phase_task, cancel_task, timeout_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
            if timeout_task in done:
                # Timeout expired — cancel the phase task
                if not phase_task.done():
                    phase_task.cancel()
                    try:
                        await phase_task
                    except (asyncio.CancelledError, Exception):
                        pass
                raise asyncio.TimeoutError(
                    f"Phase timed out after {timeout_seconds}s"
                )
            if cancel_task in done:
                # User cancelled — cancel the phase task if still running
                if not phase_task.done():
                    phase_task.cancel()
                    try:
                        await phase_task
                    except (asyncio.CancelledError, Exception):
                        pass
                return True
            # Phase finished — propagate any exception
            exc = phase_task.exception()
            if exc:
                raise exc
            return False

        async def _run_phase_with_keepalive(
            coro_fn, state: PipelineState, timeout_seconds: float = 90.0,
            keepalive_interval: float = 15.0,
        ):
            """Async generator: runs a phase and yields SSE keepalive comments every
            keepalive_interval seconds so the browser/proxy never sees an idle connection."""
            phase_task = asyncio.ensure_future(coro_fn(state))
            cancel_watch = asyncio.ensure_future(cancel_event.wait())
            deadline = time.monotonic() + timeout_seconds
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        if not phase_task.done():
                            phase_task.cancel()
                            try:
                                await phase_task
                            except (asyncio.CancelledError, Exception):
                                pass
                        raise asyncio.TimeoutError(
                            f"Phase timed out after {timeout_seconds}s"
                        )
                    wait = min(keepalive_interval, remaining)
                    done, _ = await asyncio.wait(
                        {phase_task, cancel_watch},
                        timeout=wait,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if cancel_watch in done:
                        if not phase_task.done():
                            phase_task.cancel()
                            try:
                                await phase_task
                            except (asyncio.CancelledError, Exception):
                                pass
                        return
                    if phase_task in done:
                        exc = phase_task.exception()
                        if exc:
                            raise exc
                        return
                    # Phase still running — send a keepalive SSE comment
                    yield ": keepalive\n\n"
            finally:
                for t in (phase_task, cancel_watch):
                    if not t.done():
                        t.cancel()
                        try:
                            await t
                        except (asyncio.CancelledError, Exception):
                            pass

        phase_monitor = PhaseMonitor(router, preset_name=req.preset)
        run_start = time.monotonic()
        for num, name, fn, serializer in phases:
            if cancel_event.is_set():
                yield _event({"type": "cancelled", "message": "Pipeline stopped by user"})
                return

            # Silent no-ops (e.g. writing pipeline skips generic decomposition/vetting)
            if getattr(fn, "_is_silent_noop", False) is True:
                await fn(state)
                continue

            phase_key = f"Phase {num}: {name}"
            state._current_phase_key = phase_key
            phase_start_models = _get_phase_start_models(name)
            start_payload: dict[str, Any] = {"type": "phase_start", "phase": num, "name": name}
            if phase_start_models:
                start_payload["models"] = phase_start_models
            await _broadcast_ws(run_id, start_payload)
            yield _event(start_payload)

            max_retries = get_phase_retry_budget(name)
            quality_result = None
            phase_errored = False
            phase_fatal = False
            phase_start = time.monotonic()

            for retry_attempt in range(max_retries + 1):
                try:
                    phase_timeout = get_phase_timeout(name)
                    async for _ka in _run_phase_with_keepalive(fn, state, timeout_seconds=phase_timeout):
                        yield _ka
                    if cancel_event.is_set():
                        yield _event({"type": "cancelled", "message": "Pipeline stopped by user"})
                        return
                    # Success — break the retry loop
                    break
                except asyncio.TimeoutError:
                    logger.error("Phase %s (%s) timed out after %ss", num, name, phase_timeout)
                    err_msg = f"Phase timeout: {name} exceeded {phase_timeout}s"
                    state.errors.append(err_msg)
                    err_payload = {
                        "type": "error",
                        "error_type": "timeout",
                        "message": err_msg,
                        "retryable": True,
                        "retry_after": 5,
                        "phase": num,
                        "phase_name": name,
                    }
                    await _broadcast_ws(run_id, err_payload)
                    yield _event(err_payload)
                    await _broadcast_ws(run_id, {"type": "phase_error", "phase": num, "error": err_msg})
                    yield _event({"type": "phase_error", "phase": num, "error": err_msg})
                    fail_evt = make_event(
                        EventType.PHASE_FAILED,
                        aggregate_id=run_id,
                        version=event_version,
                        phase_name=name,
                        error=err_msg,
                    )
                    await _persist_event(fail_evt)
                    event_version += 1
                    phase_errored = True
                    phase_fatal = name in CRITICAL_PHASES
                    break
                except Exception as exc:
                    logger.error("Phase %s (%s) failed: %s", num, name, exc, exc_info=True)
                    err_type = classify_error(exc)
                    if err_type == "auth":
                        err_msg = (
                            "OpenRouter API key is missing or invalid. "
                            "Please set OPENROUTER_API_KEY in your .env or ui-next/.env.local file."
                        )
                    else:
                        err_msg = f"{type(exc).__name__}: {str(exc)[:120]}"
                    state.errors.append(err_msg)
                    err_payload = {
                        "type": "error",
                        "error_type": err_type,
                        "message": err_msg,
                        "retryable": is_retryable(exc),
                        "retry_after": getattr(exc, 'retry_after', None),
                        "phase": num,
                        "phase_name": name,
                    }
                    await _broadcast_ws(run_id, err_payload)
                    yield _event(err_payload)
                    await _broadcast_ws(run_id, {"type": "phase_error", "phase": num, "error": err_msg})
                    yield _event({"type": "phase_error", "phase": num, "error": err_msg})
                    fail_evt = make_event(
                        EventType.PHASE_FAILED,
                        aggregate_id=run_id,
                        version=event_version,
                        phase_name=name,
                        error=err_msg,
                    )
                    await _persist_event(fail_evt)
                    event_version += 1
                    phase_errored = True
                    phase_fatal = err_type == "auth" or name in CRITICAL_PHASES
                    break

                # Phase executed successfully — run quality check
                quality_result = await phase_monitor.evaluate(name, state, attempt=retry_attempt + 1)
                quality_payload = {
                    "type": "phase_quality",
                    "phase": num,
                    "name": name,
                    "score": quality_result.score,
                    "passed": quality_result.passed,
                    "reason": quality_result.reason,
                    "attempt": retry_attempt + 1,
                }
                yield _event(quality_payload)
                await _broadcast_ws(run_id, quality_payload)

                # Record quality score in state history for downstream context
                state.quality_history.append({
                    "phase": name,
                    "attempt": retry_attempt + 1,
                    "score": quality_result.score,
                    "passed": quality_result.passed,
                })

                if quality_result.passed or retry_attempt >= max_retries:
                    break

                # Quality failed and budget remains — inject hints and emit retry event
                if quality_result.suggestions:
                    state.quality_hints[name] = " ".join(quality_result.suggestions)

                retry_payload = {
                    "type": "phase_retry",
                    "phase": num,
                    "name": name,
                    "attempt": retry_attempt + 1,
                    "max_attempts": max_retries + 1,
                    "reason": quality_result.reason,
                }
                yield _event(retry_payload)
                await _broadcast_ws(run_id, retry_payload)

                reset_phase_state(name, state)

            # Clear quality hints for this phase regardless of outcome
            state.quality_hints.pop(name, None)

            if phase_fatal:
                break
            if phase_errored:
                continue

            duration = time.monotonic() - phase_start
            while state.pending_events:
                ev = state.pending_events.pop(0)
                yield _event(ev)
            state.phase_durations[phase_key] = duration
            if name == "Synthesis":
                core = ""
                if state.final_solution and hasattr(state.final_solution, "core_solution"):
                    core = state.final_solution.core_solution or ""
                if core:
                    import re
                    sentences = re.split(r'(?<=[.!?])\s+', core)
                    for sentence in sentences:
                        if cancel_event and cancel_event.is_set():
                            break
                        yield _event({"type": "text_chunk", "text": sentence})
            data = serializer(state)
            if isinstance(data, dict):
                data["tokens"] = state.phase_tokens.get(phase_key, {"input": 0, "output": 0})
                data["duration"] = duration
                phase_models = state.cost_state._phase_models_by_key.get(phase_key, [])
                if phase_models:
                    data["models"] = phase_models
                subagent_outputs = _get_phase_subagents(state, name)
                if subagent_outputs:
                    data["subagents"] = [
                        {
                            "name": s.get("agent_name", "unknown"),
                            "model": s.get("model", "unknown"),
                            "tokens_in": s.get("tokens_in", 0),
                            "tokens_out": s.get("tokens_out", 0),
                            "duration_ms": s.get("duration_ms", 0),
                            "error": s.get("error"),
                        }
                        for s in subagent_outputs
                    ]
                if quality_result:
                    data["quality"] = {
                        "score": quality_result.score,
                        "passed": quality_result.passed,
                    }
            phase_complete_payload = {
                "type": "phase_complete",
                "phase": num,
                "name": name,
                "data": data,
            }
            await _broadcast_ws(run_id, phase_complete_payload)
            yield _event(phase_complete_payload)

            complete_evt = make_event(
                EventType.PHASE_COMPLETED,
                aggregate_id=run_id,
                version=event_version,
                phase_name=name,
                result={"data": data},
                tokens=state.phase_tokens.get(phase_key, {"input": 0, "output": 0}),
                model_used=",".join(state.cost_state._phase_models_by_key.get(phase_key, [])) or "unknown",
                duration_seconds=duration,
            )
            await _persist_event(complete_evt)
            event_version += 1

        token_source = state.detailed_token_usage if state.detailed_token_usage else state.phase_tokens
        total_input = sum(t.get("input", 0) for t in token_source.values())
        total_output = sum(t.get("output", 0) for t in token_source.values())
        total_tokens = total_input + total_output

        try:
            from datetime import datetime, timezone

            ts = datetime.now(timezone.utc).isoformat()
            entry = HistoryEntry(
                id=hashlib.sha256(f"{req.problem}{ts}".encode()).hexdigest()[:16],
                user_id=user_id,
                problem=req.problem[:TRUNCATION.API_STORAGE],
                preset=req.preset,
                method=get_method_from_preset(req.preset),
                timestamp=ts,
                tokens={"input": total_input, "output": total_output, "total": total_tokens},
                status="completed" if not state.errors else "error",
            )
            _save_history_entry(entry)

            try:
                from reasoner.core.memory import TaggedMemory

                tagged = TaggedMemory(HISTORY_DIR)
                method_tag = f"method:{entry.method}"
                preset_tag = f"preset:{entry.preset}"
                tagged.add(method_tag, entry.model_dump())
                tagged.add(preset_tag, entry.model_dump())
            except Exception as tag_err:
                logger.warning(f"Failed to save tagged history: {tag_err}")
        except Exception as e:
            logger.warning(f"Failed to save history: {e}")

        done_payload = {
            "type": "done",
            "errors": state.errors,
            "total_tokens": {"input": total_input, "output": total_output, "total": total_tokens},
            "duration": time.monotonic() - run_start,
            "total_cost_usd": getattr(state, 'total_cost_usd', 0.0),
            "phase_costs": getattr(state, 'phase_costs', {}),
        }
        await _broadcast_ws(run_id, done_payload)
        yield _event(done_payload)

        # Persist pipeline completion
        done_evt = make_event(
            EventType.PIPELINE_COMPLETED,
            aggregate_id=run_id,
            version=event_version,
            solution={"core_solution": getattr(state.final_solution, 'core_solution', '') if state.final_solution else ''},
            total_tokens={"input": total_input, "output": total_output},
            total_duration_seconds=time.monotonic() - run_start,
            phases_completed=len(state.phase_durations),
        )
        await _persist_event(done_evt)

        # ── Neuro Persist (main pipeline) ──
        try:
            from reasoner.api.clients import get_neuro_client
            from reasoner.core.settings import settings

            client = get_neuro_client()
            await client.post(
                f"{settings.internal_api_base_url}/neuro/learn",
                json={
                    "prompt": req.problem,
                    "response": (
                        state.final_solution.core_solution
                        if state.final_solution
                        else getattr(state, 'previous_synthesis', '')
                    ),
                    "agent_id": getattr(state, 'conversation_id', None),
                    "metadata": {
                        "preset": effective_preset_name,
                        "tokens": {"input": total_input, "output": total_output},
                        "type": "pipeline",
                    },
                },
                timeout=5.0,
            )
        except Exception:
            pass

    except Exception as exc:
        logger.error("Pipeline error for run %s: %s", run_id, exc, exc_info=True)
        err_msg = f"Pipeline processing error: {type(exc).__name__}: {str(exc)[:120]}"
        
        # Persist pipeline failure
        fail_evt = make_event(
            EventType.PIPELINE_FAILED,
            aggregate_id=run_id,
            version=event_version,
            error=err_msg,
            phase_at_failure=getattr(state, '_current_phase_key', 'unknown') if state else 'unknown',
            phases_completed=len(state.phase_durations) if state else 0,
        )
        await _persist_event(fail_evt)

        await _broadcast_ws(run_id, {"type": "done", "errors": [err_msg]})
        yield _event({"type": "done", "errors": [err_msg]})
    finally:
        await _run_store.remove(run_id)


async def run_followup_stream(
    req: FollowupRequest, user_id: str | None = None
) -> AsyncGenerator[str, None]:
    """Run the full Reasoner pipeline for a follow-up question with conversation context."""
    from reasoner.presets import FOLLOWUP_AGENT_MODELS

    tier = get_preset_price_tier(req.preset)
    agent_model = req.agent_model or FOLLOWUP_AGENT_MODELS.get(tier)
    if agent_model:
        logger.info("Follow-up tier=%s -> agent_model=%s", tier, agent_model)

    state = PipelineState(
        problem=req.question,
        preset_name=req.preset,
        conversation_id=req.conversation_id,
        conversation_history=req.history,
        previous_synthesis=req.previous_synthesis,
        turn_number=(len(req.history) // 2) + 1,
        agent_model=agent_model,
    )
    run_req = RunRequest(
        problem=req.question,
        preset=req.preset,
        top_k=req.top_k,
        sequential=req.sequential,
        enhance_prompt=req.enhance_prompt,
        expert=req.expert,
        web_search=req.web_search,
        smart_search=req.smart_search,
        attachments=getattr(req, "attachments", []) or [],
        client_run_id=req.client_run_id,
    )
    async for chunk in run_stream(run_req, initial_state=state, user_id=user_id):
        yield chunk

    try:
        from reasoner.api.clients import get_neuro_client
        from reasoner.core.settings import settings

        client = get_neuro_client()
        await client.post(
            f"{settings.internal_api_base_url}/neuro/learn",
            json={
                "prompt": req.question,
                "response": (
                    state.final_solution.core_solution
                    if state.final_solution
                    else state.previous_synthesis
                ),
                "agent_id": req.conversation_id,
                "metadata": {
                    "turn_number": state.turn_number,
                    "preset": req.preset,
                    "agent_model": state.agent_model,
                    "type": "followup",
                },
            },
            timeout=5.0,
        )
    except Exception:
        pass


async def run_stream_cached(
    req: RunRequest, 
    user_id: str | None = None,
    preset_service: PresetService | None = None,
    pipeline_service: PipelineService | None = None,
) -> AsyncGenerator[str, None]:
    if preset_service is None:
        from reasoner.application.services.preset_service import PresetService
        preset_service = PresetService()
    if pipeline_service is None:
        from reasoner.application.services.pipeline_service import PipelineService
        pipeline_service = PipelineService()

    key = _cache_key(req)
    if not req.no_cache:
        cached = await _load_cache(key)
        if cached:
            has_fatal_error = any(ev.get("type") == "done" and ev.get("errors") for ev in cached)
            # Also skip cache replay if any phase had errors — code may have been fixed
            has_phase_error = any(
                ev.get("type") == "phase_complete" and ev.get("data", {}).get("error")
                for ev in cached
            )
            if not has_fatal_error and not has_phase_error:
                for ev in cached:
                    yield _event({**ev, "cached": True} if ev.get("type") == "start" else ev)
                    if ev.get("type") in ("phase_start", "phase_complete"):
                        await asyncio.sleep(SSE_FLUSH_INTERVAL)
                return
            else:
                logger.info(f"Ignoring cached result for {key} due to stored errors.")

    collected: list[dict] = []
    async for chunk in run_stream(req, user_id=user_id):
        yield chunk
        if chunk.startswith("data: "):
            try:
                ev = json.loads(chunk[6:])
                collected.append(ev)
                if ev.get("type") == "done" and not req.no_cache:
                    await _save_cache(key, collected)
            except Exception:
                pass
