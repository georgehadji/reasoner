"""DAT-10, DAT-11: export and both erase routes iterate one ordered registry of stores.

Behaviour under test: `UserDataEraser` and `UserDataExporter`
(application/services/data_eraser.py) over `UserDataStore` strategies
(application/ports/user_data.py). Three hand-written lists had drifted apart:
export read columns that did not exist, `/api/account/delete` skipped Neuro and
the event store, and `DELETE /api/user/data` skipped uploads, history and
vectors.
"""

from __future__ import annotations

from typing import Any

import pytest

from reasoner.application.services.data_eraser import UserDataEraser, UserDataExporter
from reasoner.core.exceptions import UserDataExportError

pytestmark = pytest.mark.unit


class _Store:
    def __init__(self, name: str, *, export: Any = None, fail: str | None = None, log=None):
        self.name = name
        self._export = export
        self._fail = fail
        self._log = log if log is not None else []

    async def export(self, user_id: str) -> Any:
        if self._fail:
            raise RuntimeError(self._fail)
        return self._export

    async def erase(self, user_id: str) -> None:
        self._log.append((self.name, user_id))
        if self._fail:
            raise RuntimeError(self._fail)


@pytest.mark.asyncio
async def test_erase_visits_every_store_in_order():
    log: list = []
    stores = [_Store(n, log=log) for n in ("events", "uploads", "profile", "identity")]

    receipt = await UserDataEraser(stores).erase("u1")

    assert [n for n, _ in log] == ["events", "uploads", "profile", "identity"]
    assert receipt["status"] == "completed"
    assert receipt["erased"] == ["events", "uploads", "profile", "identity"]
    assert receipt["failed"] == []


@pytest.mark.asyncio
async def test_one_failing_store_does_not_stop_the_rest():
    log: list = []
    stores = [
        _Store("events", log=log),
        _Store("uploads", fail="disk gone", log=log),
        _Store("neuro", log=log),
    ]

    receipt = await UserDataEraser(stores).erase("u1")

    assert [n for n, _ in log] == ["events", "uploads", "neuro"]
    assert receipt["status"] == "partial"
    assert receipt["erased"] == ["events", "neuro"]
    assert receipt["failed"] == [{"store": "uploads", "error": "disk gone"}]


@pytest.mark.asyncio
async def test_a_receipt_never_says_completed_when_a_store_failed():
    receipt = await UserDataEraser([_Store("neuro", fail="unreachable")]).erase("u1")

    assert receipt["status"] != "completed"


@pytest.mark.asyncio
async def test_export_returns_one_key_per_store():
    stores = [
        _Store("profile", export={"id": "u1"}),
        _Store("valkey", export=None),
        _Store("history", export=[{"id": "h1"}]),
    ]

    out = await UserDataExporter(stores).export("u1")

    assert out == {"profile": {"id": "u1"}, "valkey": None, "history": [{"id": "h1"}]}


@pytest.mark.asyncio
async def test_a_failing_store_fails_the_export_instead_of_shortening_it():
    stores = [_Store("profile", export={}), _Store("history", fail="boom")]

    with pytest.raises(UserDataExportError) as exc:
        await UserDataExporter(stores).export("u1")

    assert "history" in str(exc.value)
