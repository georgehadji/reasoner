"""Unit tests for the sandbox-worker FastAPI app. docker_runner is monkeypatched
so nothing here needs a real Docker daemon — these prove the HTTP surface
(auth, request-shape rejection) is correct, independent of the actual
container execution (covered by tests/integration/test_sandbox_escape.py).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def worker_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("SANDBOX_WORKER_TOKEN", "expected-token")
    # app.py reads the env var into a module-level constant at import time —
    # reload so this test's token takes effect regardless of import order.
    import importlib

    from reasoner.infrastructure.execution.sandbox_worker import app as app_module

    importlib.reload(app_module)
    return TestClient(app_module.app)


def test_execute_rejects_missing_token(worker_client: TestClient) -> None:
    response = worker_client.post("/execute", json={"code": "print(1)"})
    assert response.status_code == 401


def test_execute_rejects_wrong_token(worker_client: TestClient) -> None:
    response = worker_client.post(
        "/execute",
        json={"code": "print(1)"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert response.status_code == 401


def test_execute_rejects_extra_fields(
    worker_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """extra="forbid" is the control that stops a caller from injecting an
    image, command, mount, or env var — this is the one behavior that must
    never regress."""

    response = worker_client.post(
        "/execute",
        json={"code": "print(1)", "image": "attacker/evil:latest"},
        headers={"Authorization": "Bearer expected-token"},
    )
    assert response.status_code == 422


def test_execute_success_calls_docker_runner(
    worker_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reasoner.core.ports.code_executor import ExecutionResult
    from reasoner.infrastructure.execution.sandbox_worker import app as app_module

    async def _fake_run_in_container(code, *, language, stdin, limits):
        assert code == "print(1)"
        return ExecutionResult(
            success=True, stdout="1\n", exit_code=0, policy_version="container-sandbox-v1"
        )

    monkeypatch.setattr(app_module, "run_in_container", _fake_run_in_container)

    response = worker_client.post(
        "/execute",
        json={"code": "print(1)"},
        headers={"Authorization": "Bearer expected-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["stdout"] == "1\n"


def test_health_reflects_docker_health_check(
    worker_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from reasoner.infrastructure.execution.sandbox_worker import app as app_module

    async def _unhealthy() -> bool:
        return False

    monkeypatch.setattr(app_module, "check_docker_health", _unhealthy)
    response = worker_client.get("/health")
    assert response.status_code == 503

    async def _healthy() -> bool:
        return True

    monkeypatch.setattr(app_module, "check_docker_health", _healthy)
    response = worker_client.get("/health")
    assert response.status_code == 200


def test_unconfigured_token_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """No token configured must refuse everything, not accept requests
    because there's nothing to compare against."""
    monkeypatch.delenv("SANDBOX_WORKER_TOKEN", raising=False)
    import importlib

    from reasoner.infrastructure.execution.sandbox_worker import app as app_module

    importlib.reload(app_module)
    client = TestClient(app_module.app)
    response = client.post(
        "/execute",
        json={"code": "print(1)"},
        headers={"Authorization": "Bearer anything"},
    )
    assert response.status_code == 503
