"""PR 8 of docs/plans/audit-remediation-2-2026-10-20.md: PER-8 to PER-11, DAT-8.

Upload index and quota (PER-8), orphan upload files (PER-9), the Neuro L2
index (PER-10), tenant directory names (PER-11) and chunking (DAT-8).
"""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from reasoner.core.settings import settings
from reasoner.infrastructure import uploader
from reasoner.infrastructure.persistence.upload_usage_repo import SqliteUploadUsageRepository
from reasoner.neuro.cache import L1Cache, L2Index
from reasoner.neuro.config import CacheConfig, NeuroConfig, get_agent_data_dir
from reasoner.utils.atomic_file import read_json_or_quarantine

pytestmark = pytest.mark.unit


@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    import reasoner.documents.vector_store as vector_store_module

    monkeypatch.setattr(uploader, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(vector_store_module, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(uploader, "_MAGIC_AVAILABLE", False)
    monkeypatch.setattr(settings, "UPLOAD_REQUIRE_MIME_VALIDATION", False)
    monkeypatch.setattr(settings, "DOCUMENT_SEMANTIC_RETRIEVAL_ENABLED", False)
    return tmp_path


def _upload_files(upload_dir) -> set[str]:
    # Dot files are the hash index and its lock, not upload content.
    return {p.name for p in upload_dir.iterdir() if not p.name.startswith(".")}


# ── PER-8: hash index and quota ──────────────────────────────────────


async def test_concurrent_uploads_by_one_user_keep_both_index_entries(upload_dir):
    a, b = await asyncio.gather(
        uploader.save_uploaded_file(b"first file", "a.txt", user_id="u"),
        uploader.save_uploaded_file(b"second file", "b.txt", user_id="u"),
    )
    index = json.loads((upload_dir / ".upload_hash_index.json").read_text(encoding="utf-8"))
    assert set(index["u"].values()) == {a["file_id"], b["file_id"]}


async def test_parallel_reservations_never_exceed_the_cap(tmp_path):
    repo = SqliteUploadUsageRepository(tmp_path / "usage.db")
    granted = await asyncio.gather(*[repo.reserve("u", 10, 55) for _ in range(20)])
    assert sum(granted) == 5
    assert await repo.get("u") == 50


async def test_adjust_never_goes_below_zero(tmp_path):
    repo = SqliteUploadUsageRepository(tmp_path / "usage.db")
    assert await repo.reserve("u", 10, 100)
    await repo.adjust("u", -25)
    assert await repo.get("u") == 0


def _upload_app(monkeypatch, repo):
    from reasoner.api import dependencies
    from reasoner.api.auth_deps import require_csrf
    from reasoner.api.routes import uploads
    from reasoner.domain.saas import User

    user = User(id=uuid4(), email="a@b.c")
    app = FastAPI()
    app.include_router(uploads.router)
    app.dependency_overrides[dependencies.get_current_user] = lambda: user
    app.dependency_overrides[dependencies.check_rate_limit] = lambda: True
    app.dependency_overrides[require_csrf] = lambda: True
    monkeypatch.setattr(uploads, "get_upload_usage_repo", lambda: repo)
    return app, user


async def test_usage_survives_losing_the_hash_index(upload_dir, tmp_path, monkeypatch):
    """A redeploy used to reset the quota, because usage was summed from the index."""
    from reasoner.api.routes import uploads

    repo = SqliteUploadUsageRepository(tmp_path / "usage.db")
    app, user = _upload_app(monkeypatch, repo)
    monkeypatch.setattr(uploads, "UPLOAD_USER_QUOTA_BYTES", 2000)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        first = await client.post("/api/upload", files={"file": ("a.txt", b"x" * 150)})
        assert first.status_code == 200
        used = await repo.get(str(user.id))
        assert used >= 150  # ciphertext and the text sidecar are counted too
        (upload_dir / ".upload_hash_index.json").unlink()
        second = await client.post(
            "/api/upload", files={"file": ("b.txt", b"y" * (2000 - used + 1))}
        )
    assert second.status_code == 413


async def test_failed_upload_releases_its_reservation(upload_dir, tmp_path, monkeypatch):
    from reasoner.api.routes import uploads

    repo = SqliteUploadUsageRepository(tmp_path / "usage.db")
    app, user = _upload_app(monkeypatch, repo)

    async def _fail(*a, **k):
        return {"success": False, "error": "nope"}

    monkeypatch.setattr(uploads, "save_uploaded_file", _fail)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        await client.post("/api/upload", files={"file": ("a.txt", b"x" * 50)})
    assert await repo.get(str(user.id)) == 0


async def test_delete_releases_the_stored_bytes(upload_dir, tmp_path, monkeypatch):
    repo = SqliteUploadUsageRepository(tmp_path / "usage.db")
    app, user = _upload_app(monkeypatch, repo)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        up = await client.post("/api/upload", files={"file": ("a.txt", b"x" * 50)})
        file_id = up.json()["files"][0]["file_id"]
        assert await repo.get(str(user.id)) > 0
        deleted = await client.delete(f"/api/upload/{file_id}")
    assert deleted.status_code == 200
    assert await repo.get(str(user.id)) == 0


# ── PER-9: no orphan upload files ────────────────────────────────────


async def test_failure_after_the_content_write_leaves_no_files(upload_dir, monkeypatch):
    async def _boom(*a, **k):
        raise RuntimeError("extraction exploded")

    monkeypatch.setattr(uploader, "extract_text", _boom)
    result = await uploader.save_uploaded_file(b"data", "a.txt", user_id="u")
    assert result["success"] is False
    assert _upload_files(upload_dir) == set()


async def test_stored_bytes_counts_the_text_sidecar(upload_dir):
    result = await uploader.save_uploaded_file(b"some text", "a.txt", user_id="u")
    fid = result["file_id"]
    on_disk = sum(
        p.stat().st_size
        for p in upload_dir.iterdir()
        if p.name.startswith(fid) and not p.name.endswith(".meta.json")
    )
    assert (upload_dir / f"{fid}.text.json").exists()
    assert result["stored_bytes"] == uploader.file_stored_bytes(fid) == on_disk


async def test_delete_cleans_orphans_without_a_content_file(upload_dir):
    fid = "abcdef123456"
    (upload_dir / f"{fid}.text.json").write_bytes(b"x")
    (upload_dir / f"{fid}.vectors.json").write_text("{}", encoding="utf-8")
    assert uploader.delete_file(fid) is True
    assert _upload_files(upload_dir) == set()


async def test_delete_during_indexing_leaves_no_vectors(upload_dir):
    from reasoner.documents.vector_store import DocumentVectorStore

    result = await uploader.save_uploaded_file(b"text to index", "a.txt", user_id="u")
    fid = result["file_id"]

    class _DeletingEmbedder:
        async def embed(self, text):
            uploader.delete_file(fid, user_id="u")
            return [1.0, 0.0]

    await DocumentVectorStore(embedder=_DeletingEmbedder()).index_file(fid, "text to index")
    assert not (upload_dir / f"{fid}.vectors.json").exists()


async def test_listing_hides_an_upload_still_being_written(upload_dir):
    fid = "abcdef654321"
    (upload_dir / f"{fid}.txt").write_bytes(b"x")
    (upload_dir / f"{fid}.meta.json").write_text(
        json.dumps({"user_id": "u", "filename": "a.txt", "status": "writing"}), encoding="utf-8"
    )
    assert uploader.list_uploads(user_id="u") == []


# ── PER-10: Neuro L2 index ───────────────────────────────────────────


async def test_same_content_learned_twice_is_one_l2_entry(tmp_path):
    index = L2Index(tmp_path, CacheConfig())
    await index.add("x", "s", [1.0, 0.0], {"schema_version": 1})
    await index.add("x", "s", [1.0, 0.0], {"schema_version": 1})
    assert index.size == 1
    assert len(json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))) == 1


