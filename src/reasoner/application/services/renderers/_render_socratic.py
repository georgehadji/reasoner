from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.text import Text

from reasoner.application.services.renderers._shared import (
    _duration,
    _get_attr,
    _render_action_blueprint,
    _render_errors,
    console,
    render_routing_table,
)
from reasoner.domain.pipeline_state import PipelineState


def _render_socratic(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold yellow]SOCRATIC DIALOGUE  ({duration:.1f}s)[/bold yellow]")
    render_routing_table(state)

    questions = state.socratic_state.get("questions") or []
    if questions:
        q_text = Text()
        for q in questions:
            q_text.append(f"{q.get('id')}. {q.get('target_concept')}: ", style="bold cyan")
            q_text.append(f"{q.get('question')}\n\n", style="white")
        console.print(Panel(q_text, title="[cyan]Phase 2 — Maieutic Questions[/cyan]", box=box.ROUNDED))

    answers = state.socratic_state.get("answers") or []
    if answers:
        a_text = Text()
        for a in answers:
            a_text.append(f"Refining {a.get('question_id')}:\n", style="bold")
            a_text.append(f"  Answer: {a.get('answer')}\n", style="white")
            if a.get("contradiction_found"):
                a_text.append(f"  [red]Aporia:[/red] {a.get('contradiction_found')}\n", style="red")
            a_text.append(f"  [green]Insight:[/green] {a.get('insight')}\n\n", style="green")
        console.print(Panel(a_text, title="[cyan]Phase 3 — Dialectic Answers[/cyan]", box=box.ROUNDED))

    if state.final_solution:
        fs = state.final_solution
        console.print(Panel(_get_attr(fs, 'core_solution', ''), title="[bold green]PHILOSOPHICAL SYNTHESIS[/bold green]", box=box.DOUBLE, border_style="green"))
        if _get_attr(fs, 'critical_insights', []):
            ins_text = Text()
            for i, insight in enumerate(_get_attr(fs, 'critical_insights', []), 1):
                ins_text.append(f"{i}. {insight}\n\n")
            console.print(Panel(ins_text, title="[yellow]Aporic Insights[/yellow]", box=box.ROUNDED))
        _render_action_blueprint(state)
    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# B1: PRE-MORTEM ANALYSIS RENDERER
# ─────────────────────────────────────────────────────────────────────


