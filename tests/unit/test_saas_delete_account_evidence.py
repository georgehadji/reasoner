"""Account deletion must not report success for data it could not erase.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

``delete_account`` is the GDPR Article 17 path. Its content phase -- uploads,
history files, vector indexes, Redis keys -- runs after the DB transaction
commits, and every failure in it was ``except Exception: pass``. The endpoint
returned ``{"status": "deleted"}`` with a 200 whether those stores were cleared
or not.

There was a second failure on top of that: ``user_uploads`` was assigned inside
the uploads ``try``, and the vector-store block iterates it. So an uploads
failure left the name unbound and cost the vector phase too.

Since DAT-11 every store is a ``UserDataStore`` in one registry
(api/user_data.py), run in order by ``UserDataEraser``: a failing store is
returned to the caller by name and cannot cost another store its turn.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest


class _FakePool:
    """Enough asyncpg surface for delete_account: no active subscription."""

    def __init__(self) -> None:
        self.executed: list[str] = []

    async def fetch(self, sql: str, *args: object) -> list:
        return []  # delete_account reads every live subscription (BIL-8); none here

    async def execute(self, sql: str, *args: object) -> None:
        self.executed.append(sql.strip().split()[0].upper())


class _Store:
    def __init__(self, name: str, log: list, fail: str | None = None) -> None:
        self.name, self._log, self._fail = name, log, fail

    async def export(self, user_id: str):
        return None

    async def erase(self, user_id: str) -> None:
        self._log.append(self.name)
        if self._fail:
            raise OSError(self._fail)


@pytest.fixture
def wired(monkeypatch):
    """Point delete_account at a fake pool and a fake registry."""
    from reasoner.api import saas_router, user_data
    from reasoner.core.settings import settings
    from reasoner.infrastructure.persistence import quota_repo_postgres

    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://x/y", raising=False)
    pool = _FakePool()

    class _FakeRepo:
        def __init__(self, dsn: str, pool_size: int = 2) -> None:
            pass

        async def _get_pool(self) -> _FakePool:
            return pool

    monkeypatch.setattr(quota_repo_postgres, "PostgresQuotaRepository", _FakeRepo)
    log: list[str] = []
    stores: list = []
    monkeypatch.setattr(user_data, "user_data_stores", lambda: stores)
    return saas_router, pool, log, stores


def _request() -> SimpleNamespace:
    return SimpleNamespace(client=None, headers={}, state=SimpleNamespace())


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


@pytest.mark.asyncio
async def test_an_upload_store_failure_is_returned_to_the_caller(wired):
    """A store that could not be cleared must appear in the response."""
    saas_router, pool, log, stores = wired
    stores += [_Store("uploads", log, fail="upload store unreachable"), _Store("profile", log)]

    result = await saas_router.delete_account(_request(), _user(), None)

    assert "INSERT" in pool.executed, "the deletion log is written"
    assert result["status"] == "deleted"
    assert any("uploads" in f and "upload store unreachable" in f for f in result["failed"]), (
        f"expected the uploads failure to be reported, got: {result['failed']}"
    )


@pytest.mark.asyncio
async def test_an_upload_failure_does_not_silently_cost_the_vector_phase(wired):
    """The NameError cascade: one failure took out a second erasure phase."""
    saas_router, _pool, log, stores = wired
    stores += [_Store("vectors", log), _Store("uploads", log, fail="boom"), _Store("neuro", log)]

    result = await saas_router.delete_account(_request(), _user(), None)

    assert log == ["vectors", "uploads", "neuro"], "every store ran, the failure did not stop them"
    assert [f.split(":")[0] for f in result["failed"]] == ["uploads"]


@pytest.mark.asyncio
async def test_a_clean_run_reports_nothing_failed(wired):
    """The evidence list must stay empty when every store is reachable."""
    saas_router, _pool, log, stores = wired
    stores += [_Store("uploads", log), _Store("profile", log), _Store("identity", log)]

    result = await saas_router.delete_account(_request(), _user(), None)

    assert result["failed"] == [], f"nothing failed, but got: {result['failed']}"
    assert result["erased"] == ["uploads", "profile", "identity"]
