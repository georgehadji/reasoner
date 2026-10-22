"""User-data stores for everything that is not a Postgres row (DAT-10, DAT-11):
the event store, uploaded files, vector indexes, history, Valkey and Neuro.

Each store implements ``application.ports.user_data.UserDataStore``. A store
raises when anything of the user's is left after ``erase``, after trying every
item it could, so the orchestrator can never report a partial erase as
complete. Collaborators are injected as factories: the composition root
(``api/user_data.py``) decides which concrete store backs each one.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

_UPLOAD_EXPORT_FIELDS = ("file_id", "filename", "size", "created")


def _raise_if(problems: list[str], what: str) -> None:
    if problems:
        raise RuntimeError(f"{what}: {', '.join(problems)}")


class EventsStore:
    """Event-store aggregates the user owns (pipeline runs and their events)."""

    name = "events"

    def __init__(self, get_store: Callable[[], Any]) -> None:
        self._get_store = get_store

    async def export(self, user_id: str) -> dict[str, Any]:
        store = self._get_store()
        ids = await store.list_aggregate_ids_for_user(user_id)
        return {
            "aggregates": [{"id": aid, "events": await store.count_events(aid)} for aid in ids]
        }

    async def erase(self, user_id: str) -> None:
        store = self._get_store()
        failed: list[str] = []
        # Listing raises on a store error rather than returning [], so an
        # unreachable store is a failed erase, not a clean one.
        for aid in await store.list_aggregate_ids_for_user(user_id):
            try:
                await store.delete_aggregate(aid)
            except Exception as exc:
                failed.append(f"{aid} ({exc})")
        _raise_if(failed, "event aggregates not deleted")


class UploadsStore:
    """Uploaded files, including ones whose write crashed half way."""

    name = "uploads"

    def __init__(self, files: Any, usage_repo: Callable[[], Any]) -> None:
        self._files = files
        self._usage_repo = usage_repo

    def _uploads(self, user_id: str) -> list[dict[str, Any]]:
        return self._files.list_uploads(user_id=user_id, include_incomplete=True)

    async def export(self, user_id: str) -> list[dict[str, Any]]:
        # Metadata only: the files themselves are not in the export (Q1).
        uploads = await asyncio.to_thread(self._uploads, user_id)
        return [{k: u.get(k) for k in _UPLOAD_EXPORT_FIELDS} for u in uploads]

    async def erase(self, user_id: str) -> None:
        uploads = await asyncio.to_thread(self._uploads, user_id)
        failed = []
        for upload in uploads:
            if not await asyncio.to_thread(self._files.delete_file, upload["file_id"]):
                failed.append(upload["file_id"])
        await self._usage_repo().forget(user_id)
        _raise_if(failed, "uploads not deleted")


class VectorsStore:
    """Vector indexes built from the user's uploads. Needs the upload ids, so
    it runs before ``uploads`` in the registry."""

    name = "vectors"

    def __init__(self, files: Any, vector_store: Callable[[], Any]) -> None:
        self._files = files
        self._vector_store = vector_store

    async def export(self, user_id: str) -> None:
        return None  # derived from the uploads; nothing the user supplied

    async def erase(self, user_id: str) -> None:
        uploads = await asyncio.to_thread(
            lambda: self._files.list_uploads(user_id=user_id, include_incomplete=True)
        )
        store = self._vector_store()
        failed = []
        for upload in uploads:
            try:
                await asyncio.to_thread(store.delete_index, upload["file_id"])
            except Exception:
                failed.append(upload["file_id"])
        _raise_if(failed, "vector indexes not deleted")


class HistoryStore:
    """Run history (PER-12): one directory per owner."""

    name = "history"

    def __init__(self, repo: Callable[[], Any]) -> None:
        self._repo = repo

    async def export(self, user_id: str) -> list[dict[str, Any]]:
        entries, _ = await self._repo().list(user_id, 1000, 0)
        return entries

    async def erase(self, user_id: str) -> None:
        _, failed = await self._repo().erase(user_id)
        if failed:
            raise RuntimeError(f"{failed} history file(s) not erased")


class ValkeyStore:
    """Cache keys under ``user:<id>:*``."""

    name = "valkey"

    def __init__(self, client: Callable[[], Any]) -> None:
        self._client = client

    async def export(self, user_id: str) -> None:
        return None  # a cache of derived values

    async def erase(self, user_id: str) -> None:
        client = self._client()
        keys = await client.keys(f"user:{user_id}:*")
        if keys:
            await client.delete(*keys)


class NeuroStore:
    """Long-term memory. Goes through the MemoryPort, so application code never
    imports ``reasoner.neuro``."""

    name = "neuro"

    def __init__(self, port: Callable[[], Any]) -> None:
        self._port = port

    def _require(self) -> Any:
        port = self._port()
        if port is None:
            raise RuntimeError(
                "memory port is not registered (neuro unavailable); "
                "long-term memory could not be read or erased"
            )
        return port

    async def export(self, user_id: str) -> Any:
        return await self._require().export_owner(user_id)

    async def erase(self, user_id: str) -> None:
        result = await self._require().erase_owner(user_id)
        if not result.get("erased"):
            raise RuntimeError(result.get("error") or "neuro erasure reported incomplete")
