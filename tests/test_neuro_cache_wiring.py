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
# The `client` fixture is unauthenticated (owner=None), so tenant_key()
# prefixes its disk directory with "a-" (see test_tenant_key_* above).
AGENT_DIR = f"a-{AGENT}"
PROMPT = "How does the circuit breaker pick a fallback provider?"


def test_learn_indexes_the_exchange_into_l1_and_l2(client, tmp_path):
    resp = client.post(
        "/api/neuro/learn",
        json={
            "prompt": PROMPT,
            "response": "It trips after 3 failures and routes to the next chain entry.",
            "agent_id": AGENT,
        },
    )
    assert resp.status_code == 200

    index = tmp_path / "agents" / AGENT_DIR / "cache" / "l2" / "index.json"
    assert index.exists(), "/learn did not write the L2 index"
    entries = json.loads(index.read_text())
    assert len(entries) == 1
    assert entries[0]["embedding"], "L2 entry stored without an embedding"

    l1_bundles = list((tmp_path / "agents" / AGENT_DIR / "cache" / "l1").glob("*.json"))
    assert len(l1_bundles) == 1, "/learn did not write an L1 bundle"
    bundle = json.loads(l1_bundles[0].read_text())
    assert bundle["embedding"], "L1 bundle stored without an embedding"


def test_l1_created_at_is_wall_clock_not_monotonic(client, tmp_path):
    """created_at is persisted and compared across processes, so it must be
    wall clock. time.monotonic() has an undefined reference point and made
    a restored bundle's age meaningless."""
    client.post(
        "/api/neuro/learn",
        json={
            "prompt": PROMPT,
            "response": "r",
            "agent_id": AGENT,
        },
    )
    bundle = json.loads(
        next((tmp_path / "agents" / AGENT_DIR / "cache" / "l1").glob("*.json")).read_text()
    )
    assert (
        abs(bundle["created_at"] - time.time()) < 60
    ), f"created_at {bundle['created_at']} is not a wall-clock timestamp"


def test_recall_returns_l1_hits(client):
    client.post(
        "/api/neuro/learn",
        json={
            "prompt": PROMPT,
            "response": "It trips after 3 failures and routes to the next chain entry.",
            "agent_id": AGENT,
        },
    )
    resp = client.post(
        "/api/neuro/recall",
        json={
            "prompt": PROMPT,
            "agent_id": AGENT,
            "max_results": 5,
        },
    )
    assert resp.status_code == 200
    tiers = {c["cache_tier"] for c in resp.json()["chunks"]}
    assert "L1" in tiers, f"recall never reached L1, got {tiers}"


def test_recall_returns_l2_hits(client):
    client.post(
        "/api/neuro/learn",
        json={
            "prompt": PROMPT,
            "response": "It trips after 3 failures and routes to the next chain entry.",
            "agent_id": AGENT,
        },
    )
    resp = client.post(
        "/api/neuro/recall",
        json={
            "prompt": PROMPT,
            "agent_id": AGENT,
            "max_results": 5,
        },
    )
    assert resp.status_code == 200
    tiers = {c["cache_tier"] for c in resp.json()["chunks"]}
    assert "L2" in tiers, f"recall never reached L2, got {tiers}"


def test_recall_scans_l3_where_archival_actually_writes(client, tmp_path):
    """l3_scan must read sessions/warm -- the dir archive_hot_sessions writes."""
    warm = tmp_path / "agents" / AGENT_DIR / "sessions" / "warm"
    warm.mkdir(parents=True, exist_ok=True)
    summary = "Earlier discussion of pricing tiers for premium presets."
    (warm / "sess-old.json").write_text(
        json.dumps(
            {
                "session_id": "sess-old",
                "summary": summary,
                "key_facts": ["premium presets cost roughly $0.15-$0.30 per run"],
            }
        )
    )

    resp = client.post(
        "/api/neuro/recall",
        json={
            "prompt": summary,
            "agent_id": AGENT,
            "max_results": 5,
        },
    )
    assert resp.status_code == 200
    tiers = {c["cache_tier"] for c in resp.json()["chunks"]}
    assert "L3" in tiers, f"recall never reached L3, got {tiers}"
    assert (warm / ".emb_cache").exists(), "L3 sidecar embedding cache not written"


