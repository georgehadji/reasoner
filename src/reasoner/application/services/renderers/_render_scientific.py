from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.text import Text

from reasoner.application.services.renderers._shared import (
    _duration,
    _get_attr,
    _render_action_blueprint,
    _render_errors,
    _render_stress,
    console,
    render_routing_table,
)
from reasoner.domain.pipeline_state import PipelineState


def _render_scientific(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold green]SCIENTIFIC INQUIRY  ({duration:.1f}s)[/bold green]")
    render_routing_table(state)

    hypotheses = state.scientific_state.get("hypotheses") or []
    if hypotheses:
        hy_text = Text()
        for h in hypotheses:
            hy_text.append(f"H{h.get('id')}: {h.get('statement')}\n", style="bold white")
            hy_text.append(f"  Logic: {h.get('logic')}\n", style="dim")
            hy_text.append(f"  Falsifiability: {h.get('falsifiability')}\n\n", style="dim yellow")
        console.print(Panel(hy_text, title="[cyan]Phase 2 — Hypotheses[/cyan]", box=box.ROUNDED))

    test_results = state.scientific_state.get("test_results") or []
    if test_results:
        test_text = Text()
        for res in test_results:
            color = "green" if res.get("result") == "SUPPORTED" else "red"
            test_text.append(f"Test H{res.get('hypothesis_id')}: ", style="bold")
            test_text.append(f"{res.get('result')}\n", style=color)
            test_text.append(f"  Experiment: {res.get('experiment')}\n", style="white")
            test_text.append(f"  Reasoning: {res.get('reasoning')}\n\n", style="dim")
        console.print(Panel(test_text, title="[cyan]Phase 3 — Falsification Tests[/cyan]", box=box.ROUNDED))

    _render_stress(state)

    if state.final_solution:
        fs = state.final_solution
        console.print(Panel(_get_attr(fs, 'core_solution', ''), title="[bold green]SCIENTIFIC SYNTHESIS[/bold green]", box=box.DOUBLE, border_style="green"))
        if _get_attr(fs, 'critical_insights', []):
            ins_text = Text()
            for i, insight in enumerate(_get_attr(fs, 'critical_insights', []), 1):
                ins_text.append(f"{i}. {insight}\n\n")
            console.print(Panel(ins_text, title="[yellow]Key Findings[/yellow]", box=box.ROUNDED))
        _render_action_blueprint(state)
        meta = _get_attr(fs, 'meta_audit', {})
        if any(_get_attr(meta, k) for k in ('most_dangerous_assumption', 'dominant_bias', 'remaining_uncertainty', 'assumption_failure_impact', 'non_obvious_insight')):
            meta_text = (
                f"[bold]Most dangerous assumption:[/bold] {_get_attr(meta, 'most_dangerous_assumption', '')}\n"
                f"[bold]Dominant bias:[/bold] {_get_attr(meta, 'dominant_bias', '')}\n"
                f"[bold]Remaining uncertainty:[/bold] {_get_attr(meta, 'remaining_uncertainty', '')}\n"
                f"[bold]If main assumption fails:[/bold] {_get_attr(meta, 'assumption_failure_impact', '')}\n"
                f"[bold]Non-obvious insight:[/bold] [italic]{_get_attr(meta, 'non_obvious_insight', '')}[/italic]"
            )
            console.print(Panel(meta_text, title="[cyan]Meta-Cognitive Audit[/cyan]", box=box.ROUNDED))
    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# SOCRATIC RENDERER
# ─────────────────────────────────────────────────────────────────────


