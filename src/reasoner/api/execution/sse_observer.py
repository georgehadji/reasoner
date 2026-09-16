"""The SSE driver's side of a phase, as a PhaseObserver.

`api/execution/pipeline.py` used to hold a second phase loop -- retries,
timeouts, the quality gate, critical-phase fatality -- so that it could emit
SSE frames between the steps. Two loops meant two answers to every question
about how a phase runs, and they disagreed: see the deleted `execute()`
overrides (65d8438) and `_LEGACY_CRITICAL` (b89809a).

`WorkflowRunner` now runs every phase for every driver. What is left here is
what is genuinely SSE-specific and belongs to no engine: the frames the
browser reads, the WebSocket fan-out beside them, and the event-store writes
keyed on this run.

Ordering matters and is why this is not an EventBus subscriber: `run_phase`
awaits each hook inline, in the order the phase actually reaches them. The
bus fans handlers out concurrently, and queues them once started.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from reasoner.api.phase_executor import get_phase_start_models
from reasoner.api.sse_utils import _persist_event
from reasoner.api.streaming import _get_phase_subagents
from reasoner.application.flows.base import PhaseStep
from reasoner.core.events.domain_events import EventType, make_event
from reasoner.core.exceptions import (
    ErrorCode,
    classify_error,
    error_code_for_exception,
    is_retryable,
)
from reasoner.domain.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

# The client sees a friendlier sentence than the exception text for the one
# failure a user can actually fix themselves.
_AUTH_HINT = (
    "OpenRouter API key is missing or invalid. "
    "Please set OPENROUTER_API_KEY in your .env or ui-next/.env.local file."
)


class RunStream:
    """One run's outbound surface: SSE frames, WS fan-out, event-store writes.

    The run-level frames and the per-phase ones (SseRunObserver) go to the same
    three places and share one aggregate version sequence, so they share one
    object. Keeping them apart meant `execute_run` handing `event_version` to
    the observer and reading it back out afterwards to number the terminal
    event.
    """

    def __init__(
        self,
        run_id: str,
        sse_emit: Callable[[dict | str], Awaitable[None]],
        broadcast: Callable[[dict], None],
    ) -> None:
        self.run_id = run_id
        self.broadcast = broadcast
        self.event_version = 1
        # Wrapped here so every caller gets the idle detection, including the
        # frames emitted before the phases start and after they finish.
        self.emit, self.keepalive = keepalive_ticker(sse_emit)

    async def both(self, payload: dict) -> None:
        """A client-visible frame goes to the SSE stream and the WS fan-out."""
        self.broadcast(payload)
        await self.emit(payload)

    async def persist(self, event_type: EventType, **fields: Any) -> None:
        await _persist_event(
            make_event(event_type, aggregate_id=self.run_id, version=self.event_version, **fields)
        )
        self.event_version += 1

    # ── run-level frames ─────────────────────────────────────────────

    async def started(
        self,
        *,
        problem: str,
        preset: str,
        method: str,
        auto_selected_method: str | None,
        options: dict,
        emitter: Any,
    ) -> None:
        payload: dict[str, Any] = {"type": "start", "preset": preset}
        if auto_selected_method:
            payload["auto_selected_method"] = auto_selected_method
        await self.both(payload)

        await self.persist(
            EventType.PIPELINE_STARTED,
            problem=problem,
            preset=preset,
            method=method,
            options=options,
        )
        emitter.emit("PIPELINE_STARTED", problem=problem, preset=preset, method=method)

    async def rejected(self, rejection: Any) -> None:
        """The caller's plan cannot pay for the preset preflight settled on."""
        await self.emit({
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
                    rejection.required_tier.value if rejection.required_tier else None
                ),
                "upgrade_url": "/pricing",
            },
        })

    async def done(self, state: PipelineState, tokens: dict, duration: float) -> None:
        # Kept as a named literal: tests/test_sdk_contract.py reads these keys
        # off the source, because the frame cannot be produced without driving a
        # whole pipeline and the TypeScript SDK reads every one of them.
        done_payload = {
            "type": "done",
            "errors": state.errors,
            # Failures the run survived by falling back (P5). Distinct from
            # errors: nothing here stopped a phase, but the answer was produced
            # with less than the full machinery.
            "degradations": list(getattr(state, "degradations", []) or []),
            "total_tokens": tokens,
            "duration": duration,
            "total_cost_usd": getattr(state, "total_cost_usd", 0.0),
            "phase_costs": getattr(state, "phase_costs", {}),
        }
        await self.both(done_payload)
        await self.persist(
            EventType.PIPELINE_COMPLETED,
            solution={
                "core_solution": (
                    getattr(state.final_solution, "core_solution", "")
                    if state.final_solution else ""
                )
            },
            total_tokens={"input": tokens["input"], "output": tokens["output"]},
            total_duration_seconds=duration,
            phases_completed=len(state.phase_durations),
        )

    async def failed(self, exc: BaseException, state: PipelineState | None) -> None:
        """The run itself broke, as opposed to one phase inside it."""
        message = f"Pipeline processing error: {type(exc).__name__}: {str(exc)[:120]}"
        phase = getattr(state, "_current_phase_key", "unknown") if state else "unknown"

        await self.persist(
            EventType.PIPELINE_FAILED,
            error=message,
            phase_at_failure=phase,
            phases_completed=len(state.phase_durations) if state else 0,
        )
        await self.both({
            "type": "error",
            "error_type": classify_error(exc),
            "error_code": error_code_for_exception(exc),
            "message": message,
            "retryable": False,
            "phase": None,
            "phase_name": phase,
        })
        await self.both({"type": "done", "errors": [message]})


