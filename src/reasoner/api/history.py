from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from reasoner.application.ports.history import HistoryRepository
from reasoner.core.settings import settings

# Unset keeps the in-package default for local dev; a deployment points it at a
# mounted volume, because the package dir is replaced on every redeploy.
HISTORY_DIR = (
    Path(settings.HISTORY_STORAGE_DIR)
    if settings.HISTORY_STORAGE_DIR
    else Path(__file__).parent.parent / "history"
)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


class HistoryEntry(BaseModel):
    id: str
    user_id: str | None = None
    problem: str
    preset: str
    method: str
    timestamp: str
    tokens: dict[str, int]
    status: str  # "completed", "error", "cancelled"


def history_repo() -> HistoryRepository:
    """The history store. Built per call from HISTORY_DIR (it holds no state),
    so a test or a deployment can repoint the directory."""
    from reasoner.infrastructure.persistence.history_files import FileHistoryRepository

    return FileHistoryRepository(HISTORY_DIR)
