"""Unified Workflow Runner for executing reasoning strategies with robustness."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowStrategy, WorkflowServices, PhaseStep
from reasoner.quality import PhaseMonitor, reset_phase_state
from reasoner.core.constants import get_phase_retry_budget, get_phase_timeout
from reasoner.application.event_bus.bus import get_event_bus
from reasoner.core.events.domain_events import make_event, EventType
from reasoner.exceptions import classify_error, is_retryable

logger = logging.getLogger(__name__)


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
        monitor: PhaseMonitor | None = None
    ):
        self.services = services
        self.monitor = monitor or PhaseMonitor(services.router)
        self.bus = get_event_bus()

    async def run(
        self, 
        strategy: WorkflowStrategy, 
        state: PipelineState,
        config: Any = None
    ) -> PipelineState:
        """Run the strategy to completion."""
        return await strategy.execute(state, self.services)

    async def run_phase(
        self, 
        step: PhaseStep, 
        state: PipelineState,
        **kwargs: Any
    ) -> bool:
        """
        Execute a single PhaseStep with retries, quality checks, and events.
        Returns True if successful, False if fatal error occurred.

        Note: the SSE streaming path (api/execution/pipeline.py) has its own
        phase execution loop because it needs SSE keepalive, WebSocket broadcast,
        and PhaseSpan observability — concerns that don't apply to the CLI
        WorkflowStrategy path. These are intentionally separate execution
        contexts, not duplicate code.
        """
        num = step.num
        name = step.name
        fn = step.fn
        critical = step.critical

        phase_key = f"Phase {num}: {name}"
        state._current_phase_key = phase_key
        
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
        for attempt in range(max_retries + 1):
            try:
                timeout = get_phase_timeout(name)
                await asyncio.wait_for(fn(state, self.services, **kwargs), timeout=timeout)
                
                quality_result = await self.monitor.evaluate(name, state, attempt=attempt + 1)
                
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
            
            except asyncio.TimeoutError:
                err_msg = f"Phase timeout: {name} exceeded {timeout}s"
                await self._handle_phase_error(state, name, err_msg, is_fatal=critical)
                if critical: return False
                break
                
            except Exception as exc:
                err_type = classify_error(exc)
                err_msg = f"{type(exc).__name__}: {str(exc)}"
                is_fatal = not is_retryable(exc) or critical
                
                await self._handle_phase_error(state, name, err_msg, is_fatal=is_fatal)
                
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
            return True
            
        return not critical

    async def _handle_phase_error(self, state: PipelineState, name: str, message: str, is_fatal: bool):
        state.errors.append(message)
        self.services.log(name, f"ERROR: {message}", state)
        
        fail_evt = make_event(
            EventType.PHASE_FAILED,
            aggregate_id=state.conversation_id or "unknown",
            version=1,
            phase_name=name,
            error=message,
            is_fatal=is_fatal
        )
        await self.bus.publish(fail_evt)
