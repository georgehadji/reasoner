from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from reasoner.application.services.renderers._shared import (
    _render_errors,
    console,
)
from reasoner.domain.pipeline_state import PipelineState


def _render_pre_mortem(state: PipelineState) -> None:
    pm = state.pre_mortem_state

    # Failure Narrative
    fn = pm.get("failure_narrative", {})
    if fn:
        content = Text()
        content.append("Scenario: ", style="bold red")
        content.append(f"{fn.get('scenario', 'N/A')}\n\n")
        content.append(fn.get("what_happened", ""))
        triggers = fn.get("immediate_triggers", [])
        if triggers:
            content.append("\n\nImmediate Triggers:\n", style="bold")
            for t in triggers:
                content.append(f"• {t}\n")
        console.print(Panel(content, title="[red]Failure Narrative[/red]", box=box.HEAVY))

    # Root Cause
    rc = pm.get("root_cause", {})
    if rc:
        content = Text()
        content.append("Pivot Decision: ", style="bold yellow")
        content.append(f"{rc.get('pivot_decision', '')}\n\n")
        content.append("When: ", style="bold")
        content.append(f"{rc.get('decision_point', '')}\n\n")
        content.append("Why it seemed reasonable: ", style="bold")
        content.append(f"{rc.get('why_it_seemed_reasonable', '')}\n\n")
        cascade = rc.get("cascade", [])
        if cascade:
            content.append("Cascade:\n", style="bold")
            for step in cascade:
                content.append(f"  -> {step}\n")
        console.print(Panel(content, title="[yellow]Root Cause Analysis[/yellow]", box=box.ROUNDED))

    # Early Warning Signals table
    signals = pm.get("early_signals", [])
    if signals:
        tbl = Table(title="Early Warning Signals", box=box.SIMPLE_HEAD, show_header=True)
        tbl.add_column("Day", style="cyan", width=6)
        tbl.add_column("Signal", style="white")
        tbl.add_column("How to Detect", style="dim")
        tbl.add_column("Action Threshold", style="yellow")
        for s in signals:
            tbl.add_row(
                str(s.get("day", "?")),
                s.get("signal", ""),
                s.get("how_to_detect", ""),
                s.get("action_threshold", ""),
            )
        console.print(tbl)

    # Hardened Redesign
    hs = pm.get("hardened_solution", "")
    if hs:
        content = Text()
        content.append(hs)
        safeguards = pm.get("safeguards", [])
        if safeguards:
            content.append("\n\nSafeguards:\n", style="bold green")
            for s in safeguards:
                content.append(f"✓ {s}\n", style="green")
        console.print(Panel(content, title="[green]Hardened Redesign[/green]", box=box.ROUNDED))

    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# B2: BAYESIAN REASONING RENDERER
# ─────────────────────────────────────────────────────────────────────


