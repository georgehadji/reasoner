"""HarnessDiagnosisService — rank harness components by waste/failure (#4).

Paper grounding: §3.5.2 (observe→diagnose). Consumes HarnessScorecard from #2
and ranks harness components (presets, phases, models) by waste and failure rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from reasoner.domain.harness_metrics import HarnessScorecard


@dataclass
class DiagnosisFinding:
    """A single diagnosed issue in the harness."""
    preset: str = ""
    phase: str = ""
    model: str = ""
    metric: str = ""          # "cost" | "fallback_rate" | "quality" | "latency"
    value: float = 0.0
    severity: str = "low"     # "high" | "medium" | "low"
    suggestion: str = ""


@dataclass
class DiagnosisReport:
    """Complete harness diagnosis from Scorecard data."""
    findings: list[DiagnosisFinding] = field(default_factory=list)
    total_waste_usd: float = 0.0
    critical_count: int = 0

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0


class HarnessDiagnosisService:
    """Diagnose harness waste and failure from Scorecard data."""

    def diagnose(self, scorecard: HarnessScorecard) -> DiagnosisReport:
        """Run diagnosis over a Scorecard and return ranked findings.

        Detection criteria:
        - high fallback rate (>= 0.3) → routing issue
        - low quality pass rate (< 0.5) with high cost → bad model fit
        - high cost phase with low quality lift → waste
        - high average latency (> 60s) → timeout risk
        """
        findings: list[DiagnosisFinding] = []
        total_waste = 0.0

        for preset_name, preset_data in scorecard.presets.items():
            for pm in preset_data.phase_metrics:
                # High fallback rate → routing problem
                if pm.fallback_rate >= 0.3 and pm.total_calls >= 5:
                    estimated_waste = pm.total_cost_usd * pm.fallback_rate
                    total_waste += estimated_waste
                    findings.append(DiagnosisFinding(
                        preset=preset_name,
                        phase=pm.phase_name,
                        model=pm.model_id,
                        metric="fallback_rate",
                        value=round(pm.fallback_rate, 3),
                        severity="high" if pm.fallback_rate >= 0.5 else "medium",
                        suggestion=f"Review routing: {pm.model_id} falls back {pm.fallback_rate:.0%} of the time",
                    ))

                # Low quality with non-trivial cost → model mismatch
                if pm.quality_pass_rate < 0.5 and pm.total_cost_usd >= 0.01 and pm.total_calls >= 3:
                    total_waste += pm.total_cost_usd * 0.5
                    findings.append(DiagnosisFinding(
                        preset=preset_name,
                        phase=pm.phase_name,
                        model=pm.model_id,
                        metric="quality",
                        value=round(pm.quality_pass_rate, 3),
                        severity="high" if pm.quality_pass_rate < 0.3 else "medium",
                        suggestion=f"Quality {pm.quality_pass_rate:.0%} for {pm.model_id} — consider a different model",
                    ))

                # High cost phase → investigate
                if pm.total_cost_usd >= 0.05:
                    findings.append(DiagnosisFinding(
                        preset=preset_name,
                        phase=pm.phase_name,
                        model=pm.model_id,
                        metric="cost",
                        value=round(pm.total_cost_usd, 6),
                        severity="medium",
                        suggestion=f"Phase {pm.phase_name} costs ${pm.total_cost_usd:.4f} — review budget",
                    ))

                # High latency
                if pm.avg_duration_ms >= 60_000:
                    findings.append(DiagnosisFinding(
                        preset=preset_name,
                        phase=pm.phase_name,
                        model=pm.model_id,
                        metric="latency",
                        value=round(pm.avg_duration_ms / 1000, 1),
                        severity="medium",
                        suggestion=f"Avg latency {pm.avg_duration_ms/1000:.0f}s — timeout risk",
                    ))

        # Sort by severity then value (highest impact first)
        severity_order = {"high": 0, "medium": 1, "low": 2}
        findings.sort(key=lambda f: (severity_order.get(f.severity, 3), -f.value))

        critical_count = sum(1 for f in findings if f.severity == "high")

        return DiagnosisReport(
            findings=findings,
            total_waste_usd=round(total_waste, 6),
            critical_count=critical_count,
        )
