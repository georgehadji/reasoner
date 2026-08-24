"""Search service port interface — implemented by search adapters in infrastructure/.

Moved from infrastructure/search/port.py to eliminate core -> infrastructure dependency.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

SourceType = Literal["general", "academic", "social", "news", "code"]


class SearchServicePort(Protocol):
    """Port for Web Search functionality."""

    async def search(
        self,
        query: str,
        num_results: int = 10,
        categories: list[str] | None = None,
        source_type: SourceType | None = None,
        domain: str | None = None,
    ) -> list[dict[str, Any]]: ...

    async def close(self) -> None: ...
