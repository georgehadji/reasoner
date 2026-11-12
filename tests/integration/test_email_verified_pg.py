"""Step 2 of docs/plans/email-verification-2026-11-12.md, against a real Postgres.

`_ensure_user_in_db` mirrors `User.email_verified` into `users.email_verified`,
in both directions (an email change can unverify). Uses a throwaway database
migrated with `alembic upgrade head` on the server behind REASONER_TEST_PG_DSN.
"""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

import pytest

from reasoner.api import dependencies as deps
from reasoner.domain.saas import User
from tests.integration.test_alembic_schema_contract import (
    DSN,
    _alembic_upgrade,
    _fresh_database,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not DSN, reason="REASONER_TEST_PG_DSN not set"),
]


async def test_the_row_follows_the_provider_flag_both_ways(monkeypatch):
    import asyncpg

    async with _fresh_database() as dsn:
        _alembic_upgrade(dsn)
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=2)
        try:
            async def _pool():
                return pool

            monkeypatch.setattr(deps, "_get_provision_pool", _pool)
            user = User(id=uuid4(), email=f"{uuid4().hex}@t.local", email_verified=False)
            seen = []
            for flag in (False, True, False):
                deps.forget_provisioned_user(user.id)  # skip the 60s provision cache
                await deps._ensure_user_in_db(replace(user, email_verified=flag))
                seen.append(await pool.fetchval(
                    "SELECT email_verified FROM users WHERE id = $1", user.id,
                ))
        finally:
            await pool.close()
    assert seen == [False, True, False]
