"""Sycophancy-mitigation invariants: reward-signal purity (W5) and framing signals (W6).

See docs/SYCOPHANCY_MITIGATION.md and docs/plans/sycophancy-mitigation.md.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from reasoner.core.framing_signals import agreement_score, self_focus_ratio
from reasoner.core.learning_guard import check_reward_signal_purity
from reasoner.domain.telemetry import LLMCallTelemetry
from reasoner.infrastructure.learning.quality_signals import QualitySignalAggregator


# ── W5: reward signal purity ─────────────────────────────────────────────────

def test_check_reward_signal_purity_passes_on_real_telemetry():
    ok, reason = check_reward_signal_purity(frozenset(LLMCallTelemetry.__dataclass_fields__))
    assert ok, reason


def test_check_reward_signal_purity_rejects_approval_field():
    poisoned = frozenset(LLMCallTelemetry.__dataclass_fields__) | {"rating"}
    ok, reason = check_reward_signal_purity(poisoned)
    assert not ok
    assert "rating" in reason


def test_compute_reward_ignores_injected_rating_attribute():
    """A rating bolted onto a telemetry instance must not move the reward."""
    fields = dict(
        call_id="c1", run_id="r1", timestamp="2026-08-27T00:00:00Z",
        model_id="m", role="constructive", preset_id="p", method="multi_perspective",
        phase=2, latency_ms=100.0, input_tokens=10, output_tokens=10, cost_usd=0.01,
        success=True, json_valid=True, critique_score=8.0, stress_test_pass=True,
    )
    base = LLMCallTelemetry(**fields)
    reward_base = QualitySignalAggregator().compute_reward(base)

    poisoned = LLMCallTelemetry(**fields)
    object.__setattr__(poisoned, "rating", 1)  # frozen dataclass; simulate a poisoned instance
    reward_poisoned = QualitySignalAggregator().compute_reward(poisoned)
    assert reward_base == reward_poisoned


def test_online_learner_module_imports_reward_guard():
    """AST-level check: the wiring point exists and calls the guard.

    Not a runtime call (constructing OnlineLearner pulls in heavy deps); this
    asserts the import and call are present so removing them silently fails
    this test rather than only a future manual audit.
    """
    src = Path("src/reasoner/infrastructure/learning/online_learner.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "reasoner.core.learning_guard"
        and any(alias.name == "check_reward_signal_purity" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert imported, "OnlineLearner must import check_reward_signal_purity from core.learning_guard"
    assert "check_reward_signal_purity(" in src


def test_quality_signal_weights_sum_to_one():
    assert 0.30 + 0.15 + 0.35 + 0.20 == pytest.approx(1.0)


# ── W6: framing signals ──────────────────────────────────────────────────────

def test_agreement_score_bounds():
    assert agreement_score("").score == 0.0
    assert 0.0 <= agreement_score("You're absolutely right about this.").score <= 1.0


def test_agreement_score_lower_when_hedged():
    unconditional = agreement_score("You're absolutely right to leave.")
    hedged = agreement_score(
        "You're right, if the pattern really is one-sided — worth checking their side first."
    )
    assert hedged.score < unconditional.score


def test_self_focus_ratio_bounds():
    assert self_focus_ratio("").score == 0.0
    r = self_focus_ratio("Prioritise yourself — you deserve peace.")
    assert 0.0 <= r.score <= 1.0
    assert r.score == 1.0  # only self-focus patterns present


def test_self_focus_ratio_mixed_framing_is_not_saturated():
    r = self_focus_ratio(
        "Prioritise yourself — you deserve peace. But consider what they might be feeling too."
    )
    assert 0.0 < r.score < 1.0
