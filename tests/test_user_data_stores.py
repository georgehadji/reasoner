"""The non-Postgres user-data stores (DAT-10, DAT-11): events, uploads, vectors,
history, valkey, neuro.

Behaviour under test: infrastructure/persistence/user_data_local.py. Each store
exports what it holds and, on erase, raises when anything of the user's is
left, so the orchestrator can never report a partial erase as complete. The
collaborators are injected, so these run on fakes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from reasoner.infrastructure.persistence.user_data_local import (
    EventsStore,
    HistoryStore,
    NeuroStore,
    UploadsStore,
    ValkeyStore,
    VectorsStore,
)

pytestmark = pytest.mark.unit

UID = "11111111-1111-1111-1111-111111111111"


# ── events ───────────────────────────────────────────────────────────────


class _Events:
    def __init__(self, ids, fail_on=None):
        self.ids, self.deleted, self._fail_on = list(ids), [], fail_on

    async def list_aggregate_ids_for_user(self, user_id):
        return self.ids

    async def count_events(self, aggregate_id):
        return 3

    async def delete_aggregate(self, aggregate_id):
        if aggregate_id == self._fail_on:
            raise OSError("locked")
        self.deleted.append(aggregate_id)


@pytest.mark.asyncio
async def test_events_export_lists_aggregates_with_event_counts():
    out = await EventsStore(lambda: _Events(["a", "b"])).export(UID)

    assert out == {"aggregates": [{"id": "a", "events": 3}, {"id": "b", "events": 3}]}


@pytest.mark.asyncio
async def test_events_erase_deletes_every_aggregate():
    store = _Events(["a", "b"])
    await EventsStore(lambda: store).erase(UID)
    assert store.deleted == ["a", "b"]


@pytest.mark.asyncio
async def test_events_erase_raises_after_trying_all_when_one_fails():
    store = _Events(["a", "b", "c"], fail_on="b")

    with pytest.raises(RuntimeError, match="b"):
        await EventsStore(lambda: store).erase(UID)

    assert store.deleted == ["a", "c"], "one failure must not strand the rest"


# ── uploads and vectors ──────────────────────────────────────────────────


class _Files:
    def __init__(self, ids, fail_delete=()):
        self.ids, self.deleted, self._fail = list(ids), [], set(fail_delete)

    def list_uploads(self, user_id, include_incomplete):
        assert include_incomplete is True, "a crash mid-write is still the user's file"
        return [{"file_id": i, "filename": f"{i}.txt", "size": 5, "created": 1.0} for i in self.ids]

    def delete_file(self, file_id):
        if file_id in self._fail:
            return False
        self.deleted.append(file_id)
        return True


class _Usage:
    def __init__(self):
        self.forgotten = []

    async def forget(self, user_id):
        self.forgotten.append(user_id)


@pytest.mark.asyncio
async def test_uploads_export_is_metadata_not_file_content():
    out = await UploadsStore(_Files(["f1"]), lambda: _Usage()).export(UID)

    assert out == [{"file_id": "f1", "filename": "f1.txt", "size": 5, "created": 1.0}]


@pytest.mark.asyncio
async def test_uploads_erase_deletes_files_and_forgets_the_usage_row():
    files, usage = _Files(["f1", "f2"]), _Usage()

    await UploadsStore(files, lambda: usage).erase(UID)

    assert files.deleted == ["f1", "f2"] and usage.forgotten == [UID]


@pytest.mark.asyncio
async def test_uploads_erase_raises_when_a_file_could_not_be_deleted():
    files = _Files(["f1", "f2"], fail_delete=["f1"])

    with pytest.raises(RuntimeError, match="f1"):
        await UploadsStore(files, lambda: _Usage()).erase(UID)

    assert files.deleted == ["f2"]


class _Vectors:
    def __init__(self, fail=()):
        self.deleted, self._fail = [], set(fail)

    def delete_index(self, file_id):
        if file_id in self._fail:
            raise OSError("index busy")
        self.deleted.append(file_id)


@pytest.mark.asyncio
async def test_vectors_erase_removes_the_index_of_every_upload():
    vectors = _Vectors()

    await VectorsStore(_Files(["f1", "f2"]), lambda: vectors).erase(UID)

    assert vectors.deleted == ["f1", "f2"]


@pytest.mark.asyncio
async def test_vectors_erase_raises_when_an_index_could_not_be_removed():
    with pytest.raises(RuntimeError, match="f2"):
        await VectorsStore(_Files(["f1", "f2"]), lambda: _Vectors(fail=["f2"])).erase(UID)


# ── history ──────────────────────────────────────────────────────────────


class _History:
    def __init__(self, entries, erase_result=(0, 0)):
        self.entries, self._result, self.erased = entries, erase_result, []

    async def list(self, owner, limit, offset, tag=None):
        return self.entries, len(self.entries)

    async def erase(self, owner):
        self.erased.append(owner)
        return self._result


@pytest.mark.asyncio
async def test_history_export_returns_the_users_entries():
    out = await HistoryStore(lambda: _History([{"id": "h1"}])).export(UID)

    assert out == [{"id": "h1"}]


@pytest.mark.asyncio
async def test_history_erase_raises_when_files_remain():
    with pytest.raises(RuntimeError, match="2"):
        await HistoryStore(lambda: _History([], erase_result=(5, 2))).erase(UID)


# ── valkey ───────────────────────────────────────────────────────────────


class _Valkey:
    def __init__(self, keys):
        self.keys_, self.deleted = keys, []

    async def keys(self, pattern):
        self.pattern = pattern
        return self.keys_

    async def delete(self, *keys):
        self.deleted.extend(keys)


@pytest.mark.asyncio
async def test_valkey_erase_deletes_the_users_keys_only():
    client = _Valkey(["user:u:a", "user:u:b"])

    await ValkeyStore(lambda: client).erase(UID)

    assert client.pattern == f"user:{UID}:*"
    assert client.deleted == ["user:u:a", "user:u:b"]


@pytest.mark.asyncio
async def test_valkey_erase_raises_when_valkey_is_down():
    class _Down:
        async def keys(self, pattern):
            raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        await ValkeyStore(lambda: _Down()).erase(UID)


# ── neuro ────────────────────────────────────────────────────────────────


class _Memory:
    def __init__(self, erase_result=None, export_result=None):
        self._erase = erase_result or {"erased": True}
        self._export = export_result

    async def erase_owner(self, owner):
        return self._erase

    async def export_owner(self, owner):
        return self._export


@pytest.mark.asyncio
async def test_neuro_export_returns_the_memory_entries():
    out = await NeuroStore(lambda: _Memory(export_result={"u-x": [{"content": "c"}]})).export(UID)

    assert out == {"u-x": [{"content": "c"}]}


@pytest.mark.asyncio
async def test_neuro_erase_raises_when_the_memory_port_reports_incomplete():
    port = _Memory({"erased": False, "error": "disk busy"})

    with pytest.raises(RuntimeError, match="disk busy"):
        await NeuroStore(lambda: port).erase(UID)


@pytest.mark.asyncio
async def test_neuro_erase_raises_when_the_port_is_not_registered():
    with pytest.raises(RuntimeError, match="not registered"):
        await NeuroStore(lambda: None).erase(UID)


@pytest.mark.asyncio
async def test_neuro_export_of_an_unregistered_port_raises_not_returns_empty():
    with pytest.raises(RuntimeError, match="not registered"):
        await NeuroStore(lambda: None).export(UID)


def test_every_store_has_a_stable_name():
    stores = [
        EventsStore(lambda: None), UploadsStore(SimpleNamespace(), lambda: None),
        VectorsStore(SimpleNamespace(), lambda: None), HistoryStore(lambda: None),
        ValkeyStore(lambda: None), NeuroStore(lambda: None),
    ]
    assert [s.name for s in stores] == ["events", "uploads", "vectors", "history", "valkey", "neuro"]
