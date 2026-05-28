from __future__ import annotations
from typing import Any, Optional, Protocol, Literal

SourceType = Literal["general", "academic", "social", "news", "code"]

class SearchServicePort(Protocol):
    """Port for Web Search functionality."""

    async def search(
        self,
        query: str,
        num_results: int = 10,
        categories: Optional[list[str]] = None,
        source_type: Optional[SourceType] = None,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]: ...

    async def close(self) -> None: ...
