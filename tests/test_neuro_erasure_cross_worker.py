"""DAT-13: a Neuro erasure holds on every worker, not only the one that ran it.

Behaviour under test: `TenantManager.end_erase` / `is_erased` / `get`
(neuro/server.py). The write tombstone was an in-memory dict, so after worker A
erased a user the other workers kept serving the memory from their L1/L2
caches, and their next L2 save rewrote the erased index. Two `NeuroService`s
over one `data_dir` stand in for two workers.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import reasoner.neuro.server as ns
from reasoner.neuro.config import NeuroConfig, _apply_defaults
from reasoner.neuro.server import LearnRequest, RecallRequest, tenant_key

pytestmark = pytest.mark.unit

USER = "aaaaaaaa-1111-4111-8111-111111111111"
OTHER = "bbbbbbbb-2222-4222-8222-222222222222"


class _Fake:
    active_label = "fake"
    status = {"provider": "fake"}

    async def health_check(self) -> bool:
        return True

    async def embed(self, text: str) -> list[float]:
        return [b / 255.0 for b in hashlib.sha256(text.lower().encode()).digest()[:16]]

    async def generate(self, *a, **k):
        return "{}"


def _worker(data_dir: Path, monkeypatch) -> ns.NeuroService:
    monkeypatch.setattr(ns.settings, "COHERE_RERANK_ENABLED", False, raising=False)
    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _Fake())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _Fake())
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(data_dir)
    return ns.NeuroService(cfg)


@pytest.fixture
def workers(tmp_path, monkeypatch):
    # No listing cache, so the assertions below are about the marker, not timing.
    monkeypatch.setattr(ns.TenantManager, "ERASED_CACHE_SECONDS", 0.0)
    return _worker(tmp_path, monkeypatch), _worker(tmp_path, monkeypatch), tmp_path


async def _learn(service, owner, agent_id="conv1", prompt="the secret plan"):
    await service.ingest(
        LearnRequest(prompt=prompt, response="noted", agent_id=agent_id, metadata={}), owner=owner
    )


@pytest.mark.asyncio
async def test_the_other_worker_sees_the_erasure(workers):
    a, b, _ = workers
    await _learn(b, USER)

    assert (await a.erase_owner(USER))["erased"] is True

    assert b.tenants.is_erased(tenant_key(USER, "conv1"))
    assert not b.tenants.is_erased(tenant_key(OTHER, "conv1")), "only the erased owner"


@pytest.mark.asyncio
async def test_the_other_workers_recall_returns_nothing_even_from_its_cache(workers):
    a, b, _ = workers
    await _learn(b, USER)
    before = await b.recall_chunks(RecallRequest(prompt="the secret plan", agent_id="conv1"), USER)
    assert before.total_found > 0, "worker B holds the memory in its caches"

    await a.erase_owner(USER)

    after = await b.recall_chunks(RecallRequest(prompt="the secret plan", agent_id="conv1"), USER)
    assert after.chunks == []


@pytest.mark.asyncio
async def test_the_other_worker_does_not_recreate_the_erased_directory(workers):
    a, b, data_dir = workers
    await _learn(b, USER)
    await a.erase_owner(USER)

    await _learn(b, USER, prompt="written after the erasure")

    agents = data_dir / "agents"
    assert not [p for p in agents.iterdir() if p.name.startswith(f"u-{USER}-")]


@pytest.mark.asyncio
async def test_the_other_worker_drops_the_tenant_from_memory(workers):
    a, b, _ = workers
    await _learn(b, USER)
    key = tenant_key(USER, "conv1")
    assert key in b.tenants.active_tenants

    await a.erase_owner(USER)
    await b.tenants.get(tenant_key(OTHER, "conv1"))  # any access sweeps erased tenants

    assert key not in b.tenants.active_tenants


@pytest.mark.asyncio
async def test_a_marker_expires_and_is_swept(workers, monkeypatch):
    a, b, data_dir = workers
    await a.erase_owner(USER)
    markers = list((data_dir / ".erased").iterdir())
    assert len(markers) == 1
    assert json.loads(markers[0].read_text(encoding="utf-8"))["prefix"] == f"u-{USER}-"

    later = ns._wall_clock() + ns.TenantManager.IDLE_TTL_SECONDS + 5
    monkeypatch.setattr(ns, "_wall_clock", lambda: later)

    assert not b.tenants.is_erased(tenant_key(USER, "conv1"))
    assert not list((data_dir / ".erased").iterdir()), "expired markers are swept"


@pytest.mark.asyncio
async def test_markers_live_beside_the_agents_directory_not_inside_it(workers):
    """Tenant scans (maintenance, erase_owner) walk agents/; a marker there
    would be mistaken for a tenant."""
    a, _, data_dir = workers
    await _learn(a, USER)
    await a.erase_owner(USER)

    assert (data_dir / ".erased").is_dir()
    assert not (data_dir / "agents" / ".erased").exists()
