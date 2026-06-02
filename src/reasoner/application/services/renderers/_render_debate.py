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

def _render_debate(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold magenta]DEBATE ARENA  ({duration:.1f}s)[/bold magenta]")

    prop_model  = state.phase_models.get("constructive", "?")
    opp_model   = state.phase_models.get("destructive",  "?")
    judge_model = state.phase_models.get("scoring",      "?")

    combatants = Table(title="Combatants", box=box.SIMPLE_HEAVY)
    combatants.add_column("Role", style="cyan", width=22)
    combatants.add_column("Model", style="white")
    combatants.add_row("Proposition (Model A)", prop_model)
    combatants.add_row("Opposition  (Model B)", opp_model)
    combatants.add_row("Judge",                 judge_model)
    console.print(combatants)

    console.print(Panel(state.problem, title="[bold cyan]THE MOTION[/bold cyan]", box=box.ROUNDED))

    if state.task_type:
        console.print(Panel(
            f"[bold]Task type:[/bold] {(state.task_type.value if hasattr(state.task_type, 'value') else state.task_type) if state.task_type else 'unknown'}  |  {state.task_type_rationale}",
            title="[cyan]Classification[/cyan]",
            box=box.ROUNDED,
        ))

    prop_cand = next((c for c in state.candidates if c.perspective == PerspectiveType.CONSTRUCTIVE), None)
    opp_cand  = next((c for c in state.candidates if c.perspective == PerspectiveType.DESTRUCTIVE),  None)

    if prop_cand:
        prop_text = Text()
        prop_text.append(prop_cand.content + "\n")
        if prop_cand.key_insights:
            prop_text.append("\nKey Insights:\n", style="bold yellow")
            for ins in prop_cand.key_insights:
                prop_text.append(f"  • {ins}\n", style="yellow")
        console.print(Panel(prop_text, title=f"[green]PROPOSITION — {prop_model}[/green]", box=box.ROUNDED))

    if opp_cand:
        opp_text = Text()
        opp_text.append(opp_cand.content + "\n")
        if opp_cand.key_insights:
            opp_text.append("\nKey Insights:\n", style="bold red")
            for ins in opp_cand.key_insights:
                opp_text.append(f"  • {ins}\n", style="red")
        console.print(Panel(opp_text, title=f"[red]OPPOSITION — {opp_model}[/red]", box=box.ROUNDED))

    prop_score = next((s for s in state.scores if s.perspective == PerspectiveType.CONSTRUCTIVE), None)
    opp_score  = next((s for s in state.scores if s.perspective == PerspectiveType.DESTRUCTIVE),  None)

    if prop_score and opp_score:
        scorecard = Table(title="Judge's Scorecard", box=box.SIMPLE_HEAVY)
        scorecard.add_column("Criterion",   style="cyan",  width=14)
        scorecard.add_column("Proposition", justify="center", style="green")
        scorecard.add_column("Opposition",  justify="center", style="red")

        def _sr(label: str, p: float, o: float) -> tuple[str, str, str]:
            pb = f"[bold]{p:.1f}[/bold]" if p > o else f"{p:.1f}"
            ob = f"[bold]{o:.1f}[/bold]" if o > p else f"{o:.1f}"
            return label, pb, ob

        scorecard.add_row(*_sr("Logic",       prop_score.logical_consistency, opp_score.logical_consistency))
        scorecard.add_row(*_sr("Evidence",    prop_score.evidence_support,    opp_score.evidence_support))
        scorecard.add_row(*_sr("Resilience",  prop_score.failure_resilience,  opp_score.failure_resilience))
        scorecard.add_row(*_sr("Feasibility", prop_score.feasibility,         opp_score.feasibility))
        p_total = f"[bold green]{prop_score.total:.1f}[/bold green]" if prop_score.total >= opp_score.total else f"[bold]{prop_score.total:.1f}[/bold]"
        o_total = f"[bold red]{opp_score.total:.1f}[/bold red]"      if opp_score.total > prop_score.total  else f"[bold]{opp_score.total:.1f}[/bold]"
        scorecard.add_row("TOTAL", p_total, o_total)
        console.print(scorecard)

        margin = abs(prop_score.total - opp_score.total)
        if prop_score.total >= opp_score.total:
            winner_label = f"PROPOSITION WINS  ({prop_model})  by +{margin:.1f} points"
            winner_style = "bold green on dark_green"
            loser_score  = opp_score
        else:
            winner_label = f"OPPOSITION WINS  ({opp_model})  by +{margin:.1f} points"
            winner_style = "bold red on dark_red"
            loser_score  = prop_score

        console.print(Panel(winner_label, style=winner_style, box=box.DOUBLE))

        if loser_score.steel_man:
            console.print(Panel(
                loser_score.steel_man,
                title="[yellow]Dissenting View (Strongest Counter-Argument)[/yellow]",
                box=box.ROUNDED,
            ))

    _render_stress(state, "Challenge Scenarios")

    if state.final_solution:
        fs = state.final_solution

        console.print(Panel(
            _get_attr(fs, 'core_solution', ''),
            title="[bold green]VERDICT[/bold green]",
            box=box.DOUBLE,
            border_style="green",
        ))

        if _get_attr(fs, 'critical_insights', []):
            ins_text = Text()
            for i, insight in enumerate(_get_attr(fs, 'critical_insights', []), 1):
                ins_text.append(f"{i}. {insight}\n\n")
            console.print(Panel(ins_text, title="[yellow]Key Findings[/yellow]", box=box.ROUNDED))

        _render_action_blueprint(state, title="Implementation Ruling")

        if _get_attr(fs, 'open_questions', []):
            oq_text = "\n".join(f"• {q}" for q in _get_attr(fs, 'open_questions', []))
            console.print(Panel(oq_text, title="[red]Unresolved Points[/red]", box=box.ROUNDED))

        meta = _get_attr(fs, 'meta_audit', {})
        if any(_get_attr(meta, k) for k in ('most_dangerous_assumption', 'dominant_bias', 'remaining_uncertainty', 'assumption_failure_impact', 'non_obvious_insight')):
            meta_text = (
                f"[bold]Most dangerous assumption:[/bold] {_get_attr(meta, 'most_dangerous_assumption', '')}\n"
                f"[bold]Dominant bias in judgment:[/bold] {_get_attr(meta, 'dominant_bias', '')}\n"
                f"[bold]Remaining uncertainty:[/bold] {_get_attr(meta, 'remaining_uncertainty', '')}\n"
                f"[bold]If main assumption fails:[/bold] {_get_attr(meta, 'assumption_failure_impact', '')}\n"
                f"[bold]Non-obvious insight:[/bold] [italic]{_get_attr(meta, 'non_obvious_insight', '')}[/italic]"
            )
            console.print(Panel(meta_text, title="[cyan]Judge's Reservations[/cyan]", box=box.ROUNDED))

    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# RESEARCH RENDERER
# ─────────────────────────────────────────────────────────────────────


