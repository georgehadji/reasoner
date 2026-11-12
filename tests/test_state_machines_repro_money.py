# ruff: noqa: E501
"""Phase 1 repro of the money rows in docs/plans/implicit-state-machines-2026-11-11.md.

They began as xfail(strict) tests asserting the CORRECT behaviour; Phase 3
fixed each row, so they are plain tests now. Live-SQL rows are in
tests/integration/test_state_machines_repro_money_pg.py.
"""

from __future__ import annotations

import logging
import time
import uuid
from types import SimpleNamespace

import pytest

from reasoner.domain.saas import LIVE_STATUSES, SubscriptionStatus

pytestmark = pytest.mark.unit


# -- M1: unknown Stripe statuses map to cancelled ---------------------------

@pytest.mark.parametrize("stripe_status", ["incomplete", "unpaid", "paused"])
def test_m1_unknown_stripe_status_is_not_silently_cancelled(stripe_status):
    from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter

    sub = StripeBillingAdapter(api_key="sk_test_x")._stripe_sub_to_domain(
        {"id": "sub_1", "customer": "cus_1", "status": stripe_status, "items": {"data": []}},
        uuid.uuid4(),
    )
    assert sub.status is not SubscriptionStatus.CANCELLED


def test_m1_past_due_is_live_so_it_keeps_the_paid_tier():
    """FALSE as a code bug: code and SQL agree past_due is live and keeps its tier.

    Only the comment at quota_service.py:63-66 ("past_due (tier -> FREE)") is stale.
    """
    assert SubscriptionStatus.PAST_DUE in LIVE_STATUSES


# -- M3: release without a landed reserve; unsettled expiry -----------------

@pytest.mark.asyncio
async def test_m3_release_without_reserve_does_not_credit_the_user():
    from reasoner.application.services.credit_service import CreditService
    from reasoner.infrastructure.persistence.credit_repo_memory import InMemoryCreditRepository

    uid = str(uuid.uuid4())
    svc = CreditService(InMemoryCreditRepository())
    # The reserve charge never landed, but the unstarted-run release still fires.
    await svc.true_up_run(uid, reserved_credits=500, cost_usd=0.0, reference_id="run1", preset="p")
    assert (await svc.get_balance(uid)).balance == 0


class _FakeZsetClient:
    def __init__(self):
        self.z: dict[str, float] = {}

    async def zadd(self, _key, mapping):
        self.z.update(mapping)

    async def zremrangebyscore(self, _key, lo, hi):
        gone = [m for m, s in self.z.items() if lo <= s <= hi]
        for m in gone:
            del self.z[m]
        return len(gone)


@pytest.mark.asyncio
async def test_m3_expired_unsettled_entry_is_not_dropped_silently(monkeypatch, caplog):
    from reasoner.core.ports.unsettled_run_port import UnsettledRun
    from reasoner.infrastructure.valkey import unsettled_runs

    fake = _FakeZsetClient()
    monkeypatch.setattr(unsettled_runs, "get_valkey_pool", lambda: fake)

    def run(ref: str, at: float) -> UnsettledRun:
        return UnsettledRun("u1", ref, 1.0, 5, "p", "boom", at)

    store = unsettled_runs.ValkeyUnsettledRunStore()
    await store.record(run("old", time.time() - 31 * 24 * 3600))
    with caplog.at_level(logging.DEBUG):
        await store.record(run("new", time.time()))
    assert any(
        r.levelno == logging.WARNING and "dropped 1 entries" in r.getMessage()
        for r in caplog.records
    )


# -- M7: account deletion ---------------------------------------------------

def _wire_delete(monkeypatch, pool, subs):
    from reasoner.api import saas_router, user_data
    from reasoner.core.settings import settings
    from reasoner.infrastructure.billing.stripe_adapter import StripeBillingAdapter
    from reasoner.infrastructure.persistence import quota_repo_postgres

    class _Repo:
        def __init__(self, *a, **k): ...

        async def _get_pool(self):
            return pool

    async def _cancel(self, sub_id):
        pool.log.append("provider_cancel")

    pool.rows = subs
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://x/y", raising=False)
    monkeypatch.setattr(quota_repo_postgres, "PostgresQuotaRepository", _Repo)
    monkeypatch.setattr(StripeBillingAdapter, "cancel_subscription", _cancel)
    monkeypatch.setattr(user_data, "user_data_stores", lambda: [])
    return saas_router, SimpleNamespace(client=None, headers={}, state=SimpleNamespace())


class _Pool:
    def __init__(self):
        self.log: list[str] = []
        self.rows: list = []
        self.table: dict[str, str] = {}
        self.detail: dict[str, str | None] = {}

    async def fetch(self, sql, *a):
        if "FROM account_deletion_log" in sql:
            return [{"status": self.table[a[0]]}] if a[0] in self.table else []
        return self.rows

    async def execute(self, sql, *a):
        # A one-table stand-in for account_deletion_log with its unique user_id.
        if "INSERT INTO account_deletion_log" in sql:
            if a[0] not in self.table:
                self.table[a[0]] = "requested"
                self.log.append("log_insert")
        elif "UPDATE account_deletion_log" in sql:
            self.table[a[0]] = a[1]
            if len(a) > 2:
                self.detail[a[0]] = a[2]


