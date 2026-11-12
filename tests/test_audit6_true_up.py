"""Audit 6, findings 1 and 4: atomic true-up and the unsettled-run record."""

from __future__ import annotations

from uuid import uuid4

import pytest

from reasoner.api import run_observability
from reasoner.api.run_observability import CreditSink
from reasoner.core.ports.unsettled_run_port import UnsettledRun
from reasoner.application.services.credit_service import CreditService
from reasoner.application.services.run_metering import RunContext, metered
from reasoner.application.services.unsettled_run_replay_service import (
    UnsettledRunReplayService,
)
from reasoner.domain.credits import (
    CreditReason,
    InsufficientCreditsError,
    LedgerWrite,
    usd_to_credits,
)
from reasoner.infrastructure.persistence.credit_repo_memory import InMemoryCreditRepository

pytestmark = pytest.mark.unit


@pytest.fixture
def user_id() -> str:
    return str(uuid4())


@pytest.fixture
def repo() -> InMemoryCreditRepository:
    return InMemoryCreditRepository()


@pytest.fixture
def service(repo) -> CreditService:
    return CreditService(repo)


async def _funded(service: CreditService, user_id: str, credits: int = 100) -> None:
    await service.grant(user_id, credits, CreditReason.SIGNUP_BONUS)


# ── record_batch ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_refused_write_rolls_back_the_whole_batch(repo, user_id):
    await repo.record(user_id, 10, CreditReason.SIGNUP_BONUS, reference_id="seed")

    with pytest.raises(InsufficientCreditsError):
        await repo.record_batch(
            user_id,
            [
                LedgerWrite(5, CreditReason.REFUND, reference_id="r:release"),
                LedgerWrite(-1000, CreditReason.PIPELINE_RUN, reference_id="r"),
            ],
        )

    assert (await repo.get_balance(user_id)).balance == 10
    assert [e.reference_id for e in await repo.list_entries(user_id)] == ["seed"]


@pytest.mark.asyncio
async def test_a_replayed_batch_moves_nothing(repo, user_id):
    writes = [
        LedgerWrite(5, CreditReason.REFUND, reference_id="r:release", allow_overdraft=True),
        LedgerWrite(-3, CreditReason.PIPELINE_RUN, reference_id="r", allow_overdraft=True),
    ]
    await repo.record_batch(user_id, writes)
    after_first = (await repo.get_balance(user_id)).balance

    await repo.record_batch(user_id, writes)

    assert (await repo.get_balance(user_id)).balance == after_first == 2
    assert len(await repo.list_entries(user_id)) == 2


# ── true_up_run ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_true_up_releases_the_hold_and_charges_the_real_cost(service, user_id):
    await _funded(service, user_id)
    await service.charge(user_id, 20, reference_id="run-1:reserve")  # the hold
    cost = usd_to_credits(0.0191)

    entries = await service.true_up_run(
        user_id, reserved_credits=20, cost_usd=0.0191, reference_id="run-1", preset="p"
    )

    assert {e.reference_id for e in entries} == {"run-1:release", "run-1"}
    assert (await service.get_balance(user_id)).balance == 100 - cost


@pytest.mark.asyncio
async def test_true_up_twice_charges_once(service, user_id):
    await _funded(service, user_id)
    await service.charge(user_id, 20, reference_id="run-1:reserve")
    args = dict(reserved_credits=20, cost_usd=0.0191, reference_id="run-1", preset="p")

    await service.true_up_run(user_id, **args)
    once = (await service.get_balance(user_id)).balance
    await service.true_up_run(user_id, **args)

    assert (await service.get_balance(user_id)).balance == once


@pytest.mark.asyncio
async def test_a_free_run_writes_only_the_refund(service, user_id):
    await _funded(service, user_id)
    await service.charge(user_id, 20, reference_id="run-2:reserve")

    entries = await service.true_up_run(
        user_id, reserved_credits=20, cost_usd=0.0, reference_id="run-2", preset="p"
    )

    assert [e.reference_id for e in entries] == ["run-2:release"]
    assert (await service.get_balance(user_id)).balance == 100


@pytest.mark.asyncio
async def test_nothing_held_nothing_owed_writes_nothing(service, user_id):
    assert await service.true_up_run(
        user_id, reserved_credits=0, cost_usd=0.0, reference_id="run-3", preset="p"
    ) == []


# ── metering -> unsettled record ────────────────────────────────────


