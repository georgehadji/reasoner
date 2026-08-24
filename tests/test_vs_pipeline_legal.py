"""E2E test: Legal pipeline conservative routing."""
from __future__ import annotations

import pytest

from reasoner.phases.vs_generation import GenerationStrategy, VSGenerationConfig, generate_with_vs
from reasoner.phases.vs_verification_routing import VerificationRoute, route_claim_by_vs_probability
from reasoner.vs_config import VSDeploymentProfile, VSFeatureFlags
from tests.utils.mocks import MockLLM, MockNLI

CANDIDATES_JSON = '{"candidates": [{"text": "Clause draft A", "probability": 0.5}, {"text": "Clause draft B", "probability": 0.3}, {"text": "Clause draft C", "probability": 0.2}]}'






@pytest.mark.slow
@pytest.mark.integration
class TestLegalPipeline:
    async def test_legal_pipeline_conservative_routing(self) -> None:
        query = "Draft a liability clause for SaaS terms"
        llm = MockLLM(response=CANDIDATES_JSON)
        nli = MockNLI()
        flags = VSFeatureFlags()

        gen_config = VSGenerationConfig(
            strategy=GenerationStrategy.BEST_VERIFIABLE,
            profile=VSDeploymentProfile.MAX_ACCURACY,
        )
        gen = await generate_with_vs(query, gen_config, llm, nli, flags)

        # Route low-probability claims → CONSERVATIVE
        route, meta = await route_claim_by_vs_probability(
            gen.candidates[-1].text, gen.candidates[-1].probability, flags
        )
        assert route == VerificationRoute.CONSERVATIVE
        assert meta.get("human_review_flag") is True