def test_learn_survives_a_dead_embedding_provider(client, monkeypatch, tmp_path):
    """Indexing is best-effort: it must not fail the ingest."""

    async def boom(_text):
        raise RuntimeError("embedding provider down")

    monkeypatch.setattr(_FakeEmbedding, "embed", staticmethod(boom))
    resp = client.post(
        "/api/neuro/learn",
        json={
            "prompt": "p",
            "response": "r",
            "agent_id": AGENT,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "learned"


@pytest.mark.parametrize(
    "path,payload",
    [
        ("/api/neuro/learn", {"prompt": "p", "response": "r"}),
        ("/api/neuro/recall", {"prompt": "p"}),
        ("/api/neuro/audit", {"prompt": "p", "draft_response": "d"}),
    ],
)
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

    resp = TestClient(application).post(
        "/api/neuro/learn",
        json={
            "prompt": "p",
            "response": "r",
            "agent_id": AGENT,
        },
    )
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
    client.post(
        "/api/neuro/learn",
        json={
            "prompt": "p",
            "response": "r",
            "agent_id": "../../../../pwned",
        },
    )
    assert not (tmp_path / "pwned").exists()
    assert not (tmp_path.parent / "pwned").exists()
    assert all(d.parent == tmp_path / "agents" for d in (tmp_path / "agents").iterdir())


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
    assert tenant_key("alice", "conv1") == tenant_key("alice", "conv1")
    assert tenant_key(None, "conv1") == "a-conv1"
    # an owner must not be able to forge another's namespace via agent_id
    assert tenant_key("mallory", "alice~conv1") != tenant_key("alice", "conv1")


def test_tenant_key_survives_the_filesystem_sanitizer_disjointly():
    """D1 proof-of-defect (pre-fix regression guard).

    tenant_key used to join owner and agent_id with a bare "~" separator.
    get_agent_data_dir's path sanitizer strips every character outside
    [A-Za-z0-9_-], including "~" -- so on disk, tenant_key("alice", "conv1")
    ("alice~conv1" -> sanitized "aliceconv1") collided with an anonymous
    caller who simply supplied agent_id="aliceconv1" directly
    (tenant_key(None, "aliceconv1") -> "aliceconv1" -> sanitized identically).
    Two distinct in-memory tenants then shared one on-disk directory, so an
    anonymous caller could read and write an owned tenant's memory once
    either tenant object reloaded (worker restart, TTL/LRU eviction).

    This must hold for every value tenant_key can emit, not just this one
    pair, since the fix's guarantee is structural (disjoint prefixes), not
    case-specific.
    """
    from reasoner.neuro.config import _safe_agent_id
    from reasoner.neuro.server import tenant_key

    owned = _safe_agent_id(tenant_key("alice", "conv1"))
    anon_attempts = [
        _safe_agent_id(tenant_key(None, "aliceconv1")),
        _safe_agent_id(tenant_key(None, "alice~conv1")),  # embeds the old separator directly
        _safe_agent_id(tenant_key(None, "u-alice-conv1")),  # embeds the new prefix directly
        _safe_agent_id(tenant_key(None, owned)),  # replays the sanitized owned key itself
    ]
    for attempt in anon_attempts:
        assert attempt != owned, (
            f"anonymous tenant_key output {attempt!r} collides with owned {owned!r} "
            "on disk after sanitization"
        )


def test_tenant_key_anonymous_output_never_starts_with_owned_prefix():
    """Boundary: the anonymous branch's prefix must be unconditional, not just
    true for the sampled cases above."""
    from reasoner.neuro.config import _safe_agent_id
    from reasoner.neuro.server import tenant_key

    for agent_id in [None, "", "u-", "u-x-y", "conv1", "0" * 200]:
        anon = tenant_key(None, agent_id)
        if anon is not None:
            assert not _safe_agent_id(anon).startswith("u-")


def test_tenant_key_owned_output_always_starts_with_owned_prefix():
    """Boundary: empty-string agent_id under a real owner must still resolve
    inside that owner's namespace, not silently fall through to anonymous."""
    from reasoner.neuro.config import _safe_agent_id
    from reasoner.neuro.server import tenant_key

    for agent_id in [None, "", "conv1"]:
        owned = tenant_key("alice", agent_id)
        assert _safe_agent_id(owned).startswith("u-alice-")


def test_no_regression_worker_restart_still_isolates_owner(tmp_path, monkeypatch):
    """D1 end-to-end no-regression guard, not just the key-derivation unit
    tests above: a fresh NeuroService pointed at the same data_dir (what a
    worker restart or TTL/LRU-evicted-then-reacquired tenant looks like in
    production) must not let an anonymous caller recall an owned tenant's
    memory by guessing a colliding agent_id.
    """
    import asyncio

    import reasoner.neuro.server as ns
    from reasoner.neuro.config import NeuroConfig, _apply_defaults

    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _FakeReasoning())
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)

    async def scenario():
        first_process = ns.NeuroService(cfg)
        await first_process.learn(
            prompt=PROMPT,
            response="alice's private board numbers",
            agent_id="conv1",
            owner="alice",
        )

        second_process = ns.NeuroService(cfg)  # simulates a restart/reload
        return await second_process.recall(
            PROMPT,
            agent_id="aliceconv1",
            owner=None,
            max_results=5,
        )

    leaked = asyncio.run(scenario())
    assert not leaked, f"anonymous caller recalled owned memory across a reload: {leaked}"


