"""Tests for the credits domain and CreditService."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from reasoner.application.services.credit_service import CreditService, current_period_key
from reasoner.domain.credits import (
    CREDITS_PER_USD,
    CreditReason,
    InsufficientCreditsError,
    can_afford,
    credits_to_usd,
    is_grant_reason,
    monthly_allowance,
    usd_to_credits,
)
from reasoner.domain.saas import SubscriptionTier
from reasoner.infrastructure.persistence.credit_repo_memory import InMemoryCreditRepository


@pytest.fixture
def user_id() -> str:
    return str(uuid4())


@pytest.fixture
def service() -> CreditService:
    return CreditService(InMemoryCreditRepository())


# ── Domain: conversion ──────────────────────────────────────────────


@pytest.mark.unit
def test_usd_converts_to_credits_at_the_published_rate():
    # Arrange / Act / Assert
    assert usd_to_credits(1.0) == CREDITS_PER_USD
    assert credits_to_usd(CREDITS_PER_USD) == 1.0


@pytest.mark.unit
def test_usd_to_credits_always_rounds_up():
    # A run that costs anything at all must cost at least one credit, so no
    # caller can get unbounded free work by staying under a fraction.
    assert usd_to_credits(0.0001) == 1
    assert usd_to_credits(0.0234) == 24
    assert usd_to_credits(0.02001) == 21


@pytest.mark.unit
def test_zero_and_negative_cost_is_free():
    assert usd_to_credits(0) == 0
    assert usd_to_credits(-1.0) == 0


@pytest.mark.unit
def test_tier_allowances_increase_with_tier():
    free = monthly_allowance(SubscriptionTier.FREE)
    pro = monthly_allowance(SubscriptionTier.PRO)
    enterprise = monthly_allowance(SubscriptionTier.ENTERPRISE)
    assert free < pro < enterprise


@pytest.mark.unit
def test_can_afford_refuses_to_go_below_zero():
    assert can_afford(balance=100, cost=100) is True
    assert can_afford(balance=100, cost=101) is False


@pytest.mark.unit
def test_grant_reasons_are_distinguished_from_spend_reasons():
    assert is_grant_reason(CreditReason.MONTHLY_GRANT) is True
    assert is_grant_reason(CreditReason.PURCHASE) is True
    assert is_grant_reason(CreditReason.PIPELINE_RUN) is False


@pytest.mark.unit
def test_period_key_is_year_and_month():
    stamp = datetime(2026, 8, 14, tzinfo=timezone.utc)
    assert current_period_key(stamp) == "2026-08"


# ── Service: balances and grants ────────────────────────────────────


@pytest.mark.unit
async def test_new_account_starts_at_zero(service: CreditService, user_id: str):
    balance = await service.get_balance(user_id)
    assert balance.balance == 0
    assert balance.is_exhausted is True


@pytest.mark.unit
async def test_grant_increases_balance_and_lifetime_total(service: CreditService, user_id: str):
    await service.grant(user_id, 500, CreditReason.SIGNUP_BONUS)

    balance = await service.get_balance(user_id)
    assert balance.balance == 500
    assert balance.lifetime_granted == 500
    assert balance.lifetime_spent == 0


@pytest.mark.unit
async def test_grant_rejects_non_positive_amounts(service: CreditService, user_id: str):
    with pytest.raises(ValueError):
        await service.grant(user_id, 0, CreditReason.PURCHASE)


@pytest.mark.unit
async def test_monthly_allowance_is_granted_once_per_period(
    service: CreditService, user_id: str
):
    first = await service.ensure_monthly_allowance(user_id, SubscriptionTier.FREE)
    second = await service.ensure_monthly_allowance(user_id, SubscriptionTier.FREE)

    assert first is not None
    assert second is None, "the same period must never be granted twice"

    balance = await service.get_balance(user_id)
    assert balance.balance == monthly_allowance(SubscriptionTier.FREE)


@pytest.mark.unit
async def test_monthly_allowance_grants_again_in_a_new_period(
    service: CreditService, user_id: str
):
    august = datetime(2026, 8, 1, tzinfo=timezone.utc)
    september = datetime(2026, 9, 1, tzinfo=timezone.utc)

    await service.ensure_monthly_allowance(user_id, SubscriptionTier.FREE, now=august)
    await service.ensure_monthly_allowance(user_id, SubscriptionTier.FREE, now=september)

    balance = await service.get_balance(user_id)
    assert balance.balance == 2 * monthly_allowance(SubscriptionTier.FREE)


# ── Service: charging ───────────────────────────────────────────────


@pytest.mark.unit
async def test_charge_deducts_and_records_spend(service: CreditService, user_id: str):
    await service.grant(user_id, 100, CreditReason.PURCHASE)

    entry = await service.charge(user_id, 30, reference_id="run-1")

    assert entry.delta == -30
    assert entry.balance_after == 70
    balance = await service.get_balance(user_id)
    assert balance.balance == 70
    assert balance.lifetime_spent == 30


@pytest.mark.unit
async def test_charge_refuses_to_overdraw(service: CreditService, user_id: str):
    await service.grant(user_id, 10, CreditReason.PURCHASE)

    with pytest.raises(InsufficientCreditsError):
        await service.charge(user_id, 11, reference_id="run-too-big")

    assert (await service.get_balance(user_id)).balance == 10


@pytest.mark.unit
async def test_replaying_a_reference_does_not_double_charge(
    service: CreditService, user_id: str
):
    await service.grant(user_id, 100, CreditReason.PURCHASE)

    first = await service.charge(user_id, 25, reference_id="run-abc")
    second = await service.charge(user_id, 25, reference_id="run-abc")

    assert first.id == second.id
    assert (await service.get_balance(user_id)).balance == 75


@pytest.mark.unit
async def test_concurrent_charges_cannot_spend_the_same_balance_twice(
    service: CreditService, user_id: str
):
    await service.grant(user_id, 100, CreditReason.PURCHASE)

    results = await asyncio.gather(
        *(service.charge(user_id, 20, reference_id=f"run-{i}") for i in range(5)),
        return_exceptions=True,
    )

    assert not any(isinstance(r, Exception) for r in results)
    assert (await service.get_balance(user_id)).balance == 0


@pytest.mark.unit
async def test_settlement_charges_actual_usd_spend(service: CreditService, user_id: str):
    await service.grant(user_id, 1000, CreditReason.PURCHASE)

    entry = await service.charge_usd(user_id, cost_usd=0.0234, reference_id="run-usd")

    assert entry is not None
    assert entry.delta == -24
    assert entry.reason is CreditReason.PIPELINE_RUN


@pytest.mark.unit
async def test_free_work_is_never_charged(service: CreditService, user_id: str):
    # Cache hits and runs that fail before any model call report zero cost.
    assert await service.charge_usd(user_id, cost_usd=0.0, reference_id="cached") is None
    assert (await service.get_balance(user_id)).balance == 0


@pytest.mark.unit
async def test_settlement_may_overdraw_because_the_work_already_happened(
    service: CreditService, user_id: str
):
    await service.grant(user_id, 5, CreditReason.PURCHASE)

    entry = await service.charge_usd(user_id, cost_usd=0.20, reference_id="expensive-run")

    assert entry is not None
    balance = await service.get_balance(user_id)
    assert balance.balance < 0, "an already-delivered run must be recorded honestly"
    assert balance.is_exhausted is True, "the next run must be blocked"


@pytest.mark.unit
async def test_refund_returns_credits(service: CreditService, user_id: str):
    await service.grant(user_id, 100, CreditReason.PURCHASE)
    await service.charge(user_id, 40, reference_id="run-refundable")

    await service.refund(user_id, 40, reference_id="refund-run-refundable")

    assert (await service.get_balance(user_id)).balance == 100


@pytest.mark.unit
async def test_has_credits_for_reflects_the_balance(service: CreditService, user_id: str):
    assert await service.has_credits_for(user_id) is False
    await service.grant(user_id, 1, CreditReason.SIGNUP_BONUS)
    assert await service.has_credits_for(user_id) is True


# ── Service: ledger ─────────────────────────────────────────────────


@pytest.mark.unit
async def test_ledger_returns_newest_entries_first(service: CreditService, user_id: str):
    await service.grant(user_id, 100, CreditReason.MONTHLY_GRANT, reference_id="g1")
    await service.charge(user_id, 10, reference_id="c1")
    await service.charge(user_id, 20, reference_id="c2")

    entries = await service.list_ledger(user_id)

    assert [e.reference_id for e in entries] == ["c2", "c1", "g1"]
    assert entries[0].balance_after == 70


@pytest.mark.unit
async def test_every_entry_records_the_resulting_balance(service: CreditService, user_id: str):
    await service.grant(user_id, 50, CreditReason.PURCHASE, reference_id="g")
    await service.charge(user_id, 20, reference_id="c")

    entries = await service.list_ledger(user_id)

    # The ledger must be auditable without replaying it.
    assert [e.balance_after for e in entries] == [30, 50]


# ── SSE cost extraction (what the run path settles against) ──


@pytest.mark.unit
@pytest.mark.parametrize(
    "chunk,expected",
    [
        ('data: {"type": "done", "total_cost_usd": 0.0123}', 0.0123),
        ('data: {"type": "done", "total_cost_usd": 2}', 2.0),
        # Only the terminal frame carries a settleable cost.
        ('data: {"type": "phase", "total_cost_usd": 0.5}', None),
        # Free runs and refunded-to-zero runs must not produce a charge.
        ('data: {"type": "done", "total_cost_usd": 0}', None),
        ('data: {"type": "done", "total_cost_usd": -1}', None),
        ('data: {"type": "done"}', None),
        ('data: {"type": "done", "total_cost_usd": "0.5"}', None),
        # A malformed frame must never break the stream the user is reading.
        ("data: not json", None),
        ('data: ["done"]', None),
        (": keep-alive", None),
    ],
)
def test_run_cost_is_extracted_only_from_a_terminal_done_frame(chunk: str, expected):
    from reasoner.api import _extract_run_cost

    assert _extract_run_cost(chunk) == expected
