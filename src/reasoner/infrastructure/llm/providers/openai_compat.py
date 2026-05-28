"""OpenAI-compatible provider implementations (OpenAI, xAI, DeepSeek, Qwen, etc.)."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Any

import openai

from reasoner.exceptions import ProviderUnavailableError
from reasoner.core.constants import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    OPENROUTER_BASE_URL as _OPENROUTER_BASE_URL,
    MODEL_GEMINI_PRO,
    MODEL_GEMINI_FLASH,
    TIMEOUTS,
)
from reasoner.infrastructure.llm.base import BaseLLMProvider
from reasoner.infrastructure.llm.utils import _perplexity_response_format

logger = logging.getLogger(__name__)


class OpenAICompatibleProvider(BaseLLMProvider):
    # Shared connection pool (httpx client) across all instances for performance
    _shared_pool: "httpx.AsyncClient | None" = None
    _pool_lock: "asyncio.Lock | None" = None
    _pool_init_lock: threading.Lock | None = None
    _pool_closed: bool = False

    @classmethod
    async def close_shared_pool(cls) -> None:
        """
        Close the shared HTTP connection pool.
        Should be called during application shutdown to prevent resource leaks.
        Thread-safe: uses lock to prevent concurrent close attempts.
        """
        if cls._pool_lock is None:
            cls._pool_lock = asyncio.Lock()

        async with cls._pool_lock:
            if cls._pool_closed:
                return  # Already closed
            if cls._shared_pool is not None:
                try:
                    await cls._shared_pool.aclose()
                    logger.info("Shared HTTP connection pool closed successfully")
                except Exception as e:
                    logger.error(f"Error closing shared HTTP pool: {e}")
                finally:
                    cls._shared_pool = None
            cls._pool_closed = True
            # Don't reset _pool_lock - keep it for potential future use

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        extra_body: dict[str, Any] | None = None,
        http_client: "openai.AsyncOpenAI | None" = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(model, max_retries)
        self.extra_body = extra_body or {}

        # If a pre-configured OpenAI client is provided, use it directly
        if http_client is not None:
            self.client = http_client
            return

        # Initialize the shared pool if it doesn't exist (thread-safe)
        if OpenAICompatibleProvider._pool_init_lock is None:
            OpenAICompatibleProvider._pool_init_lock = threading.Lock()
        with OpenAICompatibleProvider._pool_init_lock:
            if OpenAICompatibleProvider._shared_pool is None:
                # Reset closed flag if we're recreating the pool
                OpenAICompatibleProvider._pool_closed = False
                try:
                    import httpx
                    # Create HTTP client with connection pooling
                    OpenAICompatibleProvider._shared_pool = httpx.AsyncClient(
                        limits=httpx.Limits(
                            max_keepalive_connections=20,
                            max_connections=100,
                            keepalive_expiry=120.0,
                        ),
                        timeout=httpx.Timeout(TIMEOUTS.HTTP_TOTAL, connect=TIMEOUTS.HTTP_CONNECT),
                    )
                except ImportError:
                    # Fallback: if httpx is not available, AsyncOpenAI will create its own pool
                    pass

        # Create a dedicated OpenAI wrapper for this specific key/URL,
        # but share the underlying connection pool.
        client_kwargs: dict[str, Any] = {
            "api_key": (api_key or "missing").strip(),
            "base_url": base_url,
            "http_client": OpenAICompatibleProvider._shared_pool,
        }
        if default_headers:
            client_kwargs["default_headers"] = default_headers
        self.client = openai.AsyncOpenAI(**client_kwargs)

    async def stream_complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> AsyncIterator[str]:
        # Simple stream implementation wrapping the underlying client
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "stream": True,
        }
        if temperature != 1.0:
            kwargs["temperature"] = temperature
        
        async with self.client.chat.completions.create(**kwargs) as response:
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    # Models that support custom temperature values (0.0-2.0 range).
    # Note: OpenAI models (gpt-*, o1, o3) do NOT accept temperature parameters - they use temperature=1.0 fixed.
    _TEMPERATURE_SUPPORTED_MODELS = frozenset({
        # Kimi
        'kimi-k2-5', 'kimi-k2-6',
        # GLM/ZhipuAI
        'glm-5', 'glm-4-plus', 'glm-4-air', 'glm-4',
        # MiniMax
        'minimax-01', 'minimax-text', 'minimax-m2.5', 'minimax-m2.5-free', 'minimax-m2.7', 'minimax-m1',
        # Mistral
        'mistral-large-latest', 'mistral-medium', 'mistral-small', 'codestral', 'codestral-2508',
        'devstral', 'devstral-medium', 'devstral-small',
        # Google Gemini
        'gemini-2.0-pro-exp', 'gemini-2.0-flash-exp', MODEL_GEMINI_PRO, MODEL_GEMINI_FLASH,
        # xAI Grok
        'grok-4', 'grok-4.3', 'grok-3', 'grok-3-mini', 'grok-beta',
        # Perplexity (search-grounded, temperature has limited effect)
        'sonar-pro', 'sonar', 'sonar-deep-research',
        # Xiaomi
        'mimo-v2-pro', 'mimo-v2-flash', 'mimo-v2-omni',
        # inclusionAI
        'ling-2.6',
        # NVIDIA
        'nemotron',
        # DeepSeek
        'deepseek-v3', 'deepseek-v3.1', 'deepseek-r1', 'deepseek-r1t2', 'deepseek-v4', 'deepseek-v4-flash',
        # Qwen
        'qwen3', 'qwen3-coder', 'qwen3-coder-next', 'qwen3-coder-flash',
        # Tencent
        'hy3',
        # OpenRouter
        'owl-alpha', 'pareto-code',
    })

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        # Determine which parameter name to use based on model
        if self.model.startswith(('gpt-', 'o3', 'o1')):
            # OpenAI models (GPT, O1, O3) do NOT accept temperature parameters.
            # They use a fixed temperature=1.0 internally.
            # Sending any temperature value will cause an error.
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_completion_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            }
            # DO NOT send temperature - OpenAI models don't accept it
        elif self.model.startswith(('claude-',)):
            # Anthropic models via OpenAI-compatible endpoint
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            }
            # Anthropic Claude models support temperature (0.0-1.0)
            # Only send if not default to avoid "unsupported value" errors
            if temperature != 1.0:
                kwargs["temperature"] = temperature
        else:
            # Other models: check if temperature is supported
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
            }
            # Only send temperature for models known to support it
            # This prevents "unsupported value" errors for models that only accept default temperature
            if any(supported in self.model.lower() for supported in self._TEMPERATURE_SUPPORTED_MODELS):
                if temperature != 1.0:  # Omit default to reduce token usage and avoid errors
                    kwargs["temperature"] = temperature

        if self.extra_body:
            kwargs["extra_body"] = self.extra_body
        response_format = _perplexity_response_format(self.model, system_prompt, user_prompt)
        if response_format is not None:
            kwargs["response_format"] = response_format

        try:
            response = await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            # Safe fallback: if Perplexity rejects the structured output envelope, retry once
            # without response_format instead of failing the whole phase.
            if response_format is not None:
                message = str(exc).lower()
                if (
                    getattr(exc, "status_code", None) == 400
                    or "response_format" in message
                    or "json_schema" in message
                ):
                    logger.warning(
                        "Structured outputs rejected by model '%s' — retrying without response_format",
                        self.model,
                    )
                    kwargs.pop("response_format", None)
                    response = await self.client.chat.completions.create(**kwargs)
                else:
                    raise
            else:
                raise
        if not response.choices:
            raise ProviderUnavailableError(
                f"Provider returned empty choices (model={self.model}; possible content filtering)"
            )
        # Track token usage when available (OpenRouter, OpenAI, etc.)
        usage = getattr(response, "usage", None)
        if usage is not None:
            if hasattr(self, "last_input_tokens"):
                self.last_input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            if hasattr(self, "last_output_tokens"):
                self.last_output_tokens = getattr(usage, "completion_tokens", 0) or 0
            # Cost is not consistently available in the SDK response object;
            # leave last_cost_usd untouched so callers can estimate via pricing.py.
        return response.choices[0].message.content or ""


class OpenRouterProvider(OpenAICompatibleProvider):
    """
    OpenRouter provider — unified access to 346+ models through single API key.
    https://openrouter.ai/docs

    OpenRouter's API is OpenAI-compatible, so we extend OpenAICompatibleProvider
    with OpenRouter-specific base URL and optional features.

    Includes cost tracking based on actual token usage.
    """

    OPENROUTER_BASE_URL = _OPENROUTER_BASE_URL

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        # OpenRouter requires identification headers for every request.
        from reasoner.core.settings import settings
        default_headers: dict[str, str] = {}
        if settings.OPENROUTER_HTTP_REFERER:
            default_headers["HTTP-Referer"] = settings.OPENROUTER_HTTP_REFERER
        if settings.OPENROUTER_APP_TITLE:
            default_headers["X-Title"] = settings.OPENROUTER_APP_TITLE

        super().__init__(
            model=model,
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY", ""),
            base_url=self.OPENROUTER_BASE_URL,
            max_retries=max_retries,
            extra_body=extra_body,
            default_headers=default_headers,
        )
        # Cost tracking
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0
        self.last_cost_usd: float = 0.0
