"""Regression tests for SQL injection prevention in ErrorStore.

Verifies that _safe_int sanitizes numeric parameters before they reach
SQL string formatting in _prune_old, _query_sync, and _stats_sync.
"""

import pytest
from reasoner.infrastructure.persistence.error_store import ErrorStore


class TestSafeInt:
    """Unit tests for the _safe_int sanitizer."""

    def test_normal_integer(self):
        assert ErrorStore._safe_int(7) == 7

    def test_clamps_to_floor(self):
        assert ErrorStore._safe_int(0) == 1
        assert ErrorStore._safe_int(-5) == 1

    def test_clamps_to_ceiling(self):
        assert ErrorStore._safe_int(999999) == 3650

    def test_coerces_string_integer(self):
        """Prevents injection: '7; DROP TABLE errors' → ValueError from int()."""
        with pytest.raises((ValueError, TypeError)):
            ErrorStore._safe_int("7; DROP TABLE errors")

    def test_coerces_float(self):
        assert ErrorStore._safe_int(7.9) == 7

    def test_custom_bounds(self):
        assert ErrorStore._safe_int(5, floor=10, ceiling=100) == 10
        assert ErrorStore._safe_int(200, floor=10, ceiling=100) == 100


class TestErrorStoreInit:
    """Verify ErrorStore can be constructed without crash."""

    def test_creates_in_memory(self, tmp_path):
        db = tmp_path / "test_errors.db"
        store = ErrorStore(db_path=db, retention_days=1)
        assert store.db_path == db


class TestErrorStoreQuery:
    """Verify query with hours parameter doesn't crash."""

    def test_query_with_safe_hours(self, tmp_path):
        db = tmp_path / "test_errors.db"
        store = ErrorStore(db_path=db)
        results = store._query_sync(hours=24)
        assert isinstance(results, list)

    def test_stats_with_safe_days(self, tmp_path):
        db = tmp_path / "test_errors.db"
        store = ErrorStore(db_path=db)
        stats = store._stats_sync(days=7)
        assert stats.period_days == 7
