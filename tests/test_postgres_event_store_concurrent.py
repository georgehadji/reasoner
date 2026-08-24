"""Tests for PostgreSQL event store concurrent writes."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_concurrent_writes_without_global_lock():
    """
    Simulating 50 concurrent save_events calls should succeed
    without serialization from a global lock.
    """
    pytest.importorskip("asyncpg")
    from reasoner.infrastructure.persistence.postgres_store import PostgreSQLEventStore

    store = PostgreSQLEventStore(connection_string="postgresql://test")
    mock_pool = MagicMock()
    mock_conn = AsyncMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    # conn.transaction() must return an object usable with `async with`.
    # transaction is a *method* that returns a context-manager object,
    # so we use MagicMock (not AsyncMock) so the call itself is sync.
    mock_conn.transaction = MagicMock()
    mock_conn.transaction.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    store._pool = mock_pool

    from reasoner.core.events.domain_events import DomainEvent, EventType

    async def save_one(i: int):
        event = DomainEvent(
            event_id=f"evt-{i}",
            event_type=EventType.PHASE_COMPLETED,
            aggregate_id="pipe-1",
            version=i,
            timestamp=1704067200.0,
        )
        await store.save_events([event])

    tasks = [asyncio.create_task(save_one(i)) for i in range(50)]
    await asyncio.gather(*tasks)

    assert mock_conn.execute.await_count >= 50