def test_steady_state_learn_does_not_block_the_event_loop(tmp_path, monkeypatch):
    """D2 proof-of-defect (regression guard).

    NeuroService.ingest() used to call SessionManager's *sync* ingest()
    instead of ingest_async() -- SessionManager's own docstring documents
    the contract this violated: "callers running in async contexts should
    use ingest_async() to avoid blocking the event loop." The sync path has
    no await points, so its open()/write()/flush() froze the entire worker's
    event loop for every concurrent request, not just neuro's, for the
    duration of the write.

    This isolates the steady-state case (session already open, so
    SessionManager._start_session()'s own separate sync write -- a distinct,
    narrower, not-yet-fixed defect -- doesn't confound the measurement).
    """
    import asyncio
    import builtins

    import reasoner.neuro.server as ns
    from reasoner.neuro.config import NeuroConfig, _apply_defaults

    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _FakeReasoning())
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    svc = ns.NeuroService(cfg)

    slow_seconds = 0.2
    real_open = builtins.open

    def slow_open(path, mode="r", *a, **k):
        f = real_open(path, mode, *a, **k)
        if "a" in mode and str(path).endswith(".jsonl"):
            real_write = f.write

            def patched_write(data):
                time.sleep(slow_seconds)
                return real_write(data)

            f.write = patched_write
        return f

    async def scenario():
        # Establish the session before slowing writes, so only the
        # steady-state per-message write is under test.
        await svc.learn(prompt="warmup", response="r", agent_id="conv1", owner="alice")

        ticks = []

        async def heartbeat():
            for _ in range(30):
                await asyncio.sleep(0.01)
                ticks.append(time.monotonic())

        monkeypatch.setattr(builtins, "open", slow_open)
        try:
            t0 = time.monotonic()
            hb = asyncio.create_task(heartbeat())
            await svc.learn(prompt="steady-state", response="r", agent_id="conv1", owner="alice")
            await asyncio.sleep(0.05)
            hb.cancel()
        finally:
            monkeypatch.setattr(builtins, "open", real_open)

        return [t for t in ticks if t - t0 < slow_seconds * 0.8]

    ticks_during_write = asyncio.run(scenario())
    assert ticks_during_write, (
        "event loop was starved during a steady-state learn() write -- "
        "NeuroService.ingest() is calling the sync SessionManager.ingest() again"
    )


