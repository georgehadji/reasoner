"""
Tests for Domain Events

Tests the event sourcing foundation of the new architecture.
"""

import pytest
import time
from dataclasses import asdict

from reasoner.core.events.domain_events import (
    EventType,
    WidgetEventType,
    MemoryEventType,
    DomainEvent,
    PipelineStarted,
    PhaseCompleted,
    PipelineCompleted,
    make_event,
)


class TestDomainEvent:
    """Tests for base DomainEvent class."""
    
    def test_event_creation(self):
        """Test basic event creation."""
        event = DomainEvent(
            event_id="test-123",
            event_type=EventType.PHASE_STARTED,
            timestamp=time.time(),
            aggregate_id="agg-456",
            version=1,
            metadata={"phase": "classification"},
        )
        
        assert event.event_id == "test-123"
        assert event.event_type == EventType.PHASE_STARTED
        assert event.aggregate_id == "agg-456"
        assert event.version == 1
        assert event.metadata["phase"] == "classification"
    
    def test_event_to_dict(self):
        """Test event serialization."""
        event = DomainEvent(
            event_id="test-123",
            event_type=EventType.PHASE_STARTED,
            timestamp=1234567890.0,
            aggregate_id="agg-456",
            version=1,
        )
        
        data = event.to_dict()
        
        assert data["event_id"] == "test-123"
        assert data["event_type"] == "phase_started"
        assert data["aggregate_id"] == "agg-456"
        assert data["version"] == 1
    
    def test_event_immutability(self):
        """Test that events are frozen (immutable)."""
        event = DomainEvent(
            event_id="test-123",
            event_type=EventType.PHASE_STARTED,
            timestamp=time.time(),
            aggregate_id="agg-456",
            version=1,
        )
        
        # Should raise error when trying to modify
        with pytest.raises(Exception):  # FrozenInstanceError or similar
            event.event_id = "modified"


class TestPipelineEvents:
    """Tests for pipeline-specific events."""
    
    def test_pipeline_started_event(self):
        """Test PipelineStarted event."""
        event = PipelineStarted(
            event_id="test-123",
            event_type=EventType.PIPELINE_STARTED,
            timestamp=time.time(),
            aggregate_id="pipeline-456",
            version=1,
            problem="What is AI?",
            preset="claude-only",
            method="multi-perspective",
            options={"top_k": 2},
        )
        
        assert event.problem == "What is AI?"
        assert event.preset == "claude-only"
        assert event.method == "multi-perspective"
        assert event.options["top_k"] == 2
    
    def test_phase_completed_event(self):
        """Test PhaseCompleted event."""
        event = PhaseCompleted(
            event_id="test-123",
            event_type=EventType.PHASE_COMPLETED,
            timestamp=time.time(),
            aggregate_id="pipeline-456",
            version=2,
            phase_name="classification",
            result={"task_type": "analytical", "language": "English"},
            tokens={"prompt": 100, "completion": 50},
            model_used="claude-sonnet",
            duration_seconds=1.5,
        )
        
        assert event.phase_name == "classification"
        assert event.result["task_type"] == "analytical"
        assert event.tokens["prompt"] == 100
        assert event.model_used == "claude-sonnet"
        assert event.duration_seconds == 1.5
    
    def test_pipeline_completed_event(self):
        """Test PipelineCompleted event."""
        event = PipelineCompleted(
            event_id="test-123",
            event_type=EventType.PIPELINE_COMPLETED,
            timestamp=time.time(),
            aggregate_id="pipeline-456",
            version=10,
            solution={"core_solution": "The answer is 42"},
            total_tokens={"prompt": 1000, "completion": 500},
            total_duration_seconds=15.5,
            phases_completed=6,
        )
        
        assert event.solution["core_solution"] == "The answer is 42"
        assert event.total_tokens["prompt"] == 1000
        assert event.total_duration_seconds == 15.5
        assert event.phases_completed == 6


class TestEventFactory:
    """Tests for event factory function."""
    
    def test_make_event(self):
        """Test event creation via factory."""
        event = make_event(
            event_type=EventType.PHASE_STARTED,
            aggregate_id="test-agg",
            version=1,
            phase_name="classification",
        )
        
        assert isinstance(event, DomainEvent)
        assert event.event_type == EventType.PHASE_STARTED
        assert event.aggregate_id == "test-agg"
        assert event.version == 1
        assert event.phase_name == "classification"  # type: ignore
        assert event.event_id  # UUID generated
        assert event.timestamp  # Timestamp set
    
    def test_make_event_pipeline_started(self):
        """Test factory creates correct event type."""
        event = make_event(
            event_type=EventType.PIPELINE_STARTED,
            aggregate_id="pipeline-123",
            version=1,
            problem="Test problem",
            preset="test-preset",
            method="multi-perspective",
        )
        
        assert isinstance(event, PipelineStarted)
        assert event.problem == "Test problem"


class TestEventType:
    """Tests for EventType enum."""
    
    def test_event_type_values(self):
        """Test all event types are defined."""
        assert EventType.PIPELINE_STARTED.value == "pipeline_started"
        assert EventType.PHASE_STARTED.value == "phase_started"
        assert EventType.PHASE_COMPLETED.value == "phase_completed"
        assert EventType.PHASE_FAILED.value == "phase_failed"
        assert EventType.PIPELINE_COMPLETED.value == "pipeline_completed"
        assert EventType.PIPELINE_FAILED.value == "pipeline_failed"
    
    def test_widget_event_types(self):
        """Test widget event types."""
        assert WidgetEventType.WIDGET_DETECTED.value == "widget_detected"
        assert WidgetEventType.WIDGET_EXECUTED.value == "widget_executed"
        assert WidgetEventType.WIDGET_FAILED.value == "widget_failed"

    def test_memory_event_types(self):
        """Test memory event types."""
        assert MemoryEventType.MEMORY_STORED.value == "memory_stored"
        assert MemoryEventType.MEMORY_RECALLED.value == "memory_recalled"
