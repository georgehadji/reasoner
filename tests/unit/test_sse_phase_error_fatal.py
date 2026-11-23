"""A phase error frame says whether the run is over.

on_phase_error sends a run-level ``error`` frame for every phase failure, fatal
or not. The browser ended the stream on any ``error`` frame, so a non-critical
phase timing out (Iterative Critique's debate on a slow model) hid a run that
was still going on to synthesis. The frame now carries ``fatal`` so the client
can tell the two apart.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from reasoner.application.flows.base import PhaseStep
from reasoner.domain.pipeline_state import PipelineState


@pytest.mark.asyncio
@pytest.mark.parametrize("fatal", [False, True])
async def test_error_frame_carries_fatal(monkeypatch, fatal):
    from reasoner.api.execution import sse_observer

    async def _persist_event(event):
        return None

    monkeypatch.setattr(sse_observer, "_persist_event", _persist_event)
    sent: list = []

    async def _emit(payload):
        sent.append(payload)

    stream = sse_observer.RunStream("run-1", _emit, lambda payload: sent.append(payload))
    observer = sse_observer.SseRunObserver(stream, MagicMock(), MagicMock(), "preset")
    step = PhaseStep(3, "Adversarial Debate", lambda: None, lambda: None)

    await observer.on_phase_error(
        step, PipelineState(problem="p"), TimeoutError(), "Phase timeout", fatal
    )

    frame = next(p for p in sent if p.get("type") == "error")
    assert frame["fatal"] is fatal
