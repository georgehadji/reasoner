"""
Application Layer - Commands (Write Operations)

Commands represent intentions to change state. They are handled
by command handlers which produce domain events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from reasoner.core.constants import DEFAULT_PRESET, DEFAULT_TOP_K, DEFAULT_SOURCE_TYPE


@dataclass(frozen=True)
class Command:
    """Base class for all commands."""
    command_id: str
    timestamp: float


# ─────────────────────────────────────────────────────────────────────
# PIPELINE COMMANDS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RunPipelineCommand(Command):
    """
    Command to run the reasoning pipeline.
    
    This is the main command for executing a reasoning task.
    """
    problem: str
    preset: str = DEFAULT_PRESET
    method: str | None = None  # Auto-detected from preset if None
    top_k: int = DEFAULT_TOP_K
    source_type: str = DEFAULT_SOURCE_TYPE
    domain: str | None = None
    parallel: bool = True
    no_cache: bool = False
    # Authenticated caller, carried so the executor can record pipeline
    # ownership. Must reach the ownership write or the run is stored unowned,
    # which is_authorized() treats as world-readable.
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResumePipelineCommand(Command):
    """
    Command to resume a paused/failed pipeline.
    
    Uses event history to reconstruct state and continue.
    """
    pipeline_id: str
    from_phase: str | None = None  # Resume from specific phase
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StopPipelineCommand(Command):
    """Command to stop a running pipeline."""
    pipeline_id: str
    reason: str = "user_requested"


@dataclass(frozen=True)
class ClearPipelineCacheCommand(Command):
    """Command to clear pipeline cache."""
    all: bool = True  # Clear all or just expired
    older_than_hours: int = 24


# ─────────────────────────────────────────────────────────────────────
# WIDGET COMMANDS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ExecuteWidgetCommand(Command):
    """
    Command to execute a widget.
    
    Widgets are auto-detected features like weather, stocks, etc.
    """
    widget_type: str
    params: dict[str, Any] = field(default_factory=dict)
    auto_detect: bool = True  # Auto-detect from query
    query: str = ""  # For auto-detection


@dataclass(frozen=True)
class RefreshWidgetCommand(Command):
    """Command to refresh widget data."""
    widget_id: str


# ─────────────────────────────────────────────────────────────────────
# MEMORY COMMANDS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StoreMemoryCommand(Command):
    """Command to store conversation in memory."""
    prompt: str
    response: str
    agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    compress: bool = True


@dataclass(frozen=True)
class ClearMemoryCommand(Command):
    """Command to clear memory."""
    agent_id: str | None = None
    older_than_days: int = 30


# ─────────────────────────────────────────────────────────────────────
# HISTORY COMMANDS
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DeleteHistoryCommand(Command):
    """Command to delete history entry."""
    entry_id: str


@dataclass(frozen=True)
class ClearHistoryCommand(Command):
    """Command to clear all history."""
    older_than_days: int = 0  # 0 = all
