"""UserDataEraser must not report GDPR erasure as "completed" when Neuro
long-term memory was not actually erased (data_eraser.py step 3).

Before the fix, step 3 was a no-op ("best-effort cache clear" that cleared
nothing), so `status` could be "completed" while a user's verbatim Neuro
memory survived. These tests exercise UserDataEraser.erase() in isolation via
the injectable erase_neuro_fn, independent of the real NeuroService (covered
end to end by tests/test_neuro_owner_erasure.py).
"""

from __future__ import annotations

import pytest

from reasoner.application.services.data_eraser import UserDataEraser


class _FakeEventStore:
    def __init__(self, aggregate_ids: list[str]) -> None:
        self._aggregate_ids = aggregate_ids
        self.deleted: list[str] = []

    async def list_aggregate_ids_for_user(self, user_id: str) -> list[str]:
        return list(self._aggregate_ids)

    async def delete_aggregate(self, aggregate_id: str) -> None:
        self.deleted.append(aggregate_id)


@pytest.mark.asyncio
async def test_receipt_reports_completed_only_when_neuro_erasure_succeeds():
    async def erase_neuro_ok(user_id: str) -> dict:
        return {"erased": True, "dirs_removed": 2, "tenants_evicted": 1, "error": None}

    eraser = UserDataEraser(_FakeEventStore(["p1", "p2"]), erase_neuro_fn=erase_neuro_ok)
    receipt = await eraser.erase("user-x")

    assert receipt["status"] == "completed"
    assert receipt["neuro_memory_erased"] is True
    assert "neuro_error" not in receipt


@pytest.mark.asyncio
async def test_receipt_is_not_completed_when_neuro_erasure_fails():
    """A failing Neuro deletion must not be reported as a completed erasure,
    even though the event store deleted everything it owns."""

    async def erase_neuro_fails(user_id: str) -> dict:
        return {"erased": False, "dirs_removed": 0, "tenants_evicted": 0, "error": "disk full"}

    eraser = UserDataEraser(_FakeEventStore(["p1"]), erase_neuro_fn=erase_neuro_fails)
    receipt = await eraser.erase("user-x")

    assert receipt["status"] != "completed"
    assert receipt["neuro_memory_erased"] is False
    assert receipt["neuro_error"] == "disk full"


@pytest.mark.asyncio
async def test_receipt_is_not_completed_when_neuro_erasure_raises():
    """A raising neuro erasure call must degrade to "not completed", not be
    swallowed into an apparent success."""

    async def erase_neuro_raises(user_id: str) -> dict:
        raise RuntimeError("neuro service unreachable")

    eraser = UserDataEraser(_FakeEventStore(["p1"]), erase_neuro_fn=erase_neuro_raises)
    receipt = await eraser.erase("user-x")

    assert receipt["status"] != "completed"
    assert receipt["neuro_memory_erased"] is False
    assert "neuro service unreachable" in receipt["neuro_error"]


@pytest.mark.asyncio
async def test_aggregates_failure_still_takes_priority_over_neuro_status():
    """Existing contract: a failed event-store deletion always reports "failed"."""

    class _FailingEventStore(_FakeEventStore):
        async def list_aggregate_ids_for_user(self, user_id: str) -> list[str]:
            raise RuntimeError("db is on fire")

    async def erase_neuro_ok(user_id: str) -> dict:
        return {"erased": True, "dirs_removed": 0, "tenants_evicted": 0, "error": None}

    eraser = UserDataEraser(_FailingEventStore([]), erase_neuro_fn=erase_neuro_ok)
    receipt = await eraser.erase("user-x")

    assert receipt["status"] == "failed"


@pytest.mark.asyncio
async def test_default_neuro_erase_goes_through_the_injected_memory_port(monkeypatch):
    """Without an injected erase_neuro_fn, production wiring must call
    erase_owner on the registered MemoryPort, not silently no-op and not build
    a second NeuroService."""
    import reasoner.core.ports.memory_port as mp

    calls: list[str] = []

    class _FakePort:
        async def erase_owner(self, owner: str) -> dict:
            calls.append(owner)
            return {"erased": True, "dirs_removed": 0, "tenants_evicted": 0, "error": None}

    monkeypatch.setattr(mp, "_MEMORY_PORT", _FakePort())

    eraser = UserDataEraser(_FakeEventStore([]))
    receipt = await eraser.erase("user-z")

    assert calls == ["user-z"]
    assert receipt["neuro_memory_erased"] is True


@pytest.mark.asyncio
async def test_no_memory_port_reports_partial_not_completed(monkeypatch):
    """Neuro failed to start: the eraser must say it could not erase or verify
    long-term memory rather than report success (or construct its own service)."""
    import reasoner.core.ports.memory_port as mp

    monkeypatch.setattr(mp, "_MEMORY_PORT", None)

    receipt = await UserDataEraser(_FakeEventStore(["p1"])).erase("user-z")

    assert receipt["status"] == "partial"
    assert receipt["neuro_memory_erased"] is False
    assert "memory port is not registered" in receipt["neuro_error"]
