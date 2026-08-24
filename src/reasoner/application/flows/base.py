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
        depends_on: list[str] = None
    ):
        self.num = num
        self.name = name
        self.fn = fn
        self.serializer = serializer
        self.critical = critical
        self.depends_on = depends_on or []

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
class WorkflowStrategy(Protocol):
    """Protocol for reasoning workflow strategies."""

    async def execute(
        self,
        state: PipelineState,
        services: WorkflowServices,
    ) -> PipelineState:
        """Execute the reasoning workflow."""
        ...

    def get_phases(self, state: PipelineState) -> list[PhaseStep]:
        """Return the list of phases for this strategy."""
        ...
