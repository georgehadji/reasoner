"""Where `core` reports a degradation, without knowing who counts it.

`core.degrade.degraded()` is the one place in the codebase that records "we
swallowed this and carried on". It wants to increment a Prometheus counter,
and the counter lives in `infrastructure.metrics` because that is where the
registry and the optional-dependency shim live. A function-local import got
the value without a module-level edge, but import-linter reads the static
graph either way: `reasoner.core -> reasoner.infrastructure` was the single
import breaking the Layered Architecture contract.

So the edge is inverted. `core` declares a hook; `infrastructure.metrics`
fills it in when it is imported, which is the sanctioned adapter direction.

Nothing has to wire this at a composition root. A process that never imports
`infrastructure.metrics` has no Prometheus registry to scrape either, so the
no-op default is the right answer there rather than a missed wiring step.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

#: Set by `infrastructure.metrics` at import. None means "nobody is counting",
#: which is a normal state, not a misconfiguration.
_DEGRADATION_COUNTER: Callable[[str], None] | None = None


def set_degradation_counter(counter: Callable[[str], None] | None) -> None:
    """Install the sink for degradation counts. Accepts None so a test can reset."""
    global _DEGRADATION_COUNTER
    _DEGRADATION_COUNTER = counter


def count_degradation(site: str) -> None:
    """Record one degradation at ``site``. Never raises: metrics must not break a caller."""
    counter = _DEGRADATION_COUNTER
    if counter is None:
        return
    try:
        counter(site)
    except Exception:  # pragma: no cover - a broken metric is not a broken run
        logger.debug("degradation metric unavailable for site=%s", site)


#: Set by `infrastructure.metrics` at import. None means "nobody is counting",
#: which is a normal state, not a misconfiguration.
_QUOTA_EXCEEDED_COUNTER: Callable[[str], None] | None = None


def set_quota_exceeded_counter(counter: Callable[[str], None] | None) -> None:
    """Install the sink for quota-exceeded counts. Accepts None so a test can reset."""
    global _QUOTA_EXCEEDED_COUNTER
    _QUOTA_EXCEEDED_COUNTER = counter


#: Set by `infrastructure.metrics` at import. None means "nobody is counting".
_ILLEGAL_TRANSITION_COUNTER: Callable[[str, str, str], None] | None = None


def set_illegal_transition_counter(counter: Callable[[str, str, str], None] | None) -> None:
    """Install the sink for illegal state-machine moves. Accepts None so a test can reset."""
    global _ILLEGAL_TRANSITION_COUNTER
    _ILLEGAL_TRANSITION_COUNTER = counter


def count_illegal_transition(machine: str, src: str, dst: str) -> None:
    """Record one illegal move. Never raises: metrics must not break a caller.

    This counter decides when an observing machine may start enforcing (zero
    for one release), so a failure to count is logged, not swallowed.
    """
    counter = _ILLEGAL_TRANSITION_COUNTER
    if counter is None:
        return
    try:
        counter(machine, src, dst)
    except Exception:
        logger.warning("illegal-transition metric failed for machine=%s", machine, exc_info=True)


_UNVERIFIED_ACCESS_COUNTER: Callable[[str, str], None] | None = None


def set_unverified_access_counter(counter: Callable[[str, str], None] | None) -> None:
    """Install the sink for gated features reached by an unverified email."""
    global _UNVERIFIED_ACCESS_COUNTER
    _UNVERIFIED_ACCESS_COUNTER = counter


def count_unverified_access(feature: str, outcome: str) -> None:
    """Record one unverified access (``outcome`` is allowed or denied). Never raises.

    Explaining every hit in observe mode is what licenses enforce
    (docs/plans/email-verification-2026-11-12.md step 5), so a failure is logged.
    """
    counter = _UNVERIFIED_ACCESS_COUNTER
    if counter is None:
        return
    try:
        counter(feature, outcome)
    except Exception:
        logger.warning("unverified-access metric failed for feature=%s", feature, exc_info=True)


_STAKES_COUNTER: Callable[[str, str, str], None] | None = None


def set_stakes_counter(counter: Callable[[str, str, str], None] | None) -> None:
    """Install the sink for high-stakes events: ``(kind, a, b)``."""
    global _STAKES_COUNTER
    _STAKES_COUNTER = counter


def count_stakes(kind: str, a: str, b: str = "") -> None:
    """Record a stakes event. ``detected``: a=domain, b=source. ``rerouted``: a=from_action.

    Never raises: metrics must not break routing, but a failure is logged.
    """
    counter = _STAKES_COUNTER
    if counter is None:
        return
    try:
        counter(kind, a, b)
    except Exception:
        logger.warning("stakes metric failed for kind=%s", kind, exc_info=True)


def count_quota_exceeded(tier: str) -> None:
    """Record one quota-exceeded event. Never raises: metrics must not break a caller."""
    counter = _QUOTA_EXCEEDED_COUNTER
    if counter is None:
        return
    try:
        counter(tier)
    except Exception:
        # A broken metric is not a broken run, but it must not be silent either:
        # QuotaExceededSpike alerts on this counter, so a DEBUG line here would
        # hide the alert going dark.
        logger.warning("quota-exceeded metric failed for tier=%s", tier, exc_info=True)
