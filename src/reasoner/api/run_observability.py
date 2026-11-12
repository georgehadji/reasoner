"""HTTP-layer bindings for ``run_metering``'s Protocols.

``run_metering.metered()`` knows nothing about credits or Prometheus; it takes
a ``SettlementSink`` and a ``RunObserver``. These are the FastAPI app's
implementations of both, shared by every route that runs a metered pipeline
so the binding exists exactly once.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

from reasoner.core.ports.unsettled_run_port import UnsettledRun
from reasoner.infrastructure.valkey.unsettled_runs import ValkeyUnsettledRunStore

logger = logging.getLogger(__name__)


def count_credit_failopen(path: str) -> None:
    """Count a credit step that failed open or failed to settle. Never raises."""
    try:
        from reasoner.metrics import REASONER_CREDIT_FAILOPEN_TOTAL

        REASONER_CREDIT_FAILOPEN_TOTAL.labels(path=path).inc()
    except Exception as exc:
        logger.warning("Failed to record credit fail-open metric: %s", exc)


class CreditSink:
    """Reserves and settles a run's cost against the credit service."""

    async def reserve(
        self,
        *,
        user_id: str,
        estimated_cost_usd: float,
        reference_id: str,
        preset: str,
    ) -> int:
        from reasoner.api.dependencies import _get_credit_service
        from reasoner.domain.credits import usd_to_credits

        credits = usd_to_credits(estimated_cost_usd)
        if credits <= 0:
            return 0
        await _get_credit_service().charge(
            user_id,
            credits,
            reference_id=reference_id,
            description=f"Reservation for pending run ({preset})",
        )
        return credits

    async def release(
        self,
        *,
        user_id: str,
        credits: int,
        reference_id: str,
    ) -> None:
        if credits <= 0:
            return
        from reasoner.api.dependencies import _get_credit_service

        await _get_credit_service().refund(
            user_id,
            credits,
            reference_id=reference_id,
            description="Unused reservation released",
        )

    async def settle(
        self,
        *,
        user_id: str,
        cost_usd: float,
        reference_id: str,
        preset: str,
    ) -> None:
        from reasoner.api.dependencies import _get_credit_service

        # The quota slot is taken at admission (admit_run), not counted here: a
        # count at the end let concurrent runs all pass the check first.
        await _get_credit_service().charge_usd(
            user_id,
            cost_usd=cost_usd,
            reference_id=reference_id,
            description=f"Pipeline run ({preset})",
        )

    async def true_up(
        self,
        *,
        user_id: str,
        reserved_credits: int,
        cost_usd: float,
        reference_id: str,
        preset: str,
    ) -> None:
        """Release the reservation and charge the real cost in one ledger transaction."""
        from reasoner.api.dependencies import _get_credit_service

        await _get_credit_service().true_up_run(
            user_id,
            reserved_credits=reserved_credits,
            cost_usd=cost_usd,
            reference_id=reference_id,
            preset=preset,
        )

    async def release_quota_slot(
        self, *, user_id: str, claimed_at: datetime | None = None
    ) -> None:
        from reasoner.api.dependencies import _get_quota_service

        await _get_quota_service().release(user_id, claimed_at)

    async def record_unsettled(
        self,
        *,
        user_id: str,
        reference_id: str,
        cost_usd: float,
        reserved_credits: int,
        preset: str,
        error: str,
    ) -> None:
        """Store a served-but-unsettled run in Valkey; log it if Valkey is down too."""
        count_credit_failopen("settle")
        run = UnsettledRun(
            user_id=user_id,
            reference_id=reference_id,
            cost_usd=cost_usd,
            reserved_credits=reserved_credits,
            preset=preset,
            error=error,
            recorded_at=time.time(),
        )
        try:
            await ValkeyUnsettledRunStore().record(run)
        except Exception as exc:
            logger.error(
                "UNSETTLED RUN (valkey unavailable: %s): user=%s reference=%s cost_usd=%.6f "
                "reserved_credits=%d preset=%s error=%s",
                exc, user_id, reference_id, cost_usd, reserved_credits, preset, error,
            )


class PrometheusObserver:
    """Records a finished run's outcome. Never raises — metrics are optional."""

    def __init__(self, *, tier: str, preset: str, interface: str = "web", timer=None):
        self._tier = tier
        self._preset = preset
        self._interface = interface
        self._timer = timer

    def observe(self, *, status: str) -> None:
        if self._timer is not None:
            self._timer.observe()
        try:
            from reasoner.metrics import REASONER_QUERIES_TOTAL

            REASONER_QUERIES_TOTAL.labels(
                tier=self._tier,
                preset=self._preset,
                status=status,
                interface=self._interface,
            ).inc()
        except Exception as exc:
            logger.warning("Failed to record prometheus query metrics: %s", exc)


__all__ = ["CreditSink", "PrometheusObserver", "count_credit_failopen"]
