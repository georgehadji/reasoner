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


@pytest.fixture
def service(tmp_path, monkeypatch):
    """The same NeuroService the router wraps, called directly as MemoryPort."""
    monkeypatch.setattr(ns.settings, "COHERE_RERANK_ENABLED", False, raising=False)
    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _FakeReasoning())
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    return ns.NeuroService(cfg)


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


def test_service_satisfies_the_memory_port(service):
    """The pipeline reaches memory through MemoryPort, in-process. If the
    signatures drift, recall/learn fail at runtime inside an except block that
    swallows them -- memory would go quietly dead rather than fail loudly."""
    from reasoner.core.ports.memory_port import MemoryPort

    assert isinstance(service, MemoryPort)


def test_port_round_trip_needs_no_http_server(service):
    """This is the point of the refactor: memory used to be an HTTP self-call
    to /api/neuro/learn, which always failed in CLI/headless mode because
    nothing was listening for the app to call itself."""
    import asyncio

    async def scenario():
        await service.learn(
            prompt=PROMPT,
            response="It trips after 3 failures and routes to the next chain entry.",
            agent_id=AGENT,
        )
        return await service.recall(PROMPT, agent_id=AGENT, max_results=5)

    chunks = asyncio.run(scenario())
    assert chunks, "in-process recall returned nothing"
    assert {"content", "source", "relevance"} <= set(chunks[0])


def test_router_and_port_share_one_service(monkeypatch):
    """L1 is an in-memory cache backed by disk, so two service instances would
    hold divergent copies of it."""
    import reasoner.neuro.server as srv

    monkeypatch.setattr(srv, "_service", None)
    monkeypatch.setattr(srv, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(srv, "create_resilient_reasoning", lambda c: _FakeReasoning())

    first = srv.get_neuro_service()
    srv.create_neuro_router()
    assert srv.get_neuro_service() is first


def test_hostile_agent_id_creates_no_dirs_outside_agents(client, tmp_path):
    client.post("/api/neuro/learn", json={
        "prompt": "p", "response": "r", "agent_id": "../../../../pwned",
    })
    assert not (tmp_path / "pwned").exists()
    assert not (tmp_path.parent / "pwned").exists()
    assert all(d.parent == tmp_path / "agents"
               for d in (tmp_path / "agents").iterdir())


def test_owner_scoping_isolates_the_same_agent_id(service):
    """agent_id is a conversation id from the request body. Before owner
    scoping, anyone who learned another user's conversation id could recall
    that conversation's memory."""
    import asyncio

    async def scenario():
        await service.learn(
            prompt="alice private planning notes",
            response="alice secret",
            agent_id="shared-conversation-id",
            owner="alice",
        )
        victim = await service.recall(
            "alice private planning notes",
            agent_id="shared-conversation-id",
            owner="alice",
        )
        # same agent_id, different identity
        attacker = await service.recall(
            "alice private planning notes",
            agent_id="shared-conversation-id",
            owner="mallory",
        )
        # and an unauthenticated caller guessing the raw id
        anonymous = await service.recall(
            "alice private planning notes",
            agent_id="shared-conversation-id",
        )
        return victim, attacker, anonymous

    victim, attacker, anonymous = asyncio.run(scenario())
    assert victim, "owner lost access to their own memory"
    assert not attacker, f"cross-tenant leak: {attacker}"
    assert not anonymous, f"anonymous leak: {anonymous}"


def test_tenant_key_separates_identities():
    from reasoner.neuro.server import tenant_key

    assert tenant_key("alice", "conv1") != tenant_key("mallory", "conv1")
    assert tenant_key(None, "conv1") == "conv1"
    assert tenant_key("alice", "conv1") == tenant_key("alice", "conv1")
    # an owner must not be able to forge another's namespace via agent_id
    assert tenant_key("mallory", "alice~conv1") != tenant_key("alice", "conv1")
