"""
No-op / Dummy LLM Provider

Fallback provider used when no API keys are configured and the system
needs a valid BaseLLMProvider instance to inject into handlers.
Always returns a canned response indicating missing configuration.
"""

from __future__ import annotations

from typing import AsyncGenerator

from reasoner.infrastructure.llm.ports import BaseLLMProvider, LLMResponse, LLMConfig, Message
from reasoner.infrastructure.llm.exceptions import LLMError


class NoopProvider(BaseLLMProvider):
    """Provider that returns a dummy response when no real provider is available.

    Used as a graceful-failure fallback in ``get_architecture_components()``
    when the model registry contains no usable models.
    """

    async def _complete_impl(
        self, messages: list[Message], config: LLMConfig
    ) -> LLMResponse:
        return LLMResponse(
            content="Dummy provider - configure API keys",
            model_used="dummy",
            tokens_prompt=0,
            tokens_completion=0,
        )

    async def _complete_stream_impl(
        self, messages: list[Message], config: LLMConfig
    ) -> AsyncGenerator[str, None]:
        yield "Dummy provider"

    @property
    def provider_name(self) -> str:
        return "noop"


class NoopProviderError(LLMError):
    """Raised when the NoopProvider is used in a critical code path."""
    pass
