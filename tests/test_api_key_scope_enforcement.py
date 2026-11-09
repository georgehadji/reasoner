"""API-key scopes are enforced on the routes that can do damage (SEC-2).

Scopes were attached to the User and never read. A default read-only key
could mint a stronger key, erase the account's data, delete the account and
open a checkout. CSRF is skipped for keys, so nothing else stood in the way.
See docs/plans/audit-remediation-2026-10-20.md, SEC-2.

Running pipelines needs the ``run`` scope, which default keys hold because the
default key exists for the agent endpoints. That check lives in admission, not
on these routes (tests/test_audit5_admission.py, audit 5 SEC-19).
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-production")

from reasoner.api import app
from reasoner.api import dependencies as deps
from reasoner.core.settings import settings
from reasoner.domain.api_keys import (
    ACCOUNT_DELETE_SCOPE,
    ASSIGNABLE_SCOPES,
    DEFAULT_SCOPES,
    KEY_MANAGE_SCOPE,
    key_allows,
)
from reasoner.domain.saas import User

# (method, path, kwargs) for every guarded route.
_GUARDED = [
    ("POST", "/api/account/api-keys", {"json": {"name": "x", "scopes": ["write"]}}),
    ("DELETE", "/api/account/api-keys/k1", {}),
    ("POST", "/api/account/delete", {}),
    ("DELETE", "/api/user/data", {}),
    ("DELETE", "/api/history/e1", {}),
    ("DELETE", "/api/history", {}),
    ("DELETE", "/api/pipelines/p1", {}),
    ("POST", "/api/upload", {}),
    ("DELETE", "/api/upload/f1", {}),
    ("POST", "/api/billing/checkout?tier=pro", {}),
    ("POST", "/api/billing/portal", {}),
]


@pytest.fixture
def key_client(monkeypatch):
    """A client authenticated as an API key holding the default scopes."""
    monkeypatch.setattr(settings, "CSRF_ENFORCE_BACKEND", False)
    user = User(id=uuid4(), email="k@example.com", scopes=set(DEFAULT_SCOPES), auth_provider="api_key")

    def as_key(request: Request) -> User:
        request.state.user = user
        request.state.auth_method = "api_key"
        return user

    app.dependency_overrides[deps.get_current_user] = as_key
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(deps.get_current_user, None)


@pytest.mark.parametrize(("method", "path", "kwargs"), _GUARDED, ids=[f"{m} {p}" for m, p, _ in _GUARDED])
def test_default_key_is_refused(key_client, method, path, kwargs):
    resp = key_client.request(method, path, **kwargs)
    assert resp.status_code == 403, resp.text
    # The guard's 403, not some other refusal such as CSRF.
    assert "lacks the" in resp.text


def test_no_key_can_hold_the_session_only_scopes():
    """Minting keys and deleting the account need an interactive login."""
    assert KEY_MANAGE_SCOPE not in ASSIGNABLE_SCOPES
    assert ACCOUNT_DELETE_SCOPE not in ASSIGNABLE_SCOPES
    assert not key_allows(ASSIGNABLE_SCOPES, KEY_MANAGE_SCOPE)
    assert not key_allows(ASSIGNABLE_SCOPES, ACCOUNT_DELETE_SCOPE)


@pytest.mark.parametrize(
    ("granted", "required", "allowed"),
    [
        ({"read"}, "read", True),
        ({"write"}, "read", True),
        ({"read"}, "write", False),
        ({"write"}, "history:delete", False),
        ({"history:delete"}, "history:delete", True),
        (set(), "read", False),
    ],
)
def test_key_allows(granted, required, allowed):
    assert key_allows(granted, required) is allowed


class _Req:
    def __init__(self, auth_method):
        self.state = type("S", (), {"auth_method": auth_method})()


@pytest.mark.asyncio
async def test_session_user_passes_guard_without_scopes():
    guard = deps.require_key_scope("write")
    user = User(id=uuid4(), email="s@example.com")
    assert await guard(_Req("bearer"), user) is user


@pytest.mark.asyncio
async def test_key_with_scope_passes_guard():
    guard = deps.require_key_scope("write")
    user = User(id=uuid4(), email="k@example.com", scopes={"write"}, auth_provider="api_key")
    assert await guard(_Req("api_key"), user) is user


@pytest.mark.asyncio
async def test_key_without_scope_is_refused_by_guard():
    guard = deps.require_key_scope("history:delete")
    user = User(id=uuid4(), email="k@example.com", scopes={"read", "write"}, auth_provider="api_key")
    with pytest.raises(HTTPException) as exc:
        await guard(_Req("api_key"), user)
    assert exc.value.status_code == 403
