
import asyncio
import contextlib
import hashlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC
from typing import Any

from reasoner.api.execution.cancel import StreamingConnectionContext
from reasoner.api.execution.direct import _stream_direct_answer
from reasoner.api.execution.sse_observer import RunStream
from reasoner.api.execution.web_search import _stream_web_search_results
from reasoner.api.history import HISTORY_DIR, HistoryEntry, _save_history_entry
from reasoner.api.schemas import RunRequest
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
from reasoner.core.logging_utils import set_correlation_id
from reasoner.domain.models import TaskType
from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.router import ProviderRouter
from reasoner.infrastructure.persistence.pipeline_ownership_repo import get_pipeline_ownership_repo
from reasoner.infrastructure.redis.run_state import _run_state_manager as _run_store
from reasoner.presets import get_method_from_preset
from reasoner.quality import PhaseMonitor

logger = logging.getLogger(__name__)


def _request_from_command(command: RunPipelineCommand) -> RunRequest:
    """The rest of this module predates RunPipelineCommand and reads a RunRequest."""
    return RunRequest(
        problem=command.problem,
        preset=command.preset,
        top_k=command.top_k,
        source_type=command.source_type,
        domain=command.domain,
        sequential=not command.parallel,
        client_run_id=command.command_id,
    )


async def _claim_ownership(run_id: str, user_id: str | None) -> None:
    try:
        await get_pipeline_ownership_repo().set_owner(run_id, user_id, run_id)
    except Exception:
        # An ownership-write failure must not abort the run itself, but it does
        # mean the pipeline stays inaccessible (fail closed) until a human
        # intervenes -- log loudly rather than silently swallow it.
        logger.error(
            "Failed to record pipeline ownership for %s; pipeline will be "
            "inaccessible via ownership checks until this is fixed",
            run_id,
            exc_info=True,
        )


async def _answer_without_a_pipeline(
    preflight: Any,
    req: RunRequest,
    run_id: str,
    cancel_event: Any,
    stream: RunStream,
) -> bool:
    """HyperGate said DIRECT or WEB_SEARCH. True when the answer was streamed here."""
    from reasoner.core.settings import settings as _settings

    if preflight.action == "direct":
        async for chunk in _stream_direct_answer(
            preflight.router, req.problem, run_id, cancel_event,
            conversation_history=preflight.conversation_history,
            previous_synthesis=preflight.previous_synthesis,
            turn_number=preflight.turn_number,
            preset_name=preflight.effective_preset_name,
        ):
            await stream.emit(chunk)
        return True

    if preflight.action == "web_search":
        if _settings.OPENROUTER_WEB_SEARCH_ENABLED:
            chunks = _stream_direct_answer(
                preflight.router, req.problem, run_id, cancel_event,
                web_search=True,
                preset_name=preflight.effective_preset_name,
            )
        else:
            chunks = _stream_web_search_results(req.problem, run_id, cancel_event=cancel_event)
        async for chunk in chunks:
            await stream.emit(chunk)
        return True

    return False


def _seed_state(
    req: RunRequest,
    preflight: Any,
    initial_state: PipelineState | None,
    user_id: str | None,
    user_tier: Any,
) -> tuple[PipelineState, str | None]:
    """The state a run starts from, and the method it settled on."""
    from reasoner.presets import PRESETS as _PRESETS

    preset_name = preflight.effective_preset_name
    state = initial_state or PipelineState(problem=req.problem, preset_name=preset_name)
    # Carry the ceilings into the run so the executor halts mid-pipeline if the
    # accumulated cost crosses one.
    apply_spend_limits(state, user_tier, user_id)
    if preflight.recalled_chunks:
        state.neuro_context = preflight.recalled_chunks

    file_ids = list(getattr(req, "file_ids", []) or [])
    if not file_ids and getattr(req, "attachments", None):
        file_ids = [a.file_id for a in req.attachments if getattr(a, "file_id", None)]
    if file_ids:
        state.method_state.set("prism", {**state.method_state.get("prism"), "file_ids": file_ids})

    # Inject VS runtime parameters from preset metadata before any phase runs,
    # so _phase_brainstorm_generate can read them.
    bs_preset = _PRESETS.get(preset_name)
    if bs_preset and bs_preset.brainstorming_config:
        state.brainstorming_state["config"] = bs_preset.brainstorming_config
        logger.debug(f"Injected brainstorming config: {bs_preset.brainstorming_config}")

    method = preflight.auto_selected_method
    # Article detection applies only to auto-detected methods, where the
    # orchestrator already settled on "writing". Explicit presets
    # (coding-budget, debate-budget, ...) set their own method and leave
    # auto_selected_method None.
    if method == "writing":
        state.task_type = TaskType.TECHNICAL
        state.decomposition = ["article workflow"]
        state.method = "article"
        method = "article"
        logger.info("Article request detected in stream — routing to article method")

    return state, method


