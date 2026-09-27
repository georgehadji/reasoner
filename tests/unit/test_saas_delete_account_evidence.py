"""Account deletion must not report success for data it could not erase.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

``delete_account`` is the GDPR Article 17 path. Its Phase 3 -- uploads, history
files, vector indexes, Redis keys -- runs after the DB transaction commits, and
every failure in it was ``except Exception: pass``. The endpoint returned
``{"status": "deleted"}`` with a 200 whether those stores were cleared or not.

There was a second failure on top of that: ``user_uploads`` was assigned inside
the uploads ``try``, and the vector-store block iterates it. So an uploads
failure left the name unbound, the vector block raised ``NameError``, and that
block's own bare handler swallowed it -- one failure costing two erasure phases,
with no trace of either.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest


class _FakeConn:
    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, sql: str, *args: object) -> None:
        self.statements.append(sql.strip().split()[0].upper())

    def transaction(self):
        return _NullCtx()


class _NullCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


class _AcquireCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    """Enough asyncpg surface for delete_account: no active subscription."""

    def __init__(self) -> None:
        self.conn = _FakeConn()

    async def fetchrow(self, sql: str, *args: object):
        return None

    def acquire(self) -> _AcquireCtx:
        return _AcquireCtx(self.conn)


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Point delete_account at a fake pool and an empty history dir."""
    from reasoner.api import history as history_module
    from reasoner.api import saas_router
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
    # The real HISTORY_DIR holds this machine's transcripts; glob an empty one.
    monkeypatch.setattr(history_module, "HISTORY_DIR", tmp_path)
    return saas_router, pool


def _request() -> SimpleNamespace:
    return SimpleNamespace(client=None, headers={}, state=SimpleNamespace())


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4())


@pytest.mark.asyncio
async def test_an_upload_store_failure_is_returned_to_the_caller(wired, monkeypatch):
    """A store that could not be cleared must appear in the response."""
    saas_router, pool = wired
    from reasoner import uploader

    def _boom(**kwargs):
        raise OSError("upload store unreachable")

    monkeypatch.setattr(uploader, "list_uploads", _boom)

    result = await saas_router.delete_account(_request(), _user(), None)

    assert "DELETE" in pool.conn.statements, "the user row must still be deleted"
    assert result["status"] == "deleted"
    assert any("saas.delete_account.uploads" in f for f in result["failed"]), (
        f"expected the uploads failure to be reported, got: {result['failed']}"
    )


@pytest.mark.asyncio
async def test_an_upload_failure_does_not_silently_cost_the_vector_phase(
    wired, monkeypatch
):
    """The NameError cascade: one unbound name took out a second erasure phase."""
    saas_router, _pool = wired
    from reasoner import uploader
    from reasoner.documents import vector_store

    def _boom(**kwargs):
        raise OSError("upload store unreachable")

    class _FakeStore:
        def delete_index(self, file_id: str) -> None:
            pass

    monkeypatch.setattr(uploader, "list_uploads", _boom)
    # Without this the vector block dies constructing its store, never reaching
    # the `for upload in user_uploads` line that the cascade came from -- and
    # the test passes whether the bug is present or not.
    monkeypatch.setattr(vector_store, "DocumentVectorStore", _FakeStore)

    result = await saas_router.delete_account(_request(), _user(), None)

    # UnboundLocalError, not NameError: user_uploads is a local of
    # delete_account. Both are checked -- getting this wrong is what made the
    # first version of this test pass against the bug it was written for.
    cascaded = [
        f for f in result["failed"]
        if "UnboundLocalError" in f or "NameError" in f
    ]
    assert not cascaded, f"the vector phase died on unbound user_uploads: {cascaded}"


@pytest.mark.asyncio
async def test_a_clean_run_reports_nothing_failed(wired, monkeypatch):
    """The evidence list must stay empty when every store is reachable."""
    saas_router, _pool = wired
    from reasoner import uploader
    from reasoner.documents import vector_store
    from reasoner.infrastructure.valkey import client as valkey_client

    monkeypatch.setattr(uploader, "list_uploads", lambda **kw: [])

    class _FakeStore:
        def delete_index(self, file_id: str) -> None:
            pass

    class _FakeRedis:
        async def keys(self, pattern: str) -> list[str]:
            return []

    monkeypatch.setattr(vector_store, "DocumentVectorStore", _FakeStore)
    monkeypatch.setattr(valkey_client, "get_valkey_pool", lambda: _FakeRedis())

    result = await saas_router.delete_account(_request(), _user(), None)

    assert result["failed"] == [], f"nothing failed, but got: {result['failed']}"
    assert result["deleted"]["db"] is True
