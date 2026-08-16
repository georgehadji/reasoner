"""Regression tests for authentication gates on provider-costing routes."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from reasoner.api.dependencies import require_auth_if_legacy_disabled
from reasoner.core.settings import settings


@pytest.mark.asyncio
async def test_metered_auth_rejects_anonymous_when_legacy_access_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_LEGACY_API_KEY", False)

    with pytest.raises(HTTPException) as exc_info:
        await require_auth_if_legacy_disabled(None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_metered_auth_preserves_explicit_legacy_compatibility(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_LEGACY_API_KEY", True)

    assert await require_auth_if_legacy_disabled(None) is None
