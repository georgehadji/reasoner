from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from reasoner.application.services.renderers._shared import (
    _render_action_blueprint,
    _render_errors,
    console,
)
from reasoner.domain.pipeline_state import PipelineState


def _render_bayesian(state: PipelineState) -> None:
    b = state.bayesian_state

    # Hypotheses with Priors
    hypotheses = b.get("hypotheses_with_priors", [])
    if hypotheses:
        tbl = Table(title="Hypotheses & Prior Probabilities", box=box.SIMPLE_HEAD, show_header=True)
        tbl.add_column("ID", style="cyan", width=5)
        tbl.add_column("Statement", style="white")
        tbl.add_column("P(H)", style="yellow", width=8)
        tbl.add_column("Reasoning", style="dim")
        for h in hypotheses:
            tbl.add_row(
                h.get("id", "?"),
                h.get("statement", ""),
                str(h.get("prior_probability", "")),
                h.get("reasoning", "")[:120],
            )
        console.print(tbl)

    # Posteriors
    posteriors = b.get("posteriors", [])
    most_probable = b.get("most_probable", "")
    if posteriors:
        tbl = Table(title="Posterior Probabilities P(H|E)", box=box.SIMPLE_HEAD, show_header=True)
        tbl.add_column("ID", style="cyan", width=5)
        tbl.add_column("P(H|E)", style="yellow", width=8)
        tbl.add_column("Explanation", style="white")
        for p in posteriors:
            hid = p.get("hypothesis_id", "?")
            is_top = hid == most_probable
            label = f"{hid} ★" if is_top else hid
            tbl.add_row(label, str(p.get("posterior_probability", "")), p.get("explanation", "")[:160])
        console.print(tbl)
        if most_probable:
            console.print(Panel(
                Text(f"Most probable hypothesis: {most_probable}", style="bold green"),
                title="[green]Bayesian Verdict[/green]", box=box.ROUNDED,
            ))

    # Sensitivity Analysis
    sensitivity = b.get("sensitivity_results", [])
    if sensitivity:
        tbl = Table(title="Sensitivity Analysis", box=box.SIMPLE_HEAD, show_header=True)
        tbl.add_column("Assumption", style="white")
        tbl.add_column("Posterior Shift", style="cyan", width=14)
        tbl.add_column("Importance", style="yellow", width=12)
        for s in sensitivity:
            shift = s.get("posterior_shift", "")
            shift_color = "red" if shift == "large" else ("yellow" if shift == "medium" else "green")
            tbl.add_row(
                s.get("assumption", ""),
                f"[{shift_color}]{shift}[/{shift_color}]",
                s.get("importance", ""),
            )
        console.print(tbl)
        most_sensitive = b.get("most_sensitive_assumption", "")
        if most_sensitive:
            console.print(Panel(
                Text(f"Most critical assumption: {most_sensitive}", style="bold yellow"),
                title="[yellow]Sensitivity Finding[/yellow]", box=box.ROUNDED,
            ))

    _render_action_blueprint(state)
    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# B3: DIALECTICAL REASONING RENDERER
# ─────────────────────────────────────────────────────────────────────


