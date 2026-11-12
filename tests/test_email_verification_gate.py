"""Step 3 of docs/plans/email-verification-2026-11-12.md: the observe/enforce gate.

Gated: the FREE monthly credit grant and API key creation. An account passes
when verified or created before the cutoff; otherwise it is counted, and only
refused in enforce mode.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from reasoner.api import dependencies as deps
from reasoner.application.services import email_verification as ev
from reasoner.application.services.email_verification import GatedFeature, email_gate_allows
from reasoner.core.ports import metrics_port
from reasoner.domain.saas import SubscriptionTier, User

pytestmark = pytest.mark.unit

OLD = datetime(2025, 1, 1, tzinfo=UTC)
CUTOFF = datetime(2026, 1, 1, tzinfo=UTC)
NEW = datetime(2026, 6, 1, tzinfo=UTC)


def _user(*, verified: bool, created: datetime = NEW) -> User:
    return User(id=uuid4(), email="u@t.local", email_verified=verified, created_at=created)


@pytest.fixture
def counted():
    seen: list[tuple[str, str]] = []
    previous = metrics_port._UNVERIFIED_ACCESS_COUNTER
    metrics_port.set_unverified_access_counter(lambda *a: seen.append(a))
    yield seen
    metrics_port.set_unverified_access_counter(previous)


@pytest.fixture
def mode(monkeypatch):
    def set_mode(value: str, cutoff: str | None = None) -> None:
        monkeypatch.setattr(deps.settings, "EMAIL_VERIFICATION_MODE", value)
        monkeypatch.setattr(deps.settings, "EMAIL_VERIFICATION_CUTOFF", cutoff)

    return set_mode


# ── The policy ───────────────────────────────────────────────────────────────

def test_verified_passes_uncounted(counted):
    assert email_gate_allows(_user(verified=True), GatedFeature.FREE_CREDITS, mode="enforce")
    assert counted == []


def test_unverified_in_observe_is_allowed_and_counted(counted):
    assert email_gate_allows(
        _user(verified=False), GatedFeature.API_KEY_CREATE, mode="observe", cutoff=CUTOFF
    )
    assert counted == [("api_key_create", "allowed")]


def test_unverified_in_enforce_is_denied_and_counted(counted):
    assert not email_gate_allows(
        _user(verified=False), GatedFeature.FREE_CREDITS, mode="enforce", cutoff=CUTOFF
    )
    assert counted == [("free_credits", "denied")]


def test_account_before_the_cutoff_is_grandfathered(counted):
    user = _user(verified=False, created=OLD)
    assert email_gate_allows(user, GatedFeature.FREE_CREDITS, mode="enforce", cutoff=CUTOFF)
    assert counted == []


def test_settings_drive_the_defaults(mode, counted):
    mode("enforce", "2026-01-01T00:00:00Z")
    assert email_gate_allows(_user(verified=False, created=OLD), GatedFeature.FREE_CREDITS)
    assert not email_gate_allows(_user(verified=False), GatedFeature.FREE_CREDITS)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-01-01T00:00:00Z", CUTOFF),
        ("2026-01-01T00:00:00", CUTOFF),  # naive -> UTC
        ("not a date", None),  # grandfathers nobody, logged
        ("", None),
        (None, None),
    ],
)
def test_parse_cutoff(raw, expected):
    assert ev.parse_cutoff(raw) == expected


# ── The FREE monthly grant ───────────────────────────────────────────────────

def test_paid_tier_grant_is_never_gated(mode, counted):
    mode("enforce")
    assert deps.allowance_permitted(_user(verified=False), SubscriptionTier.PRO)
    assert counted == []


async def test_enforce_withholds_the_free_grant_until_verified(mode, monkeypatch):
    mode("enforce")
    grants: list[str] = []

    class _Service:
        async def ensure_monthly_allowance(self, user_id, tier):
            grants.append(user_id)

    async def free(_user_id):
        return SubscriptionTier.FREE

    monkeypatch.setattr(deps, "_resolve_user_tier", free)
    deps._allowance_checked.clear()
    user = _user(verified=False)
    await deps._top_up_allowance(_Service(), user)
    assert grants == []
    # Not cached as done: the same period grants once the email is verified.
    from dataclasses import replace

    await deps._top_up_allowance(_Service(), replace(user, email_verified=True))
    assert grants == [str(user.id)]


async def test_observe_still_grants(mode, monkeypatch, counted):
    mode("observe")
    grants: list[str] = []

    class _Service:
        async def ensure_monthly_allowance(self, user_id, tier):
            grants.append(user_id)

    async def free(_user_id):
        return SubscriptionTier.FREE

    monkeypatch.setattr(deps, "_resolve_user_tier", free)
    deps._allowance_checked.clear()
    await deps._top_up_allowance(_Service(), _user(verified=False))
    assert len(grants) == 1
    assert counted == [("free_credits", "allowed")]


# ── API key creation ─────────────────────────────────────────────────────────

async def test_enforce_refuses_api_key_creation(mode):
    from reasoner.api.routes.account_keys import CreateKeyRequest, create_api_key

    mode("enforce")
    with pytest.raises(HTTPException) as exc:
        await create_api_key(CreateKeyRequest(name="k"), _user(verified=False))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "email_unverified"


# ── API key callers keep the row's status ────────────────────────────────────

async def test_user_loaded_from_the_row_keeps_verified_and_signup_time(monkeypatch):
    uid = uuid4()
    row = {
        "id": uid, "email": "u@t.local", "display_name": None, "auth_provider": None,
        "avatar_url": None, "created_at": OLD, "email_verified": True,
    }

    async def fetchrow(*_a):
        return row

    async def pool():
        return SimpleNamespace(fetchrow=fetchrow)

    monkeypatch.setattr(deps, "_get_provision_pool", pool)
    user = await deps._load_user_by_id(uid)
    assert (user.email_verified, user.created_at) == (True, OLD)