async def test_truncated_l2_index_is_quarantined_not_wiped(tmp_path):
    (tmp_path / "index.json").write_text('[{"id": "a", "content": "x"', encoding="utf-8")
    index = L2Index(tmp_path, CacheConfig())
    assert index.size == 0
    await index.add("y", "s", [1.0, 0.0])
    [corrupt] = tmp_path.glob("index.json.corrupt-*")
    assert corrupt.read_text(encoding="utf-8") == '[{"id": "a", "content": "x"'


async def test_two_l2_writers_keep_each_others_entries(tmp_path):
    a, b = L2Index(tmp_path, CacheConfig()), L2Index(tmp_path, CacheConfig())
    await a.add("one", "s", [1.0, 0.0])
    await b.add("two", "s", [0.0, 1.0])
    contents = {e["content"] for e in L2Index(tmp_path, CacheConfig()).entries}
    assert contents == {"one", "two"}


async def test_l1_hits_carry_provenance(tmp_path):
    l1 = L1Cache(tmp_path, CacheConfig())
    await l1.add("x", "s", [1.0, 0.0], metadata={"schema_version": 1})
    [hit] = L1Cache(tmp_path, CacheConfig()).search([1.0, 0.0])
    assert hit.metadata == {"schema_version": 1}


async def test_unattributed_hits_do_not_use_up_recall_slots(monkeypatch):
    """Five unattributed L1 hits used to fill all five slots, so L2 never showed."""
    from reasoner.application.orchestrator import PipelineOrchestrator
    from reasoner.core.ports import memory_port

    class _Port:
        async def recall(self, prompt, agent_id=None, max_results=5, owner=None):
            unattributed = [{"content": f"l1-{i}", "source": "l1"} for i in range(5)]
            attributed = [
                {"content": f"l2-{i}", "source": "l2", "schema_version": 1} for i in range(20)
            ]
            return (unattributed + attributed)[:max_results]

    monkeypatch.setattr(memory_port, "get_memory_port", lambda: _Port())
    monkeypatch.setattr(settings, "NEURO_CONTEXT_MAX_CHUNKS", 5)
    chunks = await PipelineOrchestrator._recall_neuro_context(object(), "q", owner="o")
    assert [c["content"] for c in chunks] == [f"l2-{i}" for i in range(5)]


