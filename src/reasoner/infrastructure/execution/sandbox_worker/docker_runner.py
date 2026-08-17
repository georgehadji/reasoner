"""Runs one job container per execution request.

Hardened per security-remediation-plan.md Phase 1 item 2:
  - non-root UID, read-only root filesystem
  - no host bind mounts (code travels via argv/stdin only)
  - network namespace disabled (--network none)
  - dropped Linux capabilities and no-new-privileges
  - CPU, memory, PID, and wall-clock limits
  - ephemeral working storage (--rm; tmpfs for /tmp)
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from reasoner.core.ports.code_executor import ExecutionLimits, ExecutionResult
from reasoner.infrastructure.execution.runners import get_runner
from reasoner.infrastructure.execution.runners.python_runner import PYTHON_SANDBOX_IMAGE

logger = logging.getLogger(__name__)

POLICY_VERSION = "container-sandbox-v1"

# Non-root UID/GID baked into the sandbox image (sandbox_image/Dockerfile)
# and passed explicitly here so a misbuilt image can't silently run as root.
_SANDBOX_UID = 65532
_SANDBOX_GID = 65532

_PIDS_LIMIT = 64
_TMPFS_SIZE_MB = 64
_DOCKER_CLI_OVERHEAD_SEC = 10.0  # grace period beyond the job timeout for docker CLI startup


def _build_docker_argv(
    job_id: str,
    image: str,
    argv: list[str],
    *,
    limits: ExecutionLimits,
    seccomp_profile: str | None,
) -> list[str]:
    """Build the ``docker run`` argv list. Never a shell string — every
    element is a separate argv entry, so nothing here can be reinterpreted
    as extra flags or shell syntax."""
    cmd = [
        "docker", "run",
        "--name", job_id,
        "--rm",
        "--network", "none",
        "--read-only",
        "--user", f"{_SANDBOX_UID}:{_SANDBOX_GID}",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", str(_PIDS_LIMIT),
        "--memory", f"{limits.memory_limit_mb}m",
        "--memory-swap", f"{limits.memory_limit_mb}m",  # no swap beyond the memory cap
        "--cpus", "1",
        "--tmpfs", f"/tmp:rw,noexec,nosuid,size={_TMPFS_SIZE_MB}m",
        "-i",
    ]
    if seccomp_profile:
        cmd += ["--security-opt", f"seccomp={seccomp_profile}"]
    cmd += [image, *argv]
    return cmd


async def run_in_container(
    code: str,
    *,
    language: str,
    stdin: str,
    limits: ExecutionLimits,
    seccomp_profile: str | None = None,
) -> ExecutionResult:
    """Run one job in an isolated, ephemeral container and return the result.

    Never raises on execution failure or timeout — only returns a blocked
    result — matching the ``CodeExecutorPort`` contract so the caller never
    needs to distinguish infrastructure failure from a rejected attempt.
    """
    try:
        runner = get_runner(language)
    except ValueError as exc:
        return ExecutionResult(
            success=False,
            blocked=True,
            blocked_reason=str(exc),
            policy_version=POLICY_VERSION,
        )

    spec = runner.build_command(code, stdin, limits)
    job_id = f"reasoner-sandbox-{uuid.uuid4().hex[:12]}"
    cmd = _build_docker_argv(
        job_id, spec.image, spec.argv, limits=limits, seccomp_profile=seccomp_profile
    )

    t0 = time.monotonic()
    timeout_sec = limits.timeout_ms / 1000.0
    proc: asyncio.subprocess.Process | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(
                    input=spec.stdin_payload.encode("utf-8") if spec.stdin_payload else None
                ),
                timeout=timeout_sec + _DOCKER_CLI_OVERHEAD_SEC,
            )
        except TimeoutError:
            await _force_kill(job_id, proc)
            elapsed = int((time.monotonic() - t0) * 1000)
            return ExecutionResult(
                success=False,
                stderr=f"Execution timed out after {timeout_sec}s",
                exit_code=-1,
                timed_out=True,
                duration_ms=min(elapsed, limits.timeout_ms),
                policy_version=POLICY_VERSION,
            )

        elapsed = int((time.monotonic() - t0) * 1000)
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
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_ms=elapsed,
            truncated=truncated,
            policy_version=POLICY_VERSION,
        )
    except FileNotFoundError:
        return ExecutionResult(
            success=False,
            stderr="docker binary not found on the sandbox worker host",
            exit_code=-1,
            policy_version=POLICY_VERSION,
        )
    except Exception as exc:
        logger.error("Container sandbox execution error: %s", exc)
        return ExecutionResult(
            success=False,
            stderr=f"Sandbox infrastructure error: {exc}",
            exit_code=-1,
            policy_version=POLICY_VERSION,
        )


async def _force_kill(job_id: str, proc: asyncio.subprocess.Process) -> None:
    """Kill the runaway container and the local docker-run CLI process.

    ``--rm`` deletes ephemeral storage when the container exits normally;
    this covers the case where the container hung past the timeout and
    needs a hard removal, plus killing the local CLI process that was
    waiting on it.
    """
    try:
        rm = await asyncio.create_subprocess_exec(
            "docker", "rm", "-f", job_id,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await rm.wait()
    except Exception:
        pass
    try:
        proc.kill()
        await proc.wait()
    except Exception:
        pass


async def check_docker_health() -> bool:
    """Verify the Docker engine is reachable and the sandbox image exists.

    Used by GET /health — the API process gates enabling code execution in
    production on this passing (security remediation plan Phase 0 item 4).
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "image", "inspect", PYTHON_SANDBOX_IMAGE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        return proc.returncode == 0
    except Exception:
        return False
