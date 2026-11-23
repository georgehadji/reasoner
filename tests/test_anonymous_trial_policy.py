"""AnonymousTrialPolicy — security-remediation-plan.md Phase 2 item 3.

Anonymous runs skip the per-user credit ledger by design (no account to
charge); these tests pin the separate daily cap that bounds anonymous spend
instead, plus its fail-open posture when Valkey is unreachable.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from reasoner.application.services.anonymous_trial_policy import (
    enforce_anonymous_trial_cap,
    refund_anonymous_trial,
)

pytestmark = pytest.mark.unit


class _FakeValkey:
    """In-memory stand-in for the Valkey client's incrby/expire calls."""

    def __init__(self, fail: bool = False):
        self.store: dict[str, int] = {}
        self.expiries: dict[str, int] = {}
        self.fail = fail

    async def incrby(self, key: str, amount: int) -> int:
        if self.fail:
            raise ConnectionError("valkey unreachable")
        self.store[key] = self.store.get(key, 0) + amount
        return self.store[key]

    async def set(self, key: str, value: int, ex: int | None = None, nx: bool = False):
        if self.fail:
            raise ConnectionError("valkey unreachable")
        if nx and key in self.store:
            return None
        self.store[key] = value
        if ex is not None:
            self.expiries[key] = ex
        return True

    async def eval(self, script: str, numkeys: int, key: str, amount: int) -> int:
        """The refund script's contract: skip a missing key, floor at 0, keep the TTL."""
        if self.fail:
            raise ConnectionError("valkey unreachable")
        if key not in self.store:
            return -1
        self.store[key] = max(self.store[key] - int(amount), 0)
        return self.store[key]

    async def exists(self, key: str) -> int:
        # The key expires right after this answer: midnight UTC between two calls.
        present = int(key in self.store)
        self.store.pop(key, None)
        return present

    async def decrby(self, key: str, amount: int) -> int:
        self.store[key] = self.store.get(key, 0) - amount
        return self.store[key]


def _patch_valkey(monkeypatch: pytest.MonkeyPatch, client: _FakeValkey) -> None:
    import reasoner.infrastructure.valkey.client as valkey_client_module

    monkeypatch.setattr(valkey_client_module, "get_valkey_pool", lambda: client)


async def test_zero_estimate_never_touches_valkey(monkeypatch):
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)

    await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.0)

    assert client.store == {}


async def test_under_the_cap_is_allowed(monkeypatch):
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)

    # 0.01 USD = 10 credits, well under the default 50-credit cap.
    await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.01)

    assert list(client.store.values()) == [10]


async def test_crossing_the_cap_raises_429(monkeypatch):
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)

    # First call: 40 credits, still under the 50-credit default cap.
    await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.04)
    # Second call: another 40 credits, 80 total -- now over the cap.
    with pytest.raises(HTTPException) as exc_info:
        await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.04)

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["error"] == "Anonymous trial limit reached"


async def test_different_ips_have_independent_caps(monkeypatch):
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)

    await enforce_anonymous_trial_cap("1.1.1.1", estimated_cost_usd=0.04)
    # A different address must not be affected by the first one's spend.
    await enforce_anonymous_trial_cap("2.2.2.2", estimated_cost_usd=0.04)

    assert len(client.store) == 2


async def test_valkey_unreachable_fails_open(monkeypatch):
    client = _FakeValkey(fail=True)
    _patch_valkey(monkeypatch, client)

    # Must not raise -- no real money at risk for an anonymous caller, only
    # bounded abuse exposure the daily window already limits.
    await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=10.0)


async def test_every_counter_has_a_ttl_from_its_first_write(monkeypatch):
    """INCRBY then EXPIRE left a TTL-less key if the process died between them."""
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)

    await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.01)

    (key,) = client.store
    assert client.expiries[key] == 86_400


async def test_a_refused_attempt_does_not_stay_counted(monkeypatch):
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)
    await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.04)  # 40 of 50

    with pytest.raises(HTTPException):
        await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.04)

    assert list(client.store.values()) == [40]


async def test_refund_gives_the_counted_credits_back(monkeypatch):
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)
    charge = await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.04)

    await refund_anonymous_trial(charge)

    assert list(client.store.values()) == [0]


async def test_refund_ignores_an_expired_counter(monkeypatch):
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)
    charge = await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.04)
    client.store.clear()  # the day rolled over

    await refund_anonymous_trial(charge)

    assert client.store == {}  # no negative, TTL-less key


async def test_refund_across_midnight_never_creates_a_key(monkeypatch):
    """exists-then-decrby left a negative, TTL-less key when the day rolled over between them."""
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)
    charge = await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.04)

    await refund_anonymous_trial(charge)
    await refund_anonymous_trial(charge)  # a second refund must floor at 0, not go negative

    assert all(v >= 0 for v in client.store.values())
    client.store.clear()
    await refund_anonymous_trial(charge)
    assert client.store == {}


async def test_refund_never_raises(monkeypatch):
    client = _FakeValkey()
    _patch_valkey(monkeypatch, client)
    charge = await enforce_anonymous_trial_cap("1.2.3.4", estimated_cost_usd=0.04)
    client.fail = True

    await refund_anonymous_trial(charge)
    await refund_anonymous_trial(None)


# ── admission: a refused anonymous run is refunded ──────────────────


def _anon_request():
    from starlette.requests import Request

    return Request({"type": "http", "headers": [], "client": ("1.2.3.4", 1), "state": {}})


async def test_admit_run_refunds_an_anonymous_run_refused_after_the_cap(monkeypatch):
    from unittest.mock import AsyncMock, patch

    from reasoner.api import dependencies as deps
    from reasoner.api import idempotency_http
    from reasoner.api import run_admission as ra
    from reasoner.application.services.anonymous_trial_policy import AnonymousTrialCharge

    monkeypatch.setattr("reasoner.core.settings.settings.ALLOW_ANONYMOUS_RUNS", True, raising=False)
    charge = AnonymousTrialCharge(key="k", credits=10)
    refund = AsyncMock()
    with patch.object(ra, "enforce_anonymous_trial_cap", AsyncMock(return_value=charge)), \
         patch.object(ra, "refund_anonymous_trial", refund), \
         patch.object(deps, "check_preset_access_if_authenticated", AsyncMock()), \
         patch("reasoner.application.services.estimate_service.estimate_cost",
               AsyncMock(return_value={"estimated_cost_usd": 0.01})), \
         patch.object(idempotency_http, "register_run_or_error",
                      AsyncMock(side_effect=HTTPException(409))):
        with pytest.raises(HTTPException):
            await ra.admit_run(_anon_request(), user=None, problem="x", preset="p")

    refund.assert_awaited_once_with(charge)


async def test_a_stream_that_never_started_refunds_the_anonymous_charge():
    from unittest.mock import AsyncMock, patch

    from reasoner.api import run_admission as ra
    from reasoner.application.services.anonymous_trial_policy import AnonymousTrialCharge

    charge = AnonymousTrialCharge(key="k", credits=10)
    adm = ra.Admission(
        user_id=None, preset="p", reference_id="r", reserved_credits=0, anon_charge=charge
    )

    async def gone():
        return
        yield ""

    refund = AsyncMock()
    resp = ra.MeteredSSEResponse(gone(), adm)

    async def fake_super_call(self, scope, receive, send):
        return None

    with patch.object(ra, "refund_anonymous_trial", refund), \
         patch.object(ra.StreamingResponse, "__call__", fake_super_call):
        await resp({}, None, None)

    refund.assert_awaited_once_with(charge)
