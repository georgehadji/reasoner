"""The L1/L2/L3 tiers were reachable by /recall but nothing ever wrote them,
so recall silently degraded to HOT substring matching. These tests fail if
either half of that wiring is removed again -- the failure mode is silent,
so it needs a test rather than a runtime assertion.
"""

import hashlib
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import reasoner.neuro.server as ns
from reasoner.neuro.config import NeuroConfig, _apply_defaults


class _FakeEmbedding:
    """Deterministic stand-in: identical text -> identical vector."""
    active_label = "fake"
    status = {"provider": "fake"}

    async def health_check(self):
        return True

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.lower().encode()).digest()
        return [b / 255.0 for b in digest[:16]]


class _FakeReasoning(_FakeEmbedding):
    async def generate(self, *args, **kwargs):
        return "{}"


NEURO_KEY = "test-neuro-internal-key"


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Pin rerank off: it is orthogonal to tier wiring and reaches the network.
    monkeypatch.setattr(ns.settings, "COHERE_RERANK_ENABLED", False, raising=False)
    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _FakeReasoning())
    monkeypatch.setenv("NEURO_INTERNAL_KEY", NEURO_KEY)
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    application = FastAPI()
    application.include_router(ns.create_neuro_router(cfg))
    return application


@pytest.fixture
def client(app):
    return TestClient(app, headers={"X-Neuro-Key": NEURO_KEY})


AGENT = "wiring-test-agent"
PROMPT = "How does the circuit breaker pick a fallback provider?"


def test_learn_indexes_the_exchange_into_l1_and_l2(client, tmp_path):
    resp = client.post("/api/neuro/learn", json={
        "prompt": PROMPT,
        "response": "It trips after 3 failures and routes to the next chain entry.",
        "agent_id": AGENT,
    })
    assert resp.status_code == 200

    index = tmp_path / "agents" / AGENT / "cache" / "l2" / "index.json"
    assert index.exists(), "/learn did not write the L2 index"
    entries = json.loads(index.read_text())
    assert len(entries) == 1
    assert entries[0]["embedding"], "L2 entry stored without an embedding"

    l1_bundles = list((tmp_path / "agents" / AGENT / "cache" / "l1").glob("*.json"))
    assert len(l1_bundles) == 1, "/learn did not write an L1 bundle"
    bundle = json.loads(l1_bundles[0].read_text())
    assert bundle["embedding"], "L1 bundle stored without an embedding"


def test_l1_created_at_is_wall_clock_not_monotonic(client, tmp_path):
    """created_at is persisted and compared across processes, so it must be
    wall clock. time.monotonic() has an undefined reference point and made
    a restored bundle's age meaningless."""
    client.post("/api/neuro/learn", json={
        "prompt": PROMPT, "response": "r", "agent_id": AGENT,
    })
    bundle = json.loads(
        next((tmp_path / "agents" / AGENT / "cache" / "l1").glob("*.json")).read_text()
    )
    assert abs(bundle["created_at"] - time.time()) < 60, (
        f"created_at {bundle['created_at']} is not a wall-clock timestamp"
    )


def test_recall_returns_l1_hits(client):
    client.post("/api/neuro/learn", json={
        "prompt": PROMPT,
        "response": "It trips after 3 failures and routes to the next chain entry.",
        "agent_id": AGENT,
    })
    resp = client.post("/api/neuro/recall", json={
        "prompt": PROMPT, "agent_id": AGENT, "max_results": 5,
    })
    assert resp.status_code == 200
    tiers = {c["cache_tier"] for c in resp.json()["chunks"]}
    assert "L1" in tiers, f"recall never reached L1, got {tiers}"


def test_recall_returns_l2_hits(client):
    client.post("/api/neuro/learn", json={
        "prompt": PROMPT,
        "response": "It trips after 3 failures and routes to the next chain entry.",
        "agent_id": AGENT,
    })
    resp = client.post("/api/neuro/recall", json={
        "prompt": PROMPT, "agent_id": AGENT, "max_results": 5,
    })
    assert resp.status_code == 200
    tiers = {c["cache_tier"] for c in resp.json()["chunks"]}
    assert "L2" in tiers, f"recall never reached L2, got {tiers}"


