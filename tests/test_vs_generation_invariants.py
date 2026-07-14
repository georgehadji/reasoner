"""Invariant tests for vs_generation stage."""
from __future__ import annotations
from tests.utils.mocks import MockLLM, MockNLI

import asyncio

import pytest
from unittest.mock import AsyncMock

from reasoner.phases.vs_generation import (
    generate_with_vs,
    VSGenerationConfig,
    VSGenerationResult,
    GenerationStrategy,
)
from reasoner.vs_config import VSFeatureFlags, VSDeploymentProfile






CANDIDATES_JSON = '{"candidates": [{"text": "A", "probability": 0.6}, {"text": "B", "probability": 0.4}]}'


class TestInvariants:
    async def test_exactly_one_selected(self) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        nli = MockNLI()
        config = VSGenerationConfig(strategy=GenerationStrategy.ENSEMBLE)
        result = await generate_with_vs("Q", config, llm, nli, VSFeatureFlags())
        selected = [c for c in result.candidates if c.selected]
        assert len(selected) == 1
        assert result.selected.selected is True

    async def test_llm_call_counter_is_one_for_generation(self) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        nli = MockNLI()
        config = VSGenerationConfig(strategy=GenerationStrategy.TOP_PROBABILITY)
        await generate_with_vs("Q", config, llm, nli, VSFeatureFlags())
        # One LLM call to generate candidates, zero for TOP_PROBABILITY strategy
        assert llm.generate.await_count == 1

    async def test_best_verifiable_llm_counter_is_one(self) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        nli = MockNLI()
        config = VSGenerationConfig(strategy=GenerationStrategy.BEST_VERIFIABLE)
        await generate_with_vs("Q", config, llm, nli, VSFeatureFlags())
        # One LLM call for candidate generation
        assert llm.generate.await_count == 1

    async def test_concurrent_generation_preserves_invariant(self) -> None:
        llm = MockLLM(CANDIDATES_JSON)
        nli = MockNLI()
        config = VSGenerationConfig()

        async def run() -> VSGenerationResult:
            return await generate_with_vs("Q", config, llm, nli, VSFeatureFlags())

        results = await asyncio.gather(run(), run(), run())
        for r in results:
            assert len([c for c in r.candidates if c.selected]) == 1