@pytest.mark.asyncio
async def test_m7_provider_cancel_runs_before_the_deletion_log(monkeypatch):
    """PARTIAL: ordering confirmed, but deliberate (a failed cancel aborts with 502 and
    leaves the account usable). Pins the current order; not a bug by itself."""
    pool = _Pool()
    router, req = _wire_delete(monkeypatch, pool, [{"stripe_sub_id": "sub_1", "paypal_sub_id": None}])
    await router.delete_account(req, SimpleNamespace(id=uuid.uuid4()), None)
    assert pool.log == ["provider_cancel", "log_insert"]


@pytest.mark.asyncio
async def test_m7_repeat_delete_writes_one_log_row(monkeypatch):
    pool = _Pool()
    router, req = _wire_delete(monkeypatch, pool, [])
    user = SimpleNamespace(id=uuid.uuid4())
    await router.delete_account(req, user, None)
    await router.delete_account(req, user, None)
    assert pool.log.count("log_insert") == 1
    assert list(pool.table.values()) == ["erased"]


@pytest.mark.asyncio
async def test_m7_partial_erase_is_recorded_and_a_repeat_delete_finishes_it(monkeypatch):
    from reasoner.api import user_data

    pool = _Pool()
    router, req = _wire_delete(monkeypatch, pool, [])
    user = SimpleNamespace(id=uuid.uuid4())

    class _Store:
        name = "uploads"

        def __init__(self, fail):
            self.fail = fail

        async def erase(self, user_id):
            if self.fail:
                raise OSError("disk gone")

    monkeypatch.setattr(user_data, "user_data_stores", lambda: [_Store(True)])
    first = await router.delete_account(req, user, None)
    assert first["failed"] == ["uploads: disk gone"]
    assert list(pool.table.values()) == ["partial"]
    assert pool.detail[str(user.id)] == "uploads"  # store names only, no error text

    monkeypatch.setattr(user_data, "user_data_stores", lambda: [_Store(False)])
    second = await router.delete_account(req, user, None)
    assert second["failed"] == [] and second["erased"] == ["uploads"]
    assert list(pool.table.values()) == ["erased"]
    assert pool.log.count("log_insert") == 1


@pytest.mark.asyncio
async def test_m7_refusal_blocks_normal_use_but_lets_the_delete_route_resume(monkeypatch):
    from fastapi import HTTPException

    from reasoner.api import dependencies as deps
    from reasoner.domain.saas import User

    class _P:
        def __init__(self, status):
            self.status = status

        async def fetchval(self, sql, uid):
            return self.status

        async def execute(self, sql, *a):
            raise AssertionError("a deleted account must not be re-provisioned")

    async def _pool_for(status):
        async def _get():
            return _P(status)
        return _get

    user = User(id=uuid.uuid4(), email="a@b.c")
    for status, resume, refused in [
        ("partial", False, True), ("partial", True, False), ("erasing", True, False),
        ("requested", True, False), ("erased", True, True), ("erased", False, True),
    ]:
        monkeypatch.setattr(deps, "_get_provision_pool", await _pool_for(status))
        deps._provisioned_user_ids.clear()
        if refused:
            with pytest.raises(HTTPException) as exc:
                await deps._ensure_user_in_db(user, resume_deletion=resume)
            assert exc.value.status_code == 403
        else:
            await deps._ensure_user_in_db(user, resume_deletion=resume)


# -- M8: upload settle not shielded from cancellation -----------------------

@pytest.mark.asyncio
async def test_m8_cancelled_upload_still_settles_its_reservation(monkeypatch):
    import anyio

    from reasoner.api.routes import uploads

    state = {"bytes": 0}

    class _Usage:
        async def reserve(self, uid, n, cap):
            state["bytes"] += n
            return True

        async def get(self, uid):
            return state["bytes"]

        async def adjust(self, uid, delta):
            await anyio.sleep(0)  # re-raises Cancelled inside a cancelled scope
            state["bytes"] += delta

    class _Request:
        headers = {"content-length": "1000"}

        async def form(self):
            await anyio.sleep_forever()

    monkeypatch.setattr(uploads, "get_upload_usage_repo", lambda: _Usage())

    async with anyio.create_task_group() as tg:

        async def _call():
            await uploads.upload_file(
                _Request(), False, SimpleNamespace(id=uuid.uuid4()), None, None
            )

        tg.start_soon(_call)
        await anyio.sleep(0.05)
        tg.cancel_scope.cancel()  # what a client disconnect does under Starlette

    assert state["bytes"] == 0
