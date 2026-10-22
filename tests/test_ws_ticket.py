"""WebSocket connection tickets — security-remediation-plan.md Phase 3 item 2.

Replaces the query-string ?token= a WebSocket used to carry a real access
token in. These tests pin: single redemption succeeds, replay is rejected,
expiry is enforced, tampering is rejected, and a Valkey outage fails closed
(unlike the anonymous trial cap, this gates authentication itself).
"""

from __future__ import annotations

import pytest

from reasoner.application.services import ws_ticket
from reasoner.core.settings import settings

pytestmark = pytest.mark.unit


class _FakeValkey:
    def __init__(self, fail: bool = False):
        self.store: dict[str, str] = {}
        self.fail = fail

    async def set(
        self, key: str, value: str, nx: bool = False, ex: int | None = None
    ) -> bool | None:
        if self.fail:
            raise ConnectionError("valkey unreachable")
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


def _patch_valkey(monkeypatch: pytest.MonkeyPatch, client: _FakeValkey) -> None:
    import reasoner.infrastructure.valkey.client as valkey_client_module

    monkeypatch.setattr(valkey_client_module, "get_valkey_pool", lambda: client)


@pytest.fixture(autouse=True)
def _csrf_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "CSRF_SECRET", "test-secret-do-not-reuse")


async def test_issue_then_redeem_returns_the_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_valkey(monkeypatch, _FakeValkey())

    ticket = ws_ticket.issue_ticket("user-42")
    redeemed = await ws_ticket.redeem_ticket(ticket)

    assert redeemed == "user-42"


async def test_redeeming_twice_fails_the_second_time(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_valkey(monkeypatch, _FakeValkey())

    ticket = ws_ticket.issue_ticket("user-42")
    first = await ws_ticket.redeem_ticket(ticket)
    second = await ws_ticket.redeem_ticket(ticket)

    assert first == "user-42"
    assert second is None


async def test_expired_ticket_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_valkey(monkeypatch, _FakeValkey())
    monkeypatch.setattr(settings, "WS_TICKET_TTL_SECONDS", -1)

    ticket = ws_ticket.issue_ticket("user-42")  # already expired the moment it's issued

    assert await ws_ticket.redeem_ticket(ticket) is None


async def test_tampered_signature_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_valkey(monkeypatch, _FakeValkey())

    ticket = ws_ticket.issue_ticket("user-42")
    tampered = ticket[:-4] + "0000"

    assert await ws_ticket.redeem_ticket(tampered) is None


async def test_tampered_user_id_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Changing the embedded user_id without a matching signature must not
    let an attacker redeem another user's ticket as their own identity."""
    _patch_valkey(monkeypatch, _FakeValkey())

    ticket = ws_ticket.issue_ticket("user-42")
    forged = ticket.replace("user-42", "user-attacker", 1)

    assert await ws_ticket.redeem_ticket(forged) is None


async def test_dev_fallback_secret_is_stable_across_issue_and_redeem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without CSRF_SECRET (dev/CI, enforcement off) the fallback key was drawn
    fresh on every call, so a ticket never verified against its own issuer."""
    _patch_valkey(monkeypatch, _FakeValkey())
    monkeypatch.setattr(settings, "CSRF_SECRET", "")
    monkeypatch.setattr(settings, "CSRF_ENFORCE_BACKEND", False)

    ticket = ws_ticket.issue_ticket("user-42")

    assert await ws_ticket.redeem_ticket(ticket) == "user-42"


def test_ticket_is_a_valid_websocket_subprotocol() -> None:
    """The browser sends the ticket as `new WebSocket(url, [ticket])`, and a
    subprotocol must be an RFC 7230 token. The old ':' separator is not a
    token character, so every browser threw SyntaxError before connecting."""
    tchar = set("!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")

    ticket = ws_ticket.issue_ticket("00000000-0000-4000-8000-000000000de1")

    assert ticket and set(ticket) <= tchar, set(ticket) - tchar


@pytest.mark.parametrize("garbage", ["", "not-a-ticket", "a.b", "a.b.c", "a:b:c:d"])
async def test_malformed_tickets_are_rejected(
    monkeypatch: pytest.MonkeyPatch, garbage: str
) -> None:
    _patch_valkey(monkeypatch, _FakeValkey())

    assert await ws_ticket.redeem_ticket(garbage) is None


async def test_valkey_unreachable_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unlike anonymous_trial_policy (an abuse counter), this gates
    authentication -- "can't verify single-use" must mean reject."""
    _patch_valkey(monkeypatch, _FakeValkey(fail=True))

    ticket = ws_ticket.issue_ticket("user-42")

    assert await ws_ticket.redeem_ticket(ticket) is None
