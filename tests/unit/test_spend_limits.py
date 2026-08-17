"""Per-tier LLM spend ceilings: resolution, preflight refusal, mid-run halt."""

from __future__ import annotations

import pytest

from reasoner.application.services import spend_limit_service as svc
from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.saas import SubscriptionTier
from reasoner.domain.spend_limits import (
    TIER_SPEND_LIMITS,
    UNLIMITED,
    TierSpendLimits,
    limits_for_tier,
)
from reasoner.infrastructure.llm import spend_tracker


@pytest.fixture(autouse=True)
def _clean_spend():
    spend_tracker.reset()
    yield
    spend_tracker.reset()


@pytest.fixture
def no_global_cap(monkeypatch):
    """Neutralise the deployment-wide cap so tier defaults are what bind."""
    monkeypatch.setattr(
        svc, "global_ceiling", lambda: TierSpendLimits(UNLIMITED, UNLIMITED)
    )


class TestTierLimits:
    def test_free_is_tighter_than_pro_on_both_axes(self):
        free = limits_for_tier(SubscriptionTier.FREE)
        pro = limits_for_tier(SubscriptionTier.PRO)
        assert free.per_run_usd < pro.per_run_usd
        assert free.monthly_usd < pro.monthly_usd

    def test_every_tier_is_bounded(self):
        # An unbounded tier would defeat the point of the ceiling entirely.
        for tier, limits in TIER_SPEND_LIMITS.items():
            assert limits.per_run_usd > 0, tier
            assert limits.monthly_usd > 0, tier

    def test_accepts_string_tier(self):
        assert limits_for_tier("pro") == limits_for_tier(SubscriptionTier.PRO)

    @pytest.mark.parametrize("bad", [None, "", "platinum", "FREE_TIER"])
    def test_unknown_tier_falls_back_to_free_not_unlimited(self, bad):
        assert limits_for_tier(bad) == TIER_SPEND_LIMITS[SubscriptionTier.FREE]


class TestTightest:
    def test_positive_ceilings_take_the_lower(self):
        merged = TierSpendLimits(0.50, 8.0).tightest(TierSpendLimits(0.10, 20.0))
        assert merged == TierSpendLimits(0.10, 8.0)

    def test_zero_means_unlimited_and_loses(self):
        # 0.0 disables a cap, so it must not win as a numeric minimum would.
        merged = TierSpendLimits(0.05, 0.50).tightest(TierSpendLimits(0.0, 0.0))
        assert merged == TierSpendLimits(0.05, 0.50)

    def test_both_unlimited_stays_unlimited(self):
        merged = TierSpendLimits(0.0, 0.0).tightest(TierSpendLimits(0.0, 0.0))
        assert merged == TierSpendLimits(0.0, 0.0)

    def test_global_cap_can_tighten_a_tier(self, monkeypatch):
        monkeypatch.setattr(
            svc, "global_ceiling", lambda: TierSpendLimits(0.01, UNLIMITED)
        )
        limits = svc.resolve_spend_limits(SubscriptionTier.ENTERPRISE)
        assert limits.per_run_usd == 0.01
        assert limits.monthly_usd == TIER_SPEND_LIMITS[SubscriptionTier.ENTERPRISE].monthly_usd


class TestApplyToState:
    def test_stamps_limits_onto_state(self, no_global_cap):
        state = PipelineState(problem="x")
        svc.apply_spend_limits(state, SubscriptionTier.PRO, "user-1")

        pro = TIER_SPEND_LIMITS[SubscriptionTier.PRO]
        assert state.spend_cap_per_run_usd == pro.per_run_usd
        assert state.spend_cap_monthly_usd == pro.monthly_usd
        assert state.billing_subject == "user-1"
        assert state.subscription_tier == "pro"

    def test_monthly_cap_is_dropped_without_a_billing_subject(self, no_global_cap):
        # Nothing stable to aggregate a month over, so only per-run applies.
        state = PipelineState(problem="x")
        svc.apply_spend_limits(state, SubscriptionTier.FREE, None)
        assert state.spend_cap_per_run_usd > 0
        assert state.spend_cap_monthly_usd == UNLIMITED

    def test_defaults_are_unset_on_a_bare_state(self):
        state = PipelineState(problem="x")
        assert state.spend_cap_per_run_usd == 0.0
        assert state.spend_cap_monthly_usd == 0.0
        assert state.billing_subject == ""
        assert state.spend_cap_hit == ""


