"""Unit tests for ContainerExecutionSandbox — the httpx client side of the
Phase 1 sandbox boundary. All Docker interaction is mocked via httpx's
MockTransport; no daemon is needed (see tests/integration/test_sandbox_escape.py
for real escape tests against a live Docker daemon).
"""

from __future__ import annotations

import json

import httpx

from reasoner.infrastructure.execution.container_sandbox import ContainerExecutionSandbox

_TOKEN = "test-token"


def _sandbox(handler) -> ContainerExecutionSandbox:
    transport = httpx.MockTransport(handler)
    return ContainerExecutionSandbox("http://sandbox-worker", _TOKEN, transport=transport)


def _execute_response(**overrides) -> dict:
    body = {
        "success": True,
        "stdout": "hello\n",
        "stderr": "",
        "exit_code": 0,
        "timed_out": False,
        "duration_ms": 12,
        "truncated": False,
        "blocked": False,
        "blocked_reason": "",
        "policy_version": "container-sandbox-v1",
    }
    body.update(overrides)
    return body


async def test_execute_success_roundtrip() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        assert request.url.path == "/execute"
        assert request.headers["authorization"] == f"Bearer {_TOKEN}"
        payload = json.loads(request.content)
        assert payload["code"] == "print('hello')"
        return httpx.Response(200, json=_execute_response())

    sandbox = _sandbox(handler)
    result = await sandbox.execute("print('hello')")
    assert result.success is True
    assert result.stdout == "hello\n"
    assert result.policy_version == "container-sandbox-v1"


async def test_execute_never_sends_extra_fields_from_caller_kwargs() -> None:
    """The port signature has no way to smuggle image/mount/env through —
    confirms the wire payload only ever carries the fixed field set."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=_execute_response())

    sandbox = _sandbox(handler)
    await sandbox.execute("print(1)", language="python", stdin="in")
    assert set(captured.keys()) == {
        "code", "language", "stdin", "timeout_ms", "memory_limit_mb", "max_output_bytes",
    }


async def test_worker_unreachable_fails_closed() -> None:
    """Worker unreachable for the /execute call itself (health passed
    moments earlier, TTL cache hasn't expired) — distinct from
    test_execute_short_circuits_when_unhealthy, which never gets this far."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        raise httpx.ConnectError("connection refused", request=request)

    sandbox = _sandbox(handler)
    result = await sandbox.execute("print(1)")
    assert result.blocked is True
    assert result.blocked_reason == "sandbox_unreachable"
    assert result.success is False


async def test_worker_timeout_fails_closed_and_marks_timed_out() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        raise httpx.TimeoutException("timed out", request=request)

    sandbox = _sandbox(handler)
    result = await sandbox.execute("print(1)")
    assert result.blocked is True
    assert result.timed_out is True
    assert result.blocked_reason == "sandbox_unreachable"


async def test_worker_non_200_fails_closed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(500, text="internal error")

    sandbox = _sandbox(handler)
    result = await sandbox.execute("print(1)")
    assert result.blocked is True
    assert result.blocked_reason == "sandbox_error_500"


async def test_execute_short_circuits_when_unhealthy() -> None:
    """execute() must never even POST /execute when health_check() fails —
    the fail-closed gate has to run before every dispatch, not just once."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(503)
        return httpx.Response(200, json=_execute_response())

    sandbox = _sandbox(handler)
    result = await sandbox.execute("print(1)")
    assert result.blocked is True
    assert result.blocked_reason == "sandbox_unhealthy"
    assert calls == ["/health"]  # /execute must never have been called


async def test_health_check_is_ttl_cached() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"status": "ok"})

    sandbox = _sandbox(handler)
    assert await sandbox.health_check() is True
    assert await sandbox.health_check() is True
    assert calls == ["/health"]  # second call served from cache, no new request


async def test_health_check_false_on_503() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    sandbox = _sandbox(handler)
    assert await sandbox.health_check() is False
