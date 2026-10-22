"""Port: a user's run history (PER-12).

Entries are JSON documents with at least ``id``, ``user_id``, ``timestamp``,
``method`` and ``preset``. ``owner`` is the user id, or None for an anonymous
run. Every operation is scoped to one owner, so a caller can only ever reach
its own entries; there is no cross-owner listing.
"""

from __future__ import annotations

from typing import Any, Protocol


class HistoryRepository(Protocol):
    async def save(self, entry: dict[str, Any]) -> None:
        """Store ``entry`` under its own ``user_id`` and prune that owner's oldest."""

    async def list(
        self, owner: str | None, limit: int, offset: int, tag: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Newest first. ``tag`` (``method_<m>`` or ``preset_<p>``) filters before
        the page is cut. Returns (page, total matching)."""

    async def get(self, owner: str | None, entry_id: str) -> dict[str, Any] | None: ...

    async def delete(self, owner: str | None, entry_id: str) -> bool: ...

    async def erase(self, owner: str | None) -> tuple[int, int]:
        """Remove everything the owner has. Returns (removed, failed)."""
