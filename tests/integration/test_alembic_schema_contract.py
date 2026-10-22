"""`alembic upgrade head` produces the schema the Postgres repositories use (PER-7).

The baseline revision could not run on Postgres at all (a unique constraint on
a partitioned table without the partition key), and the credit ledger, the
Postgres api_keys table and the webhook dead-letter table existed only in raw
.sql files that nothing executes. Nothing caught either, because no test ever
ran the migrations against a real database.

Each scenario uses its own throwaway database on the server behind
REASONER_TEST_PG_DSN, for example the local `reasoner-pg-test` container:
    REASONER_TEST_PG_DSN=postgresql://postgres:test@localhost:55499/reasoner_test
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

DSN = os.environ.get("REASONER_TEST_PG_DSN")
ROOT = Path(__file__).resolve().parents[2]
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not DSN, reason="REASONER_TEST_PG_DSN not set"),
]

#: Every table a Postgres repository reads or writes.
TABLES = {
    "users", "subscriptions", "usage_quotas", "query_log", "auth_audit_log",
    "account_deletion_log", "events", "events_default", "aggregates", "snapshots",
    "read_models", "user_credits", "credit_ledger", "api_keys", "failed_webhook_events",
}
#: Unique keys behind the repositories' ON CONFLICT targets and idempotency checks.
UNIQUE_KEYS = {
    ("events", ("event_id", "aggregate_type")),       # postgres_store.append_events
    ("snapshots", ("aggregate_id",)),                 # postgres_store.save_snapshot
    ("aggregates", ("aggregate_id",)),
    ("read_models", ("model_name", "model_key")),
    ("user_credits", ("user_id",)),                   # credit_repo_postgres
    ("credit_ledger", ("user_id", "reference_id")),   # the ledger's idempotency key
    ("usage_quotas", ("user_id",)),                   # quota_repo_postgres
    ("api_keys", ("key_hash",)),                      # api_key_repo_postgres
}
COLUMNS = {("subscriptions", "stripe_sub_id"), ("subscriptions", "paypal_sub_id")}


def _with_db(name: str) -> str:
    base, _, _ = DSN.rpartition("/")
    return f"{base}/{name}"


@contextlib.asynccontextmanager
async def _fresh_database():
    import asyncpg

    name = f"contract_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(DSN)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
        try:
            yield _with_db(name)
        finally:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


def _alembic_upgrade(dsn: str) -> None:
    env = {**os.environ, "DATABASE_URL": dsn.replace("postgresql://", "postgresql+asyncpg://", 1)}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]


async def _assert_contract(dsn: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        tables = {r["table_name"] for r in await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )}
        assert TABLES <= tables, f"missing tables: {sorted(TABLES - tables)}"

        rows = await conn.fetch("""
            SELECT t.relname AS tbl,
                   array_agg(a.attname ORDER BY k.ord) AS cols
            FROM pg_index i
            JOIN pg_class t ON t.oid = i.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = 'public'
            CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord)
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
            WHERE i.indisunique
            GROUP BY i.indexrelid, t.relname
        """)
        unique = {(r["tbl"], tuple(r["cols"])) for r in rows}
        assert UNIQUE_KEYS <= unique, f"missing unique keys: {sorted(UNIQUE_KEYS - unique)}"

        columns = {(r["table_name"], r["column_name"]) for r in await conn.fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        )}
        assert COLUMNS <= columns, f"missing columns: {sorted(COLUMNS - columns)}"

        dead = await conn.fetchval("SELECT 1 FROM pg_indexes WHERE indexname = 'idx_events_type'")
        assert dead is None, "idx_events_type indexes ciphertext; migration 008 drops it"
    finally:
        await conn.close()


async def test_upgrade_head_on_an_empty_database():
    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        await _assert_contract(dsn)


async def test_upgrade_head_after_the_event_store_created_its_tables_at_boot():
    """The other order production can be in: the app booted (and created the
    event tables) before migrations ran."""
    from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore

    async with _fresh_database() as dsn:
        store = PostgreSQLEventStore(connection_string=dsn, pool_size=2)
        try:
            await store.initialize()
        finally:
            await store.close()
        _alembic_upgrade(dsn)
        await _assert_contract(dsn)


async def test_upgrade_is_repeatable():
    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        _alembic_upgrade(dsn)
        await _assert_contract(dsn)
