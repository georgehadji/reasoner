"""Concrete implementation of workflow services."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reasoner.application.flows.base import PhaseStep, WorkflowServices
from reasoner.core.ports.code_executor import CodeExecutorPort
from reasoner.domain.pipeline_state import PipelineState

if TYPE_CHECKING:
    from reasoner.application.flows.runner import WorkflowRunner
    from reasoner.pipeline import ReasonerPipeline

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

        This only *selects* an executor — it never performs I/O, so it can
        stay synchronous. For the container sandbox, the actual "is this
        adapter healthy enough to trust" gate runs inside
        ``ContainerExecutionSandbox.execute()`` (TTL-cached health check)
        rather than here, since a real Docker/network probe needs to be
        async and this constructor is called from sync contexts.
        """
        from reasoner.core.settings import settings
        if not settings.EXEC_SANDBOX_ENABLED:
            from reasoner.infrastructure.execution.noop_executor import NoopExecutor
            self.code_executor = NoopExecutor()
            return

        if settings.EXEC_SANDBOX_MODE == "container":
            try:
                from reasoner.infrastructure.execution.container_sandbox import (
                    ContainerExecutionSandbox,
                )
                self.code_executor = ContainerExecutionSandbox(
                    settings.SANDBOX_WORKER_URL,
                    settings.SANDBOX_WORKER_TOKEN,
                )
            except Exception:
                from reasoner.infrastructure.execution.noop_executor import NoopExecutor
                self.code_executor = NoopExecutor()
            return

        # Legacy/dev-only path. settings.py raises at import time if this
        # mode is ever combined with EXEC_SANDBOX_ENABLED=true in production,
        # so reaching here in production is not possible.
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
        # Propagation resistance (docs/MIND_VIRUS_MITIGATION.md M1/M2). This is the
        # chokepoint for all 29 phase modules — every flows/*.py phase reaches the
        # router through here. Applied at the application layer rather than inside
        # ProviderRouter so prompt semantics stay out of infrastructure.
        from reasoner.phases._shared import harden_system_prompt

        return await self._pipeline._call_llm_cached(
            role=role,
            system_prompt=harden_system_prompt(system_prompt),
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
