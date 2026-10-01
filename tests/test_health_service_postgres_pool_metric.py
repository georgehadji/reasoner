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


class RecordingGauge:
    """Stands in for the gauge so the test holds without prometheus_client.

    CI installs no prometheus_client, so reasoner.metrics hands out a no-op
    metric there and a real Gauge's private ``_value`` does not exist.
    """

    def __init__(self) -> None:
        self.values: list[float] = []

    def set(self, value: float) -> None:
        self.values.append(value)


@pytest.mark.asyncio
async def test_postgres_pool_free_gauge_reports_idle_not_busy(monkeypatch):
    from reasoner import metrics
    from reasoner.core.settings import settings

    # size=10, idle=3 -> 7 connections are busy. The gauge must read the
    # free count (3), never the busy count (7).
    gauge = RecordingGauge()
    monkeypatch.setattr(metrics, "REASONER_POSTGRES_POOL_FREE", gauge)
    fake_pool = FakePostgresPool(size=10, idle=3)
    monkeypatch.setattr(health_service, "_health_postgres_pool", fake_pool)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://fake/db")

    await health_service.check_health()

    assert gauge.values == [3]
