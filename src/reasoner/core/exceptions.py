"""
Reasoner Pipeline - Exception Taxonomy
Structured exception hierarchy for better error handling.

This module provides a comprehensive exception hierarchy for the Reasoner Pipeline,
enabling precise error handling and appropriate retry strategies.

Exception Hierarchy:
    ReasonerError (base)
    ├── ParseError
    │   ├── JSONExtractionError
    │   └── JSONValidationError
    ├── ProviderError
    │   ├── AuthenticationError
    │   ├── RateLimitError
    │   ├── ModelNotFoundError
    │   ├── ProviderTimeoutError
    │   └── ProviderUnavailableError
    └── PipelineError
        ├── PhaseError
        └── ConfigurationError

Usage:
    try:
        result = await provider.complete(...)
    except AuthenticationError:
        # Don't retry - API key is invalid
        log_error("Invalid API key")
    except RateLimitError as e:
        # Retry after specified delay
        await asyncio.sleep(e.retry_after)
    except ProviderError as e:
        # Retry with exponential backoff
        if is_retryable(e):
            await retry_with_backoff()
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """Structured error codes for SSE events and API responses (WI-12).

    Each code maps to a distinct failure mode for programmatic handling.
    """
    # Authentication / Authorization
    AUTH_INVALID_KEY = "AUTH_INVALID_KEY"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    AUTH_INSUFFICIENT_SCOPE = "AUTH_INSUFFICIENT_SCOPE"

    # Provider / Model
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"
    ALL_FALLBACKS_EXHAUSTED = "ALL_FALLBACKS_EXHAUSTED"

    # Pipeline / Phase
    PIPELINE_TIMEOUT = "PIPELINE_TIMEOUT"
    PHASE_FAILED = "PHASE_FAILED"
    PARSE_ERROR = "PARSE_ERROR"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"

    # Input
    INVALID_INPUT = "INVALID_INPUT"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"

    # General
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN = "UNKNOWN"


class ReasonerError(Exception):
    """
    Base exception for all Reasoner pipeline errors.
    
    Attributes:
        message (str): Human-readable error message
        details (dict): Additional error context
        retryable (bool): Whether the error is retryable
    """
    retryable: bool = False
    
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


# ─────────────────────────────────────────────────────────────────────
# PARSE ERRORS
# ─────────────────────────────────────────────────────────────────────

class ParseError(ReasonerError):
    """Raised when LLM response cannot be parsed into expected structure."""
    retryable = False


class JSONExtractionError(ParseError):
    """Failed to extract JSON from LLM response."""
    pass


class JSONValidationError(ParseError):
    """JSON extracted but doesn't match expected schema."""
    pass


# ─────────────────────────────────────────────────────────────────────
# PROVIDER ERRORS
# ─────────────────────────────────────────────────────────────────────

class ProviderError(ReasonerError):
    """Base exception for LLM provider errors."""
    pass


class AuthenticationError(ProviderError):
    """
    Invalid or missing API key.
    
    This error is NOT retryable - retrying will not help.
    The user must update their API key configuration.
    """
    retryable = False
    
    def __init__(self, message: str, provider: str | None = None):
        super().__init__(message, {"provider": provider})


class RateLimitError(ProviderError):
    """
    Rate limit exceeded.
    
    This error IS retryable after the specified delay.
    
    Attributes:
        retry_after (int | None): Seconds to wait before retrying
    """
    retryable = True
    
    def __init__(self, message: str, provider: str | None = None, retry_after: int | None = None):
        super().__init__(message, {"provider": provider, "retry_after": retry_after})


class ModelNotFoundError(ProviderError):
    """
    Requested model doesn't exist.
    
    This error is NOT retryable - the model ID is invalid.
    """
    retryable = False
    
    def __init__(self, message: str, model: str | None = None):
        super().__init__(message, {"model": model})


class ProviderTimeoutError(ProviderError):
    """
    Provider request timed out.
    
    This error IS retryable - the provider may be temporarily unavailable.
    """
    retryable = True


class ProviderUnavailableError(ProviderError):
    """
    Provider service is unavailable.
    
    This error IS retryable - may be a temporary outage.
    """
    retryable = True


# ─────────────────────────────────────────────────────────────────────
# PIPELINE ERRORS
# ─────────────────────────────────────────────────────────────────────

class PipelineError(ReasonerError):
    """Base exception for pipeline execution errors."""
    pass


