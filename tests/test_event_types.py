"""Tests for EventType split into sub-enums."""

from __future__ import annotations

import pytest

from reasoner.application.event_bus.bus import EventBus, reset_event_bus
from reasoner.core.events.domain_events import (
    ALL_EVENT_TYPES,
    EVENT_CLASSES,
    MEMORY_EVENT_CLASSES,
    PIPELINE_EVENT_CLASSES,
    SAAS_EVENT_CLASSES,
    WIDGET_EVENT_CLASSES,
    EventType,
    MemoryEventType,
    PipelineEventType,
    SaaSEventType,
    WidgetEventType,
    make_event,
)


@pytest.fixture(autouse=True)
def reset_bus():
    reset_event_bus()
    yield
    reset_event_bus()


def test_old_event_type_import_still_works() -> None:
    """from ...domain_events import EventType still resolves."""
    assert EventType.PIPELINE_STARTED == "pipeline_started"
    assert EventType.PHASE_COMPLETED == "phase_completed"


def test_backward_compat_value_comparison() -> None:
    """EventType.PIPELINE_STARTED.value still correct."""
    assert EventType.PIPELINE_STARTED.value == "pipeline_started"
    assert EventType.ERROR_OCCURRED.value == "error_occurred"


def test_event_classes_populated() -> None:
    """All 4 registries have correct entries."""
    assert len(PIPELINE_EVENT_CLASSES) == 23
    assert len(WIDGET_EVENT_CLASSES) == 3
    assert len(MEMORY_EVENT_CLASSES) == 2
    assert len(SAAS_EVENT_CLASSES) == 12
    assert len(EVENT_CLASSES) == 40


def test_make_event_with_sub_type() -> None:
    """Creates correct DomainEvent subclass."""
    event = make_event(
        PipelineEventType.PIPELINE_STARTED,
        aggregate_id="agg-1",
        version=1,
        problem="test",
    )
    assert event.event_type == PipelineEventType.PIPELINE_STARTED
    assert event.aggregate_id == "agg-1"


def test_make_event_with_widget_type() -> None:
    """make_event works with WidgetEventType."""
    event = make_event(
        WidgetEventType.WIDGET_DETECTED,
        aggregate_id="agg-1",
        version=1,
        widget_type="calculator",
    )
    assert event.event_type == WidgetEventType.WIDGET_DETECTED


def test_make_event_with_saas_type() -> None:
    """make_event works with SaaSEventType."""
    event = make_event(
        SaaSEventType.QUOTA_EXCEEDED,
        aggregate_id="user-1",
        version=1,
    )
    assert event.event_type == SaaSEventType.QUOTA_EXCEEDED


@pytest.mark.asyncio
async def test_pipeline_only_subscription() -> None:
    """Widget event not dispatched to pipeline handler."""
    bus = EventBus()
    pipeline_events = []
    widget_events = []

    async def on_pipeline(event):
        pipeline_events.append(event.event_type.value)

    async def on_widget(event):
        widget_events.append(event.event_type.value)

    bus.subscribe(PipelineEventType.PHASE_STARTED, on_pipeline)
    bus.subscribe(WidgetEventType.WIDGET_DETECTED, on_widget)

    await bus.publish(make_event(PipelineEventType.PHASE_STARTED, "a", 1))
    await bus.publish(make_event(WidgetEventType.WIDGET_DETECTED, "a", 1))

    assert pipeline_events == ["phase_started"]
    assert widget_events == ["widget_detected"]


@pytest.mark.asyncio
async def test_saas_only_subscription() -> None:
    """Pipeline event not dispatched to SaaS handler."""
    bus = EventBus()
    saas_events = []

    async def on_saas(event):
        saas_events.append(event.event_type.value)

    bus.subscribe(SaaSEventType.QUOTA_EXCEEDED, on_saas)

    await bus.publish(make_event(PipelineEventType.PHASE_STARTED, "a", 1))
    await bus.publish(make_event(SaaSEventType.QUOTA_EXCEEDED, "a", 1))

    assert saas_events == ["quota_exceeded"]


def test_all_event_types_map() -> None:
    """ALL_EVENT_TYPES contains all enum values."""
    assert len(ALL_EVENT_TYPES) == 40
    assert ALL_EVENT_TYPES["pipeline_started"] == PipelineEventType.PIPELINE_STARTED
    assert ALL_EVENT_TYPES["widget_detected"] == WidgetEventType.WIDGET_DETECTED
    assert ALL_EVENT_TYPES["memory_stored"] == MemoryEventType.MEMORY_STORED
    assert ALL_EVENT_TYPES["quota_exceeded"] == SaaSEventType.QUOTA_EXCEEDED
