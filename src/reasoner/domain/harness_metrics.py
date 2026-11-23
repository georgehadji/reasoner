"""Harness-level metrics value objects for the Code-as-Agent-Harness Scorecard (#2).

All dataclasses use all-default fields for ``--resume`` backward compatibility.
Metrics are computed purely from existing TelemetryStore columns — no schema change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PhaseMetrics:
    """Aggregated telemetry for a single phase within a preset run window.

    All durations in seconds, costs in USD, tokens as integers.
    """
    phase_name: str = ""
    model_id: str = ""
    total_calls: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: float = 0.0
    total_tokens: int = 0
    avg_quality_score: float = 0.0
    quality_passed_count: int = 0
    quality_failed_count: int = 0
    fallback_count: int = 0
    retry_count: int = 0

    @property
    def avg_duration_ms(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_duration_ms / self.total_calls

    @property
    def avg_cost_usd(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.total_cost_usd / self.total_calls

    @property
    def quality_pass_rate(self) -> float:
        total = self.quality_passed_count + self.quality_failed_count
        if total == 0:
            return 0.0
        return self.quality_passed_count / total

    @property
    def fallback_rate(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.fallback_count / self.total_calls


@dataclass
class PresetScorecard:
    """Aggregated harness metrics for one preset over a time window."""
    preset_name: str = ""
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: float = 0.0
    total_tokens: int = 0
    phase_metrics: list[PhaseMetrics] = field(default_factory=list)
    fallback_events: list[dict[str, Any]] = field(default_factory=list)
    recovery_count: int = 0  # runs with fallbacks that still completed

    @property
    def completion_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.completed_runs / self.total_runs

    @property
    def avg_duration_ms(self) -> float:
        if self.completed_runs == 0:
            return 0.0
        return self.total_duration_ms / self.completed_runs

    @property
    def avg_cost_usd(self) -> float:
        if self.completed_runs == 0:
            return 0.0
        return self.total_cost_usd / self.completed_runs

    @property
    def recovery_ability(self) -> float:
        """Fraction of runs with fallbacks that still completed successfully."""
        if self.fallback_events and self.completed_runs > 0:
            return self.recovery_count / max(len(self.fallback_events), 1)
        return 1.0  # no fallbacks = perfect recovery (nothing to recover from)


@dataclass
class HarnessScorecard:
    """Complete harness scorecard for one query over a time window."""
    presets: dict[str, PresetScorecard] = field(default_factory=dict)
    window_days: int = 7
    total_cost_usd: float = 0.0
    total_runs: int = 0

    @property
    def preset_count(self) -> int:
        return len(self.presets)

    @property
    def overall_completion_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        completed = sum(p.completed_runs for p in self.presets.values())
        return completed / self.total_runs

    def to_dict(self) -> dict[str, Any]:
        """Serialise for API/CLI output. Not a full round-trip — read-only model."""
        return {
            "window_days": self.window_days,
            "presets": {
                name: {
                    "total_runs": p.total_runs,
                    "completed_runs": p.completed_runs,
                    "failed_runs": p.failed_runs,
                    "completion_rate": round(p.completion_rate, 3),
                    "avg_duration_ms": round(p.avg_duration_ms, 1),
                    "avg_cost_usd": round(p.avg_cost_usd, 6),
                    "total_cost_usd": round(p.total_cost_usd, 6),
                    "total_tokens": p.total_tokens,
                    "recovery_ability": round(p.recovery_ability, 3),
                    "phases": [
                        {
                            "phase": pm.phase_name,
                            "model": pm.model_id,
                            "calls": pm.total_calls,
                            "cost": round(pm.total_cost_usd, 6),
                            "avg_ms": round(pm.avg_duration_ms, 1),
                            "avg_tokens": pm.total_tokens // max(pm.total_calls, 1),
                            "quality_pass_rate": round(pm.quality_pass_rate, 3),
                            "fallback_rate": round(pm.fallback_rate, 3),
                        }
                        for pm in p.phase_metrics
                    ],
                }
                for name, p in self.presets.items()
            },
            "summary": {
                "total_runs": self.total_runs,
                "total_cost_usd": round(self.total_cost_usd, 6),
                "completion_rate": round(self.overall_completion_rate, 3),
                "presets_used": self.preset_count,
            },
        }


_RISK_TIERS = frozenset({"safe", "cost", "safety"})
_COMPONENT_TYPES = frozenset({"preset", "routing", "budget", "threshold", "prompt"})


@dataclass(frozen=True)
class HarnessMutation:
    """A governed change-contract for harness mutation (#4).

    Immutable once created. Validated by HarnessGuard before evaluation.
    Promoted only after regression-free evaluation against held-out problems.
    """
    target: str = ""              # "preset:debate-budget.scoring"
    component: str = ""            # preset | routing | budget | threshold | prompt
    failure_mode: str = ""         # what symptom it targets
    predicted_effect: str = ""     # measurable hypothesis
    invariant_preserved: str = ""  # e.g. "scoring stays cross-lab"
    rollback: str = ""             # how to revert
    risk_tier: str = "safe"        # safe | cost | safety

    def __post_init__(self) -> None:
        if self.risk_tier not in _RISK_TIERS:
            object.__setattr__(self, "risk_tier", "safe")
        if self.component not in _COMPONENT_TYPES:
            object.__setattr__(self, "component", "preset")

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "component": self.component,
            "failure_mode": self.failure_mode,
            "predicted_effect": self.predicted_effect,
            "invariant_preserved": self.invariant_preserved,
            "rollback": self.rollback,
            "risk_tier": self.risk_tier,
        }
