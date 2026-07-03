"""Base LLM provider abstraction and exceptions."""

from __future__ import annotations

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from typing import AsyncIterator # Add AsyncIterator import

from reasoner.exceptions import (
    ReasonerError,
    is_retryable,
)
from reasoner.core.constants import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
)

logger = logging.getLogger(__name__)


class LLMError(ReasonerError):
    """Raised when an LLM call fails after all retries."""
    retryable = False


class BaseLLMProvider(ABC):
    def __init__(self, model: str, max_retries: int = 2) -> None:
        self.model = model
        self.max_retries = max_retries

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str: ...

    @abstractmethod
    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> AsyncIterator[str]: ...

    def supports_tools(self) -> bool:
        return False

    async def call_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> tuple[str, list[dict[str, Any]]]:
        raise NotImplementedError("This provider does not support native tool calling.")

    async def call_with_tools_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> tuple[str, list[dict[str, Any]]]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.call_with_tools(
                    system_prompt, user_prompt, tools, max_tokens, temperature
                )
            except Exception as exc:
                last_error = exc
                # Don't retry non-retryable errors
                if not is_retryable(exc):
                    raise
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 4) + random.uniform(0, 0.5))
        raise LLMError(
            f"{self.__class__.__name__}({self.model}) with tools failed "
            f"after {self.max_retries} retries: {last_error}"
        ) from last_error

    async def complete_once(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        """Single attempt — no retry. Used by the router fallback path.

        The router owns the retry budget; this is a raw single-shot wrapper
        so the fallback doesn't multiply retries (avoiding the dual-layer
        retry problem where provider-level retries + router-level fallbacks
        compound into 6+ LLM calls).
        """
        return await self.complete(system_prompt, user_prompt, max_tokens, temperature)

    async def complete_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await self.complete(
                    system_prompt, user_prompt, max_tokens, temperature
                )
            except Exception as exc:
                last_error = exc
                # Don't retry non-retryable errors
                if not is_retryable(exc):
                    raise
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 4) + random.uniform(0, 0.5))
        raise LLMError(
            f"{self.__class__.__name__}({self.model}) failed "
            f"after {self.max_retries} retries: {last_error}"
        ) from last_error

    async def stream_complete_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async for chunk in self.stream_complete(
                    system_prompt, user_prompt, max_tokens, temperature
                ):
                    yield chunk
                return # Success
            except Exception as exc:
                last_error = exc
                # Don't retry non-retryable errors
                if not is_retryable(exc):
                    raise
                if attempt < self.max_retries:
                    await asyncio.sleep(min(2 ** attempt, 4) + random.uniform(0, 0.5))
        raise LLMError(
            f"{self.__class__.__name__}({self.model}) stream failed "
            f"after {self.max_retries} retries: {last_error}"
        ) from last_error
