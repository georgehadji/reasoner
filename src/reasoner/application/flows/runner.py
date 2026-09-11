"""Unified Workflow Runner for executing reasoning strategies with robustness."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, nullcontext
from typing import Any

from reasoner.application.event_bus.bus import get_event_bus
from reasoner.application.flows.base import (
    PhaseObserver,
    PhaseStep,
    WorkflowServices,
    WorkflowStrategy,
)
from reasoner.core.constants import get_phase_retry_budget, get_phase_timeout
from reasoner.core.events.domain_events import EventType, make_event
from reasoner.core.exceptions import classify_error, is_retryable, is_run_fatal
from reasoner.domain.pipeline_state import PipelineState
from reasoner.quality import PhaseMonitor, reset_phase_state

logger = logging.getLogger(__name__)

# Wraps one attempt at a phase body. PhaseSpan is the only implementation.
_SpanFactory = Callable[[PhaseStep, PipelineState], AbstractAsyncContextManager[Any]]


def resolve_phases(strategy: WorkflowStrategy, state: PipelineState) -> list[PhaseStep]:
    """The list of phases a run executes — for every driver, not one of them.

    Both drivers built this themselves and disagreed on the result. The SSE
    driver appended the Layer B egress rewrite and the CLI did not, so watermark
    egress rewriting has never applied to a CLI, headless or MCP run. Resolving
    the list in one place is what makes "one execution engine" true rather than
    "two engines that currently agree".
    """
    phases = list(strategy.get_phases(state))

    # Layer B (optional, off by default): appended once here rather than in
    # every flow's get_phases() (docs/plans/watermark-removal-integration.md §5.5).
    from reasoner.application.services.egress_policy import resolve_egress_policy
    if phases and resolve_egress_policy().layer_b_enabled:
        from reasoner.application.flows.egress_rewrite_phase import run_egress_rewrite_phase
        from reasoner.application.services.serializers import _ser_egress_rewrite
        phases.append(
            PhaseStep(
                phases[-1].num + 0.5,
                "Egress Rewrite",
                run_egress_rewrite_phase,
                _ser_egress_rewrite,
            )
        )
    return phases


class WorkflowRunner:
    """
    Executes a WorkflowStrategy with full lifecycle management:
    - Retries on failure or low quality
    - Timeouts per phase
    - Quality monitoring
    - Event publishing to the EventBus
    """

    def __init__(
        self,
        services: WorkflowServices,
        monitor: PhaseMonitor | None = None,
        observer: PhaseObserver | None = None,
        span_factory: _SpanFactory | None = None,
    ):
        self.services = services
        self.monitor = monitor or PhaseMonitor(services.router)
        self.bus = get_event_bus()
        # A driver's own in-order side effects (SSE frames, WebSocket fan-out,
        # event-store writes). See PhaseObserver for why these are not bus
        # subscribers.
        self.observer = observer
        # Wraps one attempt at the phase body. The SSE driver passes PhaseSpan,
        # which needs a run_id the runner has no business knowing.
        self.span_factory = span_factory or (lambda step, state: nullcontext())

    async def run(
        self,
        strategy: WorkflowStrategy,
        state: PipelineState,
        config: Any = None
    ) -> PipelineState:
        """Template Method: the one phase loop every flow shares.

        This used to delegate to ``strategy.execute()``, and all 21 strategies
        implemented that as the same four lines -- except two, which is the
        whole problem. Work held in an ``execute()`` override ran on the CLI
        only, because the SSE driver builds its own list from ``get_phases()``
        and never called ``execute()``. ``ArticleFlow`` had already found that
        out and moved its work into phases (``article_phases.py:79-86``,
        ``:378-384``); ``writing.py`` (augmentation) and ``delphi.py`` (the
        converged dissent skip) still had it. Seven more strategies dropped the
        ``step.critical`` check entirely, so ``jury.py:63``'s critical Critic
        Pool was fatal on the web and non-fatal on the CLI.

        Strategies now supply steps and nothing else.
        """
        for step in resolve_phases(strategy, state):
            # Through services, not self.run_phase: PipelineWorkflowServices
            # takes its bare `await step.fn(...)` fallback when it was built
            # without a runner, which is what WORKFLOW_RUNNER_ENABLED switches.
            # Calling self.run_phase here would execute the runner's retry and
            # quality layer even with the flag off.
            success = await self.services.run_phase(step, state)
            if not success and step.critical:
                break
        return state

    async def run_phase(
        self,
        step: PhaseStep,
        state: PipelineState,
        **kwargs: Any
    ) -> bool:
        """
        Execute a single PhaseStep with retries, quality checks, and events.
        Returns True if successful, False if fatal error occurred.

        Driver-specific side effects — SSE frames, WebSocket fan-out,
        event-store writes, Langfuse spans — arrive through ``observer`` and
        ``span_factory`` rather than through a second copy of this loop.
        """
        num = step.num
        name = step.name
        fn = step.fn
        critical = step.critical
        obs = self.observer

        phase_key = f"Phase {num}: {name}"
        state._current_phase_key = phase_key

        # P1.9: Skip phase if spend cap was exceeded in a previous phase
        if getattr(state, "_spend_cap_exceeded", False):
            logger.info("Spend cap exceeded — skipping phase %s", phase_key)
            state.phase_tokens[phase_key] = {"input": 0, "output": 0}
            return True

        if obs is not None:
            await obs.on_phase_start(step, state)

        start_evt = make_event(
            EventType.PHASE_STARTED,
            aggregate_id=state.conversation_id or "unknown",
            version=1,
            phase_name=name,
            phase_number=num
        )
        await self.bus.publish(start_evt)

        max_retries = get_phase_retry_budget(name)
        phase_start_time = time.monotonic()

        success = False
        quality_result = None
        for attempt in range(max_retries + 1):
            try:
                timeout = get_phase_timeout(name)
                async with self.span_factory(step, state):
                    await asyncio.wait_for(fn(state, self.services, **kwargs), timeout=timeout)

                quality_result = await self.monitor.evaluate(name, state, attempt=attempt + 1)

                # Recorded here rather than by a driver: the hints a later phase
                # reads from quality_history were only ever written by the SSE
                # loop, so a CLI run's downstream phases saw an empty history.
                state.quality_history.append({
                    "phase": name,
                    "attempt": attempt + 1,
                    "score": quality_result.score,
                    "passed": quality_result.passed,
                })
                if obs is not None:
                    await obs.on_phase_quality(step, state, quality_result, attempt + 1)

                quality_evt = make_event(
                    EventType.PHASE_QUALITY_CHECKED,
                    aggregate_id=state.conversation_id or "unknown",
                    version=1,
                    phase_name=name,
                    score=quality_result.score,
                    passed=quality_result.passed,
                    reason=quality_result.reason
                )
                await self.bus.publish(quality_evt)

                if quality_result.passed:
                    success = True
                    break

                if attempt < max_retries:
                    if quality_result.suggestions:
                        state.quality_hints[name] = " ".join(quality_result.suggestions)

                    self.services.log(name, f"Quality check failed (score: {quality_result.score}). Retrying...", state)
                    if obs is not None:
                        await obs.on_phase_retry(
                            step, state, quality_result, attempt + 1, max_retries + 1
                        )
                    reset_phase_state(name, state)

                    retry_evt = make_event(
                        EventType.PHASE_RETRIED,
                        aggregate_id=state.conversation_id or "unknown",
                        version=1,
                        phase_name=name,
                        attempt=attempt + 1,
                        reason=quality_result.reason
                    )
                    await self.bus.publish(retry_evt)
                else:
                    self.services.log(name, f"Quality check failed after {max_retries} retries.", state)

            except TimeoutError as exc:
                err_msg = f"Phase timeout: {name} exceeded {timeout}s"
                await self._handle_phase_error(step, state, err_msg, is_fatal=critical, exc=exc)
                if critical: return False
                break

            except Exception as exc:
                err_type = classify_error(exc)
                err_msg = f"{type(exc).__name__}: {str(exc)}"
                run_fatal = is_run_fatal(exc)
                is_fatal = run_fatal or not is_retryable(exc) or critical

                await self._handle_phase_error(step, state, err_msg, is_fatal=is_fatal, exc=exc)

                # P5 step 5: a non-critical phase failing normally just breaks,
                # and the run synthesises over the missing phase. That is the
                # right call for a bad model or a malformed response. It is the
                # wrong call when the credit balance is empty or the key was
                # rejected: every remaining phase fails the same way, so the
                # run spends its whole budget of wall-clock to produce a
                # synthesis over nothing and still reports success.
                if run_fatal:
                    return False

                if not is_retryable(exc) or attempt >= max_retries:
                    if critical: return False
                    break

                self.services.log(name, f"Error: {err_msg}. Retrying...", state)
                await asyncio.sleep(1)

        if success:
            duration = time.monotonic() - phase_start_time
            state.phase_durations[phase_key] = duration

            complete_evt = make_event(
                EventType.PHASE_COMPLETED,
                aggregate_id=state.conversation_id or "unknown",
                version=1,
                phase_name=name,
                duration_seconds=duration,
                tokens=state.phase_tokens.get(phase_key, {"input": 0, "output": 0})
            )
            await self.bus.publish(complete_evt)
            if obs is not None:
                await obs.on_phase_complete(step, state, duration, quality_result)
            return True

        return not critical

    async def _handle_phase_error(
        self,
        step: PhaseStep,
        state: PipelineState,
        message: str,
        is_fatal: bool,
        exc: BaseException | None = None,
    ) -> None:
        name = step.name
        state.errors.append(message)
        self.services.log(name, f"ERROR: {message}", state)

        if self.observer is not None:
            await self.observer.on_phase_error(step, state, exc, message, is_fatal)

        fail_evt = make_event(
            EventType.PHASE_FAILED,
            aggregate_id=state.conversation_id or "unknown",
            version=1,
            phase_name=name,
            error=message,
            is_fatal=is_fatal
        )
        await self.bus.publish(fail_evt)
