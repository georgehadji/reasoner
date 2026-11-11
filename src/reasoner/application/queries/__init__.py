"""
Application Layer - Queries (Read Operations)

Queries represent requests for data. They are handled by query
handlers which return read-optimized DTOs (not domain models).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Query:
    """Base class for all queries."""
    query_id: str
    timestamp: float


# ─────────────────────────────────────────────────────────────────────
# PIPELINE QUERIES
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GetPipelineStatusQuery(Query):
    """Query to get pipeline execution status."""
    pipeline_id: str


@dataclass(frozen=True)
class GetPipelineHistoryQuery(Query):
    """Query to get pipeline event history."""
    pipeline_id: str
    from_version: int = 0


@dataclass(frozen=True)
class ListPipelinesQuery(Query):
    """Query to list recent pipelines."""
    limit: int = 50
    offset: int = 0
    status: str | None = None  # Filter by status
    method: str | None = None  # Filter by method


# ─────────────────────────────────────────────────────────────────────
# WIDGET QUERIES
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GetWidgetStateQuery(Query):
    """Query to get widget state."""
    widget_id: str


@dataclass(frozen=True)
class ListAvailableWidgetsQuery(Query):
    """Query to list available widgets."""
    query: str = ""  # For relevance scoring


# ─────────────────────────────────────────────────────────────────────
# HISTORY QUERIES
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GetHistoryQuery(Query):
    """Query to get search history."""
    limit: int = 50
    offset: int = 0
    search: str = ""  # Filter by search term
    #: The caller's own pipeline ids. None means no caller scope was given, and
    #: the handler returns nothing rather than every user's problems.
    owner_ids: tuple[str, ...] | None = None


@dataclass(frozen=True)
class GetHistoryEntryQuery(Query):
    """Query to get specific history entry."""
    entry_id: str


# ─────────────────────────────────────────────────────────────────────
# PRESET QUERIES
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ListPresetsQuery(Query):
    """Query to list available presets."""
    method: str | None = None  # Filter by method


@dataclass(frozen=True)
class GetPresetQuery(Query):
    """Query to get specific preset configuration."""
    preset_name: str


# ─────────────────────────────────────────────────────────────────────
# MODEL QUERIES
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ListModelsQuery(Query):
    """Query to list available models."""
    provider: str | None = None  # Filter by provider


@dataclass(frozen=True)
class GetModelQuery(Query):
    """Query to get specific model info."""
    model_id: str


# ─────────────────────────────────────────────────────────────────────
# HEALTH QUERIES
# ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HealthCheckQuery(Query):
    """Query to check system health."""
    include_providers: bool = True
    include_memory: bool = True
    include_search: bool = True


@dataclass(frozen=True)
class GetProviderHealthQuery(Query):
    """Query to get provider health status."""
    provider: str | None = None  # Specific provider or all