def test_read_json_or_quarantine_missing_file_is_default(tmp_path):
    assert read_json_or_quarantine(tmp_path / "nope.json", []) == ([], False)


# ── PER-11: tenant directory names ───────────────────────────────────


def test_ids_that_sanitize_alike_get_different_directories(tmp_path):
    cfg = NeuroConfig()
    cfg.data_dir = str(tmp_path)
    assert get_agent_data_dir(cfg, "u-o-a.b") != get_agent_data_dir(cfg, "u-o-ab")


def test_legacy_directory_is_renamed_on_first_access(tmp_path):
    cfg = NeuroConfig()
    cfg.data_dir = str(tmp_path)
    legacy = tmp_path / "agents" / "u-o-conv1"
    (legacy / "cache").mkdir(parents=True)
    new = get_agent_data_dir(cfg, "u-o-conv1")
    assert new != legacy
    assert new.name.startswith("u-o-conv1-")
    assert (new / "cache").is_dir()
    assert not legacy.exists()


# ── DAT-8: chunking ──────────────────────────────────────────────────

_BASE = 0x4E00  # one distinct character per position, so a chunk's offset is readable


@hyp_settings(max_examples=300, deadline=None)
@given(
    n=st.integers(0, 3000),
    size=st.integers(1, 400),
    overlap=st.integers(0, 400),
    budget=st.integers(1, 4000),
)
def test_chunks_cover_the_text_and_report_truncation(n, size, overlap, budget):
    from reasoner.documents.vector_store import _chunk_text

    text = "".join(chr(_BASE + i) for i in range(n))
    result = _chunk_text(text, size, overlap, max_chars=budget)
    if not text:
        assert result.chunks == [] and result.truncated is False
        return
    spans = [(ord(c[0]) - _BASE, ord(c[-1]) - _BASE + 1) for c in result.chunks]
    assert spans[0][0] == 0
    for (_s0, e0), (s1, e1) in zip(spans, spans[1:], strict=False):
        assert s1 <= e0, "a gap between chunks"
        assert e1 > e0, "a chunk that adds nothing new (redundant tail)"
    covered = spans[-1][1]
    assert result.truncated == (covered < n)
    if result.truncated:
        assert covered >= min(budget, size)


def test_budget_truncation_is_flagged():
    from reasoner.documents.vector_store import _chunk_text

    result = _chunk_text("x" * 1000, 100, 0, max_chars=300)
    assert result.truncated is True
    assert "".join(result.chunks) == "x" * 300
