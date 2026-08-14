"""Spend caps must bind on the path that actually serves users.

executor.py sets state._spend_cap_exceeded, but only the CLI WorkflowStrategy
runner honoured it. The SSE loop in api/execution/pipeline.py — which serves
every HTTP request — ran the remaining phases anyway and kept billing.

The monthly cap had three separate defects that each made it unenforceable:
keyed by conversation (a new chat reset the budget), stored in-process (each of
N workers allowed a full cap, and a restart cleared them), and never reset on a
month boundary.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestSseLoopHonoursTheCap:
    def test_sse_loop_checks_the_flag(self):
        src = (REPO_ROOT / "src" / "reasoner" / "api" / "execution" / "pipeline.py").read_text(
            encoding="utf-8"
        )
        assert "_spend_cap_exceeded" in src, (
            "the SSE phase loop must skip phases once a spend cap trips; without "
            "this check a capped run keeps calling paid models"
        )

    def test_sse_loop_tells_the_client(self):
        src = (REPO_ROOT / "src" / "reasoner" / "api" / "execution" / "pipeline.py").read_text(
            encoding="utf-8"
        )
        assert "spend_cap_exceeded" in src and "sse_emit" in src, (
            "a truncated run must be visible to the client, not silently short"
        )


class TestMonthlySpendAccrual:
    async def test_accrues_across_calls(self, monkeypatch):
        """Two calls for the same subject accumulate into one running total."""
        from reasoner.infrastructure.llm import executor

        monkeypatch.setattr(executor, "_MONTHLY_SPEND", {})
        # Force the in-process fallback: no Redis in the test environment.
        monkeypatch.setattr(
            "reasoner.infrastructure.redis.client.get_redis",
            lambda: (_ for _ in ()).throw(RuntimeError("no redis")),
        )

        first = await executor.accrue_monthly_spend("user-1", 0.25)
        second = await executor.accrue_monthly_spend("user-1", 0.30)

        assert first == pytest.approx(0.25)
        assert second == pytest.approx(0.55)

    async def test_subjects_are_isolated(self, monkeypatch):
        from reasoner.infrastructure.llm import executor

        monkeypatch.setattr(executor, "_MONTHLY_SPEND", {})
        monkeypatch.setattr(
            "reasoner.infrastructure.redis.client.get_redis",
            lambda: (_ for _ in ()).throw(RuntimeError("no redis")),
        )

        await executor.accrue_monthly_spend("user-1", 1.0)
        other = await executor.accrue_monthly_spend("user-2", 0.5)

        assert other == pytest.approx(0.5)

    def test_key_is_scoped_to_the_calendar_month(self):
        """Without a period in the key, 'monthly' means 'since process start'."""
        from reasoner.infrastructure.llm.executor import _monthly_spend_key

        key = _monthly_spend_key("user-1")
        assert re.search(r"\d{4}-\d{2}", key), f"no month period in key: {key}"
        assert "user-1" in key

    async def test_redis_is_preferred_over_memory(self, monkeypatch):
        """Redis is what makes the cap shared across workers and restarts."""
        from reasoner.infrastructure.llm import executor

        calls = {}

        class FakeRedis:
            async def incrbyfloat(self, key, amount):
                calls["key"] = key
                calls["amount"] = amount
                return 7.5

            async def expire(self, key, ttl):
                calls["ttl"] = ttl
                return True

        monkeypatch.setattr(
            "reasoner.infrastructure.redis.client.get_redis", lambda: FakeRedis()
        )

        total = await executor.accrue_monthly_spend("user-9", 2.5)

        assert total == pytest.approx(7.5)
        assert calls["amount"] == pytest.approx(2.5)
        assert "user-9" in calls["key"]
        # The key must expire on its own, or spend records accumulate forever.
        assert calls["ttl"] > 31 * 24 * 3600


class TestUserScopedKeying:
    def test_cap_keys_on_user_not_conversation(self):
        """Keying on conversation_id let a new chat reset the month's budget."""
        src = (
            REPO_ROOT / "src" / "reasoner" / "infrastructure" / "llm" / "executor.py"
        ).read_text(encoding="utf-8")
        block = src[src.index("Monthly spend cap check"):]
        block = block[: block.index("accrue_monthly_spend")]
        assert "user_id" in block, (
            "the monthly cap must prefer user_id; conversation_id alone means every "
            "new conversation starts the budget over"
        )


class TestPersistencePathsAreMountable:
    """Both defaulted inside the image, so redeploys destroyed the data."""

    def test_upload_dir_is_overridable(self):
        src = (REPO_ROOT / "src" / "reasoner" / "infrastructure" / "uploader.py").read_text(
            encoding="utf-8"
        )
        assert 'environ.get("UPLOAD_DIR")' in src, (
            "UPLOAD_DIR must be settable so uploads land on the mounted volume"
        )
        assert 'Path(__file__).parent / "uploads"' not in src

    def test_event_store_path_is_overridable(self):
        src = (
            REPO_ROOT
            / "src"
            / "reasoner"
            / "infrastructure"
            / "persistence"
            / "pipeline_ownership_repo.py"
        ).read_text(encoding="utf-8")
        assert 'environ.get("EVENT_STORE_PATH")' in src, (
            "pipeline ownership is authorization data — it must survive a redeploy"
        )

    def test_compose_points_both_at_volumes(self):
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        assert "UPLOAD_DIR=/app/uploads" in compose
        assert "EVENT_STORE_PATH=/app/history/events.db" in compose


class TestWorkerCountFitsMemoryLimit:
    def test_workers_are_sized_for_the_container(self):
        """Measured ~110 MB RSS per worker at import against a 1 G limit."""
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        match = re.search(r"UVICORN_WORKERS=(\d+)", compose)
        assert match, "UVICORN_WORKERS not set in docker-compose.yml"
        workers = int(match.group(1))
        assert workers <= 4, (
            f"{workers} workers x ~110 MB baseline exceeds the 1 G backend limit "
            "before serving a single request"
        )
