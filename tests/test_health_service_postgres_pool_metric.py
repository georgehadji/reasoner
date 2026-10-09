"""Regression test: the health probe's pool must not feed the pool gauges.

health_service.check_health() opens its own private asyncpg pool
(min_size=1, max_size=2) just to run ``SELECT 1``, and used to publish that
pool's size/idle count as reasoner_postgres_pool_size / _free. That pool is not
a serving pool (the app's real pools sit inside each Postgres repository at
DB_POOL_SIZE connections), so the gauge read ~1 forever: PostgresPoolLow
(`< 2`) fired permanently and PostgresPoolExhaustion (`== 0`) could never fire
on real saturation. The gauges and both alerts were removed rather than left
reporting a number unrelated to load.
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
async def test_health_probe_pool_does_not_write_pool_gauges(monkeypatch):
    from reasoner import metrics
    from reasoner.core.settings import settings

    # raising=False: the gauges no longer exist on the metrics module. On the
    # pre-fix code health_service imports them from here, so these recorders
    # are what it would write to, and the assertion below catches it.
    free, size = RecordingGauge(), RecordingGauge()
    monkeypatch.setattr(metrics, "REASONER_POSTGRES_POOL_FREE", free, raising=False)
    monkeypatch.setattr(metrics, "REASONER_POSTGRES_POOL_SIZE", size, raising=False)
    monkeypatch.setattr(health_service, "_health_postgres_pool", FakePostgresPool(size=2, idle=1))
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://fake/db")

    health = await health_service.check_health()

    assert health["checks"]["postgres"] == {"status": "ok"}
    assert free.values == []
    assert size.values == []


def test_postgres_pool_gauges_are_not_defined():
    """Nothing can alert on a gauge that nothing owns."""
    import reasoner.infrastructure.metrics as metrics_mod

    assert not hasattr(metrics_mod, "REASONER_POSTGRES_POOL_FREE")
    assert not hasattr(metrics_mod, "REASONER_POSTGRES_POOL_SIZE")
