"""PR 4 of docs/plans/audit-remediation-2-2026-10-20.md: SEC-7, BIL-17, BIL-18.

* SEC-7: the ``client_run_id`` claim was global across tenants and never
  released, so a retry after a 402 got 409 for an hour, and after the TTL a
  second tenant became the owner of the first tenant's pipeline.
* BIL-17: the anonymous rate bucket was ``ip:sha(User-Agent)``, so rotating
  the User-Agent gave a fresh bucket for ``/api/gate``'s five LLM calls.
* BIL-18: a deleted account kept working on a worker that had cached its id,
  and provisioning re-created its ``users`` row.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from reasoner.application.ports.pipeline_ownership_port import OwnershipConflictError
from reasoner.application.services.run_metering import RunContext, metered
from reasoner.domain.saas import User

pytestmark = pytest.mark.asyncio

DONE_FRAME = 'data: {"type": "done", "total_cost_usd": 0.01}\n\n'
PHASE_FRAME = 'data: {"type": "phase_complete", "total_cost_usd": 0.01}\n\n'


def _request(ip: str = "203.0.113.7", user_agent: str = "ua-1") -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/run",
        "headers": [(b"user-agent", user_agent.encode())],
        "client": (ip, 1234),
        "state": {},
    })


def _user() -> User:
    return User(id=uuid4(), email="t@example.test")


class _Owners:
    """In-memory PipelineOwnershipPort with the insert-if-absent contract."""

    def __init__(self) -> None:
        self.rows: dict[str, str | None] = {}

    async def set_owner(self, pipeline_id, user_id, run_id) -> None:
        current = self.rows.setdefault(pipeline_id, user_id)
        if current != user_id:
            raise OwnershipConflictError(pipeline_id)


async def _admit(user, client_run_id, *, reserve, owners):
    from reasoner.api import dependencies as deps
    from reasoner.api.run_admission import admit_run

    with (
        patch.object(deps, "check_preset_access_if_authenticated", AsyncMock()),
        patch.object(deps, "reserve_or_402", reserve),
        patch("reasoner.api.run_admission.get_pipeline_ownership_repo", return_value=owners),
    ):
        return await admit_run(
            _request(), user=user, problem="p", preset="debate-budget",
            client_run_id=client_run_id,
        )


# ── SEC-7: tenant-scoped, releasable claims; ownership never moves ─────


async def test_retry_after_a_402_reuses_the_same_client_run_id():
    user, owners, run_id = _user(), _Owners(), f"job-{uuid4().hex[:8]}"
    short = HTTPException(status_code=402, detail="Insufficient credits")

    with pytest.raises(HTTPException) as refused:
        await _admit(user, run_id, reserve=AsyncMock(side_effect=short), owners=owners)
    assert refused.value.status_code == 402

    # The caller tops up and retries with the same id, as the docs tell them to.
    admission = await _admit(user, run_id, reserve=AsyncMock(return_value=10), owners=owners)
    assert admission.reserved_credits == 10


async def test_a_duplicate_of_an_admitted_run_still_gets_409():
    user, owners, run_id = _user(), _Owners(), f"job-{uuid4().hex[:8]}"
    await _admit(user, run_id, reserve=AsyncMock(return_value=0), owners=owners)
    with pytest.raises(HTTPException) as dup:
        await _admit(user, run_id, reserve=AsyncMock(return_value=0), owners=owners)
    assert dup.value.status_code == 409


async def test_a_second_tenant_on_the_same_id_gets_409_and_never_owns_it():
    first, second = _user(), _user()
    owners, run_id = _Owners(), f"job-{uuid4().hex[:8]}"
    await _admit(first, run_id, reserve=AsyncMock(return_value=0), owners=owners)

    reserve = AsyncMock(return_value=0)
    with pytest.raises(HTTPException) as clash:
        await _admit(second, run_id, reserve=reserve, owners=owners)
    assert clash.value.status_code == 409
    reserve.assert_not_awaited()  # refused before any credit is held
    assert owners.rows[run_id] == str(first.id)


async def test_set_owner_never_moves_ownership(tmp_path):
    from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
        PipelineOwnershipRepository,
    )

    repo = PipelineOwnershipRepository(tmp_path / "events.db")
    await repo.set_owner("job-1", "user-a", "job-1")
    await repo.set_owner("job-1", "user-a", "job-1")  # same owner: a no-op
    with pytest.raises(OwnershipConflictError):
        await repo.set_owner("job-1", "user-b", "job-1")
    assert (await repo.get_owner("job-1")).user_id == "user-a"


class _Sink:
    async def release(self, **kwargs) -> None: ...
    async def settle(self, **kwargs) -> None: ...


async def _drain(frames, ctx):
    async def stream():
        for frame in frames:
            yield frame

    async for _ in metered(stream(), ctx, _Sink()):
        pass


@pytest.mark.parametrize("frames,released", [
    ([PHASE_FRAME], True),               # the run stopped before it finished
    ([PHASE_FRAME, DONE_FRAME], False),  # finished: a duplicate must still 409
])
async def test_metered_releases_the_claim_only_when_the_run_did_not_finish(frames, released):
    ctx = RunContext(preset="p", reference_id="r", user_id="u", run_claim="u:job-1")
    with patch(
        "reasoner.application.services.idempotency.release_run", AsyncMock(),
    ) as release:
        await _drain(frames, ctx)
    assert release.await_count == (1 if released else 0)


# ── BIL-17: one anonymous bucket per address ───────────────────────────


async def test_rotating_the_user_agent_does_not_reset_the_anonymous_bucket():
    from reasoner.api import dependencies as deps

    limiter = SimpleNamespace(is_allowed=AsyncMock(return_value=(True, {})))
    with patch.object(deps, "_get_rate_limiter_instance", return_value=limiter):
        await deps.check_rate_limit(_request(user_agent="ua-1"), user=None)
        await deps.check_rate_limit(_request(user_agent="ua-2"), user=None)
    keys = {call.args[0] for call in limiter.is_allowed.await_args_list}
    assert len(keys) == 1


async def test_anonymous_gate_calls_count_against_the_daily_cap():
    from reasoner.api.routes import gate

    cap = AsyncMock(side_effect=HTTPException(status_code=429, detail="cap"))
    decide = AsyncMock()
    with (
        patch.object(gate, "enforce_anonymous_trial_cap", cap),
        patch.object(gate, "decide_route", decide),
    ):
        with pytest.raises(HTTPException) as capped:
            await gate.gate_decision(
                SimpleNamespace(problem="p", preset="auto-budget"),
                request=_request(), user=None, csrf_checked=True,
            )
    assert capped.value.status_code == 429
    assert cap.await_args.args[0] == "203.0.113.7"
    decide.assert_not_awaited()


# ── BIL-18: deleted accounts stop working everywhere ───────────────────


class _Pool:
    """Answers the deletion-log lookup; records every other statement."""

    def __init__(self, deleted: set[str]) -> None:
        self.deleted = deleted
        self.executed: list[str] = []

    async def fetchval(self, sql, user_id):
        assert "account_deletion_log" in sql
        return 1 if user_id in self.deleted else None

    async def execute(self, sql, *args):
        self.executed.append(sql)


async def test_a_deleted_account_is_refused_even_on_a_worker_that_cached_it():
    from reasoner.api import dependencies as deps

    user = _user()
    pool = _Pool(deleted=set())
    with patch.object(deps, "_get_provision_pool", AsyncMock(return_value=pool)):
        await deps._ensure_user_in_db(user)  # this worker now caches the id
        pool.deleted.add(str(user.id))
        deps.forget_provisioned_user(user.id)  # what account deletion does here
        with pytest.raises(HTTPException) as gone:
            await deps._ensure_user_in_db(user)
    assert gone.value.status_code == 403
    assert len(pool.executed) == 1  # the users row was not re-created


async def test_the_provisioning_cache_expires(monkeypatch):
    from reasoner.api import dependencies as deps

    user = _user()
    pool = _Pool(deleted=set())
    clock = [1000.0]
    monkeypatch.setattr(deps, "_monotonic", lambda: clock[0])
    with patch.object(deps, "_get_provision_pool", AsyncMock(return_value=pool)):
        await deps._ensure_user_in_db(user)
        pool.deleted.add(str(user.id))  # deleted through another worker
        clock[0] += deps.PROVISION_CACHE_TTL_SECONDS + 1
        with pytest.raises(HTTPException) as gone:
            await deps._ensure_user_in_db(user)
    assert gone.value.status_code == 403


async def test_a_missing_users_row_is_a_hard_403_not_a_fail_open():
    import asyncpg

    from reasoner.api import dependencies as deps

    fk = asyncpg.exceptions.ForeignKeyViolationError("user_credits_user_id_fkey")
    with (
        patch.object(deps, "_persistence_is_configured", return_value=True),
        patch.object(deps, "_require_persistence"),
        patch(
            "reasoner.application.services.run_metering.reserve_run_budget",
            AsyncMock(side_effect=fk),
        ),
    ):
        with pytest.raises(HTTPException) as refused:
            await deps.reserve_or_402(
                user_id=str(uuid4()), preset="p", problem="x", reference_id="r",
            )
    assert refused.value.status_code == 403


async def test_supabase_delete_identity_removes_the_user_and_its_cached_tokens():
    from collections import OrderedDict

    from reasoner.infrastructure.auth.supabase_adapter import SupabaseAuthAdapter

    adapter = SupabaseAuthAdapter.__new__(SupabaseAuthAdapter)
    user = _user()
    adapter._cache = OrderedDict({"k": (9e9, user)})
    delete_user = AsyncMock()
    adapter._client = SimpleNamespace(
        auth=SimpleNamespace(admin=SimpleNamespace(delete_user=delete_user)),
    )
    with patch("asyncio.to_thread", AsyncMock()) as to_thread:
        await adapter.delete_identity(str(user.id))
    assert to_thread.await_args.args == (delete_user, str(user.id))
    assert not adapter._cache
