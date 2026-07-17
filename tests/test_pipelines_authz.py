"""Tests for _check_pipeline_ownership (api/routes/pipelines.py).

Exercises the fail-closed rewrite against a real, isolated
PipelineOwnershipRepository — an unknown pipeline or a storage error must
both deny for a non-admin user, where the old JSON-file-backed version
allowed both (see docs/plans/pipeline-ownership-authz-hardening.md).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest

from reasoner.api.routes.pipelines import _check_pipeline_ownership
from reasoner.domain.saas import User
from reasoner.infrastructure.persistence.pipeline_ownership_repo import (
    PipelineOwnershipRepository,
)


def _user(user_id=None, scopes: set[str] | None = None) -> User:
    return User(
        id=user_id or uuid4(),
        email="user@example.com",
        scopes=scopes or set(),
    )


@pytest.fixture
def ownership_repo(tmp_path: Path):
    repo = PipelineOwnershipRepository(db_path=tmp_path / "authz_test.db")
    with patch(
        "reasoner.infrastructure.persistence.pipeline_ownership_repo.get_pipeline_ownership_repo",
        return_value=repo,
    ):
        yield repo


@pytest.mark.asyncio
async def test_owner_is_authorized(ownership_repo):
    user = _user()
    await ownership_repo.set_owner("p1", str(user.id), "p1")
    assert await _check_pipeline_ownership("p1", user) is True


@pytest.mark.asyncio
async def test_non_owner_is_denied(ownership_repo):
    owner = _user()
    other = _user()
    await ownership_repo.set_owner("p1", str(owner.id), "p1")
    assert await _check_pipeline_ownership("p1", other) is False


@pytest.mark.asyncio
async def test_admin_bypasses_ownership(ownership_repo):
    owner = _user()
    admin = _user(scopes={"admin"})
    await ownership_repo.set_owner("p1", str(owner.id), "p1")
    assert await _check_pipeline_ownership("p1", admin) is True


@pytest.mark.asyncio
async def test_unknown_pipeline_denied_for_non_admin(ownership_repo):
    """Fail closed: no ownership record at all is NOT world-accessible."""
    user = _user()
    assert await _check_pipeline_ownership("never-recorded", user) is False


@pytest.mark.asyncio
async def test_anonymous_owner_allowed_for_anyone(ownership_repo):
    """A pipeline explicitly recorded with no owner (anonymous run) is
    accessible to any authenticated user -- distinct from no record
    existing at all."""
    user = _user()
    await ownership_repo.set_owner("anon-pipeline", None, "anon-pipeline")
    assert await _check_pipeline_ownership("anon-pipeline", user) is True


@pytest.mark.asyncio
async def test_lookup_error_denied_for_non_admin():
    """A storage error must deny, not be treated as 'no owner recorded'."""
    user = _user()
    with patch(
        "reasoner.infrastructure.persistence.pipeline_ownership_repo.get_pipeline_ownership_repo",
        side_effect=RuntimeError("db is on fire"),
    ):
        assert await _check_pipeline_ownership("p1", user) is False


@pytest.mark.asyncio
async def test_admin_bypasses_even_on_lookup_error():
    """Admin scope short-circuits before any ownership lookup, so a broken
    store can never lock out an admin."""
    admin = _user(scopes={"admin"})
    with patch(
        "reasoner.infrastructure.persistence.pipeline_ownership_repo.get_pipeline_ownership_repo",
        side_effect=RuntimeError("db is on fire"),
    ):
        assert await _check_pipeline_ownership("p1", admin) is True
