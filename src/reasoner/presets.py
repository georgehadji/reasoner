"""
Reasoner Pipeline — Routing Presets
Backward-compatible shim.  Core logic moved to reasoner.domain.preset_core;
preset data moved to reasoner.domain.preset_registry.
"""

from reasoner.domain.preset_core import (
    _KNOWN_ROUTING_ROLES,
    PipelinePreset,
    get_method_from_preset,
    get_preset_tier,
    get_preset_price_tier,
    build_auto_preset,
    FOLLOWUP_AGENT_MODELS,
    _METHOD_TO_SLUG,
)
from reasoner.domain.preset_registry import (
    _PRESET_CONFIGS,
    PRESETS,
)
from reasoner.infrastructure.llm.router import ProviderRouter


def get_preset(name: str) -> PipelinePreset:
    """Get a preset by name. Raises ValueError if not found."""
    if name not in PRESETS:
        available = ", ".join(sorted(PRESETS.keys()))
        raise ValueError(f"Unknown preset: {name!r}. Available: {available}")
    return PRESETS[name]


def is_valid_preset_name(name: str) -> bool:
    """Return True if name is a known preset key."""
    return name in PRESETS


def resolve_preset_name(name: str) -> str:
    """Return name unchanged if valid, else raise ValueError."""
    if name not in PRESETS:
        available = ", ".join(sorted(PRESETS.keys()))
        raise ValueError(f"Unknown preset: {name!r}. Available: {available}")
    return name


def build_custom_router(routing_dict: dict[str, str]) -> ProviderRouter:
    """
    Build a ProviderRouter from a custom role->model_id dict.
    The 'primary' key (required) sets the fallback provider.

    Example:
        build_custom_router({
            "primary":        "claude-sonnet",
            "constructive":   "kimi-k2-6",
            "scoring":        "sonar-pro",
            "synthesis":      "glm-5",
        })
    """
    if "primary" not in routing_dict:
        raise ValueError("Custom routing must include a 'primary' key.")

    primary_id = routing_dict["primary"]
    rest = {k: v for k, v in routing_dict.items() if k != "primary"}
    return ProviderRouter.from_model_ids(primary_id=primary_id, routing=rest)


def print_presets_summary() -> None:
    """Print a formatted summary of all available presets."""
    from rich.console import Console
    from rich.table import Table
    from rich import box

    console = Console()
    table = Table(title="Reasoner v2.0 — Available Pipeline Presets", box=box.ROUNDED)
    table.add_column("Preset ID", style="cyan", width=22)
    table.add_column("Name", width=30)
    table.add_column("Primary Model", width=18)
    table.add_column("API Keys Needed", width=40)

    for pid, preset in PRESETS.items():
        missing = preset.missing_keys()
        key_status = (
            "[green]✓ All set[/green]" if not missing
            else f"[red]Missing: {', '.join(missing)}[/red]"
        )
        table.add_row(pid, preset.name, preset.primary_id, key_status)

    console.print(table)


__all__ = [
    "_KNOWN_ROUTING_ROLES",
    "_PRESET_CONFIGS",
    "PRESETS",
    "PipelinePreset",
    "get_method_from_preset",
    "get_preset_tier",
    "get_preset_price_tier",
    "build_auto_preset",
    "FOLLOWUP_AGENT_MODELS",
    "get_preset",
    "is_valid_preset_name",
    "resolve_preset_name",
    "build_custom_router",
    "print_presets_summary",
]