def _build_run(
    req: RunRequest,
    preflight: Any,
    initial_state: PipelineState | None,
    user_id: str | None,
    user_tier: Any,
    run_id: str,
) -> tuple[Any, PipelineState, Any, str | None]:
    """Everything the run needs in hand before the first phase executes."""
    from reasoner.application.event_bus.bus import get_event_bus
    from reasoner.application.services.event_emission_service import (
        EventEmissionService,
        set_event_emitter,
    )

    preset_name = preflight.effective_preset_name
    pipeline = PipelineService().create_pipeline(
        router=preflight.router,
        preset_name=preset_name,
        top_k=req.top_k,
        parallel_perspectives=(
            (not req.sequential) if "multi-perspective" not in preset_name else True
        ),
        source_type=req.source_type,
        domain=req.domain,
        enhance_prompt=req.enhance_prompt,
        complexity=getattr(req, "complexity", None),
        batch_critique_jury=getattr(req, "batch_critique_jury", False),
        initial_state=initial_state,
        user_id=user_id,
    )

    state, method = _seed_state(req, preflight, initial_state, user_id, user_tier)

    emitter = EventEmissionService(get_event_bus(), aggregate_id=run_id)
    set_event_emitter(emitter)

    return pipeline, state, emitter, method


async def _enhance_prompt(
    req: RunRequest, pipeline: Any, state: PipelineState, stream: RunStream
) -> None:
    if not req.enhance_prompt or state.enhanced_problem:
        return
    try:
        await pipeline._phase_enhance_prompt(state)
        if state.enhanced_problem and state.enhanced_problem != state.problem:
            await stream.emit({
                "type": "prompt_enhanced",
                "original": state.problem,
                "enhanced": state.enhanced_problem,
            })
    except Exception as exc:
        logger.warning("Prompt enhancement failed, using original: %s", exc)
        state.enhanced_problem = state.problem


def _build_runner(
    pipeline: Any, req: RunRequest, run_id: str, stream: RunStream, emitter: Any
) -> Any:
    """The engine, wired to this driver's observer and Langfuse spans."""
    from reasoner.api.execution.sse_observer import SseRunObserver
    from reasoner.application.flows.runner import WorkflowRunner
    from reasoner.application.flows.services import PipelineWorkflowServices
    from reasoner.core.observability.phase_span import PhaseSpan

    router = pipeline.router

    def _span(step: Any, st: PipelineState) -> Any:
        return PhaseSpan(
            run_id, phase_name=step.name, phase_number=step.num, router=router, state=st
        )

    runner = WorkflowRunner(
        PipelineWorkflowServices(pipeline),
        monitor=PhaseMonitor(router, preset_name=req.preset),
        observer=SseRunObserver(stream, router, emitter, req.preset or ""),
        span_factory=_span,
    )
    # Circular by nature: the runner needs services, and the services need the
    # runner so run_phase() delegates instead of taking its bare
    # `await step.fn(...)` fallback.
    runner.services = PipelineWorkflowServices(pipeline, runner=runner)
    return runner


