"""DAT-12: the public Neuro health probe returns counts, not tenant keys.

Behaviour under test: `NeuroService.health` (neuro/server.py).
`GET /api/neuro/health` is anonymous, and `agents_configured` carried
`TenantManager.active_tenants`: raw `u-<user uuid>-<conversation>` keys, so
anyone could list which users have recently used memory and under which
conversation ids. The probe needs a count.
"""

from __future__ import annotations

import hashlib

import pytest

import reasoner.neuro.server as ns
from reasoner.neuro.config import NeuroConfig, _apply_defaults
from reasoner.neuro.server import LearnRequest

pytestmark = pytest.mark.unit

USER = "aaaaaaaa-1111-4111-8111-111111111111"


class _Fake:
    active_label = "fake"
    status = {"provider": "fake"}

    async def health_check(self) -> bool:
        return True

    async def embed(self, text: str) -> list[float]:
        return [b / 255.0 for b in hashlib.sha256(text.encode()).digest()[:16]]

    async def generate(self, *a, **k):
        return "{}"


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(ns.settings, "COHERE_RERANK_ENABLED", False, raising=False)
    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _Fake())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _Fake())
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    return ns.NeuroService(cfg)


@pytest.mark.asyncio
async def test_health_after_a_learn_does_not_contain_the_owners_id(service):
    await service.ingest(
        LearnRequest(prompt="my plan", response="ok", agent_id="conv-1", metadata={}),
        owner=USER,
    )

    health = await service.health()

    assert USER not in health.model_dump_json()
    assert "conv-1" not in health.model_dump_json()


@pytest.mark.asyncio
async def test_health_reports_how_many_tenants_are_active(service):
    await service.ingest(
        LearnRequest(prompt="a", response="b", agent_id="conv-1", metadata={}), owner=USER
    )

    health = await service.health()

    assert health.active_tenant_count == 1
    assert health.agents_configured == list(service.config.agents.keys())
