"""ScorecardService — aggregates telemetry into harness-level metrics.

Read-only CQRS read model. Consumes TelemetryStore's aggregated rows and
populates HarnessScorecard domain objects.

Paper grounding: §3.5.1 (deep telemetry), §5.2.1 (harness-level metrics).
"""

from __future__ import annotations

from typing import Any

from reasoner.core.scorecard_constants import SCORECARD_DEFAULT_WINDOW_DAYS
from reasoner.domain.harness_metrics import (
    HarnessScorecard,
    PhaseMetrics,
    PresetScorecard,
)


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

        # Fetch all four aggregations in parallel
        import asyncio

        phase_rows_task = store.get_scorecard_rows(window_days)
        fallback_events_task = store.get_scorecard_fallback_events(window_days)
        recovery_task = store.get_recovery_count(window_days)
        run_counts_task = store.get_run_counts(window_days)

        results = await asyncio.gather(
            phase_rows_task, fallback_events_task, recovery_task, run_counts_task,
            return_exceptions=True
        )

        parsed_results = []
        for i, res in enumerate(results):
            if isinstance(res, BaseException):
                import logging
                logging.getLogger(__name__).warning("Scorecard metric fetch failed (index %d): %s", i, res)
                parsed_results.append([] if i == 0 else {})
            else:
                parsed_results.append(res)

        phase_rows, fallback_by_preset, recovery_counts, run_counts = parsed_results

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

        # Attach run counts, fallback events, and recovery counts
        for preset_name, preset in presets.items():
            counts = run_counts.get(preset_name, {})
            preset.total_runs = counts.get("total_runs", 0)
            preset.completed_runs = counts.get("completed_runs", 0)
            preset.failed_runs = counts.get("failed_runs", 0)
            preset.fallback_events = fallback_by_preset.get(preset_name, [])
            preset.recovery_count = recovery_counts.get(preset_name, 0)
            # Aggregate total cost and duration from phase metrics
            preset.total_cost_usd = sum(pm.total_cost_usd for pm in preset.phase_metrics)
            preset.total_duration_ms = sum(pm.total_duration_ms for pm in preset.phase_metrics)

        # Compute summary-level totals
        total_cost = sum(p.total_cost_usd for p in presets.values())
        total_runs = sum(p.total_runs for p in presets.values())

        return HarnessScorecard(
            presets=presets,
            window_days=window_days,
            total_cost_usd=total_cost,
            total_runs=total_runs,
        )
