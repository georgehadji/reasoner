"""Regression tests: the authenticated user_id must reach the ownership write.

RunPipelineCommandHandler used to call execute_run(command, router, sse_emit)
without forwarding a user_id, so PipelineExecutionService.execute_run fell back
to its user_id=None default and recorded ownership with a NULL owner. Because
is_authorized() treats a record with user_id=None as an explicit "no owner ->
allow", every authenticated run became readable/resumable/deletable by any other
authenticated caller who knew the run id.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from reasoner.application.commands import RunPipelineCommand
from reasoner.application.handlers.handlers import RunPipelineCommandHandler
from reasoner.application.ports.pipeline_ownership_port import (
    OwnershipRecord,
    is_authorized,
)
from reasoner.models import PipelineState


def _command(user_id: str | None) -> RunPipelineCommand:
    return RunPipelineCommand(
        command_id="run-abc",
        timestamp=0.0,
        problem="test problem",
        user_id=user_id,
    )


@pytest.mark.asyncio
async def test_handler_forwards_user_id_to_executor():
    """The handler must pass command.user_id down to execute_run."""
    executor = MagicMock()
    executor.execute_run = AsyncMock(return_value=PipelineState(problem="test problem"))

    handler = RunPipelineCommandHandler(
        llm_router=MagicMock(),
        event_store=None,
        pipeline_executor=executor,
    )

    await handler.handle(_command("user-42"), sse_emit=AsyncMock())

    executor.execute_run.assert_awaited_once()
    assert executor.execute_run.await_args.kwargs["user_id"] == "user-42"


@pytest.mark.asyncio
async def test_handler_preserves_anonymous_runs():
    """An unauthenticated run still forwards None rather than inventing an owner."""
    executor = MagicMock()
    executor.execute_run = AsyncMock(return_value=PipelineState(problem="test problem"))

    handler = RunPipelineCommandHandler(
        llm_router=MagicMock(),
        event_store=None,
        pipeline_executor=executor,
    )

    await handler.handle(_command(None), sse_emit=AsyncMock())

    assert executor.execute_run.await_args.kwargs["user_id"] is None


def test_null_owner_record_is_world_readable():
    """Documents why the NULL owner above was a security bug, not a cosmetic one."""
    unowned = OwnershipRecord(user_id=None, run_id="run-abc")
    assert is_authorized(unowned, "someone-else") is True

    owned = OwnershipRecord(user_id="user-42", run_id="run-abc")
    assert is_authorized(owned, "user-42") is True
    assert is_authorized(owned, "someone-else") is False