class SseRunObserver:
    """The per-phase half of a run's frames, as a PhaseObserver."""

    def __init__(self, stream: RunStream, router: Any, emitter: Any, preset_name: str) -> None:
        self.stream = stream
        self.router = router
        self.emitter = emitter
        self.preset_name = preset_name
        # state.errors is cumulative across the run. Remember the mark at each
        # phase start so phase_complete reports only what *this* phase appended.
        self._errors_before = 0

    @property
    def sse_emit(self) -> Callable[[dict | str], Awaitable[None]]:
        return self.stream.emit

    async def _both(self, payload: dict) -> None:
        await self.stream.both(payload)

    # ── PhaseObserver ────────────────────────────────────────────────

    async def on_phase_start(self, step: PhaseStep, state: PipelineState) -> None:
        self._errors_before = len(state.errors)

        payload: dict[str, Any] = {"type": "phase_start", "phase": step.num, "name": step.name}
        models = get_phase_start_models(step.name, self.router)
        if models:
            payload["models"] = models
        await self._both(payload)

        self.emitter.emit("PHASE_STARTED", phase_name=step.name, phase_number=step.num)

    async def on_phase_quality(
        self, step: PhaseStep, state: PipelineState, result: Any, attempt: int
    ) -> None:
        await self._both({
            "type": "phase_quality",
            "phase": step.num,
            "name": step.name,
            "score": result.score,
            "passed": result.passed,
            "reason": result.reason,
            "attempt": attempt,
        })

    async def on_phase_retry(
        self, step: PhaseStep, state: PipelineState, result: Any, attempt: int, max_attempts: int
    ) -> None:
        await self._both({
            "type": "phase_retry",
            "phase": step.num,
            "name": step.name,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "reason": result.reason,
        })

    async def on_phase_error(
        self,
        step: PhaseStep,
        state: PipelineState,
        exc: BaseException | None,
        message: str,
        fatal: bool,
    ) -> None:
        if isinstance(exc, TimeoutError):
            err_type = "timeout"
            error_code = ErrorCode.PROVIDER_TIMEOUT.value
            retryable, retry_after = True, 5
        elif exc is not None:
            err_type = classify_error(exc)
            error_code = error_code_for_exception(exc)
            retryable = is_retryable(exc)
            retry_after = getattr(exc, "retry_after", None)
        else:
            err_type, error_code, retryable, retry_after = "unknown", None, False, None

        # state.errors already holds the runner's message; this only changes
        # what the browser renders.
        client_message = _AUTH_HINT if err_type == "auth" else message

        await self._both({
            "type": "error",
            "error_type": err_type,
            "error_code": error_code,
            "message": client_message,
            "retryable": retryable,
            "retry_after": retry_after,
            "phase": step.num,
            "phase_name": step.name,
        })
        await self._both({
            "type": "phase_error",
            "phase": step.num,
            "error": client_message,
            "error_code": error_code,
        })

        await self._persist(EventType.PHASE_FAILED, phase_name=step.name, error=client_message)
        self.emitter.emit("PHASE_FAILED", phase_name=step.name, error=client_message)

    async def on_phase_complete(
        self, step: PhaseStep, state: PipelineState, duration: float, result: Any
    ) -> None:
        phase_key = f"Phase {step.num}: {step.name}"
        tokens = state.phase_tokens.get(phase_key, {"input": 0, "output": 0})

        self._observe_duration(step.name, duration)

        for ev in self.emitter.pop_pending_events():
            await self.sse_emit(ev)

        if step.name == "Synthesis":
            await self._stream_synthesis_sentences(state)

        data = step.serializer(state)
        if isinstance(data, dict):
            self._enrich(data, step, state, duration, tokens, result)

        await self._both({
            "type": "phase_complete",
            "phase": step.num,
            "name": step.name,
            "data": data,
            # Running total, so a run abandoned before the terminal `done`
            # frame can still be billed for what it actually spent.
            # run_metering.extract_run_cost reads this; without it, cost was
            # observable only on `done` and a client that hung up mid-run had
            # its whole reservation released while the provider spend had
            # already been incurred.
            "total_cost_usd": round(getattr(state, "total_cost_usd", 0.0) or 0.0, 6),
        })

        self.emitter.emit(
            "PHASE_COMPLETED",
            phase_name=step.name,
            duration_seconds=duration,
            tokens=tokens,
        )
        await self._persist(
            EventType.PHASE_COMPLETED,
            phase_name=step.name,
            result={"data": data},
            tokens=tokens,
            model_used=(
                ",".join(state.cost_state._phase_models_by_key.get(phase_key, [])) or "unknown"
            ),
            duration_seconds=duration,
        )

    # ── helpers ──────────────────────────────────────────────────────

    async def _persist(self, event_type: EventType, **fields: Any) -> None:
        await self.stream.persist(event_type, **fields)

    def _observe_duration(self, name: str, duration: float) -> None:
        try:
            from reasoner.metrics import PHASE_DURATION

            PHASE_DURATION.labels(
                phase=name,
                method=self.preset_name or "unknown",
                preset=self.preset_name or "unknown",
            ).observe(duration)
        except Exception:
            pass

    async def _stream_synthesis_sentences(self, state: PipelineState) -> None:
        """Deliver the synthesis a sentence at a time so the UI can type it out."""
        fs = state.final_solution
        core = getattr(fs, "core_solution", "") if fs else ""
        if isinstance(core, dict):
            core = core.get("core_solution", core.get("synthesis", "")) or ""
        if not core or not isinstance(core, str):
            return
        for sentence in re.split(r"(?<=[.!?])\s+", core):
            await self.sse_emit({"type": "text_chunk", "text": sentence})

    def _enrich(
        self,
        data: dict,
        step: PhaseStep,
        state: PipelineState,
        duration: float,
        tokens: dict,
        result: Any,
    ) -> None:
        phase_key = f"Phase {step.num}: {step.name}"
        data["tokens"] = tokens
        data["duration"] = duration

        # Surface what this phase recorded. Without this, a phase whose work
        # all failed still serializes to an empty payload and the UI can only
        # say "No content for this phase" — the failure is invisible to the
        # user and to us.
        phase_errors = state.errors[self._errors_before:]
        if phase_errors:
            data["errors"] = phase_errors
            # Explicit alongside `errors` rather than left for the UI to infer
            # from array length: a phase that appended to state.errors and
            # recovered (e.g. article_phases.py's outline/critic parse-error
            # fallback to {}) still emits `phase_complete`, so without this it
            # renders identically to a clean pass — confirmed on the 2026-08-28
            # article run where two such phases showed green while the drafts
            # and revisions built on their empty output. See
            # docs/plans/article-flow-truncation-remediation.md W7.
            data["status"] = "degraded"

        phase_models = state.cost_state._phase_models_by_key.get(phase_key, [])
        if phase_models:
            data["models"] = phase_models

        subagent_outputs = _get_phase_subagents(state, step.name)
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

        if result is not None:
            data["quality"] = {"score": result.score, "passed": result.passed}


def keepalive_ticker(
    sse_emit: Callable[[dict | str], Awaitable[None]],
    idle_seconds: float = 15.0,
    tick_seconds: float = 5.0,
) -> tuple[Callable[[dict | str], Awaitable[None]], Callable[[], Awaitable[None]]]:
    """Wrap ``sse_emit`` so an idle stream still gets a comment frame.

    Replaces `run_phase_with_keepalive`, which could only punctuate the inside
    of one phase because it wrapped the phase coroutine. A run can idle
    elsewhere too -- preflight, neuro recall, the gap between phases -- and a
    proxy that times out does not care which. Returns the wrapped emit and the
    ticker coroutine to run as a task.
    """
    last = time.monotonic()

    async def emit(event: dict | str) -> None:
        nonlocal last
        last = time.monotonic()
        await sse_emit(event)

    async def tick() -> None:
        nonlocal last
        while True:
            await asyncio.sleep(tick_seconds)
            if time.monotonic() - last >= idle_seconds:
                await sse_emit(": keepalive\n\n")
                last = time.monotonic()

    return emit, tick
