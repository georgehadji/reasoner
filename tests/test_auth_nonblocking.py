"""Supabase JWT validation does not block the loop, is cached, and runs once
per request (OPS-3).

`SupabaseAuthAdapter.authenticate` made supabase-py's sync HTTPS `get_user`
call inside `async def`, uncached, and agent routes ran it twice
(check_rate_limit's get_optional_user, then get_current_user).
See docs/plans/audit-remediation-2026-10-20.md, OPS-3.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import OrderedDict
from types import SimpleNamespace

import jwt
import pytest

from reasoner.infrastructure.auth.supabase_adapter import SupabaseAuthAdapter


class _BlockingAuth:
    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.calls = 0

    def get_user(self, token):
        self.calls += 1
        time.sleep(self.delay)  # supabase-py: a sync HTTPS round trip
        return SimpleNamespace(user=SimpleNamespace(
            id=str(uuid.UUID(int=1)), email="a@b.c", app_metadata={}, user_metadata={},
        ))


def _adapter(delay: float = 0.0) -> SupabaseAuthAdapter:
    adapter = SupabaseAuthAdapter.__new__(SupabaseAuthAdapter)
    adapter._client = SimpleNamespace(auth=_BlockingAuth(delay))
    adapter._cache = OrderedDict()
    return adapter


def _token(exp_in: float) -> str:
    return jwt.encode({"sub": "x", "exp": int(time.time() + exp_in)}, "k" * 32, algorithm="HS256")


@pytest.mark.asyncio
async def test_a_slow_verification_does_not_stall_the_loop():
    adapter = _adapter(delay=0.5)
    gaps: list[float] = []

    async def ticker():
        last = time.monotonic()
        for _ in range(8):
            await asyncio.sleep(0.05)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    user, _ = await asyncio.gather(adapter.authenticate(_token(3600)), ticker())
    assert user.email == "a@b.c"
    assert max(gaps) < 0.3, f"the loop stalled for {max(gaps):.2f}s"


@pytest.mark.asyncio
async def test_a_verified_token_is_cached_but_never_past_its_exp():
    adapter = _adapter()
    auth = adapter._client.auth

    token = _token(3600)
    await adapter.authenticate(token)
    await adapter.authenticate(token)
    assert auth.calls == 1

    expired = _token(-5)
    await adapter.authenticate(expired)
    await adapter.authenticate(expired)
    assert auth.calls == 3, "a token past its exp must be re-verified, not served from cache"


@pytest.mark.asyncio
async def test_a_request_authenticates_once(monkeypatch):
    from fastapi.security import HTTPAuthorizationCredentials
    from starlette.requests import Request

    from reasoner.api import dependencies
    from reasoner.domain.saas import User

    calls = []

    async def _resolve(token):
        calls.append(token)
        return User(id=uuid.uuid4(), email="a@b.c")

    async def _no_db(user):
        return None

    monkeypatch.setattr(dependencies, "_resolve_auth_token", _resolve)
    monkeypatch.setattr(dependencies, "_ensure_user_in_db", _no_db)
    request = Request({"type": "http", "headers": [], "method": "GET", "path": "/"})
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="a.b.c")

    first = await dependencies.get_optional_user(request, creds)
    second = await dependencies.get_current_user(request, creds)
    assert second is first
    assert len(calls) == 1
