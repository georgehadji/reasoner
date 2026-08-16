"""Direct API provider wrappers for multi-provider fallback.

Wraps the official SDKs for Anthropic, OpenAI, and Google Gemini
with the BaseLLMProvider interface. Used by ProviderRouter when
OpenRouter fails and MULTI_PROVIDER_FALLBACK_ENABLED is true.
"""

from __future__ import annotations

import logging
from typing import Any

from reasoner.core.constants import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from reasoner.core.constants_limits import TIMEOUTS
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

            from reasoner.core.settings import settings
            from reasoner.infrastructure.llm.caching import breakpoint_marker, is_cacheable

            # Anthropic only caches behind an explicit breakpoint. Below the
            # minimum cacheable prefix the marker is a documented no-op, so it
            # is only worth the structured-block payload for large prompts.
            system: Any = system_prompt
            if settings.PROMPT_CACHE_ENABLED and is_cacheable(system_prompt):
                system = [{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": breakpoint_marker(self.model),
                }]

            client = AsyncAnthropic(api_key=self._api_key, timeout=TIMEOUTS.LLM_CALL)
            response = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except ImportError as exc:
            raise LLMError("anthropic SDK not installed. pip install anthropic") from exc
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
            client = openai.AsyncOpenAI(api_key=self._api_key, timeout=TIMEOUTS.LLM_CALL)
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
            client = genai.aio.Client(api_key=self._api_key, http_options={"timeout": int(TIMEOUTS.LLM_CALL * 1000)})
            response = await client.models.generate_content(
                model=self.model,
                contents=f"{system_prompt}\n\n{user_prompt}",
                config={"max_output_tokens": max_tokens, "temperature": temperature},
            )
            return response.text or ""
        except ImportError as exc:
            raise LLMError("google-genai SDK not installed. pip install google-genai") from exc
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


class OpenAICompatibleDirectProvider(BaseLLMProvider):
    """Generic provider for OpenAI-compatible APIs (DeepSeek, Mistral, xAI, Perplexity, Qwen).

    Uses httpx to call the chat completions endpoint directly — no SDK dependency.
    """

    def __init__(self, api_key: str, model: str, base_url: str):
        super().__init__(model)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        import json
        import httpx
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(TIMEOUTS.LLM_CALL, connect=10.0)) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    content=json.dumps(payload),
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            raise LLMError(f"{self.model} direct API failed: {e}") from e

    async def stream_complete(self, *args, **kwargs) -> Any:
        raise NotImplementedError("Streaming not supported for fallback providers")


_FALLBACK_PROVIDER_REGISTRY: dict[str, type[BaseLLMProvider]] = {
    "anthropic": AnthropicDirectProvider,
    "openai": OpenAIDirectProvider,
    "google": GoogleDirectProvider,
    "mistral": OpenAICompatibleDirectProvider,
    "deepseek": OpenAICompatibleDirectProvider,
    "xai": OpenAICompatibleDirectProvider,
    "perplexity": OpenAICompatibleDirectProvider,
    "qwen": OpenAICompatibleDirectProvider,
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
        "mistral": "MISTRAL_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "xai": "XAI_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
        "qwen": "DASHSCOPE_API_KEY",
    }
    api_key = os.environ.get(key_env[name], "")

    if not api_key:
        raise LLMError(f"{name} API key not set. Set {key_env[name]} environment variable.")

    # Provider-specific config (base URL + default model) for OpenAI-compatible providers
    _provider_config = {
        "mistral": {
            "base_url": "https://api.mistral.ai/v1",
            "model": "mistral-large-latest",
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
        },
        "xai": {
            "base_url": "https://api.x.ai/v1",
            "model": "grok-2-latest",
        },
        "perplexity": {
            "base_url": "https://api.perplexity.ai",
            "model": "sonar-pro",
        },
        "qwen": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "model": "qwen-max",
        },
    }

    if cls is OpenAICompatibleDirectProvider:
        cfg = _provider_config.get(name, {})
        return cls(
            api_key=api_key,
            base_url=cfg.get("base_url", "https://api.openai.com/v1"),
            model=cfg.get("model", name),
        )

    return cls(api_key=api_key)
