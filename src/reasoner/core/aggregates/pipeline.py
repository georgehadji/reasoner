"""
Reasoner - Event-Sourced Aggregates

Aggregates are the core transactional boundaries in DDD.
They maintain state by applying domain events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeVar, Generic
import copy

from reasoner.core.events.domain_events import (
    DomainEvent,
    PipelineStarted,
    PhaseStarted,
    PhaseCompleted,
    PhaseFailed,
    PipelineCompleted,
    PipelineFailed,
    ContextFetched,
    ContextVetted,
    PerspectiveGenerated,
    CandidateScored,
    StressTestCompleted,
    EventType,
    WidgetDetected,
    WidgetExecuted,
    WidgetFailed,
)


T = TypeVar('T')


class Aggregate:
    """
    Base class for all aggregates.
    
    Provides:
    - Event sourcing (apply events to rebuild state)
    - Version tracking for optimistic concurrency
    - Event accumulation for persistence
    """
    
    def __init__(self, aggregate_id: str):
        self.aggregate_id = aggregate_id
        self.version = 0
        self._pending_events: list[DomainEvent] = []
        self._state: dict[str, Any] = {}
    
    def apply(self, event: DomainEvent) -> None:
        """
        Apply an event to update state.
        
        This is the core of event sourcing - state is derived
        from the sequence of events.
        """
        if event.aggregate_id != self.aggregate_id:
            raise ValueError(
                f"Event aggregate_id {event.aggregate_id} "
                f"doesn't match aggregate {self.aggregate_id}"
            )
        
        # Version check for optimistic concurrency
        if event.version != self.version + 1:
            raise ValueError(
                f"Event version {event.version} doesn't match "
                f"expected version {self.version + 1}"
            )
        
        self._apply_event(event)
        self.version = event.version
    
    def _apply_event(self, event: DomainEvent) -> None:
        """
        Subclass hook to apply event-specific logic.
        
        Override this in subclasses to handle specific event types.
        """
        pass
    
    def record_event(self, event: DomainEvent) -> None:
        """
        Record a new event for later persistence.
        
        Events are accumulated and should be persisted atomically.
        """
        self._pending_events.append(event)
        self.apply(event)
    
    def get_pending_events(self) -> list[DomainEvent]:
        """Get events that haven't been persisted yet."""
        return list(self._pending_events)
    
    def clear_pending_events(self) -> None:
        """Clear pending events after persistence."""
        self._pending_events.clear()
    
    def load_from_history(self, history: list[DomainEvent]) -> None:
        """
        Rebuild state from event history.
        
        This is how aggregates are reconstructed from storage.
        """
        for event in sorted(history, key=lambda e: e.version):
            self.apply(event)
    
    @property
    def state(self) -> dict[str, Any]:
        """Get current state as dictionary."""
        return copy.deepcopy(self._state)


@dataclass
class PipelineStateData:
    """Data class representing pipeline state."""
    problem: str = ""
    preset: str = ""
    method: str = ""
    language: str = "English"
    task_type: str = ""
    decomposition: dict[str, Any] = field(default_factory=dict)
    web_discovery_results: list[dict[str, Any]] = field(default_factory=list)
    vetted_context: list[dict[str, Any]] = field(default_factory=list)
    perspectives: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    scores: list[dict[str, Any]] = field(default_factory=list)
    stress_tests: list[dict[str, Any]] = field(default_factory=list)
    synthesis: dict[str, Any] = field(default_factory=dict)
    phase_results: list[dict[str, Any]] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_tokens: dict[str, int] = field(default_factory=dict)
    start_time: float = 0.0
    end_time: float = 0.0
    status: str = "pending"  # pending, running, completed, failed


