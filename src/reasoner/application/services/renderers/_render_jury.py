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

def _render_jury(state: PipelineState) -> None:
    """Render the JURY multi-agent evaluation result."""
    duration = _duration(state)
    console.rule(f"[bold magenta]JURY EVALUATION  ({duration:.1f}s)[/bold magenta]")

    # Generator Pool
    if state.generation_candidates:
        gen_table = Table(title="Generator Pool", box=box.SIMPLE_HEAVY)
        gen_table.add_column("Generator", style="cyan", width=15)
        gen_table.add_column("Model", style="white", width=18)
        gen_table.add_column("Confidence", justify="center", width=12)
        gen_table.add_column("Approach", style="white")

        for gc in state.generation_candidates:
            filled = int(gc.confidence * 10)
            conf_bar = "#" * filled + "-" * (10 - filled)
            # Ensure attributes are strings or renderable objects
            gen_table.add_row(
                str(gc.generator_id),
                str(gc.model_used or "?"),
                f"{gc.confidence:.0%} {conf_bar}",
                str(gc.approach_summary[:60] + ("…" if len(gc.approach_summary) > 60 else "")),
            )
        console.print(gen_table)

    # Critic Scores Matrix
    if state.critic_scores:
        console.print("\n[bold cyan]Critic Scores Matrix[/bold cyan]")
        for cs in state.critic_scores:
            score_text = Text()
            score_text.append(f"[bold]{cs.critic_id}[/bold] ({cs.critic_model})\n", style="cyan")
            for gen_id, ds in cs.candidate_scores.items():
                score_text.append(f"  {gen_id}: ", style="white")
                score_text.append(f"F={ds.factuality:.1f} ", style="green")
                score_text.append(f"R={ds.reasoning:.1f} ", style="blue")
                score_text.append(f"C={ds.completeness:.1f} ", style="yellow")
                score_text.append(f"H={ds.helpfulness:.1f} ", style="magenta")
                score_text.append(f"[bold]Avg={ds.total:.1f}[/bold]\n", style="bold")
            if cs.dissenting_note:
                score_text.append(f"  [yellow]Dissenting:[/yellow] {cs.dissenting_note[:100]}\n", style="yellow")
            console.print(Panel(score_text, box=box.ROUNDED))

    # Verification Results
    if state.verification_results:
        verif_table = Table(title="Verification Results", box=box.SIMPLE_HEAVY)
        verif_table.add_column("Claim", width=40)
        verif_table.add_column("Source", width=12)
        verif_table.add_column("Verdict", width=12)
        verif_table.add_column("Confidence", justify="center", width=12)

        for vr in state.verification_results:
            color = _label_color(vr.verdict)
            verif_table.add_row(
                vr.claim[:40] + ("…" if len(vr.claim) > 40 else ""),
                vr.source_generator,
                f"[{color}]{vr.verdict.value}[/{color}]",
                f"{vr.confidence:.0%}",
            )
        console.print(verif_table)

    # Meta-Evaluation
    if state.meta_evaluation:
        meta = state.meta_evaluation
        meta_text = Text()
        meta_text.append("[bold]Critic Reliability:[/bold]\n", style="cyan")
        for cid, rel in _get_attr(meta, 'critic_reliability', {}).items():
            rel_val = rel if isinstance(rel, (int, float)) else (
                rel.get("score", rel.get("value", rel.get("reliability", 0)))
                if isinstance(rel, dict) else 0
            )
            try:
                meta_text.append(f"  {cid}: {float(rel_val):.1f}/10\n", style="white")
            except (TypeError, ValueError):
                meta_text.append(f"  {cid}: {rel_val}\n", style="white")
        meta_text.append(f"\n[bold]Agreement Rate:[/bold] {_get_attr(meta, 'agreement_rate', 0):.0%}\n", style="cyan")
        meta_text.append(f"[bold]Most Reliable:[/bold] {_get_attr(meta, 'most_reliable_critic', '')}\n", style="green")
        meta_text.append(f"[bold]Least Reliable:[/bold] {_get_attr(meta, 'least_reliable_critic', '')}\n", style="red")
        if _get_attr(meta, 'meta_insight', ''):
            meta_text.append(f"\n[bold]Meta Insight:[/bold] {_get_attr(meta, 'meta_insight', '')}\n", style="yellow")
        console.print(Panel(meta_text, title="[cyan]Meta-Evaluation (Judge-the-Judges)[/cyan]", box=box.ROUNDED))

    # Final Solution
    if state.final_solution:
        fs = state.final_solution

        console.print(Panel(
            _get_attr(fs, 'core_solution', ''),
            title="[bold green]FINAL SOLUTION (Jury Verdict)[/bold green]",
            box=box.DOUBLE,
            border_style="green",
        ))

        # Generator Attribution
        if _get_attr(fs, 'generator_attribution', {}):
            attr_text = Text()
            for gid, desc in _get_attr(fs, 'generator_attribution', {}).items():
                attr_text.append(f"[bold]{gid}:[/bold] {desc}\n", style="cyan")
            console.print(Panel(attr_text, title="[cyan]Generator Attribution[/cyan]", box=box.ROUNDED))

        # Critic Weighting
        if _get_attr(fs, 'critic_weighting', {}):
            weight_text = Text()
            for cid, weight in _get_attr(fs, 'critic_weighting', {}).items():
                weight_text.append(f"{cid}: {weight:.1%}\n", style="white")
            console.print(Panel(weight_text, title="[cyan]Critic Weighting (by Reliability)[/cyan]", box=box.ROUNDED))

        if _get_attr(fs, 'critical_insights', []):
            ins_text = Text()
            for i, insight in enumerate(_get_attr(fs, 'critical_insights', []), 1):
                ins_text.append(f"{i}. {insight}\n\n")
            console.print(Panel(ins_text, title="[yellow]Critical Insights[/yellow]", box=box.ROUNDED))

        _render_action_blueprint(state, title="Implementation Plan")

        if _get_attr(fs, 'open_questions', []):
            oq_text = "\n".join(f"• {q}" for q in _get_attr(fs, 'open_questions', []))
            console.print(Panel(oq_text, title="[red]Open Questions[/red]", box=box.ROUNDED))

        meta = _get_attr(fs, 'meta_audit', {})
        if any(_get_attr(meta, k) for k in ('most_dangerous_assumption', 'dominant_bias', 'remaining_uncertainty', 'assumption_failure_impact', 'non_obvious_insight')):
            meta_text = (
                f"[bold]Most dangerous assumption:[/bold] {_get_attr(meta, 'most_dangerous_assumption', '')}\n"
                f"[bold]Dominant bias:[/bold] {_get_attr(meta, 'dominant_bias', '')}\n"
                f"[bold]Remaining uncertainty:[/bold] {_get_attr(meta, 'remaining_uncertainty', '')}\n"
                f"[bold]If main assumption fails:[/bold] {_get_attr(meta, 'assumption_failure_impact', '')}\n"
                f"[bold]Non-obvious insight:[/bold] [italic]{_get_attr(meta, 'non_obvious_insight', '')}[/italic]"
            )
            console.print(Panel(meta_text, title="[cyan]Meta-Cognitive Audit[/cyan]", box=box.ROUNDED))

    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# SCIENTIFIC RENDERER
# ─────────────────────────────────────────────────────────────────────


