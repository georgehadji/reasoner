"""DAT-10: GET /api/account/export returns every store, or an error.

Behaviour under test: `export_data` (api/saas_router.py) over the registry in
api/user_data.py. It selected columns that do not exist (`users.display_name`,
`subscriptions.stripe_subscription_id`, `query_audit_logs.preset/method/tokens_*`)
and returned 500 for everyone, and it left out history, runs, memory, uploads
and the credit ledger. The live-Postgres column check is in
tests/integration/test_user_data_pg.py.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

pytestmark = pytest.mark.unit

NAMES = ["events", "history", "neuro", "profile", "credit_ledger", "identity"]


class _Store:
    def __init__(self, name: str, export=None, fail: bool = False) -> None:
        self.name, self._export, self._fail = name, export, fail

    async def export(self, user_id: str):
        if self._fail:
            raise OSError("unreadable")
        return self._export

    async def erase(self, user_id: str) -> None:
        raise AssertionError("export must not erase")


@pytest.fixture
def wired(monkeypatch):
    from reasoner.api import saas_router, user_data

    audit: list = []

    async def log_event(user_id, event_type, ip, ua):
        audit.append(event_type)

    monkeypatch.setattr(saas_router, "_log_auth_event", log_event)
    stores: list = []
    monkeypatch.setattr(user_data, "user_data_stores", lambda: stores)
    return saas_router, stores, audit


def _request():
    return SimpleNamespace(client=None, headers={})


@pytest.mark.asyncio
async def test_export_has_a_key_for_every_store(wired):
    saas_router, stores, audit = wired
    stores += [_Store(n, export={"n": n} if n != "identity" else None) for n in NAMES]

    out = await saas_router.export_data(_request(), SimpleNamespace(id=uuid.uuid4()), None)

    assert set(NAMES) <= set(out)
    assert out["history"] == {"n": "history"} and out["identity"] is None
    assert "exported_at" in out
    assert audit == ["data_export"]


@pytest.mark.asyncio
async def test_one_failing_store_fails_the_export_and_names_it(wired):
    saas_router, stores, audit = wired
    stores += [_Store("profile", export={}), _Store("neuro", fail=True)]

    with pytest.raises(HTTPException) as exc:
        await saas_router.export_data(_request(), SimpleNamespace(id=uuid.uuid4()), None)

    assert exc.value.status_code == 500
    assert exc.value.detail["stores"] == ["neuro"]
    assert audit == [], "an export that was not delivered is not logged as one"
