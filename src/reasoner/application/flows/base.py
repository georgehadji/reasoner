"""Base interfaces for workflow strategies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from reasoner.core.ports.code_executor import CodeExecutorPort
from reasoner.core.ports.llm_port import LLMPort
from reasoner.domain.pipeline_state import PipelineState


class PhaseStep:
    """A single step in a reasoning flow."""
    def __init__(
        self,
        num: float,
        name: str,
        fn: Callable,
        serializer: Callable,
        critical: bool = False,
    ):
        self.num = num
        self.name = name
        self.fn = fn
        self.serializer = serializer
        self.critical = critical

@runtime_checkable
class WorkflowServices(Protocol):
    """Port defining core services provided by the orchestrator to workflows."""

    router: LLMPort
    code_executor: CodeExecutorPort | None = None

    def log(self, phase: str, message: str, state: PipelineState) -> None: ...

    async def call_llm(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        state: PipelineState,
        phase_key: str | None = None,
        **kwargs: Any,
    ) -> tuple[str, dict[str, Any]]: ...

    async def run_phase(self, step: PhaseStep, state: PipelineState, **kwargs: Any) -> bool: ...

@runtime_checkable
class PhaseObserver(Protocol):
    """Side effects a driver wants around each phase, in the order they happen.

    ``WorkflowRunner.run_phase`` awaits every hook inline. That is the point:
    the EventBus runs handlers concurrently, and queues them once started, so
    it is the right channel for projections and the wrong one for an SSE
    stream whose frame order is the contract the browser reads. The runner
    still publishes its ``PHASE_*`` domain events either way.

    ``result`` is the ``PhaseQualityResult`` from the phase's quality gate, or
    None on a phase that never got that far.
    """

    async def on_phase_start(self, step: PhaseStep, state: PipelineState) -> None: ...

    async def on_phase_quality(
        self, step: PhaseStep, state: PipelineState, result: Any, attempt: int
    ) -> None: ...

    async def on_phase_retry(
        self, step: PhaseStep, state: PipelineState, result: Any, attempt: int, max_attempts: int
    ) -> None: ...

    async def on_phase_error(
        self,
        step: PhaseStep,
        state: PipelineState,
        exc: BaseException | None,
        message: str,
        fatal: bool,
    ) -> None: ...

    async def on_phase_complete(
        self, step: PhaseStep, state: PipelineState, duration: float, result: Any
    ) -> None: ...


@runtime_checkable
class WorkflowStrategy(Protocol):
    """Protocol for reasoning workflow strategies.

    Steps only. The loop that runs them lives in ``WorkflowRunner.run``; a
    strategy that supplies its own would be reachable from the CLI and not
    from the web, which is exactly the split this Protocol used to permit.
    """

    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        """Return the list of phases for this strategy."""
        ...
