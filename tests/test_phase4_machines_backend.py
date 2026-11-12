"""Phase 4 state machines B5 (admission), B8 (WS replay), B9 (Neuro tier).

docs/plans/implicit-state-machines-2026-11-11.md, Phase 4.
"""

from __future__ import annotations

import gzip
import json
import os
import time

import pytest

from reasoner.api.run_admission import AdmissionResource, _Held
from reasoner.infrastructure.websocket.manager import (
    ReplayState,
    WebSocketManager,
    WebSocketMessage,
)
from reasoner.neuro.sessions import SessionManager

pytestmark = [pytest.mark.unit]


async def test_failing_release_does_not_skip_later_releases():
    held, released = _Held(), []

    async def boom():
        raise RuntimeError("ledger down")

    async def ok():
        released.append("claim")

    held.hold(AdmissionResource.RUN_CLAIM, ok)  # acquired first, released last
    held.hold(AdmissionResource.QUOTA_SLOT, boom)
    await held.release_all()
    assert released == ["claim"]


async def test_events_after_complete_are_dropped_and_counted():
    mgr = WebSocketManager()
    await mgr._deliver_local("p1", WebSocketMessage("progress", {}, "p1"))
    await mgr._deliver_local("p1", WebSocketMessage("complete", {}, "p1"))
    await mgr._deliver_local("p1", WebSocketMessage("progress", {}, "p1"))
    assert [m.type for m in mgr._replay_buffers["p1"]] == ["progress", "complete"]
    assert mgr.dropped_after_complete == 1
    assert mgr._replay_state["p1"] is ReplayState.COMPLETE


def _old_hot_session(mgr: SessionManager, sid: str) -> None:
    f = mgr.hot_dir / f"{sid}.jsonl"
    f.write_text(json.dumps({"_type": "exchange", "prompt": "p", "response": "r"}) + "\n")
    old = time.time() - 10 * 86400
    os.utime(f, (old, old))


async def test_failed_archive_leaves_session_in_hot_only(tmp_path, monkeypatch):
    mgr = SessionManager(tmp_path)
    _old_hot_session(mgr, "s1")
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 2:  # gz published, summary not
            raise OSError("disk full")
        return real(src, dst)

    monkeypatch.setattr("reasoner.neuro.sessions.os.replace", flaky)
    assert await mgr.archive_hot_sessions() == []
    assert (mgr.hot_dir / "s1.jsonl").exists()
    assert list(mgr.warm_dir.iterdir()) == []


async def test_archive_moves_session_to_warm(tmp_path):
    mgr = SessionManager(tmp_path)
    _old_hot_session(mgr, "s1")
    assert len(await mgr.archive_hot_sessions()) == 1
    assert not (mgr.hot_dir / "s1.jsonl").exists()
    assert (mgr.warm_dir / "s1.json").exists()
    with gzip.open(mgr.warm_dir / "s1.jsonl.gz", "rt") as fh:
        assert fh.read()
    assert mgr.stats["warm_sessions"] == 1


# ── M4: a metered release carries the claim time ─────────────────────────────

async def test_metered_quota_release_passes_the_claim_time():
    """M4: without claimed_at the period guard in release_slot never fires."""
    from reasoner.application.services.run_metering import RunContext, _release_quota_slot

    seen: list[dict] = []

    class _Sink:
        async def release_quota_slot(self, **kwargs) -> None:
            seen.append(kwargs)

    ctx = RunContext(preset="p", reference_id="r", user_id="u", quota_slot=True)
    await _release_quota_slot(_Sink(), ctx)
    assert seen == [{"user_id": "u", "claimed_at": ctx.created_at}]
