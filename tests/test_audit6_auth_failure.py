"""Audit 6 finding 2: a failed login must not become an anonymous, unbilled run.

`get_optional_user` still returns None (health, gate and neuro rely on that) but
records why; `admit_run` refuses the run. No credentials at all is unchanged.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from reasoner.api import dependencies
from reasoner.api.run_admission import admit_run, require_credentials_resolved
from reasoner.auth import AuthenticationError
from reasoner.core.settings import settings
from reasoner.domain.saas import User

pytestmark = pytest.mark.unit


def _request(**state) -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(**state), headers={})


def _creds() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="rsn_revoked")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (HTTPException(status_code=401, detail="Invalid or revoked API key"), "rejected"),
        (AuthenticationError("bad token", status_code=401), "rejected"),
        (RuntimeError("db down"), "unavailable"),
    ],
)
async def test_optional_user_records_why_it_returned_none(monkeypatch, error, expected):
    monkeypatch.setattr(dependencies, "_resolve_auth_token", AsyncMock(side_effect=error))
    request = _request()
    assert await dependencies.get_optional_user(request, _creds()) is None
    assert request.state.auth_failure == expected


@pytest.mark.asyncio
async def test_optional_user_with_no_credentials_records_nothing():
    request = _request()
    assert await dependencies.get_optional_user(request, None) is None
    assert not hasattr(request.state, "auth_failure")


@pytest.mark.asyncio
async def test_optional_user_success_records_nothing(monkeypatch):
    user = User(id=uuid4(), email="u@example.com")
    monkeypatch.setattr(dependencies, "_resolve_auth_token", AsyncMock(return_value=user))
    request = _request()
    assert await dependencies.get_optional_user(request, _creds()) is user
    assert not hasattr(request.state, "auth_failure")


def test_resolved_check_refuses_rejected_with_401_and_unavailable_with_503():
    with pytest.raises(HTTPException) as rejected:
        require_credentials_resolved(_request(auth_failure="rejected"), None)
    assert rejected.value.status_code == 401
    with pytest.raises(HTTPException) as unavailable:
        require_credentials_resolved(_request(auth_failure="unavailable"), None)
    assert unavailable.value.status_code == 503
    assert unavailable.value.headers["Retry-After"] == "5"


def test_resolved_check_lets_true_anonymous_and_signed_in_callers_through():
    require_credentials_resolved(_request(), None)
    require_credentials_resolved(
        _request(auth_failure="rejected"), User(id=uuid4(), email="u@example.com")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("failure", "status"), [("rejected", 401), ("unavailable", 503)])
async def test_admit_run_refuses_even_with_legacy_access_enabled(monkeypatch, failure, status):
    monkeypatch.setattr(settings, "ENABLE_LEGACY_API_KEY", True)
    with pytest.raises(HTTPException) as exc:
        await admit_run(_request(auth_failure=failure), user=None, problem="p", preset="x")
    assert exc.value.status_code == status


@pytest.mark.asyncio
async def test_mcp_resolve_caller_never_degrades_to_anonymous(monkeypatch):
    mcp_context = pytest.importorskip("reasoner.api.mcp.context")
    monkeypatch.setattr(
        dependencies, "_resolve_auth_token", AsyncMock(side_effect=RuntimeError("db down"))
    )
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(
            request=SimpleNamespace(headers={"authorization": "Bearer rsn_x"})
        )
    )
    with pytest.raises(mcp_context.McpAuthError):
        await mcp_context.resolve_caller(ctx)