async def _run_phases(
    pipeline: Any,
    state: PipelineState,
    req: RunRequest,
    run_id: str,
    stream: RunStream,
    emitter: Any,
    cancel_event: Any,
) -> bool:
    """Hand the run to WorkflowRunner. False when the caller cancelled it.

    This used to be a second phase loop -- its own retries, timeouts, quality
    gate and fatality rule -- kept here only so SSE frames could be emitted
    between the steps. The frames are an observer now, and WorkflowRunner runs
    the phases for this driver exactly as it does for the CLI.
    """
    from reasoner.application.flows.factory import WorkflowFactory

    method = state.method or pipeline._get_method_from_preset()
    strategy = WorkflowFactory().get_strategy(method)
    if strategy is None:
        logger.error(f"No strategy found for method: {method}")
        return True

    runner = _build_runner(pipeline, req, run_id, stream, emitter)

    # Cancellation is a driver concern, so it stays out of the runner: a watcher
    # cancels the run task, which propagates into whichever phase coroutine is
    # in flight.
    run_task = asyncio.ensure_future(runner.run(strategy, state))
    cancel_watch = asyncio.ensure_future(cancel_event.wait())
    done, _ = await asyncio.wait({run_task, cancel_watch}, return_when=asyncio.FIRST_COMPLETED)

    if cancel_watch in done:
        run_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await run_task
        await stream.emit({"type": "cancelled", "message": "Pipeline stopped by user"})
        return False

    cancel_watch.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await cancel_watch
    await run_task
    return True


def _token_totals(state: PipelineState) -> dict[str, int]:
    source = state.detailed_token_usage if state.detailed_token_usage else state.phase_tokens
    total_input = sum(t.get("input", 0) for t in source.values())
    total_output = sum(t.get("output", 0) for t in source.values())
    return {
        "input": total_input,
        "output": total_output,
        "total": total_input + total_output,
    }


def _record_history(
    req: RunRequest, state: PipelineState, user_id: str | None, tokens: dict
) -> None:
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
            tokens=tokens,
            status="completed" if not state.errors else "error",
        )
        _save_history_entry(entry)
        _tag_history(entry)
    except Exception as e:
        logger.warning(f"Failed to save history: {e}")


def _tag_history(entry: HistoryEntry) -> None:
    try:
        import re as _re

        from reasoner.core.memory import TaggedMemory

        def _sanitize(s: str | None) -> str:
            return _re.sub(r"[^a-zA-Z0-9_-]", "_", s or "unknown")

        tagged = TaggedMemory(HISTORY_DIR)
        tagged.add(f"method_{_sanitize(entry.method)}", entry.model_dump())
        tagged.add(f"preset_{_sanitize(entry.preset)}", entry.model_dump())
    except Exception as tag_err:
        logger.warning(f"Failed to save tagged history: {tag_err}")


async def _teardown(conn_context: StreamingConnectionContext, run_id: str) -> None:
    # Cancel all pending broadcast tasks for this run (B-13)
    await conn_context.cleanup()
    await _run_store.remove(run_id)
    # Close the neuro HTTP client to prevent connection pool exhaustion
    try:
        from reasoner.clients import close_neuro_client

        await close_neuro_client()
    except Exception:
        pass


async def _settle_preflight(
    orchestrator: PipelineOrchestrator,
    req: RunRequest,
    initial_state: PipelineState | None,
    user_id: str | None,
    user_tier: Any,
    run_id: str,
    cancel_event: Any,
    stream: RunStream,
) -> Any | None:
    """Resolve preset, method and affordability. None when the run stops here."""
    preflight = await orchestrator.preflight(req, initial_state, user_id=user_id)

    if preflight.gate_reasoning:
        await stream.emit({
            "type": "method_selected",
            "data": {
                "action": preflight.action,
                "method": preflight.auto_selected_method,
                "confidence": preflight.gate_confidence,
                "reasoning": preflight.gate_reasoning,
                "alternatives": preflight.gate_alternatives,
            },
        })

    if await _answer_without_a_pipeline(preflight, req, run_id, cancel_event, stream):
        return None

    # Refuse a run the caller's plan cannot pay for. Checked against the preset
    # preflight actually resolved, not the one requested -- auto presets only
    # settle on a tier here.
    rejection = check_run_allowed(preflight.effective_preset_name, user_tier, user_id)
    if rejection is not None:
        logger.info(
            "Run %s refused: %s cap for tier %s (preset %s)",
            run_id, rejection.cap_type, user_tier.value, preflight.effective_preset_name,
        )
        await stream.rejected(rejection)
        return None

    return preflight


