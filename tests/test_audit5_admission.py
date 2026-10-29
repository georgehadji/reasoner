"""A key needs the ``run`` scope to start a billed run (audit 5 SEC-19).

``require_key_scope`` guarded uploads, deletes, keys and billing, but no route
that starts a run, so a key could never be made read-only. The check sits in
``admit_run``, the one admission sequence every HTTP run route shares, so a new
route cannot forget it (docs/plans/audit-remediation-5-2026-10-29.md, PR 1).

Default keys keep ``run``: the SEC-2 decision that the default key exists for
the agent endpoints still holds (tests/test_api_key_scope_enforcement.py).
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-production")

from reasoner.api import dependencies as deps  # noqa: E402
from reasoner.api import run_admission  # noqa: E402
from reasoner.domain.api_keys import ASSIGNABLE_SCOPES, DEFAULT_SCOPES, RUN_SCOPE  # noqa: E402
from reasoner.domain.saas import User  # noqa: E402

pytestmark = [pytest.mark.unit]


class _Req:
    def __init__(self, auth_method: str | None):
        self.state = type("S", (), {"auth_method": auth_method})()


def _key_user(scopes, key_id=None) -> User:
    return User(
        id=uuid4(), email="k@example.com", scopes=set(scopes),
        auth_provider="api_key", api_key_id=key_id,
    )


def test_run_scope_is_assignable_and_default():
    assert RUN_SCOPE in ASSIGNABLE_SCOPES
    assert RUN_SCOPE in DEFAULT_SCOPES


def test_key_without_run_scope_is_refused():
    with pytest.raises(HTTPException) as exc:
        run_admission.require_run_scope(_Req("api_key"), _key_user({"read"}))
    assert exc.value.status_code == 403
    assert "lacks the 'run' scope" in exc.value.detail


def test_key_with_run_scope_passes():
    run_admission.require_run_scope(_Req("api_key"), _key_user({"read", RUN_SCOPE}))


def test_session_caller_needs_no_run_scope():
    user = User(id=uuid4(), email="s@example.com")
    run_admission.require_run_scope(_Req("bearer"), user)


def test_anonymous_caller_is_not_checked():
    run_admission.require_run_scope(_Req(None), None)


@pytest.mark.asyncio
async def test_admit_run_refuses_key_without_run_scope(monkeypatch):
    """The step is wired into admit_run, before the preset gate or any hold."""
    reached: list[str] = []

    async def fake_preset_gate(preset, user, request):
        reached.append(preset)

    monkeypatch.setattr(deps, "check_preset_access_if_authenticated", fake_preset_gate)

    with pytest.raises(HTTPException) as exc:
        await run_admission.admit_run(
            _Req("api_key"), user=_key_user({"read"}), problem="q", preset="auto-budget",
        )
    assert exc.value.status_code == 403
    assert reached == []


@pytest.mark.asyncio
async def test_run_stamps_last_run_at(monkeypatch):
    """Q1 step 2 removes ``run`` from keys that never ran, so runs are recorded."""
    key_id = uuid4()
    recorded: list = []

    class _Service:
        async def record_run(self, kid):
            recorded.append(kid)

    monkeypatch.setattr(deps, "_get_api_key_service", lambda: _Service())

    run_admission.require_run_scope(_Req("api_key"), _key_user({RUN_SCOPE}, key_id))
    await asyncio.sleep(0)

    assert recorded == [key_id]


@pytest.mark.asyncio
async def test_resolved_key_user_carries_its_key_id(monkeypatch):
    from reasoner.domain.api_keys import ApiKey

    key_id = uuid4()
    owner = User(id=uuid4(), email="o@example.com")
    record = ApiKey(
        id=key_id, user_id=owner.id, name="k", key_hash="h", key_prefix="p",
        scopes=frozenset(DEFAULT_SCOPES),
    )

    class _Service:
        async def authenticate(self, token):
            return record

    async def fake_load(user_id):
        return owner

    monkeypatch.setattr(deps, "_get_api_key_service", lambda: _Service())
    monkeypatch.setattr(deps, "_load_user_by_id", fake_load)

    user = await deps._resolve_api_key("rsn_live_x")
    assert user.api_key_id == key_id


@pytest.mark.asyncio
async def test_memory_repo_records_last_run():
    from reasoner.infrastructure.persistence.api_key_repo_memory import InMemoryApiKeyRepository

    repo = InMemoryApiKeyRepository()
    key = await repo.create(
        user_id=str(uuid4()), name="k", key_hash="h1", key_prefix="p",
        scopes=frozenset(DEFAULT_SCOPES), expires_at=None,
    )
    assert key.id not in repo._last_run
    await repo.touch_last_run(key.id)
    assert repo._last_run[key.id] is not None
