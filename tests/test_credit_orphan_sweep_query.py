"""The orphan sweep must be bounded below so the partial reserve index can serve it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from reasoner.infrastructure.persistence.credit_repo_postgres import PostgresCreditRepository

pytestmark = pytest.mark.unit


class _Pool:
    async def fetch(self, sql, *args):
        self.sql, self.args = sql, args
        return []


@pytest.mark.asyncio
async def test_sweep_has_a_lower_time_bound():
    repo = PostgresCreditRepository("postgresql://x")
    pool = _Pool()

    async def _get_pool():
        return pool

    repo._get_pool = _get_pool
    cutoff = datetime.now(UTC) - timedelta(hours=1)
    await repo.list_orphaned_reservations(cutoff, limit=10)
    assert "r.created_at > $3" in pool.sql
    lower = pool.args[2]
    assert timedelta(days=6) < datetime.now(UTC) - lower < timedelta(days=8)
