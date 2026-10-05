"""Regression tests for fix/persistent-data-paths (re-lands PR #9).

feedback_store.py, event_store.py, pipeline_ownership_repo.py and
uploader.py each defaulted their storage path to something computed from
``Path(__file__)``, which lands inside the installed package directory
(``src/reasoner/...``). A container redeploy replaces that directory
wholesale, so anything written there -- feedback, the event store,
pipeline-ownership records, uploaded files -- is silently lost.

Each store now reads a dedicated setting first (``FEEDBACK_DB_PATH``,
``EVENT_STORE_DB_PATH``, ``UPLOAD_STORAGE_DIR``) and only falls back to the
historical in-package default when it is unset. These tests pin that: set
the setting to a temp path, construct the store, assert it wrote there
instead of the in-package default.
"""

from __future__ import annotations

import importlib

from reasoner.core.settings import settings
from reasoner.infrastructure.persistence.event_store import EventStore
from reasoner.infrastructure.persistence.feedback_store import FeedbackStore
from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
    PipelineOwnershipRepository,
)


def test_feedback_store_honors_feedback_db_path_setting(tmp_path, monkeypatch):
    target = tmp_path / "custom_feedback.db"
    monkeypatch.setattr(settings, "FEEDBACK_DB_PATH", str(target))

    store = FeedbackStore(jsonl_path=tmp_path / "unused.jsonl")

    assert store.db_path == target
    assert target.exists()


def test_feedback_store_falls_back_to_in_package_default_when_unset(
    tmp_path, monkeypatch
):
    """Unset FEEDBACK_DB_PATH must not change local dev/test behavior."""
    from pathlib import Path

    from reasoner.infrastructure.persistence import (
        feedback_store as feedback_store_module,
    )

    monkeypatch.setattr(settings, "FEEDBACK_DB_PATH", "")
    expected = Path(feedback_store_module.__file__).parent.parent.parent / "feedback.db"

    store = FeedbackStore(jsonl_path=tmp_path / "unused.jsonl")

    assert store.db_path == expected


def test_event_store_honors_event_store_db_path_setting(tmp_path, monkeypatch):
    target = tmp_path / "custom_events.db"
    monkeypatch.setattr(settings, "EVENT_STORE_DB_PATH", str(target))

    store = EventStore()

    assert store.db_path == target
    assert target.exists()


def test_pipeline_ownership_repo_honors_event_store_db_path_setting(tmp_path, monkeypatch):
    target = tmp_path / "custom_events.db"
    monkeypatch.setattr(settings, "EVENT_STORE_DB_PATH", str(target))

    repo = PipelineOwnershipRepository()

    assert repo._conn.db_path == target
    assert target.exists()


def test_upload_dir_honors_upload_storage_dir_setting(tmp_path, monkeypatch):
    target = tmp_path / "custom_uploads"
    monkeypatch.setattr(settings, "UPLOAD_STORAGE_DIR", str(target))

    import reasoner.infrastructure.uploader as uploader_module

    try:
        importlib.reload(uploader_module)
        assert uploader_module.UPLOAD_DIR == target
        assert target.exists()
    finally:
        # Restore the module to its unset-setting state so later tests that
        # import reasoner.infrastructure.uploader see the historical default.
        monkeypatch.setattr(settings, "UPLOAD_STORAGE_DIR", "")
        importlib.reload(uploader_module)


# ── configured path in a directory that does not exist yet ──
# sqlite3.connect() will not create parent directories, so a bind-mounted
# /app/history that is empty (or a nested path) used to fail with
# OperationalError: unable to open database file.


def test_event_store_creates_missing_parent_dir(tmp_path, monkeypatch):
    target = tmp_path / "nope" / "nested" / "events.db"
    monkeypatch.setattr(settings, "EVENT_STORE_DB_PATH", str(target))

    EventStore()

    assert target.exists()


def test_pipeline_ownership_repo_creates_missing_parent_dir(tmp_path, monkeypatch):
    target = tmp_path / "nope" / "nested" / "events.db"
    monkeypatch.setattr(settings, "EVENT_STORE_DB_PATH", str(target))

    PipelineOwnershipRepository()

    assert target.exists()


def test_feedback_store_creates_missing_parent_dir(tmp_path, monkeypatch):
    target = tmp_path / "nope" / "nested" / "feedback.db"
    monkeypatch.setattr(settings, "FEEDBACK_DB_PATH", str(target))

    FeedbackStore(jsonl_path=tmp_path / "unused.jsonl")

    assert target.exists()


def test_event_store_memory_db_still_works():
    store = EventStore(db_path=":memory:")

    assert store.db_path.name == ":memory:"


# ── unset setting keeps the historical in-package default ──


def test_event_store_falls_back_to_in_package_default_when_unset(monkeypatch):
    from pathlib import Path

    from reasoner.infrastructure.persistence import event_store as event_store_module

    monkeypatch.setattr(settings, "EVENT_STORE_DB_PATH", "")
    monkeypatch.setattr(
        event_store_module, "EventStoreConnection", lambda p: _StubConn(p)
    )

    store = EventStore()

    assert store.db_path == Path(event_store_module.__file__).parent.parent / "events.db"


def test_pipeline_ownership_repo_falls_back_to_in_package_default_when_unset(
    monkeypatch,
):
    from pathlib import Path

    from reasoner.infrastructure.persistence import (
        pipeline_ownership_repo as repo_module,
    )

    monkeypatch.setattr(settings, "EVENT_STORE_DB_PATH", "")
    monkeypatch.setattr(repo_module, "EventStoreConnection", lambda p: _StubConn(p))

    repo = PipelineOwnershipRepository()

    assert repo._conn.db_path == (
        Path(repo_module.__file__).parent.parent.parent / "events.db"
    )


class _StubConn:
    """Records the path without opening (or creating) the real in-package file."""

    def __init__(self, db_path):
        self.db_path = db_path

    def init_db(self):
        pass
