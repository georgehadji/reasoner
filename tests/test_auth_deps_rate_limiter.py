"""Tests for rate-limiter fail-closed behavior.

Was auth_deps's own IP-only, fail-open(503) implementation; converged onto
dependencies.check_rate_limit (docs/plans/pre-existing-fixes.md #3), which
every route now uses directly, fail-closed to 429 on limiter errors.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request

from reasoner.api.dependencies import check_rate_limit


@pytest.mark.asyncio
async def test_rate_limiter_fail_closed(monkeypatch):
    """
    If the rate limiter raises an unexpected exception,
    check_rate_limit must fail-closed with HTTP 429 (deny the request).
    """
    mock_request = Request(scope={
        "type": "http",
        "method": "POST",
        "path": "/api/run",
        "headers": [],
    })

    mock_limiter = AsyncMock()
    mock_limiter.is_allowed = AsyncMock(side_effect=RuntimeError("redis down"))

    from reasoner.api import dependencies as deps_module
    monkeypatch.setattr(deps_module, "_rate_limiter_instance", mock_limiter)

    with pytest.raises(HTTPException) as exc_info:
        await check_rate_limit(request=mock_request, user=None, credentials=None)

    assert exc_info.value.status_code == 429
