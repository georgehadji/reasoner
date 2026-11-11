"""perf audit LI-01: pipeline_owners needs an index on user_id.

GET /api/pipelines calls list_pipeline_ids_for_user on every request. Without an
index on user_id that is a full table scan, which also holds the event store's
single worker while it runs.
"""

from __future__ import annotations

import pytest

from reasoner.infrastructure.persistence.event_store_connection import EventStoreConnection

pytestmark = pytest.mark.unit

_OWNER_QUERY = "EXPLAIN QUERY PLAN SELECT pipeline_id FROM pipeline_owners WHERE user_id = ?"


def _plan(conn: EventStoreConnection) -> str:
    rows = conn._get_connection().execute(_OWNER_QUERY, ("u",)).fetchall()
    return " ".join(str(r["detail"]) for r in rows)


def test_owner_lookup_by_user_uses_an_index(tmp_path):
    conn = EventStoreConnection(tmp_path / "events.db")
    conn.init_db()

    assert "USING INDEX" in _plan(conn)
    conn.close()


def test_the_index_survives_the_nullable_migration(tmp_path):
    """The migration rebuilds the table; an index made before it would be dropped."""
    conn = EventStoreConnection(tmp_path / "events.db")
    raw = conn._get_connection()
    raw.executescript(
        """
        CREATE TABLE pipeline_owners (
            pipeline_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO pipeline_owners (pipeline_id, user_id, run_id) VALUES ('p1', 'u', 'p1');
        """
    )
    raw.commit()

    conn.init_db()

    assert "USING INDEX" in _plan(conn)
    assert raw.execute("SELECT COUNT(*) FROM pipeline_owners").fetchone()[0] == 1
    conn.close()
