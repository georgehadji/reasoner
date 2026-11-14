"""GET /api/health is public: a failed probe must not hand its exception text
(which can name hosts, ports or DSNs) to anyone but an admin."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from reasoner.application.services import health_service

SECRET = "connection to db-internal.example:5432 refused"


async def _check(monkeypatch, *, is_admin: bool) -> dict:
    from reasoner.core.settings import settings

    async def refuse(*_args, **_kwargs):
        raise ConnectionError(SECRET)

    monkeypatch.setattr(health_service, "_health_postgres_pool", None)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://x:x@localhost:5432/x")
    with patch("asyncpg.create_pool", side_effect=refuse):
        return await health_service.check_health(is_admin=is_admin)


@pytest.mark.asyncio
async def test_public_failure_carries_status_only(monkeypatch):
    health = await _check(monkeypatch, is_admin=False)

    assert health["checks"]["postgres"] == {"status": "error"}
    assert health["status"] == "unhealthy"
    assert SECRET not in repr(health)


@pytest.mark.asyncio
async def test_admin_failure_keeps_the_reason(monkeypatch):
    health = await _check(monkeypatch, is_admin=True)

    assert health["checks"]["postgres"] == {"status": "error", "reason": SECRET}
