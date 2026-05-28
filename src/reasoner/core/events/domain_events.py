"""
Reasoner - Domain Events for Event Sourcing

All events are immutable (frozen dataclasses) and represent
something that happened in the domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from datetime import datetime
from enum import Enum


class PipelineEventType(str, Enum):
    """Pipeline lifecycle and method events."""
    PIPELINE_STARTED = "pipeline_started"
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    PHASE_FAILED = "phase_failed"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"
    PERSPECTIVE_GENERATED = "perspective_generated"
    CANDIDATE_SCORED = "candidate_scored"
    STRESS_TEST_COMPLETED = "stress_test_completed"
    RETRY_ATTEMPTED = "retry_attempted"
    CONTEXT_FETCHED = "context_fetched"
    CONTEXT_VETTED = "context_vetted"
    SOURCE_ADDED = "source_added"
    ERROR_OCCURRED = "error_occurred"
    LLM_GENERATION_COMPLETED = "llm_generation_completed"


class WidgetEventType(str, Enum):
    """Widget lifecycle events."""
    WIDGET_DETECTED = "widget_detected"
    WIDGET_EXECUTED = "widget_executed"
    WIDGET_FAILED = "widget_failed"


class MemoryEventType(str, Enum):
    """Neuro memory events."""
    MEMORY_STORED = "memory_stored"
    MEMORY_RECALLED = "memory_recalled"


class SaaSEventType(str, Enum):
    """SaaS / billing events."""
    USER_REGISTERED = "user_registered"
    USER_LOGGED_IN = "user_logged_in"
    SUBSCRIPTION_CREATED = "subscription_created"
    SUBSCRIPTION_UPDATED = "subscription_updated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    QUOTA_EXCEEDED = "quota_exceeded"
    QUOTA_RESET = "quota_reset"
    QUERY_LOGGED = "query_logged"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SUCCEEDED = "payment_succeeded"


# Union type for backward compatibility
_AllEventType = PipelineEventType | WidgetEventType | MemoryEventType | SaaSEventType

# Old import path still resolves
EventType = PipelineEventType  # type: ignore[misc]

# For consumers that need to handle all types:
ALL_EVENT_TYPES: dict[str, _AllEventType] = {
    e.value: e for e in (
        list(PipelineEventType) + list(WidgetEventType) +
        list(MemoryEventType) + list(SaaSEventType)
    )
}


@dataclass(frozen=True)
class DomainEvent:
    """
    Base class for all domain events.
    
    All events are immutable and contain:
    - event_id: Unique identifier
    - event_type: Type of event
    - timestamp: When it happened
    - aggregate_id: ID of the aggregate this event belongs to
    - version: Event version for optimistic concurrency
    """
    event_id: str
    event_type: _AllEventType
    timestamp: float
    aggregate_id: str
    version: int
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary for storage."""
        from dataclasses import asdict
        return {
            **asdict(self),
            'event_type': self.event_type.value,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainEvent:
        """Deserialize event from dictionary."""
        return cls(**data)


# ─────────────────────────────────────────────────────────────────────
# PIPELINE EVENTS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PipelineStarted(DomainEvent):
    """Pipeline execution started."""
    problem: str = ""
    preset: str = ""
    method: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhaseStarted(DomainEvent):
    """Phase execution started."""
    phase_name: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhaseCompleted(DomainEvent):
    """Phase execution completed successfully."""
    phase_name: str = ""
    result: Any = None
    tokens: dict[str, int] = field(default_factory=dict)
    model_used: str = ""
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class PhaseFailed(DomainEvent):
    """Phase execution failed."""
    phase_name: str = ""
    error: str = ""
    retry_count: int = 0


@dataclass(frozen=True)
class PipelineCompleted(DomainEvent):
    """Pipeline execution completed successfully."""
    solution: dict[str, Any] = field(default_factory=dict)
    total_tokens: dict[str, int] = field(default_factory=dict)
    total_duration_seconds: float = 0.0
    phases_completed: int = 0


@dataclass(frozen=True)
class PipelineFailed(DomainEvent):
    """Pipeline execution failed."""
    error: str = ""
    phase_at_failure: str = ""
    phases_completed: int = 0


@dataclass(frozen=True)
class LLMGenerationCompleted(DomainEvent):
    """LLM generation completed for a specific phase/role."""
    model_name: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    raw_response: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    duration_seconds: float = 0.0
    pipeline_id: str = ""  # Redundant but useful for tracing
    phase_name: str = ""  # Redundant but useful for tracing


# ─────────────────────────────────────────────────────────────────────
# CONTEXT EVENTS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ContextFetched(DomainEvent):
    """Context fetched from external source."""
    source_type: str = ""
    query: str = ""
    result_count: int = 0


@dataclass(frozen=True)
class ContextVetted(DomainEvent):
    """Context vetting completed."""
    sources_vetted: int = 0
    flags: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class SourceAdded(DomainEvent):
    """New source added to context."""
    url: str = ""
    title: str = ""
    source_type: str = ""
    relevance_score: float = 0.0


# ─────────────────────────────────────────────────────────────────────
# METHOD-SPECIFIC EVENTS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PerspectiveGenerated(DomainEvent):
    """Perspective solution generated."""
    perspective_type: str = ""
    model_used: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class CandidateScored(DomainEvent):
    """Candidate solution scored."""
    candidate_id: str = ""
    scores: dict[str, float] = field(default_factory=dict)
    total_score: float = 0.0
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StressTestCompleted(DomainEvent):
    """Stress test completed for a candidate."""
    candidate_id: str = ""
    scenario: str = ""
    survival_rate: float = 0.0
    failure_mode: str = ""


# ─────────────────────────────────────────────────────────────────────
# WIDGET EVENTS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WidgetDetected(DomainEvent):
    """Widget auto-detected from query."""
    widget_type: str = ""
    trigger_pattern: str = ""
    confidence: float = 0.0


@dataclass(frozen=True)
class WidgetExecuted(DomainEvent):
    """Widget executed successfully."""
    widget_type: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class WidgetFailed(DomainEvent):
    """Widget execution failed."""
    widget_type: str = ""
    error: str = ""


# ─────────────────────────────────────────────────────────────────────
# MEMORY EVENTS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MemoryStored(DomainEvent):
    """Memory stored in Neuro system."""
    session_id: str = ""
    entry_id: int = 0
    compressed: bool = False


@dataclass(frozen=True)
class MemoryRecalled(DomainEvent):
    """Memory recalled from Neuro system."""
    query: str = ""
    chunks_found: int = 0
    latency_ms: float = 0.0


# ─────────────────────────────────────────────────────────────────────
# ERROR EVENTS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ErrorOccurred(DomainEvent):
    """Error occurred during execution."""
    error_type: str = ""
    error_message: str = ""
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetryAttempted(DomainEvent):
    """Retry attempt for failed operation."""
    operation: str = ""
    attempt: int = 0
    max_retries: int = 0
    delay_seconds: float = 0.0


# ─────────────────────────────────────────────────────────────────────
# EVENT FACTORY
# ─────────────────────────────────────────────────────────────────────

import uuid
import time


def make_event(
    event_type: _AllEventType,
    aggregate_id: str,
    version: int,
    **kwargs: Any
) -> DomainEvent:
    """
    Factory function to create domain events.
    
    Automatically sets:
    - event_id: UUID
    - timestamp: Current time
    """
    event_class = EVENT_CLASSES.get(event_type, DomainEvent)
    
    return event_class(
        event_id=str(uuid.uuid4()),
        event_type=event_type,
        timestamp=time.time(),
        aggregate_id=aggregate_id,
        version=version,
        **kwargs
    )


# Split registries for type-safe subscriptions
PIPELINE_EVENT_CLASSES: dict[PipelineEventType, type[DomainEvent]] = {
    PipelineEventType.PIPELINE_STARTED: PipelineStarted,
    PipelineEventType.PHASE_STARTED: PhaseStarted,
    PipelineEventType.PHASE_COMPLETED: PhaseCompleted,
    PipelineEventType.PHASE_FAILED: PhaseFailed,
    PipelineEventType.PIPELINE_COMPLETED: PipelineCompleted,
    PipelineEventType.PIPELINE_FAILED: PipelineFailed,
    PipelineEventType.CONTEXT_FETCHED: ContextFetched,
    PipelineEventType.CONTEXT_VETTED: ContextVetted,
    PipelineEventType.SOURCE_ADDED: SourceAdded,
    PipelineEventType.PERSPECTIVE_GENERATED: PerspectiveGenerated,
    PipelineEventType.CANDIDATE_SCORED: CandidateScored,
    PipelineEventType.STRESS_TEST_COMPLETED: StressTestCompleted,
    PipelineEventType.ERROR_OCCURRED: ErrorOccurred,
    PipelineEventType.RETRY_ATTEMPTED: RetryAttempted,
    PipelineEventType.LLM_GENERATION_COMPLETED: LLMGenerationCompleted,
}

WIDGET_EVENT_CLASSES: dict[WidgetEventType, type[DomainEvent]] = {
    WidgetEventType.WIDGET_DETECTED: WidgetDetected,
    WidgetEventType.WIDGET_EXECUTED: WidgetExecuted,
    WidgetEventType.WIDGET_FAILED: WidgetFailed,
}

MEMORY_EVENT_CLASSES: dict[MemoryEventType, type[DomainEvent]] = {
    MemoryEventType.MEMORY_STORED: MemoryStored,
    MemoryEventType.MEMORY_RECALLED: MemoryRecalled,
}

SAAS_EVENT_CLASSES: dict[SaaSEventType, type[DomainEvent]] = {
    SaaSEventType.USER_REGISTERED: DomainEvent,
    SaaSEventType.USER_LOGGED_IN: DomainEvent,
    SaaSEventType.SUBSCRIPTION_CREATED: DomainEvent,
    SaaSEventType.SUBSCRIPTION_UPDATED: DomainEvent,
    SaaSEventType.SUBSCRIPTION_CANCELLED: DomainEvent,
    SaaSEventType.QUOTA_EXCEEDED: DomainEvent,
    SaaSEventType.QUOTA_RESET: DomainEvent,
    SaaSEventType.QUERY_LOGGED: DomainEvent,
    SaaSEventType.PAYMENT_FAILED: DomainEvent,
    SaaSEventType.PAYMENT_SUCCEEDED: DomainEvent,
}

# Shorthand backward compat
EVENT_CLASSES: dict[_AllEventType, type[DomainEvent]] = {
    **PIPELINE_EVENT_CLASSES,
    **WIDGET_EVENT_CLASSES,
    **MEMORY_EVENT_CLASSES,
    **SAAS_EVENT_CLASSES,
}
