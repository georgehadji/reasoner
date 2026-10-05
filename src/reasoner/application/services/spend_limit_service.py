"""Resolves and applies per-tier LLM spend ceilings.

Sits between the pure ceilings in `domain.spend_limits` and the two places
they are enforced:

  * preflight — reject a run whose preset cannot fit the caller's per-run
    ceiling, before spending anything on it;
  * mid-run — `infrastructure.llm.executor` halts further phases once the
    accumulated cost crosses a ceiling.

Deployment-wide caps (`SPEND_CAP_PER_RUN_USD`, `SPEND_CAP_MONTHLY_USD`)
layer on top of the tier defaults, and the stricter of the two binds.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from reasoner.core.degrade import degraded
from reasoner.domain.saas import SubscriptionStatus, SubscriptionTier
from reasoner.domain.spend_limits import (
    UNLIMITED,
    TierSpendLimits,
    limits_for_tier,
)

logger = logging.getLogger(__name__)

# Statuses that entitle a user to their subscription's tier. Anything else
# (cancelled, past_due) falls back to FREE.
_ENTITLED_STATUSES = frozenset({SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING})


@dataclass(frozen=True, slots=True)
class SpendRejection:
    """A run refused before execution because the caller's plan cannot take it."""

    reason: str
    cap_type: str  # "preset_tier" | "per_run" | "monthly"
    cap_usd: float
    estimated_usd: float
    tier: SubscriptionTier
    required_tier: SubscriptionTier | None = None


# Tier ordering, for "is the caller's plan at least X" comparisons. The single
# ranking shared by the runtime gate (check_run_allowed) and the early HTTP gate
# in api/dependencies.py.
_TIER_RANK: dict[SubscriptionTier, int] = {
    SubscriptionTier.FREE: 0,
    SubscriptionTier.PRO: 1,
    SubscriptionTier.ENTERPRISE: 2,
}

# Upper bound on one subscription lookup. A cold cache plus a slow or unreachable
# Postgres would otherwise block for the asyncpg connect timeout on every request.
TIER_LOOKUP_TIMEOUT_S = 1.0

# Budget for the one lookup that decides whether a run the caller already paid
# a credit reservation for may proceed (api/execution/pipeline.py). Longer than
# the request-path budget: refusing a paying user's premium run because the DB
# answered in 2s is worse than making that run wait.
RUN_TIER_LOOKUP_TIMEOUT_S = 5.0

# How long a FREE fallback (timeout or error) is remembered per user. Without it
# an unreachable subscription store costs every request a full timeout wait.
FALLBACK_CACHE_TTL_S = 5.0
_FALLBACK_CACHE_MAX = 1024
_fallback_until: dict[str, float] = {}


def _fallback_active(user_id: str) -> bool:
    expiry = _fallback_until.get(user_id)
    if expiry is None:
        return False
    if expiry <= time.monotonic():
        _fallback_until.pop(user_id, None)
        return False
    return True


def _remember_fallback(user_id: str) -> None:
    now = time.monotonic()
    if len(_fallback_until) >= _FALLBACK_CACHE_MAX:
        for uid in [u for u, t in _fallback_until.items() if t <= now]:
            del _fallback_until[uid]
        if len(_fallback_until) >= _FALLBACK_CACHE_MAX:
            _fallback_until.clear()
    _fallback_until[user_id] = now + FALLBACK_CACHE_TTL_S


def tier_satisfies(user_tier: SubscriptionTier, required_tier: SubscriptionTier) -> bool:
    """Whether *user_tier* meets or exceeds *required_tier*.

    Fails closed on both sides: an unrecognised user tier ranks as FREE, and an
    unrecognised *required* tier ranks above ENTERPRISE so nobody satisfies it.
    """
    required_rank = _TIER_RANK.get(required_tier, len(_TIER_RANK))
    return _TIER_RANK.get(user_tier, 0) >= required_rank


def pricing_data_available() -> bool:
    """True when per-model prices are loaded, not just the default entry.

    `domain.pricing` populates PRICING_DB from `openrouter_models.json`. When
    that file is absent every model prices identically, so a cost estimate
    reflects only how many phases a preset runs — not what its models cost.
    The pre-run estimate is skipped in that state; the mid-run ceiling still
    applies, and it measures real spend rather than estimating it.
    """
    try:
        from reasoner.domain.pricing import PRICING_DB

        return len(PRICING_DB) > 1
    except Exception as exc:
        # Reported as "prices are not loaded", which is also what a genuinely
        # absent openrouter_models.json looks like. The caller reads it as
        # permission to skip the per-run ceiling entirely, so an import that
        # breaks for any other reason silently unbinds that cap.
        return degraded("spend_limit.pricing_data_available", False, exc=exc)


