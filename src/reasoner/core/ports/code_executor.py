"""Core port for code execution — Hexagonal DDD port layer.

Paper grounding: §2.1.3, §3.4.3 (sandboxed execution), §3.4.4 (deterministic sensors).
Infrastructure adapters implement this port; phases/uses only depend on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ExecutionResult:
    """Deterministic result from executing user- or agent-written code.

    All fields carry their runtime values regardless of success/failure
    so harness-level verification sensors can inspect them.
    """
    success: bool = False
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    timed_out: bool = False
    duration_ms: int = 0
    truncated: bool = False  # output was clipped to EXEC_MAX_OUTPUT_BYTES
    blocked: bool = False    # AST guard rejected the code, or sandbox refused
    blocked_reason: str = ""
    policy_version: str = ""  # identifies which guard/sandbox config produced this result

    @property
    def summary(self) -> str:
        """One-line summary for logging and interpret-phase context."""
        if self.blocked:
            return f"BLOCKED: {self.blocked_reason}"
        if self.timed_out:
            return "TIMEOUT"
        if self.success:
            return f"exit {self.exit_code}, {self.duration_ms}ms"
        return f"FAIL exit {self.exit_code}: {self.stderr[:120]}"


@dataclass
class ExecutionLimits:
    """Resource limits enforced by the executor.

    These are safe defaults for PoT/Coding verification —
    not user-code execution limits.
    """
    timeout_ms: int = 30_000       # 30s wall-clock
    memory_limit_mb: int = 256      # RAM cap
    max_output_bytes: int = 65_536  # stdout/stderr clipped here


@runtime_checkable
class CodeExecutorPort(Protocol):
    """Port that infrastructure adapters implement.

    Phases depend on this Protocol, never on concrete adapters.
    """

    async def execute(
        self,
        code: str,
        *,
        language: str = "python",
        stdin: str = "",
        limits: ExecutionLimits | None = None,
    ) -> ExecutionResult:
        """Execute code in a sandboxed environment and return the result.

        Args:
            code: Source code to execute.
            language: Language identifier (default "python").
            stdin: Input to pipe to the process's stdin.
            limits: Resource limits (defaults if None).

        Returns:
            ExecutionResult with stdout, stderr, exit code, and diagnostics.
            The executor MUST NOT raise on execution failure — only on
            infrastructure failure (sandbox init error, disk full, etc.).
        """
        ...

    async def health_check(self) -> bool:
        """Return whether this executor is safe to use right now.

        Callers must fail closed (fall back to a non-executing adapter) when
        this returns False rather than attempt execution anyway. Adapters
        that are not an isolation boundary (e.g. the legacy subprocess
        executor) should always return False so they are never silently
        treated as the approved isolated path.
        """
        ...
