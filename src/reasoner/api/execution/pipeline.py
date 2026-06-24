
import asyncio
import uuid
import logging
import time
import hashlib
import json
from typing import Callable, Awaitable, Any

from reasoner.application.commands import RunPipelineCommand
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.pipeline_service import PipelineService
from reasoner.application.orchestrator import PipelineOrchestrator
from reasoner.core.logging_utils import set_correlation_id
from reasoner.api.schemas import RunRequest
from reasoner.api.streaming import _get_phase_subagents
from reasoner.api.execution.direct import _stream_direct_answer
from reasoner.api.execution.web_search import _stream_web_search_results
from reasoner.api.history import HistoryEntry, _save_history_entry, _save_pipeline_owner, HISTORY_DIR
from reasoner.infrastructure.redis.run_state import _run_state_manager as _run_store
from reasoner.core.events.domain_events import make_event, EventType
from reasoner.api.sse_utils import _event, _broadcast_ws, _persist_event
from reasoner.api.phase_executor import get_phase_start_models, get_critical_phases, run_phase_with_keepalive
from reasoner.core.constants import TRUNCATION, get_phase_retry_budget, get_phase_timeout
from reasoner.exceptions import classify_error, is_retryable
from reasoner.core.exceptions import ErrorCode, error_code_for_exception
from reasoner.quality import PhaseMonitor, reset_phase_state
from reasoner.presets import get_method_from_preset

logger = logging.getLogger(__name__)

class PipelineExecutionService:
    async def execute_run(
        self,
        command: RunPipelineCommand,
        router: ProviderRouter,
        sse_emit: Callable[[dict | str], Awaitable[None]],
        user_id: str | None = None,
        initial_state: PipelineState | None = None
    ) -> PipelineState:
        # Reconstruct req for compatibility with existing code
        req = RunRequest(
            problem=command.problem,
            preset=command.preset,
            method=command.method,
            top_k=command.top_k,
            source_type=command.source_type,
            domain=command.domain,
            sequential=not command.parallel,
            client_run_id=command.command_id
        )
        
        preset_service = PresetService()
        pipeline_service = PipelineService()
        request = None
        

    from reasoner.core.settings import settings as _settings

    if preset_service is None:
        preset_service = PresetService()
    if pipeline_service is None:
        from reasoner.application.services.pipeline_service import PipelineService
        pipeline_service = PipelineService()

    run_id = req.client_run_id or str(uuid.uuid4())
    from reasoner.core.logging_utils import set_correlation_id
    set_correlation_id(run_id)
    event_version = 1
    state: PipelineState | None = None
    cancel_event = await _run_store.add(run_id, user_id=user_id)
    _save_pipeline_owner(run_id, user_id)

    # Track per-run WS broadcast tasks so they can be cancelled on disconnect (B-13)
    _run_tasks: set[asyncio.Task] = set()

    def _tracked_broadcast(run_id: str, payload: dict) -> None:
        coro = _broadcast_ws(run_id, payload, _tasks=_run_tasks)
        task = asyncio.create_task(coro)
        _run_tasks.add(task)
        task.add_done_callback(_run_tasks.discard)

    # Yield a "connecting" event immediately so the UI has content to render
    # while the preflight (HyperGate LLM calls) completes.
    await sse_emit({"type": "connecting", "message": "Running system check…"})
    try:
        # ── Orchestrator Preflight: preset resolution, HyperGate, neuro recall ──
        orchestrator = PipelineOrchestrator(preset_service, pipeline_service)
        preflight = await orchestrator.preflight(req, initial_state)

        if preflight.action == "direct":
            async for chunk in _stream_direct_answer(
                preflight.router, req.problem, run_id, cancel_event,
                conversation_history=preflight.conversation_history,
                previous_synthesis=preflight.previous_synthesis,
                turn_number=preflight.turn_number,
                preset_name=preflight.effective_preset_name,
            ):
                await sse_emit(chunk)
            return
        if preflight.action == "web_search":
            # Route through OpenRouter web_search when enabled (no SearXNG roundtrip)
            if _settings.OPENROUTER_WEB_SEARCH_ENABLED:
                async for chunk in _stream_direct_answer(
                    preflight.router, req.problem, run_id, cancel_event,
                    web_search=True,
                    preset_name=preflight.effective_preset_name,
                ):
                    await sse_emit(chunk)
            else:
                async for chunk in _stream_web_search_results(req.problem, run_id, cancel_event=cancel_event):
                    await sse_emit(chunk)
            return

        router = preflight.router
        effective_preset_name = preflight.effective_preset_name
        auto_selected_method = preflight.auto_selected_method
        recalled_chunks = preflight.recalled_chunks

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

        # ── Prism file_ids: extract from explicit file_ids or attachments ──
        file_ids = list(getattr(req, "file_ids", []) or [])
        if not file_ids and getattr(req, "attachments", None):
            file_ids = [a.file_id for a in req.attachments if getattr(a, "file_id", None)]
        if file_ids:
            state.method_state.set("prism", {
                **state.method_state.get("prism"),
                "file_ids": file_ids,
            })

        # ── Wire event bus for domain event sourcing ──
        from reasoner.application.event_bus.bus import get_event_bus
        from reasoner.application.services.event_emission_service import (
            EventEmissionService, set_event_emitter,
        )
        emitter = EventEmissionService(get_event_bus(), aggregate_id=run_id)
        set_event_emitter(emitter)

        # --- BRAINSTORMING CONFIG: inject VS runtime parameters from preset metadata
        # before any phase runs so _phase_brainstorm_generate can read them.
        from reasoner.presets import PRESETS as _PRESETS
        _bs_preset = _PRESETS.get(effective_preset_name)
        if _bs_preset and _bs_preset.brainstorming_config:
            state.brainstorming_state["config"] = _bs_preset.brainstorming_config
            logger.debug(f"Injected brainstorming config: {_bs_preset.brainstorming_config}")

        # --- ARTICLE DETECTION: only for auto-detected methods where the
        # orchestrator already set auto_selected_method to "writing".
        # Explicit presets (coding-budget, debate-budget, etc.) set their own
        # method — the orchestrator leaves auto_selected_method=None for them.
        if auto_selected_method == "writing":
            state.task_type = TaskType.TECHNICAL
            state.decomposition = ["article workflow"]
            state.method = "article"
            auto_selected_method = "article"
            logger.info("Article request detected in stream — routing to article method")

        logger.info(f"Pipeline start with routing: {router.describe()}")
        start_payload: dict = {"type": "start", "preset": effective_preset_name}
        if auto_selected_method:
            start_payload["auto_selected_method"] = auto_selected_method
        _tracked_broadcast(run_id, start_payload)
        await sse_emit(start_payload)

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

        # Emit domain event for pipeline start
        emitter.emit("PIPELINE_STARTED", problem=req.problem,
                      preset=effective_preset_name,
                      method=get_method_from_preset(effective_preset_name) or "multi-perspective")

        if req.enhance_prompt and not state.enhanced_problem:
            try:
                await pipeline._phase_enhance_prompt(state)
                if state.enhanced_problem and state.enhanced_problem != state.problem:
                    await sse_emit({"type": "prompt_enhanced", "original": state.problem, "enhanced": state.enhanced_problem})
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
        
        phases: list[tuple[int, str, Any, Any]] = []
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

        # CRITICAL_PHASES computed via get_critical_phases(phases, step_metadata)

        # _PHASE_ROLE_HINTS moved to api/phase_executor.py