def global_ceiling() -> TierSpendLimits:
    """Deployment-wide ceiling from settings. 0.0 on either axis = unlimited."""
    from reasoner.core.settings import settings

    return TierSpendLimits(
        per_run_usd=max(settings.SPEND_CAP_PER_RUN_USD, UNLIMITED),
        monthly_usd=max(settings.SPEND_CAP_MONTHLY_USD, UNLIMITED),
    )


def resolve_spend_limits(tier: SubscriptionTier | str | None) -> TierSpendLimits:
    """Effective ceilings for a tier, with the global cap layered on top."""
    return limits_for_tier(tier).tightest(global_ceiling())


async def resolve_user_tier(
    user_id: str | None,
    *,
    timeout: float | None = None,
    use_fallback_cache: bool = True,
) -> SubscriptionTier:
    """Resolve the tier a user is entitled to from their subscription.

    Falls back to FREE on every uncertain path — no user, no subscription, a
    status that does not entitle, or a lookup failure — so an outage can
    never hand out a paid tier. The repository returns the newest row without
    filtering on status, so the status check has to happen here.

    The lookup is bounded by *timeout* (default TIER_LOOKUP_TIMEOUT_S). A
    timeout or error is remembered for FALLBACK_CACHE_TTL_S so an outage costs
    one wait per window, not one per request; a caller that makes a final
    decision (the run gate) passes ``use_fallback_cache=False`` to bypass and
    not write that memory.
    """
    if not user_id:
        return SubscriptionTier.FREE
    if use_fallback_cache and _fallback_active(user_id):
        return SubscriptionTier.FREE

    budget = TIER_LOOKUP_TIMEOUT_S if timeout is None else timeout
    try:
        repo = _get_subscription_repo()
        subscription = await asyncio.wait_for(
            repo.get_subscription_by_user(user_id), timeout=budget
        )
    except TimeoutError:
        logger.warning(
            "Subscription lookup timed out after %.1fs; defaulting to FREE tier", budget
        )
        if use_fallback_cache:
            _remember_fallback(user_id)
        return SubscriptionTier.FREE
    except Exception:
        logger.warning("Subscription lookup failed; defaulting to FREE tier", exc_info=True)
        if use_fallback_cache:
            _remember_fallback(user_id)
        return SubscriptionTier.FREE

    if subscription is None or subscription.status not in _ENTITLED_STATUSES:
        return SubscriptionTier.FREE
    return subscription.tier


def apply_spend_limits(
    state,
    tier: SubscriptionTier,
    billing_subject: str | None,
) -> TierSpendLimits:
    """Stamp the resolved ceilings onto pipeline state for the executor.

    `billing_subject` is what the monthly ceiling aggregates over. Without a
    user id there is nothing stable to aggregate on, so the monthly ceiling
    is left off and only the per-run one applies.
    """
    limits = resolve_spend_limits(tier)
    subject = billing_subject or ""

    state.spend_cap_per_run_usd = limits.per_run_usd
    state.spend_cap_monthly_usd = limits.monthly_usd if subject else UNLIMITED
    state.billing_subject = subject
    state.subscription_tier = tier.value
    return limits


# Context carried into a single phase call. Phases re-send the problem plus
# accumulated prior output, so this is a flat working assumption rather than
# a per-phase measurement.
_ASSUMED_INPUT_TOKENS_PER_ROLE = 2000


def estimate_run_cost(preset_id: str) -> float:
    """Estimate the USD cost of one run of a preset, before running it.

    Sums each routed role at its own phase token budget and its own model's
    price, so a preset that fans out over more (or pricier) models estimates
    higher — which is what separates a premium run from a budget one.

    Deliberately an approximation: it assumes one call per role and a flat
    input size, and it cannot see retries. The authoritative figure is the
    cost accumulated during the run, which the executor enforces against the
    same ceiling.
    """
    from reasoner.core.constants import DEFAULT_MAX_TOKENS, PHASE_TOKEN_BUDGETS
    from reasoner.infrastructure.llm.pricing_resolver import get_pricing

    routing = _preset_routing(preset_id)
    if not routing:
        return 0.0

    total = 0.0
    for role, model_id in routing.items():
        output_tokens = PHASE_TOKEN_BUDGETS.get(role, DEFAULT_MAX_TOKENS)
        pricing = get_pricing(model_id)
        total += pricing.calculate_cost(_ASSUMED_INPUT_TOKENS_PER_ROLE, output_tokens)
    return total


