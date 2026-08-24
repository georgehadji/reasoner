from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from reasoner.application.services.renderers._shared import (
    _duration,
    _get_attr,
    _label_color,
    _render_action_blueprint,
    _render_errors,
    _render_stress,
    console,
    render_routing_table,
)
from reasoner.domain.pipeline_state import PipelineState


def _render_multi_perspective(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold blue]Reasoner v2.0 Pipeline Complete ({duration:.1f}s)[/bold blue]")

    render_routing_table(state)

    console.print(Panel(
        f"[bold]Task Type:[/bold] {(state.task_type.value if hasattr(state.task_type, 'value') else state.task_type) if state.task_type else 'unknown'}\n"
        f"[bold]Rationale:[/bold] {state.task_type_rationale}",
        title="[cyan]Phase 0 — Classification[/cyan]",
        box=box.ROUNDED,
    ))

    if state.decomposition:
        dec = state.decomposition
        sub_problems = dec.sub_problems if hasattr(dec, 'sub_problems') else dec.get('sub_problems', [])
        assumptions = dec.assumptions if hasattr(dec, 'assumptions') else dec.get('assumptions', [])
        dec_text = Text()
        for sp in sub_problems:
            sp_id = sp.id if hasattr(sp, 'id') else sp.get('id', '')
            sp_desc = sp.description if hasattr(sp, 'description') else sp.get('description', '')
            dec_text.append(f"• {sp_id}: {sp_desc}\n", style="white")
        dec_text.append("\nAssumptions:\n", style="bold")
        for a in assumptions:
            a_label = a.label if hasattr(a, 'label') else a.get('label', 'UNKNOWN')
            a_text = a.text if hasattr(a, 'text') else a.get('text', '')
            color = _label_color(a_label)
            label_val = a_label.value if hasattr(a_label, 'value') else a_label
            dec_text.append(f"  [{label_val}] ", style=color)
            dec_text.append(f"{a_text}\n")
        console.print(Panel(dec_text, title="[cyan]Phase 1 — Decomposition[/cyan]", box=box.ROUNDED))

    if state.scores:
        table = Table(title="Phase 3 — Critique Scores", box=box.SIMPLE_HEAVY)
        table.add_column("Perspective", style="cyan")
        table.add_column("Logic", justify="center")
        table.add_column("Evidence", justify="center")
        table.add_column("Resilience", justify="center")
        table.add_column("Feasibility", justify="center")
        table.add_column("Total", justify="center", style="bold")
        table.add_column("Biases")

        for s in sorted(state.scores, key=lambda x: x.total, reverse=True):
            is_top = s.perspective in [c.perspective for c in state.top_candidates]
            row_style = "bold green" if is_top else ""
            table.add_row(
                s.perspective.value,
                f"{s.logical_consistency:.1f}",
                f"{s.evidence_support:.1f}",
                f"{s.failure_resilience:.1f}",
                f"{s.feasibility:.1f}",
                f"[bold]{s.total:.1f}[/bold]",
                ", ".join(s.bias_flags[:2]) if s.bias_flags else "—",
                style=row_style,
            )
        console.print(table)

    _render_stress(state)

    if state.final_solution:
        fs = state.final_solution

        console.print(Panel(
            _get_attr(fs, 'core_solution', ''),
            title="[bold green]CORE SOLUTION[/bold green]",
            box=box.DOUBLE,
            border_style="green",
        ))

        insights_text = Text()
        for i, insight in enumerate(_get_attr(fs, 'critical_insights', []), 1):
            insights_text.append(f"{i}. {insight}\n\n")
        console.print(Panel(insights_text, title="[yellow]Critical Insights[/yellow]", box=box.ROUNDED))

        _render_action_blueprint(state)

        if _get_attr(fs, 'open_questions', []):
            oq_text = "\n".join(f"• {q}" for q in _get_attr(fs, 'open_questions', []))
            console.print(Panel(oq_text, title="[red]Open Questions (Unresolved)[/red]", box=box.ROUNDED))

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
# DEBATE RENDERER
# ─────────────────────────────────────────────────────────────────────


