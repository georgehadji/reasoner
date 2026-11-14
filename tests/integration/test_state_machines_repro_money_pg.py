# ruff: noqa: E501
"""Phase 1 live-Postgres repro of the money rows (docs/plans/implicit-state-machines-2026-11-11.md).

They began as xfail(strict) tests asserting the CORRECT behaviour; Phase 3
fixed each row, so they are plain tests now.
"""

from __future__ import annotations

import contextlib
from dataclasses import replace
from types import SimpleNamespace

import pytest

from reasoner.domain.saas import SubscriptionStatus
from reasoner.infrastructure.billing import webhooks
from reasoner.infrastructure.persistence.pg_pool import close_shared_pools
from tests.integration.test_alembic_schema_contract import (
    DSN,
    _alembic_upgrade,
    _fresh_database,
)
from tests.integration.test_audit2_billing_pg import T1, T2, _sub, _subscription_repo, _user

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not DSN, reason="REASONER_TEST_PG_DSN not set"),
]


@contextlib.asynccontextmanager
async def _webhook_pool():
    import asyncpg

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        pg = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        previous, webhooks._webhook_pool = webhooks._webhook_pool, pg
        try:
            yield pg
        finally:
            webhooks._webhook_pool = previous
            await pg.close()


# -- M1 ---------------------------------------------------------------------

async def test_m1_same_second_update_does_not_revive_a_cancelled_subscription():
    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        repo = _subscription_repo(dsn)
        try:
            await repo.upsert_subscription(_sub(uid, "sub_1"), T1)
            await repo.set_subscription_status("sub_1", "cancelled", T2)  # deleted
            await repo.upsert_subscription(_sub(uid, "sub_1"), T2)  # updated, same second
            current = await repo.get_subscription_by_user(uid)
        finally:
            await close_shared_pools()
    assert current.status is SubscriptionStatus.CANCELLED


async def test_m1_stripe_upsert_does_not_adopt_a_paypal_tombstone():
    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        repo = _subscription_repo(dsn)
        tomb = replace(
            _sub(uid, "x", SubscriptionStatus.CANCELLED),
            stripe_subscription_id=None, paypal_subscription_id="I-1",
        )
        try:
            await repo.record_paypal_cancel_tombstone(tomb, T1)
            await repo.upsert_subscription(_sub(uid, "sub_new"), T2)
            import asyncpg

            conn = await asyncpg.connect(dsn)
            try:
                status = await conn.fetchval(
                    "SELECT status FROM subscriptions WHERE paypal_sub_id = 'I-1'"
                )
            finally:
                await conn.close()
        finally:
            await close_shared_pools()
    assert status == "cancelled"  # the tombstone must keep guarding the PayPal id


# -- M2 ---------------------------------------------------------------------

async def test_m2_stale_worker_release_cannot_delete_a_done_row():
    async with _webhook_pool() as pool:
        assert await webhooks._db_claim_webhook("evt_1", "stripe") is True  # worker A
        await pool.execute(
            "UPDATE processed_webhooks SET claimed_at = now() - interval '1 day' "
            "WHERE event_id = 'evt_1'"
        )
        assert await webhooks._db_claim_webhook("evt_1", "stripe") is True  # worker B takes over
        await webhooks._db_complete_webhook("evt_1", "stripe")  # B finishes: done
        await webhooks._db_release_webhook("evt_1", "stripe")  # A fails late and releases
        # The event was applied once and is done; a retry must not be claimable.
        assert await webhooks._db_claim_webhook("evt_1", "stripe") is False


async def test_m2_dead_letter_not_marked_replayed_when_nothing_ran():
    marked: list[str] = []

    class _Repo:
        async def list_failures(self, unreplayed_only=True, limit=50):
            return [SimpleNamespace(id="f1", provider="stripe", payload={"id": "evt_1"})]

        async def mark_replayed(self, failure_id):
            marked.append(failure_id)
            return True

    async def _repo():
        return _Repo()

    async with _webhook_pool():
        original, webhooks._get_dead_letter_repo = webhooks._get_dead_letter_repo, _repo
        try:
            # Another worker holds a live 'processing' lease: nothing has been applied yet.
            assert await webhooks._db_claim_webhook("evt_1", "stripe") is True
            await webhooks.replay_failed_webhooks()
        finally:
            webhooks._get_dead_letter_repo = original
    assert marked == []


# -- M7 ---------------------------------------------------------------------

async def _log_columns(dsn: str) -> set[str]:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'account_deletion_log'"
        )
    finally:
        await conn.close()
    return {r["column_name"] for r in rows}


async def test_m7_deletion_log_records_erase_status():
    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        assert "status" in await _log_columns(dsn)


async def test_m7_deletion_log_is_unique_per_user():
    import asyncpg

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        uid = await _user(dsn)
        conn = await asyncpg.connect(dsn)
        try:
            ins = "INSERT INTO account_deletion_log (user_id) VALUES ($1)"
            await conn.execute(ins, uid)
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute(ins, uid)
        finally:
            await conn.close()