def _preset_routing(preset_id: str) -> dict[str, str]:
    """Role → model map for a preset, empty when the preset is unknown.

    An unknown preset yields no estimate rather than a guessed one; the
    mid-run ceiling still bounds it.
    """
    try:
        from reasoner.presets import PRESETS

        preset = PRESETS.get(preset_id)
    except Exception as exc:
        # No routing makes estimate_run_cost return 0.0, and 0.0 is under
        # every per-run ceiling, so this failure reads downstream as "this
        # run is free" rather than "this run could not be priced".
        return degraded("spend_limit.preset_routing", {}, exc=exc)

    if preset is None:
        return {}

    routing = dict(getattr(preset, "routing", None) or {})
    primary = getattr(preset, "primary_id", None)
    if primary and "primary" not in routing:
        routing["primary"] = primary
    return routing


def check_run_allowed(
    preset_id: str,
    tier: SubscriptionTier,
    billing_subject: str | None = None,
) -> SpendRejection | None:
    """Refuse a run the caller's plan cannot take, before spending on it.

    Returns None when the run may proceed. Three refusals, cheapest check
    first:

      * the preset is locked to a higher plan — exact, from the preset's own
        `required_tier`, so a free user gets "upgrade" instead of a run that
        dies half way through;
      * the estimated cost already exceeds the per-run ceiling (only when
        real per-model pricing is loaded — see `pricing_data_available`);
      * the subject has already spent their month, so the next run has
        nowhere to go.
    """
    required = required_tier_for(preset_id)
    if not tier_satisfies(tier, required):
        return SpendRejection(
            reason=(
                f"Preset '{preset_id}' requires the {required.value} plan; "
                f"this account is on {tier.value}."
            ),
            cap_type="preset_tier",
            cap_usd=UNLIMITED,
            estimated_usd=0.0,
            tier=tier,
            required_tier=required,
        )

    limits = resolve_spend_limits(tier)

    if limits.per_run_usd > UNLIMITED and pricing_data_available():
        estimated = estimate_run_cost(preset_id)
        if estimated > limits.per_run_usd:
            return SpendRejection(
                reason=(
                    f"Preset '{preset_id}' costs about ${estimated:.2f} per run, "
                    f"above the ${limits.per_run_usd:.2f} per-run limit on the "
                    f"{tier.value} plan."
                ),
                cap_type="per_run",
                cap_usd=limits.per_run_usd,
                estimated_usd=estimated,
                tier=tier,
            )

    if billing_subject and limits.monthly_usd > UNLIMITED:
        from reasoner.infrastructure.llm import spend_tracker

        spent = spend_tracker.get(billing_subject)
        if spent >= limits.monthly_usd:
            return SpendRejection(
                reason=(
                    f"Monthly usage limit reached (${spent:.2f} of "
                    f"${limits.monthly_usd:.2f} on the {tier.value} plan)."
                ),
                cap_type="monthly",
                cap_usd=limits.monthly_usd,
                estimated_usd=spent,
                tier=tier,
            )

    return None


def required_tier_for(preset_id: str) -> SubscriptionTier:
    """Minimum plan a preset is available on; FREE when it cannot be resolved.

    Shared by the runtime gate (check_run_allowed) and the early HTTP gate in
    api/dependencies.py, so both agree on what a preset costs in plan terms.
    """
    try:
        from reasoner.domain.preset_core import get_preset_tier

        return get_preset_tier(preset_id)
    except Exception as exc:
        # FREE is the lowest rank, so preflight's tier refusal can never
        # fire while this is failing: every preset looks available on every
        # plan. check_run_allowed is the only entitlement gate that always
        # runs (the early HTTP gate in api/dependencies.py is opt-in), so a
        # lookup that has silently stopped checking is worse than none.
        return degraded("spend_limit.required_tier", SubscriptionTier.FREE, exc=exc)


# ── Subscription repository singleton ──

_subscription_repo = None


def _get_subscription_repo():
    """Cached subscription repository.

    Tier is resolved on every run, but subscriptions only change via billing
    webhooks, which invalidate the cache entry directly.
    """
    global _subscription_repo
    if _subscription_repo is None:
        from reasoner.core.settings import settings
        from reasoner.infrastructure.persistence.cached_subscription_repo import (
            CachedSubscriptionRepository,
        )
        from reasoner.infrastructure.persistence.subscription_repo import (
            PostgresSubscriptionRepository,
        )

        dsn = settings.DATABASE_URL.replace("+asyncpg", "")
        pg_repo = PostgresSubscriptionRepository(dsn, pool_size=settings.DB_POOL_SIZE)
        _subscription_repo = CachedSubscriptionRepository(pg_repo)
    return _subscription_repo


def _reset_subscription_repo() -> None:
    """Reset the repository singleton (used by tests)."""
    global _subscription_repo
    _subscription_repo = None
    _fallback_until.clear()


__all__ = [
    "SpendRejection",
    "pricing_data_available",
    "global_ceiling",
    "resolve_spend_limits",
    "resolve_user_tier",
    "required_tier_for",
    "tier_satisfies",
    "apply_spend_limits",
    "estimate_run_cost",
    "check_run_allowed",
]
