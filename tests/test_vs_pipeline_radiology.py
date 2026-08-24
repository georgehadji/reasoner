"""E2E test: Radiology pipeline with VS enabled."""
from __future__ import annotations

import pytest

from reasoner.phases.vs_calibration import extract_calibration_signals
from reasoner.phases.vs_claim_extraction import (
    ClaimExtractionMode,
    VSClaimExtractionConfig,
    extract_claims_from_vs_candidates,
)
from reasoner.phases.vs_conflict_surfacing import surface_cross_candidate_conflicts
from reasoner.phases.vs_decomposition import DecompositionVSConfig, decompose_with_vs
from reasoner.phases.vs_generation import GenerationStrategy, VSGenerationConfig, generate_with_vs
from reasoner.phases.vs_probe_generation import ProbeGenerationConfig, generate_probes_with_vs
from reasoner.phases.vs_verification_routing import VerificationRoute, route_claim_by_vs_probability
from reasoner.vs_config import VSDeploymentProfile, VSFeatureFlags
from tests.utils.mocks import MockLLM, MockNLI

CANDIDATES_JSON = '{"candidates": [{"text": "Lesion A found in upper lobe", "probability": 0.5}, {"text": "No significant findings", "probability": 0.3}, {"text": "Possible nodule in mediastinum", "probability": 0.2}]}'






@pytest.fixture
def flags() -> VSFeatureFlags:
    return VSFeatureFlags()


@pytest.mark.slow
@pytest.mark.integration
class TestRadiologyPipeline:
    async def test_radiology_pipeline_vs(self, flags: VSFeatureFlags) -> None:
        query = "Identify lesions in this chest CT"
        llm = MockLLM(response=CANDIDATES_JSON)
        nli = MockNLI()

        # Probes
        probe_config = ProbeGenerationConfig(domain="radiology", k=5)
        probes = await generate_probes_with_vs(query, probe_config, llm, flags)
        assert len(probes.probes) >= 1

        # Decomposition
        decomp_config = DecompositionVSConfig(top_n=3)
        decomp = await decompose_with_vs(query, decomp_config, llm, flags)
        assert len(decomp.sub_queries) >= 1

        # Generation (BEST_VERIFIABLE)
        gen_config = VSGenerationConfig(
            strategy=GenerationStrategy.BEST_VERIFIABLE,
            profile=VSDeploymentProfile.MAX_ACCURACY,
        )
        gen = await generate_with_vs(query, gen_config, llm, nli, flags)
        assert gen.selected.selected is True
        assert len(gen.candidates) >= 1

        # Calibration
        cal = await extract_calibration_signals(gen, flags)
        assert 0.0 <= cal.entropy <= 1.0

        # Claims
        claims = await extract_claims_from_vs_candidates(
            gen.candidates, VSClaimExtractionConfig(mode=ClaimExtractionMode.SINGLE), llm, flags
        )
        assert len(claims.claims) >= 1

        # Verification routing for top candidate
        route, meta = await route_claim_by_vs_probability(
            claims.claims[0], gen.selected.probability, flags
        )
        assert route in {VerificationRoute.NLI_ONLY, VerificationRoute.NLI_THEN_LLM, VerificationRoute.CONSERVATIVE}

        # Conflict surfacing
        conflicts = await surface_cross_candidate_conflicts(gen.candidates, nli, flags)
        assert isinstance(conflicts, list)

        # Generation stage made exactly 1 LLM call (probes + decomp may add more)
        assert llm.generate.await_count >= 1
