"""GDPR erasure must not be reported "completed" when Neuro long-term memory
was not actually erased.

Before the fix, the Neuro step was a no-op ("best-effort cache clear" that
cleared nothing), so `status` could be "completed" while a user's verbatim
Neuro memory survived. Since DAT-11 the Neuro step is the `neuro` store in the
user-data registry; these tests drive `UserDataEraser` over `NeuroStore` and
`EventsStore` with a fake memory port, independent of the real NeuroService
(covered end to end by tests/test_neuro_owner_erasure.py).
"""

from __future__ import annotations

import pytest

from reasoner.application.services.data_eraser import UserDataEraser
from reasoner.infrastructure.persistence.user_data_local import EventsStore, NeuroStore


class _FakeEventStore:
    def __init__(self, aggregate_ids: list[str]) -> None:
        self._aggregate_ids = aggregate_ids
        self.deleted: list[str] = []

    async def list_aggregate_ids_for_user(self, user_id: str) -> list[str]:
        return list(self._aggregate_ids)

    async def delete_aggregate(self, aggregate_id: str) -> None:
        self.deleted.append(aggregate_id)


class _Port:
    def __init__(self, result: dict | Exception) -> None:
        self._result = result
        self.calls: list[str] = []

    async def erase_owner(self, owner: str) -> dict:
        self.calls.append(owner)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _eraser(events: _FakeEventStore, port: _Port | None) -> UserDataEraser:
    return UserDataEraser([EventsStore(lambda: events), NeuroStore(lambda: port)])


@pytest.mark.asyncio
async def test_receipt_reports_completed_only_when_neuro_erasure_succeeds():
    port = _Port({"erased": True, "dirs_removed": 2, "tenants_evicted": 1, "error": None})

    receipt = await _eraser(_FakeEventStore(["p1", "p2"]), port).erase("user-x")

    assert receipt["status"] == "completed"
    assert receipt["erased"] == ["events", "neuro"]
    assert receipt["failed"] == []


@pytest.mark.asyncio
async def test_receipt_is_not_completed_when_neuro_erasure_fails():
    """A failing Neuro deletion must not be reported as a completed erasure,
    even though the event store deleted everything it owns."""
    port = _Port({"erased": False, "dirs_removed": 0, "tenants_evicted": 0, "error": "disk full"})

    receipt = await _eraser(_FakeEventStore(["p1"]), port).erase("user-x")

    assert receipt["status"] != "completed"
    assert receipt["erased"] == ["events"]
    assert receipt["failed"] == [{"store": "neuro", "error": "disk full"}]


@pytest.mark.asyncio
async def test_receipt_is_not_completed_when_neuro_erasure_raises():
    """A raising neuro erasure call must degrade to "not completed", not be
    swallowed into an apparent success."""
    port = _Port(RuntimeError("neuro service unreachable"))

    receipt = await _eraser(_FakeEventStore(["p1"]), port).erase("user-x")

    assert receipt["status"] != "completed"
    assert "neuro service unreachable" in receipt["failed"][0]["error"]


@pytest.mark.asyncio
async def test_an_event_store_failure_does_not_stop_neuro_erasure():
    """The old eraser reported "failed" for the event store; the registry
    reports it and still erases Neuro, so one failure never strands the rest."""

    class _FailingEventStore(_FakeEventStore):
        async def list_aggregate_ids_for_user(self, user_id: str) -> list[str]:
            raise RuntimeError("db is on fire")

    port = _Port({"erased": True})

    receipt = await _eraser(_FailingEventStore([]), port).erase("user-x")

    assert receipt["status"] == "partial"
    assert receipt["failed"][0]["store"] == "events"
    assert port.calls == ["user-x"]


@pytest.mark.asyncio
async def test_default_neuro_erase_goes_through_the_injected_memory_port(monkeypatch):
    """Production wiring calls erase_owner on the registered MemoryPort, not a
    second NeuroService."""
    import reasoner.core.ports.memory_port as mp
    from reasoner.core.ports.memory_port import get_memory_port

    port = _Port({"erased": True})
    monkeypatch.setattr(mp, "_MEMORY_PORT", port)

    receipt = await UserDataEraser([NeuroStore(get_memory_port)]).erase("user-z")

    assert port.calls == ["user-z"]
    assert receipt["status"] == "completed"


@pytest.mark.asyncio
async def test_no_memory_port_reports_partial_not_completed(monkeypatch):
    """Neuro failed to start: the eraser must say it could not erase or verify
    long-term memory rather than report success."""
    import reasoner.core.ports.memory_port as mp
    from reasoner.core.ports.memory_port import get_memory_port

    monkeypatch.setattr(mp, "_MEMORY_PORT", None)

    receipt = await UserDataEraser([NeuroStore(get_memory_port)]).erase("user-z")

    assert receipt["status"] == "partial"
    assert "memory port is not registered" in receipt["failed"][0]["error"]
