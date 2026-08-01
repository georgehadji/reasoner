"""Unit tests for PrismFileSearch."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from reasoner.infrastructure.prism.file_search import PrismFileSearch
from reasoner.infrastructure.uploader import get_upload_dir


@pytest.fixture
def mock_embedder():
    emb = AsyncMock()
    emb.embed.return_value = [1.0, 0.0, 0.0]
    return emb


@pytest.fixture(autouse=True)
def cleanup_sidecars():
    yield
    for f in get_upload_dir().glob("*.vectors.json"):
        if f.name.startswith("test-"):
            f.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_search_chunks_loads_sidecar(mock_embedder):
    """File search reads sidecars and returns scored chunks."""
    file_id = "test-doc-1"
    sidecar = {
        "file_id": file_id,
        "chunks": [
            {"text": "chunk one", "embedding": [1.0, 0.0, 0.0]},
            {"text": "chunk two", "embedding": [0.0, 1.0, 0.0]},
        ],
    }
    path = get_upload_dir() / f"{file_id}.vectors.json"
    path.write_text(json.dumps(sidecar), encoding="utf-8")

    fs = PrismFileSearch(embedder=mock_embedder)
    results = await fs.search_chunks([file_id], "query", top_k=2)

    assert len(results) == 2
    assert results[0].file_id == file_id
    assert results[0].content == "chunk one"
    assert results[0].score == pytest.approx(1.0)

    path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_search_chunks_missing_sidecar(mock_embedder):
    """Missing sidecar returns empty list."""
    fs = PrismFileSearch(embedder=mock_embedder)
    results = await fs.search_chunks(["test-missing"], "query", top_k=2)
    assert results == []


@pytest.mark.asyncio
async def test_search_chunks_top_k(mock_embedder):
    """Only top_k results are returned."""
    file_id = "test-doc-2"
    sidecar = {
        "file_id": file_id,
        "chunks": [
            {"text": "a", "embedding": [1.0, 0.0, 0.0]},
            {"text": "b", "embedding": [0.5, 0.0, 0.0]},
            {"text": "c", "embedding": [0.2, 0.0, 0.0]},
        ],
    }
    path = get_upload_dir() / f"{file_id}.vectors.json"
    path.write_text(json.dumps(sidecar), encoding="utf-8")

    fs = PrismFileSearch(embedder=mock_embedder)
    results = await fs.search_chunks([file_id], "query", top_k=1)

    assert len(results) == 1
    assert results[0].content == "a"

    path.unlink(missing_ok=True)
