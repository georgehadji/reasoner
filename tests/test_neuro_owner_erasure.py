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

# Owners are str(user.id) -- always a canonical UUID. erase_owner refuses
# anything else (see its docstring), so the fixtures use real UUIDs.
USER_X = "aaaaaaaa-1111-4111-8111-111111111111"
USER_Y = "bbbbbbbb-2222-4222-8222-222222222222"


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
    await _learn(service, USER_X, "conv1", "x's secret plan A", "response A")
    await _learn(service, USER_X, "conv2", "x's secret plan B", "response B")
    await _learn(service, USER_Y, "conv1", "y's unrelated chat", "y's response")

    agents_dir = Path(tmp_path) / "agents"
    before = {p.name for p in agents_dir.iterdir()}
    assert sum(1 for n in before if n.startswith(f"u-{USER_X}-")) == 2
    assert sum(1 for n in before if n.startswith(f"u-{USER_Y}-")) == 1

    result = await service.erase_owner(USER_X)

    assert result["erased"] is True
    assert result["dirs_removed"] == 2
    assert result["tenants_evicted"] == 2
    assert result["error"] is None

    after = {p.name for p in agents_dir.iterdir()}
    assert not any(n.startswith(f"u-{USER_X}-") for n in after), f"user-x data survived: {after}"
    assert any(n.startswith(f"u-{USER_Y}-") for n in after), "user-y's data was wrongly removed"

    # In-process cache: x's tenants must be gone, y's must still be live.
    assert not any(k.startswith(f"u-{USER_X}-") for k in service.tenants.active_tenants)
    assert tenant_key(USER_Y, "conv1") in service.tenants.active_tenants

    # x's memory is actually unrecoverable, not just relocated.
    x_recall = await service.recall("x's secret plan A", agent_id="conv1", owner=USER_X)
    assert x_recall == [], f"user-x memory is still recallable after erasure: {x_recall}"

    # y is unaffected end to end.
    y_recall = await service.recall("y's unrelated chat", agent_id="conv1", owner=USER_Y)
    assert any("y's unrelated chat" in c["content"] for c in y_recall), (
        "erasing user-x must not touch user-y's memory"
    )


@pytest.mark.asyncio
async def test_erase_owner_with_no_data_is_still_a_success(service):
    """A user who never used Neuro has nothing to remove -- that is a
    successful erasure, not a failure (mirrors get_agent_data_dir's existing
    'nothing stored' contract)."""
    result = await service.erase_owner("cccccccc-3333-4333-8333-333333333333")
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
    await _learn(service, USER_X, "shared-conv-id", "x's chat", "x response")

    result = await service.erase_owner(USER_X)
    assert result["dirs_removed"] == 1

    agents_dir = Path(tmp_path) / "agents"
    remaining = {p.name for p in agents_dir.iterdir()}
    assert any(n.startswith("a-") for n in remaining), "anonymous tenant was wrongly removed"
    assert not any(n.startswith(f"u-{USER_X}-") for n in remaining)


def test_erase_owner_prefix_matches_the_storage_sanitizer(tmp_path):
    """The prefix erase_owner searches for must be derived the same way the
    storage layer derives tenant directory names, or erasure silently misses
    real data. This is a static proof, independent of the async fixture."""
    from reasoner.neuro.server import _owned_prefix

    owner = "018f3c9a-7b2e-4d1f-9c8a-1a2b3c4d5e6f"
    full_key = tenant_key(owner, "some-conversation")
    assert _safe_agent_id(full_key).startswith(_safe_agent_id(_owned_prefix(owner)))


# ── Review follow-up: races, tombstone, owner validation, symlinks ──────────


def _agent_dirs(tmp_path) -> set[str]:
    agents = Path(tmp_path) / "agents"
    return {p.name for p in agents.iterdir()} if agents.exists() else set()


@pytest.mark.asyncio
async def test_tenant_recreated_after_first_eviction_is_evicted_again(service, monkeypatch):
    """A tenant re-created between the eviction and the delete (concurrent
    recall/learn loading from still-present files) must not survive erasure
    and keep serving erased data from memory."""
    await _learn(service, USER_X, "conv1", "x's secret", "x response")
    key = tenant_key(USER_X, "conv1")

    real_evict = service.tenants.evict_prefix
    calls = 0

    async def evict_then_resurrect(prefix):
        nonlocal calls
        calls += 1
        evicted = await real_evict(prefix)
        if calls == 1:
            # Simulate the racing request: tenant back in memory, built from
            # files the delete loop has not removed yet.
            service.tenants._tenants[key] = {"l1": object(), "l2": object()}
            service.tenants._last_access[key] = 0.0
        return evicted

    monkeypatch.setattr(service.tenants, "evict_prefix", evict_then_resurrect)

    result = await service.erase_owner(USER_X)

    assert result["erased"] is True
    assert calls == 2, "eviction must run again after the delete loop"
    assert key not in service.tenants.active_tenants


