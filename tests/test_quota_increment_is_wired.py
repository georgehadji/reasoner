"""The query quota is claimed at admission, not counted at the end (audit 6, finding 3).

``QuotaService.check()`` only reads. Counting a run after it finished let N
concurrent runs at 19/20 all pass the check and all be counted: 24/20. Admission
now takes the slot atomically (``claim_quota_slot`` -> ``QuotaService.increment``),
and a run that ends up costing nothing gives it back (``metered`` ->
``CreditSink.release_quota_slot``). ``CreditSink.settle`` / ``true_up`` no longer count.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from reasoner.api import dependencies as deps
from reasoner.api.run_observability import CreditSink
from reasoner.application.services.quota_service import QuotaService
from reasoner.application.services.run_metering import RunContext, metered, release_unstarted
from reasoner.domain.saas import QuotaResult, SubscriptionTier, User

DONE = 'data: {"type": "done", "total_cost_usd": 0.02, "errors": []}'


class _FakeQuotaRepo:
    """Atomic like the Postgres row lock: the await inside the lock yields."""

    def __init__(self, used: int, limit: int) -> None:
        self.used, self.limit = used, limit
        self._lock = asyncio.Lock()

    async def check_and_increment(self, user_id: str, preset: str) -> QuotaResult:
        async with self._lock:
            await asyncio.sleep(0)
            if self.limit != -1 and self.used >= self.limit:
                return QuotaResult(allowed=False, remaining=0, reason="Quota exceeded")
            if self.limit == -1:
                return QuotaResult(allowed=True, remaining=-1)
            self.used += 1
            return QuotaResult(allowed=True, remaining=self.limit - self.used)

    async def release_slot(self, user_id: str) -> None:
        if self.limit != -1:
            self.used = max(0, self.used - 1)


# ── the limit is hard under concurrency ─────────────────────────────


@pytest.mark.asyncio
async def test_five_concurrent_admissions_at_19_of_20_let_exactly_one_through() -> None:
    repo = _FakeQuotaRepo(used=19, limit=20)
    service = QuotaService(repo)

    results = await asyncio.gather(*(service.increment("u1", "p") for _ in range(5)))

    assert [r.allowed for r in results].count(True) == 1
    assert repo.used == 20  # not 24


@pytest.mark.asyncio
async def test_a_denied_claim_carries_a_retry_after() -> None:
    result = await QuotaService(_FakeQuotaRepo(used=20, limit=20)).increment("u1", "p")

    assert not result.allowed
    assert result.retry_after and result.retry_after > 0


# ── claim_quota_slot ────────────────────────────────────────────────


def _user() -> User:
    return User(id=uuid4(), email="a@example.com")


@pytest.mark.asyncio
async def test_claim_raises_429_when_the_limit_is_reached() -> None:
    service = QuotaService(_FakeQuotaRepo(used=20, limit=20))
    with patch.object(deps, "_persistence_is_configured", return_value=True), \
         patch.object(deps, "_get_quota_service", return_value=service), \
         patch.object(deps, "resolve_request_tier", AsyncMock(return_value=SubscriptionTier.FREE)):
        with pytest.raises(HTTPException) as err:
            await deps.claim_quota_slot(_user(), "p")

    assert err.value.status_code == 429
    assert err.value.headers["Retry-After"]


@pytest.mark.asyncio
async def test_claim_reports_a_held_slot_only_for_a_finite_tier() -> None:
    user = _user()
    for limit, held in ((20, True), (-1, False)):
        service = QuotaService(_FakeQuotaRepo(used=0, limit=limit))
        with patch.object(deps, "_persistence_is_configured", return_value=True), \
             patch.object(deps, "_get_quota_service", return_value=service), \
             patch.object(deps, "resolve_request_tier", AsyncMock(return_value=SubscriptionTier.FREE)):
            assert await deps.claim_quota_slot(user, "p") is held


@pytest.mark.asyncio
async def test_claim_for_an_anonymous_caller_takes_nothing() -> None:
    assert await deps.claim_quota_slot(None, "p") is False


@pytest.mark.asyncio
async def test_a_quota_outage_admits_the_run_uncounted() -> None:
    service = AsyncMock()
    service.increment.side_effect = ConnectionError("db down")
    with patch.object(deps, "_persistence_is_configured", return_value=True), \
         patch.object(deps, "_get_quota_service", return_value=service), \
         patch.object(deps, "resolve_request_tier", AsyncMock(return_value=SubscriptionTier.FREE)):
        assert await deps.claim_quota_slot(_user(), "p") is False


# ── the sink no longer counts; the slot is released for a free run ──


@pytest.mark.asyncio
async def test_settle_and_true_up_do_not_touch_the_quota() -> None:
    credit, quota = AsyncMock(), AsyncMock()
    with patch("reasoner.api.dependencies._get_credit_service", return_value=credit), \
         patch("reasoner.api.dependencies._get_quota_service", return_value=quota):
        await CreditSink().settle(user_id="u1", cost_usd=0.02, reference_id="r", preset="p")
        await CreditSink().true_up(
            user_id="u1", reserved_credits=5, cost_usd=0.02, reference_id="r", preset="p"
        )

    quota.increment.assert_not_awaited()
    quota.release.assert_not_awaited()


@pytest.mark.asyncio
async def test_settle_still_charges_credits() -> None:
    credit = AsyncMock()
    with patch("reasoner.api.dependencies._get_credit_service", return_value=credit):
        await CreditSink().settle(user_id="u1", cost_usd=0.05, reference_id="run-9", preset="p")

    credit.charge_usd.assert_awaited_once()
    assert credit.charge_usd.await_args.args[0] == "u1"
    assert credit.charge_usd.await_args.kwargs["cost_usd"] == 0.05


class _Sink:
    def __init__(self) -> None:
        self.released: list[str] = []

    async def settle(self, **_kw): ...
    async def reserve(self, **_kw): return 0
    async def true_up(self, **_kw): ...
    async def record_unsettled(self, **_kw): ...

    async def release_quota_slot(self, *, user_id: str, claimed_at=None) -> None:
        self.released.append(user_id)


async def _frames(*items: str):
    for item in items:
        yield item


def _ctx(**kw) -> RunContext:
    return RunContext(preset="p", reference_id="r", user_id="u1", quota_slot=True, **kw)


@pytest.mark.asyncio
async def test_a_billed_run_keeps_its_slot() -> None:
    sink = _Sink()

    async for _ in metered(_frames(DONE), _ctx(reserved_credits=5), sink):
        pass

    assert sink.released == []


@pytest.mark.asyncio
async def test_a_run_that_cost_nothing_gives_its_slot_back() -> None:
    sink = _Sink()

    async for _ in metered(_frames('data: {"type": "phase_start"}'), _ctx(reserved_credits=5), sink):
        pass

    assert sink.released == ["u1"]


@pytest.mark.asyncio
async def test_a_run_without_a_slot_releases_nothing() -> None:
    sink = _Sink()
    ctx = RunContext(preset="p", reference_id="r", user_id="u1", quota_slot=False)

    async for _ in metered(_frames('data: {"type": "phase_start"}'), ctx, sink):
        pass

    assert sink.released == []


@pytest.mark.asyncio
async def test_a_stream_that_never_started_gives_its_slot_back() -> None:
    sink = _Sink()
    ctx = _ctx(reserved_credits=5, started=asyncio.Event())

    await release_unstarted(sink, ctx)

    assert sink.released == ["u1"]


@pytest.mark.asyncio
async def test_a_failing_release_never_reaches_the_caller() -> None:
    sink = _Sink()
    sink.release_quota_slot = AsyncMock(side_effect=RuntimeError("db down"))

    seen = [f async for f in metered(_frames("data: {}"), _ctx(), sink)]

    assert seen == ["data: {}"]


# ── admit_run: claim first, give it back if the reservation is refused ──


def _request():
    from starlette.requests import Request

    return Request({"type": "http", "headers": [], "client": ("1.2.3.4", 1), "state": {}})


@pytest.mark.asyncio
async def test_admit_run_gives_the_slot_back_when_the_reservation_is_refused() -> None:
    from reasoner.api import idempotency_http
    from reasoner.api.run_admission import admit_run

    claim, release = AsyncMock(return_value=True), AsyncMock()
    with patch.object(deps, "claim_quota_slot", claim), \
         patch.object(deps, "release_quota_slot", release), \
         patch.object(deps, "check_preset_access_if_authenticated", AsyncMock()), \
         patch.object(deps, "reserve_or_402", AsyncMock(side_effect=HTTPException(402))), \
         patch.object(idempotency_http, "register_run_or_error", AsyncMock(return_value=None)):
        user = _user()
        with pytest.raises(HTTPException) as err:
            await admit_run(_request(), user=user, problem="x", preset="p")

    assert err.value.status_code == 402
    release.assert_awaited_once_with(user)


@pytest.mark.asyncio
async def test_admit_run_marks_the_admission_with_the_slot() -> None:
    from reasoner.api import idempotency_http
    from reasoner.api.run_admission import admit_run

    with patch.object(deps, "claim_quota_slot", AsyncMock(return_value=True)), \
         patch.object(deps, "check_preset_access_if_authenticated", AsyncMock()), \
         patch.object(deps, "reserve_or_402", AsyncMock(return_value=7)), \
         patch.object(idempotency_http, "register_run_or_error", AsyncMock(return_value=None)):
        adm = await admit_run(_request(), user=_user(), problem="x", preset="p")

    assert adm.quota_slot is True
    assert adm.run_context().quota_slot is True
