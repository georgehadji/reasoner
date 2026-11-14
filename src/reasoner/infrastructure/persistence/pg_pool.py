"""One shared asyncpg pool per (DSN, event loop) per worker process.

Every Postgres adapter (credits, quota, subscriptions, upload usage, webhooks,
user provisioning) acquires from this pool instead of creating its own, so a
worker holds at most ``DB_POOL_SIZE`` connections in total. Production runs
8 gunicorn workers, so the Postgres ceiling is ``8 * DB_POOL_SIZE``.

asyncpg pools are bound to the loop that created them. A pool made on another
loop (tests, ``asyncio.run``) is never reused; a new one is created for the
running loop.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

import asyncpg

from reasoner.core.constants import DEFAULT_DB_COMMAND_TIMEOUT

logger = logging.getLogger(__name__)

_MIN_SIZE = 1
# An advisory-lock holder pins one connection while the guarded writes need
# another, so holders are capped at half the pool; the floor of 2 keeps that
# half non-zero and leaves one connection for the writes.
_MIN_MAX_SIZE = 2


@dataclass
class _Slot:
    pool: asyncpg.Pool | None = None
    loop: asyncio.AbstractEventLoop | None = None
    # Shared creation task, awaited through asyncio.shield: a caller that times
    # out abandons its wait without cancelling the connect, so the pool still
    # completes in the background and the next call finds it ready.
    task: asyncio.Task | None = None
    lock_sem: asyncio.Semaphore | None = None
    lock_sem_loop: asyncio.AbstractEventLoop | None = field(default=None, repr=False)


_slots: dict[str, _Slot] = {}


def _normalise(dsn: str) -> str:
    # asyncpg rejects the SQLAlchemy '+asyncpg' driver suffix.
    return dsn.replace("+asyncpg", "")


def pool_max_size() -> int:
    from reasoner.core.settings import settings

    return max(_MIN_MAX_SIZE, int(settings.DB_POOL_SIZE))


async def _create(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(
        dsn,
        min_size=_MIN_SIZE,
        max_size=pool_max_size(),
        command_timeout=DEFAULT_DB_COMMAND_TIMEOUT,
    )


def _on_task_done(dsn: str, task: asyncio.Task) -> None:
    # Runs even when every waiter timed out, so a late success still lands and
    # a late failure is logged rather than "never retrieved".
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.warning("Postgres pool creation failed: %s", exc)
        return
    slot = _slots.get(dsn)
    if slot is None or task is not slot.task:
        # Superseded (or closed) while connecting: its pool must not replace the
        # current one. This runs on the task's own loop, so terminate it here.
        logger.warning("Discarding Postgres pool from a superseded creation task")
        task.result().terminate()
        return
    slot.pool, slot.loop = task.result(), task.get_loop()


async def get_shared_pool(dsn: str) -> asyncpg.Pool:
    """The process-wide pool for *dsn* on the running loop, created on first use."""
    dsn = _normalise(dsn)
    loop = asyncio.get_running_loop()
    slot = _slots.setdefault(dsn, _Slot())
    if slot.pool is not None and slot.loop is loop:
        return slot.pool

    task = slot.task
    # A failed task, or one from another loop, is replaced so the next call
    # retries; an in-flight one is shared.
    if task is None or task.get_loop() is not loop or (
        task.done() and (task.cancelled() or task.exception() is not None)
    ):
        task = loop.create_task(_create(dsn))
        task.add_done_callback(functools.partial(_on_task_done, dsn))
        slot.task = task
    return await asyncio.shield(task)


@asynccontextmanager
async def advisory_lock(dsn: str, key: str):
    """Hold a session advisory lock on *key* on one pooled connection.

    Lock and unlock run on the same connection, which goes back to the pool
    only after the unlock. Holders are capped (see ``_MIN_MAX_SIZE``) so many
    concurrent holders cannot take every connection and starve the guarded
    writes, which need pool connections of their own.
    """
    pool = await get_shared_pool(dsn)
    slot = _slots[_normalise(dsn)]
    loop = asyncio.get_running_loop()
    if slot.lock_sem is None or slot.lock_sem_loop is not loop:
        slot.lock_sem = asyncio.Semaphore(max(1, pool_max_size() // 2))
        slot.lock_sem_loop = loop
    async with slot.lock_sem, pool.acquire(timeout=10.0) as conn:
        await conn.execute("SELECT pg_advisory_lock(hashtext($1))", str(key))
        try:
            yield
        finally:
            try:
                await conn.execute("SELECT pg_advisory_unlock(hashtext($1))", str(key))
            except Exception:
                # Closing the session releases the lock; the pool drops a closed
                # connection instead of reusing it.
                logger.warning("Advisory unlock failed; terminating the connection")
                conn.terminate()


async def close_shared_pools() -> None:
    """Close this loop's pools (app shutdown) and reset all state. Idempotent."""
    slots = list(_slots.values())
    _slots.clear()
    loop = asyncio.get_running_loop()
    for slot in slots:
        if slot.task is not None and not slot.task.done():
            slot.task.cancel()
        if slot.pool is None:
            continue
        if slot.loop is loop:
            await slot.pool.close()
        else:
            logger.warning("Postgres pool belongs to another event loop; not closing it")
