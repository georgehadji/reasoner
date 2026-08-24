"""
Infrastructure - LLM Provider Ports (Hexagonal Architecture)

This module defines the interfaces (ports) that the domain layer
uses to interact with LLM providers. The domain layer knows only
about these interfaces, not the concrete implementations.

Implementations (adapters) are in separate modules:
- anthropic_adapter.py
- openai_adapter.py
- ollama_adapter.py
- etc.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from reasoner.core.constants import (
    DEFAULT_BACKOFF_BASE,
    DEFAULT_BACKOFF_DELAY,
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
)


class MessageRole(str, Enum):
    """Role of a message in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class Message:
    """
    A message in a conversation.
    
    Immutable message structure for LLM communication.
    """
    role: MessageRole
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary for API consumption."""
        return {
            'role': self.role.value,
            'content': self.content,
        }


@dataclass
class LLMResponse:
    """
    Response from an LLM provider.
    
    Contains the generated text and metadata about the call.
    """
    content: str
    model_used: str
    tokens_prompt: int = 0
    tokens_completion: int = 0
    finish_reason: str = "stop"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DegradedLLMResponse:
    """
    Placeholder response when all LLM providers fail.
    
    Carries enough metadata for downstream telemetry and UI warnings.
    """
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    degraded: bool = True
    error: str = ""

    @property
    def tokens_total(self) -> int:
        """Total tokens used."""
        return self.tokens_prompt + self.tokens_completion

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'content': self.content,
            'model_used': self.model_used,
            'tokens': {
                'prompt': self.tokens_prompt,
                'completion': self.tokens_completion,
                'total': self.tokens_total,
            },
            'finish_reason': self.finish_reason,
            'metadata': self.metadata,
        }


@dataclass
class LLMConfig:
    """
    Configuration for LLM calls.
    
    Immutable configuration that can be passed to providers.
    """
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    timeout_seconds: float | None = None
    stop_sequences: list[str] = field(default_factory=list)
    response_format: dict[str, Any] | None = None  # For structured outputs

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API consumption."""
        config = {
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'top_p': self.top_p,
            'frequency_penalty': self.frequency_penalty,
            'presence_penalty': self.presence_penalty,
        }

        if self.timeout_seconds:
            config['timeout'] = self.timeout_seconds

        if self.stop_sequences:
            config['stop'] = self.stop_sequences

        if self.response_format:
            config['response_format'] = self.response_format

        return config


