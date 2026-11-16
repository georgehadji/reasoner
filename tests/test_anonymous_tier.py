"""ANONYMOUS_TIER: the plan a caller with no account is treated as.

Defaults to FREE, as before. A local or self-hosted instance that runs without
sign-in (ALLOW_ANONYMOUS_RUNS=true) had no way past FREE's $0.07 per-run
ceiling and preset-tier gate, so article-budget and every premium preset were
refused ("refused by plan limit (per_run)", 2026-11-09). Production refuses any
value but "free" at startup.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from reasoner.application.services import spend_limit_service as sls
from reasoner.core.settings import settings
from reasoner.domain.saas import SubscriptionTier


@pytest.mark.asyncio
async def test_anonymous_defaults_to_free(monkeypatch):
    monkeypatch.setattr(settings, "ANONYMOUS_TIER", "free")
    assert await sls.resolve_user_tier(None) is SubscriptionTier.FREE


@pytest.mark.asyncio
async def test_anonymous_tier_is_configurable(monkeypatch):
    monkeypatch.setattr(settings, "ANONYMOUS_TIER", "enterprise")
    tier = await sls.resolve_user_tier(None)

    assert tier is SubscriptionTier.ENTERPRISE
    # The run gate then admits what FREE refused.
    assert sls.check_run_allowed("article-premium", tier, None) is None


@pytest.mark.asyncio
async def test_unknown_anonymous_tier_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "ANONYMOUS_TIER", "platinum")
    assert await sls.resolve_user_tier(None) is SubscriptionTier.FREE


def test_production_refuses_a_paid_anonymous_tier():
    # Every other production guard is satisfied, so only this one can fire.
    env = {
        **os.environ,
        "PYTHONPATH": "src",
        "ENVIRONMENT": "production",
        "ANONYMOUS_TIER": "pro",
        "CSRF_SECRET": "x" * 40,
        "ADMIN_API_KEY": "y" * 40,
        "JWT_SECRET_KEY": "z" * 40,
        "EXEC_SANDBOX_ENABLED": "false",
    }
    proc = subprocess.run(
        [sys.executable, "-c", "import reasoner.core.settings"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "ANONYMOUS_TIER" in proc.stderr
