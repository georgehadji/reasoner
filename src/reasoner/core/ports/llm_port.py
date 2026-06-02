"""Port interface for LLM access — ProviderRouter implements this."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMPort(Protocol):
    """Port for LLM communication.

    Implemented by ProviderRouter. The application layer depends on this port,
    not on the concrete ProviderRouter class.
    """

    async def call(
        self,
        role: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = ...,
        temperature: float = ...,
        timeout_seconds: float | None = ...,
        stream: bool = False,
    ) -> tuple[str, dict[str, Any]]: ...

    def get(self, role: str) -> Any: ...