class TestPreflight:
    def test_free_user_refused_a_premium_preset(self, no_global_cap):
        rejection = svc.check_run_allowed("debate-premium", SubscriptionTier.FREE)
        assert rejection is not None
        assert rejection.cap_type == "preset_tier"
        assert rejection.required_tier == SubscriptionTier.PRO

    def test_free_user_allowed_a_budget_preset(self, no_global_cap):
        assert svc.check_run_allowed("debate-budget", SubscriptionTier.FREE) is None

    def test_pro_user_allowed_a_premium_preset(self, no_global_cap):
        assert svc.check_run_allowed("debate-premium", SubscriptionTier.PRO) is None

    def test_monthly_exhaustion_refuses_the_next_run(self, no_global_cap):
        monthly = TIER_SPEND_LIMITS[SubscriptionTier.FREE].monthly_usd
        spend_tracker.record("user-spent", monthly + 0.01)

        rejection = svc.check_run_allowed(
            "debate-budget", SubscriptionTier.FREE, "user-spent"
        )
        assert rejection is not None
        assert rejection.cap_type == "monthly"

    def test_another_users_spend_does_not_refuse_this_one(self, no_global_cap):
        spend_tracker.record("heavy-user", 999.0)
        assert svc.check_run_allowed(
            "debate-budget", SubscriptionTier.FREE, "light-user"
        ) is None

    def test_estimate_check_is_skipped_without_per_model_pricing(self, monkeypatch, no_global_cap):
        # Without openrouter_models.json every model prices identically, so an
        # estimate would reject on phase count alone. It must not run.
        monkeypatch.setattr(svc, "pricing_data_available", lambda: False)
        monkeypatch.setattr(svc, "estimate_run_cost", lambda _p: 999.0)
        assert svc.check_run_allowed("debate-budget", SubscriptionTier.FREE) is None

    def test_estimate_refuses_when_pricing_is_available(self, monkeypatch, no_global_cap):
        monkeypatch.setattr(svc, "pricing_data_available", lambda: True)
        monkeypatch.setattr(svc, "estimate_run_cost", lambda _p: 999.0)

        rejection = svc.check_run_allowed("debate-budget", SubscriptionTier.FREE)
        assert rejection is not None
        assert rejection.cap_type == "per_run"
        assert rejection.estimated_usd == 999.0

    def test_unknown_preset_is_not_refused_on_a_guessed_estimate(self, no_global_cap):
        assert svc.estimate_run_cost("no-such-preset") == 0.0
        assert svc.check_run_allowed("no-such-preset", SubscriptionTier.FREE) is None


class TestEstimate:
    def test_scales_with_the_number_of_routed_roles(self, monkeypatch):
        from reasoner.domain.pricing import ModelPricing

        monkeypatch.setattr(
            svc, "_preset_routing", lambda p: {"a": "m", "b": "m"} if p == "big" else {"a": "m"}
        )
        monkeypatch.setattr(
            "reasoner.application.services.pricing_service.get_pricing",
            lambda _m: ModelPricing(1e-6, 5e-6),
        )
        assert svc.estimate_run_cost("big") > svc.estimate_run_cost("small")

    def test_real_presets_estimate_above_zero(self):
        assert svc.estimate_run_cost("debate-premium") > 0


class TestSpendTracker:
    def test_records_and_accumulates_per_subject(self):
        spend_tracker.record("a", 1.0)
        spend_tracker.record("a", 0.5)
        spend_tracker.record("b", 2.0)
        assert spend_tracker.get("a") == pytest.approx(1.5)
        assert spend_tracker.get("b") == pytest.approx(2.0)

    def test_unknown_subject_is_zero(self):
        assert spend_tracker.get("nobody") == 0.0

    def test_ignores_empty_subject_and_non_positive_cost(self):
        spend_tracker.record("", 5.0)
        spend_tracker.record("c", 0.0)
        spend_tracker.record("c", -3.0)
        assert spend_tracker.get("") == 0.0
        assert spend_tracker.get("c") == 0.0

    def test_reset_targets_one_subject(self):
        spend_tracker.record("a", 1.0)
        spend_tracker.record("b", 1.0)
        spend_tracker.reset("a")
        assert spend_tracker.get("a") == 0.0
        assert spend_tracker.get("b") == pytest.approx(1.0)

    def test_spend_is_scoped_to_the_billing_period(self, monkeypatch):
        spend_tracker.record("a", 5.0)
        assert spend_tracker.get("a") == pytest.approx(5.0)
        # Roll into the next month: last month's total must stop counting.
        monkeypatch.setattr(spend_tracker, "current_period", lambda: "2099-01")
        assert spend_tracker.get("a") == 0.0
