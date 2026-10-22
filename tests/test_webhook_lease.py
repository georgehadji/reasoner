"""BIL-21: a finished webhook is marked done; a failed one is released.

The DB-side lease (claim, reclaim after expiry) is exercised on a real
Postgres in tests/integration/test_webhook_lease_pg.py. These tests pin that
the handlers call the right end of it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from reasoner.application.services.billing_service import BillingService
from reasoner.core.constants_limits import WEBHOOK_LEASE_SECONDS
from reasoner.infrastructure.billing import webhooks
from reasoner.infrastructure.billing.paypal_adapter import PayPalBillingAdapter
from tests.test_paypal_webhook_verification import _EVENT, _HEADERS, _request

pytestmark = pytest.mark.unit


class _Valkey:
    def __init__(self, completed: bool = False) -> None:
        self._completed = completed

    async def get(self, *a):
        return "1" if self._completed else None

    async def set(self, *a, **k):
        return True

    async def setex(self, *a):
        return None

    async def delete(self, *a):
        return None


@pytest.fixture
def lease(monkeypatch):
    done, release = AsyncMock(), AsyncMock()
    monkeypatch.setattr(webhooks, "_db_claim_webhook", AsyncMock(return_value=True))
    monkeypatch.setattr(webhooks, "_db_complete_webhook", done)
    monkeypatch.setattr(webhooks, "_db_release_webhook", release)
    monkeypatch.setattr(webhooks, "get_valkey_pool", lambda: _Valkey())
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-ID")
    monkeypatch.setattr(
        PayPalBillingAdapter, "verify_webhook_signature", AsyncMock(return_value=True)
    )
    return done, release


def test_the_lease_outlives_the_slowest_handler():
    # The Stripe API calls inside sync_subscription are the slowest step; the
    # plan measured them at about 30 s. A lease below that would let a second
    # worker take an event the first is still applying.
    assert WEBHOOK_LEASE_SECONDS >= 300


@pytest.mark.asyncio
async def test_a_processed_event_is_marked_done(monkeypatch, lease):
    done, release = lease
    monkeypatch.setattr(BillingService, "handle_webhook", AsyncMock())

    await webhooks.handle_paypal_webhook(_request(_EVENT, _HEADERS))

    done.assert_awaited_once_with("WH-1", "paypal")
    release.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_event_is_released_not_marked_done(monkeypatch, lease):
    done, release = lease
    monkeypatch.setattr(
        BillingService, "handle_webhook", AsyncMock(side_effect=RuntimeError("db down"))
    )
    monkeypatch.setattr(webhooks, "_record_webhook_failure", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await webhooks.handle_paypal_webhook(_request(_EVENT, _HEADERS))

    assert exc.value.status_code == 500
    release.assert_awaited_once_with("WH-1", "paypal")
    done.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_event_valkey_already_finished_is_marked_done(monkeypatch, lease):
    """The DB claim was won, then Valkey said the event completed earlier. The
    row must not stay 'processing' for the next worker to reclaim."""
    done, _ = lease
    monkeypatch.setattr(webhooks, "get_valkey_pool", lambda: _Valkey(completed=True))
    handle = AsyncMock()
    monkeypatch.setattr(BillingService, "handle_webhook", handle)

    await webhooks.handle_paypal_webhook(_request(_EVENT, _HEADERS))

    handle.assert_not_awaited()
    done.assert_awaited_once_with("WH-1", "paypal")
