"""FastAPI middleware classes for security, memory limits, and request timeouts."""

from __future__ import annotations

import asyncio
import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class _BodyTooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    """Refuse a request body over its limit before the app has read it.

    Pure ASGI rather than BaseHTTPMiddleware: it must see ``receive`` itself.
    A declared Content-Length over the limit is refused up front. A chunked
    or understated body is counted as it arrives; at the limit the 413 is
    sent and the app's own reply is dropped, because a route that catches
    every exception (the upload route does) would otherwise answer instead.
    ``per_path`` maps a path prefix to its limit; the longest prefix wins.
    """

    def __init__(self, app, default_limit: int, per_path: dict[str, int] | None = None):
        self.app = app
        self.default_limit = default_limit
        self.per_path = sorted((per_path or {}).items(), key=lambda kv: -len(kv[0]))

    @staticmethod
    def app_limits() -> dict:
        """The app's caps. Upload matches the route's own Content-Length check;
        data-URL routes carry base64 images of up to one upload's size (four
        reference images for generation)."""
        from reasoner.core.constants import (
            MAX_DATA_URL_CHARS,
            REQUEST_BODY_MAX_BYTES,
            UPLOAD_MAX_FILE_BYTES,
        )
        from reasoner.core.settings import settings

        return {
            "default_limit": REQUEST_BODY_MAX_BYTES,
            "per_path": {
                "/api/upload": UPLOAD_MAX_FILE_BYTES * settings.UPLOAD_MAX_FILES + 2**20,
                "/api/provenance/": MAX_DATA_URL_CHARS + REQUEST_BODY_MAX_BYTES,
                "/api/generate-image": 4 * MAX_DATA_URL_CHARS + REQUEST_BODY_MAX_BYTES,
            },
        }

    def _limit(self, path: str) -> int:
        matches = (n for prefix, n in self.per_path if path.startswith(prefix))
        return next(matches, self.default_limit)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope["path"])
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            await _too_large(scope, receive, send, limit)
            return

        received = 0
        rejected = False

        async def counted_receive():
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit and not rejected:
                    rejected = True
                    await _too_large(scope, receive, send, limit)
                    raise _BodyTooLargeError
            return message

        async def guarded_send(message):
            if not rejected:
                await send(message)

        try:
            await self.app(scope, counted_receive, guarded_send)
        except _BodyTooLargeError:
            pass


async def _too_large(scope, receive, send, limit: int) -> None:
    response = JSONResponse(
        {"detail": f"Request body too large (limit {limit} bytes)"}, status_code=413
    )
    await response(scope, receive, send)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # Critical Enhancement 6.5: CSP header
        # Interim CSP: removed unsafe-eval (SEC-014). Full nonce-based CSP
        # requires frontend coordination and is planned for Phase 4+.
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "font-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response.headers["Content-Security-Policy"] = csp
        return response


def _anonymize_ip(ip: str | None) -> str | None:
    """Mask the last octet of IPv4 or last 64 bits of IPv6 for GDPR compliance (SEC-018)."""
    if not ip:
        return None
    # IPv4: mask last octet
    if "." in ip:
        parts = ip.split(".")
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.0"
        return ip
    # IPv6: mask last 64 bits (interface identifier)
    if ":" in ip:
        try:
            import ipaddress
            addr = ipaddress.IPv6Address(ip)
            network = ipaddress.IPv6Network(
                (int(addr) & 0xFFFFFFFFFFFFFFFF0000000000000000, 64), strict=False
            )
            return str(network.network_address)
        except ValueError:
            pass
        return ip
    return ip


def _sanitize_url_for_audit(url_path: str, url_query: str) -> str:
    """Sanitize PII from URLs before audit logging (Critical Enhancement 6.6)."""
    from urllib.parse import parse_qs, urlencode
    sensitive_params = {"token", "api_key", "password", "secret", "session", "jwt", "code"}
    if not url_query:
        return url_path
    try:
        params = parse_qs(url_query)
        sanitized = {
            k: ["[REDACTED]" if k.lower() in sensitive_params else v[0]]
            for k, v in params.items()
        }
        query = urlencode(sanitized, doseq=True)
        return f"{url_path}?{query}" if query else url_path
    except Exception:
        return url_path


class AuditMiddleware(BaseHTTPMiddleware):
    """Log mutating requests for audit trail (Critical Enhancement 6.3 / 6.6)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        if request.method in ("POST", "DELETE", "PUT", "PATCH"):
            try:
                user = getattr(request.state, "user", None)
                path = _sanitize_url_for_audit(request.url.path, request.url.query)
                logger.info(
                    "audit: method=%s path=%s user=%s status=%d ip=%s",
                    request.method,
                    path,
                    str(user.id) if user else None,
                    response.status_code,
                    _anonymize_ip(request.client.host if request.client else None),
                )
            except Exception as exc:
                logger.error("Audit logging failed: %s", exc)

        return response


class MemoryLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce memory limits and prevent OOM.

    Configured via environment variables:
    - MEMORY_LIMIT_MB: Maximum memory in MB (default: 1024)
    - MEMORY_WARNING_MB: Warning threshold (default: 768)
    """

    def __init__(self, app, memory_limit_mb: int = 1024, warning_mb: int = 768):
        super().__init__(app)
        self.memory_limit_mb = memory_limit_mb
        self.warning_mb = warning_mb
        self._warning_logged = False
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        try:
            import psutil

            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024

            # Export memory usage gauge for Prometheus (Phase 2.10)
            try:
                from reasoner.metrics import REASONER_MEMORY_USAGE_MB
                REASONER_MEMORY_USAGE_MB.set(round(memory_mb, 1))
            except Exception:
                pass

            if memory_mb > self.memory_limit_mb:
                logger.error(
                    f"Memory limit exceeded: {memory_mb:.1f}MB > {self.memory_limit_mb}MB"
                )
                return JSONResponse(
                    {"error": "Server memory limit exceeded. Please try again later."},
                    status_code=503,
                )

            async with self._lock:
                if memory_mb > self.warning_mb and not self._warning_logged:
                    logger.warning(
                        f"Memory usage high: {memory_mb:.1f}MB (limit: {self.memory_limit_mb}MB)"
                    )
                    self._warning_logged = True
                elif memory_mb < self.warning_mb * 0.8:
                    self._warning_logged = False

        except ImportError:
            logger.warning(
                "psutil not installed — MemoryLimitMiddleware is disabled. "
                "Install psutil to enable RSS-based memory enforcement."
            )

        return await call_next(request)


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce request timeouts.

    Prevents long-running requests from blocking the server indefinitely.
    """

    def __init__(self, app, timeout_seconds: float = 300.0):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next):
        # Skip timeout for SSE endpoints (they're long-running by design)
        if request.url.path.startswith("/api/run"):
            return await call_next(request)

        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds,
            )
        except TimeoutError:
            logger.warning(f"Request timeout: {request.url.path}")
            return JSONResponse(
                {"error": "Request timeout"},
                status_code=504,
            )
