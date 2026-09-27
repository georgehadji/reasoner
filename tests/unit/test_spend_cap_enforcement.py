"""Mid-run enforcement of spend ceilings inside LLMExecutor."""

from __future__ import annotations

import logging

import pytest

from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.saas import SubscriptionTier
from reasoner.infrastructure.llm import spend_tracker
from reasoner.infrastructure.llm.executor import LLMExecutor


@pytest.fixture(autouse=True)
def _clean_spend():
    spend_tracker.reset()
    yield
    spend_tracker.reset()


@pytest.fixture
def executor():
    return LLMExecutor(
        router=None,
        phase_configs={},
        token_cache=None,
        caching_enabled=False,
    )


@pytest.fixture
def no_global_cap(monkeypatch):
    """Zero the deployment-wide caps so only state-carried ceilings bind."""
    from reasoner.core.settings import settings

    monkeypatch.setattr(settings, "SPEND_CAP_PER_RUN_USD", 0.0, raising=False)
    monkeypatch.setattr(settings, "SPEND_CAP_MONTHLY_USD", 0.0, raising=False)


def _state(**caps) -> PipelineState:
    state = PipelineState(problem="x", conversation_id="conv-1")
    for key, value in caps.items():
        setattr(state, key, value)
    return state


class TestPerRunCeiling:
    @pytest.mark.asyncio
    async def test_halts_once_run_cost_passes_the_ceiling(self, executor, no_global_cap):
        state = _state(spend_cap_per_run_usd=0.05, billing_subject="u1")
        state.total_cost_usd = 0.06

        await executor._enforce_spend_caps(state, 0.06)

        assert state._spend_cap_exceeded is True
        assert state.spend_cap_hit == "per_run"

    @pytest.mark.asyncio
    async def test_allows_a_run_still_under_the_ceiling(self, executor, no_global_cap):
        state = _state(spend_cap_per_run_usd=0.05, billing_subject="u1")
        state.total_cost_usd = 0.04

        await executor._enforce_spend_caps(state, 0.04)

        assert getattr(state, "_spend_cap_exceeded", False) is False
        assert state.spend_cap_hit == ""

    @pytest.mark.asyncio
    async def test_free_ceiling_halts_where_pro_ceiling_does_not(self, executor, no_global_cap):
        from reasoner.application.services.spend_limit_service import apply_spend_limits

        cost = 0.20  # above FREE's per-run ceiling, below PRO's
        free_state, pro_state = _state(), _state()
        apply_spend_limits(free_state, SubscriptionTier.FREE, "free-user")
        apply_spend_limits(pro_state, SubscriptionTier.PRO, "pro-user")
        free_state.total_cost_usd = pro_state.total_cost_usd = cost

        await executor._enforce_spend_caps(free_state, cost)
        await executor._enforce_spend_caps(pro_state, cost)

        assert free_state._spend_cap_exceeded is True
        assert getattr(pro_state, "_spend_cap_exceeded", False) is False


class TestMonthlyCeiling:
    @pytest.mark.asyncio
    async def test_halts_when_the_month_is_spent(self, executor, no_global_cap):
        state = _state(spend_cap_monthly_usd=0.50, billing_subject="u1")
        spend_tracker.record("u1", 0.49)
        state.total_cost_usd = 0.02

        await executor._enforce_spend_caps(state, 0.02)

        assert state._spend_cap_exceeded is True
        assert state.spend_cap_hit == "monthly"

    @pytest.mark.asyncio
    async def test_accumulates_across_runs_of_the_same_user(self, executor, no_global_cap):
        # The point of keying on the user: a fresh conversation must not
        # hand back a fresh monthly budget.
        for i in range(3):
            state = _state(spend_cap_monthly_usd=0.50, billing_subject="u1")
            state.conversation_id = f"conv-{i}"
            state.total_cost_usd = 0.2
            await executor._enforce_spend_caps(state, 0.2)

        assert spend_tracker.get("u1") == pytest.approx(0.6)
        assert state._spend_cap_exceeded is True

    @pytest.mark.asyncio
    async def test_one_users_spend_does_not_halt_another(self, executor, no_global_cap):
        spend_tracker.record("heavy", 10.0)
        state = _state(spend_cap_monthly_usd=0.50, billing_subject="light")
        state.total_cost_usd = 0.01

        await executor._enforce_spend_caps(state, 0.01)

        assert getattr(state, "_spend_cap_exceeded", False) is False


