"""A run stops when its request does: disconnect, closed stream, or timeout (RUN-1).

``_run_phases`` waited with ``asyncio.wait``, which never cancels what it
waits on, and ``run_stream`` cancelled its task only from the disconnect
probe. A closed stream or the absolute timeout left the pipeline running and
billing with nobody reading. Once the queue filled, it blocked forever.
See docs/plans/audit-remediation-2026-10-20.md, RUN-1.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from reasoner.api import streaming
from reasoner.api.execution import pipeline as execution


class _SlowRun:
    """Stands in for the phase work: runs until cancelled, counting 'LLM calls'."""

    def __init__(self, delay: float = 0.01):
        self.delay = delay
        self.calls = 0
        self.cancelled = asyncio.Event()

    async def work(self, emit=None):
        try:
            while True:
                self.calls += 1
                if emit is not None:
                    await emit({"type": "phase_progress", "n": self.calls})
                await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


# ── _run_phases ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancelling_the_driver_cancels_the_run(monkeypatch):
    slow = _SlowRun()
    monkeypatch.setattr(
        execution, "_build_runner",
        lambda *a, **k: SimpleNamespace(run=lambda strategy, state: slow.work()),
    )
    from reasoner.application.flows.factory import WorkflowFactory

    monkeypatch.setattr(WorkflowFactory, "get_strategy", lambda self, method: object())

    driver = asyncio.create_task(execution._run_phases(
        SimpleNamespace(), SimpleNamespace(method="orchestrated"), None, "r1",
        None, None, asyncio.Event(),
    ))
    await asyncio.sleep(0.05)
    driver.cancel()  # what a disconnect or the absolute timeout does
    with pytest.raises(asyncio.CancelledError):
        await driver

    await asyncio.wait_for(slow.cancelled.wait(), timeout=1)
    calls = slow.calls
    await asyncio.sleep(0.05)
    assert slow.calls == calls, "the run kept working after its driver was cancelled"


# ── run_stream ───────────────────────────────────────────────────────────────


def _fake_registry(monkeypatch, slow: _SlowRun):
    async def handle(command, sse_emit=None, initial_state=None):
        await slow.work(sse_emit)

    handler = SimpleNamespace(handle=handle)
    registry = SimpleNamespace(command_handlers={"RunPipelineCommand": handler})
    import reasoner.application.handlers.handlers as handlers

    monkeypatch.setattr(handlers, "get_handler_registry", lambda *a, **k: registry)


def _req(run_id: str):
    return SimpleNamespace(problem="p", preset="x", client_run_id=run_id)


@pytest.mark.asyncio
async def test_closing_the_stream_cancels_the_run(monkeypatch):
    slow = _SlowRun()
    _fake_registry(monkeypatch, slow)
    gen = streaming.run_stream(_req("c1"))

    await gen.__anext__()  # preflight keepalive
    await gen.__anext__()  # first progress frame
    await gen.aclose()  # Starlette does this when the client goes away

    await asyncio.wait_for(slow.cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_unread_stream_does_not_block_the_run_forever(monkeypatch):
    """A consumer that stops reading must not leave the task stuck on a full queue."""
    slow = _SlowRun(delay=0)
    _fake_registry(monkeypatch, slow)
    gen = streaming.run_stream(_req("c2"))
    await gen.__anext__()  # preflight keepalive, yielded before the run starts
    await gen.__anext__()  # the run is now producing
    await asyncio.sleep(0.2)  # it fills the 256-slot queue, then blocks on put
    assert slow.calls >= 256
    await gen.aclose()
    await asyncio.wait_for(slow.cancelled.wait(), timeout=1)


@pytest.mark.asyncio
async def test_absolute_timeout_cancels_the_run(monkeypatch):
    slow = _SlowRun()
    _fake_registry(monkeypatch, slow)
    monkeypatch.setattr(streaming, "PIPELINE_ABSOLUTE_TIMEOUT_SECONDS", 0.1)

    frames = [f async for f in streaming.run_stream(_req("c3"))]

    assert slow.cancelled.is_set()
    assert any("PIPELINE_TIMEOUT" in f for f in frames)
