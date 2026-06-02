"""
Reasoner Pipeline - Output Renderer
Rich terminal display and JSON export, with method-specific layouts.

Methods:
  MULTI_PERSPECTIVE — 4 perspectives: constructive, destructive, systemic, minimalist
  DEBATE            — adversarial competition: Proposition vs Opposition → Verdict
  RESEARCH          — evidence report: quality matrix, claim verification, evidence gaps
  JURY              — 3 generators → 3 critics → verification → meta-evaluation → verdict
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from reasoner.domain.pipeline_state import PipelineState
from reasoner.models import (
    ClaimLabel,
    PerspectiveType,
)

console = Console()


# ─────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────────────────────────────

def _get_attr(obj, key, default=None):
    """Safely get attribute from dict or object."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ─────────────────────────────────────────────────────────────────────
# METHOD DETECTION
# ─────────────────────────────────────────────────────────────────────


class MethodType(Enum):
    MULTI_PERSPECTIVE = "multi-perspective"
    DEBATE            = "debate"

    RESEARCH          = "research"
    JURY              = "jury"
    SCIENTIFIC        = "scientific"
    SOCRATIC          = "socratic"
    PRE_MORTEM        = "pre-mortem"
    BAYESIAN          = "bayesian"
    DIALECTICAL       = "dialectical"
    ANALOGICAL        = "analogical"
    DELPHI            = "delphi"
    COVE              = "cove"
    SOT               = "sot"
    TOT               = "tot"
    POT               = "pot"
    SELF_DISCOVER     = "self-discover"


_DEBATE_PRESETS       = {"debate-budget", "debate-premium"}
_RESEARCH_PRESETS     = {"research-budget", "research-premium"}
_JURY_PRESETS         = {"jury-budget", "jury-premium"}
_SCIENTIFIC_PRESETS   = {"scientific-budget", "scientific-premium"}
_SOCRATIC_PRESETS     = {"socratic-budget", "socratic-premium"}
_PRE_MORTEM_PRESETS   = {"pre-mortem-budget", "pre-mortem-premium"}
_BAYESIAN_PRESETS     = {"bayesian-budget", "bayesian-premium"}
_DIALECTICAL_PRESETS  = {"dialectical-budget", "dialectical-premium"}
_ANALOGICAL_PRESETS   = {"analogical-budget", "analogical-premium"}
_DELPHI_PRESETS       = {"delphi-budget", "delphi-premium"}
_COVE_PRESETS         = {"cove-budget", "cove-premium"}
_SOT_PRESETS          = {"sot-budget", "sot-premium"}
_TOT_PRESETS          = {"tot-budget", "tot-premium"}
_POT_PRESETS          = {"pot-budget", "pot-premium"}
_SELF_DISCOVER_PRESETS = {"self-discover-budget", "self-discover-premium"}
# STANDARD presets (now called MULTI_PERSPECTIVE)
_MULTI_PERSPECTIVE_PRESETS = {
    "multi-perspective-budget", "multi-perspective-premium"
}



def _method_type(preset_name: str | None) -> MethodType:
    if preset_name in _DEBATE_PRESETS:       return MethodType.DEBATE
    if preset_name in _RESEARCH_PRESETS:     return MethodType.RESEARCH
    if preset_name in _JURY_PRESETS:         return MethodType.JURY
    if preset_name in _SCIENTIFIC_PRESETS:   return MethodType.SCIENTIFIC
    if preset_name in _SOCRATIC_PRESETS:     return MethodType.SOCRATIC
    if preset_name in _PRE_MORTEM_PRESETS:   return MethodType.PRE_MORTEM
    if preset_name in _BAYESIAN_PRESETS:     return MethodType.BAYESIAN
    if preset_name in _DIALECTICAL_PRESETS:  return MethodType.DIALECTICAL
    if preset_name in _ANALOGICAL_PRESETS:   return MethodType.ANALOGICAL
    if preset_name in _DELPHI_PRESETS:       return MethodType.DELPHI
    if preset_name in _COVE_PRESETS:         return MethodType.COVE
    if preset_name in _SOT_PRESETS:          return MethodType.SOT
    if preset_name in _TOT_PRESETS:          return MethodType.TOT
    if preset_name in _POT_PRESETS:          return MethodType.POT
    if preset_name in _SELF_DISCOVER_PRESETS: return MethodType.SELF_DISCOVER
    if preset_name in _MULTI_PERSPECTIVE_PRESETS: return MethodType.MULTI_PERSPECTIVE
    return MethodType.MULTI_PERSPECTIVE  # default


# ─────────────────────────────────────────────────────────────────────
# SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────


