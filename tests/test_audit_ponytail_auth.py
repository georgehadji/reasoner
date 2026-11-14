"""Auth findings from the ponytail audit: grant needs the admin key, MCP binds
key scopes."""

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
async def test_mcp_scope_check_covers_keys(monkeypatch):
    from reasoner.api.mcp import context
    from reasoner.api.mcp.context import McpAuthError, resolve_caller

    legacy = User(id=uuid4(), email="l@internal", scopes={"read"})

    async def _resolve(token):
        return legacy

    monkeypatch.setattr(deps, "_resolve_auth_token", _resolve)
    monkeypatch.setattr(context, "_bearer_token_from_context", lambda ctx: "rsn_live_key")
    with pytest.raises(McpAuthError, match="lacks the 'run' scope"):
        await resolve_caller(object(), scope="run")