def test_new_session_start_does_not_block_the_event_loop(tmp_path, monkeypatch):
    """D4 proof-of-defect (regression guard).

    SessionManager._start_session() writes the session-start header
    synchronously. ingest_async() already offloads the exchange write via
    asyncio.to_thread (see test_steady_state_learn_does_not_block_the_event_loop
    for that fix), but originally still called _start_session() directly --
    so a session's *first* message (new session, or a max_hot_entries
    rollover) still froze the event loop, just less often than every message.
    """
    import asyncio
    import builtins

    import reasoner.neuro.server as ns
    from reasoner.neuro.config import NeuroConfig, _apply_defaults

    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _FakeReasoning())
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    svc = ns.NeuroService(cfg)

    slow_seconds = 0.2
    real_open = builtins.open

    def slow_open(path, mode="r", *a, **k):
        f = real_open(path, mode, *a, **k)
        if "a" in mode and str(path).endswith(".jsonl"):
            real_write = f.write

            def patched_write(data):
                time.sleep(slow_seconds)
                return real_write(data)

            f.write = patched_write
        return f

    async def scenario():
        ticks = []

        async def heartbeat():
            for _ in range(30):
                await asyncio.sleep(0.01)
                ticks.append(time.monotonic())

        monkeypatch.setattr(builtins, "open", slow_open)
        try:
            t0 = time.monotonic()
            hb = asyncio.create_task(heartbeat())
            # No prior learn() call -- this is a brand-new session, so
            # ingest_async() must call _start_session() before the write.
            await svc.learn(prompt="first message", response="r", agent_id="conv1", owner="alice")
            await asyncio.sleep(0.05)
            hb.cancel()
        finally:
            monkeypatch.setattr(builtins, "open", real_open)

        return [t for t in ticks if t - t0 < slow_seconds * 0.8]

    ticks_during_write = asyncio.run(scenario())
    assert ticks_during_write, (
        "event loop was starved while starting a new session -- "
        "SessionManager._start_session() is being called synchronously from ingest_async() again"
    )


def test_first_touch_of_a_new_tenant_does_not_block_the_event_loop(tmp_path, monkeypatch):
    """D5 proof-of-defect (regression guard).

    TenantManager.get() used to construct L1Cache/L2Index inline: their
    __init__ calls a synchronous _load() (glob + read_text per cache file),
    and this ran while the manager held its single asyncio.Lock -- so the
    *first* recall/learn/audit for any not-yet-cached agent_id froze the
    whole worker's event loop for the read duration, not just this tenant's.
    """
    import asyncio
    import pathlib

    import reasoner.neuro.server as ns
    from reasoner.neuro.config import NeuroConfig, _apply_defaults

    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _FakeReasoning())
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    svc = ns.NeuroService(cfg)

    # Pre-seed a tenant's L1/L2 cache dirs so first-touch _load() has real
    # files to read (an empty cache dir loads in effectively zero time).
    owner, agent_id = "alice", "d5-tenant"
    tenant_dir = tmp_path / "agents" / f"u-{owner}-{agent_id}"
    l1_dir = tenant_dir / "cache" / "l1"
    l2_dir = tenant_dir / "cache" / "l2"
    l1_dir.mkdir(parents=True)
    l2_dir.mkdir(parents=True)
    # _FakeEmbedding.embed() produces 16-dim vectors -- match that shape so
    # l1.search()'s cosine_similarity() doesn't choke on a dimension mismatch.
    for i in range(6):
        (l1_dir / f"bundle{i}.json").write_text(
            json.dumps(
                {
                    "id": f"b{i}",
                    "content": "c",
                    "source": "s",
                    "embedding": [0.1] * 16,
                    "created_at": time.time(),
                }
            )
        )
    (l2_dir / "index.json").write_text(
        json.dumps(
            [
                {"id": f"e{i}", "content": "c", "source": "s", "embedding": [0.1] * 16}
                for i in range(20)
            ]
        )
    )

    slow_seconds = 0.05
    real_read_text = pathlib.Path.read_text

    def slow_read_text(self, *a, **k):
        time.sleep(slow_seconds)
        return real_read_text(self, *a, **k)

    async def scenario():
        ticks = []

        async def heartbeat():
            for _ in range(40):
                await asyncio.sleep(0.01)
                ticks.append(time.monotonic())

        monkeypatch.setattr(pathlib.Path, "read_text", slow_read_text)
        try:
            t0 = time.monotonic()
            hb = asyncio.create_task(heartbeat())
            # First touch of this agent_id: TenantManager.get() must build
            # L1Cache/L2Index (7 slowed reads total) before this returns.
            await svc.recall("anything", agent_id=agent_id, owner=owner, max_results=5)
            await asyncio.sleep(0.05)
            hb.cancel()
        finally:
            monkeypatch.setattr(pathlib.Path, "read_text", real_read_text)

        window = slow_seconds * 7 * 0.5
        return [t for t in ticks if t - t0 < window]

    ticks_during_load = asyncio.run(scenario())
    assert ticks_during_load, (
        "event loop was starved while a new tenant's L1/L2 caches loaded -- "
        "TenantManager.get() is constructing L1Cache/L2Index synchronously again"
    )


