"""
Regression tests for BUG-003: StopPipelineCommandHandler must use the
per-run _cancelled_runs dict instead of the removed _cancel_flag global.
"""

import pytest
from reasoner.application.commands import StopPipelineCommand
from reasoner.application.handlers.handlers import StopPipelineCommandHandler
import reasoner.api as api


class TestStopPipelineCommandHandler:
    @pytest.mark.asyncio
    async def test_stop_sets_cancelled_runs_entry(self, monkeypatch):
        """Handler should mark the pipeline_id in _cancelled_runs."""
        handler = StopPipelineCommandHandler(event_store=None)
        command = StopPipelineCommand(
            command_id="cmd-001",
            timestamp=0.0,
            pipeline_id="pipe-123",
            reason="user_requested",
        )

        # Ensure clean state and register the run
        await api._run_store.reset()
        await api._run_store.add("pipe-123")

        result = await handler.handle(command)

        assert result["status"] == "stopped"
        assert result["pipeline_id"] == "pipe-123"
        event = await api._run_store.get_cancel_event("pipe-123")
        assert event is not None and event.is_set()

        # Cleanup
        await api._run_store.reset()

    @pytest.mark.asyncio
    async def test_stop_with_event_store_persists_event(self, monkeypatch):
        """Handler should persist a PHASE_FAILED event when event_store is provided."""
        saved_events = []

        class FakeEventStore:
            async def save_events(self, events):
                saved_events.extend(events)

        handler = StopPipelineCommandHandler(event_store=FakeEventStore())
        command = StopPipelineCommand(
            command_id="cmd-002",
            timestamp=0.0,
            pipeline_id="pipe-456",
            reason="timeout",
        )

        await api._run_store.reset()
        await api._run_store.add("pipe-456")

        result = await handler.handle(command)

        assert result["status"] == "stopped"
        event = await api._run_store.get_cancel_event("pipe-456")
        assert event is not None and event.is_set()
        assert len(saved_events) == 1
        assert saved_events[0].phase_name == "user_stopped"
        assert "timeout" in saved_events[0].error

        await api._run_store.reset()
