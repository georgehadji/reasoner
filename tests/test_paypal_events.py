"""BIL-20: every PayPal lifecycle event has a row, in both tables.

`RE-ACTIVATED` and `EXPIRED` were unhandled. A user who paid after a failed
payment stayed past_due/FREE, and an expired subscription stayed active. The
adapter (event -> status) and the service (event -> write) now each hold one
table, and a test pins that the two have the same rows.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from reasoner.application.services.billing_service import PAYPAL_HANDLERS, BillingService
from reasoner.domain.saas import SubscriptionStatus
from reasoner.infrastructure.billing.paypal_adapter import (
    PAYPAL_EVENT_STATUS,
    PayPalBillingAdapter,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 1, tzinfo=UTC)
PAYPAL_ID = "I-1"


class _Repo:
    """In-memory stand-in for the PayPal-facing half of the subscription
    repository, with the same ordering rule: an older event never overwrites."""

    def __init__(self) -> None:
        self.status: str | None = None
        self.last_at: datetime | None = None
        self.quota_syncs = 0

    def _apply(self, status: str, at: datetime | None) -> bool:
        if at and self.last_at and at < self.last_at:
            return False
        self.status, self.last_at = status, at or self.last_at
        return True

    async def upsert_subscription(self, sub, at) -> bool:
        return self._apply(sub.status.value, at)

    async def set_subscription_status_by_paypal(self, paypal_id, status, at) -> bool:
        assert paypal_id == PAYPAL_ID
        return self._apply(status, at)

    async def sync_quota_for_subscription(self, sub) -> None:
        self.quota_syncs += 1


async def _deliver(repo: _Repo, event_type: str, minutes: int) -> None:
    adapter = PayPalBillingAdapter.__new__(PayPalBillingAdapter)
    event = {
        "event_type": event_type,
        "resource": {"id": PAYPAL_ID, "custom_id": str(uuid4())},
    }
    sub = await adapter.sync_subscription(event)
    await BillingService(adapter)._apply_webhook(
        event_type, sub, repo, T0 + timedelta(minutes=minutes)
    )


def test_the_two_tables_have_the_same_rows():
    assert set(PAYPAL_HANDLERS) == set(PAYPAL_EVENT_STATUS)


def test_the_two_missing_cases_are_rows():
    assert PAYPAL_EVENT_STATUS["BILLING.SUBSCRIPTION.RE-ACTIVATED"] is SubscriptionStatus.ACTIVE
    assert PAYPAL_EVENT_STATUS["BILLING.SUBSCRIPTION.EXPIRED"] is SubscriptionStatus.CANCELLED


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", sorted(PAYPAL_HANDLERS))
async def test_each_event_lands_in_the_status_its_row_names(event_type):
    repo = _Repo()
    await _deliver(repo, event_type, 1)
    assert repo.status == PAYPAL_EVENT_STATUS[event_type].value


@pytest.mark.asyncio
async def test_paying_after_a_failed_payment_ends_active():
    repo = _Repo()
    await _deliver(repo, "BILLING.SUBSCRIPTION.ACTIVATED", 1)
    await _deliver(repo, "BILLING.SUBSCRIPTION.PAYMENT.FAILED", 2)
    assert repo.status == "past_due"
    await _deliver(repo, "BILLING.SUBSCRIPTION.RE-ACTIVATED", 3)
    assert repo.status == "active"
    assert repo.quota_syncs >= 2, "the quota follows the tier back up"


@pytest.mark.asyncio
async def test_an_expired_subscription_ends_cancelled():
    repo = _Repo()
    await _deliver(repo, "BILLING.SUBSCRIPTION.ACTIVATED", 1)
    await _deliver(repo, "BILLING.SUBSCRIPTION.EXPIRED", 2)
    assert repo.status == "cancelled"


@pytest.mark.asyncio
async def test_a_late_reactivation_does_not_undo_a_newer_expiry():
    repo = _Repo()
    await _deliver(repo, "BILLING.SUBSCRIPTION.EXPIRED", 5)
    await _deliver(repo, "BILLING.SUBSCRIPTION.RE-ACTIVATED", 3)
    assert repo.status == "cancelled"


@pytest.mark.asyncio
async def test_an_unlisted_paypal_event_writes_nothing():
    repo = _Repo()
    await _deliver(repo, "BILLING.SUBSCRIPTION.UPDATED", 1)
    assert repo.status is None