class PhaseError(PipelineError):
    """
    Error during a specific pipeline phase.
    
    Attributes:
        phase (int): Phase number where error occurred
        phase_name (str): Human-readable phase name
    """
    def __init__(self, message: str, phase: int, phase_name: str):
        super().__init__(message, {"phase": phase, "phase_name": phase_name})
        self.phase = phase
        self.phase_name = phase_name


class ConfigurationError(ReasonerError):
    """
    Invalid pipeline configuration.

    This error is NOT retryable - configuration must be fixed.
    """
    retryable = False


class EventStoreCorruptionError(PipelineError):
    """Raised when event store data is inconsistent (e.g. version gaps after compaction)."""
    retryable = False


# ─────────────────────────────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────────────────────────────

def is_retryable(error: Exception) -> bool:
    """
    Check if an error is retryable.

    Args:
        error: Exception to check

    Returns:
        bool: True if the error should be retried

    Examples:
        >>> is_retryable(AuthenticationError("Invalid key"))
        False
        >>> is_retryable(RateLimitError("Rate limit"))
        True
        >>> is_retryable(ValueError("Unknown error"))
        False
    """
    if isinstance(error, ReasonerError):
        return error.retryable

    # OpenAI SDK / HTTP client errors with transient status codes
    status_code = getattr(error, 'status_code', None)
    if isinstance(status_code, int):
        # 429 = rate limit, 500/502/503/504 = server-side transient
        if status_code in (429, 500, 502, 503, 504):
            return True
        # 401/403/404 are not retryable
        return False

    # Network-level errors (e.g. "fetch failed", connection reset, etc.)
    msg = str(getattr(error, 'message', '')) or str(error)
    if 'fetch failed' in msg.lower():
        return True

    # Unknown errors are not retryable by default
    return False


def error_code_for_exception(error: Exception) -> str:
    """Map an exception to its canonical ErrorCode string (WI-12).

    Returns the ErrorCode value, falling back to ErrorCode.UNKNOWN.
    """
    if isinstance(error, AuthenticationError):
        return ErrorCode.AUTH_INVALID_KEY.value
    elif isinstance(error, RateLimitError):
        return ErrorCode.RATE_LIMIT_EXCEEDED.value
    elif isinstance(error, ModelNotFoundError):
        return ErrorCode.MODEL_NOT_FOUND.value
    elif isinstance(error, ProviderTimeoutError):
        return ErrorCode.PROVIDER_TIMEOUT.value
    elif isinstance(error, ProviderUnavailableError):
        return ErrorCode.PROVIDER_UNAVAILABLE.value
    elif isinstance(error, ParseError):
        return ErrorCode.PARSE_ERROR.value
    elif isinstance(error, PipelineError):
        return ErrorCode.PHASE_FAILED.value
    error_name = type(error).__name__
    if error_name in ("AuthenticationError", "PermissionDeniedError"):
        return ErrorCode.AUTH_INVALID_KEY.value
    if error_name == "RateLimitError":
        return ErrorCode.RATE_LIMIT_EXCEEDED.value
    if "timeout" in error_name.lower():
        return ErrorCode.PROVIDER_TIMEOUT.value
    return ErrorCode.UNKNOWN.value


def classify_error(error: Exception) -> str:
    """
    Classify error type for logging/monitoring.
    
    Args:
        error: Exception to classify
        
    Returns:
        str: Error category for monitoring
        
    Categories:
        - auth: Authentication/authorization errors
        - rate_limit: Rate limiting errors
        - model_not_found: Invalid model ID
        - timeout: Request timeouts
        - unavailable: Service unavailable
        - parse: JSON parsing errors
        - pipeline: Pipeline execution errors
        - unknown: Unclassified errors
    """
    if isinstance(error, AuthenticationError):
        return "auth"
    elif isinstance(error, RateLimitError):
        return "rate_limit"
    elif isinstance(error, ModelNotFoundError):
        return "model_not_found"
    elif isinstance(error, ProviderTimeoutError):
        return "timeout"
    elif isinstance(error, ProviderUnavailableError):
        return "unavailable"
    elif isinstance(error, ParseError):
        return "parse"
    elif isinstance(error, PipelineError):
        return "pipeline"
    # Recognize common third-party provider errors even when not wrapped
    error_name = type(error).__name__
    if error_name in ("AuthenticationError", "PermissionDeniedError"):
        return "auth"
    if error_name == "RateLimitError":
        return "rate_limit"
    if error_name in ("NotFoundError", "BadRequestError"):
        return "model_not_found"
    if error_name in ("APITimeoutError", "TimeoutError"):
        return "timeout"
    if error_name in ("APIConnectionError", "InternalServerError", "APIError"):
        return "unavailable"
    return "unknown"
