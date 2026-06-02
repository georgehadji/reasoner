"""
PhaseLifecycleManager -- executes a single pipeline phase with retry, timeout,
quality monitoring, cancellation, and event publishing.

Extracted from api/streaming.py::run_stream() to separate phase orchestration
from SSE protocol concerns.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

from reasoner.domain.pipeline_state import PipelineState
from reasoner.core.constants import get_phase_retry_budget, get_phase_timeout
from reasoner.exceptions import classify_error
from reasoner.quality import PhaseMonitor, reset_phase_state
from reasoner.core.events.domain_events import make_event, EventType

logger = logging.getLogger(__name__)


@dataclass
class PhaseRunResult:
    """Rich outcome of a single phase execution."""
    success: bool
    fatal: bool
    phase_num: int | float
    phase_name: str
    phase_key: str = ""
    data: dict | None = None
    tokens: dict[str, int] | None = None
    models: list[str] | None = None
    duration: float = 0.0
    error: str | None = None
    error_type: str | None = None
    quality_score: float | None = None
    quality_passed: bool | None = None
    retries_used: int = 0
    events_to_persist: list[Any] | None = None


class PhaseLifecycleManager:
    """Encapsulates execution of a single pipeline phase.

    Handles retry, timeout, quality monitoring, cancellation,
    and domain event creation. Returns PhaseRunResult that the
    streaming layer formats into SSE events.
    """

    def __init__(
        self,
        router: Any,
        run_id: str,
        cancel_event: asyncio.Event,
        phase_monitor: PhaseMonitor | None = None,
        keepalive_interval: float = 15.0,
    ):
        self._router = router
        self._run_id = run_id
        self._cancel_event = cancel_event
        self._phase_monitor = phase_monitor or PhaseMonitor(router)
        self._keepalive_interval = keepalive_interval

    async def execute_phase(
        self,
        num: int | float,
        name: str,
        state: PipelineState,
        phase_fn: Callable,
        critical_phases: set[str],
        event_version: int = 1,
    ) -> PhaseRunResult:
        """Run one phase: retry loop, quality check, timeout, cancellation."""
        if self._cancel_event.is_set():
            return PhaseRunResult(
                success=False, fatal=False,
                phase_num=num, phase_name=name,
                error="Pipeline cancelled before phase start",
            )

        max_retries = get_phase_retry_budget(name)
        quality_result = None
        phase_errored = False
        phase_fatal = False
        phase_start = self._now()
        events: list[Any] = []
        retries_used = 0
        phase_key = f"Phase {num}: {name}"
        state._current_phase_key = phase_key

        for attempt in range(max_retries + 1):
            if self._cancel_event.is_set():
                return PhaseRunResult(
                    success=False, fatal=False,
                    phase_num=num, phase_name=name,
                    error="Pipeline cancelled",
                    duration=self._now() - phase_start,
                    phase_key=phase_key,
                )

            try:
                phase_timeout = get_phase_timeout(name)
                await self._run_with_timeout(phase_fn, state, phase_timeout)
                break

            except asyncio.TimeoutError:
                phase_errored, phase_fatal = self._handle_timeout(
                    name, phase_timeout, state, critical_phases,
                    event_version, events)
                break

            except Exception as exc:
                phase_errored, phase_fatal = self._handle_exception(
                    name, exc, state, critical_phases,
                    event_version, events)
                break

            # Phase function succeeded -- run quality check (still inside retry loop)
            if not self._cancel_event.is_set():
                quality_result = await self._phase_monitor.evaluate(
                    name, state, attempt=retries_used + 1)
                state.quality_history.append({
                    "phase": name, "attempt": retries_used + 1,
                    "score": quality_result.score,
                    "passed": quality_result.passed,
                })
                if not quality_result.passed and retries_used < max_retries:
                    if quality_result.suggestions:
                        state.quality_hints[name] = " ".join(quality_result.suggestions)
                    reset_phase_state(name, state)
                    retries_used += 1
                    continue

            # Fall through: phase passed quality or retries exhausted
            break

        # Post-loop cleanup -- runs once regardless of success/failure
        state.quality_hints.pop(name, None)
        duration = self._now() - phase_start
        state.phase_durations[phase_key] = duration
        return PhaseRunResult(
            success=not phase_errored and (
                quality_result is None or quality_result.passed),
            fatal=phase_fatal,
            phase_num=num, phase_name=name, phase_key=phase_key,
            duration=duration,
            error=state.errors[-1] if phase_errored and state.errors else None,
            tokens=state.phase_tokens.get(
                phase_key, {"input": 0, "output": 0}),
            models=state.cost_state._phase_models_by_key.get(phase_key, []),
            quality_score=quality_result.score if quality_result else None,
            quality_passed=quality_result.passed if quality_result else None,
            retries_used=retries_used,
            events_to_persist=events or None,
        )

    async def _run_with_timeout(
        self, phase_fn: Callable, state: PipelineState,
        timeout_seconds: float,
    ) -> None:
        """Run phase_fn(state); raise on cancel or timeout."""
        phase_task = asyncio.ensure_future(phase_fn(state))
        cancel_watch = asyncio.ensure_future(self._cancel_event.wait())
        deadline = self._now() + timeout_seconds
        try:
            while True:
                remaining = deadline - self._now()
                if remaining <= 0:
                    self._cancel_safely(phase_task)
                    raise asyncio.TimeoutError(
                        f"Phase timed out after {timeout_seconds}s")
                wait = min(self._keepalive_interval, remaining)
                done, _ = await asyncio.wait(
                    {phase_task, cancel_watch}, timeout=wait,
                    return_when=asyncio.FIRST_COMPLETED)
                if cancel_watch in done:
                    self._cancel_safely(phase_task)
                    raise asyncio.CancelledError("Cancelled by user")
                if phase_task in done:
                    exc = phase_task.exception()
                    if exc:
                        raise exc
                    return
        finally:
            for t in (phase_task, cancel_watch):
                if not t.done():
                    t.cancel()
                    try:
                        await t
                    except (asyncio.CancelledError, Exception):
                        pass

    def _handle_timeout(
        self, name: str, phase_timeout: float, state: PipelineState,
        critical_phases: set[str], event_version: int, events: list[Any],
    ) -> tuple[bool, bool]:
        err_msg = f"Phase timeout: {name} exceeded {phase_timeout}s"
        state.errors.append(err_msg)
        events.append(make_event(
            EventType.PHASE_FAILED, aggregate_id=self._run_id,
            version=event_version, phase_name=name, error=err_msg))
        return True, name in critical_phases

    def _handle_exception(
        self, name: str, exc: Exception, state: PipelineState,
        critical_phases: set[str], event_version: int, events: list[Any],
    ) -> tuple[bool, bool]:
        err_type = classify_error(exc)
        if err_type == "auth":
            err_msg = ("OpenRouter API key is missing or invalid. "
                       "Please set OPENROUTER_API_KEY in your .env file.")
        else:
            err_msg = f"{type(exc).__name__}: {str(exc)[:120]}"
        state.errors.append(err_msg)
        events.append(make_event(
            EventType.PHASE_FAILED, aggregate_id=self._run_id,
            version=event_version, phase_name=name, error=err_msg))
        return True, err_type == "auth" or name in critical_phases

    @staticmethod
    def _cancel_safely(task: asyncio.Task) -> None:
        if not task.done():
            task.cancel()

    @staticmethod
    def _now() -> float:
        import time
        return time.monotonic()
