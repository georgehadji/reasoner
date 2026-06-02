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

def _render_analogical(state: PipelineState) -> None:
    a = state.analogical_state

    # Abstract structure panel
    structure = a.get("abstract_structure", "")
    if structure:
        content = Text()
        content.append(structure)
        constraints = a.get("constraints", [])
        objectives = a.get("objectives", [])
        actors = a.get("actors", [])
        core_dynamics = a.get("core_dynamics", [])
        if constraints:
            content.append("\n\nConstraints:\n", style="bold")
            for c in constraints:
                content.append(f"  • {c}\n")
        if objectives:
            content.append("\nObjectives:\n", style="bold cyan")
            for o in objectives:
                content.append(f"  • {o}\n")
        if actors:
            content.append("\nActors:\n", style="bold yellow")
            for actor in actors:
                content.append(f"  • {actor}\n")
        if core_dynamics:
            content.append("\nCore Dynamics:\n", style="bold magenta")
            for d in core_dynamics:
                content.append(f"  • {d}\n")
        structural_type = a.get("structural_type", "")
        if structural_type:
            content.append(f"\nStructural Type: ", style="bold")
            content.append(structural_type, style="cyan")
        console.print(Panel(content, title="[cyan]Abstract Problem Structure[/cyan]", box=box.ROUNDED))

    # Source domains table
    domains = a.get("source_domains", [])
    if domains:
        tbl = Table(title="Source Domains with Isomorphic Solutions", box=box.SIMPLE_HEAD)
        tbl.add_column("Domain", style="yellow")
        tbl.add_column("Solved Problem", style="white")
        tbl.add_column("Key Mechanism", style="cyan")
        tbl.add_column("Relevance", style="green", width=10)
        for d in domains:
            tbl.add_row(
                d.get("domain", ""),
                (d.get("solved_problem", "") or "")[:80],
                (d.get("key_mechanism", "") or "")[:80],
                d.get("relevance_score", ""),
            )
        console.print(tbl)

    # Analogy mapping table
    mappings = a.get("analogy_mappings", [])
    if mappings:
        tbl = Table(title="Structural Analogy Mappings", box=box.SIMPLE_HEAD)
        tbl.add_column("Source Element", style="yellow")
        tbl.add_column("Target Element", style="cyan")
        tbl.add_column("Mapping Type", style="dim", width=14)
        tbl.add_column("Confidence", style="green", width=10)
        for m in mappings:
            tbl.add_row(
                m.get("source_element", ""),
                m.get("target_element", ""),
                m.get("mapping_type", ""),
                m.get("confidence", ""),
            )
        console.print(tbl)

    # Transfer steps
    transfer_steps = a.get("transfer_steps", [])
    if transfer_steps:
        content = Text()
        content.append("Transfer Steps:\n", style="bold green")
        for i, step in enumerate(transfer_steps, 1):
            content.append(f"  {i}. {step}\n")
        adaptations = a.get("adaptations_required", [])
        if adaptations:
            content.append("\nAdaptations Required:\n", style="bold yellow")
            for adap in adaptations:
                content.append(f"  ⟳ {adap}\n", style="yellow")
        caveats = a.get("caveats", [])
        if caveats:
            content.append("\nCaveats:\n", style="bold dim")
            for cav in caveats:
                content.append(f"  ! {cav}\n", style="dim")
        console.print(Panel(content, title="[green]Transfer Plan[/green]", box=box.ROUNDED))

    # Transferred solution
    transferred = a.get("transferred_solution", "")
    if transferred:
        confidence = a.get("transfer_confidence", "")
        title_suffix = f" [dim](confidence: {confidence})[/dim]" if confidence else ""
        console.print(Panel(
            Text(transferred, style="bold"),
            title=f"[green]Transferred Solution[/green]{title_suffix}",
            box=box.ROUNDED,
        ))

    # Broken analogies
    broken = a.get("broken_analogies", [])
    if broken:
        content = Text()
        content.append("Where the analogy breaks down:\n", style="bold red")
        for b in broken:
            content.append(f"  ✗ {b}\n", style="red")
        unmapped = a.get("unmapped_elements", [])
        if unmapped:
            content.append("\nUnmapped Source Elements:\n", style="bold dim")
            for u in unmapped:
                content.append(f"  ? {u}\n", style="dim")
        console.print(Panel(content, title="[red]Analogy Limitations[/red]", box=box.ROUNDED))

    _render_action_blueprint(state)
    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# B5: DELPHI METHOD RENDERER
# ─────────────────────────────────────────────────────────────────────


