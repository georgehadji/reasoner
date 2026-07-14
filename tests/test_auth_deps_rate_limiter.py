"""Tests for rate-limiter fail-closed behavior in auth_deps."""

from __future__ import annotations

import pytest
from fastapi import HTTPException, Request
from unittest.mock import AsyncMock, patch

from reasoner.api.auth_deps import check_rate_limit


@pytest.mark.asyncio
async def test_rate_limiter_fail_closed():
    """
    If the rate limiter raises an unexpected exception,
    check_rate_limit must fail-closed with HTTP 503.
    """
    mock_request = Request(scope={
        "type": "http",
        "method": "POST",
        "path": "/api/run",
        "headers": [],
    })

    mock_limiter = AsyncMock()
    mock_limiter.is_allowed = AsyncMock(side_effect=RuntimeError("redis down"))

    with patch(
        "reasoner.api.auth_deps._get_rate_limiter_instance_auth_deps",
        return_value=mock_limiter,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit(mock_request)

    assert exc_info.value.status_code == 503
    assert "Rate limiting unavailable" in exc_info.value.detail
