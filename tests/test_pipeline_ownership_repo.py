"""Unit tests for PipelineOwnershipRepository (SQLite-backed).

This store replaces the JSON-file ownership map, whose lookup collapsed
every failure mode (missing file, corrupt JSON, unknown pipeline) into the
same `None` result, which every caller then treated as "allowed". These
tests pin the load-bearing distinction: "no record exists" (get_owner
returns None) versus "record exists with no owner" (OwnershipRecord with
user_id=None) — Phase 2 authorization logic depends on being able to tell
these apart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reasoner.application.ports.pipeline_ownership_port import OwnershipRecord
from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
    PipelineOwnershipRepository,
)


@pytest.fixture
def repo(tmp_path: Path) -> PipelineOwnershipRepository:
    db_path = tmp_path / "test_events.db"
    return PipelineOwnershipRepository(db_path=db_path)


@pytest.mark.asyncio
async def test_get_owner_returns_none_for_unknown_pipeline(repo):
    """No record at all -> None, distinct from an owned-by-nobody record."""
    assert await repo.get_owner("does-not-exist") is None


@pytest.mark.asyncio
async def test_set_then_get_owner_roundtrips(repo):
    await repo.set_owner("pipeline-1", "user-a", "pipeline-1")
    record = await repo.get_owner("pipeline-1")
    assert record == OwnershipRecord(user_id="user-a", run_id="pipeline-1")


@pytest.mark.asyncio
async def test_set_owner_with_none_user_id_is_explicit_anonymous_record(repo):
    """An explicitly anonymous run has a record (not None) with user_id=None —
    the caller must be able to tell this apart from no record existing."""
    await repo.set_owner("pipeline-anon", None, "pipeline-anon")
    record = await repo.get_owner("pipeline-anon")
    assert record is not None
    assert record.user_id is None
    assert record.run_id == "pipeline-anon"


@pytest.mark.asyncio
async def test_set_owner_upserts_idempotently(repo):
    await repo.set_owner("pipeline-1", "user-a", "pipeline-1")
    await repo.set_owner("pipeline-1", "user-b", "pipeline-1")  # overwrite
    record = await repo.get_owner("pipeline-1")
    assert record.user_id == "user-b"


@pytest.mark.asyncio
async def test_list_pipeline_ids_for_user(repo):
    await repo.set_owner("p1", "user-a", "p1")
    await repo.set_owner("p2", "user-a", "p2")
    await repo.set_owner("p3", "user-b", "p3")

    ids = await repo.list_pipeline_ids_for_user("user-a")
    assert sorted(ids) == ["p1", "p2"]

    ids_b = await repo.list_pipeline_ids_for_user("user-b")
    assert ids_b == ["p3"]

    assert await repo.list_pipeline_ids_for_user("user-c") == []


@pytest.mark.asyncio
async def test_backfill_from_json_imports_all_entries(repo, tmp_path: Path):
    json_path = tmp_path / "pipeline_owners.json"
    json_path.write_text(
        json.dumps({"p1": "user-a", "p2": None, "p3": "user-b"}),
        encoding="utf-8",
    )

    count = await repo.backfill_from_json(json_path)
    assert count == 3

    assert (await repo.get_owner("p1")).user_id == "user-a"
    assert (await repo.get_owner("p2")).user_id is None
    assert (await repo.get_owner("p3")).user_id == "user-b"


@pytest.mark.asyncio
async def test_backfill_from_json_never_overwrites_existing_rows(repo, tmp_path: Path):
    """Backfill only fills gaps — a row already set via set_owner (e.g. after
    cutover) must survive a backfill run, even if the JSON disagrees."""
    await repo.set_owner("p1", "user-real", "p1")

    json_path = tmp_path / "pipeline_owners.json"
    json_path.write_text(json.dumps({"p1": "user-stale-json-value"}), encoding="utf-8")

    count = await repo.backfill_from_json(json_path)
    assert count == 0
    assert (await repo.get_owner("p1")).user_id == "user-real"


@pytest.mark.asyncio
async def test_backfill_from_json_missing_file_is_a_noop(repo, tmp_path: Path):
    count = await repo.backfill_from_json(tmp_path / "does-not-exist.json")
    assert count == 0


@pytest.mark.asyncio
async def test_backfill_from_json_corrupt_file_is_a_noop(repo, tmp_path: Path):
    json_path = tmp_path / "corrupt.json"
    json_path.write_text("{not valid json", encoding="utf-8")
    count = await repo.backfill_from_json(json_path)
    assert count == 0


def test_pipeline_owners_table_user_id_is_nullable(tmp_path: Path):
    """Regression guard for the schema migration: a fresh DB must create
    pipeline_owners.user_id as nullable, not NOT NULL as it originally was."""
    from reasoner.infrastructure.persistence.event_store_connection import (
        EventStoreConnection,
    )

    conn = EventStoreConnection(tmp_path / "fresh.db")
    conn.init_db()
    cols = conn._get_connection().execute("PRAGMA table_info(pipeline_owners)").fetchall()
    user_id_col = next(c for c in cols if c["name"] == "user_id")
    assert user_id_col["notnull"] == 0
    conn.close()


def test_migration_relaxes_preexisting_not_null_constraint(tmp_path: Path):
    """A DB created before this change (user_id NOT NULL) must be rebuilt
    nullable on the next init_db() call, and existing rows must survive."""
    import sqlite3
    from reasoner.infrastructure.persistence.event_store_connection import (
        EventStoreConnection,
    )

    db_path = tmp_path / "legacy.db"
    raw = sqlite3.connect(str(db_path))
    raw.execute(
        """
        CREATE TABLE pipeline_owners (
            pipeline_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    raw.execute(
        "INSERT INTO pipeline_owners (pipeline_id, user_id, run_id) VALUES (?, ?, ?)",
        ("legacy-p1", "legacy-user", "legacy-p1"),
    )
    raw.commit()
    raw.close()

    conn = EventStoreConnection(db_path)
    conn.init_db()  # should migrate in place

    row = conn._get_connection().execute(
        "SELECT user_id, run_id FROM pipeline_owners WHERE pipeline_id = ?",
        ("legacy-p1",),
    ).fetchone()
    assert row["user_id"] == "legacy-user"
    assert row["run_id"] == "legacy-p1"

    cols = conn._get_connection().execute("PRAGMA table_info(pipeline_owners)").fetchall()
    user_id_col = next(c for c in cols if c["name"] == "user_id")
    assert user_id_col["notnull"] == 0
    conn.close()
