"""Per-run in-memory state is bounded (OPS-4).

WS replay buffers were created for every broadcast run and dropped only when
its last subscriber left, so every SSE-only run leaked one. Langfuse phase
spans were never removed, and flush() blocked the loop. Every run built a
TaggedMemory, which re-read every history JSONL file just to append two lines.
See docs/plans/audit-remediation-2026-10-20.md, OPS-4.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from reasoner.core.constants import WS_MAX_REPLAY_BUFFERS, WS_REPLAY_TTL_SECONDS
from reasoner.infrastructure.websocket import manager as ws_mod
from reasoner.infrastructure.websocket.manager import WebSocketManager, WebSocketMessage


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(ws_mod.time, "monotonic", lambda: now[0])
    return now


def _msg(pid: str) -> WebSocketMessage:
    return WebSocketMessage(type="event", data={}, pipeline_id=pid)


@pytest.mark.asyncio
async def test_unsubscribed_replay_buffers_expire(clock):
    mgr = WebSocketManager()
    for i in range(1000):  # 1000 SSE-only runs: nobody ever subscribes
        await mgr.broadcast_to_pipeline(f"run-{i}", _msg(f"run-{i}"))
    clock[0] += WS_REPLAY_TTL_SECONDS + 1
    await mgr.broadcast_to_pipeline("run-new", _msg("run-new"))

    assert list(mgr._replay_buffers) == ["run-new"]
    assert set(mgr._replay_touched) == {"run-new"}


@pytest.mark.asyncio
async def test_replay_buffers_are_capped_and_late_joiners_still_replay(clock, monkeypatch):
    mgr = WebSocketManager()
    for i in range(WS_MAX_REPLAY_BUFFERS + 5):
        await mgr.broadcast_to_pipeline(f"run-{i}", _msg(f"run-{i}"))
    assert len(mgr._replay_buffers) == WS_MAX_REPLAY_BUFFERS
    assert "run-0" not in mgr._replay_buffers

    sent = []

    async def _send(connection_id, message):
        sent.append(message.pipeline_id)

    monkeypatch.setattr(mgr, "send_to_connection", _send)
    last = f"run-{WS_MAX_REPLAY_BUFFERS + 4}"
    await mgr.subscribe("conn-1", last)
    assert sent == [last], "a client joining within the TTL still gets the buffered events"


@pytest.mark.asyncio
async def test_a_finished_run_leaves_no_spans_and_flushes_off_the_loop(monkeypatch):
    from reasoner.infrastructure.observability import langfuse_subscriber as lf

    flushed_on: list[str] = []
    client = SimpleNamespace(flush=lambda: flushed_on.append(threading.current_thread().name))
    monkeypatch.setattr(lf, "_is_langfuse_enabled", True)
    monkeypatch.setattr(lf, "_langfuse_client", client)

    sub = lf.LangfuseSubscriber.__new__(lf.LangfuseSubscriber)
    trace = SimpleNamespace(update=lambda **kw: None)
    sub._active_traces = {"run-1": trace, "run-2": trace}
    sub._active_spans = {"run-1-Phase A": object(), "run-1-Phase B": object(), "run-2-Phase A": object()}

    await sub.handle_pipeline_completed(SimpleNamespace(
        aggregate_id="run-1", solution="", total_tokens=0,
        total_duration_seconds=0.0, phases_completed=2,
    ))

    assert list(sub._active_traces) == ["run-2"]
    assert list(sub._active_spans) == ["run-2-Phase A"]
    assert flushed_on and flushed_on[0] != threading.main_thread().name


def test_appending_history_does_not_read_it(tmp_path, monkeypatch):
    from reasoner.core.memory import TaggedMemory

    (tmp_path / "method_x.jsonl").write_text('{"old": 1}\n' * 100)
    monkeypatch.setattr(TaggedMemory, "_load", lambda self: pytest.fail("appending re-read history"))
    TaggedMemory(tmp_path).add("method_x", {"new": 1})
    assert (tmp_path / "method_x.jsonl").read_text().count("\n") == 101


def test_reads_still_see_appended_entries_and_large_files_rotate(tmp_path, monkeypatch):
    from reasoner.core.memory import TaggedMemory

    monkeypatch.setattr(TaggedMemory, "MAX_FILE_BYTES", 50)
    mem = TaggedMemory(tmp_path)
    for i in range(5):
        mem.add("preset_y", {"i": i, "pad": "x" * 20})

    assert (tmp_path / "preset_y.jsonl.1").exists()
    reader = TaggedMemory(tmp_path)
    assert 0 < reader.count("preset_y") < 5
    assert reader.get_by_tag("preset_y")[-1]["i"] == 4
