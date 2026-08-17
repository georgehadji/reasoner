"""AnonymousTrialPolicy — security-remediation-plan.md Phase 2 item 3.

Anonymous runs skip the per-user credit ledger by design (no account to
charge); these tests pin the separate daily cap that bounds anonymous spend
instead, plus its fail-open posture when Valkey is unreachable.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from reasoner.application.services.anonymous_trial_policy import enforce_anonymous_trial_cap

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

    async def expire(self, key: str, ttl: int) -> None:
        if self.fail:
            raise ConnectionError("valkey unreachable")
        self.expiries[key] = ttl


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
