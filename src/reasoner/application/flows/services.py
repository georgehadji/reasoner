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
        self.code_executor = None
        
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
