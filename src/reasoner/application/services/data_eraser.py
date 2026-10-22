"""GDPR export and erasure over one ordered registry of stores (DAT-10, DAT-11).

``UserDataEraser`` and ``UserDataExporter`` iterate the same sequence of
``UserDataStore`` strategies. Which stores exist, and in what order, is decided
once, in ``api/user_data.py``; neither class knows about any particular store.

Erasure is best-effort per store but never silent: a store that raises is
recorded in the receipt, the rest still run, and the receipt is only
"completed" when every store succeeded. Export is all-or-nothing: a store that
fails fails the export, because a shorter document would look complete.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from reasoner.application.ports.user_data import UserDataStore
from reasoner.core.degrade import degraded
from reasoner.core.exceptions import UserDataExportError

logger = logging.getLogger(__name__)


class UserDataEraser:
    """Erase a user from every store, in registry order."""

    def __init__(self, stores: Sequence[UserDataStore]) -> None:
        self._stores = list(stores)

    async def erase(self, user_id: str) -> dict[str, Any]:
        """Returns ``{status, erased: [names], failed: [{store, error}], timestamp}``.

        ``status`` is "completed" only when no store failed; otherwise "partial".
        """
        erased: list[str] = []
        failed: list[dict[str, str]] = []
        for store in self._stores:
            try:
                await store.erase(str(user_id))
                erased.append(store.name)
            except Exception as exc:
                degraded(f"user_data.erase.{store.name}", None, exc=exc)
                failed.append({"store": store.name, "error": str(exc) or type(exc).__name__})
        receipt = {
            "status": "partial" if failed else "completed",
            "erased": erased,
            "failed": failed,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        logger.info("GDPR erasure receipt for user %s: %s", user_id, receipt)
        return receipt


class UserDataExporter:
    """Export a user's data from every store, keyed by store name."""

    def __init__(self, stores: Sequence[UserDataStore]) -> None:
        self._stores = list(stores)

    async def export(self, user_id: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        failed: list[str] = []
        for store in self._stores:
            try:
                out[store.name] = await store.export(str(user_id))
            except Exception as exc:
                degraded(f"user_data.export.{store.name}", None, exc=exc)
                failed.append(store.name)
        if failed:
            raise UserDataExportError(
                f"export incomplete: {', '.join(failed)}", {"stores": failed}
            )
        return out
