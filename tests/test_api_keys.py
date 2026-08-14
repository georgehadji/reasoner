"""Tests for the API key domain and ApiKeyService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from reasoner.application.services.api_key_service import (
    ApiKeyLimitError,
    ApiKeyService,
    MAX_EXPIRY_DAYS,
)
from reasoner.domain.api_keys import (
    ASSIGNABLE_SCOPES,
    DEFAULT_SCOPES,
    MAX_KEYS_PER_USER,
    ApiKey,
    InvalidScopeError,
    generate_key,
    hash_key,
    looks_like_api_key,
    normalize_scopes,
    verify_key,
)
from reasoner.infrastructure.persistence.api_key_repo_memory import InMemoryApiKeyRepository


@pytest.fixture
def user_id() -> str:
    return str(uuid4())


@pytest.fixture
def service() -> ApiKeyService:
    return ApiKeyService(InMemoryApiKeyRepository())


# ── Domain: generation and verification ─────────────────────────────


@pytest.mark.unit
def test_generated_keys_are_namespaced_and_unique():
    first = generate_key()
    second = generate_key()

    assert first.plaintext.startswith("rsn_live_")
    assert first.plaintext != second.plaintext
    assert first.key_hash != second.key_hash


@pytest.mark.unit
def test_plaintext_is_never_derivable_from_the_stored_hash():
    minted = generate_key()

    assert minted.plaintext not in minted.key_hash
    assert minted.key_hash == hash_key(minted.plaintext)
    assert len(minted.key_hash) == 64


@pytest.mark.unit
def test_prefix_is_a_display_sample_not_the_secret():
    minted = generate_key()

    assert minted.plaintext.startswith(minted.key_prefix)
    assert len(minted.key_prefix) < len(minted.plaintext)


@pytest.mark.unit
def test_verify_key_accepts_only_the_original_secret():
    minted = generate_key()

    assert verify_key(minted.plaintext, minted.key_hash) is True
    assert verify_key(minted.plaintext + "x", minted.key_hash) is False
    assert verify_key("rsn_live_wrong", minted.key_hash) is False


@pytest.mark.unit
@pytest.mark.parametrize(
    "token,expected",
    [
        ("rsn_live_abc123", True),
        ("rsn_test_abc123", True),
        ("rsn_staging_abc123", False),
        ("rsn_live_", False),
        ("eyJhbGciOi.eyJzdWIi.sig", False),
        ("", False),
    ],
)
def test_api_key_shape_detection(token: str, expected: bool):
    assert looks_like_api_key(token) is expected


# ── Domain: scopes ──────────────────────────────────────────────────


@pytest.mark.unit
def test_absent_scopes_default_to_read_only():
    assert normalize_scopes(None) == DEFAULT_SCOPES
    assert "write" not in DEFAULT_SCOPES


@pytest.mark.unit
def test_admin_scopes_can_never_be_assigned_to_a_user_key():
    # A key must not be able to escalate beyond the account behind it.
    assert "admin" not in ASSIGNABLE_SCOPES
    with pytest.raises(InvalidScopeError):
        normalize_scopes({"admin"})
    with pytest.raises(InvalidScopeError):
        normalize_scopes({"read", "key:manage"})


@pytest.mark.unit
def test_valid_scopes_are_accepted():
    assert normalize_scopes({"read", "write"}) == frozenset({"read", "write"})


# ── Domain: lifecycle predicates ────────────────────────────────────


def _key(**overrides) -> ApiKey:
    base = dict(
        id=uuid4(),
        user_id=uuid4(),
        name="test",
        key_hash="0" * 64,
        key_prefix="rsn_live_00000000",
        scopes=frozenset({"read"}),
    )
    return ApiKey(**{**base, **overrides})


@pytest.mark.unit
def test_a_revoked_key_is_unusable():
    assert _key(revoked_at=datetime.now(timezone.utc)).is_usable() is False


@pytest.mark.unit
def test_an_expired_key_is_unusable():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    assert _key(expires_at=past).is_usable() is False


@pytest.mark.unit
def test_a_fresh_key_is_usable():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert _key(expires_at=future).is_usable() is True
    assert _key().is_usable() is True


@pytest.mark.unit
def test_serialised_key_never_contains_the_hash():
    payload = _key().to_dict()

    assert "key_hash" not in payload
    assert "key" not in payload
    assert payload["key_prefix"].startswith("rsn_live_")


# ── Service ─────────────────────────────────────────────────────────


@pytest.mark.unit
async def test_create_returns_the_plaintext_exactly_once(service: ApiKeyService, user_id: str):
    minted = await service.create(user_id, name="prod")

    assert minted.plaintext.startswith("rsn_live_")

    listed = await service.list_keys(user_id)
    assert len(listed) == 1
    assert minted.plaintext not in listed[0].to_dict().values()


@pytest.mark.unit
async def test_created_key_authenticates(service: ApiKeyService, user_id: str):
    minted = await service.create(user_id, name="prod", scopes={"read", "write"})

    resolved = await service.authenticate(minted.plaintext)

    assert resolved is not None
    assert str(resolved.user_id) == user_id
    assert resolved.scopes == frozenset({"read", "write"})


@pytest.mark.unit
async def test_unknown_key_does_not_authenticate(service: ApiKeyService):
    assert await service.authenticate("rsn_live_definitelynotreal") is None


@pytest.mark.unit
async def test_revoked_key_stops_authenticating(service: ApiKeyService, user_id: str):
    minted = await service.create(user_id, name="leaked")

    revoked = await service.revoke(user_id, minted.key.id)

    assert revoked is True
    assert await service.authenticate(minted.plaintext) is None


@pytest.mark.unit
async def test_expired_key_stops_authenticating(service: ApiKeyService, user_id: str):
    repo = InMemoryApiKeyRepository()
    expiring = ApiKeyService(repo)
    minted = generate_key()
    await repo.create(
        user_id=user_id,
        name="stale",
        key_hash=minted.key_hash,
        key_prefix=minted.key_prefix,
        scopes=frozenset({"read"}),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )

    assert await expiring.authenticate(minted.plaintext) is None


@pytest.mark.unit
async def test_one_user_cannot_revoke_another_users_key(service: ApiKeyService, user_id: str):
    minted = await service.create(user_id, name="victim")
    attacker = str(uuid4())

    revoked = await service.revoke(attacker, minted.key.id)

    assert revoked is False
    assert await service.authenticate(minted.plaintext) is not None


@pytest.mark.unit
async def test_revoking_twice_reports_no_change(service: ApiKeyService, user_id: str):
    minted = await service.create(user_id, name="once")

    assert await service.revoke(user_id, minted.key.id) is True
    assert await service.revoke(user_id, minted.key.id) is False


@pytest.mark.unit
async def test_revoked_keys_are_hidden_unless_requested(service: ApiKeyService, user_id: str):
    minted = await service.create(user_id, name="gone")
    await service.revoke(user_id, minted.key.id)

    assert await service.list_keys(user_id) == []
    assert len(await service.list_keys(user_id, include_revoked=True)) == 1


@pytest.mark.unit
async def test_keys_are_scoped_to_their_owner(service: ApiKeyService, user_id: str):
    other = str(uuid4())
    await service.create(user_id, name="mine")
    await service.create(other, name="theirs")

    mine = await service.list_keys(user_id)

    assert len(mine) == 1
    assert mine[0].name == "mine"


@pytest.mark.unit
async def test_key_count_is_capped_per_user(service: ApiKeyService, user_id: str):
    for i in range(MAX_KEYS_PER_USER):
        await service.create(user_id, name=f"key-{i}")

    with pytest.raises(ApiKeyLimitError):
        await service.create(user_id, name="one-too-many")


@pytest.mark.unit
async def test_revoking_frees_a_slot(service: ApiKeyService, user_id: str):
    created = [await service.create(user_id, name=f"key-{i}") for i in range(MAX_KEYS_PER_USER)]

    await service.revoke(user_id, created[0].key.id)

    assert await service.create(user_id, name="replacement") is not None


@pytest.mark.unit
@pytest.mark.parametrize("name", ["", "   "])
async def test_blank_names_are_rejected(service: ApiKeyService, user_id: str, name: str):
    with pytest.raises(ValueError):
        await service.create(user_id, name=name)


@pytest.mark.unit
@pytest.mark.parametrize("days", [0, -1, MAX_EXPIRY_DAYS + 1])
async def test_out_of_range_expiry_is_rejected(service: ApiKeyService, user_id: str, days: int):
    with pytest.raises(ValueError):
        await service.create(user_id, name="bad-expiry", expires_in_days=days)


@pytest.mark.unit
async def test_expiry_is_stored_when_requested(service: ApiKeyService, user_id: str):
    minted = await service.create(user_id, name="temporary", expires_in_days=30)

    assert minted.key.expires_at is not None
    assert minted.key.is_usable() is True


@pytest.mark.unit
async def test_unassignable_scope_is_rejected_at_creation(service: ApiKeyService, user_id: str):
    with pytest.raises(InvalidScopeError):
        await service.create(user_id, name="escalation", scopes={"admin"})
