"""security-remediation-plan.md Phase 4: cross-tenant dedup isolation,
fail-closed MIME validation, bounded indexing queue, and encryption at
rest for uploads and vector sidecars.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from reasoner.core.settings import settings
from reasoner.infrastructure import uploader
from reasoner.infrastructure.uploader import save_uploaded_file

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _isolated_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(uploader, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(uploader, "_HASH_INDEX_PATH", tmp_path / ".hash_index.json")
    monkeypatch.setattr(uploader, "_MAGIC_AVAILABLE", False)
    monkeypatch.setattr(settings, "UPLOAD_REQUIRE_MIME_VALIDATION", False)
    monkeypatch.setattr(settings, "CSRF_SECRET", "test-secret-do-not-reuse")

    # DocumentVectorStore imported UPLOAD_DIR as its own name binding
    # (`from reasoner.uploader import UPLOAD_DIR`) -- patching
    # infrastructure.uploader.UPLOAD_DIR above doesn't reach it.
    import reasoner.documents.vector_store as vector_store_module

    monkeypatch.setattr(vector_store_module, "UPLOAD_DIR", tmp_path)
    return tmp_path


# ── 1. Cross-tenant dedup isolation ─────────────────────────────────


async def test_same_content_different_tenants_gets_distinct_file_ids():
    content = b"identical content across tenants"

    result_a = await save_uploaded_file(content, "doc.txt", user_id="user-a")
    result_b = await save_uploaded_file(content, "doc.txt", user_id="user-b")

    assert result_a["success"] is True
    assert result_b["success"] is True
    assert result_a["file_id"] != result_b["file_id"]
    assert result_b.get("deduplicated") is not True


async def test_same_tenant_reupload_still_deduplicates():
    content = b"same tenant, same content"

    first = await save_uploaded_file(content, "doc.txt", user_id="user-a")
    second = await save_uploaded_file(content, "doc.txt", user_id="user-a")

    assert second["deduplicated"] is True
    assert second["file_id"] == first["file_id"]


async def test_anonymous_uploads_never_deduplicate_even_against_each_other():
    content = b"anonymous content"

    first = await save_uploaded_file(content, "doc.txt", user_id=None)
    second = await save_uploaded_file(content, "doc.txt", user_id=None)

    assert first["success"] is True
    assert second["success"] is True
    assert first["file_id"] != second["file_id"]
    assert second.get("deduplicated") is not True


# ── 2. Fail-closed MIME validation ──────────────────────────────────


async def test_upload_rejected_when_magic_unavailable_and_validation_required(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_REQUIRE_MIME_VALIDATION", True)

    result = await save_uploaded_file(b"hello", "doc.txt", user_id="user-a")

    assert result["success"] is False


async def test_upload_allowed_when_validation_explicitly_disabled(monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_REQUIRE_MIME_VALIDATION", False)

    result = await save_uploaded_file(b"hello", "doc.txt", user_id="user-a")

    assert result["success"] is True


# ── 3. Bounded indexing queue ────────────────────────────────────────


async def test_queue_full_drops_the_job_instead_of_blocking_or_growing():
    from reasoner.infrastructure.documents import index_queue

    index_queue._reset_for_tests()
    q = index_queue._ensure_started()
    # Fill the real queue to its configured maxsize directly (bypassing the
    # workers, which would otherwise drain it) to exercise the full-queue path.
    for i in range(q.maxsize):
        q.put_nowait((f"file-{i}", "text"))

    accepted = index_queue.enqueue_index_job("overflow-file", "text")

    assert accepted is False
    assert q.qsize() == q.maxsize  # nothing appended past capacity
    index_queue._reset_for_tests()


async def test_queue_accepts_jobs_under_capacity():
    from reasoner.infrastructure.documents import index_queue

    index_queue._reset_for_tests()
    accepted = index_queue.enqueue_index_job("some-file", "text")

    assert accepted is True
    index_queue._reset_for_tests()


# ── 4. Encryption at rest ───────────────────────────────────────────


async def test_new_upload_is_encrypted_on_disk(_isolated_upload_dir):
    content = b"sensitive document content"

    result = await save_uploaded_file(content, "doc.txt", user_id="user-a")

    file_id = result["file_id"]
    on_disk = (uploader.UPLOAD_DIR / f"{file_id}.txt").read_bytes()
    assert on_disk != content  # not stored as plaintext

    meta = json.loads((uploader.UPLOAD_DIR / f"{file_id}.meta.json").read_text())
    assert meta["encrypted"] is True


async def test_encrypted_upload_round_trips_through_get_file_text(_isolated_upload_dir):
    content = b"round trip content for extraction"

    result = await save_uploaded_file(content, "doc.txt", user_id="user-a")
    text = await uploader.get_file_text(result["file_id"], user_id="user-a")

    assert text == content.decode("utf-8")


async def test_legacy_plaintext_file_with_no_encrypted_flag_still_reads(_isolated_upload_dir):
    """Proves no migration is required: a file written before this change
    existed (no "encrypted" key in its meta) must keep reading correctly."""
    file_id = "aaaa00000001"  # must match get_file_text's [a-f0-9-]+ validation
    (uploader.UPLOAD_DIR / f"{file_id}.txt").write_bytes(b"old plaintext content")
    (uploader.UPLOAD_DIR / f"{file_id}.meta.json").write_text(
        json.dumps({"user_id": "user-a", "filename": "old.txt", "mime_type": "text/plain"})
    )

    text = await uploader.get_file_text(file_id, user_id="user-a")

    assert text == "old plaintext content"


async def test_vector_sidecar_encrypted_and_legacy_plaintext_both_readable(_isolated_upload_dir):
    from reasoner.documents.vector_store import DocumentVectorStore

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    store = DocumentVectorStore(embedder=embedder)

    # New sidecar: encrypted.
    file_id = "vec-encrypted-1"
    (uploader.UPLOAD_DIR / f"{file_id}.meta.json").write_text(
        json.dumps({"user_id": "user-a"})
    )
    await store.index_file(file_id, "some content to embed and chunk for retrieval testing")
    envelope = json.loads((uploader.UPLOAD_DIR / f"{file_id}.vectors.json").read_text())
    assert envelope.get("encrypted") is True

    # Legacy sidecar: plain, no "encrypted" key -- must still be readable.
    legacy_id = "vec-legacy-1"
    (uploader.UPLOAD_DIR / f"{legacy_id}.meta.json").write_text(
        json.dumps({"user_id": "user-a"})
    )
    (uploader.UPLOAD_DIR / f"{legacy_id}.vectors.json").write_text(
        json.dumps({
            "file_id": legacy_id,
            "chunks": [{"text": "legacy chunk", "embedding": [1.0, 0.0]}],
        })
    )

    results = await store.retrieve("query", [file_id, legacy_id], top_k=10, user_id="user-a")

    assert any("legacy chunk" in r for r in results)
