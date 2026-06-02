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

def _render_pot(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold green]PROGRAM-OF-THOUGHTS  ({duration:.1f}s)[/bold green]")
    render_routing_table(state)

    code = state.pot_state.get("code", "")
    if code:
        console.print(Panel(
            f"```python\n{code}\n```",
            title="[cyan]Generated Code[/cyan]", box=box.ROUNDED,
        ))

    explanation = state.pot_state.get("explanation", "")
    if explanation:
        console.print(Panel(explanation, title="[dim]Approach Explanation[/dim]", box=box.ROUNDED))

    output = state.pot_state.get("execution_output", "")
    error = state.pot_state.get("execution_error", "")
    if output or error:
        out_text = Text()
        if output:
            out_text.append(f"Output:\n{output}\n", style="green")
        if error:
            out_text.append(f"\nError:\n{error}\n", style="red")
        console.print(Panel(out_text, title="[cyan]Execution Results[/cyan]", box=box.ROUNDED))

    interpretation = state.pot_state.get("interpretation", "")
    if interpretation:
        console.print(Panel(interpretation, title="[yellow]Interpretation[/yellow]", box=box.ROUNDED))

    computed = state.pot_state.get("computed_answer", "")
    if computed:
        console.print(Panel(computed, title="[bold green]COMPUTED ANSWER[/bold green]", box=box.DOUBLE, border_style="green"))

    caveats = state.pot_state.get("caveats", [])
    if caveats:
        c_text = Text()
        c_text.append("Caveats:\n", style="bold yellow")
        for c in caveats:
            c_text.append(f"  ! {c}\n", style="yellow")
        console.print(Panel(c_text, title="[yellow]Caveats[/yellow]", box=box.ROUNDED))

    _render_errors(state)


# ── Self-Discover RENDERER ───────────────────────────────────────────