def test_recall_scans_l3_where_archival_actually_writes(client, tmp_path):
    """l3_scan must read sessions/warm -- the dir archive_hot_sessions writes."""
    warm = tmp_path / "agents" / AGENT / "sessions" / "warm"
    warm.mkdir(parents=True, exist_ok=True)
    summary = "Earlier discussion of pricing tiers for premium presets."
    (warm / "sess-old.json").write_text(json.dumps({
        "session_id": "sess-old",
        "summary": summary,
        "key_facts": ["premium presets cost roughly $0.15-$0.30 per run"],
    }))

    resp = client.post("/api/neuro/recall", json={
        "prompt": summary, "agent_id": AGENT, "max_results": 5,
    })
    assert resp.status_code == 200
    tiers = {c["cache_tier"] for c in resp.json()["chunks"]}
    assert "L3" in tiers, f"recall never reached L3, got {tiers}"
    assert (warm / ".emb_cache").exists(), "L3 sidecar embedding cache not written"


def test_learn_survives_a_dead_embedding_provider(client, monkeypatch, tmp_path):
    """Indexing is best-effort: it must not fail the ingest."""
    async def boom(_text):
        raise RuntimeError("embedding provider down")

    monkeypatch.setattr(_FakeEmbedding, "embed", staticmethod(boom))
    resp = client.post("/api/neuro/learn", json={
        "prompt": "p", "response": "r", "agent_id": AGENT,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "learned"


@pytest.mark.parametrize("path,payload", [
    ("/api/neuro/learn", {"prompt": "p", "response": "r"}),
    ("/api/neuro/recall", {"prompt": "p"}),
    ("/api/neuro/audit", {"prompt": "p", "draft_response": "d"}),
])
def test_endpoints_reject_callers_without_the_internal_key(app, path, payload):
    """These are mounted on the public app. Ungated, /audit is a free LLM
    proxy and /learn writes into tenant memory."""
    unauthenticated = TestClient(app)
    assert unauthenticated.post(path, json=payload).status_code == 403

    wrong_key = TestClient(app, headers={"X-Neuro-Key": "not-the-key"})
    assert wrong_key.post(path, json=payload).status_code == 403


def test_health_is_also_gated(app):
    """It reports provider status and configured agent ids."""
    assert TestClient(app).get("/api/neuro/health").status_code == 403


def test_key_comes_from_the_environment(monkeypatch):
    """Every gunicorn worker and the Next server must agree on this value,
    so it is read from one env var rather than derived from another secret."""
    from reasoner.core.settings import settings

    monkeypatch.setenv("NEURO_INTERNAL_KEY", "  operator-chosen-key  ")
    assert settings.neuro_internal_key == "operator-chosen-key"

    monkeypatch.delenv("NEURO_INTERNAL_KEY", raising=False)
    assert settings.neuro_internal_key == ""


def test_unset_key_leaves_endpoints_open_for_local_dev(tmp_path, monkeypatch):
    """api/__init__.py refuses to start in production when the key is unset,
    so this fail-open branch is only ever the development posture."""
    monkeypatch.setattr(ns.settings, "COHERE_RERANK_ENABLED", False, raising=False)
    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _FakeReasoning())
    monkeypatch.delenv("NEURO_INTERNAL_KEY", raising=False)
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    application = FastAPI()
    application.include_router(ns.create_neuro_router(cfg))

    resp = TestClient(application).post("/api/neuro/learn", json={
        "prompt": "p", "response": "r", "agent_id": AGENT,
    })
    assert resp.status_code == 200


def test_pipeline_client_carries_a_key_the_gate_accepts(app, monkeypatch):
    """The orchestrator swallows neuro failures, so a self-call rejected by
    the gate would make memory silently dead in production rather than loud."""
    import asyncio

    import reasoner.infrastructure.clients as clients

    monkeypatch.setenv("NEURO_INTERNAL_KEY", NEURO_KEY)
    asyncio.run(clients.close_neuro_client())
    try:
        neuro_client = clients.get_neuro_client()
        assert neuro_client.headers.get("X-Neuro-Key") == NEURO_KEY

        # the gate must accept exactly the headers that client sends
        resp = TestClient(app, headers=dict(neuro_client.headers)).post(
            "/api/neuro/learn",
            json={"prompt": "p", "response": "r", "agent_id": AGENT},
        )
        assert resp.status_code == 200
    finally:
        asyncio.run(clients.close_neuro_client())


def test_hostile_agent_id_creates_no_dirs_outside_agents(client, tmp_path):
    client.post("/api/neuro/learn", json={
        "prompt": "p", "response": "r", "agent_id": "../../../../pwned",
    })
    assert not (tmp_path / "pwned").exists()
    assert not (tmp_path.parent / "pwned").exists()
    assert all(d.parent == tmp_path / "agents"
               for d in (tmp_path / "agents").iterdir())
