"""Step 1 of docs/plans/email-verification-2026-11-12.md: read the verified flag.

The auth adapters set ``User.email_verified`` from the provider, and the
Supabase adapter carries the real signup time (the grandfather rule needs it).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from reasoner.infrastructure.auth.local_adapter import LocalAuthAdapter
from reasoner.infrastructure.auth.supabase_adapter import SupabaseAuthAdapter, _as_datetime

pytestmark = pytest.mark.unit

_SECRET = "x" * 40


def _supabase(**fields) -> SupabaseAuthAdapter:
    user = SimpleNamespace(
        id=str(uuid.UUID(int=7)), email="a@b.c", app_metadata={}, user_metadata={}, **fields
    )
    adapter = SupabaseAuthAdapter.__new__(SupabaseAuthAdapter)
    adapter._client = SimpleNamespace(
        auth=SimpleNamespace(get_user=lambda _t: SimpleNamespace(user=user))
    )
    return adapter


async def test_supabase_confirmed_address_is_verified():
    user = await _supabase(email_confirmed_at="2026-01-02T03:04:05Z")._verify("t")
    assert user.email_verified is True


async def test_supabase_unconfirmed_address_is_not_verified():
    user = await _supabase(email_confirmed_at=None)._verify("t")
    assert user.email_verified is False


async def test_supabase_user_without_the_field_is_not_verified():
    # Fail closed: an older client shape with no field must not count as confirmed.
    assert (await _supabase()._verify("t")).email_verified is False


async def test_supabase_signup_time_is_carried():
    user = await _supabase(created_at="2025-06-01T00:00:00+00:00")._verify("t")
    assert user.created_at == datetime(2025, 6, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (datetime(2025, 1, 1), datetime(2025, 1, 1, tzinfo=UTC)),  # naive -> UTC
        ("2025-01-01T00:00:00Z", datetime(2025, 1, 1, tzinfo=UTC)),
        ("not a date", None),
        ("", None),
        (None, None),
    ],
)
def test_as_datetime(raw, expected):
    assert _as_datetime(raw) == expected


async def test_local_token_is_verified_by_default():
    adapter = LocalAuthAdapter(_SECRET)
    token = adapter.create_token(str(uuid.UUID(int=8)), "d@e.f")
    assert (await adapter.authenticate(token)).email_verified is True


async def test_local_token_can_be_unverified():
    adapter = LocalAuthAdapter(_SECRET)
    token = adapter.create_token(str(uuid.UUID(int=8)), "d@e.f", email_verified=False)
    assert (await adapter.authenticate(token)).email_verified is False
