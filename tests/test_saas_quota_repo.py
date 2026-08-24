"""Unit tests for PostgresQuotaRepository with mocked asyncpg pool."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from reasoner.domain.saas import SubscriptionTier
from reasoner.infrastructure.persistence.quota_repo_postgres import PostgresQuotaRepository


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    return pool


@pytest.fixture
def repo(mock_pool):
    # _pool is a CLASS attribute and _get_pool() reads it off the class, so an
    # instance-level `r._pool = mock_pool` no longer shadows it -- _get_pool()
    # saw None and called asyncpg.create_pool() against postgresql://test,
    # which is why these "mocked pool" tests died on socket.gaierror. Patch the
    # class attribute and restore it so the process-wide pool stays clean.
    original = PostgresQuotaRepository._pool
    PostgresQuotaRepository._pool = mock_pool
    try:
        yield PostgresQuotaRepository("postgresql://test")
    finally:
        PostgresQuotaRepository._pool = original


@pytest.mark.asyncio
async def test_get_quota_existing_user(repo, mock_pool):
    mock_pool.fetchrow.return_value = {
        "user_id": "11111111-1111-1111-1111-111111111111",
        "tier": "free",
        "used_queries": 5,
        "max_queries": 20,
        "period_start": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    quota = await repo.get_quota("11111111-1111-1111-1111-111111111111")
    assert quota.used_queries == 5
    assert quota.max_queries == 20
    assert quota.tier == SubscriptionTier.FREE


@pytest.mark.asyncio
async def test_get_quota_creates_default_for_new_user(repo, mock_pool):
    mock_pool.fetchrow.side_effect = [
        None,  # First call: no row
        {
            "user_id": "22222222-2222-2222-2222-222222222222",
            "tier": "free",
            "used_queries": 0,
            "max_queries": 20,
            "period_start": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        },
    ]
    quota = await repo.get_quota("22222222-2222-2222-2222-222222222222")
    assert quota.used_queries == 0
    assert quota.max_queries == 20
    mock_pool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_increment_allows_when_under_limit(repo, mock_pool):
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {
        "tier": "free",
        "used_queries": 5,
        "max_queries": 20,
    }
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_tx = AsyncMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_conn.transaction = MagicMock(return_value=mock_tx)
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    result = await repo.check_and_increment("user-1", "test-preset")
    assert result.allowed is True
    assert result.remaining == 14


@pytest.mark.asyncio
async def test_check_and_increment_blocks_when_exhausted(repo, mock_pool):
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {
        "tier": "free",
        "used_queries": 20,
        "max_queries": 20,
    }
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_tx = AsyncMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_conn.transaction = MagicMock(return_value=mock_tx)
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    result = await repo.check_and_increment("user-1", "test-preset")
    assert result.allowed is False
    assert result.remaining == 0


@pytest.mark.asyncio
async def test_check_and_increment_unlimited_enterprise(repo, mock_pool):
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {
        "tier": "enterprise",
        "used_queries": 9999,
        "max_queries": -1,
    }
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_tx = AsyncMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=False)
    mock_conn.transaction = MagicMock(return_value=mock_tx)
    mock_pool.acquire = MagicMock(return_value=mock_conn)

    result = await repo.check_and_increment("user-1", "test-preset")
    assert result.allowed is True
    assert result.remaining == -1


@pytest.mark.asyncio
async def test_reset_monthly(repo, mock_pool):
    await repo.reset_monthly("user-1")
    mock_pool.execute.assert_called_once()
