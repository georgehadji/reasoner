"""Tests for vs_verification_routing stage."""
from __future__ import annotations

from reasoner.phases.vs_verification_routing import (
    VerificationRoute,
    route_claim_by_vs_probability,
)
from reasoner.reasoner_vs_constants import VS_ROUTING_HIGH_PROB, VS_ROUTING_MEDIUM_PROB
from reasoner.vs_config import VSFeatureFlags


class TestVerificationRouting:
    async def test_high_probability_routes_nli_only(self) -> None:
        route, meta = await route_claim_by_vs_probability("claim", 0.95, VSFeatureFlags())
        assert route == VerificationRoute.NLI_ONLY
        assert meta["confidence"] == "high"

    async def test_medium_probability_routes_nli_then_llm(self) -> None:
        route, meta = await route_claim_by_vs_probability("claim", 0.50, VSFeatureFlags())
        assert route == VerificationRoute.NLI_THEN_LLM
        assert meta["confidence"] == "medium"

    async def test_low_probability_routes_conservative(self) -> None:
        route, meta = await route_claim_by_vs_probability("claim", 0.10, VSFeatureFlags())
        assert route == VerificationRoute.CONSERVATIVE
        assert meta["confidence"] == "low"
        assert meta["human_review_flag"] is True

    async def test_exact_boundary_high(self) -> None:
        route, _ = await route_claim_by_vs_probability("claim", VS_ROUTING_HIGH_PROB, VSFeatureFlags())
        assert route == VerificationRoute.NLI_ONLY

    async def test_exact_boundary_medium(self) -> None:
        route, _ = await route_claim_by_vs_probability("claim", VS_ROUTING_MEDIUM_PROB, VSFeatureFlags())
        assert route == VerificationRoute.NLI_THEN_LLM

    async def test_conservative_never_routes_to_llm(self) -> None:
        route, _ = await route_claim_by_vs_probability("claim", 0.0, VSFeatureFlags())
        assert route == VerificationRoute.CONSERVATIVE
        assert route != VerificationRoute.NLI_THEN_LLM

    async def test_disabled_returns_nli_only(self) -> None:
        route, meta = await route_claim_by_vs_probability("claim", 0.10, VSFeatureFlags.all_disabled())
        assert route == VerificationRoute.NLI_ONLY
        assert meta == {}
