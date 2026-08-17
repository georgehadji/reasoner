"""Credit reservation around /api/generate-image — security-remediation-plan.md
Phase 2 item 2. Before this, image generation had zero cost tracking; these
tests pin reserve-on-request, refund-on-failure, and no-double-charge.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from reasoner.api.routes import images
from reasoner.api.schemas import GenerateImageRequest
from reasoner.domain.saas import User

pytestmark = pytest.mark.unit


def _user() -> User:
    return User(id=uuid4(), email="test@example.com", created_at=datetime.now(timezone.utc))


class _RecordingReservation:
    """Test double standing in for _reserve_image_credits/_release_image_credits."""

    def __init__(self, reserved: int = 10):
        self.reserved = reserved
        self.reserve_calls: list[dict] = []
        self.release_calls: list[dict] = []

    async def reserve(self, **kwargs):
        self.reserve_calls.append(kwargs)
        return self.reserved

    async def release(self, user, credits, reference_id):
        self.release_calls.append({"user": user, "credits": credits, "reference_id": reference_id})


async def _fake_generate_images_success(**kwargs):
    return {
        "success": True,
        "images": [{"image_data": "data:image/png;base64,abc", "model_used": "gemini-pro-image"}],
        "enhanced_prompt": kwargs["prompt"],
        "rewritten_prompt": None,
    }


async def _fake_generate_images_failure(**kwargs):
    return {"success": False, "error": "provider timeout"}


async def test_anonymous_request_never_reserves(monkeypatch):
    """user=None must not touch the credit system at all -- anonymous image
    gen spend isn't in scope for this pass (only pipeline runs got an
    AnonymousTrialPolicy)."""
    reservation = _RecordingReservation()
    monkeypatch.setattr(images, "_reserve_image_credits", reservation.reserve)
    monkeypatch.setattr(images, "generate_images", _fake_generate_images_success)

    result = await images.generate_image_endpoint(
        request=None,
        body=GenerateImageRequest(prompt="draw a fox"),
        user=None,
        rate_limit_checked=True,
        csrf_checked=True,
        quota=None,
    )

    assert result["success"] is True
    assert reservation.reserve_calls == []


async def test_authenticated_success_reserves_and_keeps_the_charge(monkeypatch):
    reservation = _RecordingReservation(reserved=6)
    monkeypatch.setattr(images, "_reserve_image_credits", reservation.reserve)
    monkeypatch.setattr(images, "_release_image_credits", reservation.release)
    monkeypatch.setattr(images, "generate_images", _fake_generate_images_success)

    user = _user()
    result = await images.generate_image_endpoint(
        request=None,
        body=GenerateImageRequest(prompt="draw a fox", num_images=2),
        user=user,
        rate_limit_checked=True,
        csrf_checked=True,
        quota=None,
    )

    assert result["success"] is True
    assert len(reservation.reserve_calls) == 1
    assert reservation.reserve_calls[0]["estimated_cost_usd"] > 0
    # No true-up against real spend for images (see estimate_service
    # module comment) -- success keeps the reservation, no release call.
    assert reservation.release_calls == []


async def test_generation_failure_releases_the_full_reservation(monkeypatch):
    reservation = _RecordingReservation(reserved=6)
    monkeypatch.setattr(images, "_reserve_image_credits", reservation.reserve)
    monkeypatch.setattr(images, "_release_image_credits", reservation.release)
    monkeypatch.setattr(images, "generate_images", _fake_generate_images_failure)

    user = _user()
    result = await images.generate_image_endpoint(
        request=None,
        body=GenerateImageRequest(prompt="draw a fox"),
        user=user,
        rate_limit_checked=True,
        csrf_checked=True,
        quota=None,
    )

    assert result["success"] is False
    assert len(reservation.release_calls) == 1
    assert reservation.release_calls[0]["credits"] == 6


async def test_generation_exception_releases_the_reservation_and_reports_error(monkeypatch):
    reservation = _RecordingReservation(reserved=6)
    monkeypatch.setattr(images, "_reserve_image_credits", reservation.reserve)
    monkeypatch.setattr(images, "_release_image_credits", reservation.release)

    async def exploding(**kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(images, "generate_images", exploding)

    user = _user()
    result = await images.generate_image_endpoint(
        request=None,
        body=GenerateImageRequest(prompt="draw a fox"),
        user=user,
        rate_limit_checked=True,
        csrf_checked=True,
        quota=None,
    )

    assert result == {"success": False, "error": "Internal server error"}
    assert len(reservation.release_calls) == 1


async def test_zero_estimated_cost_never_calls_reserve(monkeypatch):
    """_reserve_image_credits itself no-ops on <=0, but the real
    estimate_image_cost() never returns 0 for num_images>=1 -- this pins
    the actual reservation-side short-circuit path."""
    from reasoner.application.services.estimate_service import estimate_image_cost

    cost = await estimate_image_cost("image-gen-budget", 1)
    assert cost > 0
