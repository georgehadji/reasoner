"""DAT-10 on a real Postgres: every exported column exists, and erase leaves nothing.

Behaviour under test: infrastructure/persistence/user_data_pg.py, the five
Postgres `UserDataStore`s, against a database built by `alembic upgrade head`.
Export used to select `users.display_name`, `subscriptions.stripe_subscription_id`
and `query_audit_logs.preset/method/tokens_*`, none of which exist, so
`GET /api/account/export` returned 500 for everyone.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from reasoner.infrastructure.persistence.user_data_pg import (
    EXPORT_FIELDS,
    pg_user_data_stores,
)
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


async def _seed(conn) -> str:
    uid = str(await conn.fetchval(
        "INSERT INTO users (email) VALUES ($1) RETURNING id", f"{uuid4().hex}@t.local"
    ))
    await conn.execute(
        "INSERT INTO subscriptions (user_id, tier, status, current_period_start, "
        "current_period_end, stripe_sub_id) VALUES ($1, 'pro', 'active', now(), now(), 'sub_1')",
        uid,
    )
    await conn.execute(
        "INSERT INTO usage_quotas (user_id, tier, used_queries, max_queries, period_start) "
        "VALUES ($1, 'pro', 3, 100, now())", uid,
    )
    await conn.execute(
        "INSERT INTO query_log (user_id, preset, method, tokens_in, tokens_out, cost_usd) "
        "VALUES ($1, 'debate-budget', 'debate', 10, 20, 0.01)", uid,
    )
    await conn.execute(
        "INSERT INTO credit_ledger (user_id, delta, balance_after, reason, reference_id) "
        "VALUES ($1, 100, 100, 'grant', 'ref-1')", uid,
    )
    return uid


async def test_every_export_column_exists_in_the_alembic_schema():
    import asyncpg

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        conn = await asyncpg.connect(dsn)
        try:
            columns = {(r["table_name"], r["column_name"]) for r in await conn.fetch(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public'"
            )}
        finally:
            await conn.close()

    wanted = {(table, col) for table, fields in EXPORT_FIELDS.items() for col in fields}
    assert wanted <= columns, f"export selects missing columns: {sorted(wanted - columns)}"


async def test_export_returns_each_store_with_the_users_rows():
    import asyncpg

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        try:
            async with pool.acquire() as conn:
                uid = await _seed(conn)

            async def get_pool():
                return pool

            out = {s.name: await s.export(uid) for s in pg_user_data_stores(get_pool)}
        finally:
            await pool.close()

    assert out["profile"]["email"].endswith("@t.local")
    assert [s["tier"] for s in out["subscriptions"]] == ["pro"]
    assert out["quota"]["used_queries"] == 3
    assert [q["method"] for q in out["query_log"]] == ["debate"]
    assert [e["delta"] for e in out["credit_ledger"]] == [100]


async def test_erase_removes_every_row_including_the_query_log():
    """query_log is ON DELETE SET NULL, so deleting only the user would leave
    the rows behind with no owner. They are the user's data and are erased."""
    import asyncpg

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        try:
            async with pool.acquire() as conn:
                uid = await _seed(conn)
                other = await _seed(conn)

            async def get_pool():
                return pool

            for store in pg_user_data_stores(get_pool):
                await store.erase(uid)

            async with pool.acquire() as conn:
                left = {
                    table: await conn.fetchval(f"SELECT count(*) FROM {table} WHERE {col} = $1", uid)
                    for table, col in (
                        ("users", "id"), ("subscriptions", "user_id"), ("usage_quotas", "user_id"),
                        ("query_log", "user_id"), ("credit_ledger", "user_id"),
                    )
                }
                kept = await conn.fetchval("SELECT count(*) FROM query_log WHERE user_id = $1", other)
        finally:
            await pool.close()

    assert left == dict.fromkeys(left, 0)
    assert kept == 1, "another user's rows are untouched"


async def test_the_pg_stores_are_named_for_the_registry():
    async def get_pool():
        return None

    assert [s.name for s in pg_user_data_stores(get_pool)] == [
        "query_log", "credit_ledger", "quota", "subscriptions", "profile",
    ]
