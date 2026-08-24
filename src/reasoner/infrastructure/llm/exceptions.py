"""
Infrastructure Exceptions

Common exceptions used across infrastructure adapters.
"""

from __future__ import annotations


class InfrastructureError(Exception):
    """Base exception for infrastructure errors."""
    retryable = False


class LLMError(InfrastructureError):
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


class ProviderCreditsExhaustedError(LLMError):
    """API credit limit reached (HTTP 402). Not retryable — add credits and retry."""
    retryable = False


class SearchError(InfrastructureError):
    """Base exception for search errors."""
    retryable = True


class MemoryError(InfrastructureError):
    """Base exception for memory/storage errors."""
    retryable = True


def is_retryable(error: Exception) -> bool:
    """Check if an error is retryable."""
    if isinstance(error, InfrastructureError):
        return error.retryable

    # Network errors are generally retryable
    retryable_types = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    return isinstance(error, retryable_types)
