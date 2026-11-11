"""Defect hunt over the audit 6 round 2 money path: proofs for D1 and D2.

D1: an account erasure left the account's ``unsettled_runs`` entries (user id, cost,
    preset) in Valkey until the 30-day trim, because the registry's Valkey store only
    deletes ``user:<id>:*`` keys.
D2: a run that cost nothing and whose true-up timed out kept its quota slot, because the
    timeout branch recorded the run but never gave the slot back.
"""

from __future__ import annotations

import json
import time

import anyio
import pytest

from reasoner.application.services.run_metering import RunContext, metered
from reasoner.core.ports.unsettled_run_port import UnsettledRun
from reasoner.infrastructure.valkey import unsettled_runs as store_module
from reasoner.infrastructure.valkey.unsettled_runs import ValkeyUnsettledRunStore

pytestmark = pytest.mark.unit


class _FakeZset:
    """The sorted-set and key commands the stores use, in memory."""

    def __init__(self) -> None:
        self.z: dict[str, float] = {}

    async def zadd(self, key, mapping):
        self.z.update(mapping)

    async def zrange(self, key, start, stop):
        ordered = [m for m, _ in sorted(self.z.items(), key=lambda kv: kv[1])]
        return ordered[start:] if stop == -1 else ordered[start : stop + 1]

    async def zrem(self, key, member):
        self.z.pop(member, None)

    async def zremrangebyscore(self, key, lo, hi):
        for m in [m for m, s in self.z.items() if lo <= s <= hi]:
            del self.z[m]


def _run(user: str, ref: str) -> UnsettledRun:
    return UnsettledRun(
        user_id=user, reference_id=ref, cost_usd=0.01, reserved_credits=5,
        preset="p", error="boom", recorded_at=time.time(),
    )


# ── D1: erasure reaches the unsettled-run set ────────────────────────


@pytest.fixture
def valkey(monkeypatch) -> _FakeZset:
    fake = _FakeZset()
    monkeypatch.setattr(store_module, "get_valkey_pool", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_erasing_a_user_removes_their_unsettled_runs_only(valkey):
    from reasoner.infrastructure.persistence.user_data_local import UnsettledRunsStore

    store = ValkeyUnsettledRunStore()
    await store.record(_run("u-gone", "r1"))
    await store.record(_run("u-gone", "r2"))
    await store.record(_run("u-stays", "r3"))

    await UnsettledRunsStore().erase("u-gone")

    assert [r.reference_id for r in await store.list_pending(10)] == ["r3"]


@pytest.mark.asyncio
async def test_erasing_a_user_with_no_unsettled_runs_is_a_no_op(valkey):
    from reasoner.infrastructure.persistence.user_data_local import UnsettledRunsStore

    await UnsettledRunsStore().erase("nobody")

    assert valkey.z == {}


def test_the_registry_lists_the_unsettled_run_store():
    from reasoner.api.user_data import user_data_stores

    assert "unsettled_runs" in [s.name for s in user_data_stores()]


@pytest.mark.asyncio
async def test_a_member_is_the_json_the_store_wrote(valkey):
    """Guards the erase scan: it matches on the ``user_id`` field of that JSON."""
    await ValkeyUnsettledRunStore().record(_run("u1", "r1"))

    (member,) = valkey.z
    assert json.loads(member)["user_id"] == "u1"


# ── D2: a timed-out zero-cost run gives its slot back ────────────────


class _HangingSink:
    def __init__(self) -> None:
        self.released: list[str] = []

    async def settle(self, **_kw): ...
    async def reserve(self, **_kw): return 0

    async def true_up(self, **_kw):
        await anyio.sleep(60)

    async def record_unsettled(self, **_kw): ...

    async def release_quota_slot(self, *, user_id: str) -> None:
        self.released.append(user_id)


async def _no_cost_frames():
    yield 'data: {"type": "phase_start"}'


async def _paid_frames():
    yield 'data: {"type": "done", "total_cost_usd": 0.02, "errors": []}'


def _ctx() -> RunContext:
    return RunContext(
        preset="p", reference_id="r", user_id="u1", reserved_credits=5, quota_slot=True
    )


@pytest.mark.asyncio
async def test_a_zero_cost_run_whose_true_up_times_out_gives_its_slot_back(monkeypatch):
    monkeypatch.setattr("reasoner.application.services.run_metering.SETTLE_TIMEOUT_SECONDS", 0.05)
    sink = _HangingSink()

    async for _ in metered(_no_cost_frames(), _ctx(), sink):
        pass

    assert sink.released == ["u1"]


@pytest.mark.asyncio
async def test_a_billed_run_whose_true_up_times_out_keeps_its_slot(monkeypatch):
    monkeypatch.setattr("reasoner.application.services.run_metering.SETTLE_TIMEOUT_SECONDS", 0.05)
    sink = _HangingSink()

    async for _ in metered(_paid_frames(), _ctx(), sink):
        pass

    assert sink.released == []
