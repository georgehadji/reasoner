"""A neuro session file that cannot be read must not read as an empty session.

P5, docs/plans/root-cause-remediation-2026-09-07.md. Every caller of these
readers checks ``.exists()`` first, so an exception inside them is a real read
failure on a file that is present -- but they returned ``[]``, which is
exactly what a session with no history returns. ``get_recent_context()`` feeds
that straight into bootstrap context injection.
"""

from __future__ import annotations

import gzip
import json
import logging

import pytest

from reasoner.neuro.sessions import SessionManager

DEGRADE_LOGGER = "reasoner.core.degrade"


@pytest.fixture
def manager(tmp_path) -> SessionManager:
    return SessionManager(tmp_path)


def _sites(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records]


class TestCorruptArchive:
    def test_a_corrupt_gz_is_reported_not_returned_as_empty(self, manager, caplog) -> None:
        corrupt = manager.warm_dir / "sess-1.jsonl.gz"
        corrupt.write_bytes(b"this is not gzip data")

        with caplog.at_level(logging.WARNING, logger=DEGRADE_LOGGER):
            entries = manager._read_jsonl_gz(corrupt)

        assert entries == [], "nothing was readable, so there is nothing to return"
        assert any("site=neuro.sessions.read_jsonl_gz" in m for m in _sites(caplog)), (
            f"expected a degradation record, got: {_sites(caplog)}"
        )

    def test_the_public_transcript_call_reports_it_too(self, manager, caplog) -> None:
        """get_session_transcript is the path a caller actually takes."""
        (manager.warm_dir / "sess-2.jsonl.gz").write_bytes(b"not gzip")

        with caplog.at_level(logging.WARNING, logger=DEGRADE_LOGGER):
            assert manager.get_session_transcript("sess-2") == []

        assert any("site=neuro.sessions.read_jsonl_gz" in m for m in _sites(caplog))

    def test_a_readable_gz_still_round_trips(self, manager) -> None:
        """The guard above must not have cost us the normal path."""
        good = manager.warm_dir / "sess-3.jsonl.gz"
        with gzip.open(good, "wt", encoding="utf-8") as gz:
            gz.write(json.dumps({"_type": "exchange", "prompt": "hi"}) + "\n")

        assert manager.get_session_transcript("sess-3") == [
            {"_type": "exchange", "prompt": "hi"}
        ]


class TestCountCachePoisoning:
    def test_a_failed_read_is_not_cached_as_zero_exchanges(self, manager, caplog) -> None:
        """A transient read error used to pin the file at 0 for the process.

        ``_count_entries`` cached ``count`` after the except block, so the 0
        left over from a failed open stuck in ``_counts_cache`` and every later
        call returned it without retrying.
        """
        path = manager.hot_dir / "sess-4.jsonl"
        path.mkdir()  # a directory where a file is expected: open() raises

        with caplog.at_level(logging.WARNING, logger=DEGRADE_LOGGER):
            assert manager._count_entries(path) == 0

        assert any("site=neuro.sessions.count_entries" in m for m in _sites(caplog))
        assert str(path) not in manager._counts_cache, "a count we could not measure was cached"

        # Replace the directory with a real file: the next call must re-read.
        path.rmdir()
        path.write_text(json.dumps({"_type": "exchange"}) + "\n")
        assert manager._count_entries(path) == 1


class TestWarmListing:
    def test_an_unreadable_warm_file_is_reported_not_silently_skipped(
        self, manager, caplog
    ) -> None:
        (manager.warm_dir / "good.json").write_text(json.dumps({"summary": "s"}))
        (manager.warm_dir / "broken.json").write_text("{not json")

        with caplog.at_level(logging.WARNING, logger=DEGRADE_LOGGER):
            listed = manager.get_warm_sessions()

        assert [s["session_id"] for s in listed] == ["good"]
        assert any("site=neuro.sessions.warm_listing" in m for m in _sites(caplog)), (
            f"expected a degradation record, got: {_sites(caplog)}"
        )
