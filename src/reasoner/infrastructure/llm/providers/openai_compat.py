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

    # Substrings identifying models that REJECT a custom temperature (fixed at
    # 1.0 internally). Authoritative as of Jun 2026 OpenRouter capability data
    # (supported_parameters lacks "temperature"). This is a denylist: every
    # other model is assumed to accept temperature, so newly added models get
    # their tuned per-phase temperature by default instead of silently losing it.
    #
    #   OpenAI GPT-4/GPT-5/o-series + codex .... reasoning/fixed-temp
    #   anthropic claude-opus, claude-fable ..... fixed-temp premium tiers
    #   openrouter/pareto-code .................. fixed-temp router
    # Note: gpt-oss-* DOES accept temperature and is intentionally not matched.
    _FIXED_TEMPERATURE_MARKERS = (
        "gpt-4", "gpt-5",          # openai/gpt-4o-mini, all gpt-5.x (+ codex/mini/nano/pro)
        "/o1", "/o3", "/o4",       # openai o-series via OpenRouter
        "claude-opus", "claude-fable",
        "pareto-code",
    )

    def _supports_temperature(self) -> bool:
        """True when the model accepts a custom ``temperature`` parameter."""
        m = self.model.lower()
        # Direct (non-OpenRouter) OpenAI models: bare gpt-/o-series prefixes.
        if m.startswith(("gpt-", "o1", "o3", "o4")):
            return False
        return not any(marker in m for marker in self._FIXED_TEMPERATURE_MARKERS)

    def _uses_completion_tokens(self) -> bool:
        """True for direct OpenAI endpoints that require ``max_completion_tokens``."""
        return self.model.lower().startswith(("gpt-", "o1", "o3", "o4"))

    async def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
        }
        # Direct OpenAI endpoints use max_completion_tokens; everything else
        # (including OpenRouter-routed OpenAI models) accepts max_tokens.
        if self._uses_completion_tokens():
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens
        # Send temperature only to models that accept it, and only when it
        # differs from the model default (1.0) to avoid wasted tokens/errors.
        if self._supports_temperature() and temperature != 1.0:
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

    def supports_tools(self) -> bool:
        return True

    async def call_with_tools(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> tuple[str, list[dict[str, Any]]]:
        import json
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "tools": tools,
        }
        if self._uses_completion_tokens():
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens

        if self._supports_temperature() and temperature != 1.0:
            kwargs["temperature"] = temperature

        if self.extra_body:
            kwargs["extra_body"] = self.extra_body

        response = await self.client.chat.completions.create(**kwargs)
        if not response.choices:
            raise ProviderUnavailableError(
                f"Provider returned empty choices (model={self.model}; possible content filtering)"
            )

        # Track token usage when available
        usage = getattr(response, "usage", None)
        if usage is not None:
            if hasattr(self, "last_input_tokens"):
                self.last_input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            if hasattr(self, "last_output_tokens"):
                self.last_output_tokens = getattr(usage, "completion_tokens", 0) or 0

        message = response.choices[0].message
        content = message.content or ""
        tool_calls_out = []
        if message.tool_calls:
            for tc in message.tool_calls:
                args = {}
                try:
                    if tc.function.arguments:
                        args = json.loads(tc.function.arguments)
                except Exception:
                    pass
                tool_calls_out.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args,
                })

        return content, tool_calls_out


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
