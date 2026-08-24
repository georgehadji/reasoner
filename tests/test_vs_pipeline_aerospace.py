"""E2E test: Aerospace pipeline failure-mode probes."""
from __future__ import annotations

import pytest

from reasoner.phases.vs_generation import GenerationStrategy, VSGenerationConfig, generate_with_vs
from reasoner.phases.vs_probe_generation import ProbeGenerationConfig, generate_probes_with_vs
from reasoner.phases.vs_verification_routing import VerificationRoute, route_claim_by_vs_probability
from reasoner.vs_config import VSDeploymentProfile, VSFeatureFlags
from reasoner.vs_vertical_configs.aerospace_config import AEROSPACE_CONFIG
from tests.utils.mocks import MockLLM, MockNLI

PROBES_JSON = '{"candidates": [{"text": "Failure mode: hydraulic seal degradation", "probability": 0.4}, {"text": "Failure mode: actuator fatigue", "probability": 0.3}, {"text": "Failure mode: contamination in fluid", "probability": 0.3}]}'






@pytest.mark.slow
@pytest.mark.integration
class TestAerospacePipeline:
    async def test_aerospace_failure_mode_probes(self) -> None:
        query = "Analyze failure modes for landing gear hydraulics"
        llm = MockLLM(response=PROBES_JSON)
        nli = MockNLI()
        flags = VSFeatureFlags()

        probe_config = ProbeGenerationConfig(
            domain=AEROSPACE_CONFIG.domain,
            k=AEROSPACE_CONFIG.k,
            tail_threshold=AEROSPACE_CONFIG.tail_threshold,
        )
        probes = await generate_probes_with_vs(query, probe_config, llm, flags)

        assert any("failure" in p.lower() for p in probes.probes), "Failure-mode probes generated"

        # Aerospace tail threshold is tight (0.06) — low-prob candidates route conservative
        gen_config = VSGenerationConfig(
            strategy=GenerationStrategy.BEST_VERIFIABLE,
            profile=VSDeploymentProfile.MAX_ACCURACY,
        )
        gen = await generate_with_vs(query, gen_config, llm, nli, flags)

        route, meta = await route_claim_by_vs_probability(
            gen.candidates[-1].text, 0.05, flags
        )
        assert route == VerificationRoute.CONSERVATIVE
        assert meta.get("human_review_flag") is True
