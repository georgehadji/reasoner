"""
Tests for Event-Sourced Aggregates

Tests the PipelineAggregate for event sourcing functionality.
"""


import pytest

from reasoner.core.aggregates.pipeline import (
    Aggregate,
    PipelineAggregate,
)
from reasoner.core.events.domain_events import (
    EventType,
    make_event,
)


class TestAggregateBase:
    """Tests for base Aggregate class."""

    def test_aggregate_creation(self):
        """Test aggregate initialization."""
        agg = Aggregate("test-id")

        assert agg.aggregate_id == "test-id"
        assert agg.version == 0
        assert len(agg.get_pending_events()) == 0

    def test_aggregate_version_tracking(self):
        """Test version increments with events."""
        agg = Aggregate("test-id")

        # Can't directly test without concrete implementation
        # This tests the interface
        assert agg.version == 0


class TestPipelineAggregate:
    """Tests for PipelineAggregate."""

    def test_pipeline_aggregate_creation(self):
        """Test pipeline aggregate initialization."""
        agg = PipelineAggregate("pipeline-123")

        assert agg.aggregate_id == "pipeline-123"
        assert agg.version == 0
        assert agg.state_data.problem == ""
        assert agg.state_data.status == "pending"

    def test_apply_pipeline_started(self):
        """Test applying PipelineStarted event."""
        agg = PipelineAggregate("pipeline-123")

        event = make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=1,
            problem="What is AI?",
            preset="claude-only",
            method="multi-perspective",
        )

        agg.apply(event)

        assert agg.version == 1
        assert agg.state_data.problem == "What is AI?"
        assert agg.state_data.preset == "claude-only"
        assert agg.state_data.method == "multi-perspective"
        assert agg.state_data.status == "running"
        assert agg.is_running

    def test_apply_phase_completed(self):
        """Test applying PhaseCompleted event."""
        agg = PipelineAggregate("pipeline-123")

        # First start pipeline
        start_event = make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=1,
            problem="Test problem",
            preset="test-preset",
            method="multi-perspective",
        )
        agg.apply(start_event)

        # Then complete a phase
        phase_event = make_event(
            EventType.PHASE_COMPLETED,
            aggregate_id="pipeline-123",
            version=2,
            phase_name="classification",
            result={"task_type": "analytical", "language": "English"},
            tokens={"prompt": 100, "completion": 50, "total": 150},
            model_used="claude-sonnet",
            duration_seconds=1.5,
        )
        agg.apply(phase_event)

        assert agg.version == 2
        assert agg.state_data.task_type == "analytical"
        assert agg.state_data.language == "English"
        assert len(agg.state_data.phase_results) == 1
        assert agg.state_data.phase_results[0]["phase"] == "classification"
        assert agg.state_data.total_tokens["total"] == 150

    def test_apply_pipeline_completed(self):
        """Test applying PipelineCompleted event."""
        agg = PipelineAggregate("pipeline-123")

        # Start and complete pipeline
        agg.apply(make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=1,
            problem="Test",
            preset="test",
            method="multi-perspective",
        ))

        agg.apply(make_event(
            EventType.PIPELINE_COMPLETED,
            aggregate_id="pipeline-123",
            version=2,
            solution={"core_solution": "The answer"},
            total_tokens={"total": 500},
            total_duration_seconds=10.5,
            phases_completed=6,
        ))

        assert agg.version == 2
        assert agg.state_data.status == "completed"
        assert agg.state_data.synthesis["core_solution"] == "The answer"
        assert agg.is_completed

    def test_version_mismatch_raises_error(self):
        """Test that version mismatch raises error."""
        agg = PipelineAggregate("pipeline-123")

        # Try to apply event with wrong version
        event = make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=5,  # Wrong version
            problem="Test",
            preset="test",
            method="test",
        )

        with pytest.raises(ValueError, match="version"):
            agg.apply(event)

    def test_aggregate_mismatch_raises_error(self):
        """Test that aggregate ID mismatch raises error."""
        agg = PipelineAggregate("pipeline-123")

        event = make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-456",  # Wrong aggregate
            version=1,
            problem="Test",
            preset="test",
            method="test",
        )

        with pytest.raises(ValueError, match="aggregate_id"):
            agg.apply(event)

    def test_record_event(self):
        """Test recording events for persistence."""
        agg = PipelineAggregate("pipeline-123")

        event = make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=1,
            problem="Test",
            preset="test",
            method="test",
        )

        agg.record_event(event)

        # Event should be in pending
        pending = agg.get_pending_events()
        assert len(pending) == 1
        assert pending[0].event_type == EventType.PIPELINE_STARTED

        # State should be updated
        assert agg.state_data.problem == "Test"

    def test_clear_pending_events(self):
        """Test clearing pending events after persistence."""
        agg = PipelineAggregate("pipeline-123")

        agg.record_event(make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=1,
            problem="Test",
            preset="test",
            method="test",
        ))

        assert len(agg.get_pending_events()) == 1

        agg.clear_pending_events()

        assert len(agg.get_pending_events()) == 0

    def test_load_from_history(self):
        """Test rebuilding state from event history."""
        agg = PipelineAggregate("pipeline-123")

        # Create event history
        history = [
            make_event(
                EventType.PIPELINE_STARTED,
                aggregate_id="pipeline-123",
                version=1,
                problem="History Test",
                preset="test",
                method="jury",
            ),
            make_event(
                EventType.PHASE_COMPLETED,
                aggregate_id="pipeline-123",
                version=2,
                phase_name="classification",
                result={"task_type": "strategic"},
                tokens={},
                model_used="test",
                duration_seconds=1.0,
            ),
        ]

        agg.load_from_history(history)

        assert agg.version == 2
        assert agg.state_data.problem == "History Test"
        assert agg.state_data.method == "jury"
        assert agg.state_data.task_type == "strategic"

    def test_to_dict_serialization(self):
        """Test aggregate serialization."""
        agg = PipelineAggregate("pipeline-123")

        agg.record_event(make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=1,
            problem="Serialize Test",
            preset="test",
            method="test",
        ))

        data = agg.to_dict()

        assert data["aggregate_id"] == "pipeline-123"
        assert data["version"] == 1
        assert "state" in data
        assert len(data["pending_events"]) == 1

    def test_can_resume(self):
        """Test resume capability detection."""
        agg = PipelineAggregate("pipeline-123")

        # Initially can resume
        assert agg.can_resume()

        # After completion, cannot resume
        agg.apply(make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=1,
            problem="Test",
            preset="test",
            method="test",
        ))
        agg.apply(make_event(
            EventType.PIPELINE_COMPLETED,
            aggregate_id="pipeline-123",
            version=2,
            solution={},
            total_tokens={},
            total_duration_seconds=1.0,
        ))

        assert not agg.can_resume()

    def test_get_last_phase(self):
        """Test getting last completed phase."""
        agg = PipelineAggregate("pipeline-123")

        # No phases yet
        assert agg.get_last_phase() is None

        # Add phases
        agg.apply(make_event(
            EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=1,
            problem="Test",
            preset="test",
            method="test",
        ))
        agg.apply(make_event(
            EventType.PHASE_COMPLETED,
            aggregate_id="pipeline-123",
            version=2,
            phase_name="classification",
            result={},
            tokens={},
            model_used="test",
            duration_seconds=1.0,
        ))
        agg.apply(make_event(
            EventType.PHASE_COMPLETED,
            aggregate_id="pipeline-123",
            version=3,
            phase_name="decomposition",
            result={},
            tokens={},
            model_used="test",
            duration_seconds=2.0,
        ))

        assert agg.get_last_phase() == "decomposition"
