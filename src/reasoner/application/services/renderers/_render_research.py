from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from reasoner.application.services.renderers._shared import (
    _duration,
    _get_attr,
    _label_color,
    _render_action_blueprint,
    _render_errors,
    _render_stress,
    console,
)
from reasoner.domain.pipeline_state import PipelineState


def _render_research(state: PipelineState) -> None:
    duration = _duration(state)
    console.rule(f"[bold blue]EVIDENCE SYNTHESIS REPORT  ({duration:.1f}s)[/bold blue]")

    if state.phase_models:
        infra_table = Table(title="Research Infrastructure", box=box.SIMPLE_HEAVY)
        infra_table.add_column("Phase / Role", style="cyan", width=22)
        infra_table.add_column("Model",        style="white")
        infra_table.add_column("Type",         style="white", width=14)

        role_labels = {
            "classification":  "Ph0  Classification",
            "decomposition":   "Ph1  Decomposition",
            "constructive":    "Ph2a Constructive",
            "destructive":     "Ph2b Destructive",
            "systemic":        "Ph2c Systemic",
            "minimalist":      "Ph2d Minimalist",
            "scoring":         "Ph3  Scoring",
            "stress_testing":  "Ph4  Stress Testing",
            "synthesis":       "Ph5  Synthesis",
        }
        for role in list(role_labels.keys()) + [r for r in state.phase_models if r not in role_labels]:
            if role in state.phase_models:
                model = state.phase_models[role]
                model_type = "[yellow]Web-grounded[/yellow]" if "sonar" in model else "Offline"
                infra_table.add_row(role_labels.get(role, role), model, model_type)
        console.print(infra_table)

    if state.decomposition:
        dec = state.decomposition
        sub_problems = dec.sub_problems if hasattr(dec, 'sub_problems') else dec.get('sub_problems', [])
        assumptions = dec.assumptions if hasattr(dec, 'assumptions') else dec.get('assumptions', [])
        rq_text = Text()
        for sp in sub_problems:
            sp_id = sp.id if hasattr(sp, 'id') else sp.get('id', '')
            sp_desc = sp.description if hasattr(sp, 'description') else sp.get('description', '')
            rq_text.append(f"RQ {sp_id}: {sp_desc}\n", style="bold white")
            sp_constraints = sp.constraints if hasattr(sp, 'constraints') else sp.get('constraints', [])
            if sp_constraints:
                rq_text.append(f"  Constraints: {', '.join(sp_constraints)}\n", style="dim")
        console.print(Panel(rq_text, title="[cyan]Research Question Breakdown[/cyan]", box=box.ROUNDED))

        if assumptions:
            assume_table = Table(title="Evidence Status of Assumptions", box=box.SIMPLE_HEAVY)
            assume_table.add_column("Status",    width=12)
            assume_table.add_column("Assumption")
            assume_table.add_column("Rationale", style="dim")
            for a in assumptions:
                a_label = a.label if hasattr(a, 'label') else a.get('label', 'UNKNOWN')
                color = _label_color(a_label)
                label_val = a_label.value if hasattr(a_label, 'value') else a_label
                a_text = a.text if hasattr(a, 'text') else a.get('text', '')
                a_rationale = a.rationale if hasattr(a, 'rationale') else a.get('rationale', '')
                assume_table.add_row(
                    f"[{color}]{label_val}[/{color}]",
                    a_text,
                    a_rationale,
                )
            console.print(assume_table)

    if state.scores:
        eq_table = Table(title="Evidence Quality by Perspective", box=box.SIMPLE_HEAVY)
        eq_table.add_column("Perspective",  style="cyan")
        eq_table.add_column("Logic",        justify="center")
        eq_table.add_column("Evidence",     justify="center", style="bold yellow")
        eq_table.add_column("Resilience",   justify="center")
        eq_table.add_column("Feasibility",  justify="center")
        eq_table.add_column("Total",        justify="center", style="bold")
        eq_table.add_column("Potential Bias")

        for s in sorted(state.scores, key=lambda x: x.evidence_support, reverse=True):
            is_top = s.perspective in [c.perspective for c in state.top_candidates]
            eq_table.add_row(
                s.perspective.value,
                f"{s.logical_consistency:.1f}",
                f"[bold yellow]{s.evidence_support:.1f}[/bold yellow]",
                f"{s.failure_resilience:.1f}",
                f"{s.feasibility:.1f}",
                f"[bold]{s.total:.1f}[/bold]",
                ", ".join(s.bias_flags[:2]) if s.bias_flags else "—",
                style="bold green" if is_top else "",
            )
        console.print(eq_table)

    _render_stress(state, "Adversarial Challenge")

    if state.final_solution:
        fs = state.final_solution

        console.print(Panel(
            _get_attr(fs, 'core_solution', ''),
            title="[bold green]EVIDENCE-GROUNDED SYNTHESIS[/bold green]",
            box=box.DOUBLE,
            border_style="green",
        ))

        if _get_attr(fs, 'claim_labels', {}):
            claim_table = Table(title="Claim Verification Status", box=box.SIMPLE_HEAVY)
            claim_table.add_column("Status", width=14)
            claim_table.add_column("Claim")
            for claim, label in _get_attr(fs, 'claim_labels', {}).items():
                color = _label_color(label)
                claim_table.add_row(f"[{color}]{label.value}[/{color}]", claim)
            console.print(claim_table)

        if _get_attr(fs, 'open_questions', []):
            oq_text = "\n".join(f"• {q}" for q in _get_attr(fs, 'open_questions', []))
            console.print(Panel(oq_text, title="[red]Evidence Gaps (Unverified / Missing Data)[/red]", box=box.ROUNDED))

        if _get_attr(fs, 'critical_insights', []):
            ins_text = Text()
            for i, insight in enumerate(_get_attr(fs, 'critical_insights', []), 1):
                ins_text.append(f"{i}. {insight}\n\n")
            console.print(Panel(ins_text, title="[yellow]Key Findings[/yellow]", box=box.ROUNDED))

        _render_action_blueprint(state, title="Recommended Actions")

        meta = _get_attr(fs, 'meta_audit', {})
        if any(_get_attr(meta, k) for k in ('most_dangerous_assumption', 'dominant_bias', 'remaining_uncertainty', 'assumption_failure_impact', 'non_obvious_insight')):
            meta_text = (
                f"[bold]Critical evidence gap:[/bold] {_get_attr(meta, 'most_dangerous_assumption', '')}\n"
                f"[bold]Potential researcher bias:[/bold] {_get_attr(meta, 'dominant_bias', '')}\n"
                f"[bold]Remaining uncertainty:[/bold] {_get_attr(meta, 'remaining_uncertainty', '')}\n"
                f"[bold]Impact if gap unresolved:[/bold] {_get_attr(meta, 'assumption_failure_impact', '')}\n"
                f"[bold]Non-obvious finding:[/bold] [italic]{_get_attr(meta, 'non_obvious_insight', '')}[/italic]"
            )
            console.print(Panel(meta_text, title="[cyan]Epistemic Caveats[/cyan]", box=box.ROUNDED))

    _render_errors(state)


# ─────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────


