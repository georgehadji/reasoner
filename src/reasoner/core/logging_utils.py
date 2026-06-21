"""
Reasoner Pipeline - Structured Logging Utilities
Provides JSON-structured logging with correlation IDs for observability.
Includes automatic redaction of sensitive API keys and secrets.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any

# Context variables for log context across async calls
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_log_context: ContextVar[dict[str, Any]] = ContextVar("log_context", default={})


# ═══════════════════════════════════════════════════════════════════════════════
# SENSITIVE DATA REDACTION PATTERNS
# ═══════════════════════════════════════════════════════════════════════════════

# Patterns for API keys and secrets that should be redacted from logs
SENSITIVE_PATTERNS: list[tuple[re.Pattern, str]] = [
    # OpenAI API keys
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), 'sk-***REDACTED***'),
    # Anthropic API keys
    (re.compile(r'sk-ant-[a-zA-Z0-9\-]{20,}'), 'sk-ant-***REDACTED***'),
    # Google API keys
    (re.compile(r'AIza[a-zA-Z0-9_\-]{35}'), 'AIza***REDACTED***'),
    # DeepSeek API keys
    (re.compile(r'sk-[a-f0-9]{32,}'), 'sk-***REDACTED***'),
    # Perplexity API keys
    (re.compile(r'pplx-[a-zA-Z0-9]{20,}'), 'pplx-***REDACTED***'),
    # Generic Bearer tokens
    (re.compile(r'Bearer\s+[a-zA-Z0-9_\-\.]{20,}'), 'Bearer ***REDACTED***'),
    # JWT tokens
    (re.compile(r'eyJ[a-zA-Z0-9_\-]*\.eyJ[a-zA-Z0-9_\-]*\.[a-zA-Z0-9_\-]*'), 'eyJ***REDACTED***'),
    # Connection strings with passwords
    (re.compile(r'(postgres|mysql|mongodb|redis)://[^:]+:[^@]+@'), r'\1://***:***@'),
    # Generic secret patterns
    (re.compile(r'(api_key|apikey|secret|password|token|credential)["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{10,}', re.IGNORECASE), r'\1=***REDACTED***'),
]


def redact_sensitive(message: str) -> str:
    """
    Redact sensitive information from log messages.
    
    Removes API keys, tokens, passwords, and other secrets from
    log output to prevent credential leakage in logs.
    
    Args:
        message: The log message to sanitize
        
    Returns:
        Sanitized message with sensitive values replaced
    """
    if not isinstance(message, str):
        message = str(message)
    
    for pattern, replacement in SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    
    return message


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively redact sensitive values in a dictionary.
    
    Args:
        data: Dictionary to sanitize
        
    Returns:
        New dictionary with sensitive values redacted
    """
    result = {}
    sensitive_keys = {
        'api_key', 'apikey', 'key', 'secret', 'password', 'token',
        'credential', 'auth', 'authorization', 'bearer'
    }
    
    for k, v in data.items():
        key_lower = k.lower()
        
        # Check if key name suggests sensitive data
        if any(s in key_lower for s in sensitive_keys):
            result[k] = '***REDACTED***'
        elif isinstance(v, str):
            result[k] = redact_sensitive(v)
        elif isinstance(v, dict):
            result[k] = redact_dict(v)
        elif isinstance(v, list):
            result[k] = [
                redact_dict(item) if isinstance(item, dict)
                else redact_sensitive(item) if isinstance(item, str)
                else item
                for item in v
            ]
        else:
            result[k] = v
    
    return result


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogSource(str, Enum):
    API = "api"
    PIPELINE = "pipeline"
    LLM = "llm"
    PARSING = "parsing"
    PRESETS = "presets"


@dataclass
class StructuredLogEntry:
    """Structured log entry in JSON format."""
    timestamp: str
    level: str
    source: str
    message: str
    correlation_id: str
    extra: dict[str, Any] = field(default_factory=dict)
    user_id: str | None = None
    tier: str | None = None
    preset: str | None = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str)


class SafeLoggingFilter(logging.Filter):
    """Filter that redacts sensitive data from every log record.

    Install on the root logger (or any logger) so that *all* output
    — including exception messages from third-party libraries —
    is sanitized before reaching handlers.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_sensitive(record.msg)
        if record.args:
            record.args = tuple(
                redact_sensitive(arg) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True


def set_log_context(user_id: str | None = None, tier: str | None = None, preset: str | None = None) -> None:
    """Set request-scoped context for structured logging (Critical Enhancement 7.3)."""
    _log_context.set({"user_id": user_id, "tier": tier, "preset": preset})


def get_correlation_id() -> str:
    """Get current correlation ID or generate new one."""
    cid = _correlation_id.get()
    if not cid:
        cid = str(uuid.uuid4())[:8]
        _correlation_id.set(cid)
    return cid


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context."""
    _correlation_id.set(correlation_id)


