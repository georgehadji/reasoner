"""Regression test for the inverted Postgres pool-free gauge.

health_service.check_health() used to set REASONER_POSTGRES_POOL_FREE to
``get_size() - get_idle_size()``, which in asyncpg is the number of BUSY
connections, not free ones. The critical PostgresPoolExhaustion alert
(``reasoner_postgres_pool_free == 0``, docs/monitoring/alerts.yml) therefore
fired on an idle pool and stayed silent when the pool was actually exhausted.
"""

from __future__ import annotations

import pytest

from reasoner.application.services import health_service


class FakePostgresPool:
    """Mimics the asyncpg.Pool methods check_health() reads."""

    def __init__(self, size: int, idle: int):
        self._size = size
        self._idle = idle

    async def fetchval(self, _query: str) -> int:
        return 1

    def get_size(self) -> int:
        return self._size

    def get_idle_size(self) -> int:
        return self._idle


@pytest.mark.asyncio
async def test_postgres_pool_free_gauge_reports_idle_not_busy(monkeypatch):
    from reasoner.core.settings import settings
    from reasoner.metrics import REASONER_POSTGRES_POOL_FREE

    # size=10, idle=3 -> 7 connections are busy. The gauge must read the
    # free count (3), never the busy count (7).
    fake_pool = FakePostgresPool(size=10, idle=3)
    monkeypatch.setattr(health_service, "_health_postgres_pool", fake_pool)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://fake/db")

    await health_service.check_health()

    assert REASONER_POSTGRES_POOL_FREE._value.get() == 3