@pytest.mark.asyncio
async def test_get_during_erasure_waits_and_finds_nothing(service, tmp_path, monkeypatch):
    """get() for an owner being erased must wait for the erasure instead of
    re-creating the tenant from disk files that are not yet deleted. (recall
    itself short-circuits to empty for such an owner, see below.)"""
    import asyncio

    await _learn(service, USER_X, "conv1", "x's secret plan", "x response")

    in_delete = asyncio.Event()
    release = asyncio.Event()
    real_remove = service._remove_owner_dirs

    async def paused_remove(prefix, result):
        in_delete.set()
        await release.wait()
        return await real_remove(prefix, result)

    monkeypatch.setattr(service, "_remove_owner_dirs", paused_remove)

    erase = asyncio.create_task(service.erase_owner(USER_X))
    await in_delete.wait()
    getter = asyncio.create_task(service.tenants.get(tenant_key(USER_X, "conv1")))
    await asyncio.sleep(0.05)
    assert not getter.done(), "get() must wait while the owner is being erased"

    release.set()
    result = await erase
    tenant = await asyncio.wait_for(getter, timeout=5)

    assert result["erased"] is True
    assert tenant["l1"].search is not None
    assert tenant["sessions"].search_hot("x's secret plan", max_results=3) == []


@pytest.mark.asyncio
async def test_learn_for_just_erased_owner_is_dropped_with_warning(service, tmp_path, caplog):
    """A pipeline run already in flight when the user is erased finishes and
    calls learn(owner=...): that write must not re-create their tenant."""
    await _learn(service, USER_X, "conv1", "before", "r")
    await service.erase_owner(USER_X)
    assert not any(n.startswith(f"u-{USER_X}-") for n in _agent_dirs(tmp_path))

    with caplog.at_level("WARNING", logger="neuro.api"):
        resp = await service.ingest(
            LearnRequest(prompt="late", response="late run output", agent_id="conv1", metadata={}),
            owner=USER_X,
        )

    assert resp.status == "dropped_erased"
    assert not any(n.startswith(f"u-{USER_X}-") for n in _agent_dirs(tmp_path))
    assert tenant_key(USER_X, "conv1") not in service.tenants.active_tenants
    assert any("erased owner" in r.getMessage() for r in caplog.records)

    # Other owners are unaffected.
    await _learn(service, USER_Y, "conv1", "y chat", "y response")
    assert any(n.startswith(f"u-{USER_Y}-") for n in _agent_dirs(tmp_path))


@pytest.mark.asyncio
async def test_erase_tombstone_expires(service, tmp_path):
    await service.erase_owner(USER_X)
    prefix = f"u-{USER_X}-"
    assert service.tenants.is_erased(f"{prefix}conv1")

    service.tenants._erased_until[prefix] -= service.tenants.IDLE_TTL_SECONDS + 1

    assert not service.tenants.is_erased(f"{prefix}conv1")
    await _learn(service, USER_X, "conv1", "back again", "ok")
    assert any(n.startswith(prefix) for n in _agent_dirs(tmp_path))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_owner",
    ["", "user", "user-x", "alice-bob", "../x", "a/b", USER_X.upper(), USER_X + "-extra"],
)
async def test_erase_owner_rejects_non_canonical_owner(service, tmp_path, bad_owner):
    """tenant_key("alice","bob-x") == tenant_key("alice-bob","x"): a free-form
    owner makes the prefix ambiguous, so erasing "user" would delete
    "user-x"'s data. Refuse anything that is not a canonical UUID."""
    await _learn(service, "user-x", "conv", "other owner's data", "r")
    before = _agent_dirs(tmp_path)

    result = await service.erase_owner(bad_owner)

    assert result["erased"] is False
    assert result["error"]
    assert result["dirs_removed"] == 0
    assert _agent_dirs(tmp_path) == before, "a rejected erasure must not delete anything"
    assert tenant_key("user-x", "conv") in service.tenants.active_tenants


@pytest.mark.asyncio
async def test_erase_owner_does_not_touch_owner_differing_in_last_char(service, tmp_path):
    other = USER_X[:-1] + "2"
    await _learn(service, USER_X, "conv", "x", "r")
    await _learn(service, other, "conv", "other", "r")

    result = await service.erase_owner(USER_X)

    assert result["erased"] is True and result["dirs_removed"] == 1
    assert _agent_dirs(tmp_path) == {f"u-{other}-conv"}


@pytest.mark.asyncio
async def test_erase_owner_unlinks_symlinked_tenant_dir(service, tmp_path):
    agents = Path(tmp_path) / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    target = Path(tmp_path) / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("not ours")
    link = agents / f"u-{USER_X}-linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this platform")

    result = await service.erase_owner(USER_X)

    assert result["erased"] is True and result["error"] is None
    assert result["dirs_removed"] == 1
    assert not link.is_symlink()
    assert (target / "keep.txt").exists(), "the symlink target must not be followed"


