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

def _render_self_discover(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold yellow]SELF-DISCOVER  ({duration:.1f}s)[/bold yellow]")
    render_routing_table(state)

    modules = state.self_discover_state.get("selected_modules", [])
    if modules:
        tbl = Table(title="Selected Reasoning Modules", box=box.SIMPLE_HEAD)
        tbl.add_column("Order", style="cyan", width=5)
        tbl.add_column("Module")
        tbl.add_column("Rationale", style="dim")
        for m in modules:
            tbl.add_row(str(m.get("order", "")), m.get("module", ""), m.get("rationale", ""))
        console.print(tbl)

    strategy = state.self_discover_state.get("composition_strategy", "")
    if strategy:
        console.print(Panel(strategy, title="[cyan]Composition Strategy[/cyan]", box=box.ROUNDED))

    adapted = state.self_discover_state.get("adapted_modules", [])
    if adapted:
        for am in adapted:
            am_text = Text()
            am_text.append(f"Module: {am.get('module', '')}\n", style="bold cyan")
            am_text.append(f"Instruction: {am.get('instruction', '')}\n", style="white")
            am_text.append(f"Input: {am.get('input', '')}\n", style="dim")
            am_text.append(f"Output: {am.get('output', '')}\n", style="dim")
            console.print(Panel(am_text, box=box.ROUNDED))

    outputs = state.self_discover_state.get("module_outputs", [])
    if outputs:
        out_text = Text()
        out_text.append("Module Outputs:\n", style="bold")
        for mo in outputs:
            out_text.append(f"  {mo.get('module', '')}: {mo.get('output', '')[:200]}\n", style="white")
        console.print(Panel(out_text, title="[cyan]Execution Trace[/cyan]", box=box.ROUNDED))

    final = state.self_discover_state.get("final_answer", "")
    if final:
        console.print(Panel(final, title="[bold green]SELF-DISCOVERED ANSWER[/bold green]", box=box.DOUBLE, border_style="green"))

    attribution = state.self_discover_state.get("module_attribution", {})
    if attribution:
        attr_text = Text()
        attr_text.append("Module Attribution:\n", style="bold")
        for mod, contrib in attribution.items():
            attr_text.append(f"  {mod}: {contrib}\n", style="dim")
        console.print(Panel(attr_text, title="[dim]Attribution[/dim]", box=box.ROUNDED))

    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# PERSPECTIVE CONTENT RENDERER
# ─────────────────────────────────────────────────────────────────────


