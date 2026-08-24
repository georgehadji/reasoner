"""
Autonomous Debugging Protocol — Adversarial Validation Tests
Detection tests for VERIFIED hypotheses H-A, H-B, H-C.
"""

from __future__ import annotations

import time
from datetime import UTC

import pytest

# ═════════════════════════════════════════════════════════════════════
# H-A: Cache Poisoning from Incomplete Cache Key
# ═════════════════════════════════════════════════════════════════════

class TestCacheKeyCompleteness:
    def test_cache_key_differs_on_sequential(self):
        from reasoner.api.cache import _cache_key

        class MockReq:
            problem = "x"
            preset = "p"
            top_k = 2
            routing = None
            force_pipeline = False
            sequential = False
            enhance_prompt = False
            expert = False
            web_search = False
            smart_search = True
            source_type = "general"
            domain = None
            attachments = None

        req1 = MockReq()
        req2 = MockReq()
        req2.sequential = True
        assert _cache_key(req1) != _cache_key(req2)

    def test_cache_key_differs_on_enhance_prompt(self):
        from reasoner.api.cache import _cache_key

        class MockReq:
            problem = "x"
            preset = "p"
            top_k = 2
            routing = None
            force_pipeline = False
            sequential = False
            enhance_prompt = False
            expert = False
            web_search = False
            smart_search = True
            source_type = "general"
            domain = None
            attachments = None

        req1 = MockReq()
        req2 = MockReq()
        req2.enhance_prompt = True
        assert _cache_key(req1) != _cache_key(req2)

    def test_cache_key_differs_on_source_type(self):
        from reasoner.api.cache import _cache_key

        class MockReq:
            problem = "x"
            preset = "p"
            top_k = 2
            routing = None
            force_pipeline = False
            sequential = False
            enhance_prompt = False
            expert = False
            web_search = False
            smart_search = True
            source_type = "general"
            domain = None
            attachments = None

        req1 = MockReq()
        req2 = MockReq()
        req2.source_type = "academic"
        assert _cache_key(req1) != _cache_key(req2)

    def test_cache_key_differs_on_domain(self):
        from reasoner.api.cache import _cache_key

        class MockReq:
            problem = "x"
            preset = "p"
            top_k = 2
            routing = None
            force_pipeline = False
            sequential = False
            enhance_prompt = False
            expert = False
            web_search = False
            smart_search = True
            source_type = "general"
            domain = None
            attachments = None

        req1 = MockReq()
        req2 = MockReq()
        req2.domain = "arxiv.org"
        assert _cache_key(req1) != _cache_key(req2)


# ═════════════════════════════════════════════════════════════════════
# H-B: Global Pipeline Cancellation via Invalid run_id
# ═════════════════════════════════════════════════════════════════════

class TestStopPipelineScope:
    @pytest.mark.asyncio
    async def test_invalid_run_id_does_not_cancel_active_runs(self):
        from reasoner.api import _run_store, stop_pipeline

        await _run_store.reset()
        await _run_store.add("run-a")
        await _run_store.add("run-b")

        result = await stop_pipeline(run_id="fake-id")

        event_a = await _run_store.get_cancel_event("run-a")
        event_b = await _run_store.get_cancel_event("run-b")
        assert event_a is None or not event_a.is_set()
        assert event_b is None or not event_b.is_set()
        assert result["cancelled"] == []

    @pytest.mark.asyncio
    async def test_valid_run_id_cancels_only_that_run(self):
        from reasoner.api import _run_store, stop_pipeline

        await _run_store.reset()
        await _run_store.add("run-a")
        await _run_store.add("run-b")

        result = await stop_pipeline(run_id="run-a")

        event_a = await _run_store.get_cancel_event("run-a")
        event_b = await _run_store.get_cancel_event("run-b")
        assert event_a is not None and event_a.is_set()
        assert event_b is not None and not event_b.is_set()
        assert result["cancelled"] == ["run-a"]

    @pytest.mark.asyncio
    async def test_global_stop_without_run_id_cancels_all(self):
        from uuid import UUID

        from reasoner.api import _run_store, stop_pipeline
        from reasoner.domain.saas import User

        await _run_store.reset()
        await _run_store.add("run-a")
        await _run_store.add("run-b")

        # Global stop requires an authenticated user with admin scope
        class AdminUser(User):
            __slots__ = ("scopes",)
            def __init__(self, id, email, scopes=None):
                from datetime import datetime
                object.__setattr__(self, "id", id)
                object.__setattr__(self, "email", email)
                object.__setattr__(self, "display_name", None)
                object.__setattr__(self, "created_at", datetime.now(UTC))
                object.__setattr__(self, "scopes", scopes or [])

        mock_user = AdminUser(id=UUID("11111111-1111-1111-1111-111111111111"), email="test@example.com", scopes=["admin"])
        result = await stop_pipeline(run_id=None, user=mock_user)

        event_a = await _run_store.get_cancel_event("run-a")
        event_b = await _run_store.get_cancel_event("run-b")
        assert event_a is not None and event_a.is_set()
        assert event_b is not None and event_b.is_set()
        assert set(result["cancelled"]) == {"run-a", "run-b"}


