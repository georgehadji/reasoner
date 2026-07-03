"""Web search streaming execution."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from reasoner.application.services.search_service import SearchService
from reasoner.api.schemas import RunRequest
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.pipeline_service import PipelineService

_search_service = SearchService()

async def _stream_web_search_results(
    problem: str,
    run_id: str,
    num_results: int = 10,
    cancel_event: asyncio.Event | None = None,
) -> AsyncGenerator[str, None]:
    """Stream web search results as a virtual single-phase pipeline."""
    async for chunk in _search_service.stream_web_search_results(
        problem, run_id, num_results=num_results, cancel_event=cancel_event
    ):
        yield chunk





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
        problem=req.problem,
        preset=req.preset,
        method=getattr(req, "method", None),
        top_k=getattr(req, "top_k", 2),
        source_type=getattr(req, "source_type", "general"),
        domain=getattr(req, "domain", None),
        parallel=not getattr(req, "sequential", False)
    )
    
    queue = asyncio.Queue()
    
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
