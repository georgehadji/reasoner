"""
No-op / Dummy LLM Provider

Fallback provider used when no API keys are configured and the system
needs a valid BaseLLMProvider instance to inject into handlers.
Always returns a canned response indicating missing configuration.

Base class matters here. There are two unrelated ``BaseLLMProvider``
classes in this package with incompatible interfaces:

    base.BaseLLMProvider   complete(system_prompt, user_prompt, ...) -> str
    ports.BaseLLMProvider  complete(messages, config) -> LLMResponse

``ProviderRouter`` calls ``complete_with_retry``, which only the ``base``
one has. This module used to subclass the ``ports`` one, so the no-API-key
path in ``api/__init__.py`` built a router that raised
``AttributeError: 'NoopProvider' object has no attribute
'complete_with_retry'`` on the first call, instead of returning the canned
message it exists to return.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from reasoner.infrastructure.llm.base import BaseLLMProvider, LLMError

_MESSAGE = "Dummy provider - configure API keys"


class NoopProvider(BaseLLMProvider):
    """Provider that returns a dummy response when no real provider is available.

    Used as a graceful-failure fallback in ``get_architecture_components()``
    and in ``api/__init__.py`` when the model registry contains no usable
    models.
    """

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        return _MESSAGE

    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> AsyncIterator[str]:
        yield _MESSAGE

    @property
    def provider_name(self) -> str:
        return "noop"


class NoopProviderError(LLMError):
    """Raised when the NoopProvider is used in a critical code path."""
    pass
