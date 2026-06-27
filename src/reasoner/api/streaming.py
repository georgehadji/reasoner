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
    CREATIVE_MAX_TOKENS,
    CREATIVE_TEMPERATURE,
    DIRECT_ANSWER_MAX_TOKENS,
    DIRECT_ANSWER_TEMPERATURE,
    SSE_FLUSH_INTERVAL,
    TRUNCATION,
    get_phase_retry_budget,
    get_phase_timeout,
)
from reasoner.core.constants_models import (
    MODEL_CLAUDE_SONNET,
    MODEL_GEMINI_PRO,
    MODEL_GPT5,
    MODEL_KIMI_K2_6,
    MODEL_MISTRAL_LARGE_3,
    MODEL_QWEN36_PLUS,
)
from reasoner.quality import PhaseMonitor, reset_phase_state
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.domain.pipeline_state import PipelineState
from reasoner.models import TaskType
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.pipeline_service import PipelineService
from reasoner.application.services.search_service import SearchService
from reasoner.application.orchestrator import PipelineOrchestrator
from reasoner.exceptions import classify_error, is_retryable
from reasoner.core.exceptions import ErrorCode, error_code_for_exception
from reasoner.presets import (
    get_method_from_preset,
    get_preset_price_tier,
)
from reasoner.phases._shared import build_followup_context, _wrap_user_input

from .cache import _cache_key, _load_cache, _save_cache
from .history import HISTORY_DIR, HistoryEntry, _save_history_entry, _save_pipeline_owner
from reasoner.infrastructure.redis.run_state import _run_state_manager as _run_store
from reasoner.core.events.domain_events import make_event, EventType
from .schemas import FollowupRequest, RunRequest
# SSE protocol helpers shared across streaming endpoints.
from .sse_utils import _event, _broadcast_ws, _persist_event
from .phase_executor import (
    get_phase_start_models,
    get_critical_phases,
    run_phase_with_keepalive,
)

logger = logging.getLogger(__name__)



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



async def run_stream(
    req: RunRequest,
    initial_state: PipelineState | None = None,
    user_id: str | None = None,
    preset_service: PresetService | None = None,
    pipeline_service: PipelineService | None = None,
    request=None,
) -> AsyncGenerator[str, None]:
    from reasoner.application.commands import RunPipelineCommand
    from reasoner.application.handlers.handlers import get_handler_registry
    import asyncio
    import uuid
    
    run_id = req.client_run_id or str(uuid.uuid4())
    command = RunPipelineCommand(
        command_id=run_id,
        timestamp=time.time(),
        problem=req.problem,
        preset=req.preset,
        method=getattr(req, "method", None),
        top_k=getattr(req, "top_k", 2),
        source_type=getattr(req, "source_type", "general"),
        domain=getattr(req, "domain", None),
        parallel=not getattr(req, "sequential", False)
    )
    
    queue = asyncio.Queue(maxsize=256)
    
    async def sse_emit(event: dict | str) -> None:
        if isinstance(event, dict):
            await queue.put(_event(event))
        else:
            await queue.put(event)
            
    async def run_task():
        try:
            registry = get_handler_registry()
            handler = registry.command_handlers["RunPipelineCommand"]
            await handler.handle(command, sse_emit=sse_emit)
        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            await queue.put(None)
            
    task = asyncio.create_task(run_task())
    
    while True:
        chunk = await queue.get()
        if chunk is None:
            break
        yield chunk


async def run_followup_stream(
    req: FollowupRequest, request=None, user_id: str | None = None
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
    async for chunk in run_stream(run_req, initial_state=state, user_id=user_id, request=request):
        yield chunk

    try:
        from reasoner.clients import get_neuro_client
        from reasoner.core.settings import settings

        client = get_neuro_client()
        await client.post(
            f"{settings.internal_api_base_url}/api/neuro/learn",
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
    request=None,
    user_id: str | None = None,
    preset_service: PresetService | None = None,
    pipeline_service: PipelineService | None = None,
) -> AsyncGenerator[str, None]:
    if preset_service is None:
        preset_service = PresetService()
    if pipeline_service is None:
        from reasoner.application.services.pipeline_service import PipelineService
        pipeline_service = PipelineService()

    key = _cache_key(req, user_id=user_id)
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

    MAX_COLLECTED_EVENTS = 200  # cap in-memory buffer (v3.4)
    collected: list[dict] = []
    gen = run_stream(
        req,
        request=request,
        user_id=user_id,
        preset_service=preset_service,
        pipeline_service=pipeline_service,
    )
    try:
        async for chunk in gen:
            yield chunk
            await asyncio.sleep(SSE_FLUSH_INTERVAL)
            if chunk.startswith("data: "):
                try:
                    ev = json.loads(chunk[6:])
                    if len(collected) < MAX_COLLECTED_EVENTS:
                        collected.append(ev)
                    if ev.get("type") == "done" and not req.no_cache:
                        await _save_cache(key, collected)
                except Exception:
                    pass
    finally:
        await gen.aclose()