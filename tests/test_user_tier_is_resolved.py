"""The caller's real subscription tier must reach rate limits, quota, and metrics.

Three call sites hardcoded the free tier (TODO #501/#502), so a paying
subscriber got the free-tier rate limit, saw the free allowance in the UI, and
had every run reported as "free" in the Prometheus counter — which made per-tier
cost breakdowns impossible.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from reasoner.domain.saas import SubscriptionTier

REPO_ROOT = Path(__file__).resolve().parents[1]


class _StubUser:
    id = "user-abc"
    email = "pro@example.com"


@pytest.mark.asyncio
async def test_rate_limit_uses_the_subscribers_tier():
    """A pro user must get the pro multiplier, not the default bucket."""
    from reasoner.api import dependencies

    limiter = AsyncMock()
    limiter.is_allowed_for_user.return_value = (
        True,
        {"limit_minute": 120, "remaining_minute": 119, "retry_after": 0},
    )

    request = AsyncMock()
    request.state = type("S", (), {})()

    with (
        patch.object(dependencies, "_get_rate_limiter_instance", return_value=limiter),
        patch.object(
            dependencies,
            "_resolve_user_tier",
            AsyncMock(return_value=SubscriptionTier.PRO),
        ),
    ):
        await dependencies.check_rate_limit(
            request=request, user=_StubUser(), credentials=None
        )

    _, kwargs = limiter.is_allowed_for_user.call_args
    assert kwargs["tier"] == "pro", "paying users must not be limited at the free rate"


@pytest.mark.asyncio
async def test_quota_endpoint_reports_the_subscribers_allowance():
    from reasoner.api import dependencies, saas_router
    from reasoner.application.services.quota_service import TIER_LIMITS

    quota_service = AsyncMock()
    quota_service.check.return_value = type("R", (), {"remaining": 7})()

    with (
        patch.object(saas_router, "_get_quota_service", return_value=quota_service),
        patch.object(
            dependencies,
            "_resolve_user_tier",
            AsyncMock(return_value=SubscriptionTier.PRO),
        ),
    ):
        result = await saas_router.get_quota_status(user=_StubUser())

    assert result["max"] == TIER_LIMITS[SubscriptionTier.PRO]
    assert quota_service.check.call_args[0][1] is SubscriptionTier.PRO


def test_no_hardcoded_free_tier_remains_at_the_fixed_call_sites():
    """Guards against the TODO(#501)/TODO(#502) placeholders coming back."""
    sources = {
        "api/dependencies.py": REPO_ROOT / "src/reasoner/api/dependencies.py",
        "api/saas_router.py": REPO_ROOT / "src/reasoner/api/saas_router.py",
        "api/__init__.py": REPO_ROOT / "src/reasoner/api/__init__.py",
    }
    for label, path in sources.items():
        text = path.read_text(encoding="utf-8")
        assert "TODO(#501)" not in text, f"{label} still defers tier resolution"
        assert "TODO(#502)" not in text, f"{label} still defers tier resolution"

    deps = sources["api/dependencies.py"].read_text(encoding="utf-8")
    assert 'tier="default"' not in deps, "check_rate_limit must pass the resolved tier"
