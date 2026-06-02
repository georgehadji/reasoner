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

def _render_delphi(state: PipelineState) -> None:
    d = state.delphi_state

    # Round 1 expert estimates table
    r1 = d.get("round_1_estimates", [])
    if r1:
        tbl = Table(title="Round 1 — Independent Expert Estimates", box=box.SIMPLE_HEAD)
        tbl.add_column("Expert", style="cyan", width=10)
        tbl.add_column("Estimate", style="white")
        tbl.add_column("Confidence", style="yellow", width=10)
        tbl.add_column("Key Assumption", style="dim")
        for e in r1:
            tbl.add_row(
                e.get("expert_id", "?"),
                str(e.get("estimate_label", e.get("estimate_value", "N/A"))),
                e.get("confidence", ""),
                (e.get("key_assumptions", [""])[0] if e.get("key_assumptions") else "")[:80],
            )
        console.print(tbl)

    # Aggregated statistics
    stats = d.get("aggregated_stats", {})
    if stats:
        content = Text()
        median = stats.get("median", stats.get("central_theme", "N/A"))
        iqr = stats.get("iqr", stats.get("spread", "N/A"))
        outlier = stats.get("outlier_expert", "N/A")
        content.append("Median: ", style="bold")
        content.append(f"{median}\n")
        content.append("Spread (IQR): ", style="bold")
        content.append(f"{iqr}\n")
        content.append("Outlier expert: ", style="bold yellow")
        content.append(f"{outlier}\n")
        console.print(Panel(content, title="[yellow]Anonymous Aggregated Statistics[/yellow]", box=box.ROUNDED))

    # Round 2 revisions table
    r2 = d.get("round_2_estimates", [])
    if r2:
        tbl = Table(title="Round 2 — Revised Estimates", box=box.SIMPLE_HEAD)
        tbl.add_column("Expert", style="cyan", width=10)
        tbl.add_column("Revised Estimate", style="white")
        tbl.add_column("Position", style="yellow", width=12)
        tbl.add_column("Rationale", style="dim")
        for e in r2:
            position = e.get("position", "")
            pos_color = "green" if position == "revised" else "red"
            tbl.add_row(
                e.get("expert_id", "?"),
                str(e.get("revised_label", e.get("revised_estimate", "N/A"))),
                f"[{pos_color}]{position}[/{pos_color}]",
                e.get("rationale", "")[:80],
            )
        console.print(tbl)

    # Convergence verdict
    consensus = d.get("consensus", {})
    converged = d.get("converged", False)
    if consensus:
        color = "green" if converged else "yellow"
        label = "CONVERGED" if converged else "NOT CONVERGED"
        content = Text()
        content.append(f"{label}\n", style=f"bold {color}")
        final_val = consensus.get("median", consensus.get("consensus_label", ""))
        if final_val:
            content.append(f"Consensus: {final_val}\n")
        remaining = consensus.get("remaining_disagreement", "")
        if remaining:
            content.append(f"Remaining disagreement: {remaining}\n", style="dim")
        console.print(Panel(content, title=f"[{color}]Convergence Result[/{color}]", box=box.ROUNDED))

    # Minority dissent
    dissent = d.get("dissent", {})
    if dissent:
        minority_report = dissent.get("minority_report", "")
        missing = dissent.get("what_consensus_misses", [])
        content = Text()
        if minority_report:
            content.append(minority_report + "\n\n", style="italic")
        if missing:
            content.append("What the consensus misses:\n", style="bold red")
            for m in missing:
                content.append(f"  x {m}\n", style="red")
        console.print(Panel(content, title="[red]Minority Dissent Report[/red]", box=box.ROUNDED))

    _render_action_blueprint(state)
    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────