# ═════════════════════════════════════════════════════════════════════
# H-C: Rate Limiter Fixed-Window Reset
# ═════════════════════════════════════════════════════════════════════

class TestRateLimiterSlidingWindow:
    def test_reset_snaps_to_exact_boundary(self, monkeypatch):
        """
        Verify that _in_memory_reset_windows_if_needed snaps window start to the
        exact boundary (+= N * period) rather than resetting to 'now'.
        """
        from reasoner.rate_limiter import ClientBucket, RateLimitConfig, RateLimiter

        rl = RateLimiter(RateLimitConfig(requests_per_minute=2, burst_size=2))
        base_time = 1000.0

        # Manually create a bucket with known window starts
        bucket = ClientBucket()
        bucket.minute_window_start = base_time
        bucket.hour_window_start = base_time
        bucket.last_update = base_time

        # Advance time by 125 seconds (2 full minute windows + 5s remainder)
        monkeypatch.setattr(time, "monotonic", lambda: base_time + 125.0)
        rl._in_memory_reset_windows_if_needed(bucket)

        # Should snap to base_time + 2*60 = 1120.0 (not reset to 1125.0)
        assert bucket.minute_window_start == base_time + 120.0
        assert bucket.requests_minute == 0

    def test_hour_window_snaps_to_exact_boundary(self, monkeypatch):
        from reasoner.rate_limiter import ClientBucket, RateLimitConfig, RateLimiter

        rl = RateLimiter(RateLimitConfig(requests_per_minute=2, burst_size=2))
        base_time = 1000.0

        bucket = ClientBucket()
        bucket.minute_window_start = base_time
        bucket.hour_window_start = base_time
        bucket.last_update = base_time

        # Advance by 2 hours + 5 minutes
        monkeypatch.setattr(time, "monotonic", lambda: base_time + 7500.0)
        rl._in_memory_reset_windows_if_needed(bucket)

        # Should snap to base_time + 2*3600 = 8200.0 (not reset to 8500.0)
        assert bucket.hour_window_start == base_time + 7200.0
        assert bucket.requests_hour == 0

    def test_no_reset_when_inside_window(self, monkeypatch):
        from reasoner.rate_limiter import ClientBucket, RateLimitConfig, RateLimiter

        rl = RateLimiter(RateLimitConfig(requests_per_minute=2, burst_size=2))
        base_time = 1000.0

        bucket = ClientBucket()
        bucket.minute_window_start = base_time
        bucket.hour_window_start = base_time
        bucket.last_update = base_time
        bucket.requests_minute = 1
        bucket.requests_hour = 1

        # Advance by only 30 seconds
        monkeypatch.setattr(time, "monotonic", lambda: base_time + 30.0)
        rl._in_memory_reset_windows_if_needed(bucket)

        # Nothing should change
        assert bucket.minute_window_start == base_time
        assert bucket.hour_window_start == base_time
        assert bucket.requests_minute == 1
        assert bucket.requests_hour == 1
