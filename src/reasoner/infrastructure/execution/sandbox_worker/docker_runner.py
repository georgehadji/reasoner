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
import contextlib
import logging
import os
import socket
import time
import uuid
from collections.abc import Awaitable, Callable

from reasoner.core.degrade import degraded
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
_READ_CHUNK = 64 * 1024

# Every job container carries this label, so a worker that restarts after a
# crash can remove the containers its predecessor left running. The hostname
# is the container's own name under Compose, stable across restarts.
_WORKER_LABEL = "reasoner.sandbox.worker"
WORKER_ID = os.getenv("SANDBOX_WORKER_ID") or socket.gethostname()


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
        "--label", f"{_WORKER_LABEL}={WORKER_ID}",
        "--rm",
        "--stop-timeout", "1",
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
    # The in-container clock: the job dies on time even if this worker does,
    # which the host-side wait_for cannot promise.
    seconds = max(1, -(-limits.timeout_ms // 1000))
    cmd += [image, "timeout", "-s", "KILL", str(seconds), *argv]
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
        payload = spec.stdin_payload.encode("utf-8") if spec.stdin_payload else b""
        outcome, stdout_bytes, stderr_bytes = await _collect(
            proc, payload, limits.max_output_bytes, timeout_sec + _DOCKER_CLI_OVERHEAD_SEC,
            abort=lambda: _force_kill(job_id, proc),
        )
        if outcome == "timeout":
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
        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")

        if outcome == "overflow":
            # The job was killed at the cap rather than left printing into a
            # discarded pipe while it holds a slot until the timeout.
            return ExecutionResult(
                success=False,
                stdout=stdout_str,
                stderr=stderr_str,
                exit_code=-1,
                duration_ms=elapsed,
                truncated=True,
                policy_version=POLICY_VERSION,
            )

        return ExecutionResult(
            success=proc.returncode == 0,
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_ms=elapsed,
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


async def _collect(
    proc: asyncio.subprocess.Process,
    payload: bytes,
    cap: int,
    timeout: float,
    abort: Callable[[], Awaitable[None]],
) -> tuple[str, bytes, bytes]:
    """Feed stdin and read stdout/stderr, keeping at most ``cap`` bytes of each.

    ``communicate()`` buffered everything the job printed, so a print loop
    could fill the worker's memory before the timeout. On overflow or
    timeout ``abort`` kills the job while the readers keep draining (and
    discarding): a reader that stopped would leave the pipe full, and the
    process could then never be reaped. Returns
    ("ok" | "overflow" | "timeout", stdout, stderr).
    """
    out, err = bytearray(), bytearray()
    over = asyncio.Event()

    async def feed() -> None:
        try:
            if payload:
                proc.stdin.write(payload)
                await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass  # the job exited without reading its input
        finally:
            proc.stdin.close()

    async def pump(stream: asyncio.StreamReader, buf: bytearray) -> None:
        while chunk := await stream.read(_READ_CHUNK):
            room = cap - len(buf)
            if len(chunk) > room:
                over.set()
            buf += chunk[: max(room, 0)]

    reading = asyncio.gather(feed(), pump(proc.stdout, out), pump(proc.stderr, err))
    overflow = asyncio.ensure_future(over.wait())
    done, _ = await asyncio.wait(
        {reading, overflow}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
    )
    overflow.cancel()
    if reading not in done:
        await abort()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(reading, timeout=_DOCKER_CLI_OVERHEAD_SEC)
    else:
        await proc.wait()
    outcome = "overflow" if over.is_set() else ("ok" if reading in done else "timeout")
    return outcome, bytes(out), bytes(err)


async def remove_orphaned_containers() -> None:
    """Remove job containers a crashed predecessor of this worker left running."""
    try:
        ps = await asyncio.create_subprocess_exec(
            "docker", "ps", "-aq", "--filter", f"label={_WORKER_LABEL}={WORKER_ID}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        ids = (await ps.communicate())[0].decode().split()
        if ids:
            rm = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", *ids,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await rm.wait()
            logger.warning("Removed %d orphaned sandbox container(s)", len(ids))
    except OSError as exc:
        degraded("sandbox.orphan_cleanup", None, exc=exc)


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
        if rm.returncode != 0:
            logger.warning(
                "Container %s may still be running: docker rm -f exited %s",
                job_id, rm.returncode,
            )
    except OSError as exc:
        # Could not even launch `docker rm`. The container that ran past its
        # timeout is then still holding CPU and memory with nobody watching.
        logger.warning("Could not remove container %s: %s", job_id, exc)
    try:
        proc.kill()
        await proc.wait()
    except ProcessLookupError:
        # The docker CLI process exited on its own; the container above is
        # what actually needed killing.
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
    except Exception as exc:
        # Failing closed is right -- production gates code execution on this.
        # But "docker is not installed", "the image was never built" and "we
        # broke this function" all arrived as the same silent False, so the
        # feature could be off for weeks with no way to tell which.
        return degraded("sandbox.docker_health", False, exc=exc)
