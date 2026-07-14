"""
Contract tests for the cancellation mechanism.

End-to-end verification that RunStateStore correctly signals cancellation
to running "pipeline" coroutines without cross-run interference.
"""

import asyncio

import pytest
import pytest_asyncio

from reasoner.api.run_state import RunStateStore


class TestCancellationContract:
    """Contract tests for per-run cancellation."""

    @pytest_asyncio.fixture
    async def store(self):
        s = RunStateStore()
        yield s
        await s.reset()

    async def _fake_pipeline(self, store: RunStateStore, run_id: str, done: list):
        """Simulate a long-running pipeline that checks cancellation."""
        event = await store.get_cancel_event(run_id)
        if event is None:
            return
        for _ in range(1000):
            if event.is_set():
                done.append((run_id, "cancelled"))
                return
            await asyncio.sleep(0.001)
        done.append((run_id, "completed"))

    @pytest.mark.asyncio
    async def test_cancel_stops_active_run(self, store):
        done = []
        await store.add("run-1")
        task = asyncio.create_task(self._fake_pipeline(store, "run-1", done))

        await asyncio.sleep(0.01)
        await store.request_cancel("run-1")

        await asyncio.wait_for(task, timeout=2.0)
        assert done == [("run-1", "cancelled")]

    @pytest.mark.asyncio
    async def test_concurrent_cancellations_no_lost_signals(self, store):
        done = []
        run_ids = [f"run-{i}" for i in range(20)]

        for rid in run_ids:
            await store.add(rid)

        tasks = [
            asyncio.create_task(self._fake_pipeline(store, rid, done))
            for rid in run_ids
        ]

        await asyncio.sleep(0.01)
        await store.request_cancel_all()

        await asyncio.gather(*tasks)

        assert len(done) == 20
        assert all(status == "cancelled" for _, status in done)

    @pytest.mark.asyncio
    async def test_cancel_one_run_does_not_affect_other(self, store):
        done = []
        await store.add("run-a")
        await store.add("run-b")

        task_a = asyncio.create_task(self._fake_pipeline(store, "run-a", done))
        task_b = asyncio.create_task(self._fake_pipeline(store, "run-b", done))

        await asyncio.sleep(0.01)
        await store.request_cancel("run-a")

        await asyncio.wait_for(task_a, timeout=2.0)
        # task_b should still be running; cancel it to clean up
        await store.request_cancel("run-b")
        await asyncio.wait_for(task_b, timeout=2.0)

        statuses = {rid: status for rid, status in done}
        assert statuses["run-a"] == "cancelled"
        assert statuses["run-b"] == "cancelled"
