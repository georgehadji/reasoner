"""The research flow's file search is owner-checked and reads encrypted sidecars (SEC-4).

PrismFileSearch read UPLOAD_DIR/{file_id}.vectors.json by bare id: any caller
naming another tenant's file id got its legacy plaintext chunks, and every new
upload (encrypted sidecar) returned nothing. DocumentVectorStore now serves the
port with the owner check retrieve() already had.
See docs/plans/audit-remediation-2026-10-20.md, SEC-4.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from reasoner.documents.vector_store import DocumentVectorStore
from reasoner.uploader import UPLOAD_DIR

_IDS = ("test-tenancy-a", "test-tenancy-b")


@pytest.fixture
def store():
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[1.0, 0.0])
    yield DocumentVectorStore(embedder=embedder)
    for fid in _IDS:
        for suffix in (".meta.json", ".vectors.json"):
            (UPLOAD_DIR / f"{fid}{suffix}").unlink(missing_ok=True)


def _upload(file_id: str, owner: str, text: str, *, encrypted: bool) -> None:
    (UPLOAD_DIR / f"{file_id}.meta.json").write_text(json.dumps({"user_id": owner}))
    sidecar = {"file_id": file_id, "chunks": [{"text": text, "embedding": [1.0, 0.0]}]}
    if encrypted:
        from reasoner.security.encryption import get_encryption_service

        sidecar = {"encrypted": True, "payload": get_encryption_service().encrypt(json.dumps(sidecar))}
    (UPLOAD_DIR / f"{file_id}.vectors.json").write_text(json.dumps(sidecar))


@pytest.mark.asyncio
async def test_another_users_file_returns_no_chunks(store):
    _upload(_IDS[0], "alice", "alice's secret", encrypted=False)

    assert await store.search_chunks([_IDS[0]], "q", user_id="mallory") == []
    assert await store.search_chunks([_IDS[0]], "q", user_id=None) == []
    (own,) = await store.search_chunks([_IDS[0]], "q", user_id="alice")
    assert own.file_id == _IDS[0] and own.content == "alice's secret"


@pytest.mark.asyncio
async def test_encrypted_sidecar_returns_chunks(store):
    _upload(_IDS[1], "alice", "encrypted text", encrypted=True)

    (chunk,) = await store.search_chunks([_IDS[1]], "q", user_id="alice")
    assert chunk.content == "encrypted text"
    assert chunk.score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_research_flow_passes_the_run_owner():
    from reasoner.application.flows.prism_research import _action_uploads_search

    seen = {}

    class _Search:
        async def search_chunks(self, file_ids, query, top_k=5, user_id=None):
            seen["user_id"] = user_id
            return []

    await _action_uploads_search(_Search(), ["abc"], ["q"], "alice")
    assert seen["user_id"] == "alice"


@pytest.mark.parametrize("bad", ["../x", "a/b", "ABC", "x" * 37])
def test_a_path_like_file_id_is_rejected(bad):
    from reasoner.api.schemas import RunRequest

    with pytest.raises(ValidationError):
        RunRequest(problem="hello there", file_ids=[bad])
    assert RunRequest(problem="hello there", file_ids=["0a1b2c3d-4e5"]).file_ids == ["0a1b2c3d-4e5"]
