"""Audit 9 billing findings 1-8, one test each (SQL ones also run live in
tests/integration/test_audit9_billing_pg.py)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from reasoner.application.services import billing_service
from reasoner.application.services.billing_service import BillingService, _paypal_cancel
from reasoner.domain.credits import usd_to_credits
from reasoner.domain.saas import Subscription, SubscriptionStatus, SubscriptionTier
from reasoner.infrastructure.llm import spend_tracker
from reasoner.infrastructure.persistence.subscription_repo import PostgresSubscriptionRepository

pytestmark = pytest.mark.unit


def _sub(**kw) -> Subscription:
    base = dict(
        id=uuid4(), user_id=uuid4(), tier=SubscriptionTier.PRO,
        status=SubscriptionStatus.CANCELLED, paypal_subscription_id="I-1",
    )
    base.update(kw)
    return Subscription(**base)


class _Pool:
    """Records SQL; acquire() yields a connection recording the same."""

    def __init__(self, fetchrow=None, fetchval=None):
        self.sql: list[str] = []
        self._fetchrow, self._fetchval = fetchrow, fetchval
        pool = self

        class _Conn:
            async def fetchrow(self, q, *a):
                pool.sql.append(q)
                return pool._fetchrow

            async def execute(self, q, *a):
                pool.sql.append(q)

            def transaction(self):
                @asynccontextmanager
                async def cm():
                    yield

                return cm()

        self._conn = _Conn()

    async def fetchval(self, q, *a):
        self.sql.append(q)
        return self._fetchval

    async def fetchrow(self, q, *a):
        self.sql.append(q)
        return self._fetchrow

    async def execute(self, q, *a):
        self.sql.append(q)
        return "UPDATE 1"

    def acquire(self, timeout=None):
        @asynccontextmanager
        async def cm():
            yield self._conn

        return cm()


def _repo(pool) -> PostgresSubscriptionRepository:
    repo = PostgresSubscriptionRepository.__new__(PostgresSubscriptionRepository)
    repo._get_pool = AsyncMock(return_value=pool)
    return repo


# 1 ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unmatched_paypal_cancel_records_tombstone():
    repo = MagicMock()
    repo.set_subscription_status_by_paypal = AsyncMock(return_value=False)
    repo.record_paypal_cancel_tombstone = AsyncMock()
    at = datetime(2026, 11, 1, tzinfo=UTC)
    await _paypal_cancel(_sub(), repo, at)
    repo.record_paypal_cancel_tombstone.assert_awaited_once()
    assert repo.record_paypal_cancel_tombstone.await_args.args[1] == at


# 2 ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reset_monthly_is_conditional_and_utc_month_start():
    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository

    pool = _Pool()
    repo = PostgresQuotaRepository.__new__(PostgresQuotaRepository)
    repo._get_pool = AsyncMock(return_value=pool)
    pool.execute = AsyncMock()
    await repo.reset_monthly("u")
    sql = pool.execute.await_args.args[0]
    assert "period_start IS NULL OR" in sql and "period_start <" in sql
    assert sql.count("AT TIME ZONE 'UTC' AT TIME ZONE 'UTC'") == 0
    assert "date_trunc('month', NOW() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'" in sql


# 3 ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_subscription_prefers_live_over_newer_dead_row():
    pool = _Pool(fetchrow=None)
    await _repo(pool).get_subscription_by_user("u")
    assert "(status IN ('active', 'trialing', 'past_due')) DESC, created_at DESC" in pool.sql[0]


# 4 ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stripe_checkout_check_and_write_run_under_user_lock():
    events: list[str] = []

    class Repo:
        @asynccontextmanager
        async def user_lock(self, uid):
            events.append("lock")
            yield
            events.append("unlock")

        async def get_subscription_by_user(self, uid):
            events.append("check")

        async def upsert_subscription(self, sub, at):
            events.append("upsert")
            return False

    sub = _sub(stripe_subscription_id="sub_1", paypal_subscription_id=None)
    await BillingService(port=None)._apply_webhook("checkout.session.completed", sub, Repo())
    assert events == ["lock", "check", "upsert", "unlock"]


# 5 ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_record_shared_uses_valkey_counter_and_falls_back(monkeypatch):
    from reasoner.infrastructure.valkey import client as vclient

    spend_tracker.reset()

    class Fake:
        def __init__(self):
            self.n = 0.0
            self.expired = None

        async def incrbyfloat(self, key, amt):
            self.key = key
            self.n += amt
            return self.n

        async def expire(self, key, s):
            self.expired = s

    fake = Fake()
    monkeypatch.setattr(vclient, "_pool", fake)
    assert await spend_tracker.record_shared("u9", 1.0) == pytest.approx(1.0)
    assert await spend_tracker.record_shared("u9", 0.5) == pytest.approx(1.5)
    assert fake.key == f"spend:u9:{spend_tracker.current_period()}"
    assert fake.expired == 40 * 86400
    assert spend_tracker.get("u9") == pytest.approx(1.5)

    class Broken:
        async def incrbyfloat(self, *a):
            raise ConnectionError("down")

    monkeypatch.setattr(vclient, "_pool", Broken())
    spend_tracker.reset()
    assert await spend_tracker.record_shared("u10", 2.0) == pytest.approx(2.0)
    spend_tracker.reset()


# 6 ---------------------------------------------------------------------------
def test_usd_to_credits_ignores_float_noise():
    assert usd_to_credits(2.007) == 2007
    assert usd_to_credits(0.0000001) == 1


# 7 ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_webhook_invalidates_quota_cache(monkeypatch):
    from reasoner.infrastructure.persistence import cached_quota_repo, cached_subscription_repo

    inv = AsyncMock()
    monkeypatch.setattr(cached_quota_repo, "invalidate_quota", inv)
    guarded = MagicMock()
    guarded.delete = AsyncMock()
    monkeypatch.setattr(cached_subscription_repo, "get_guarded_valkey", lambda c: guarded)
    monkeypatch.setattr(billing_service.BillingService, "_apply_webhook", AsyncMock())
    sub = _sub()
    port = MagicMock()
    port.sync_subscription = AsyncMock(return_value=sub)
    await BillingService(port).handle_webhook({"event_type": "x"})
    inv.assert_awaited_once_with(str(sub.user_id))


@pytest.mark.asyncio
async def test_invalidate_quota_deletes_key(monkeypatch):
    from reasoner.infrastructure.persistence import cached_quota_repo as m

    guarded = MagicMock()
    guarded.delete = AsyncMock()
    monkeypatch.setattr(m, "get_guarded_valkey", lambda c: guarded)
    await m.invalidate_quota("u1")
    guarded.delete.assert_awaited_once_with("quota:u1")


# 8 ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tier_change_keeps_used_queries():
    pool = _Pool(fetchval="free", fetchrow={"tier": "pro", "used_queries": 7})
    await _repo(pool).sync_quota_for_subscription(_sub())
    updates = [q for q in pool.sql if q.lstrip().startswith("UPDATE usage_quotas")]
    assert updates and not any("used_queries = 0" in q for q in updates)


async def test_refresh_pulls_other_workers_spend_into_gate(monkeypatch):
    """The sync admission gate must see spend another worker recorded in Valkey."""
    from reasoner.infrastructure.valkey import client as vclient

    spend_tracker.reset()

    class Fake:
        async def get(self, key):
            return "3.25" if key == f"spend:u10:{spend_tracker.current_period()}" else None

    monkeypatch.setattr(vclient, "_pool", Fake())
    assert spend_tracker.get("u10") == 0.0
    assert await spend_tracker.refresh("u10") == pytest.approx(3.25)
    assert spend_tracker.get("u10") == pytest.approx(3.25)
