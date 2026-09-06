"""HTTP-layer bindings for ``run_metering``'s Protocols.

``run_metering.metered()`` knows nothing about credits or Prometheus; it takes
a ``SettlementSink`` and a ``RunObserver``. These are the FastAPI app's
implementations of both, shared by every route that runs a metered pipeline
so the binding exists exactly once.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


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
        from reasoner.api.dependencies import _get_credit_service, _get_quota_service

        await _get_credit_service().charge_usd(
            user_id,
            cost_usd=cost_usd,
            reference_id=reference_id,
            description=f"Pipeline run ({preset})",
        )
        # The one place a run is known to have both succeeded and been billed.
        # QuotaService.check() deliberately does not increment ("call
        # increment() separately after a successful pipeline run to avoid
        # charging for failed runs") but nothing ever called it, so
        # used_queries never advanced and the query quota could not deny.
        # After the charge, not before: an unbilled run must not eat a slot.
        await _get_quota_service().increment(user_id, preset)


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


__all__ = ["CreditSink", "PrometheusObserver"]
