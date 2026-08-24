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


def _render_dialectical(state: PipelineState) -> None:
    d = state.dialectical_state

    # Thesis (green)
    thesis = d.get("thesis", "")
    commitments = d.get("key_commitments", [])
    if thesis:
        content = Text()
        content.append(thesis)
        if commitments:
            content.append("\n\nKey Commitments:\n", style="bold")
            for c in commitments:
                content.append(f"• {c}\n")
        console.print(Panel(content, title="[green]Thesis — Affirmative Position[/green]", box=box.ROUNDED))

    # Antithesis (red)
    antithesis = d.get("antithesis", "")
    contradictions = d.get("contradictions_exposed", [])
    if antithesis:
        content = Text()
        content.append(antithesis)
        if contradictions:
            content.append("\n\nContradictions Exposed:\n", style="bold red")
            for c in contradictions:
                content.append(f"✗ {c}\n", style="red")
        console.print(Panel(content, title="[red]Antithesis — Negation[/red]", box=box.ROUNDED))

    # Contradiction Analysis table
    irreconcilable = d.get("irreconcilable", [])
    compatible = d.get("compatible", [])
    if irreconcilable or compatible:
        tbl = Table(title="Contradiction Analysis", box=box.SIMPLE_HEAD, show_header=True)
        tbl.add_column("Type", style="cyan", width=18)
        tbl.add_column("Contradiction", style="white")
        for c in irreconcilable:
            tbl.add_row("[red]Irreconcilable[/red]", c)
        for c in compatible:
            tbl.add_row("[yellow]Compatible[/yellow]", c)
        console.print(tbl)

    # Aufhebung (magenta)
    aufhebung = d.get("aufhebung", "")
    if aufhebung:
        content = Text()
        content.append(aufhebung, style="bold")
        preserved_t = d.get("preserved_from_thesis", [])
        preserved_a = d.get("preserved_from_antithesis", [])
        new_insights = d.get("new_insights", [])
        if preserved_t:
            content.append("\n\nPreserved from Thesis:\n", style="bold green")
            for p in preserved_t:
                content.append(f"✓ {p}\n", style="green")
        if preserved_a:
            content.append("\nPreserved from Antithesis:\n", style="bold red")
            for p in preserved_a:
                content.append(f"✓ {p}\n", style="red")
        if new_insights:
            content.append("\nGenuine Novelty:\n", style="bold yellow")
            for i in new_insights:
                content.append(f"★ {i}\n", style="yellow")
        console.print(Panel(content, title="[magenta]Aufhebung — Qualitative Transcendence[/magenta]", box=box.HEAVY))

    _render_action_blueprint(state)
    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# B4: ANALOGICAL REASONING RENDERER
# ─────────────────────────────────────────────────────────────────────


