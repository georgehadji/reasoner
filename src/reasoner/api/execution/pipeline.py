
import asyncio
import contextlib
import hashlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC

from reasoner.api.execution.cancel import StreamingConnectionContext
from reasoner.api.execution.direct import _stream_direct_answer
from reasoner.api.execution.sse_observer import keepalive_ticker
from reasoner.api.execution.web_search import _stream_web_search_results
from reasoner.api.history import HISTORY_DIR, HistoryEntry, _save_history_entry
from reasoner.api.schemas import RunRequest
from reasoner.api.sse_utils import _persist_event
from reasoner.application.commands import RunPipelineCommand
from reasoner.application.orchestrator import PipelineOrchestrator
from reasoner.application.services.adaptive_routing import build_adaptive_routing_service
from reasoner.application.services.pipeline_service import PipelineService
from reasoner.application.services.preset_service import PresetService
from reasoner.application.services.spend_limit_service import (
    apply_spend_limits,
    check_run_allowed,
    resolve_user_tier,
)
from reasoner.core.constants import TRUNCATION
from reasoner.core.events.domain_events import EventType, make_event
from reasoner.core.exceptions import classify_error, error_code_for_exception
from reasoner.core.logging_utils import set_correlation_id
from reasoner.domain.models import TaskType
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.infrastructure.persistence.pipeline_ownership_repo import get_pipeline_ownership_repo
from reasoner.infrastructure.redis.run_state import _run_state_manager as _run_store
from reasoner.presets import get_method_from_preset
from reasoner.quality import PhaseMonitor

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

        run_id = req.client_run_id or str(uuid.uuid4())
        set_correlation_id(run_id)
        event_version = 1
        state: PipelineState | None = None
        cancel_event = await _run_store.add(run_id, user_id=user_id)
        try:
            await get_pipeline_ownership_repo().set_owner(run_id, user_id, run_id)
        except Exception:
            # An ownership-write failure must not abort the run itself, but it
            # does mean the pipeline stays inaccessible (fail closed) until a
            # human intervenes -- log loudly rather than silently swallow it.
            logger.error(
                "Failed to record pipeline ownership for %s; pipeline will be "
                "inaccessible via ownership checks until this is fixed",
                run_id,
                exc_info=True,
            )

        # Track per-run WS broadcast tasks so they can be cancelled on disconnect (B-13)
        conn_context = StreamingConnectionContext(run_id)

        def _tracked_broadcast(run_id: str, payload: dict) -> None:
            conn_context.tracked_broadcast(payload)

        # Keepalive comments used to be punctuated from inside one phase by
        # run_phase_with_keepalive, so a run that idled anywhere else -- in
        # preflight, in neuro recall, between phases -- sent nothing and a
        # proxy was free to drop the connection. The ticker covers the whole
        # run instead, and only fires when the stream has actually gone quiet.
        sse_emit, _keepalive = keepalive_ticker(sse_emit)

        # Yield a "connecting" event immediately so the UI has content to render
        # while the preflight (HyperGate LLM calls) completes.
        await sse_emit({"type": "connecting", "message": "Running system check…"})
        keepalive_task = asyncio.ensure_future(_keepalive())
        try:
            # Resolve the caller's plan up front — the spend ceilings it implies
            # gate the run below and bound every LLM call inside it.
            user_tier = await resolve_user_tier(user_id)

            # ── Orchestrator Preflight: preset resolution, HyperGate, neuro recall ──
            orchestrator = PipelineOrchestrator(
                preset_service,
                pipeline_service,
                adaptive_routing=build_adaptive_routing_service(),
            )
            preflight = await orchestrator.preflight(req, initial_state, user_id=user_id)

            if preflight.gate_reasoning:
                await sse_emit({
                    "type": "method_selected",
                    "data": {
                        "action": preflight.action,
                        "method": preflight.auto_selected_method,
                        "confidence": preflight.gate_confidence,
                        "reasoning": preflight.gate_reasoning,
                        "alternatives": preflight.gate_alternatives,
                    },
                })

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
                # Route through OpenRouter web_search when enabled
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

            # Refuse a run the caller's plan cannot pay for. Checked against the
            # preset preflight actually resolved, not the one requested — auto
            # presets only settle on a tier here.
            rejection = check_run_allowed(effective_preset_name, user_tier, user_id)
            if rejection is not None:
                logger.info(
                    "Run %s refused: %s cap for tier %s (preset %s)",
                    run_id, rejection.cap_type, user_tier.value, effective_preset_name,
                )
                await sse_emit({
                    "type": "error",
                    "error": rejection.reason,
                    "code": (
                        "PRESET_TIER_REQUIRED"
                        if rejection.cap_type == "preset_tier"
                        else "SPEND_LIMIT_EXCEEDED"
                    ),
                    "data": {
                        "cap_type": rejection.cap_type,
                        "cap_usd": round(rejection.cap_usd, 4),
                        "estimated_usd": round(rejection.estimated_usd, 4),
                        "tier": rejection.tier.value,
                        "required_tier": (
                            rejection.required_tier.value
                            if rejection.required_tier else None
                        ),
                        "upgrade_url": "/pricing",
                    },
                })
                return

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
                user_id=user_id,
            )
            state = initial_state or PipelineState(problem=req.problem, preset_name=effective_preset_name)
            # Carry the ceilings into the run so the executor halts mid-pipeline
            # if the accumulated cost crosses one.
            apply_spend_limits(state, user_tier, user_id)
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
                EventEmissionService,
                set_event_emitter,
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

            from reasoner.application.flows.factory import WorkflowFactory
            from reasoner.application.flows.runner import WorkflowRunner
            from reasoner.application.flows.services import PipelineWorkflowServices

            flow_factory = WorkflowFactory()
            method = state.method or pipeline._get_method_from_preset()
            strategy = flow_factory.get_strategy(method)

            run_start = time.monotonic()
            if strategy is None:
                logger.error(f"No strategy found for method: {method}")
            else:
                # One engine. This used to be a second phase loop -- its own
                # retries, timeouts, quality gate and fatality rule -- kept here
                # only so SSE frames could be emitted between the steps. The
                # frames are now an observer; WorkflowRunner runs the phases for
                # this driver exactly as it does for the CLI.
                from reasoner.api.execution.sse_observer import SseRunObserver
                from reasoner.core.observability.phase_span import PhaseSpan

                observer = SseRunObserver(
                    run_id=run_id,
                    sse_emit=sse_emit,
                    broadcast=_tracked_broadcast,
                    router=router,
                    emitter=emitter,
                    preset_name=req.preset or "",
                    event_version=event_version,
                )

                def _span(step, st):
                    return PhaseSpan(
                        run_id,
                        phase_name=step.name,
                        phase_number=step.num,
                        router=router,
                        state=st,
                    )

                runner = WorkflowRunner(
                    PipelineWorkflowServices(pipeline),
                    monitor=PhaseMonitor(router, preset_name=req.preset),
                    observer=observer,
                    span_factory=_span,
                )
                # Circular by nature: the runner needs services, and the services
                # need the runner so run_phase() delegates instead of taking its
                # bare `await step.fn(...)` fallback.
                runner.services = PipelineWorkflowServices(pipeline, runner=runner)

                # Cancellation is a driver concern, so it stays out of the
                # runner: a watcher cancels the run task, which propagates into
                # whichever phase coroutine is in flight.
                run_task = asyncio.ensure_future(runner.run(strategy, state))
                cancel_watch = asyncio.ensure_future(cancel_event.wait())
                done, _ = await asyncio.wait(
                    {run_task, cancel_watch}, return_when=asyncio.FIRST_COMPLETED
                )
                if cancel_watch in done:
                    run_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await run_task
                    await sse_emit({"type": "cancelled", "message": "Pipeline stopped by user"})
                    return
                cancel_watch.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await cancel_watch
                await run_task

                event_version = observer.event_version

            token_source = state.detailed_token_usage if state.detailed_token_usage else state.phase_tokens
            total_input = sum(t.get("input", 0) for t in token_source.values())
            total_output = sum(t.get("output", 0) for t in token_source.values())
            total_tokens = total_input + total_output

            try:
                from datetime import datetime

                ts = datetime.now(UTC).isoformat()
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
                    import re as _re

                    from reasoner.core.memory import TaggedMemory
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
                # Failures the run survived by falling back (P5). Distinct from
                # errors: nothing here stopped a phase, but the answer was
                # produced with less than the full machinery.
                "degradations": list(getattr(state, "degradations", []) or []),
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

            # Emit explicit error event (H4)
            err_payload = {
                "type": "error",
                "error_type": classify_error(exc),
                "error_code": error_code_for_exception(exc),
                "message": err_msg,
                "retryable": False,
                "phase": None,
                "phase_name": getattr(state, '_current_phase_key', 'unknown') if state else 'unknown',
            }
            _tracked_broadcast(run_id, err_payload)
            await sse_emit(err_payload)

            _tracked_broadcast(run_id, {"type": "done", "errors": [err_msg]})
            await sse_emit({"type": "done", "errors": [err_msg]})
        finally:
            keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive_task
            # Cancel all pending broadcast tasks for this run (B-13)
            await conn_context.cleanup()
            await _run_store.remove(run_id)
            # Close neuro HTTP client to prevent connection pool exhaustion
            try:
                from reasoner.clients import close_neuro_client
                await close_neuro_client()
            except Exception:
                pass
