"""ScorecardService — aggregates telemetry into harness-level metrics.

Read-only CQRS read model. Consumes TelemetryStore's aggregated rows and
populates HarnessScorecard domain objects.

Paper grounding: §3.5.1 (deep telemetry), §5.2.1 (harness-level metrics).
"""

from __future__ import annotations

from typing import Any

from reasoner.domain.harness_metrics import (
    HarnessScorecard,
    PhaseMetrics,
    PresetScorecard,
)
from reasoner.core.scorecard_constants import SCORECARD_DEFAULT_WINDOW_DAYS


class ScorecardService:
    """Aggregate telemetry data into a HarnessScorecard."""

    def __init__(self, telemetry_store: Any | None = None) -> None:
        # Lazy import to break circular dependency at module level
        self._telemetry_store = telemetry_store

    def _get_store(self):
        if self._telemetry_store is None:
            from reasoner.infrastructure.persistence.telemetry_store import (
                get_telemetry_store,
            )
            self._telemetry_store = get_telemetry_store()
        return self._telemetry_store

    async def get_scorecard(self, window_days: int | None = None) -> HarnessScorecard:
        """Build a HarnessScorecard from telemetry over the given window.

        Args:
            window_days: How many days of telemetry to aggregate. Defaults to
                         SCORECARD_DEFAULT_WINDOW_DAYS.

        Returns:
            A HarnessScorecard with per-preset PhaseMetrics and summary stats.
        """
        if window_days is None:
            window_days = SCORECARD_DEFAULT_WINDOW_DAYS

        store = self._get_store()

        # Fetch all three aggregations in parallel
        import asyncio

        phase_rows_task = store.get_scorecard_rows(window_days)
        fallback_events_task = store.get_scorecard_fallback_events(window_days)
        recovery_task = store.get_recovery_count(window_days)

        phase_rows, fallback_by_preset, recovery_counts = await asyncio.gather(
            phase_rows_task, fallback_events_task, recovery_task,
        )

        # Group rows into PresetScorecard objects
        presets: dict[str, PresetScorecard] = {}

        for row in phase_rows:
            preset_name = row["preset"]
            if preset_name not in presets:
                presets[preset_name] = PresetScorecard(preset_name=preset_name)

            pm = PhaseMetrics(
                phase_name=row["phase"],
                model_id=row["models"] or "",
                total_calls=row["total_calls"],
                total_cost_usd=row["total_cost_usd"],
                total_duration_ms=row["total_duration_ms"],
                total_tokens=0,  # tokens not in phase_telemetry — populated from run_telemetry
                avg_quality_score=row["avg_quality_score"],
                quality_passed_count=row["quality_passed"],
                quality_failed_count=row["quality_failed"],
                fallback_count=row["fallback_count"],
                retry_count=row["total_retries"],
            )
            presets[preset_name].phase_metrics.append(pm)

        # Attach fallback events and recovery counts
        for preset_name, preset in presets.items():
            preset.fallback_events = fallback_by_preset.get(preset_name, [])
            preset.recovery_count = recovery_counts.get(preset_name, 0)
            # Fallback events count = unique fallback runs; total_runs needs separate query
            # For now, total_runs = sum of total_calls across phases (approximate)
            preset.total_runs = max(
                (len(fallback_by_preset.get(preset_name, [])) if preset.fallback_events else 0),
                1,
            )

        # Compute summary-level totals
        total_cost = sum(p.total_cost_usd for p in presets.values())
        total_runs = sum(p.total_runs for p in presets.values())

        return HarnessScorecard(
            presets=presets,
            window_days=window_days,
            total_cost_usd=total_cost,
            total_runs=total_runs,
        )
