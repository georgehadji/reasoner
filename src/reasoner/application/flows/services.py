"""Concrete implementation of workflow services."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING
from reasoner.domain.pipeline_state import PipelineState
from reasoner.application.flows.base import WorkflowServices, PhaseStep
from reasoner.core.ports.code_executor import CodeExecutorPort

if TYPE_CHECKING:
    from reasoner.pipeline import ReasonerPipeline
    from reasoner.application.flows.runner import WorkflowRunner

class PipelineWorkflowServices(WorkflowServices):
    """Binds ReasonerPipeline methods to the WorkflowServices port."""
    
    def __init__(self, pipeline: ReasonerPipeline, runner: WorkflowRunner | None = None) -> None:
        self._pipeline = pipeline
        self.router = pipeline.router
        self._runner = runner
        self.code_executor: CodeExecutorPort | None = None
        self._init_executor()

    def _init_executor(self) -> None:
        """Install the configured executor, failing closed when disabled.

        ``NoopExecutor`` is deliberately used instead of ``None`` so phases do
        not fall back to simulating execution with an LLM.  A simulated result
        is not execution evidence and could be mistaken for verified output.
        """
        from reasoner.core.settings import settings
        if not settings.EXEC_SANDBOX_ENABLED:
            from reasoner.infrastructure.execution.noop_executor import NoopExecutor
            self.code_executor = NoopExecutor()
            return
        try:
            from reasoner.infrastructure.execution.subprocess_executor import SubprocessExecutor
            self.code_executor = SubprocessExecutor()
        except Exception:
            from reasoner.infrastructure.execution.noop_executor import NoopExecutor
            self.code_executor = NoopExecutor()
        
    def log(self, phase: str, message: str, state: PipelineState) -> None:
        self._pipeline._log(phase, message, state)
        
    async def call_llm(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        state: PipelineState,
        phase_key: str | None = None,
        **kwargs: Any,
    ) -> tuple[str, dict[str, Any]]:
        return await self._pipeline._call_llm_cached(
            role=role,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            state=state,
            phase_key=phase_key,
            **kwargs
        )

    async def run_phase(self, step: PhaseStep, state: PipelineState, **kwargs: Any) -> bool:
        if self._runner is None:
            # Fallback for simple execution without runner robustness
            await step.fn(state, self, **kwargs)
            return True
        return await self._runner.run_phase(step, state, **kwargs)