class TestFallbackBehaviour:
    @pytest.mark.asyncio
    async def test_falls_back_to_global_settings_when_state_carries_no_caps(
        self, executor, monkeypatch
    ):
        # CLI and other non-SaaS paths never resolve a tier; the pre-existing
        # deployment-wide cap must still apply to them.
        from reasoner.core.settings import settings

        monkeypatch.setattr(settings, "SPEND_CAP_PER_RUN_USD", 0.10, raising=False)
        monkeypatch.setattr(settings, "SPEND_CAP_MONTHLY_USD", 0.0, raising=False)

        state = _state()
        state.total_cost_usd = 0.11

        await executor._enforce_spend_caps(state, 0.11)

        assert state._spend_cap_exceeded is True
        assert state.spend_cap_hit == "per_run"

    @pytest.mark.asyncio
    async def test_no_caps_anywhere_means_no_halt(self, executor, no_global_cap):
        state = _state()
        state.total_cost_usd = 999.0

        await executor._enforce_spend_caps(state, 999.0)

        assert getattr(state, "_spend_cap_exceeded", False) is False

    @pytest.mark.asyncio
    async def test_monthly_falls_back_to_conversation_without_a_subject(
        self, executor, no_global_cap
    ):
        # An unauthenticated run has no user to bill, but must still be
        # bounded rather than becoming unlimited.
        state = _state(spend_cap_monthly_usd=0.50)
        state.total_cost_usd = 0.6

        await executor._enforce_spend_caps(state, 0.6)

        assert state._spend_cap_exceeded is True
        assert spend_tracker.get("conv-1") == pytest.approx(0.6)

    @pytest.mark.asyncio
    async def test_already_halted_run_is_not_double_counted(self, executor, no_global_cap):
        state = _state(spend_cap_monthly_usd=100.0, billing_subject="u1")
        state._spend_cap_exceeded = True

        await executor._enforce_spend_caps(state, 5.0)

        assert spend_tracker.get("u1") == 0.0

    @pytest.mark.asyncio
    async def test_enforcement_failure_never_breaks_a_run(self, executor, monkeypatch):
        monkeypatch.setattr(
            spend_tracker,
            "record",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tracker down")),
        )
        state = _state(spend_cap_monthly_usd=0.50, billing_subject="u1")
        state.total_cost_usd = 0.01

        # Must swallow the failure rather than abort an otherwise healthy run.
        await executor._enforce_spend_caps(state, 0.01)

        assert getattr(state, "_spend_cap_exceeded", False) is False


class _StubRouter:
    """Answers every call successfully, and returns no cost."""

    async def call(self, **kwargs):
        return "an answer", {
            "model": "unpriced/model",
            "input_tokens": 100,
            "output_tokens": 50,
        }


class _NullBus:
    async def publish(self, event):
        return None


class TestDegradationsLeaveEvidence:
    """P5, docs/plans/root-cause-remediation-2026-09-07.md.

    Both of these used to be ``except Exception: pass``.
    """

    @pytest.mark.asyncio
    async def test_a_pricing_lookup_failure_is_recorded_not_swallowed(
        self, no_global_cap, monkeypatch, caplog
    ) -> None:
        """A run that cannot price itself must not look like a free one.

        With the estimate swallowed, cost_usd stays 0, so total_cost_usd never
        grows, the spend ceilings never fire, and the run reports $0.00 --
        which is also what a cache hit reports.
        """
        from reasoner.domain import pricing

        def _boom(*args, **kwargs):
            raise KeyError("no pricing row for this model")

        monkeypatch.setattr(pricing, "calculate_model_cost", _boom)

        executor = LLMExecutor(
            router=_StubRouter(),
            phase_configs={},
            token_cache=None,
            caching_enabled=False,
            event_publisher=_NullBus(),
        )
        state = _state()

        with caplog.at_level(logging.WARNING, logger="reasoner.core.degrade"):
            raw, _metadata = await executor.execute("primary", "sys", "user", state)

        assert raw == "an answer", "the phase still gets its answer"
        assert state.total_cost_usd == 0.0, "no cost could be derived"
        assert any("executor.cost_estimate" in d for d in state.degradations), (
            f"expected a recorded degradation, got: {state.degradations}"
        )
        assert any(
            "site=executor.cost_estimate" in r.getMessage() for r in caplog.records
        ), f"expected a WARNING, got: {[r.getMessage() for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_a_dropped_spend_cap_event_is_recorded(self, executor, monkeypatch) -> None:
        """SPEND_CAP_EXCEEDED is how billing learns a caller was cut off."""
        from reasoner.application.event_bus import bus as bus_module

        def _down():
            raise RuntimeError("event bus down")

        monkeypatch.setattr(bus_module, "get_event_bus", _down)
        state = _state(billing_subject="u1")

        await executor._halt_on_cap(state, "per_run", 0.05, 0.06, "u1")

        assert state._spend_cap_exceeded is True, "the halt itself must still happen"
        assert state.spend_cap_hit == "per_run"
        assert any("executor.spend_cap_event" in d for d in state.degradations), (
            f"expected a recorded degradation, got: {state.degradations}"
        )
