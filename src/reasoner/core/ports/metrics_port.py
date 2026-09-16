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
