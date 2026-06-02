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

def _render_tot(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold magenta]TREE-OF-THOUGHTS  ({duration:.1f}s)[/bold magenta]")
    render_routing_table(state)

    dps = state.tot_state.get("decision_points", [])
    if dps:
        tbl = Table(title="Decision Points", box=box.SIMPLE_HEAD)
        tbl.add_column("ID", style="cyan", width=4)
        tbl.add_column("Description")
        for dp in dps:
            tbl.add_row(dp.get("id", ""), dp.get("description", ""))
        console.print(tbl)

    evaluations = state.tot_state.get("evaluations", [])
    if evaluations:
        tbl = Table(title="Candidate Evaluations", box=box.SIMPLE_HEAD)
        tbl.add_column("Candidate", style="cyan")
        tbl.add_column("Score", justify="center")
        tbl.add_column("Verdict")
        for ev in evaluations:
            v = ev.get("verdict", "")
            color = "green" if v == "proceed" else "red" if v == "reject" else "yellow"
            tbl.add_row(ev.get("candidate_id", ""), str(ev.get("score", "")), f"[{color}]{v}[/{color}]")
        console.print(tbl)

    final_path = state.tot_state.get("final_path", [])
    if final_path:
        path_text = " → ".join(final_path)
        console.print(Panel(
            Text(path_text, style="bold green"),
            title="[green]Optimal Path[/green]", box=box.DOUBLE,
        ))

    backtrack = state.tot_state.get("backtrack_decision", "")
    if backtrack:
        console.print(Panel(
            f"Backtrack decision: {backtrack}",
            title="[cyan]Search Strategy[/cyan]", box=box.ROUNDED,
        ))

    _render_errors(state)


# ── PoT RENDERER ─────────────────────────────────────────────────────


