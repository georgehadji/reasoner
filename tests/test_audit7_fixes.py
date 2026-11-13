"""Regression tests for the audit-7 findings (fix/audit7) and audit-5 BIL-26.

One test per fix, each failing on the code before it. Billing helpers are
exercised against in-process fakes; nothing here calls a model.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from reasoner.api import run_admission
from reasoner.api.run_admission import FlatCharge, admit_flat_charge, close_flat_charge
from reasoner.domain.saas import User

pytestmark = pytest.mark.unit


def _user() -> User:
    return User(id=uuid4(), email="t@example.com", created_at=datetime.now(UTC))


def _request() -> SimpleNamespace:
    return SimpleNamespace(state=SimpleNamespace(), headers={}, client=None)


class _FakeSink:
    def __init__(self, reserve=None):
        self._reserve = reserve
        self.released: list[dict] = []
        self.unsettled: list[dict] = []

    async def reserve(self, **kwargs):
        if isinstance(self._reserve, Exception):
            raise self._reserve
        return self._reserve

    async def release(self, **kwargs):
        self.released.append(kwargs)

    async def record_unsettled(self, **kwargs):
        self.unsettled.append(kwargs)


@pytest.fixture
def sink(monkeypatch):
    holder = {"sink": _FakeSink(reserve=7)}
    monkeypatch.setattr(
        "reasoner.api.run_observability.CreditSink", lambda: holder["sink"]
    )
    monkeypatch.setattr("reasoner.api.dependencies._persistence_is_configured", lambda: True)
    monkeypatch.setattr("reasoner.api.dependencies._require_persistence", lambda name: None)
    return holder


# ── BIL-26: flat charges ────────────────────────────────────────────────────


async def test_flat_charge_holds_credits(sink):
    charge = await admit_flat_charge(_request(), user=_user(), cost_usd=0.007, kind="search")

    assert charge.credits == 7
    assert charge.reference_id.startswith("search:")
    assert not charge.reference_id.endswith(":reserve")  # the orphan sweeper must skip it


async def test_zero_balance_flat_charge_is_402(sink):
    from fastapi import HTTPException

    from reasoner.domain.credits import InsufficientCreditsError

    sink["sink"] = _FakeSink(reserve=InsufficientCreditsError(required=7, available=0))
    with pytest.raises(HTTPException) as exc:
        await admit_flat_charge(_request(), user=_user(), cost_usd=0.007, kind="search")
    assert exc.value.status_code == 402


async def test_unserved_flat_charge_is_released(sink):
    charge = FlatCharge("u1", "search:abc", 7, 0.007)

    await close_flat_charge(charge, served=False)

    assert sink["sink"].released == [
        {"user_id": "u1", "credits": 7, "reference_id": "search:abc:release"}
    ]


async def test_served_flat_charge_during_ledger_outage_is_recorded(sink):
    """Fail-open used to make the call free for good: no settlement follows."""
    sink["sink"] = _FakeSink(reserve=RuntimeError("ledger down"))
    charge = await admit_flat_charge(_request(), user=_user(), cost_usd=0.002, kind="image-preview")
    assert charge.unreserved and charge.credits == 0

    await close_flat_charge(charge, served=True)

    [record] = sink["sink"].unsettled
    assert record["cost_usd"] == 0.002 and record["preset"] == "image-preview"


async def test_anonymous_flat_charge_hits_trial_cap(monkeypatch):
    seen = {}

    async def cap(ip, cost):
        seen["cost"] = cost
        return None

    monkeypatch.setattr(run_admission, "enforce_anonymous_trial_cap", cap)
    monkeypatch.setattr(run_admission.settings, "ENABLE_LEGACY_API_KEY", True)
    monkeypatch.setattr("reasoner.api.client_ip.get_client_ip", lambda request: "1.2.3.4")

    charge = await admit_flat_charge(_request(), user=None, cost_usd=0.022, kind="smart-search")

    assert seen["cost"] == 0.022 and charge.user_id is None


class _FakeValkey:
    def __init__(self, fail: bool = False):
        self.counts: dict[str, int] = {}
        self.fail = fail

    async def incr(self, key):
        if self.fail:
            raise ConnectionError("valkey down")
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        return True


async def test_gate_free_until_daily_allowance(monkeypatch):
    from reasoner.core.constants_limits import GATE_FREE_CALLS_PER_DAY

    valkey = _FakeValkey()
    monkeypatch.setattr("reasoner.infrastructure.valkey.client.get_valkey_pool", lambda: valkey)

    results = [
        await run_admission.within_gate_allowance("u1")
        for _ in range(GATE_FREE_CALLS_PER_DAY + 1)
    ]

    assert all(results[:-1]) and results[-1] is False


async def test_gate_allowance_fails_open_without_valkey(monkeypatch):
    monkeypatch.setattr(
        "reasoner.infrastructure.valkey.client.get_valkey_pool", lambda: _FakeValkey(fail=True)
    )
    assert await run_admission.within_gate_allowance("u1") is True


# ── Finding 10: a timed-out release_unstarted is recorded ──────────────────


async def test_release_unstarted_timeout_records_unsettled(monkeypatch):
    from reasoner.application.services import run_metering

    class SlowSink:
        def __init__(self):
            self.unsettled: list[dict] = []

        async def true_up(self, **kwargs):
            await asyncio.sleep(10)

        async def record_unsettled(self, **kwargs):
            self.unsettled.append(kwargs)

        async def release_quota_slot(self, **kwargs):
            pass

    monkeypatch.setattr(run_metering, "SETTLE_TIMEOUT_SECONDS", 0.05)
    ctx = run_metering.RunContext(
        preset="p", reference_id="run:1", user_id="u1", reserved_credits=30, started=asyncio.Event()
    )
    sink = SlowSink()

    await run_metering.release_unstarted(sink, ctx)

    [record] = sink.unsettled
    assert record["reserved_credits"] == 30 and record["cost_usd"] == 0.0


# ── Finding 11: the API key cap holds under parallel creates ────────────────


async def test_key_cap_holds_under_parallel_creates():
    from reasoner.infrastructure.persistence.api_key_repo_memory import InMemoryApiKeyRepository

    repo = InMemoryApiKeyRepository()
    uid = str(uuid4())
    results = await asyncio.gather(
        *(
            repo.create(uid, f"k{i}", f"h{i}", f"p{i}", frozenset({"read"}), max_live=20)
            for i in range(25)
        )
    )

    assert sum(r is not None for r in results) == 20
    assert await repo.count_live_for_user(uid) == 20


# ── Finding 1: calculator exponent DoS ──────────────────────────────────────


@pytest.mark.parametrize(
    "expr",
    # The last one is the nested-power case asteval let through (2.9s holding the GIL).
    ["pow(3, 2000000)", "9**9**9", "10**200000", "(((9999**1000)**10)**10)**10"],
)
def test_calculator_rejects_huge_powers(expr):
    from reasoner.infrastructure.widgets.calculator import calculate_expression

    assert calculate_expression(expr)["valid"] is False


def test_calculator_keeps_normal_powers():
    from reasoner.infrastructure.widgets.calculator import calculate_expression

    assert calculate_expression("2**10")["result"] == 1024


# ── Finding 2: Stop reaches a run on another worker ─────────────────────────


async def test_stop_lookup_sees_a_run_on_another_worker():
    from reasoner.infrastructure.redis.run_state import RunStateManager

    class Redis:
        async def get(self, key):
            return "owner-1" if key.endswith("run-9") else None

    manager = RunStateManager()
    manager._redis = Redis()

    assert await manager.lookup("run-9") == (True, "owner-1")
    assert await manager.lookup("run-0") == (False, None)


async def test_remote_cancel_flag_reaches_the_local_run(monkeypatch):
    from reasoner.api.execution import pipeline

    calls = {"n": 0}

    async def is_cancelled(run_id):
        calls["n"] += 1
        return calls["n"] >= 2

    monkeypatch.setattr(pipeline, "_CANCEL_POLL_SECONDS", 0.01)
    monkeypatch.setattr(pipeline._run_store, "is_cancelled", is_cancelled)

    await asyncio.wait_for(pipeline._cancel_requested("r1", asyncio.Event()), timeout=1)

    assert calls["n"] == 2


# ── Finding 3: the response cache keys on attached files ────────────────────


def test_cache_key_differs_by_file_ids():
    from reasoner.api.cache import _cache_key
    from reasoner.api.schemas import RunRequest

    a = RunRequest(problem="Summarise the contract", file_ids=["a" * 32])
    b = RunRequest(problem="Summarise the contract", file_ids=["b" * 32])

    assert _cache_key(a, "u1") != _cache_key(b, "u1")


# ── Finding 9: augmentation cache keys on methods ───────────────────────────


def test_augmentation_cache_key_differs_by_methods():
    from reasoner.application.flows.augmentation import _make_cache_key

    assert _make_cache_key("q", ["a"]) != _make_cache_key("q", ["a", "b"])
    assert _make_cache_key("q", ["b", "a"]) == _make_cache_key("q", ["a", "b"])


# ── Finding 5: erase reaches the error log and the upload hash index ────────


async def test_error_log_export_and_erase(tmp_path):
    from reasoner.infrastructure.persistence.error_store import ErrorEntry, ErrorStore
    from reasoner.infrastructure.persistence.user_data_local import ErrorLogStore

    store = ErrorStore(tmp_path / "errors.db")
    await store.insert(ErrorEntry(level="error", source="api", message="boom", user_id="u1"))
    await store.insert(ErrorEntry(level="error", source="api", message="other", user_id="u2"))
    log = ErrorLogStore(lambda: store)

    exported = await log.export("u1")
    await log.erase("u1")

    assert [r["message"] for r in exported] == ["boom"]
    assert "traceback" not in exported[0]
    assert await log.export("u1") == []
    assert len(await log.export("u2")) == 1


def test_deleting_an_upload_forgets_its_hash(tmp_path, monkeypatch):
    from reasoner.infrastructure import uploader

    monkeypatch.setattr(uploader, "UPLOAD_DIR", tmp_path)
    uploader._record_hash("u1", "h1", "f1")
    uploader._record_hash("u1", "h2", "f2")

    uploader._forget_hash("u1", "f1")
    assert uploader._load_hash_index() == {"u1": {"h2": "f2"}}

    uploader._forget_hash("u1", "f2")
    assert uploader._load_hash_index() == {}


# ── Finding 12: the strict limiter is its own instance ──────────────────────


def test_strict_rate_limiter_is_not_the_shared_singleton():
    from reasoner.api import saas_router
    from reasoner.infrastructure.rate_limiter import get_rate_limiter

    assert saas_router._strict_rate_limiter is not get_rate_limiter()
    assert saas_router._strict_rate_limiter.config.requests_per_minute == 5
