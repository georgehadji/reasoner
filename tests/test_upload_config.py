"""Uploads work as configured (OPS-7).

The runtime image had no libmagic1, so with UPLOAD_REQUIRE_MIME_VALIDATION on
(the default) every upload failed closed. libmagic reports Markdown as
text/plain, which MIME_TYPE_MAP rejected for .md. The response leaked the
server path, and there was no per-user byte quota.
See docs/plans/audit-remediation-2026-10-20.md, OPS-7.
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from reasoner.infrastructure import uploader


@pytest.fixture
def libmagic_says_text_plain(monkeypatch):
    class _Magic:
        @staticmethod
        def from_buffer(content, mime=True):
            return "text/plain"

    monkeypatch.setattr(uploader, "_MAGIC_AVAILABLE", True)
    monkeypatch.setattr(uploader, "magic", _Magic, raising=False)


@pytest.mark.asyncio
async def test_a_markdown_upload_is_accepted_and_leaks_no_path(libmagic_says_text_plain):
    result = await uploader.save_uploaded_file(b"# Notes\n\nhello", "notes.md", user_id=None)
    try:
        assert result["success"], result
        assert "path" not in result
        assert result["text"].startswith("# Notes")
    finally:
        uploader.delete_file(result.get("file_id", ""))


@pytest.mark.asyncio
async def test_going_over_the_quota_is_413(monkeypatch, tmp_path):
    from reasoner.api import dependencies
    from reasoner.api.auth_deps import require_csrf
    from reasoner.api.routes import uploads
    from reasoner.core.constants_limits import UPLOAD_USER_QUOTA_BYTES
    from reasoner.domain.saas import User

    saved: list = []
    app = FastAPI()
    app.include_router(uploads.router)
    app.dependency_overrides[dependencies.get_current_user] = lambda: User(id=uuid4(), email="a@b.c")
    app.dependency_overrides[dependencies.check_rate_limit] = lambda: True
    app.dependency_overrides[require_csrf] = lambda: True
    from reasoner.infrastructure.persistence.upload_usage_repo import SqliteUploadUsageRepository

    repo = SqliteUploadUsageRepository(tmp_path / "usage.db")
    monkeypatch.setattr(uploads, "get_upload_usage_repo", lambda: repo)

    async def _save(*a, **k):
        saved.append(a)
        return {"success": True}

    user = app.dependency_overrides[dependencies.get_current_user]()
    app.dependency_overrides[dependencies.get_current_user] = lambda: user
    await repo.adjust(str(user.id), UPLOAD_USER_QUOTA_BYTES - 10)

    monkeypatch.setattr(uploads, "save_uploaded_file", _save)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        small = await client.post("/api/upload", files={"file": ("a.txt", b"12345")})
        big = await client.post("/api/upload", files={"file": ("b.txt", b"x" * 11)})

    assert small.status_code == 200
    assert big.status_code == 413
    assert len(saved) == 1, "the over-quota file must not be saved"


def test_the_runtime_image_installs_libmagic():
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()
    runtime = dockerfile.split("AS runtime", 1)[1]
    assert re.search(r"apt-get install[^\n]*\\\n[^\n]*\blibmagic1\b", runtime), (
        "python-magic needs libmagic1 in the runtime stage, or uploads fail closed"
    )
