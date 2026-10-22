"""DAT-11: both erase routes reach every store in the registry.

Behaviour under test: `delete_account` (api/saas_router.py) and
`erase_user_data` (api/routes/gdpr.py) over the registry in api/user_data.py.
`/api/account/delete` never called `UserDataEraser`, so Neuro tenants and
event-store aggregates survived; `DELETE /api/user/data` skipped uploads,
history files and vectors. There were two erase lists and both were incomplete.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from reasoner.api.user_data import ACCOUNT_STORE_NAMES

pytestmark = pytest.mark.unit

NAMES = [
    "events", "vectors", "uploads", "history", "neuro", "valkey",
    "query_log", "credit_ledger", "quota", "subscriptions", "profile", "identity",
]


class _Store:
    def __init__(self, name: str, log: list) -> None:
        self.name, self._log = name, log

    async def export(self, user_id: str):
        return None

    async def erase(self, user_id: str) -> None:
        self._log.append(self.name)


class _Pool:
    def __init__(self, log: list) -> None:
        self._log = log

    async def fetch(self, sql: str, *args):
        return []

    async def execute(self, sql: str, *args):
        self._log.append("deletion_log")


@pytest.fixture
def registry(monkeypatch):
    from reasoner.api import user_data
    from reasoner.core.settings import settings
    from reasoner.infrastructure.persistence import quota_repo_postgres

    log: list[str] = []
    stores = [_Store(n, log) for n in NAMES]
    monkeypatch.setattr(user_data, "user_data_stores", lambda: stores)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://x/y", raising=False)

    class _Repo:
        def __init__(self, dsn, pool_size=2):
            pass

        async def _get_pool(self):
            return _Pool(log)

    monkeypatch.setattr(quota_repo_postgres, "PostgresQuotaRepository", _Repo)
    return log


def _request():
    return SimpleNamespace(client=None, headers={}, state=SimpleNamespace())


@pytest.mark.asyncio
async def test_delete_account_erases_every_store_in_the_registry(registry):
    from reasoner.api import saas_router

    result = await saas_router.delete_account(
        _request(), SimpleNamespace(id=uuid.uuid4()), None
    )

    assert [n for n in registry if n != "deletion_log"] == NAMES
    assert result["erased"] == NAMES and result["failed"] == []


@pytest.mark.asyncio
async def test_the_deletion_log_is_written_before_any_store_is_erased(registry):
    from reasoner.api import saas_router

    await saas_router.delete_account(_request(), SimpleNamespace(id=uuid.uuid4()), None)

    assert registry[0] == "deletion_log"


@pytest.mark.asyncio
async def test_the_data_route_reaches_the_same_stores_minus_the_account(registry, monkeypatch):
    from reasoner.api.routes import gdpr

    user = SimpleNamespace(id=uuid.uuid4())
    receipt = await gdpr.erase_user_data(user)

    assert receipt["erased"] == [n for n in NAMES if n not in ACCOUNT_STORE_NAMES]
    assert "profile" not in registry and "identity" not in registry


@pytest.mark.asyncio
async def test_the_data_route_reports_a_failed_store_as_an_error(registry, monkeypatch):
    from fastapi import HTTPException

    from reasoner.api import user_data
    from reasoner.api.routes import gdpr

    class _Broken(_Store):
        async def erase(self, user_id):
            raise OSError("disk gone")

    stores = [_Store("events", registry), _Broken("uploads", registry), _Store("neuro", registry)]
    monkeypatch.setattr(user_data, "user_data_stores", lambda: stores)

    with pytest.raises(HTTPException) as exc:
        await gdpr.erase_user_data(SimpleNamespace(id=uuid.uuid4()))

    assert exc.value.status_code == 500 and "uploads" in exc.value.detail
    assert "neuro" in registry, "the failure did not stop the rest"
