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

    def __bool__(self) -> bool:
        """Always false: this object is a failure, and must not read as success.

        ``router.call`` returns ``tuple[str | DegradedLLMResponse, dict]``, so a
        caller cannot tell the two apart without an explicit ``isinstance``
        check. The production path does check (``LLMExecutor`` at both call
        sites, plus headless, main, HyperGate and the subagent base), but a
        dataclass instance is truthy by default, so any *new* caller written as
        ``if not response:`` silently treats a total provider failure as a
        successful reply.

        Not hypothetical: the e2e suite's
        ``test_all_presets_can_make_real_call`` does exactly that. Its
        ``assert response`` passed on a degraded object and it failed one line
        later on empty metadata, which reads like a metadata bug rather than
        the empty completion it actually was.

        Returning False makes the naive spelling correct instead of wrong.
        Explicit ``isinstance`` checks are unaffected.
        """
        return False

    @property
    def tokens_total(self) -> int:
        """Total tokens used."""
        return self.metadata.get("input_tokens", 0) + self.metadata.get("output_tokens", 0)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'content': self.text,
            'model_used': self.metadata.get("model", "unknown"),
            'tokens': {
                'prompt': self.metadata.get("input_tokens", 0),
                'completion': self.metadata.get("output_tokens", 0),
                'total': self.tokens_total,
            },
            'finish_reason': self.metadata.get("finish_reason", "error"),
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
            ProviderError: any provider failure, translated at the adapter
                boundary (see reasoner.core.exceptions).
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


# ─────────────────────────────────────────────────────────────────────
# NO EXCEPTIONS, AND NO BaseLLMProvider, LIVE HERE
# ─────────────────────────────────────────────────────────────────────
#
# This module once held a third LLMError tree (AuthenticationError,
# RateLimitError, ModelNotFoundError, ProviderTimeoutError,
# ProviderUnavailableError, is_retryable). Nothing imported any of them,
# including this module itself, so they were deleted.
#
# It also held a second BaseLLMProvider with an incompatible interface --
# complete(messages, config) -> LLMResponse, and no complete_with_retry(),
# which is the method ProviderRouter calls. Anything built on it produced a
# router that raised AttributeError on its first call, and NoopProvider plus
# two test dummies had already been built on it. Deleted in P2
# (docs/plans/root-cause-remediation-2026-09-07.md). The one base class is
# base.BaseLLMProvider; the error vocabulary is core.exceptions.
#
# What remains here is the data the router and the application layer pass
# around -- Message, LLMConfig, LLMResponse, DegradedLLMResponse, ProviderInfo
# -- plus the LLMProvider Protocol.
