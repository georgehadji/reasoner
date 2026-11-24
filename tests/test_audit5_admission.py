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


# ── In-flight run cap (audit 8 WS5-2, D7) ──────────────────────────────────


@pytest.fixture
def inflight_env(monkeypatch):
    """Admission with every external step stubbed, and Redis out of reach."""
    import time
    from unittest.mock import AsyncMock

    from reasoner.api import idempotency_http
    from reasoner.domain.saas import SubscriptionTier
    from reasoner.infrastructure.redis import run_state

    manager = run_state.RunStateManager()
    manager._redis_ok = False
    manager._redis_last_fail = time.monotonic()
    manager._redis_cooldown_seconds = 1e9
    monkeypatch.setattr(run_state, "_run_state_manager", manager)

    reserve = AsyncMock(return_value=5)
    monkeypatch.setattr(deps, "check_preset_access_if_authenticated", AsyncMock())
    monkeypatch.setattr(deps, "claim_quota_slot", AsyncMock(return_value=False))
    monkeypatch.setattr(deps, "reserve_or_402", reserve)
    monkeypatch.setattr(
        idempotency_http, "register_run_or_error", AsyncMock(return_value=None)
    )
    tier = {"value": SubscriptionTier.FREE}
    monkeypatch.setattr(
        deps, "resolve_request_tier", AsyncMock(side_effect=lambda r, u: tier["value"])
    )
    return type("Env", (), {"reserve": reserve, "tier": tier, "manager": manager})()


class _AdmitReq:
    def __init__(self):
        self.state = type("S", (), {})()


def _signed_in() -> User:
    return User(id=uuid4(), email="u@example.com")


@pytest.mark.asyncio
async def test_free_user_gets_one_run_at_a_time_and_a_refusal_holds_no_credits(inflight_env):
    user = _signed_in()
    first = await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    assert first.inflight_owner == str(user.id)

    with pytest.raises(HTTPException) as exc:
        await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    assert exc.value.status_code == 429
    assert int(exc.value.headers["Retry-After"]) > 0
    assert exc.value.detail["limit"] == 1
    assert inflight_env.reserve.await_count == 1  # the refused run reserved nothing


@pytest.mark.asyncio
async def test_another_user_is_not_affected(inflight_env):
    await run_admission.admit_run(_AdmitReq(), user=_signed_in(), problem="q", preset="auto-budget")
    await run_admission.admit_run(_AdmitReq(), user=_signed_in(), problem="q", preset="auto-budget")


@pytest.mark.asyncio
async def test_pro_user_gets_three(inflight_env):
    from reasoner.domain.saas import SubscriptionTier

    inflight_env.tier["value"] = SubscriptionTier.PRO
    user = _signed_in()
    for _ in range(3):
        await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    with pytest.raises(HTTPException) as exc:
        await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_a_run_refused_for_credits_gives_its_slot_back(inflight_env):
    user = _signed_in()
    inflight_env.reserve.side_effect = HTTPException(status_code=402, detail="no credits")
    with pytest.raises(HTTPException) as exc:
        await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    assert exc.value.status_code == 402

    inflight_env.reserve.side_effect = None
    inflight_env.reserve.return_value = 5
    await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")


@pytest.mark.asyncio
async def test_a_full_worker_answers_503_whoever_asks(inflight_env, monkeypatch):
    from reasoner.core import constants_limits

    monkeypatch.setattr(constants_limits, "MAX_INFLIGHT_RUNS_PER_WORKER", 1)
    await run_admission.admit_run(_AdmitReq(), user=_signed_in(), problem="q", preset="auto-budget")
    with pytest.raises(HTTPException) as exc:
        await run_admission.admit_run(
            _AdmitReq(), user=_signed_in(), problem="q", preset="auto-budget"
        )
    assert exc.value.status_code == 503
    assert "Retry-After" in exc.value.headers


class _NoSink:
    """The slot is released whatever the settlement does; a user-less run never calls it."""


async def _frames(*, fail: bool = False):
    yield 'data: {"type": "phase_complete", "total_cost_usd": 0.0}\n\n'
    if fail:
        raise RuntimeError("provider blew up")


async def _slot_is_free(env, user) -> bool:
    try:
        await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    except HTTPException:
        return False
    return True


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_the_slot_frees_when_the_run_ends_however_it_ends(inflight_env, fail):
    from reasoner.application.services.run_metering import metered

    user = _signed_in()
    adm = await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    assert not await _slot_is_free(inflight_env, user)

    ctx = adm.run_context()
    try:
        async for _ in metered(_frames(fail=fail), ctx, _NoSink()):
            pass
    except RuntimeError:
        assert fail
    assert await _slot_is_free(inflight_env, user)


@pytest.mark.asyncio
async def test_the_slot_frees_when_the_stream_never_started(inflight_env):
    from reasoner.application.services.run_metering import release_unstarted

    user = _signed_in()
    adm = await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    await release_unstarted(_NoSink(), adm.run_context())
    assert await _slot_is_free(inflight_env, user)


@pytest.mark.asyncio
async def test_a_finished_run_lowers_the_count_exactly_once(inflight_env):
    """Settling after release_unstarted, or twice, must not free a later run's slot."""
    from reasoner.application.services.run_metering import metered, release_unstarted
    from reasoner.domain.saas import SubscriptionTier

    inflight_env.tier["value"] = SubscriptionTier.PRO
    user = _signed_in()
    first = await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")
    # 3 held
    await run_admission.admit_run(_AdmitReq(), user=user, problem="q", preset="auto-budget")

    ctx = first.run_context()
    await release_unstarted(_NoSink(), ctx)
    async for _ in metered(_frames(), ctx, _NoSink()):
        pass
    # Exactly one slot came back: one run fits, a second does not.
    assert await _slot_is_free(inflight_env, user)
    assert not await _slot_is_free(inflight_env, user)
