"""Auth findings from the ponytail audit: grant needs the admin key, MCP binds
legacy-key scopes, legacy keys honour another worker's revocation."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-production")

from reasoner.api import app
from reasoner.api import dependencies as deps
from reasoner.core.settings import settings
from reasoner.domain.saas import User


def test_grant_needs_the_admin_key_not_just_the_scope(monkeypatch):
    monkeypatch.setattr(settings, "CSRF_ENFORCE_BACKEND", False)
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "k-admin")
    user = User(id=uuid4(), email="a@example.com", scopes={"admin"})

    def as_admin(request: Request) -> User:
        request.state.user = user
        return user

    app.dependency_overrides[deps.get_current_user] = as_admin
    try:
        client = TestClient(app, raise_server_exceptions=False)
        body = {"user_id": str(uuid4()), "credits": 5}
        assert client.post("/api/credits/grant", json=body).status_code == 403
        assert (
            client.post(
                "/api/credits/grant", json=body, headers={"X-Admin-Key": "wrong"}
            ).status_code
            == 403
        )
    finally:
        app.dependency_overrides.pop(deps.get_current_user, None)


@pytest.mark.asyncio
async def test_mcp_scope_check_covers_legacy_keys(monkeypatch):
    from reasoner.api.mcp import context
    from reasoner.api.mcp.context import McpAuthError, resolve_caller

    legacy = User(id=uuid4(), email="l@internal", scopes={"read"})

    async def _resolve(token):
        return legacy

    monkeypatch.setattr(deps, "_resolve_auth_token", _resolve)
    monkeypatch.setattr(context, "_bearer_token_from_context", lambda ctx: "plain-legacy-key")
    with pytest.raises(McpAuthError, match="lacks the 'run' scope"):
        await resolve_caller(object(), scope="run")


@pytest.mark.asyncio
async def test_legacy_key_revoked_elsewhere_is_refused(monkeypatch):
    from reasoner.auth import AuthenticationError
    from reasoner.infrastructure.auth_legacy import AuthManager

    mgr = AuthManager()
    raw = await mgr.generate_key("k")
    await mgr.authenticate(raw)  # warm every in-process copy

    row = {"key_hash": mgr._hash_key(raw), "name": "k", "is_active": False, "expires_at": None,
           "created_at": mgr._keys[mgr._hash_key(raw)].created_at, "scopes": {"read"}}

    class _Store:  # another worker already revoked it in the shared DB
        async def get_by_hash(self, h):
            return row

        async def update_usage(self, h):
            pass

    mgr._store = _Store()
    with pytest.raises(AuthenticationError, match="deactivated"):
        await mgr.authenticate(raw)
