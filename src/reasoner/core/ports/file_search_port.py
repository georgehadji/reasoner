"""Port for semantic search over uploaded file chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class FileChunk:
    file_id: str
    content: str
    score: float


class FileSearchPort(Protocol):
    async def search_chunks(
        self,
        file_ids: list[str],
        query: str,
        top_k: int = 5,
    ) -> list[FileChunk]: ...
