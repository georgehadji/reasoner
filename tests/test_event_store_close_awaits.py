"""close_event_store must await a backend whose close() is a coroutine.

get_event_store() returns either EventStore (SQLite, sync close) or
PostgreSQLEventStore (postgres_store.py:1013, async close awaiting both the
write and read asyncpg pools). reset_event_store() and api/__init__.py's
lifespan both called close() bare, so on a Postgres backend the coroutine was
discarded and both pools leaked, leaving only a RuntimeWarning.

These use a stand-in with the same close() shape rather than a real Postgres
pool: the defect is that the coroutine is never awaited, which is decidable
without a database. The real-backend behaviour is covered by the asyncpg
pools' own close(), not by this repo.
"""

from __future__ import annotations

import warnings

import pytest

from reasoner.infrastructure.persistence import event_store as es


class _AsyncCloseStore:
    """Same close() shape as PostgreSQLEventStore: a coroutine."""

    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _SyncCloseStore:
    """Same close() shape as the SQLite EventStore: an ordinary method."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def _restore_global():
    original = es._event_store
    yield
    es._event_store = original


@pytest.mark.asyncio
async def test_async_backend_close_is_awaited(_restore_global) -> None:
    """Proof of defect: bare close() left this False and leaked both pools."""
    store = _AsyncCloseStore()
    es._event_store = store

    await es.close_event_store()

    assert store.closed is True
    assert es._event_store is None


@pytest.mark.asyncio
async def test_async_backend_close_emits_no_never_awaited_warning(_restore_global) -> None:
    """The symptom that should never return: a discarded coroutine."""
    es._event_store = _AsyncCloseStore()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        await es.close_event_store()

    never_awaited = [w for w in caught if "never awaited" in str(w.message)]
    assert not never_awaited, f"coroutine was discarded: {never_awaited}"


@pytest.mark.asyncio
async def test_sync_backend_still_closes(_restore_global) -> None:
    """No-regression: the SQLite path has a sync close and must still work."""
    store = _SyncCloseStore()
    es._event_store = store

    await es.close_event_store()

    assert store.closed is True
    assert es._event_store is None


@pytest.mark.asyncio
async def test_close_is_a_noop_when_nothing_was_created(_restore_global) -> None:
    """Boundary: closing before any store exists must not raise."""
    es._event_store = None

    await es.close_event_store()

    assert es._event_store is None


@pytest.mark.asyncio
async def test_global_is_cleared_even_when_close_raises(_restore_global) -> None:
    """Boundary: a failing close must not leave a dead store bound.

    Otherwise the next get_event_store() hands back a closed store, which is
    the same shape as the shared-cache-port leak fixed earlier on this branch.
    """

    class _Boom:
        async def close(self) -> None:
            raise RuntimeError("pool already gone")

    es._event_store = _Boom()

    with pytest.raises(RuntimeError):
        await es.close_event_store()

    assert es._event_store is None
