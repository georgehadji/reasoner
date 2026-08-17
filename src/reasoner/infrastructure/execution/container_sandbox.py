"""ContainerExecutionSandbox — the approved isolated CodeExecutorPort adapter.

Lives in the `backend` API process but never touches Docker itself: it's an
httpx client to the sandbox-worker service (a separate container with its
own Docker access — see infrastructure/execution/sandbox_worker/). This
adapter's only job is to shuttle a request/response across that internal
boundary and fail closed (blocked=True) on any transport problem, matching
CodeExecutorPort's "never raise on execution failure" contract.
"""

from __future__ import annotations

import logging
import time

import httpx

from reasoner.core.ports.code_executor import ExecutionLimits, ExecutionResult

logger = logging.getLogger(__name__)

_HEALTH_CACHE_TTL_SECONDS = 30.0


class ContainerExecutionSandbox:
    """Talks to the sandbox-worker service; implements CodeExecutorPort."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        connect_timeout: float = 2.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._connect_timeout = connect_timeout
        self._transport = transport
        self._health_cache: tuple[float, bool] | None = None

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            transport=self._transport,
            timeout=httpx.Timeout(timeout, connect=self._connect_timeout),
            headers={"Authorization": f"Bearer {self._token}"},
        )

    async def execute(
        self,
        code: str,
        *,
        language: str = "python",
        stdin: str = "",
        limits: ExecutionLimits | None = None,
    ) -> ExecutionResult:
        if limits is None:
            limits = ExecutionLimits()

        # Deny by default: never dispatch to a worker that hasn't recently
        # proven it's healthy. This is the runtime half of "block enabling
        # code execution unless the sandbox adapter passes health checks" —
        # checked before every call (TTL-cached) rather than once at startup,
        # so a worker that goes unhealthy mid-deployment is caught too.
        if not await self.health_check():
            return ExecutionResult(
                success=False,
                stderr="Sandbox worker failed its health check",
                exit_code=-1,
                blocked=True,
                blocked_reason="sandbox_unhealthy",
            )

        payload = {
            "code": code,
            "language": language,
            "stdin": stdin,
            "timeout_ms": limits.timeout_ms,
            "memory_limit_mb": limits.memory_limit_mb,
            "max_output_bytes": limits.max_output_bytes,
        }
        # A little slack beyond the job's own wall-clock so the HTTP call
        # doesn't time out a fraction of a second before the worker itself
        # would have returned a clean timeout result.
        request_timeout = (limits.timeout_ms / 1000.0) + 15.0

        try:
            async with self._client(request_timeout) as client:
                response = await client.post("/execute", json=payload)
        except httpx.TimeoutException:
            return ExecutionResult(
                success=False,
                stderr="Sandbox worker did not respond in time",
                exit_code=-1,
                timed_out=True,
                blocked=True,
                blocked_reason="sandbox_unreachable",
            )
        except httpx.HTTPError as exc:
            logger.error("Sandbox worker request failed: %s", exc)
            return ExecutionResult(
                success=False,
                stderr="Sandbox worker is unreachable",
                exit_code=-1,
                blocked=True,
                blocked_reason="sandbox_unreachable",
            )

        if response.status_code != 200:
            logger.error(
                "Sandbox worker returned %s: %s", response.status_code, response.text[:500]
            )
            return ExecutionResult(
                success=False,
                stderr="Sandbox worker rejected the request",
                exit_code=-1,
                blocked=True,
                blocked_reason=f"sandbox_error_{response.status_code}",
            )

        data = response.json()
        return ExecutionResult(
            success=data["success"],
            stdout=data["stdout"],
            stderr=data["stderr"],
            exit_code=data["exit_code"],
            timed_out=data["timed_out"],
            duration_ms=data["duration_ms"],
            truncated=data["truncated"],
            blocked=data["blocked"],
            blocked_reason=data["blocked_reason"],
            policy_version=data["policy_version"],
        )

    async def health_check(self) -> bool:
        """TTL-cached so callers can check before every construction without
        adding a network round trip to every pipeline run."""
        now = time.monotonic()
        if self._health_cache is not None:
            checked_at, healthy = self._health_cache
            if now - checked_at < _HEALTH_CACHE_TTL_SECONDS:
                return healthy

        healthy = await self._check_health_uncached()
        self._health_cache = (now, healthy)
        return healthy

    async def _check_health_uncached(self) -> bool:
        try:
            async with self._client(5.0) as client:
                response = await client.get("/health")
            return response.status_code == 200
        except httpx.HTTPError as exc:
            logger.warning("Sandbox worker health check failed: %s", exc)
            return False
