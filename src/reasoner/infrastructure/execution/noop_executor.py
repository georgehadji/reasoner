"""NoopExecutor — graceful degradation when sandbox is unavailable.

Returns execution_disabled result so pipeline degrades cleanly
instead of crashing.
"""

from __future__ import annotations

from reasoner.core.ports.code_executor import (
    ExecutionLimits,
    ExecutionResult,
)


class NoopExecutor:
    """Fallback executor that returns a disabled result.

    Used when the platform sandbox can't initialise (e.g. missing
    subprocess permissions, read-only filesystem).  Enables the
    pipeline to continue with a clear 'execution not available' signal.
    """

    async def execute(
        self,
        code: str,
        *,
        language: str = "python",
        stdin: str = "",
        limits: ExecutionLimits | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            stderr="Code execution is disabled on this platform.",
            exit_code=-1,
            blocked=True,
            blocked_reason="execution_disabled",
        )

    async def health_check(self) -> bool:
        """Never healthy — this adapter intentionally does not execute code."""
        return False
