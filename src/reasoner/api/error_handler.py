"""
Global Exception Handlers for FastAPI

Captures all unhandled exceptions, HTTP errors, and validation failures
with full request context. Persists to ErrorStore and reports to Sentry.
Ensures no user-facing error goes unlogged in production.
"""

from __future__ import annotations

import logging
import traceback as tb
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from reasoner.logging_utils import get_correlation_id

logger = logging.getLogger(__name__)

# Lazy import to avoid circular deps
_error_store = None


def _get_error_store():
    """Lazy initialization of error store."""
    global _error_store
    if _error_store is None:
        from reasoner.infrastructure.persistence.error_store import ErrorStore
        _error_store = ErrorStore()
    return _error_store


def _extract_user_id(request: Request) -> str | None:
    """Extract user ID from request state if available."""
    user = getattr(request.state, "user", None)
    if user is not None:
        return str(getattr(user, "id", user))
    # Try to extract from auth header for logging purposes
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        # Don't decode JWT here, just note it's present
        return None
    return None


def _log_error(
    level: str,
    source: str,
    message: str,
    request: Request | None = None,
    status_code: int | None = None,
    traceback: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Log an error to structured logger and ErrorStore."""
    correlation_id = get_correlation_id()
    user_id = _extract_user_id(request) if request else None
    path = request.url.path if request else None
    method = request.method if request else None

    # Structured logging
    logger.error(
        "[%s] %s %s | %s | user=%s | corr=%s | %s",
        level.upper(),
        method or "-",
        path or "-",
        source,
        user_id or "anon",
        correlation_id,
        message,
        extra={
            "correlation_id": correlation_id,
            "source": source,
            "level": level,
            "path": path,
            "method": method,
            "status_code": status_code,
            "user_id": user_id,
            **(extra or {}),
        },
    )

    # Persist to ErrorStore (fire and forget, don't block response)
    try:
        import asyncio
        from reasoner.infrastructure.persistence.error_store import ErrorEntry

        store = _get_error_store()
        entry = ErrorEntry(
            level=level,
            source=source,
            message=message,
            correlation_id=correlation_id,
            user_id=user_id,
            path=path,
            method=method,
            status_code=status_code,
            traceback=traceback,
            extra=extra,
        )
        # Schedule async insert without awaiting
        asyncio.create_task(store.insert(entry))
    except Exception as store_exc:
        logger.warning("Failed to persist error to ErrorStore: %s", store_exc)

    # Report to Sentry if available
    try:
        import sentry_sdk
        if sentry_sdk.Hub.current.client is not None:
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("correlation_id", correlation_id)
                scope.set_tag("source", source)
                if path:
                    scope.set_tag("path", path)
                if user_id:
                    scope.set_user({"id": user_id})
                if extra:
                    for key, value in extra.items():
                        scope.set_extra(key, value)
                sentry_sdk.capture_message(message, level=level)
    except Exception:
        pass


def _safe_json_response(
    status_code: int,
    detail: str,
    correlation_id: str,
    request: Request | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Build a safe JSON error response that doesn't leak internals."""
    from reasoner.core.settings import settings
    env = getattr(settings, "ENVIRONMENT", "development")

    body: dict[str, Any] = {
        "error": detail,
        "status_code": status_code,
        "correlation_id": correlation_id,
    }

    if env != "production" and request is not None:
        body["path"] = request.url.path
        body["method"] = request.method

    # In development, include extra detail (validation errors, etc.)
    if env != "production" and extra:
        body["detail"] = extra

    return JSONResponse(status_code=status_code, content=body)


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTPException (4xx, 5xx from FastAPI/Starlette)."""
    # Don't log 401/403 as errors — they're expected auth failures
    level = "warning" if exc.status_code < 500 else "error"
    source = "api"

    # Skip logging for routine auth failures and rate limits
    if exc.status_code in (401, 403, 429):
        return _safe_json_response(exc.status_code, str(exc.detail), get_correlation_id(), request)

    _log_error(
        level=level,
        source=source,
        message=str(exc.detail),
        request=request,
        status_code=exc.status_code,
        extra={"headers": dict(request.headers) if level == "error" else None},
    )

    return _safe_json_response(exc.status_code, str(exc.detail), get_correlation_id(), request)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle RequestValidationError (malformed JSON, missing fields)."""
    errors = exc.errors()
    simplified = [
        {"loc": e.get("loc", []), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in errors[:5]  # Limit to first 5 errors
    ]

    _log_error(
        level="warning",
        source="api",
        message=f"Request validation failed: {len(errors)} errors",
        request=request,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        extra={"validation_errors": simplified},
    )

    return _safe_json_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "Request validation failed",
        get_correlation_id(),
        request,
        extra={"validation_errors": simplified},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions (500s)."""
    traceback_str = tb.format_exc()
    exc_type = type(exc).__name__

    _log_error(
        level="error",
        source="api",
        message=f"Unhandled {exc_type}: {str(exc)}",
        request=request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        traceback=traceback_str,
        extra={"exception_type": exc_type},
    )

    # Report to Sentry as exception (not just message)
    try:
        import sentry_sdk
        if sentry_sdk.Hub.current.client is not None:
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass

    return _safe_json_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "An internal server error occurred. Our team has been notified.",
        get_correlation_id(),
        request,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════════

def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    logger.info("Global exception handlers registered")