class CorrelationIdFilter(logging.Filter):
    """Logging filter that injects correlation_id into every log record (O3).

    Attach to any handler so standard logging.getLogger() calls carry
    the request's run_id/correlation_id without needing StructuredLogger.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        cid = get_correlation_id()
        record.correlation_id = cid or ""
        return True


# Install filter on root logger by default (O3)
_CORRELATION_FILTER_INSTALLED = False


def _ensure_correlation_filter() -> None:
    """Install CorrelationIdFilter on the root logger once."""
    global _CORRELATION_FILTER_INSTALLED
    if not _CORRELATION_FILTER_INSTALLED:
        root = logging.getLogger()
        # Check if already installed to avoid duplicates
        already = any(isinstance(f, CorrelationIdFilter) for f in root.filters)
        if not already:
            root.addFilter(CorrelationIdFilter())
        _CORRELATION_FILTER_INSTALLED = True


# Auto-install on import
_ensure_correlation_filter()


class StructuredLogger:
    """
    Logger that outputs structured JSON logs with correlation IDs.
    """

    def __init__(self, name: str, source: LogSource = LogSource.PIPELINE):
        self.logger = logging.getLogger(name)
        self.source = source.value

    def _log(
        self,
        level: LogLevel,
        message: str,
        extra: dict[str, Any] | None = None,
        exc_info: bool = False,
    ) -> None:
        # CRITICAL: Redact sensitive information before logging
        safe_message = redact_sensitive(message)
        safe_extra = redact_dict(extra) if extra else {}

        # Pull in request-scoped context (Critical Enhancement 7.3)
        ctx = _log_context.get()

        entry = StructuredLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            level=level.value,
            source=self.source,
            message=safe_message,
            correlation_id=get_correlation_id(),
            extra=safe_extra,
            user_id=ctx.get("user_id"),
            tier=ctx.get("tier"),
            preset=ctx.get("preset"),
        )

        # Output as JSON to stdout for log aggregation
        print(entry.to_json(), file=sys.stdout)

        # Also log to standard logger for development
        std_level = getattr(logging, level.value)
        self.logger.log(std_level, safe_message, extra=entry.extra, exc_info=exc_info)

    def debug(self, message: str, **extra: Any) -> None:
        self._log(LogLevel.DEBUG, message, extra)

    def info(self, message: str, **extra: Any) -> None:
        self._log(LogLevel.INFO, message, extra)

    def warning(self, message: str, **extra: Any) -> None:
        self._log(LogLevel.WARNING, message, extra)

    def error(self, message: str, **extra: Any) -> None:
        self._log(LogLevel.ERROR, message, extra)

    def critical(self, message: str, **extra: Any) -> None:
        self._log(LogLevel.CRITICAL, message, extra)

    def exception(self, message: str, **extra: Any) -> None:
        self._log(LogLevel.ERROR, message, extra, exc_info=True)


# Pre-configured loggers for each component
api_logger = StructuredLogger("api", LogSource.API)
pipeline_logger = StructuredLogger("pipeline", LogSource.PIPELINE)
llm_logger = StructuredLogger("llm", LogSource.LLM)
parsing_logger = StructuredLogger("parsing", LogSource.PARSING)
presets_logger = StructuredLogger("presets", LogSource.PRESETS)


# Decorator for timing async functions
def timed_async(correlation_extra: dict[str, Any] | None = None):
    """Decorator to log execution time of async functions."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            logger = pipeline_logger
            func_name = func.__name__
            start_time = time.monotonic()

            logger.info(
                f"Starting {func_name}",
                extra={
                    "event": "function_start",
                    "function": func_name,
                    **(correlation_extra or {}),
                },
            )

            try:
                result = await func(*args, **kwargs)
                duration = time.monotonic() - start_time
                logger.info(
                    f"Completed {func_name}",
                    extra={
                        "event": "function_complete",
                        "function": func_name,
                        "duration_seconds": round(duration, 3),
                        **(correlation_extra or {}),
                    },
                )
                return result
            except Exception as e:
                duration = time.monotonic() - start_time
                logger.error(
                    f"Failed {func_name}",
                    extra={
                        "event": "function_error",
                        "function": func_name,
                        "duration_seconds": round(duration, 3),
                        "error": str(e),
                        "error_type": type(e).__name__,
                        **(correlation_extra or {}),
                    },
                )
                raise

        return wrapper
    return decorator


def setup_production_logging() -> None:
    """Auto-configure logging based on environment (Phase 4.2 hardening).

    Production: JSON-structured logs to stdout (consumed by log aggregators).
    Development: Human-readable format with timestamps.
    Testing: Suppress log output.
    """
    from reasoner.core.settings import settings

    env = getattr(settings, 'ENVIRONMENT', 'development')
    if env == 'production':
        configure_logging(level='INFO', json_output=True)
    elif env == 'testing':
        configure_logging(level='WARNING', json_output=False)
    else:
        configure_logging(level='DEBUG', json_output=False)


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON logs to stdout
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    if json_output:
        # Use our structured logger - just set up root logger
        logging.basicConfig(
            level=log_level,
            format="%(message)s",  # JSON output handled by StructuredLogger
            stream=sys.stdout,
        )
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )