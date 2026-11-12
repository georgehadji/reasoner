"""Audit 9: API/data findings (problem rewrite, WS bridge, cache cap, uploads)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


def test_run_request_keeps_comparisons_and_unicode():
    from reasoner.api.schemas import RunRequest

    text = "Prove x < 5 and y > 3 when x\u00b2 = 4"
    assert RunRequest(problem=text).problem == text


def test_run_request_still_strips_script_blocks():
    from reasoner.api.schemas import RunRequest

    assert "alert" not in RunRequest(problem="hi <script>alert(1)</script> there").problem


@pytest.mark.asyncio
async def test_bridge_delivers_remote_once_and_publishes_local(monkeypatch):
    from reasoner.infrastructure.websocket.manager import WebSocketManager, WebSocketMessage

    a, b = WebSocketManager(), WebSocketManager()
    a._bridge_enabled = True
    sent: list[str] = []

    async def _send(self, cid, msg):
        sent.append(cid)

    monkeypatch.setattr(WebSocketManager, "send_to_connection", _send)
    b.subscriptions["run-1"] = {"conn-b"}
    published: list[dict] = []

    async def _publish(self, pid, msg):
        published.append({"origin": self._worker_id, "pid": pid})

    monkeypatch.setattr(WebSocketManager, "_publish", _publish)
    msg = WebSocketMessage(type="event", data={}, pipeline_id="run-1")
    await a.broadcast_to_pipeline("run-1", msg)  # worker A runs the pipeline
    assert published == [{"origin": a._worker_id, "pid": "run-1"}]
    await b.broadcast_to_pipeline("run-1", msg, _from_bridge=True)  # B gets it via pub/sub
    assert sent == ["conn-b"]
    assert len(published) == 1  # bridged delivery is not re-published


def test_ws_and_http_origins_share_one_helper(monkeypatch):
    from reasoner.core.settings import settings
    from reasoner.infrastructure.websocket.ws_security import is_origin_allowed

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "APP_URL", "https://app.example")
    monkeypatch.setattr(settings, "CORS_ORIGINS", "https://other.example")
    assert settings.effective_allowed_origins == ["https://app.example"]
    assert is_origin_allowed("https://app.example")
    assert not is_origin_allowed("https://other.example")


@pytest.mark.asyncio
async def test_truncated_stream_is_not_cached(monkeypatch):
    from reasoner.api import streaming
    from reasoner.api.schemas import RunRequest

    async def _fake_run_stream(*a, **k):
        for i in range(250):
            yield "data: " + json.dumps({"type": "phase_start", "i": i}) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    save = AsyncMock()
    monkeypatch.setattr(streaming, "run_stream", _fake_run_stream)
    monkeypatch.setattr(streaming, "_load_cache", AsyncMock(return_value=None))
    monkeypatch.setattr(streaming, "_save_cache", save)
    monkeypatch.setattr(streaming, "SSE_FLUSH_INTERVAL", 0)
    req = RunRequest(problem="a perfectly normal problem")
    async for _ in streaming.run_stream_cached(req, preset_service=object(), pipeline_service=object()):
        pass
    save.assert_not_awaited()


def test_reserve_upload_id_never_reuses_an_existing_id(tmp_path, monkeypatch):
    from reasoner.infrastructure import uploader

    monkeypatch.setattr(uploader, "UPLOAD_DIR", tmp_path)
    ids = iter(["a" * 12 + "-x", "a" * 12 + "-x", "b" * 12 + "-y"])  # str(uuid)[:12] -> 12 chars
    monkeypatch.setattr(uploader.uuid, "uuid4", lambda: next(ids))
    (tmp_path / f"{'a' * 12}.meta.json").write_text('{"user_id": "victim"}')
    file_id, meta = uploader._reserve_upload_id()
    assert file_id == "b" * 12
    assert json.loads((tmp_path / f"{'a' * 12}.meta.json").read_text()) == {"user_id": "victim"}


@pytest.mark.asyncio
async def test_upload_reserves_quota_from_content_length_before_reading(monkeypatch):
    from fastapi import HTTPException

    from reasoner.api.routes import uploads

    usage = AsyncMock()
    usage.reserve = AsyncMock(return_value=False)
    usage.get = AsyncMock(return_value=uploads.UPLOAD_USER_QUOTA_BYTES)  # already at quota
    monkeypatch.setattr(uploads, "get_upload_usage_repo", lambda: usage)

    class _Req:
        headers = {"content-length": "1000"}

        async def form(self):
            raise AssertionError("body must not be parsed before the quota check")

    class _User:
        id = "u1"

    with pytest.raises(HTTPException) as exc:
        await uploads.upload_file(_Req(), force_ocr=False, user=_User(), rate_limit_checked=None, csrf_checked=None)
    assert exc.value.status_code == 413
    usage.reserve.assert_awaited()


@pytest.mark.asyncio
async def test_save_uploaded_file_hashes_off_the_loop(tmp_path, monkeypatch):
    from reasoner.infrastructure import uploader

    seen: list[str] = []
    real = asyncio.to_thread

    async def _spy(fn, *a, **k):
        seen.append(getattr(fn, "__name__", "lambda"))
        return await real(fn, *a, **k)

    monkeypatch.setattr(uploader.asyncio, "to_thread", _spy)
    monkeypatch.setattr(uploader, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(uploader.settings, "UPLOAD_REQUIRE_MIME_VALIDATION", False)
    monkeypatch.setattr(uploader, "_MAGIC_AVAILABLE", False)
    await uploader.save_uploaded_file(b"hello", "a.txt", user_id="u1")
    assert "<lambda>" in seen and "_reserve_upload_id" in seen
