# tests/test_saas_preset_tiers.py
import pytest
from reasoner.presets import PRESETS, get_preset_tier
from reasoner.domain.saas import SubscriptionTier


def test_all_budget_presets_are_free():
    for name, preset in PRESETS.items():
        if name.endswith("-budget"):
            assert preset.required_tier == SubscriptionTier.FREE, f"{name} should be FREE"


def test_all_premium_presets_require_pro():
    for name, preset in PRESETS.items():
        if name.endswith("-premium") or name == "image-gen-premium":
            assert preset.required_tier == SubscriptionTier.PRO, f"{name} should be PRO"


def test_get_preset_tier_unknown_preset_defaults_free():
    assert get_preset_tier("nonexistent-preset") == SubscriptionTier.FREE


class TestPresetTierEnforcement:
    """Premium presets must actually be gated, not just labelled.

    check_preset_access/require_tier previously ignored the caller's subscription
    and raised a "not yet implemented" 403 in production while allowing everything
    everywhere else, so any authenticated free user could run premium presets.
    """

    @staticmethod
    def _user():
        from uuid import uuid4
        from reasoner.domain.saas import User

        return User(id=uuid4(), email="tier@test.local")

    @pytest.fixture(autouse=True)
    def _enable_enforcement(self, monkeypatch):
        """Gating is opt-in (PRESET_TIER_ENFORCEMENT_ENABLED); turn it on here."""
        from reasoner.core.settings import settings

        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", True)

    @staticmethod
    def _as_tier(tier):
        from unittest.mock import AsyncMock, patch

        return patch(
            "reasoner.api.dependencies._resolve_user_tier",
            AsyncMock(return_value=tier),
        )

    def test_tier_ordering(self):
        from reasoner.api.dependencies import tier_satisfies

        assert tier_satisfies(SubscriptionTier.PRO, SubscriptionTier.PRO)
        assert tier_satisfies(SubscriptionTier.ENTERPRISE, SubscriptionTier.PRO)
        assert tier_satisfies(SubscriptionTier.FREE, SubscriptionTier.FREE)
        assert not tier_satisfies(SubscriptionTier.FREE, SubscriptionTier.PRO)

    @pytest.mark.asyncio
    async def test_free_user_blocked_from_premium_preset(self):
        from fastapi import HTTPException
        from reasoner.api.dependencies import check_preset_access

        with self._as_tier(SubscriptionTier.FREE):
            with pytest.raises(HTTPException) as exc:
                await check_preset_access("debate-premium", self._user())
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_free_user_allowed_budget_preset(self):
        from reasoner.api.dependencies import check_preset_access

        with self._as_tier(SubscriptionTier.FREE):
            await check_preset_access("debate-budget", self._user())

    @pytest.mark.asyncio
    async def test_pro_user_allowed_premium_preset(self):
        from reasoner.api.dependencies import check_preset_access

        with self._as_tier(SubscriptionTier.PRO):
            await check_preset_access("debate-premium", self._user())


class TestPresetTierEnforcedOnRunRoute:
    """Gating must be wired into /api/run, not just available as a helper."""

    @pytest.fixture(autouse=True)
    def _enable_enforcement(self, monkeypatch):
        from reasoner.core.settings import settings

        monkeypatch.setattr(settings, "PRESET_TIER_ENFORCEMENT_ENABLED", True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tier,preset,expected_status", [
        (SubscriptionTier.FREE, "debate-premium", 403),
        (SubscriptionTier.FREE, "debate-budget", 200),
        (SubscriptionTier.PRO, "debate-premium", 200),
    ])
    async def test_run_route_enforces_preset_tier(self, tier, preset, expected_status):
        from uuid import uuid4
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        import reasoner.api as api
        from reasoner.api.dependencies import get_optional_user
        from reasoner.domain.saas import User

        user = User(id=uuid4(), email="tier-route@test.local")
        api.app.dependency_overrides[get_optional_user] = lambda: user
        try:
            with patch(
                "reasoner.api.dependencies._resolve_user_tier",
                AsyncMock(return_value=tier),
            ):
                async def fake_stream(*args, **kwargs):
                    yield 'data: {"type":"done"}\n\n'

                with patch("reasoner.api.run_stream_cached", fake_stream):
                    transport = ASGITransport(app=api.app)
                    async with AsyncClient(transport=transport, base_url="http://test") as client:
                        response = await client.post(
                            "/api/run",
                            json={"problem": "x", "preset": preset, "no_cache": True},
                        )
            assert response.status_code == expected_status
        finally:
            api.app.dependency_overrides.pop(get_optional_user, None)