def _label_color(label: ClaimLabel) -> str:
    return {
        ClaimLabel.VERIFIED:   "green",
        ClaimLabel.HYPOTHESIS: "yellow",
        ClaimLabel.UNKNOWN:    "red",
    }.get(label, "white")



def _duration(state: PipelineState) -> float:
    return (datetime.now(timezone.utc) - state.started_at).total_seconds()



def _render_stress(state: PipelineState, section_title: str = "Phase 4 — Stress Tests") -> None:
    if not state.stress_results:
        return
    stress_text = Text()
    for sr in state.stress_results:
        color = "green" if sr.survival_rate > 0.7 else "yellow" if sr.survival_rate > 0.4 else "red"
        stress_text.append(f"[{sr.scenario.value.upper()}] ", style="bold")
        stress_text.append("Survival: ", style="white")
        stress_text.append(f"{sr.survival_rate:.0%}\n", style=color)
        stress_text.append(f"  Failure: {sr.failure_mode}\n", style="dim")
        stress_text.append(f"  Recovery: {sr.recovery_path}\n\n", style="dim cyan")
    console.print(Panel(stress_text, title=f"[cyan]{section_title}[/cyan]", box=box.ROUNDED))



def _render_action_blueprint(state: PipelineState, title: str = "Action Blueprint") -> None:
    fs = state.final_solution
    if not fs:
        return
    
    action_blueprint = _get_attr(fs, 'action_blueprint', [])
    if not action_blueprint:
        return
        
    table = Table(title=title, box=box.SIMPLE_HEAVY)
    table.add_column("#", width=3)
    table.add_column("Action")
    table.add_column("Horizon", width=12)
    table.add_column("Go Criteria")
    table.add_column("Fallback")
    for step in action_blueprint:
        if isinstance(step, dict) and any(step.get(k) for k in ("action", "step", "time_horizon", "go_criteria", "fallback")):
            table.add_row(
                str(step.get("step", "")),
                str(step.get("action", "")),
                str(step.get("time_horizon", "")),
                str(step.get("go_criteria", "")),
                str(step.get("fallback", "")),
            )
        elif step is not None and str(step).strip():
            table.add_row("", str(step), "", "", "")
    console.print(table)



def _render_errors(state: PipelineState) -> None:
    if state.errors:
        err_text = "\n".join(f"• {e}" for e in state.errors)
        console.print(Panel(
            err_text,
            title=f"[yellow]Pipeline Warnings ({len(state.errors)})[/yellow]",
            box=box.ROUNDED,
        ))


# ─────────────────────────────────────────────────────────────────────
# ROUTING TABLE (used in standard + research)
# ─────────────────────────────────────────────────────────────────────


def render_routing_table(state: PipelineState) -> None:
    """Render a table showing which model handled each phase."""
    if not state.phase_models:
        return
    table = Table(title="Model Routing", box=box.SIMPLE_HEAVY, show_header=True)
    table.add_column("Phase / Role", style="cyan", width=20)
    table.add_column("Model Used", style="white")

    role_labels = {
        "classification":  "Ph0  Classification",
        "decomposition":   "Ph1  Decomposition",
        "constructive":    "Ph2a Constructive",
        "destructive":     "Ph2b Destructive",
        "systemic":        "Ph2c Systemic",
        "minimalist":      "Ph2d Minimalist",
        "scoring":         "Ph3  Scoring / Critique",
        "stress_testing":  "Ph4  Stress Testing",
        "synthesis":       "Ph5  Synthesis",
    }

    all_roles = list(role_labels.keys()) + [
        r for r in state.phase_models if r not in role_labels
    ]

    for role in all_roles:
        if role in state.phase_models:
            label = role_labels.get(role, role)
            table.add_row(label, state.phase_models[role])

    console.print(table)


# ─────────────────────────────────────────────────────────────────────
# MULTI-PERSPECTIVE RENDERER
# ─────────────────────────────────────────────────────────────────────


