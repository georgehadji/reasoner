"""Per-subscription-tier LLM spend ceilings.

A run's cost is unbounded by construction: the pipeline fans out across
several models per phase, retries on failure, and follows up with full
context. Quota alone ("20 queries/month") does not bound that — one
`debate-premium` run can cost 10x a `coding-budget` one, so a fixed query
count lets a single heavy user consume many times the revenue they pay.

These ceilings are the hard stop, not the target. `per_run_usd` aborts a
single runaway pipeline; `monthly_usd` aborts a user who spreads the same
overspend across many runs. Normal usage should sit well below both.

Pure domain: no settings, no I/O. Global overrides from configuration are
merged in by `application.services.spend_limit_service`.
"""

from __future__ import annotations

from dataclasses import dataclass

from reasoner.domain.saas import SubscriptionTier

# A ceiling of 0.0 means "no limit" — consistent with the SPEND_CAP_*_USD
# settings, where 0.0 disables the cap.
UNLIMITED = 0.0


@dataclass(frozen=True, slots=True)
class TierSpendLimits:
    """LLM spend ceilings for one subscription tier, in USD."""

    per_run_usd: float = UNLIMITED
    monthly_usd: float = UNLIMITED

    def tightest(self, other: TierSpendLimits) -> TierSpendLimits:
        """Combine two ceilings, keeping the stricter of each.

        Used to layer a deployment-wide cap over the tier default. Because
        0.0 means unlimited, it loses to any positive ceiling rather than
        winning as a numeric minimum would.
        """
        return TierSpendLimits(
            per_run_usd=_stricter(self.per_run_usd, other.per_run_usd),
            monthly_usd=_stricter(self.monthly_usd, other.monthly_usd),
        )


def _stricter(a: float, b: float) -> float:
    """Return the binding ceiling of two, treating 0.0 as unlimited."""
    if a <= UNLIMITED:
        return max(b, UNLIMITED)
    if b <= UNLIMITED:
        return a
    return min(a, b)


# Ceilings per tier. Sized against the unit economics: a FREE user is an
# acquisition cost that must stay a small fraction of a paid user's margin,
# and a PRO user must not be able to outspend the net revenue their
# subscription brings in after VAT and payment fees.
TIER_SPEND_LIMITS: dict[SubscriptionTier, TierSpendLimits] = {
    # per_run must clear the worst-case (full-token-budget) estimate of a
    # typical budget-tier preset, not just its historical average — the two
    # are not the same number, and per_run is a ceiling, not a target.
    # Synthesis' output budget was later raised to 32K (constants_limits.py,
    # "leverage qwen3.6-plus's 1M context window"), which lifted every
    # preset's worst-case estimate without a matching update here: the old
    # 0.05 sat *below* the typical budget preset's own worst-case estimate,
    # so it rejected normal free-tier runs outright rather than only genuine
    # outliers. Measured across all 25 budget presets: 13/25 clear 0.05,
    # 23/25 clear 0.07. The two that remain rejected (article-budget,
    # iterative-critique-budget) are real outliers and stay rejected on the
    # free tier, which is correct and not fixed here.
    #
    # MEASURING THIS: estimate_run_cost() resolves per-model pricing through
    # the model-registry port, which the composition roots inject
    # (set_model_registry_port at api/__init__.py, main.py, headless.py) and
    # tests/conftest.py injects at import. A bare `python -c` that skips that
    # injection falls back to undifferentiated pricing and inflates every
    # estimate ~4.4x (debate-budget reads $0.273 instead of $0.0615), which
    # makes it look like no preset can ever pass at any cap. Inject the port
    # before trusting a number from this estimator.
    #
    # ~7 budget runs/month at this ceiling (was ~10 at 0.05). Still enough to
    # evaluate the product, bounded enough that a few thousand free accounts
    # stay affordable.
    SubscriptionTier.FREE: TierSpendLimits(per_run_usd=0.07, monthly_usd=0.50),
    # per_run covers the most expensive premium preset; monthly is ~4x the
    # expected average, so it only binds on genuine outliers.
    SubscriptionTier.PRO: TierSpendLimits(per_run_usd=0.50, monthly_usd=8.00),
    # Effectively uncapped for normal use; still bounded so a credential
    # leak or a runaway integration cannot bill without limit.
    SubscriptionTier.ENTERPRISE: TierSpendLimits(per_run_usd=2.00, monthly_usd=100.00),
}

# Applied to callers with no resolvable subscription (anonymous or legacy
# API-key requests). Deliberately the FREE ceiling: an unidentified caller
# should never get more spending room than a signed-up free user.
ANONYMOUS_SPEND_LIMITS = TIER_SPEND_LIMITS[SubscriptionTier.FREE]


def limits_for_tier(tier: SubscriptionTier | str | None) -> TierSpendLimits:
    """Look up the ceilings for a tier, falling back to the anonymous ones.

    Accepts the enum or its string value so callers can pass a tier
    deserialized from state without converting first. An unknown tier is
    treated as anonymous rather than unlimited — fail closed.
    """
    if tier is None:
        return ANONYMOUS_SPEND_LIMITS
    if isinstance(tier, str):
        try:
            tier = SubscriptionTier(tier)
        except ValueError:
            return ANONYMOUS_SPEND_LIMITS
    return TIER_SPEND_LIMITS.get(tier, ANONYMOUS_SPEND_LIMITS)


__all__ = [
    "UNLIMITED",
    "TierSpendLimits",
    "TIER_SPEND_LIMITS",
    "ANONYMOUS_SPEND_LIMITS",
    "limits_for_tier",
]
