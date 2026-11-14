"""
Application Layer - Queries (Read Operations)

Queries represent requests for data. They are handled by query
handlers which return read-optimized DTOs (not domain models).
"""

from __future__ import annotations

from dataclasses import dataclass


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
