"""A successful billed run must advance used_queries exactly once.

QuotaService.check() deliberately does not increment -- its own docstring says
to "call increment() separately after a successful pipeline run to avoid
charging for failed runs". Nothing called it. used_queries never advanced, so
the query quota could never deny, on any backend.

CreditSink.settle is the one place a run is known to have both succeeded and
been billed: run_metering._settle is the single terminal success path, and it
is skipped entirely for anonymous callers (RunContext.user_id is None).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from reasoner.api.run_observability import CreditSink


@pytest.mark.asyncio
async def test_settle_increments_quota_after_charging() -> None:
    """Proof of defect: increment had zero callers, so this never ran."""
    credit, quota = AsyncMock(), AsyncMock()

    with patch("reasoner.api.dependencies._get_credit_service", return_value=credit), \
         patch("reasoner.api.dependencies._get_quota_service", return_value=quota):
        await CreditSink().settle(
            user_id="u1", cost_usd=0.02, reference_id="run-1", preset="coding-budget"
        )

    quota.increment.assert_awaited_once_with("u1", "coding-budget")


@pytest.mark.asyncio
async def test_settle_charges_before_it_increments() -> None:
    """Order matters: an unbilled run must not consume a quota slot."""
    calls: list[str] = []
    credit, quota = AsyncMock(), AsyncMock()
    credit.charge_usd.side_effect = lambda *a, **k: calls.append("charge")
    quota.increment.side_effect = lambda *a, **k: calls.append("increment")

    with patch("reasoner.api.dependencies._get_credit_service", return_value=credit), \
         patch("reasoner.api.dependencies._get_quota_service", return_value=quota):
        await CreditSink().settle(
            user_id="u1", cost_usd=0.02, reference_id="run-1", preset="p"
        )

    assert calls == ["charge", "increment"]


@pytest.mark.asyncio
async def test_a_failed_charge_does_not_consume_a_quota_slot() -> None:
    """Boundary: if billing raises, the run was not billed, so do not count it."""
    credit, quota = AsyncMock(), AsyncMock()
    credit.charge_usd.side_effect = RuntimeError("card declined")

    with patch("reasoner.api.dependencies._get_credit_service", return_value=credit), \
         patch("reasoner.api.dependencies._get_quota_service", return_value=quota):
        with pytest.raises(RuntimeError):
            await CreditSink().settle(
                user_id="u1", cost_usd=0.02, reference_id="run-1", preset="p"
            )

    quota.increment.assert_not_awaited()


@pytest.mark.asyncio
async def test_settle_still_charges_credits() -> None:
    """No-regression: the pre-existing charge is unchanged."""
    credit, quota = AsyncMock(), AsyncMock()

    with patch("reasoner.api.dependencies._get_credit_service", return_value=credit), \
         patch("reasoner.api.dependencies._get_quota_service", return_value=quota):
        await CreditSink().settle(
            user_id="u1", cost_usd=0.05, reference_id="run-9", preset="debate-premium"
        )

    credit.charge_usd.assert_awaited_once()
    assert credit.charge_usd.await_args.args[0] == "u1"
    assert credit.charge_usd.await_args.kwargs["cost_usd"] == 0.05
