"""Request bodies are capped and document parsing can be killed (SEC-5).

No body cap existed (uvicorn, Caddy or middleware), and the anonymous
/api/provenance/inspect took an unbounded `image`. DOCX/PDF parsing was sync on
the loop, so the extraction timeout could not interrupt it, and a zip bomb
inflated in full. See docs/plans/audit-remediation-2026-10-20.md, SEC-5.
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import time
import zipfile

import httpx
import pytest
from fastapi import FastAPI, Request

from reasoner.api.middleware import BodySizeLimitMiddleware


def _app(ran: list, *, swallow: bool = False) -> FastAPI:
    app = FastAPI()

    @app.post("/api/echo")
    @app.post("/api/upload")
    async def echo(request: Request):
        try:
            body = await request.body()
        except Exception:
            if not swallow:
                raise
            return {"swallowed": True}  # what a catch-all route does
        ran.append(len(body))
        return {"n": len(body)}

    app.add_middleware(BodySizeLimitMiddleware, default_limit=100, per_path={"/api/upload": 1000})
    return app


async def _post(app, path, content, headers=None):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.post(path, content=content, headers=headers)


@pytest.mark.asyncio
async def test_declared_oversized_body_is_refused_before_the_handler():
    ran: list = []
    r = await _post(_app(ran), "/api/echo", b"x" * 101)
    assert r.status_code == 413 and ran == []


@pytest.mark.asyncio
@pytest.mark.parametrize("swallow", [False, True])
async def test_chunked_oversized_body_is_refused(swallow):
    async def chunks():
        for _ in range(5):
            yield b"x" * 40  # no Content-Length: counted as it arrives

    ran: list = []
    r = await _post(_app(ran, swallow=swallow), "/api/echo", chunks())
    assert r.status_code == 413, "a route that catches every error must not answer instead"
    assert ran == []


@pytest.mark.asyncio
async def test_limits_are_per_path_and_bodies_under_them_pass():
    ran: list = []
    app = _app(ran)
    assert (await _post(app, "/api/echo", b"x" * 100)).status_code == 200
    assert (await _post(app, "/api/upload", b"x" * 500)).status_code == 200
    assert (await _post(app, "/api/upload", b"x" * 1001)).status_code == 413
    assert ran == [100, 500]


def test_provenance_image_field_is_capped():
    from pydantic import ValidationError

    from reasoner.api.routes.provenance import ProvenanceContentRequest
    from reasoner.core.constants_limits import MAX_DATA_URL_CHARS

    with pytest.raises(ValidationError):
        ProvenanceContentRequest(image="data:image/png;base64," + "A" * MAX_DATA_URL_CHARS)


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_a_zip_bomb_docx_is_refused_before_parsing():
    from reasoner.infrastructure.documents.parse_worker import parse_docx, zip_bomb_reason

    bomb = _zip({"word/document.xml": b"\0" * (20 * 1024 * 1024)})
    assert "ratio" in zip_bomb_reason(bomb)
    assert zip_bomb_reason(_zip({"a.txt": b"plain text, normal ratio"})) is None
    assert zip_bomb_reason(b"not a zip") is None

    result = parse_docx(bomb)
    assert result.startswith("[DOCX extraction")  # refused, or python-docx missing
    assert "refused" in result or "not available" in result


@pytest.mark.asyncio
async def test_a_parser_past_the_timeout_is_killed(tmp_path, monkeypatch):
    import psutil

    from reasoner.infrastructure import uploader

    pid_file = tmp_path / "pid"
    hang = tmp_path / "hang.py"
    hang.write_text(
        f"import os, time\nopen({str(pid_file)!r}, 'w').write(str(os.getpid()))\ntime.sleep(60)\n"
    )
    monkeypatch.setattr(uploader, "_PARSE_WORKER", hang)

    start = time.monotonic()
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(uploader._parse_in_child("pdf", b"x"), timeout=3)
    assert time.monotonic() - start < 10

    pid = int(pid_file.read_text())
    assert not psutil.pid_exists(pid) or psutil.Process(pid).status() == psutil.STATUS_ZOMBIE


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS is POSIX-only")
async def test_the_parser_child_runs_under_a_memory_cap(monkeypatch):
    from reasoner.infrastructure import uploader

    monkeypatch.setattr(uploader, "DOCUMENT_PARSE_MEMORY_LIMIT_BYTES", 32 * 1024 * 1024)
    result = await uploader._parse_in_child("docx", _zip({"word/document.xml": b"<w/>"}))
    assert result.startswith("[DOCX extraction")


@pytest.mark.asyncio
async def test_get_file_text_reads_the_cache_instead_of_reparsing(monkeypatch):
    from reasoner.infrastructure import uploader

    file_id = "0a1b2c3d-cac"
    (uploader.UPLOAD_DIR / f"{file_id}.meta.json").write_text(json.dumps({"user_id": "u1", "encrypted": True}))
    uploader._text_cache_path(file_id).write_bytes(uploader._encrypt_bytes(b"cached text"))

    async def _no_parse(*a, **k):
        raise AssertionError("re-parsed a file whose text is cached")

    monkeypatch.setattr(uploader, "extract_text", _no_parse)
    try:
        assert await uploader.get_file_text(file_id, user_id="u1") == "cached text"
        assert await uploader.get_file_text(file_id, user_id="other") is None
    finally:
        uploader.delete_file(file_id)
        assert not uploader._text_cache_path(file_id).exists()