class _Sink:
    def __init__(self):
        self.unsettled: list[dict] = []

    async def settle(self, **_kw): ...
    async def reserve(self, **_kw): return 0

    async def true_up(self, **_kw):
        await _never()

    async def record_unsettled(self, **kw):
        self.unsettled.append(kw)


async def _never():
    import anyio

    await anyio.sleep(60)


async def _frames():
    yield 'data: {"type": "done", "total_cost_usd": 0.01, "errors": []}'


@pytest.mark.asyncio
async def test_a_settle_timeout_records_the_run(monkeypatch):
    monkeypatch.setattr("reasoner.application.services.run_metering.SETTLE_TIMEOUT_SECONDS", 0.05)
    sink = _Sink()
    ctx = RunContext(preset="p", reference_id="run-9", user_id="u", tier="free", reserved_credits=20)

    async for _ in metered(_frames(), ctx, sink):
        pass

    assert [(r["reference_id"], r["reserved_credits"], r["cost_usd"]) for r in sink.unsettled] == [
        ("run-9", 20, 0.01)
    ]


# ── CreditSink.record_unsettled / fail-open counter ─────────────────


class _FakeStore:
    def __init__(self, fail: bool = False):
        self.runs: list[UnsettledRun] = []
        self.fail = fail

    async def record(self, run):
        if self.fail:
            raise ConnectionError("valkey down")
        self.runs.append(run)

    async def list_pending(self, limit):
        return list(self.runs)[:limit]

    async def remove(self, run):
        self.runs.remove(run)


def _counter_spy(monkeypatch) -> list[str]:
    paths: list[str] = []
    monkeypatch.setattr(run_observability, "count_credit_failopen", paths.append)
    return paths


@pytest.mark.asyncio
async def test_credit_sink_stores_the_unsettled_run_and_counts_it(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(run_observability, "ValkeyUnsettledRunStore", lambda: store)
    paths = _counter_spy(monkeypatch)

    await CreditSink().record_unsettled(
        user_id="u", reference_id="r", cost_usd=0.5, reserved_credits=20, preset="p", error="boom"
    )

    assert paths == ["settle"]
    assert [(r.user_id, r.reference_id, r.reserved_credits) for r in store.runs] == [("u", "r", 20)]


@pytest.mark.asyncio
async def test_credit_sink_logs_when_the_store_is_down_too(monkeypatch, caplog):
    monkeypatch.setattr(run_observability, "ValkeyUnsettledRunStore", lambda: _FakeStore(fail=True))
    _counter_spy(monkeypatch)

    with caplog.at_level("ERROR"):
        await CreditSink().record_unsettled(
            user_id="u", reference_id="r", cost_usd=0.5, reserved_credits=20, preset="p", error="boom"
        )

    assert "UNSETTLED RUN (valkey unavailable" in caplog.text
    assert "reference=r" in caplog.text


def test_failopen_counter_never_raises(monkeypatch):
    import reasoner.metrics as metrics

    class Boom:
        def labels(self, **_kw):
            raise RuntimeError("registry broken")

    monkeypatch.setattr(metrics, "REASONER_CREDIT_FAILOPEN_TOTAL", Boom())

    run_observability.count_credit_failopen("require_credits")  # must not raise


# ── replay ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_settles_then_removes_and_a_second_replay_is_a_no_op(service, user_id):
    await _funded(service, user_id)
    await service.charge(user_id, 20, reference_id="run-7:reserve")
    store = _FakeStore()
    await store.record(
        UnsettledRun(
            user_id=user_id, reference_id="run-7", cost_usd=0.0191, reserved_credits=20,
            preset="p", error="boom", recorded_at=1.0,
        )
    )
    replay = UnsettledRunReplayService(store, service)

    assert await replay.replay() == {"replayed": 1, "failed": 0}
    settled = (await service.get_balance(user_id)).balance
    assert store.runs == []

    assert await replay.replay() == {"replayed": 0, "failed": 0}
    assert (await service.get_balance(user_id)).balance == settled


@pytest.mark.asyncio
async def test_a_failing_replay_keeps_the_entry(service, user_id, monkeypatch):
    store = _FakeStore()
    run = UnsettledRun(
        user_id=user_id, reference_id="run-8", cost_usd=0.01, reserved_credits=20,
        preset="p", error="boom", recorded_at=1.0,
    )
    await store.record(run)

    async def down(*_a, **_kw):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(service, "true_up_run", down)

    assert await UnsettledRunReplayService(store, service).replay() == {"replayed": 0, "failed": 1}
    assert store.runs == [run]
