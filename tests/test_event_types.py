"""Tests for EventType split into sub-enums."""

from __future__ import annotations

import pytest

from reasoner.core.events.domain_events import (
    PipelineEventType,
    WidgetEventType,
    MemoryEventType,
    SaaSEventType,
    EventType,
    ALL_EVENT_TYPES,
    PIPELINE_EVENT_CLASSES,
    WIDGET_EVENT_CLASSES,
    MEMORY_EVENT_CLASSES,
    SAAS_EVENT_CLASSES,
    EVENT_CLASSES,
    make_event,
    DomainEvent,
)
from reasoner.application.event_bus.bus import EventBus, get_event_bus, reset_event_bus


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
    """Every declared event type has a class, and the registries partition cleanly.

    Asserted structurally rather than as fixed counts, which went stale on every
    new event type without indicating anything was actually wrong.
    """
    for enum_cls, registry in (
        (PipelineEventType, PIPELINE_EVENT_CLASSES),
        (WidgetEventType, WIDGET_EVENT_CLASSES),
        (MemoryEventType, MEMORY_EVENT_CLASSES),
        (SaaSEventType, SAAS_EVENT_CLASSES),
    ):
        missing = [e for e in enum_cls if e not in registry]
        assert not missing, f"{enum_cls.__name__} entries without a class: {missing}"

    combined = (
        len(PIPELINE_EVENT_CLASSES)
        + len(WIDGET_EVENT_CLASSES)
        + len(MEMORY_EVENT_CLASSES)
        + len(SAAS_EVENT_CLASSES)
    )
    assert len(EVENT_CLASSES) == combined


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
    expected = {
        e.value
        for enum_cls in (PipelineEventType, WidgetEventType, MemoryEventType, SaaSEventType)
        for e in enum_cls
    }
    assert set(ALL_EVENT_TYPES) == expected
    assert ALL_EVENT_TYPES["pipeline_started"] == PipelineEventType.PIPELINE_STARTED
    assert ALL_EVENT_TYPES["widget_detected"] == WidgetEventType.WIDGET_DETECTED
    assert ALL_EVENT_TYPES["memory_stored"] == MemoryEventType.MEMORY_STORED
    assert ALL_EVENT_TYPES["quota_exceeded"] == SaaSEventType.QUOTA_EXCEEDED
