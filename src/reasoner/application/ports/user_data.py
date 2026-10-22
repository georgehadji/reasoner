"""Port: one place a user's data lives (DAT-10, DAT-11).

A store knows how to export and erase its own data. Export and both erase
routes iterate the same ordered sequence of stores, so a store cannot be
erasable but not exportable, or erased by one route and skipped by another.
"""

from __future__ import annotations

from typing import Any, Protocol


class UserDataStore(Protocol):
    name: str
    """Stable key in export documents and erasure receipts."""

    async def export(self, user_id: str) -> Any:
        """The user's data in this store: JSON-serialisable, or None when the
        store holds nothing exportable. Raises on failure."""

    async def erase(self, user_id: str) -> None:
        """Remove the user's data from this store. Raises on failure, so a
        partial erase can never be reported as complete."""
