"""The health check must answer inside the UI's 3s liveness timeout.

useServerStatus aborts /api/health after 3s and shows "Offline". The Postgres
and Valkey probes used to run in sequence with 5s caps each, so with both
dependencies down the check took ~6s and a running backend read as offline.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from reasoner.application.services import health_service


class _HangingValkey:
    class connection_pool:  # noqa: N801 - mimics the attribute shape
        max_connections = 1

    async def ping(self) -> bool:
        await asyncio.sleep(60)
        return True


async def _hang(*_args, **_kwargs):
    await asyncio.sleep(60)


@pytest.mark.asyncio
async def test_down_dependencies_are_probed_in_parallel_and_capped(monkeypatch):
    from reasoner.core.settings import settings

    monkeypatch.setattr(health_service, "_PROBE_TIMEOUT_S", 0.3)
    monkeypatch.setattr(health_service, "_health_postgres_pool", None)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://x:x@localhost:5432/x")
    monkeypatch.setenv("VALKEY_URL", "redis://127.0.0.1:6379/0")

    with patch("asyncpg.create_pool", side_effect=_hang), patch(
        "reasoner.infrastructure.valkey.client.get_valkey_pool", return_value=_HangingValkey()
    ):
        started = time.perf_counter()
        health = await health_service.check_health()
        elapsed = time.perf_counter() - started

    assert health["checks"]["postgres"]["status"] == "error"
    assert health["checks"]["valkey"]["status"] == "error"
    assert health["status"] == "unhealthy"
    # Sequential would be >= 0.6s; parallel is one cap plus overhead.
    assert elapsed < 0.55


def test_probe_cap_fits_the_ui_liveness_timeout():
    assert health_service._PROBE_TIMEOUT_S < 3.0
