"""
Infrastructure Persistence Package

Event storage and retrieval for event-sourced aggregates.
Supports SQLite (default) and PostgreSQL (production).

PostgreSQL exports are lazy-loaded so that importing this package
does not crash when asyncpg is missing or broken.
"""

from reasoner.infrastructure.persistence.event_store import (
    EventStore,
    get_event_store,
    reset_event_store,
)
from reasoner.infrastructure.persistence.snapshots import (
    ReadModelProjection,
    SnapshotManager,
    SnapshotStrategy,
    setup_read_model_projections,
)

__all__ = [
    # SQLite
    'EventStore',
    'get_event_store',
    'reset_event_store',
    # PostgreSQL (lazy)
    'PostgreSQLEventStore',
    'get_postgres_store',
    'initialize_postgres_store',
    # Snapshots & CQRS
    'SnapshotStrategy',
    'SnapshotManager',
    'ReadModelProjection',
    'setup_read_model_projections',
]


def __getattr__(name: str):
    """Lazy-load PostgreSQL symbols so asyncpg is not required at import time."""
    if name in ('PostgreSQLEventStore', 'get_postgres_store', 'initialize_postgres_store'):
        from reasoner.infrastructure.persistence import postgres_store
        return getattr(postgres_store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
