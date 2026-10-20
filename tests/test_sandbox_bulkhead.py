"""Sandbox jobs have bounded output, their own clock and a concurrency cap (OPS-5).

`communicate()` buffered all job output, so a print loop filled the worker's
memory before the timeout. There was no in-container timeout and no limit on
concurrent jobs, and a crashed worker left its containers running.
See docs/plans/audit-remediation-2026-10-20.md, OPS-5.

A local child process stands in for `docker run`, so this needs no daemon;
tests/integration/test_sandbox_escape.py covers the real container.
"""

from __future__ import annotations

import asyncio
import importlib
import sys

import httpx
import pytest

from reasoner.core.ports.code_executor import ExecutionLimits
from reasoner.infrastructure.execution.sandbox_worker import docker_runner


@pytest.fixture
def fake_docker(monkeypatch):
    """Run `script` instead of the container; record which jobs were killed."""
    killed: list[str] = []

    def use(script: str):
        monkeypatch.setattr(
            docker_runner, "_build_docker_argv", lambda *a, **k: [sys.executable, "-c", script]
        )

    async def _kill(job_id, proc):
        killed.append(job_id)
        proc.kill()
        await proc.wait()

    monkeypatch.setattr(docker_runner, "_force_kill", _kill)
    use.killed = killed
    return use


@pytest.mark.asyncio
async def test_an_output_flood_is_truncated_and_the_job_removed(fake_docker):
    fake_docker("import sys\nwhile True:\n    sys.stdout.write('x' * 65536); sys.stdout.flush()\n")

    result = await asyncio.wait_for(
        docker_runner.run_in_container(
            "", language="python", stdin="",
            limits=ExecutionLimits(timeout_ms=20_000, max_output_bytes=4096),
        ),
        timeout=15,
    )

    assert result.truncated and not result.success
    assert len(result.stdout) == 4096
    assert len(fake_docker.killed) == 1, "a job that overflowed must be removed, not left running"


@pytest.mark.asyncio
async def test_normal_output_and_stdin_still_work(fake_docker):
    fake_docker("import sys\nprint(sys.stdin.read().upper())\n")

    result = await docker_runner.run_in_container(
        "", language="python", stdin="hello", limits=ExecutionLimits(timeout_ms=20_000)
    )

    assert result.success and result.stdout.strip() == "HELLO"
    assert not result.truncated and fake_docker.killed == []


@pytest.mark.asyncio
async def test_a_job_past_its_timeout_is_killed(fake_docker, monkeypatch):
    monkeypatch.setattr(docker_runner, "_DOCKER_CLI_OVERHEAD_SEC", 0)
    fake_docker("import time\ntime.sleep(60)\n")

    result = await docker_runner.run_in_container(
        "", language="python", stdin="", limits=ExecutionLimits(timeout_ms=1_000)
    )

    assert result.timed_out and len(fake_docker.killed) == 1


def test_the_container_has_its_own_clock_and_a_worker_label():
    argv = docker_runner._build_docker_argv(
        "job-1", "img", ["python3", "-c", "1"],
        limits=ExecutionLimits(timeout_ms=2_500), seccomp_profile=None,
    )
    image_at = argv.index("img")
    assert argv[image_at + 1 : image_at + 5] == ["timeout", "-s", "KILL", "3"]
    assert f"reasoner.sandbox.worker={docker_runner.WORKER_ID}" in argv
    assert "--stop-timeout" in argv


@pytest.mark.asyncio
async def test_one_request_past_capacity_gets_429(monkeypatch):
    monkeypatch.setenv("SANDBOX_WORKER_TOKEN", "t")
    monkeypatch.setenv("SANDBOX_MAX_CONCURRENCY", "2")
    from reasoner.infrastructure.execution.sandbox_worker import app as app_module

    importlib.reload(app_module)
    release = asyncio.Event()

    async def _slow(*a, **k):
        await release.wait()
        from reasoner.core.ports.code_executor import ExecutionResult

        return ExecutionResult(success=True, stdout="ok")

    monkeypatch.setattr(app_module, "run_in_container", _slow)
    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://w") as client:
        post = lambda: client.post(  # noqa: E731
            "/execute", json={"code": "1"}, headers={"Authorization": "Bearer t"}
        )
        running = [asyncio.create_task(post()) for _ in range(2)]
        await asyncio.sleep(0.2)
        refused = await post()
        release.set()
        statuses = [r.status_code for r in await asyncio.gather(*running)]

    assert refused.status_code == 429
    assert statuses == [200, 200]


@pytest.mark.asyncio
async def test_a_restarted_worker_removes_its_orphans(monkeypatch):
    calls: list[tuple] = []

    class _Proc:
        returncode = 0

        def __init__(self, out=b""):
            self._out = out

        async def communicate(self):
            return self._out, b""

        async def wait(self):
            return 0

    async def _exec(*argv, **kwargs):
        calls.append(argv)
        return _Proc(b"abc\ndef\n" if argv[1] == "ps" else b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _exec)
    await docker_runner.remove_orphaned_containers()

    assert f"label=reasoner.sandbox.worker={docker_runner.WORKER_ID}" in calls[0]
    assert calls[1] == ("docker", "rm", "-f", "abc", "def")
