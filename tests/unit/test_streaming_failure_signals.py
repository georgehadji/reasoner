"""SSE streaming failures that used to be invisible.

P5, docs/plans/root-cause-remediation-2026-09-07.md.

``run_stream_cached`` wrapped the parse, the collect and the cache write in one
``except Exception: pass``. Every ``data:`` line it parses came from our own
serializers, so a parse failure is our bug -- and it took the ``done``
detection with it, which is the only thing that writes the cache at all. A
serializer change could therefore switch response caching off permanently and
look exactly like a cold cache.
"""

from __future__ import annotations

import logging

import pytest

from reasoner.api import streaming
from reasoner.api.schemas import RunRequest


def _req() -> RunRequest:
    return RunRequest(problem="anything", no_cache=False)


async def _drain(gen) -> list[str]:
    return [chunk async for chunk in gen]


@pytest.fixture
def no_cache_read(monkeypatch):
    async def _empty(_key):
        return None

    monkeypatch.setattr(streaming, "_load_cache", _empty)
    monkeypatch.setattr(streaming, "_cache_key", lambda req, user_id=None: "k")


@pytest.mark.asyncio
async def test_an_unparseable_event_is_reported(monkeypatch, caplog, no_cache_read):
    async def _bad_stream(*args, **kwargs):
        yield "data: {not json at all}\n\n"

    monkeypatch.setattr(streaming, "run_stream", _bad_stream)

    with caplog.at_level(logging.WARNING):
        chunks = await _drain(streaming.run_stream_cached(_req()))

    assert chunks, "the client must still receive the stream"
    assert any("streaming.cache_collect" in r.message for r in caplog.records), (
        f"a serializer bug silently disabled caching: "
        f"{[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_a_bad_event_does_not_stop_the_ones_after_it(
    monkeypatch, caplog, no_cache_read
):
    """Splitting one handler into three must not change the sequencing.

    The old code recovered per chunk too, so this passes either way by
    design -- it is here to catch the `continue` swallowing a later `done`.
    """
    saved: list[list[dict]] = []

    async def _mixed_stream(*args, **kwargs):
        yield "data: {not json at all}\n\n"
        yield 'data: {"type": "done"}\n\n'

    async def _capture(_key, events):
        saved.append(events)

    monkeypatch.setattr(streaming, "run_stream", _mixed_stream)
    monkeypatch.setattr(streaming, "_save_cache", _capture)

    with caplog.at_level(logging.WARNING):
        await _drain(streaming.run_stream_cached(_req()))

    assert saved, "the run was never cached despite reaching a done event"
    assert saved[0] == [{"type": "done"}]


@pytest.mark.asyncio
async def test_a_failed_cache_write_is_reported(monkeypatch, caplog, no_cache_read):
    async def _stream(*args, **kwargs):
        yield 'data: {"type": "done"}\n\n'

    async def _boom(_key, _events):
        raise OSError("cache volume is read-only")

    monkeypatch.setattr(streaming, "run_stream", _stream)
    monkeypatch.setattr(streaming, "_save_cache", _boom)

    with caplog.at_level(logging.WARNING):
        await _drain(streaming.run_stream_cached(_req()))

    assert any("streaming.cache_save" in r.message for r in caplog.records), (
        f"the cache write failed silently: {[r.message for r in caplog.records]}"
    )


@pytest.mark.asyncio
async def test_a_clean_run_reports_nothing(monkeypatch, caplog, no_cache_read):
    async def _stream(*args, **kwargs):
        yield 'data: {"type": "done"}\n\n'

    async def _ok(_key, _events):
        return None

    monkeypatch.setattr(streaming, "run_stream", _stream)
    monkeypatch.setattr(streaming, "_save_cache", _ok)

    with caplog.at_level(logging.WARNING):
        await _drain(streaming.run_stream_cached(_req()))

    assert not [r for r in caplog.records if "streaming." in r.message], (
        f"a clean run reported a degradation: {[r.message for r in caplog.records]}"
    )