class PipelineAggregate(Aggregate):
    """
    Event-sourced aggregate for pipeline execution.
    
    Maintains the complete state of a pipeline run by applying
    domain events. Can be reconstructed from event history for
    resume functionality.
    """
    
    def __init__(self, aggregate_id: str):
        super().__init__(aggregate_id)
        self._state_data = PipelineStateData()
    
    def _apply_event(self, event: DomainEvent) -> None:
        """Apply event-specific state changes."""
        
        if isinstance(event, PipelineStarted):
            self._apply_pipeline_started(event)
        elif isinstance(event, PhaseStarted):
            self._apply_phase_started(event)
        elif isinstance(event, PhaseCompleted):
            self._apply_phase_completed(event)
        elif isinstance(event, PhaseFailed):
            self._apply_phase_failed(event)
        elif isinstance(event, PipelineCompleted):
            self._apply_pipeline_completed(event)
        elif isinstance(event, PipelineFailed):
            self._apply_pipeline_failed(event)
        elif isinstance(event, ContextFetched):
            self._apply_context_fetched(event)
        elif isinstance(event, ContextVetted):
            self._apply_context_vetted(event)
        elif isinstance(event, PerspectiveGenerated):
            self._apply_perspective_generated(event)
        elif isinstance(event, CandidateScored):
            self._apply_candidate_scored(event)
        elif isinstance(event, StressTestCompleted):
            self._apply_stress_test_completed(event)
    
    def _apply_pipeline_started(self, event: PipelineStarted) -> None:
        self._state_data.problem = event.problem
        self._state_data.preset = event.preset
        self._state_data.method = event.method
        self._state_data.start_time = event.timestamp
        self._state_data.status = "running"
        self._state_data.logs.append(f"Pipeline started: {event.method}")
    
    def _apply_phase_started(self, event: PhaseStarted) -> None:
        self._state_data.logs.append(f"Phase started: {event.phase_name}")
    
    def _apply_phase_completed(self, event: PhaseCompleted) -> None:
        self._state_data.phase_results.append({
            'phase': event.phase_name,
            'result': event.result,
            'tokens': event.tokens,
            'model_used': event.model_used,
            'duration': event.duration_seconds,
        })
        
        # Update token counts
        for key, value in event.tokens.items():
            current = self._state_data.total_tokens.get(key, 0)
            self._state_data.total_tokens[key] = current + value
        
        # Handle specific phase results
        if event.phase_name == "classification":
            if isinstance(event.result, dict):
                self._state_data.task_type = event.result.get('task_type', '')
                self._state_data.language = event.result.get('language', 'English')
        elif event.phase_name == "decomposition":
            self._state_data.decomposition = event.result or {}
        elif event.phase_name == "perspective":
            if event.result:
                self._state_data.perspectives.append(event.result)
        elif event.phase_name == "scoring":
            if event.result:
                self._state_data.scores.append(event.result)
        
        self._state_data.logs.append(
            f"Phase completed: {event.phase_name} "
            f"({event.duration_seconds:.2f}s, {event.tokens.get('total', 0)} tokens)"
        )
    
    def _apply_phase_failed(self, event: PhaseFailed) -> None:
        self._state_data.errors.append(
            f"Phase {event.phase_name} failed: {event.error}"
        )
        self._state_data.logs.append(
            f"Phase failed: {event.phase_name} (attempt {event.retry_count})"
        )
    
    def _apply_pipeline_completed(self, event: PipelineCompleted) -> None:
        self._state_data.synthesis = event.solution
        self._state_data.total_tokens = event.total_tokens
        self._state_data.end_time = event.timestamp
        self._state_data.status = "completed"
        self._state_data.logs.append(
            f"Pipeline completed: {event.total_duration_seconds:.2f}s"
        )
    
    def _apply_pipeline_failed(self, event: PipelineFailed) -> None:
        self._state_data.errors.append(f"Pipeline failed: {event.error}")
        self._state_data.end_time = event.timestamp
        self._state_data.status = "failed"
        self._state_data.logs.append(f"Pipeline failed at {event.phase_at_failure}")
    
    def _apply_context_fetched(self, event: ContextFetched) -> None:
        self._state_data.logs.append(
            f"Context fetched: {event.result_count} results from {event.source_type}"
        )
    
    def _apply_context_vetted(self, event: ContextVetted) -> None:
        self._state_data.vetted_context = event.flags
        self._state_data.logs.append(
            f"Context vetted: {event.sources_vetted} sources, "
            f"{len(event.flags)} flags"
        )
    
    def _apply_perspective_generated(self, event: PerspectiveGenerated) -> None:
        self._state_data.logs.append(
            f"Perspective generated: {event.perspective_type} "
            f"using {event.model_used}"
        )
    
    def _apply_candidate_scored(self, event: CandidateScored) -> None:
        self._state_data.candidates.append({
            'id': event.candidate_id,
            'scores': event.scores,
            'total': event.total_score,
            'flags': event.flags,
        })
    
    def _apply_stress_test_completed(self, event: StressTestCompleted) -> None:
        self._state_data.stress_tests.append({
            'candidate_id': event.candidate_id,
            'scenario': event.scenario,
            'survival_rate': event.survival_rate,
            'failure_mode': event.failure_mode,
        })
    
    # Properties for accessing state
    @property
    def state_data(self) -> PipelineStateData:
        """Get current pipeline state."""
        return self._state_data
    
    @property
    def is_completed(self) -> bool:
        """Check if pipeline has completed."""
        return self._state_data.status == "completed"
    
    @property
    def is_failed(self) -> bool:
        """Check if pipeline has failed."""
        return self._state_data.status == "failed"
    
    @property
    def is_running(self) -> bool:
        """Check if pipeline is still running."""
        return self._state_data.status == "running"
    
    def can_resume(self) -> bool:
        """Check if pipeline can be resumed from current state."""
        return self._state_data.status in ("running", "pending")
    
    def get_last_phase(self) -> str | None:
        """Get the name of the last completed phase."""
        if not self._state_data.phase_results:
            return None
        return self._state_data.phase_results[-1]['phase']
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary."""
        from dataclasses import asdict
        return {
            'aggregate_id': self.aggregate_id,
            'version': self.version,
            'state': asdict(self._state_data),
            'pending_events': [e.to_dict() for e in self.get_pending_events()],
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PipelineAggregate:
        """Deserialize from dictionary."""
        from reasoner.core.events.domain_events import make_event
        
        aggregate = cls(data['aggregate_id'])
        aggregate.version = data['version']
        
        # Restore state data
        state_dict = data.get('state', {})
        for key, value in state_dict.items():
            if hasattr(aggregate._state_data, key):
                setattr(aggregate._state_data, key, value)
        
        # Replay pending events
        for event_dict in data.get('pending_events', []):
            event = make_event(
                EventType(event_dict['event_type']),
                event_dict['aggregate_id'],
                event_dict['version'],
                **{k: v for k, v in event_dict.items() 
                   if k not in ('event_type', 'aggregate_id', 'version')}
            )
            aggregate._pending_events.append(event)
        
        return aggregate


@dataclass
class WidgetStateData:
    """Data class representing widget state."""
    widget_type: str = ""
    query: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending, detected, executing, completed, failed
    error: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration_seconds: float = 0.0


class WidgetAggregate(Aggregate):
    """
    Event-sourced aggregate for widget execution.
    
    Tracks widget lifecycle from detection through execution.
    """
    
    def __init__(self, aggregate_id: str):
        super().__init__(aggregate_id)
        self._state_data = WidgetStateData()
    
    def _apply_event(self, event: DomainEvent) -> None:
        """Apply event-specific state changes."""
        
        from reasoner.core.events.domain_events import (
            WidgetDetected, WidgetExecuted, WidgetFailed
        )
        
        if isinstance(event, WidgetDetected):
            self._apply_widget_detected(event)
        elif isinstance(event, WidgetExecuted):
            self._apply_widget_executed(event)
        elif isinstance(event, WidgetFailed):
            self._apply_widget_failed(event)
    
    def _apply_widget_detected(self, event: WidgetDetected) -> None:
        self._state_data.widget_type = event.widget_type
        self._state_data.status = "detected"
        self._state_data.logs.append(f"Widget detected: {event.widget_type}")
    
    def _apply_widget_executed(self, event: WidgetExecuted) -> None:
        self._state_data.result = event.result
        self._state_data.status = "completed"
        self._state_data.end_time = event.timestamp
        self._state_data.duration_seconds = event.duration_seconds
        self._state_data.logs.append(
            f"Widget completed: {event.widget_type} "
            f"({event.duration_seconds:.2f}s)"
        )
    
    def _apply_widget_failed(self, event: WidgetFailed) -> None:
        self._state_data.status = "failed"
        self._state_data.error = event.error
        self._state_data.end_time = event.timestamp
        self._state_data.logs.append(f"Widget failed: {event.error}")
    
    @property
    def state_data(self) -> WidgetStateData:
        """Get current widget state."""
        return self._state_data
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary."""
        from dataclasses import asdict
        return {
            'aggregate_id': self.aggregate_id,
            'version': self.version,
            'state': asdict(self._state_data),
            'pending_events': [e.to_dict() for e in self.get_pending_events()],
        }
