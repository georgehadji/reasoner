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

def _render_cove(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold cyan]CHAIN-OF-VERIFICATION  ({duration:.1f}s)[/bold cyan]")
    render_routing_table(state)

    draft = state.cove_state.get("draft_answer", "")
    if draft:
        console.print(Panel(draft, title="[yellow]Draft Answer[/yellow]", box=box.ROUNDED))

    claims = state.cove_state.get("claims", [])
    if claims:
        tbl = Table(title="Claims to Verify", box=box.SIMPLE_HEAD)
        tbl.add_column("#", width=3)
        tbl.add_column("Claim")
        tbl.add_column("Confidence", width=10)
        for i, c in enumerate(claims, 1):
            tbl.add_row(str(i), c.get("claim", ""), str(c.get("confidence", "")))
        console.print(tbl)

    questions = state.cove_state.get("verification_questions", [])
    if questions:
        q_text = Text()
        for q in questions:
            q_text.append(f"Q: {q.get('question', '')}\n", style="bold cyan")
            q_text.append(f"  → Target: {q.get('target_claim', '')}\n\n", style="dim")
        console.print(Panel(q_text, title="[cyan]Verification Questions[/cyan]", box=box.ROUNDED))

    answers = state.cove_state.get("verification_answers", [])
    if answers:
        a_text = Text()
        for a in answers:
            verdict = a.get("verdict", "unknown")
            color = "green" if verdict == "supports" else "red" if verdict == "contradicts" else "yellow"
            a_text.append(f"Verdict: [{color}]{verdict}[/{color}]\n", style="bold")
            a_text.append(f"  Answer: {a.get('answer', '')}\n", style="white")
            a_text.append(f"  Reasoning: {a.get('reasoning', '')}\n\n", style="dim")
        console.print(Panel(a_text, title="[cyan]Independent Verification[/cyan]", box=box.ROUNDED))

    revised = state.cove_state.get("revised_answer", "")
    if revised:
        console.print(Panel(revised, title="[bold green]REVISED ANSWER[/bold green]", box=box.DOUBLE, border_style="green"))

    changes = state.cove_state.get("changes_made", [])
    if changes:
        c_text = Text()
        c_text.append("Changes Made:\n", style="bold")
        for ch in changes:
            c_text.append(f"  • {ch}\n", style="yellow")
        console.print(Panel(c_text, title="[yellow]Revision Log[/yellow]", box=box.ROUNDED))

    _render_errors(state)


# ── SoT RENDERER ─────────────────────────────────────────────────────