class _SlowEmbedding(_FakeEmbedding):
    """embed() parks until released, so a test can erase while ingest awaits it."""

    def __init__(self):
        import asyncio

        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, text: str) -> list[float]:
        self.entered.set()
        await self.release.wait()
        return await super().embed(text)


@pytest.mark.asyncio
async def test_learn_erased_while_embedding_is_dropped_before_indexing(service, tmp_path):
    """The tombstone is also checked after the slow embed(): an erasure that
    completes while ingest awaits the embedding must stop the L1/L2 write."""
    import asyncio

    slow = _SlowEmbedding()
    service.embedder = slow
    task = asyncio.create_task(
        service.ingest(
            LearnRequest(prompt="p", response="r", agent_id="conv1", metadata={}), owner=USER_X
        )
    )
    await asyncio.wait_for(slow.entered.wait(), timeout=5)

    result = await service.erase_owner(USER_X)
    assert result["erased"] is True
    slow.release.set()
    resp = await asyncio.wait_for(task, timeout=5)

    assert resp.status == "dropped_erased"
    assert not any(n.startswith(f"u-{USER_X}-") for n in _agent_dirs(tmp_path)), (
        "L1/L2 write re-created the erased owner's directory"
    )


@pytest.mark.asyncio
async def test_failed_erasure_still_blocks_writes(service, tmp_path, monkeypatch):
    """Deliberate: after a failed erasure data is still on disk, so new writes
    stay blocked for the tombstone window rather than adding to it."""
    await _learn(service, USER_X, "conv1", "x data", "r")

    async def failing_remove(prefix, result):
        return ["u-x-conv1: permission denied"]

    monkeypatch.setattr(service, "_remove_owner_dirs", failing_remove)
    result = await service.erase_owner(USER_X)

    assert result["erased"] is False
    resp = await service.ingest(
        LearnRequest(prompt="p", response="r", agent_id="conv1", metadata={}), owner=USER_X
    )
    assert resp.status == "dropped_erased"


@pytest.mark.asyncio
async def test_cancelled_erasure_releases_waiters_and_keeps_tombstone(service, monkeypatch):
    import asyncio

    started = asyncio.Event()

    async def hang(prefix, result):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(service, "_remove_owner_dirs", hang)
    erase = asyncio.create_task(service.erase_owner(USER_X))
    await started.wait()
    getter = asyncio.create_task(service.tenants.get(tenant_key(USER_X, "conv1")))
    await asyncio.sleep(0.05)
    assert not getter.done()

    erase.cancel()
    with pytest.raises(asyncio.CancelledError):
        await erase

    await asyncio.wait_for(getter, timeout=5)  # not stuck behind a dead erase
    assert not service.tenants._erasing
    assert service.tenants.is_erased(tenant_key(USER_X, "conv1"))


@pytest.mark.asyncio
async def test_recall_and_list_after_erasure_return_empty_without_recreating_dirs(
    service, tmp_path
):
    await _learn(service, USER_X, "conv1", "x data", "r")
    await service.erase_owner(USER_X)

    assert await service.recall("x data", agent_id="conv1", owner=USER_X) == []
    assert await service.list_sessions(agent_id="conv1", owner=USER_X) == {
        "entries": [],
        "total": 0,
    }
    assert not any(n.startswith(f"u-{USER_X}-") for n in _agent_dirs(tmp_path))


@pytest.mark.asyncio
async def test_neuro_maintenance_skips_erased_tenant_dirs(service, tmp_path, monkeypatch):
    """api/cron.py opens its own SessionManager per agents/* directory; it must
    not archive (write warm summaries into) an erased owner's directory."""
    import reasoner.neuro.config as ncfg
    import reasoner.neuro.sessions as nsess
    from reasoner.api.cron import run_neuro_maintenance

    agents = Path(tmp_path) / "agents"
    erased_dir = agents / f"u-{USER_X}-conv1"
    live_dir = agents / f"u-{USER_Y}-conv1"
    erased_dir.mkdir(parents=True)
    live_dir.mkdir(parents=True)
    await service.erase_owner(USER_X)  # tombstones; recreate the dir afterwards
    erased_dir.mkdir(parents=True)

    touched: list[str] = []

    class _RecordingSessions:
        def __init__(self, path, cfg):
            touched.append(Path(path).name)

        async def archive_hot_sessions(self):
            return []

        def archive_warm_to_cold(self):
            return []

    monkeypatch.setattr(ncfg, "load_config", lambda: service.config)
    monkeypatch.setattr(ns, "get_neuro_service", lambda: service)
    monkeypatch.setattr(nsess, "SessionManager", _RecordingSessions)

    await run_neuro_maintenance()

    assert touched == [f"u-{USER_Y}-conv1"]