async def _announce_start(
    req: RunRequest,
    preflight: Any,
    method: str | None,
    emitter: Any,
    user_id: str | None,
    stream: RunStream,
) -> None:
    logger.info(f"Pipeline start with routing: {preflight.router.describe()}")
    await stream.started(
        problem=req.problem,
        preset=preflight.effective_preset_name,
        method=get_method_from_preset(preflight.effective_preset_name) or "multi-perspective",
        auto_selected_method=method,
        options={"top_k": req.top_k, "source_type": req.source_type, "user_id": user_id},
        emitter=emitter,
    )


async def _finish_run(
    orchestrator: PipelineOrchestrator,
    req: RunRequest,
    state: PipelineState,
    user_id: str | None,
    run_id: str,
    run_start: float,
    stream: RunStream,
) -> None:
    tokens = _token_totals(state)
    _record_history(req, state, user_id, tokens)
    await stream.done(state, tokens, time.monotonic() - run_start)
    # Postflight: neuro persist.
    await orchestrator.postflight(state, req, user_id=user_id, run_id=run_id)


class PipelineExecutionService:
    """Drives one streaming run: preflight, hand to WorkflowRunner, postflight.

    It executed the phases itself until Phase B-1; what is left is the shape of
    a run, with every step that has its own reason to exist extracted beside it.
    """

    async def execute_run(
        self,
        command: RunPipelineCommand,
        router: ProviderRouter,
        sse_emit: Callable[[dict | str], Awaitable[None]],
        user_id: str | None = None,
        initial_state: PipelineState | None = None,
    ) -> PipelineState | None:
        """Run one streaming pipeline and return the state it produced.

        Returning the state matters: RunPipelineCommandHandler assigns it and
        hands it to _completion_payload, which reads `state.phase_tokens`.
        Every path here used to return None against a `-> PipelineState`
        annotation, so the handler raised AttributeError *after* the client
        already had its `done` frame -- recording PIPELINE_FAILED instead of
        PIPELINE_COMPLETED and emitting a spurious trailing `error` frame on
        every finished web run.
        """
        req = _request_from_command(command)
        run_id = req.client_run_id or str(uuid.uuid4())
        set_correlation_id(run_id)
        await _claim_ownership(run_id, user_id)

        cancel_event = await _run_store.add(run_id, user_id=user_id)
        # Tracks per-run WS broadcast tasks so they can be cancelled on
        # disconnect (B-13).
        conn_context = StreamingConnectionContext(run_id)
        stream = RunStream(run_id, sse_emit, conn_context.tracked_broadcast)

        # Emit immediately so the UI has content to render while preflight
        # (HyperGate LLM calls) completes.
        await stream.emit({"type": "connecting", "message": "Running system check…"})
        keepalive = asyncio.ensure_future(stream.keepalive())

        state: PipelineState | None = None
        orchestrator = PipelineOrchestrator(
            PresetService(), PipelineService(), adaptive_routing=build_adaptive_routing_service()
        )
        try:
            # Resolve the caller's plan up front -- the spend ceilings it
            # implies gate the run below and bound every LLM call inside it.
            user_tier = await resolve_user_tier(user_id)
            preflight = await _settle_preflight(
                orchestrator, req, initial_state, user_id, user_tier,
                run_id, cancel_event, stream,
            )
            if preflight is None:
                return None

            pipeline, state, emitter, method = _build_run(
                req, preflight, initial_state, user_id, user_tier, run_id
            )
            await _announce_start(req, preflight, method, emitter, user_id, stream)
            await _enhance_prompt(req, pipeline, state, stream)

            run_start = time.monotonic()
            if not await _run_phases(
                pipeline, state, req, run_id, stream, emitter, cancel_event
            ):
                return state

            await _finish_run(orchestrator, req, state, user_id, run_id, run_start, stream)
        except Exception as exc:
            logger.error("Pipeline error for run %s: %s", run_id, exc, exc_info=True)
            await stream.failed(exc, state)
        finally:
            keepalive.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive
            await _teardown(conn_context, run_id)

        return state
