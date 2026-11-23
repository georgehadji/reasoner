"""The one shared asyncpg pool per (DSN, loop) behind every Postgres adapter."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from reasoner.infrastructure.persistence import pg_pool

DSN = "postgresql://x"


def _pool_double(label="pool"):
    pool = MagicMock(name=label)
    pool.close = AsyncMock()
    return pool


@pytest.mark.asyncio
async def test_different_repos_get_the_same_pool(monkeypatch):
    from reasoner.infrastructure.persistence.credit_repo_postgres import PostgresCreditRepository
    from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository
    from reasoner.infrastructure.persistence.subscription_repo import (
        PostgresSubscriptionRepository,
    )
    from reasoner.infrastructure.persistence.upload_usage_repo import (
        PostgresUploadUsageRepository,
    )

    made = []

    async def create_pool(*args, **kwargs):
        made.append(_pool_double())
        return made[-1]

    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", create_pool)
    repos = [
        PostgresQuotaRepository(DSN),
        PostgresCreditRepository(DSN),
        PostgresSubscriptionRepository(DSN),
        PostgresUploadUsageRepository(DSN),
    ]
    pools = await asyncio.gather(*(r._get_pool() for r in repos))
    assert len(made) == 1
    assert all(p is made[0] for p in pools)


@pytest.mark.asyncio
async def test_sqlalchemy_driver_suffix_shares_the_pool(monkeypatch):
    made = []

    async def create_pool(dsn, **kwargs):
        made.append(dsn)
        return _pool_double()

    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", create_pool)
    a = await pg_pool.get_shared_pool("postgresql+asyncpg://x")
    b = await pg_pool.get_shared_pool("postgresql://x")
    assert a is b and made == ["postgresql://x"]


@pytest.mark.asyncio
async def test_pool_is_sized_by_db_pool_size(monkeypatch):
    seen = {}

    async def create_pool(dsn, **kwargs):
        seen.update(kwargs)
        return _pool_double()

    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", create_pool)
    monkeypatch.setattr("reasoner.core.settings.settings.DB_POOL_SIZE", 8)
    await pg_pool.get_shared_pool(DSN)
    assert seen["max_size"] == 8 and seen["min_size"] <= 2


@pytest.mark.asyncio
async def test_slow_first_connect_completes_in_background(monkeypatch):
    sentinel = _pool_double()
    state = {"n": 0, "cancelled": False}

    async def slow_create_pool(*args, **kwargs):
        state["n"] += 1
        try:
            await asyncio.sleep(0.2)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise
        return sentinel

    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", slow_create_pool)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(pg_pool.get_shared_pool(DSN), timeout=0.05)
    assert state["cancelled"] is False

    await asyncio.sleep(0.3)
    assert await pg_pool.get_shared_pool(DSN) is sentinel
    assert state["n"] == 1


@pytest.mark.asyncio
async def test_failed_connect_is_retried(monkeypatch):
    sentinel = _pool_double()
    attempts = {"n": 0}

    async def flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OSError("connection refused")
        return sentinel

    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", flaky)
    with pytest.raises(OSError):
        await pg_pool.get_shared_pool(DSN)
    assert await pg_pool.get_shared_pool(DSN) is sentinel
    assert attempts["n"] == 2


def test_pool_from_another_loop_is_not_reused(monkeypatch):
    made = []

    async def create_pool(*args, **kwargs):
        made.append(_pool_double())
        return made[-1]

    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", create_pool)
    first = asyncio.run(pg_pool.get_shared_pool(DSN))
    second = asyncio.run(pg_pool.get_shared_pool(DSN))
    assert first is made[0] and second is made[1] and first is not second


@pytest.mark.asyncio
async def test_superseded_task_does_not_overwrite_current_pool(monkeypatch):
    stray, current = _pool_double("stray"), _pool_double("current")
    release = asyncio.Event()

    async def create_pool(*args, **kwargs):
        await release.wait()
        return stray

    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", create_pool)
    loop = asyncio.get_running_loop()
    slot = pg_pool._slots.setdefault(DSN, pg_pool._Slot())
    old = loop.create_task(pg_pool._create(DSN))
    old.add_done_callback(lambda t: pg_pool._on_task_done(DSN, t))
    slot.task = old
    new = loop.create_task(asyncio.sleep(0, current))
    new.add_done_callback(lambda t: pg_pool._on_task_done(DSN, t))
    slot.task = new
    assert await new is current
    release.set()
    await old
    await asyncio.sleep(0)

    assert slot.pool is current
    stray.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_close_closes_pool_and_is_idempotent(monkeypatch):
    pool = _pool_double()

    async def create_pool(*args, **kwargs):
        return pool

    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", create_pool)
    await pg_pool.get_shared_pool(DSN)
    await asyncio.sleep(0)

    await pg_pool.close_shared_pools()
    pool.close.assert_awaited_once()
    assert pg_pool._slots == {}
    await pg_pool.close_shared_pools()


class _Conn:
    def __init__(self):
        self.calls = []
        self.terminated = False

    async def execute(self, sql, *args):
        self.calls.append(sql)

    def terminate(self):
        self.terminated = True


def _pool_with_conn(conn, acquired):
    @asynccontextmanager
    async def acquire(timeout=None):
        acquired.append(conn)
        yield conn

    pool = _pool_double()
    pool.acquire = acquire
    return pool


@pytest.mark.asyncio
async def test_user_lock_uses_a_pooled_connection_not_a_raw_one(monkeypatch):
    from reasoner.infrastructure.persistence.subscription_repo import (
        PostgresSubscriptionRepository,
    )

    conn, acquired = _Conn(), []
    pool = _pool_with_conn(conn, acquired)
    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", AsyncMock(return_value=pool))
    raw = AsyncMock(side_effect=AssertionError("raw asyncpg.connect used"))
    monkeypatch.setattr(pg_pool.asyncpg, "connect", raw, raising=False)

    async with PostgresSubscriptionRepository(DSN).user_lock("u1"):
        assert conn.calls == ["SELECT pg_advisory_lock(hashtext($1))"]
    # Unlocked on the same connection before it went back to the pool.
    assert conn.calls[-1] == "SELECT pg_advisory_unlock(hashtext($1))"
    assert acquired == [conn] and not conn.terminated
    raw.assert_not_called()


@pytest.mark.asyncio
async def test_failed_unlock_terminates_the_connection(monkeypatch):
    conn, acquired = _Conn(), []

    async def execute(sql, *args):
        if "unlock" in sql:
            raise OSError("gone")

    conn.execute = execute
    pool = _pool_with_conn(conn, acquired)
    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", AsyncMock(return_value=pool))
    async with pg_pool.advisory_lock(DSN, "u1"):
        pass
    assert conn.terminated


@pytest.mark.asyncio
async def test_lock_holders_are_capped_below_pool_size(monkeypatch):
    monkeypatch.setattr("reasoner.core.settings.settings.DB_POOL_SIZE", 4)
    conn, acquired = _Conn(), []
    pool = _pool_with_conn(conn, acquired)
    monkeypatch.setattr(pg_pool.asyncpg, "create_pool", AsyncMock(return_value=pool))
    inside, peak = 0, 0

    async def hold():
        nonlocal inside, peak
        async with pg_pool.advisory_lock(DSN, "u"):
            inside += 1
            peak = max(peak, inside)
            await asyncio.sleep(0.01)
            inside -= 1

    await asyncio.gather(*(hold() for _ in range(8)))
    assert peak == 2  # DB_POOL_SIZE 4 // 2
