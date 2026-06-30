"""Direct API provider wrappers for multi-provider fallback.

Wraps the official SDKs for Anthropic, OpenAI, and Google Gemini
with the BaseLLMProvider interface. Used by ProviderRouter when
OpenRouter fails and MULTI_PROVIDER_FALLBACK_ENABLED is true.
"""

from __future__ import annotations

import logging
from typing import Any

from reasoner.core.constants import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from reasoner.infrastructure.llm.base import BaseLLMProvider, LLMError

logger = logging.getLogger(__name__)


class AnthropicDirectProvider(BaseLLMProvider):
    """Direct Anthropic API provider (uses anthropic SDK)."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-5"):
        super().__init__(model)
        self._api_key = api_key

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        try:
            from anthropic import AsyncAnthropic
            client = AsyncAnthropic(api_key=self._api_key)
            response = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except ImportError:
            raise LLMError("anthropic SDK not installed. pip install anthropic")
        except Exception as e:
            raise LLMError(f"Anthropic direct API failed: {e}") from e

    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> Any:  # AsyncIterator[str]
        raise NotImplementedError("Streaming not supported for fallback providers")


class OpenAIDirectProvider(BaseLLMProvider):
    """Direct OpenAI API provider (uses openai SDK, not via OpenRouter)."""

    def __init__(self, api_key: str | None = None, model: str = "gpt-5.5"):
        super().__init__(model)
        self._api_key = api_key

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        try:
            import openai
            client = openai.AsyncOpenAI(api_key=self._api_key)
            response = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(f"OpenAI direct API failed: {e}") from e

    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> Any:
        raise NotImplementedError("Streaming not supported for fallback providers")


class GoogleDirectProvider(BaseLLMProvider):
    """Direct Google Gemini API provider (uses google-genai SDK)."""

    def __init__(self, api_key: str | None = None, model: str = "gemini-3.5-flash"):
        super().__init__(model)
        self._api_key = api_key

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        try:
            import google.genai as genai
            client = genai.aio.Client(api_key=self._api_key)
            response = await client.models.generate_content(
                model=self.model,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config={"max_output_tokens": max_tokens, "temperature": temperature},
            )
            return response.text or ""
        except ImportError:
            raise LLMError("google-genai SDK not installed. pip install google-genai")
        except Exception as e:
            raise LLMError(f"Google direct API failed: {e}") from e

    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> Any:
        raise NotImplementedError("Streaming not supported for fallback providers")


_FALLBACK_PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "anthropic": AnthropicDirectProvider,
    "openai": OpenAIDirectProvider,
    "google": GoogleDirectProvider,
}


def build_fallback_provider(name: str) -> BaseLLMProvider:
    """Build a fallback provider by name."""
    import os

    cls = _FALLBACK_PROVIDER_REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown fallback provider: {name}. Options: {list(_FALLBACK_PROVIDER_REGISTRY.keys())}")

    # Map provider name → env var for API key
    key_env = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
    }
    api_key = os.environ.get(key_env[name], "")

    if not api_key:
        raise LLMError(f"{name} API key not set. Set {key_env[name]} environment variable.")

    return cls(api_key=api_key)
