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
    """Settles a run's cost against the credit service."""

    async def settle(
        self,
        *,
        user_id: str,
        cost_usd: float,
        reference_id: str,
        preset: str,
    ) -> None:
        from reasoner.api.dependencies import _get_credit_service

        await _get_credit_service().charge_usd(
            user_id,
            cost_usd=cost_usd,
            reference_id=reference_id,
            description=f"Pipeline run ({preset})",
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


__all__ = ["CreditSink", "PrometheusObserver"]
