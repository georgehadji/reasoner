"""Capability model — names the authorization/metering policy every
provider-costing route must declare.

Not a runtime policy engine: today's auth/metering checks are already
centralized as shared FastAPI dependencies (``require_credits``,
``check_quota``, ``reserve_or_402``) rather than duplicated per route. What
was missing was a forcing function -- something that fails CI when a new
costed route is added without wiring one of them in. That's what
``CAPABILITY_POLICY`` plus ``tests/test_capability_coverage.py`` (which scans
the actual route source for reservation calls and cross-checks them against
this table) exist to do; this module itself doesn't dispatch or enforce
anything at request time.

MCP tools (``api/mcp/tools.py``) aren't FastAPI routes, so they're outside
what the coverage test can scan for -- covered by direct code review instead
(see ``_run_and_bill`` and ``reasoner_followup``, both call ``reserve_or_402``
identically to the HTTP agent routes).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from reasoner.domain.credits import CreditReason


class Capability(str, Enum):
    """A costed or privileged action a route performs.

    Named after the ledger reason it produces (``domain.credits.CreditReason``)
    where one exists, so the two vocabularies stay in sync.
    """

    PIPELINE_RUN = "pipeline.run"
    IMAGE_GENERATE = "image.generate"
    CACHE_INVALIDATE = "cache.invalidate"  # reserved for a later phase


@dataclass(frozen=True)
class CapabilityPolicy:
    """Declarative record of how a capability is authorized and metered."""

    requires_auth: bool
    credit_reason: CreditReason | None
    rate_limited: bool
    routes: tuple[str, ...]


CAPABILITY_POLICY: dict[Capability, CapabilityPolicy] = {
    Capability.PIPELINE_RUN: CapabilityPolicy(
        requires_auth=False,  # anonymous allowed via ENABLE_LEGACY_API_KEY,
        # capped by application.services.anonymous_trial_policy instead of
        # the per-user credit ledger.
        credit_reason=CreditReason.PIPELINE_RUN,
        rate_limited=True,
        routes=("/api/run", "/api/run-followup", "/api/agent/run", "/api/agent/run/sync"),
    ),
    Capability.IMAGE_GENERATE: CapabilityPolicy(
        requires_auth=False,
        credit_reason=CreditReason.IMAGE_GENERATION,
        rate_limited=True,
        routes=("/api/generate-image",),
    ),
}


__all__ = ["Capability", "CapabilityPolicy", "CAPABILITY_POLICY"]
