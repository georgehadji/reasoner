"""One way to swallow a failure, and it leaves evidence.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

``except Exception: return documents`` appears ~117 times under ``src/``. The
intent behind them is sound -- one failing subsystem should not take a run down
-- but "degrade with a signal" and "swallow" were never distinguished, so the
result is failures that happen in production and leave no trace. D11 is the
archetype: ``rerank_via_nemotron`` is documented as "Returns input unchanged on
any global failure", and it did, for every call, for as long as its default
model id was absent from the catalogue. The only evidence was a DEBUG line.

A site that chooses to continue must do three things, and this does all three
in one call so the pattern is greppable and the ratchet can count what has not
been converted:

    except Exception as exc:
        return degraded("rerank.nemotron", documents, exc=exc, state=state)

1. Log at WARNING under a stable ``site`` name, so a dashboard can alert on it.
2. Increment ``reasoner_degradation_total{site=...}``.
3. Append to ``PipelineState.degradations``, so the run's own output can say it
   degraded -- which the epistemic-labelling promise (VERIFIED / HYPOTHESIS /
   UNKNOWN) already requires of us.

Step 3 is the one that matters: a metric tells an operator, the state field
tells the person reading the answer.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def degraded[T](
    site: str,
    fallback: T,
    *,
    exc: BaseException,
    state: Any | None = None,
    detail: str | None = None,
) -> T:
    """Record a swallowed failure and return the fallback value.

    Args:
        site: Stable dotted name for this degradation, e.g. "rerank.nemotron".
            It is a metric label, so keep the cardinality bounded: no model
            ids, no user input, no exception text.
        fallback: The value the caller continues with.
        exc: The exception being swallowed.
        state: Optional PipelineState. When present, the degradation is
            appended to ``state.degradations`` so the run can report it.
        detail: Optional extra context. It is appended to the log line and,
            when ``state`` is given, to the recorded degradation -- so it is
            read by whoever reads the run's output, not only by an operator.

    Returns:
        ``fallback``, unchanged, so this can be used as ``return degraded(...)``.
    """
    reason = f"{type(exc).__name__}: {exc}"
    if detail:
        reason = f"{reason} ({detail})"

    logger.warning("degradation site=%s %s", site, reason)

    # Lazy, function-local: reasoner.core must not depend on
    # reasoner.infrastructure at module scope (tests/architecture/
    # test_layer_boundaries.py), and prometheus_client is an optional
    # dependency that degrades to a no-op metric when absent. Same shape as
    # the lazy imports in core/search.py.
    try:
        from reasoner.infrastructure.metrics import REASONER_DEGRADATION_TOTAL

        REASONER_DEGRADATION_TOTAL.labels(site=site).inc()
    except Exception:  # pragma: no cover - metrics must never break a caller
        logger.debug("degradation metric unavailable for site=%s", site)

    degradations = getattr(state, "degradations", None)
    if isinstance(degradations, list):
        degradations.append(f"{site}: {reason}")

    return fallback