def _render_cost_summary(state: PipelineState) -> None:
    """Display cost and token usage summary for the pipeline run."""
    # Only show if we have cost data
    if state.total_cost_usd == 0.0 and not state.phase_costs:
        return
    
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    
    # Build cost table
    table = Table(title="💰 Pipeline Cost Summary", box=box.ROUNDED, show_header=True)
    table.add_column("Phase", style="cyan", width=30)
    table.add_column("Model", style="white", width=40)
    table.add_column("Input Tokens", justify="right", style="green")
    table.add_column("Output Tokens", justify="right", style="yellow")
    table.add_column("Cost (USD)", justify="right", style="bold magenta")
    
    total_input = 0
    total_output = 0
    
    for phase, cost in state.phase_costs.items():
        usage = state.detailed_token_usage.get(phase, {})
        input_tok = usage.get("input", 0)
        output_tok = usage.get("output", 0)
        model = usage.get("model", state.phase_models.get(phase, "unknown"))
        
        total_input += input_tok
        total_output += output_tok
        
        table.add_row(
            phase.replace("_", " ").title(),
            model,
            f"{input_tok:,}",
            f"{output_tok:,}",
            f"${cost:.4f}",
        )
    
    # Total row
    table.add_row(
        "[bold]TOTAL[/bold]",
        "",
        f"[bold]{total_input:,}[/bold]",
        f"[bold]{total_output:,}[/bold]",
        f"[bold]${state.total_cost_usd:.4f}[/bold]",
    )
    
    console.print(table)
    
    # Additional context for free models
    if state.total_cost_usd == 0.0:
        console.print(Panel(
            "[green]✓ This run used only free models — no charges incurred![/green]",
            box=box.ROUNDED,
        ))
    elif state.total_cost_usd < 0.01:
        console.print(Panel(
            f"[green]✓ Ultra-low cost run: ${state.total_cost_usd:.4f} (less than 1¢)[/green]",
            box=box.ROUNDED,
        ))


# ─────────────────────────────────────────────────────────────────────
# JSON EXPORT
# ─────────────────────────────────────────────────────────────────────


def export_to_json(state: PipelineState, path: str) -> None:
    """
    Export complete pipeline state to JSON file.
    
    Args:
        state: PipelineState to export
        path: File path to save to
        
    Raises:
        PermissionError: If write permission is denied
        OSError: If disk is full or path is invalid
        TypeError: If state contains non-serializable data
    """
    import logging
    logger = logging.getLogger(__name__)

    def _serialize(obj: Any) -> Any:
        if hasattr(obj, "value"):  # Enum
            return obj.value
        if hasattr(obj, "__dataclass_fields__"):
            return {k: _serialize(v) for k, v in asdict(obj).items()}
        if isinstance(obj, list):
            return [_serialize(i) for i in obj]
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    data = {
        "problem":             state.problem,
        "preset_name":         state.preset_name,
        "started_at":          state.started_at.isoformat(),
        "task_type":           (state.task_type.value if hasattr(state.task_type, 'value') else state.task_type) if state.task_type else None,
        "task_type_rationale": state.task_type_rationale,
        "phase_models":        state.phase_models,
        "sub_problems":        _serialize((state.decomposition.sub_problems if hasattr(state.decomposition, 'sub_problems') else state.decomposition.get('sub_problems', [])) if state.decomposition else []),
        "assumptions":         _serialize((state.decomposition.assumptions if hasattr(state.decomposition, 'assumptions') else state.decomposition.get('assumptions', [])) if state.decomposition else []),
        "candidates":          _serialize(state.candidates),
        "scores":              _serialize(state.scores),
        "stress_results":      _serialize(state.stress_results),
        "final_solution":      _serialize(state.final_solution),
        "errors":              state.errors,
        "phase_logs":          state.phase_logs,
    }

    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Pipeline state exported to {path}")
    except PermissionError as e:
        logger.error(f"Permission denied exporting to {path}: {e}")
        raise
    except OSError as e:
        logger.error(f"OS error exporting to {path}: {e}")
        raise
    except TypeError as e:
        logger.error(f"Cannot serialize pipeline state: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error exporting to {path}: {e}")
        raise


# ═══════════════════════════════════════════════════════════════════════
# v2.2 NEW METHOD RENDERERS
# ═══════════════════════════════════════════════════════════════════════

# ── CoVe RENDERER ────────────────────────────────────────────────────


def render_perspective_content(content: str) -> str:
    """Convert non-standard perspective JSON to human-readable markdown.

    If the content is a JSON string with nested objects (e.g., from a
    destructive perspective that ignored the schema), flatten it to
    markdown bullet points. Otherwise return as-is.
    """
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return content  # Not JSON — return raw

    if not isinstance(data, dict):
        return content  # JSON array/primitive — return raw

    if "core_analysis" in data:
        return content  # Standard schema — return raw

    # Non-standard nested dict — flatten to markdown
    lines = []
    for category, items in data.items():
        lines.append(f"**{category.replace('_', ' ').title()}**")
        if isinstance(items, dict):
            for sub_key, sub_val in items.items():
                title = sub_key.replace('_', ' ').title()
                if isinstance(sub_val, dict):
                    val_text = sub_val.get('risk', sub_val.get('incorrect_assumption', str(sub_val)))
                else:
                    val_text = str(sub_val)
                lines.append(f"- **{title}**: {val_text}")
        else:
            lines.append(str(items))
        lines.append("")
    return "\n".join(lines)

