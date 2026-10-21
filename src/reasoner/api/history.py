from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from reasoner.application.ports.history import HistoryRepository

HISTORY_DIR = Path(__file__).parent.parent / "history"
HISTORY_DIR.mkdir(exist_ok=True)


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