class ProviderHealth(str, Enum):
    """Health status of a provider."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ProviderInfo:
    """Information about a provider."""
    name: str
    model: str
    health: ProviderHealth = ProviderHealth.UNKNOWN
    latency_ms: float = 0.0
    rate_limit_remaining: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    """
    Protocol for LLM providers (Hexagonal Architecture Port).
    
    Any class that implements this protocol can be used as an
    LLM provider, regardless of inheritance.
    
    This is the interface that the domain layer depends on.
    """

    async def complete(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """
        Complete a conversation with the LLM.
        
        Args:
            messages: List of messages in the conversation
            config: Optional configuration for the call
        
        Returns:
            LLMResponse with generated content and metadata
        
        Raises:
            LLMError: If the call fails after retries
            RateLimitError: If rate limited
            AuthenticationError: If authentication fails
        """
        ...

    async def complete_stream(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> Any:
        """
        Stream completion from the LLM.
        
        Returns an async generator that yields chunks of content.
        
        Args:
            messages: List of messages in the conversation
            config: Optional configuration for the call
        
        Yields:
            str: Chunks of generated content
        """
        ...

    def get_info(self) -> ProviderInfo:
        """Get information about this provider."""
        ...

    @property
    def model(self) -> str:
        """The model name this provider uses."""
        ...

    @property
    def provider_name(self) -> str:
        """The name of the provider (e.g., 'anthropic', 'openai')."""
        ...


class BaseLLMProvider(ABC):
    """
    Base class for LLM providers with common functionality.
    
    Provides:
    - Retry logic with exponential backoff
    - Health tracking
    - Common error handling
    
    Subclasses must implement:
    - _complete_impl(): The actual API call
    - _complete_stream_impl(): Streaming API call
    """

    def __init__(
        self,
        model: str,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay_seconds: float = DEFAULT_BACKOFF_DELAY,
    ):
        self._model = model
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self._health = ProviderHealth.UNKNOWN
        self._latency_ms = 0.0
        self._request_count = 0
        self._error_count = 0

    @abstractmethod
    async def _complete_impl(
        self,
        messages: list[Message],
        config: LLMConfig,
    ) -> LLMResponse:
        """
        Implement the actual API call.
        
        Subclasses must override this with provider-specific logic.
        """
        ...

    @abstractmethod
    async def _complete_stream_impl(
        self,
        messages: list[Message],
        config: LLMConfig,
    ) -> Any:
        """
        Implement the streaming API call.
        
        Subclasses must override this with provider-specific logic.
        """
        ...

    async def complete(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> LLMResponse:
        """
        Complete with automatic retry logic.
        """
        import asyncio
        import time

        from reasoner.infrastructure.llm.exceptions import (
            LLMError,
            RateLimitError,
            is_retryable,
        )

        config = config or LLMConfig()
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            start_time = time.perf_counter()

            try:
                response = await self._complete_impl(messages, config)

                # Update health on success
                self._health = ProviderHealth.HEALTHY
                self._latency_ms = (time.perf_counter() - start_time) * 1000
                self._request_count += 1

                return response

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                self._error_count += 1

                # Update health on error
                if isinstance(exc, RateLimitError):
                    self._health = ProviderHealth.DEGRADED
                else:
                    self._health = ProviderHealth.UNHEALTHY

                # Don't retry non-retryable errors
                if not is_retryable(exc):
                    raise

                # Don't retry if we've exhausted retries
                if attempt >= self.max_retries:
                    raise

                # Exponential backoff
                delay = self.base_delay_seconds * (DEFAULT_BACKOFF_BASE ** attempt)
                await asyncio.sleep(delay)

        raise LLMError(
            f"{self.provider_name}({self.model}) failed "
            f"after {self.max_retries + 1} attempts: {last_error}"
        ) from last_error

    async def complete_stream(
        self,
        messages: list[Message],
        config: LLMConfig | None = None,
    ) -> Any:
        """
        Stream with error handling.
        """
        config = config or LLMConfig()

        try:
            async for chunk in self._complete_stream_impl(messages, config):
                yield chunk
                self._health = ProviderHealth.HEALTHY
        except Exception:
            self._health = ProviderHealth.UNHEALTHY
            raise

    def get_info(self) -> ProviderInfo:
        """Get provider information."""
        return ProviderInfo(
            name=self.provider_name,
            model=self.model,
            health=self._health,
            latency_ms=self._latency_ms,
            metadata={
                'request_count': self._request_count,
                'error_count': self._error_count,
                'success_rate': (
                    self._request_count / (self._request_count + self._error_count)
                    if (self._request_count + self._error_count) > 0
                    else 0.0
                ),
            },
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider name (e.g., 'anthropic', 'openai')."""
        ...


# ─────────────────────────────────────────────────────────────────────
# EXCEPTIONS
# ─────────────────────────────────────────────────────────────────────

class LLMError(Exception):
    """Base exception for LLM errors."""
    retryable = False


class AuthenticationError(LLMError):
    """Authentication failed (invalid API key)."""
    retryable = False


class RateLimitError(LLMError):
    """Rate limit exceeded."""
    retryable = True


class ModelNotFoundError(LLMError):
    """Model not found."""
    retryable = False


class ProviderTimeoutError(LLMError):
    """Request timed out."""
    retryable = True


class ProviderUnavailableError(LLMError):
    """Provider service unavailable."""
    retryable = True


def is_retryable(error: Exception) -> bool:
    """Check if an error is retryable."""
    if isinstance(error, LLMError):
        return error.retryable

    # Network errors are generally retryable
    retryable_types = (
        ConnectionError,
        TimeoutError,
    )
    return isinstance(error, retryable_types)
