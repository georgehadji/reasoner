"""Sandbox failures that used to leave no trace.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

``check_docker_health`` gates whether code execution is enabled in production
(``GET /health``), and every way it can fail arrived as the same silent
``False``: docker not installed, image never built, or a bug in the function
itself. The feature could be off for weeks with no way to tell which.

``_force_kill`` runs when a container outlived its timeout. Both of its
handlers swallowed, so a ``docker rm -f`` that failed -- leaving the runaway
container holding CPU and memory -- looked exactly like one that worked.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from reasoner.infrastructure.execution.sandbox_worker import docker_runner


class _FakeProc:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.killed = False

    async def wait(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self.killed = True


@pytest.mark.asyncio
async def test_an_unreachable_docker_says_why(monkeypatch, caplog):
    async def _no_docker(*args, **kwargs):
        raise FileNotFoundError("docker: command not found")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _no_docker)

    with caplog.at_level(logging.WARNING):
        healthy = await docker_runner.check_docker_health()

    assert healthy is False, "the health check must still fail closed"
    assert any("sandbox.docker_health" in r.message for r in caplog.records), (
        f"code execution was disabled with no reason given: "
        f"{[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_a_healthy_docker_reports_nothing(monkeypatch, caplog):
    async def _ok(*args, **kwargs):
        return _FakeProc(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _ok)

    with caplog.at_level(logging.WARNING):
        healthy = await docker_runner.check_docker_health()

    assert healthy is True
    assert not caplog.records, f"a healthy check logged: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_a_container_that_would_not_die_is_reported(monkeypatch, caplog):
    """`docker rm -f` exiting non-zero means the runaway container is still up."""
    async def _rm_fails(*args, **kwargs):
        return _FakeProc(returncode=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _rm_fails)
    cli = _FakeProc()

    with caplog.at_level(logging.WARNING):
        await docker_runner._force_kill("job-abc", cli)

    assert cli.killed, "the local docker CLI process must still be killed"
    assert any("job-abc" in r.message for r in caplog.records), (
        f"a container that survived removal left no trace: "
        f"{[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_a_docker_cli_that_already_exited_is_not_an_error(monkeypatch, caplog):
    """The narrowed handler must still tolerate the ordinary race."""
    async def _rm_ok(*args, **kwargs):
        return _FakeProc(returncode=0)

    class _AlreadyGone(_FakeProc):
        def kill(self) -> None:
            raise ProcessLookupError("no such process")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _rm_ok)

    with caplog.at_level(logging.WARNING):
        await docker_runner._force_kill("job-abc", _AlreadyGone())

    assert not caplog.records, f"an ordinary race was reported: {[r.message for r in caplog.records]}"


@pytest.mark.asyncio
async def test_untrusted_code_left_on_disk_is_reported(monkeypatch, caplog):
    """The tempdir cleanup was wrapped in a try whose body already had
    ``ignore_errors=True``, so the handler never caught anything -- and a
    removal that silently did nothing left the executed script on disk.
    Windows file locks make that a real case, not a theoretical one."""
    import shutil

    from reasoner.infrastructure.execution.subprocess_executor import SubprocessExecutor

    real_rmtree = shutil.rmtree
    skipped: list[str] = []

    def _do_nothing(path, *a, **kw):
        skipped.append(str(path))

    monkeypatch.setattr(shutil, "rmtree", _do_nothing)

    try:
        with caplog.at_level(logging.WARNING):
            result = await SubprocessExecutor().execute("print('ok')")
    finally:
        for path in skipped:
            real_rmtree(path, ignore_errors=True)

    assert result.success, f"the run itself must be unaffected: {result.stderr}"
    assert any("untrusted code left on disk" in r.message for r in caplog.records), (
        f"the leaked tempdir was not reported: {[r.message for r in caplog.records]}"
    )
