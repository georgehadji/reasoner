"""WS8-1: the lifespan must not crash when Langfuse keys are set.

`init_default_subscribers` read `_is_langfuse_enabled` off the subscriber
instance. That name is a module global, so with both LANGFUSE_* keys set the
call raised AttributeError and the production lifespan never finished.
"""

import pytest

from reasoner.application.event_bus.bus import (
    get_event_bus,
    init_default_subscribers,
    reset_event_bus,
)
from reasoner.core.events.domain_events import PipelineEventType
from reasoner.infrastructure.observability import langfuse_subscriber as ls


class _FakeLangfuse:
    def __init__(self, **_kwargs):
        pass

    def flush(self):
        pass


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    reset_event_bus()
    ls.reset_langfuse()
    monkeypatch.setattr("reasoner.application.event_bus.bus.settings.LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setattr("reasoner.application.event_bus.bus.settings.LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk")
    yield
    reset_event_bus()
    ls.reset_langfuse()


async def test_boot_with_keys_and_working_client_subscribes_handlers(monkeypatch):
    monkeypatch.setattr(ls, "_LANGFUSE_AVAILABLE", True)
    monkeypatch.setattr(ls, "_Langfuse", _FakeLangfuse)
    bus = get_event_bus()

    await init_default_subscribers(bus)

    assert bus.get_subscriber_count(PipelineEventType.PIPELINE_STARTED) >= 1


async def test_boot_with_keys_and_missing_sdk_does_not_raise(monkeypatch):
    monkeypatch.setattr(ls, "_LANGFUSE_AVAILABLE", False)
    bus = get_event_bus()

    await init_default_subscribers(bus)

    assert bus.total_subscribers > 0


async def test_failing_optional_subscriber_is_skipped_not_fatal(monkeypatch):
    async def boom():
        raise RuntimeError("langfuse exploded")

    monkeypatch.setattr("reasoner.application.event_bus.bus.get_langfuse_subscriber", boom)
    bus = get_event_bus()

    await init_default_subscribers(bus)

    assert bus.total_subscribers > 0
