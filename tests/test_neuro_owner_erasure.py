"""GDPR Art. 17 erasure of Neuro long-term memory (D-defect re-land of PR #9).

data_eraser.py step 3 used to import SessionManager, never call it, and fall
through with a "best-effort cache clear" comment -- Neuro L1/L2/L3 memory
(verbatim prompts and responses) survived every erasure while the receipt
said "completed". tenant_key(owner, agent_id) now scopes a signed-in user's
data to one tenant per conversation ("u-{owner}-{agent_id}"), not one
directory per user, so erasure has to enumerate every tenant an owner has
used. These tests pin NeuroService.erase_owner: it must remove exactly one
owner's tenants -- in memory and on disk -- and leave every other owner's
memory intact and recallable.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import reasoner.neuro.server as ns
from reasoner.neuro.config import NeuroConfig, _apply_defaults, _safe_agent_id
from reasoner.neuro.server import LearnRequest, tenant_key


class _FakeEmbedding:
    active_label = "fake"
    status = {"provider": "fake"}

    async def health_check(self) -> bool:
        return True

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.lower().encode()).digest()
        return [b / 255.0 for b in digest[:16]]


class _FakeReasoning(_FakeEmbedding):
    async def generate(self, *args, **kwargs):
        return "{}"


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(ns.settings, "COHERE_RERANK_ENABLED", False, raising=False)
    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _FakeReasoning())
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    return ns.NeuroService(cfg)


async def _learn(
    service: ns.NeuroService, owner: str | None, agent_id: str, prompt: str, response: str
) -> None:
    await service.ingest(
        LearnRequest(prompt=prompt, response=response, agent_id=agent_id, metadata={}),
        owner=owner,
    )


@pytest.mark.asyncio
async def test_erase_owner_removes_their_tenants_and_leaves_others(service, tmp_path):
    # user-x has two conversations, user-y has one -- exercising the "one
    # tenant per (owner, agent_id) pair, not one directory per user" case.
    await _learn(service, "user-x", "conv1", "x's secret plan A", "response A")
    await _learn(service, "user-x", "conv2", "x's secret plan B", "response B")
    await _learn(service, "user-y", "conv1", "y's unrelated chat", "y's response")

    agents_dir = Path(tmp_path) / "agents"
    before = {p.name for p in agents_dir.iterdir()}
    assert sum(1 for n in before if n.startswith("u-user-x-")) == 2
    assert sum(1 for n in before if n.startswith("u-user-y-")) == 1

    result = await service.erase_owner("user-x")

    assert result["erased"] is True
    assert result["dirs_removed"] == 2
    assert result["tenants_evicted"] == 2
    assert result["error"] is None

    after = {p.name for p in agents_dir.iterdir()}
    assert not any(n.startswith("u-user-x-") for n in after), f"user-x data survived: {after}"
    assert any(n.startswith("u-user-y-") for n in after), "user-y's data was wrongly removed"

    # In-process cache: x's tenants must be gone, y's must still be live.
    assert not any(k.startswith("u-user-x-") for k in service.tenants.active_tenants)
    assert tenant_key("user-y", "conv1") in service.tenants.active_tenants

    # x's memory is actually unrecoverable, not just relocated.
    x_recall = await service.recall("x's secret plan A", agent_id="conv1", owner="user-x")
    assert x_recall == [], f"user-x memory is still recallable after erasure: {x_recall}"

    # y is unaffected end to end.
    y_recall = await service.recall("y's unrelated chat", agent_id="conv1", owner="user-y")
    assert any("y's unrelated chat" in c["content"] for c in y_recall), (
        "erasing user-x must not touch user-y's memory"
    )


@pytest.mark.asyncio
async def test_erase_owner_with_no_data_is_still_a_success(service):
    """A user who never used Neuro has nothing to remove -- that is a
    successful erasure, not a failure (mirrors get_agent_data_dir's existing
    'nothing stored' contract)."""
    result = await service.erase_owner("never-had-any-data")
    assert result == {
        "erased": True,
        "dirs_removed": 0,
        "tenants_evicted": 0,
        "error": None,
    }


@pytest.mark.asyncio
async def test_erase_owner_never_touches_anonymous_tenants(service, tmp_path):
    """Anonymous (owner=None) tenants use the 'a-' prefix and are not owned
    by any signed-in identity; erasing a real owner must not sweep them up."""
    await _learn(service, None, "shared-conv-id", "anonymous chat", "anon response")
    await _learn(service, "user-x", "shared-conv-id", "x's chat", "x response")

    result = await service.erase_owner("user-x")
    assert result["dirs_removed"] == 1

    agents_dir = Path(tmp_path) / "agents"
    remaining = {p.name for p in agents_dir.iterdir()}
    assert any(n.startswith("a-") for n in remaining), "anonymous tenant was wrongly removed"
    assert not any(n.startswith("u-user-x-") for n in remaining)


def test_erase_owner_prefix_matches_the_storage_sanitizer(tmp_path):
    """The prefix erase_owner searches for must be derived the same way the
    storage layer derives tenant directory names, or erasure silently misses
    real data. This is a static proof, independent of the async fixture."""
    from reasoner.neuro.server import _owned_prefix

    owner = "018f3c9a-7b2e-4d1f-9c8a-1a2b3c4d5e6f"
    full_key = tenant_key(owner, "some-conversation")
    assert _safe_agent_id(full_key).startswith(_safe_agent_id(_owned_prefix(owner)))
