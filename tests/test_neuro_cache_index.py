"""Neuro L1/L2: cross-worker freshness, vectorised search, append-only L2 index."""

import json

import numpy as np
import pytest

from reasoner.neuro.cache import L1Cache, L2Index, cosine_similarity, read_l2_entries
from reasoner.neuro.config import CacheConfig


@pytest.mark.parametrize("tier", [L1Cache, L2Index])
async def test_a_second_worker_sees_entries_written_after_it_loaded(tmp_path, tier):
    """RB-01: each uvicorn worker holds its own copy of a tenant. A learn in one
    worker stayed invisible to recall in the other until the tenant was evicted."""
    reader, writer = tier(tmp_path, CacheConfig()), tier(tmp_path, CacheConfig())
    assert reader.search([1.0, 0.0]) == []
    await writer.add("fresh", "s", [1.0, 0.0], {"schema_version": 1})
    [hit] = reader.search([1.0, 0.0])
    assert hit.content == "fresh"


async def test_vectorised_search_ranks_like_pairwise_cosine(tmp_path):
    """LI-01: one mat-vec must return what the per-entry cosine loop returned."""
    rng = np.random.default_rng(7)
    index = L2Index(tmp_path, CacheConfig(l2_similarity_threshold=0.0, l2_max_entries=100))
    vectors = rng.normal(size=(40, 8)).tolist()
    for i, v in enumerate(vectors):
        await index.add(f"c{i}", "s", v)
    query = rng.normal(size=8).tolist()

    pairwise = sorted(
        ((cosine_similarity(query, v), f"c{i}") for i, v in enumerate(vectors)), reverse=True
    )
    expected = [(s, c) for s, c in pairwise if s > 0.0][:5]
    got = [(h.relevance, h.content) for h in index.search(query, top_k=5)]

    assert [c for _, c in got] == [c for _, c in expected]
    assert np.allclose([s for s, _ in got], [s for s, _ in expected], atol=1e-5)


async def test_l2_learn_appends_one_line_then_compacts(tmp_path):
    """LI-02: a learn rewrote every entry of index.json; it now appends one line."""
    cfg = CacheConfig(l2_max_entries=3)
    index = L2Index(tmp_path, cfg)
    path = tmp_path / "index.jsonl"
    await index.add("a", "s", [1.0, 0.0])
    before = path.read_bytes()
    await index.add("b", "s", [0.0, 1.0])
    assert path.read_bytes().startswith(before)

    for content in "cdefg":  # the 7th record passes 2 x max and triggers compaction
        await index.add(content, "s", [1.0, 1.0])
    assert len([line for line in path.read_text(encoding="utf-8").split("\n") if line]) <= 2 * 3
    assert [e["content"] for e in L2Index(tmp_path, cfg).entries] == ["e", "f", "g"]


async def test_legacy_index_json_is_migrated(tmp_path):
    legacy = [{"id": "x", "content": "old", "source": "s", "embedding": [1.0, 0.0]}]
    (tmp_path / "index.json").write_text(json.dumps(legacy), encoding="utf-8")
    assert [e["content"] for e in read_l2_entries(tmp_path)] == ["old"]  # export sees it unmigrated

    index = L2Index(tmp_path, CacheConfig())
    assert [e["content"] for e in index.entries] == ["old"]
    assert not (tmp_path / "index.json").exists()
    assert [e["content"] for e in read_l2_entries(tmp_path)] == ["old"]


async def test_a_torn_l2_line_loses_only_itself(tmp_path):
    good = json.dumps({"id": "a", "content": "kept", "embedding": [1.0, 0.0]})
    (tmp_path / "index.jsonl").write_text(good + "\n" + '{"id": "b", "con', encoding="utf-8")
    index = L2Index(tmp_path, CacheConfig())
    await index.add("next", "s", [0.0, 1.0])
    assert {e["content"] for e in L2Index(tmp_path, CacheConfig()).entries} == {"kept", "next"}
