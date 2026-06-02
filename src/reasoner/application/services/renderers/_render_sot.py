from __future__ import annotations

from reasoner.application.services.renderers._shared import (
    console, _get_attr, _duration, _label_color,
    _render_stress, _render_action_blueprint, _render_errors,
    render_routing_table, render_perspective_content,
)
from reasoner.domain.pipeline_state import PipelineState

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

def _render_sot(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold blue]SKELETON-OF-THOUGHT  ({duration:.1f}s)[/bold blue]")
    render_routing_table(state)

    sub_problems = state.sot_state.get("sub_problems", [])
    if sub_problems:
        tbl = Table(title="Problem Skeleton", box=box.SIMPLE_HEAD)
        tbl.add_column("ID", style="cyan", width=4)
        tbl.add_column("Sub-Problem")
        tbl.add_column("Expected Output", style="dim")
        for sp in sub_problems:
            tbl.add_row(sp.get("id", ""), sp.get("description", ""), sp.get("expected_output", ""))
        console.print(tbl)

    solutions = state.sot_state.get("solutions", [])
    if solutions:
        for sol in solutions:
            sol_text = Text()
            sol_text.append(f"Solution for {sol.get('sub_problem_id', '')}:\n", style="bold cyan")
            sol_text.append(sol.get("solution", "") + "\n")
            insights = sol.get("key_insights", [])
            if insights:
                sol_text.append("\nKey Insights:\n", style="bold")
                for ins in insights:
                    sol_text.append(f"  • {ins}\n", style="yellow")
            console.print(Panel(sol_text, box=box.ROUNDED))

    assembled = state.sot_state.get("assembled_answer", "")
    if assembled:
        console.print(Panel(assembled, title="[bold green]ASSEMBLED ANSWER[/bold green]", box=box.DOUBLE, border_style="green"))

    transitions = state.sot_state.get("transitions", [])
    if transitions:
        t_text = Text()
        t_text.append("Transitions:\n", style="bold")
        for t in transitions:
            t_text.append(f"  → {t}\n", style="dim")
        console.print(Panel(t_text, title="[dim]Assembly Glue[/dim]", box=box.ROUNDED))

    _render_errors(state)


# ── ToT RENDERER ─────────────────────────────────────────────────────


