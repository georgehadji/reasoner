"""Audit 7, phase 8: dead code removed, the active-users gauge, and the vector-store helpers."""

from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from reasoner.documents import vector_store as vs


def test_the_router_and_executor_have_no_stream_parameter():
    from reasoner.infrastructure.llm.executor import LLMExecutor
    from reasoner.infrastructure.llm.router import ProviderRouter

    assert "stream" not in inspect.signature(ProviderRouter.call).parameters
    assert "stream" not in inspect.signature(LLMExecutor.execute).parameters


def test_require_tier_is_gone():
    from reasoner.api import dependencies

    assert not hasattr(dependencies, "require_tier")


@pytest.mark.asyncio
async def test_active_users_gauge_counts_distinct_users_from_query_log(monkeypatch):
    import reasoner.api as api

    seen: list[str] = []

    class _Pool:
        async def fetchval(self, sql):
            seen.append(sql)
            return 1

    sleeps = 0

    async def _sleep(_seconds):
        nonlocal sleeps
        sleeps += 1
        if sleeps > 1:
            raise asyncio.CancelledError

    gauge = MagicMock()
    monkeypatch.setattr(api, "_health_postgres_pool", _Pool())
    monkeypatch.setattr(api.asyncio, "sleep", _sleep)
    monkeypatch.setattr("reasoner.metrics.REASONER_ACTIVE_USERS", gauge)
    with pytest.raises(asyncio.CancelledError):
        await api._update_active_users_loop()

    assert seen == [api.ACTIVE_USERS_SQL]
    gauge.set.assert_called_once_with(1)


def test_the_gauge_query_uses_columns_the_baseline_creates():
    from reasoner.api import ACTIVE_USERS_SQL

    baseline = Path("migrations/alembic/versions/df9629e72f17_baseline.py").read_text(encoding="utf-8")
    block = re.search(r"CREATE TABLE IF NOT EXISTS query_log \((.*?)\);", baseline, re.S).group(1)
    assert "FROM query_log" in ACTIVE_USERS_SQL
    for column in ("user_id", "created_at"):
        assert column in ACTIVE_USERS_SQL and column in block


def test_rank_orders_chunks_by_cosine_similarity():
    query = [1.0, 0.0]
    chunks = [
        ("a", {"text": "far", "embedding": [0.0, 1.0]}),
        ("a", {"text": "near", "embedding": [1.0, 0.1]}),
        ("b", {"text": "none"}),  # no embedding: skipped
        ("b", {"text": "mid", "embedding": [1.0, 1.0]}),
    ]
    ranked = vs._rank(query, chunks, top_k=2)
    assert [text for _, _, text in ranked] == ["near", "mid"]
    assert ranked[0][0] == pytest.approx(vs._cosine_similarity(query, [1.0, 0.1]))


def test_a_sidecar_round_trips_through_the_thread_helpers(tmp_path):
    sidecar = {"chunks": [{"text": "hello", "embedding": [0.5, 0.5]}]}
    path = tmp_path / "f1.json"
    vs._write_sidecar(path, sidecar)
    assert "hello" not in path.read_text()  # encrypted on disk
    assert vs._load_chunks([("f1", path), ("missing", tmp_path / "none.json")]) == [
        ("f1", sidecar["chunks"][0])
    ]