def test_recall_rejects_an_unknown_compression_level(client):
    """D6 proof-of-defect (regression guard).

    RecallRequest.compression used to be a bare `str`: an unrecognized value
    reached CompressionLevel(level) in smart_compress() with no upstream
    guard and no try/except around that call, turning a malformed client
    field into an unhandled 500 instead of a validation error.
    """
    resp = client.post(
        "/api/neuro/recall",
        json={"prompt": PROMPT, "agent_id": AGENT, "compression": "not-a-real-level"},
    )
    assert (
        resp.status_code == 422
    ), f"expected a validation error for an unknown compression level, got {resp.status_code}"


def test_recall_still_accepts_every_real_compression_level(client):
    for level in ("none", "minimal", "aggressive"):
        resp = client.post(
            "/api/neuro/recall",
            json={"prompt": PROMPT, "agent_id": AGENT, "compression": level},
        )
        assert resp.status_code == 200, f"compression={level!r} should be accepted"


def test_concurrent_learns_do_not_lose_l2_index_entries(tmp_path, monkeypatch):
    """D7 real concurrency load test (regression guard).

    L2Index.add() snapshots json.dumps(self.entries) on the calling coroutine
    (synchronous, no lock), then hands the write to a background thread via
    asyncio.to_thread. N concurrent /learn calls for one tenant therefore
    race N background-thread writes to the same index.json with nothing
    serializing them -- whichever thread's write finishes *last* wins, so a
    smaller, earlier snapshot can silently clobber a fuller, later one.

    This runs N genuinely concurrent NeuroService.ingest() calls (the exact
    code path /learn's handler delegates to) against one tenant. The
    snapshot each call captures is deterministic (self.entries.append() and
    json.dumps() are both synchronous with no await between them, so
    concurrent asyncio tasks interleave at await points, not mid-append) --
    but the *finish order* of the N background writes is genuinely raced by
    the OS thread pool. To make that race reproduce every run instead of
    flaking, the write of the smallest snapshot (index=1, i.e. the call that
    reached add() first) is forced to finish last, so it deterministically
    clobbers the rest -- proving the mechanism, not just its probability.
    """
    import asyncio
    import pathlib

    import reasoner.neuro.server as ns
    from reasoner.neuro.config import NeuroConfig, _apply_defaults

    monkeypatch.setattr(ns, "create_resilient_embedding", lambda c: _FakeEmbedding())
    monkeypatch.setattr(ns, "create_resilient_reasoning", lambda c: _FakeReasoning())
    cfg = _apply_defaults(NeuroConfig())
    cfg.data_dir = str(tmp_path)
    svc = ns.NeuroService(cfg)

    n_calls = 20
    owner, agent_id = "alice", "load-test-tenant"

    real_write_text = pathlib.Path.write_text

    def slow_write_text(self, data, *a, **k):
        if self.name == "index.json":
            try:
                snapshot_size = len(json.loads(data))
            except Exception:
                snapshot_size = n_calls
            # Smaller snapshots (earlier callers) sleep longer, so their
            # write finishes last and clobbers every fuller snapshot.
            time.sleep(max(0, n_calls - snapshot_size) * 0.01)
        return real_write_text(self, data, *a, **k)

    async def scenario():
        monkeypatch.setattr(pathlib.Path, "write_text", slow_write_text)
        try:
            await asyncio.gather(
                *(
                    svc.learn(
                        prompt=f"concurrent prompt {i}",
                        response=f"concurrent response {i}",
                        agent_id=agent_id,
                        owner=owner,
                    )
                    for i in range(n_calls)
                )
            )
        finally:
            monkeypatch.setattr(pathlib.Path, "write_text", real_write_text)

    asyncio.run(scenario())

    index_path = tmp_path / "agents" / f"u-{owner}-{agent_id}" / "cache" / "l2" / "index.json"
    entries = json.loads(index_path.read_text())
    assert len(entries) == n_calls, (
        f"expected all {n_calls} concurrent learns to survive in the L2 index, "
        f"found {len(entries)} -- concurrent writers clobbered each other"
    )
