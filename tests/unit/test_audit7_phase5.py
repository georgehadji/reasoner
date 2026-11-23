"""Audit 7, phase 5: the in-process maintenance loop and the two prunes."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from reasoner.api import maintenance
from reasoner.infrastructure.persistence.billing_deadletter_repo import (
    PostgresBillingDeadLetterRepo,
)
from reasoner.infrastructure.persistence.feedback_store import FeedbackEntry, FeedbackStore


class _Pool:
    def __init__(self, result):
        self._result = result

    async def set(self, key, value, nx=False, ex=None):
        assert key == maintenance.LOCK_KEY and nx and ex < maintenance.MAINTENANCE_INTERVAL_SECONDS
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _jobs(calls, failing=()):
    def make(name):
        async def job():
            calls.append(name)
            if name in failing:
                raise RuntimeError(name)
            return {}

        return job

    return lambda: [(f"maintenance.{n}", make(n)) for n in ("a", "b", "c")]


def _use_pool(monkeypatch, result):
    monkeypatch.setattr(
        "reasoner.infrastructure.valkey.client.get_valkey_pool", lambda: _Pool(result)
    )


@pytest.mark.asyncio
async def test_jobs_run_when_the_lock_is_held(monkeypatch):
    calls: list[str] = []
    _use_pool(monkeypatch, True)
    monkeypatch.setattr(maintenance, "_jobs", _jobs(calls))
    await maintenance.run_maintenance_once()
    assert calls == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_no_job_runs_when_another_worker_holds_the_lock(monkeypatch):
    calls: list[str] = []
    _use_pool(monkeypatch, None)
    monkeypatch.setattr(maintenance, "_jobs", _jobs(calls))
    await maintenance.run_maintenance_once()
    assert calls == []


@pytest.mark.asyncio
async def test_a_failing_job_does_not_stop_the_others(monkeypatch):
    calls: list[str] = []
    _use_pool(monkeypatch, True)
    monkeypatch.setattr(maintenance, "_jobs", _jobs(calls, failing={"a"}))
    await maintenance.run_maintenance_once()
    assert calls == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_valkey_down_still_runs_the_jobs(monkeypatch):
    calls: list[str] = []
    _use_pool(monkeypatch, ConnectionError("down"))
    monkeypatch.setattr(maintenance, "_jobs", _jobs(calls))
    await maintenance.run_maintenance_once()
    assert calls == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_feedback_prune_deletes_old_rows_only(tmp_path):
    store = FeedbackStore(db_path=tmp_path / "f.db", jsonl_path=tmp_path / "none.jsonl")
    now = datetime.now(UTC)
    for i, age in enumerate((200, 100, 10)):
        await store.insert(
            FeedbackEntry(
                conversation_id="c", message_id=str(i), rating="up",
                timestamp=(now - timedelta(days=age)).isoformat(),
            )
        )
    # The column default writes a space-separated stamp: the prune must read that shape too.
    old_default = (now - timedelta(days=300)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(tmp_path / "f.db") as conn:
        conn.execute(
            "INSERT INTO feedback_entries (timestamp, conversation_id, message_id, rating)"
            " VALUES (?, 'c', 'old', 'up')", (old_default,),
        )
    assert await store.prune_older_than(90) == 3
    remaining = await store.get_entries()
    assert [e.message_id for e in remaining] == ["2"]


@pytest.mark.asyncio
async def test_dead_letter_prune_issues_one_bounded_delete():
    seen = {}

    class _Conn:
        async def execute(self, sql, *args):
            seen["sql"], seen["args"] = sql, args
            return "DELETE 4"

    class _Acquire:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *exc):
            return False

    class _PgPool:
        def acquire(self, timeout=None):
            return _Acquire()

    repo = PostgresBillingDeadLetterRepo(_PgPool())

    async def _noop():
        return None

    repo._ensure_table = _noop
    assert await repo.prune_older_than(90) == 4
    assert "DELETE FROM failed_webhook_events" in seen["sql"]
    assert "created_at <" in seen["sql"] and seen["args"] == (90,)
