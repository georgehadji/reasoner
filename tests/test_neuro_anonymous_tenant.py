"""No shared anonymous memory (DAT-4, tenant part).

tenant_key(None, None) is None, and TenantManager.get(None) is the "default"
tenant. Every anonymous run without a conversation id learned into it, and
/api/neuro/recall with no owner and no agent_id read it back, so one anonymous
caller could read another's synthesis. A missing key now means no memory.
Anonymous runs with a conversation id keep their own "a-<id>" tenant (Q6).
See docs/plans/audit-remediation-2026-10-20.md, DAT-4.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import reasoner.neuro.server as ns
from reasoner.neuro.config import NeuroConfig, _apply_defaults
from reasoner.neuro.server import LearnRequest, RecallRequest


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


def _tenants(tmp_path) -> set[str]:
    agents = Path(tmp_path) / "agents"
    return {p.name for p in agents.iterdir()} if agents.exists() else set()


@pytest.mark.asyncio
async def test_two_anonymous_runs_cannot_recall_each_other(service, tmp_path):
    learned = await service.ingest(
        LearnRequest(prompt="alice asks", response="alice's private answer", metadata={}),
        owner=None,
    )
    assert learned.status == "dropped_anonymous"

    recalled = await service.recall_chunks(RecallRequest(prompt="alice asks"), owner=None)
    assert recalled.chunks == []
    assert await service.list_sessions(owner=None) == {"entries": [], "total": 0}
    assert not any(name.endswith("default") for name in _tenants(tmp_path)), (
        "no shared tenant may be created for anonymous callers"
    )


@pytest.mark.asyncio
async def test_an_anonymous_conversation_keeps_its_own_tenant(service, tmp_path):
    learned = await service.ingest(
        LearnRequest(prompt="p", response="r", agent_id="conv-1", metadata={}), owner=None
    )
    assert learned.status != "dropped_anonymous"
    assert "a-conv-1" in _tenants(tmp_path)
