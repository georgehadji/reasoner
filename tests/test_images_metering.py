"""Credit reservation around /api/generate-image — security-remediation-plan.md
Phase 2 item 2, moved onto ``admit_flat_charge`` by audit-5 BIL-26. These tests
pin charge-on-request, refund-on-failure (a client disconnect included), and
no-double-charge.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from reasoner.api.routes import images
from reasoner.api.run_admission import FlatCharge
from reasoner.api.schemas import GenerateImageRequest
from reasoner.domain.saas import User

pytestmark = pytest.mark.unit


def _user() -> User:
    return User(id=uuid4(), email="test@example.com", created_at=datetime.now(UTC))


class _RecordingCharge:
    """Test double standing in for admit_flat_charge/close_flat_charge."""

    def __init__(self, credits: int = 10):
        self.credits = credits
        self.admit_calls: list[dict] = []
        self.close_calls: list[dict] = []

    async def admit(self, request, *, user, cost_usd, kind):
        self.admit_calls.append({"user": user, "cost_usd": cost_usd, "kind": kind})
        return FlatCharge(str(user.id) if user else None, f"{kind}:x", self.credits, cost_usd)

    async def close(self, charge, *, served):
        self.close_calls.append({"credits": charge.credits, "served": served})


@pytest.fixture
def charge(monkeypatch) -> _RecordingCharge:
    recorder = _RecordingCharge(credits=6)
    monkeypatch.setattr(images, "admit_flat_charge", recorder.admit)
    monkeypatch.setattr(images, "close_flat_charge", recorder.close)

    async def no_auto_models(body, num_images):
        return None, None

    monkeypatch.setattr(images, "_auto_select_models", no_auto_models)
    return recorder


async def _fake_generate_images_success(**kwargs):
    return {
        "success": True,
        "images": [{"image_data": "data:image/png;base64,abc", "model_used": "gemini-pro-image"}],
        "enhanced_prompt": kwargs["prompt"],
        "rewritten_prompt": None,
    }


async def _fake_generate_images_failure(**kwargs):
    return {"success": False, "error": "provider timeout"}


async def _call(body: GenerateImageRequest, user: User | None):
    return await images.generate_image_endpoint(
        request=None, body=body, user=user, rate_limit_checked=True, csrf_checked=True, quota=None,
    )


async def test_authenticated_success_charges_and_keeps_the_charge(monkeypatch, charge):
    monkeypatch.setattr(images, "generate_images", _fake_generate_images_success)

    result = await _call(GenerateImageRequest(prompt="draw a fox", num_images=2), _user())

    assert result["success"] is True
    assert len(charge.admit_calls) == 1
    assert charge.admit_calls[0]["kind"] == "image"
    assert charge.admit_calls[0]["cost_usd"] > 0
    # No true-up against real spend for images: success keeps the hold.
    assert charge.close_calls == [{"credits": 6, "served": True}]


async def test_anonymous_request_goes_through_admission(monkeypatch, charge):
    """BIL-26: with legacy access on, an anonymous image used to skip both the
    reservation and the trial cap. admit_flat_charge applies the cap."""
    monkeypatch.setattr(images, "generate_images", _fake_generate_images_success)

    result = await _call(GenerateImageRequest(prompt="draw a fox"), None)

    assert result["success"] is True
    assert charge.admit_calls[0]["user"] is None


async def test_generation_failure_gives_the_charge_back(monkeypatch, charge):
    monkeypatch.setattr(images, "generate_images", _fake_generate_images_failure)

    result = await _call(GenerateImageRequest(prompt="draw a fox"), _user())

    assert result["success"] is False
    assert charge.close_calls == [{"credits": 6, "served": False}]


async def test_generation_exception_gives_the_charge_back(monkeypatch, charge):
    async def exploding(**kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(images, "generate_images", exploding)

    result = await _call(GenerateImageRequest(prompt="draw a fox"), _user())

    assert result == {"success": False, "error": "Internal server error"}
    assert charge.close_calls == [{"credits": 6, "served": False}]


async def test_client_disconnect_gives_the_charge_back(monkeypatch, charge):
    """A disconnect cancels the task. The release used to run only on
    Exception, so CancelledError left the hold debited for good."""

    async def cancelled(**kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(images, "generate_images", cancelled)

    with pytest.raises(asyncio.CancelledError):
        await _call(GenerateImageRequest(prompt="draw a fox"), _user())

    assert charge.close_calls == [{"credits": 6, "served": False}]


async def test_preview_is_charged(monkeypatch, charge):
    """BIL-26: preview_only ran an LLM call before any credit check."""

    async def enhance(prompt):
        return "a red fox"

    monkeypatch.setattr(images, "enhance_image_prompt", enhance)

    result = await _call(GenerateImageRequest(prompt="draw a fox", preview_only=True), _user())

    assert result["enhanced_prompt"] == "a red fox"
    assert charge.admit_calls[0]["kind"] == "image-preview"
    assert charge.close_calls == [{"credits": 6, "served": True}]


async def test_estimated_image_cost_is_positive():
    """estimate_image_cost() never returns 0 for num_images>=1, so every
    image request holds credits."""
    from reasoner.application.services.estimate_service import estimate_image_cost

    cost = await estimate_image_cost("image-gen-budget", 1)
    assert cost > 0
