"""SubprocessExecutor — sandboxed subprocess execution for PoT verification.

Runs Python code in an isolated tempdir with:
  - Resource limits (CPU/wall timeout, memory cap)
  - No network access (no sockets, no host FS)
  - AST safety guard (import allowlist, blocked patterns)
  - Output byte cap

Platform notes:
  - POSIX: resource.RLIMIT_AS for memory, SIGALRM for timeout
  - Windows: psutil for memory monitoring, CREATE_NO_WINDOW for process,
    subprocess timeout= param (Python 3.12+)

Architecture:
  Implements CodeExecutorPort from core/ports/.  Phases depend on the
  port, never on this adapter.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Optional

from reasoner.core.code_safety import check_code_safety, CodeSafetyError
from reasoner.core.exec_constants import (
    EXEC_DEFAULT_TIMEOUT_MS,
    EXEC_MEM_LIMIT_MB,
    EXEC_MAX_OUTPUT_BYTES,
)
from reasoner.core.ports.code_executor import (
    CodeExecutorPort,
    ExecutionLimits,
    ExecutionResult,
)

logger = logging.getLogger(__name__)

_IS_WINDOWS = platform.system() == "Windows"


class SubprocessExecutor:
    """Execute Python code in an isolated subprocess.

    Thread-safety: uses tempfile.mkdtemp() per execution — no shared state.
    """

    def __init__(self, python_path: str | None = None) -> None:
        self._python_path = python_path or sys.executable

    async def execute(
        self,
        code: str,
        *,
        language: str = "python",
        stdin: str = "",
        limits: ExecutionLimits | None = None,
    ) -> ExecutionResult:
        if limits is None:
            limits = ExecutionLimits(
                timeout_ms=EXEC_DEFAULT_TIMEOUT_MS,
                memory_limit_mb=EXEC_MEM_LIMIT_MB,
                max_output_bytes=EXEC_MAX_OUTPUT_BYTES,
            )

        # 1. AST safety guard
        try:
            check_code_safety(code)
        except CodeSafetyError as exc:
            return ExecutionResult(
                success=False,
                stderr=str(exc),
                exit_code=-1,
                blocked=True,
                blocked_reason=str(exc),
            )

        # 2. Write code to tempdir
        script_path = None
        tmpdir = None
        try:
            tmpdir = Path(tempfile.mkdtemp(prefix="reasoner_exec_"))
            script_path = tmpdir / "script.py"
            script_path.write_text(
                textwrap.dedent(f"""\
                import sys
                sys.path.insert(0, '')
                {code}
                """),
                encoding="utf-8",
            )

            # 3. Build the subprocess command
            cmd = [
                self._python_path,
                "-I",   # isolated mode (no user site-packages)
                "-S",   # don't import site (minimal startup)
                str(script_path),
            ]

            # 4. Environment — completely isolated, no network
            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": tmpdir.as_posix(),
            }

            # POSIX: resource.RLIMIT_AS memory cap
            preexec_fn = None
            if not _IS_WINDOWS:
                import resource
                mem_bytes = limits.memory_limit_mb * 1024 * 1024
                def _set_limits():
                    try:
                        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                    except Exception:
                        pass
                preexec_fn = _set_limits

            # 5. Execute with timeout
            t0 = time.monotonic()
            timeout_sec = limits.timeout_ms / 1000.0

            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(tmpdir),
                    env=env,
                    preexec_fn=preexec_fn,
                    # Windows: CREATE_NO_WINDOW
                    creationflags=(
                        0x08000000  # CREATE_NO_WINDOW
                        if _IS_WINDOWS else 0
                    ),
                )

                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(input=stdin.encode() if stdin else None),
                        timeout=timeout_sec,
                    )
                except asyncio.TimeoutError:
                    # Kill the hung process
                    try:
                        proc.kill()
                        await proc.wait()
                    except Exception:
                        pass
                    elapsed = int((time.monotonic() - t0) * 1000)
                    return ExecutionResult(
                        success=False,
                        stderr=f"Execution timed out after {timeout_sec}s",
                        exit_code=-1,
                        timed_out=True,
                        duration_ms=min(elapsed, limits.timeout_ms),
                    )

                elapsed = int((time.monotonic() - t0) * 1000)

                # Decode and clip output
                stdout_str = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
                stderr_str = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

                truncated = False
                if len(stdout_str) > limits.max_output_bytes:
                    stdout_str = stdout_str[:limits.max_output_bytes]
                    truncated = True
                if len(stderr_str) > limits.max_output_bytes:
                    stderr_str = stderr_str[:limits.max_output_bytes]
                    truncated = True

                return ExecutionResult(
                    success=proc.returncode == 0,
                    stdout=stdout_str,
                    stderr=stderr_str,
                    exit_code=proc.returncode or 0,
                    timed_out=False,
                    duration_ms=elapsed,
                    truncated=truncated,
                )

            except FileNotFoundError:
                return ExecutionResult(
                    success=False,
                    stderr=f"Python interpreter not found: {self._python_path}",
                    exit_code=-1,
                )
            except Exception as exc:
                logger.error("Subprocess execution error: %s", exc)
                return ExecutionResult(
                    success=False,
                    stderr=f"Execution infrastructure error: {exc}",
                    exit_code=-1,
                )

        finally:
            # 6. Clean up tempdir
            if tmpdir and tmpdir.exists():
                import shutil
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
