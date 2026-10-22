"""RUN-6, RUN-7, RUN-8: "how did the run end" is a closed set, not `state is None`.

`execute_run` used to return the state after a Stop and `None` after a failed
preflight or a spend-cap rejection; the handler then ran its success block for
the first (publishing PIPELINE_COMPLETED for a run the user stopped, and
emitting an `end` frame that agent and MCP results mistook for the terminal
frame) and dereferenced `None` for the second (`AttributeError: 'NoneType'
object has no attribute 'phase_tokens'`, surfacing as "Internal error").
`RunOutcome` makes each ending an explicit value the handler matches on.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from reasoner.application.commands import RunPipelineCommand
from reasoner.application.handlers.handlers import RunPipelineCommandHandler
from reasoner.application.ports.run_outcome import RunOutcome
from reasoner.core.events.domain_events import EventType
from reasoner.domain.pipeline_state import PipelineState

pytestmark = pytest.mark.unit


class _Bus:
    def __init__(self) -> None:
        self.events: list = []

    async def publish(self, event) -> None:
        self.events.append(event)

    @property
    def types(self) -> list[EventType]:
        return [e.event_type for e in self.events]


def _command() -> RunPipelineCommand:
    return RunPipelineCommand(command_id="run-outcome-1", timestamp=0.0, problem="p")


async def _handle(outcome: RunOutcome):
    executor = SimpleNamespace(execute_run=AsyncMock(return_value=outcome))
    handler = RunPipelineCommandHandler(
        llm_router=MagicMock(), event_store=None, pipeline_executor=executor
    )
    handler.event_bus = _Bus()
    frames: list[dict] = []

    async def emit(frame) -> None:
        frames.append(frame)

    aggregate = await handler.handle(_command(), sse_emit=emit)
    return handler.event_bus, frames, aggregate


async def test_completed_publishes_completion_and_no_end_frame() -> None:
    bus, frames, _ = await _handle(
        RunOutcome("completed", state=PipelineState(problem="p"))
    )

    assert EventType.PIPELINE_COMPLETED in bus.types
    # RUN-6: the real `done` frame is the terminal one; a trailing `end` made
    # agent/MCP results read cost 0, tokens 0 and no errors.
    assert [f for f in frames if f.get("type") == "end"] == []


async def test_stopped_run_is_not_published_as_completed() -> None:
    """RUN-7: Stop returned the state, so the success block ran."""
    bus, frames, _ = await _handle(
        RunOutcome("cancelled", state=PipelineState(problem="p"), reason="stopped by user")
    )

    assert EventType.PIPELINE_COMPLETED not in bus.types
    assert EventType.PIPELINE_FAILED in bus.types
    assert [f for f in frames if f.get("type") == "end"] == []


async def test_rejected_run_names_its_cause_instead_of_attribute_error() -> None:
    """RUN-8: a run refused before it started has no state to read."""
    bus, frames, aggregate = await _handle(
        RunOutcome("rejected", state=None, reason="spend cap reached")
    )

    assert EventType.PIPELINE_COMPLETED not in bus.types
    failed = [e for e in bus.events if e.event_type == EventType.PIPELINE_FAILED]
    assert failed and "spend cap reached" in failed[0].error
    # The stream already carried the cause; the handler adds no generic frame.
    assert [f for f in frames if f.get("code") == "INTERNAL_ERROR"] == []
    assert aggregate is not None


async def test_failed_run_does_not_raise_or_double_report() -> None:
    bus, frames, _ = await _handle(
        RunOutcome("failed", state=PipelineState(problem="p"), reason="provider exploded")
    )

    assert EventType.PIPELINE_COMPLETED not in bus.types
    assert EventType.PIPELINE_FAILED in bus.types
    assert [f for f in frames if f.get("code") == "INTERNAL_ERROR"] == []
