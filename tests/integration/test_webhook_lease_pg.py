"""BIL-21 on a real Postgres: the webhook claim is a lease, not a permanent lock.

A worker that died after claiming an event left the claim behind, so the
provider's retry was dropped as a duplicate and the event was lost.
"""

from __future__ import annotations

import contextlib

import pytest

from reasoner.infrastructure.billing import webhooks
from tests.integration.test_alembic_schema_contract import (
    DSN,
    _alembic_upgrade,
    _fresh_database,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not DSN, reason="REASONER_TEST_PG_DSN not set"),
]


@contextlib.asynccontextmanager
async def _pool():
    """A migrated throwaway database, wired in as the receiver's pool. Built
    inside each test: a fixture's pool would belong to another event loop."""
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


async def _backdate(pool, event_id: str, seconds: int) -> None:
    await pool.execute(
        "UPDATE processed_webhooks SET claimed_at = now() - make_interval(secs => $2) "
        "WHERE event_id = $1",
        event_id, float(seconds),
    )


async def test_the_first_claim_wins_and_a_retry_inside_the_lease_is_a_duplicate():
    async with _pool():
        assert await webhooks._db_claim_webhook("evt_1", "stripe") is True
        assert await webhooks._db_claim_webhook("evt_1", "stripe") is False


async def test_a_crashed_claim_is_reclaimed_after_the_lease():
    async with _pool() as pool:
        assert await webhooks._db_claim_webhook("evt_1", "stripe") is True
        # The worker died here: no complete, no release.
        await _backdate(pool, "evt_1", webhooks.WEBHOOK_LEASE_SECONDS + 5)

        assert await webhooks._db_claim_webhook("evt_1", "stripe") is True
        assert await webhooks._db_claim_webhook("evt_1", "stripe") is False, "the new lease holds"


async def test_a_finished_event_is_never_reclaimed():
    async with _pool() as pool:
        assert await webhooks._db_claim_webhook("evt_1", "stripe") is True
        await webhooks._db_complete_webhook("evt_1", "stripe")
        await _backdate(pool, "evt_1", 10 * webhooks.WEBHOOK_LEASE_SECONDS)

        assert await webhooks._db_claim_webhook("evt_1", "stripe") is False


async def test_a_released_event_can_be_claimed_at_once():
    async with _pool():
        assert await webhooks._db_claim_webhook("evt_1", "paypal") is True
        await webhooks._db_release_webhook("evt_1", "paypal")

        assert await webhooks._db_claim_webhook("evt_1", "paypal") is True


async def test_providers_do_not_share_event_ids():
    async with _pool():
        assert await webhooks._db_claim_webhook("evt_1", "stripe") is True
        assert await webhooks._db_claim_webhook("evt_1", "paypal") is True


async def test_rows_from_before_the_migration_are_done():
    # The old table had no status. Those rows default to 'done', so nothing replays.
    async with _pool() as pool:
        await pool.execute(
            "INSERT INTO processed_webhooks (event_id, provider, processed_at) "
            "VALUES ('old', 'stripe', now() - interval '3 days')"
        )
        status = await pool.fetchval("SELECT status FROM processed_webhooks WHERE event_id = 'old'")
        assert status == "done"
        assert await webhooks._db_claim_webhook("old", "stripe") is False
