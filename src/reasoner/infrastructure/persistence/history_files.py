"""File adapter of the HistoryRepository port, one directory per owner (PER-12).

Layout: ``<root>/<owner_key>/<entry id>.json``. Listing one user's history
therefore reads that user's directory and nothing else, and erasing a user is
removing a directory. Every file operation runs in a worker thread, so a slow
disk never stalls the event loop, and writes are atomic.

Until ``scripts/migrate_history_layout.py --apply`` has written the layout
marker, files in the old flat layout (``<root>/<id>.json``) are still read
and erased for their owner, so a deploy that precedes the migration does not
show empty history.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from reasoner.core.constants_limits import HISTORY_MAX_ENTRIES_PER_OWNER
from reasoner.utils.atomic_file import atomic_write_text

LAYOUT_MARKER = ".layout-v2"


def owner_key(owner: str | None) -> str:
    """Directory name for an owner: a digest, so the user id is not on disk as a name."""
    if not owner:
        return "anon"
    return "u-" + hashlib.sha256(owner.encode("utf-8")).hexdigest()[:16]


def entry_tags(entry: dict[str, Any]) -> set[str]:
    def clean(value: Any) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]", "_", value or "unknown")

    return {f"method_{clean(entry.get('method'))}", f"preset_{clean(entry.get('preset'))}"}


class FileHistoryRepository:
    def __init__(self, root: Path, max_entries: int = HISTORY_MAX_ENTRIES_PER_OWNER) -> None:
        self._root = Path(root)
        self._max = max_entries

    # ── port ────────────────────────────────────────────────────────────

    async def save(self, entry: dict[str, Any]) -> None:
        await asyncio.to_thread(self._save, entry)

    async def list(
        self, owner: str | None, limit: int, offset: int, tag: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        return await asyncio.to_thread(self._list, owner, limit, offset, tag)

    async def get(self, owner: str | None, entry_id: str) -> dict[str, Any] | None:
        found = await asyncio.to_thread(self._find, owner, entry_id)
        return found[1] if found else None

    async def delete(self, owner: str | None, entry_id: str) -> bool:
        return await asyncio.to_thread(self._delete, owner, entry_id)

    async def erase(self, owner: str | None) -> tuple[int, int]:
        return await asyncio.to_thread(self._erase, owner)

    # ── implementation (blocking; always called through to_thread) ──────

    def _dir(self, owner: str | None) -> Path:
        return self._root / owner_key(owner)

    def _files(self, owner: str | None) -> list[Path]:
        """The owner's entry files, newest first by modification time."""
        try:
            with os.scandir(self._dir(owner)) as scan:
                stamped = [(e.stat().st_mtime, e.path) for e in scan if e.name.endswith(".json")]
        except FileNotFoundError:
            return []
        stamped.sort(reverse=True)
        return [Path(p) for _, p in stamped]

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _flat_layout_active(self) -> bool:
        return not (self._root / LAYOUT_MARKER).exists()

    def _flat(self, owner: str | None) -> tuple[list[tuple[Path, dict[str, Any]]], int]:
        """Flat-layout files this owner wrote, and the count of unreadable ones."""
        if not self._flat_layout_active():
            return [], 0
        mine, unreadable = [], 0
        for path in self._root.glob("*.json"):
            data = self._read(path)
            if data is None:
                unreadable += 1
            elif (data.get("user_id") or None) == (owner or None):
                mine.append((path, data))
        return mine, unreadable

    def _save(self, entry: dict[str, Any]) -> None:
        owner = entry.get("user_id")
        folder = self._dir(owner)
        folder.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            folder / f"{Path(str(entry['id'])).name}.json",
            json.dumps(entry, ensure_ascii=False),
        )
        for stale in self._files(owner)[self._max:]:
            stale.unlink(missing_ok=True)

    def _list(
        self, owner: str | None, limit: int, offset: int, tag: str | None,
    ) -> tuple[list[dict[str, Any]], int]:
        paths = self._files(owner)
        flat, _ = self._flat(owner)
        if tag is None and not flat:
            page = (self._read(p) for p in paths[offset:offset + limit])
            return [e for e in page if e], len(paths)
        # A tag, or the old layout, needs this owner's entries parsed: at most
        # the per-owner cap, never anyone else's.
        entries = {e["id"]: e for p in paths if (e := self._read(p)) and "id" in e}
        entries.update({d["id"]: d for _, d in flat if "id" in d})
        wanted = [e for e in entries.values() if tag is None or tag in entry_tags(e)]
        wanted.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return wanted[offset:offset + limit], len(wanted)

    def _find(self, owner: str | None, entry_id: str) -> tuple[Path, dict[str, Any]] | None:
        name = f"{Path(entry_id).name}.json"
        path = self._dir(owner) / name
        data = self._read(path)
        if data is not None:
            return path, data
        if self._flat_layout_active():
            path = self._root / name
            data = self._read(path)
            if data is not None and (data.get("user_id") or None) == (owner or None):
                return path, data
        return None

    def _delete(self, owner: str | None, entry_id: str) -> bool:
        found = self._find(owner, entry_id)
        if found is None:
            return False
        found[0].unlink(missing_ok=True)
        return True

    def _erase(self, owner: str | None) -> tuple[int, int]:
        removed = failed = 0
        folder = self._dir(owner)
        flat, unreadable = self._flat(owner)
        # Everything in the owner's directory is theirs, readable or not
        # (a torn temp write included).
        targets = list(folder.iterdir()) if folder.exists() else []
        for path in [*targets, *(p for p, _ in flat)]:
            try:
                path.unlink()
                removed += 1
            except OSError:
                failed += 1
        try:
            folder.rmdir()
        except OSError:
            pass
        # An unreadable flat file cannot be attributed, so it cannot be certified erased.
        return removed, failed + unreadable