# _get_phase_start_models moved to get_phase_start_models(phase_name, router)

# _run_phase_cancellable removed (unused)

        # _run_phase_with_keepalive moved to run_phase_with_keepalive(coro_fn, state, cancel_event, ...)
        phase_monitor = PhaseMonitor(router, preset_name=req.preset)
        run_start = time.monotonic()
        for num, name, fn, serializer in phases:
            if cancel_event.is_set():
                await sse_emit({"type": "cancelled", "message": "Pipeline stopped by user"})
                return

            # Disconnect detection (B-13): request.is_disconnected() calls
            # _receive() which blocks indefinitely during SSE streaming (POST
            # body already consumed, client sends no further data).  The ASGI
            # spec provides no non-blocking disconnect poll.
            #
            # Cleanup is instead handled by the finally block which cancels
            # all tracked broadcast tasks and removes the run from the store.
            # When the streaming response generator is garbage-collected
            # (client disconnect), aclose() propagates GeneratorExit into
            # run_stream(), triggering the existing finally block.

            # Silent no-ops (e.g. writing pipeline skips generic decomposition/vetting)
            if getattr(fn, "_is_silent_noop", False):  # v3.1: relaxed from identity check
                await fn(state)
                continue

            phase_key = f"Phase {num}: {name}"
            state._current_phase_key = phase_key
            phase_start_models = get_phase_start_models(name, router)
            start_payload: dict[str, Any] = {"type": "phase_start", "phase": num, "name": name}
            if phase_start_models:
                start_payload["models"] = phase_start_models
            _tracked_broadcast(run_id, start_payload)
            await sse_emit(start_payload)

            # Emit domain event for phase start
            emitter.emit("PHASE_STARTED", phase_name=name,
                          phase_number=num)

            max_retries = get_phase_retry_budget(name)
            quality_result = None
            phase_errored = False
            phase_fatal = False
            phase_start = time.monotonic()

            for retry_attempt in range(max_retries + 1):
                try:
                    phase_timeout = get_phase_timeout(name)
                    from reasoner.core.observability.phase_span import PhaseSpan
                    async with PhaseSpan(run_id, phase_name=name, phase_number=num, router=router, state=state):
                        async for _ka in run_phase_with_keepalive(fn, state, cancel_event, timeout_seconds=phase_timeout):
                            await sse_emit(_ka)
                    if cancel_event.is_set():
                        await sse_emit({"type": "cancelled", "message": "Pipeline stopped by user"})
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
                        "error_code": ErrorCode.PROVIDER_TIMEOUT.value,
                        "message": err_msg,
                        "retryable": True,
                        "retry_after": 5,
                        "phase": num,
                        "phase_name": name,
                    }
                    _tracked_broadcast(run_id, err_payload)
                    await sse_emit(err_payload)
                    _tracked_broadcast(run_id, {"type": "phase_error", "phase": num, "error": err_msg, "error_code": ErrorCode.PROVIDER_TIMEOUT.value})
                    await sse_emit({"type": "phase_error", "phase": num, "error": err_msg, "error_code": ErrorCode.PROVIDER_TIMEOUT.value})
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
                    emitter.emit("PHASE_FAILED", phase_name=name,
                                  error=err_msg)
                    phase_fatal = name in get_critical_phases(phases, step_metadata)
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
                    error_code = error_code_for_exception(exc)
                    err_payload = {
                        "type": "error",
                        "error_type": err_type,
                        "error_code": error_code,
                        "message": err_msg,
                        "retryable": is_retryable(exc),
                        "retry_after": getattr(exc, 'retry_after', None),
                        "phase": num,
                        "phase_name": name,
                    }
                    _tracked_broadcast(run_id, err_payload)
                    await sse_emit(err_payload)
                    _tracked_broadcast(run_id, {"type": "phase_error", "phase": num, "error": err_msg, "error_code": error_code})
                    await sse_emit({"type": "phase_error", "phase": num, "error": err_msg, "error_code": error_code})
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
                    emitter.emit("PHASE_FAILED", phase_name=name,
                                  error=err_msg)
                    phase_fatal = err_type == "auth" or name in get_critical_phases(phases, step_metadata)
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
                await sse_emit(quality_payload)
                _tracked_broadcast(run_id, quality_payload)

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
                await sse_emit(retry_payload)
                _tracked_broadcast(run_id, retry_payload)

                reset_phase_state(name, state)

            # Clear quality hints for this phase regardless of outcome
            state.quality_hints.pop(name, None)

            if phase_fatal:
                break
            if phase_errored:
                continue

            duration = time.monotonic() - phase_start
            for ev in emitter.pop_pending_events():
                await sse_emit(ev)
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
                        await sse_emit({"type": "text_chunk", "text": sentence})
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
            _tracked_broadcast(run_id, phase_complete_payload)
            await sse_emit(phase_complete_payload)

            # Emit domain event for phase completion
            emitter.emit("PHASE_COMPLETED", phase_name=name,
                          duration_seconds=duration,
                          tokens=state.phase_tokens.get(phase_key,
                              {"input": 0, "output": 0}))

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

                import re as _re
                _sanitize = lambda s: _re.sub(r'[^a-zA-Z0-9_-]', '_', s or 'unknown')
                tagged = TaggedMemory(HISTORY_DIR)
                method_tag = f"method_{_sanitize(entry.method)}"
                preset_tag = f"preset_{_sanitize(entry.preset)}"
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
        _tracked_broadcast(run_id, done_payload)
        await sse_emit(done_payload)

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

        # Emit domain event for pipeline completion
        emitter.emit("PIPELINE_COMPLETED", phases_completed=len(state.phase_durations))

        # ── Postflight: neuro persist ──
        await orchestrator.postflight(state, req, user_id=user_id, run_id=run_id)

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

        _tracked_broadcast(run_id, {"type": "done", "errors": [err_msg]})
        await sse_emit({"type": "done", "errors": [err_msg]})
    finally:
        # Cancel all pending broadcast tasks for this run (B-13)
        for t in list(_run_tasks):
            if not t.done():
                t.cancel()
        if _run_tasks:
            await asyncio.gather(*_run_tasks, return_exceptions=True)
        await _run_store.remove(run_id)



        
        return state
