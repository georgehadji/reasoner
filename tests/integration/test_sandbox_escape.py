"""Real escape tests against the container sandbox — security-remediation-plan.md
Phase 1 acceptance criteria: "Escape tests cannot read/write a sentinel
outside the job workspace", "the worker has no credentials, database
access, or network route to private services".

Requires a live Docker daemon AND the sandbox image already built
(``docker build -t reasoner-sandbox-python:latest -f
src/reasoner/infrastructure/execution/sandbox_worker/sandbox_image/Dockerfile
src/reasoner/infrastructure/execution/sandbox_worker/sandbox_image``).
Everything here is marked ``@pytest.mark.docker`` and auto-skips when no
daemon is reachable — running green here is NOT proof of isolation; it only
runs where a real daemon exists (typically CI with Docker enabled, or a
developer machine with Docker Desktop/dockerd running).
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from reasoner.core.ports.code_executor import ExecutionLimits
from reasoner.infrastructure.execution.runners.python_runner import PYTHON_SANDBOX_IMAGE
from reasoner.infrastructure.execution.sandbox_worker.docker_runner import run_in_container


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=5, check=False
        )
        return result.returncode == 0
    except Exception:
        return False


def _sandbox_image_available() -> bool:
    if not _docker_available():
        return False
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", PYTHON_SANDBOX_IMAGE],
            capture_output=True, timeout=5, check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(not _docker_available(), reason="No reachable Docker daemon"),
    pytest.mark.skipif(
        not _sandbox_image_available(),
        reason=f"{PYTHON_SANDBOX_IMAGE} not built — see module docstring",
    ),
]


async def test_cannot_write_outside_the_ephemeral_workspace() -> None:
    """Attempt to write a sentinel to a path outside the container's own
    tmpfs. read-only rootfs must reject it."""
    code = "open('/etc/reasoner-escape-sentinel', 'w').write('escaped')"
    result = await run_in_container(
        code, language="python", stdin="", limits=ExecutionLimits(timeout_ms=10_000)
    )
    assert result.success is False


async def test_cannot_reach_the_network() -> None:
    """--network none must make any socket call fail, not silently succeed."""
    code = (
        "import socket\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.settimeout(3)\n"
        "s.connect(('8.8.8.8', 53))\n"
        "print('CONNECTED')\n"
    )
    result = await run_in_container(
        code, language="python", stdin="", limits=ExecutionLimits(timeout_ms=10_000)
    )
    assert "CONNECTED" not in result.stdout
    assert result.success is False


async def test_memory_limit_is_enforced() -> None:
    """Allocating well past the memory cap must fail/get killed, not
    silently succeed and pressure the host."""
    code = (
        "buf = bytearray(1024 * 1024 * 1024)  # 1GB against a much smaller cap\n"
        "print('ALLOCATED')\n"
    )
    result = await run_in_container(
        code, language="python", stdin="",
        limits=ExecutionLimits(timeout_ms=10_000, memory_limit_mb=64),
    )
    assert "ALLOCATED" not in result.stdout


async def test_wall_clock_timeout_is_enforced() -> None:
    code = "import time\ntime.sleep(30)\n"
    result = await run_in_container(
        code, language="python", stdin="", limits=ExecutionLimits(timeout_ms=2_000)
    )
    assert result.timed_out is True


async def test_container_is_removed_after_run() -> None:
    """--rm must actually clean up — no leaked containers after a run."""
    before = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=reasoner-sandbox-", "-q"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    assert before == ""  # sanity: no leftovers from a prior failed run

    await run_in_container(
        "print('ok')", language="python", stdin="", limits=ExecutionLimits(timeout_ms=10_000)
    )

    after = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=reasoner-sandbox-", "-q"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    assert after == ""
