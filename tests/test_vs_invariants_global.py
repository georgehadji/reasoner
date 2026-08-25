"""Global invariant tests for VS integration."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from reasoner.phases.vs_generation import _generate_with_vs_inner
from reasoner.phases.vs_probe_generation import generate_probes_with_vs
from reasoner.vs_config import VSFeatureFlags
from tests.utils.mocks import MockLLM, MockNLI


class TestLLMCallCounter:
    async def test_generation_makes_exactly_one_llm_call(self) -> None:
        from reasoner.phases.vs_generation import GenerationStrategy, VSGenerationConfig

        llm = MockLLM('{"candidates": [{"text": "a", "probability": 1}]}')
        nli = MockNLI()
        config = VSGenerationConfig(strategy=GenerationStrategy.TOP_PROBABILITY)
        flags = VSFeatureFlags()

        await _generate_with_vs_inner("Q", config, llm, nli, flags)
        assert llm.generate.await_count == 1

    async def test_probe_generation_makes_at_most_two_llm_calls(self) -> None:
        from reasoner.phases.vs_probe_generation import ProbeGenerationConfig

        # Single candidate triggers fallback → 2 calls max
        llm = MockLLM('{"candidates": [{"text": "probe", "probability": 1}]}')
        config = ProbeGenerationConfig()
        flags = VSFeatureFlags()

        await generate_probes_with_vs("Q", config, llm, flags)
        assert llm.generate.await_count <= 2


class TestTaintPropagation:
    async def test_generation_has_vs_metadata(self) -> None:
        from reasoner.phases.vs_generation import GenerationStrategy, VSGenerationConfig

        llm = MockLLM('{"candidates": [{"text": "a", "probability": 1}]}')
        nli = MockNLI()
        config = VSGenerationConfig(strategy=GenerationStrategy.TOP_PROBABILITY)
        flags = VSFeatureFlags()

        result = await _generate_with_vs_inner("Q", config, llm, nli, flags)
        assert "vs_strategy" in result.vs_metadata or "strategy" in result.vs_metadata

    async def test_probe_generation_has_vs_metadata(self) -> None:
        from reasoner.phases.vs_probe_generation import ProbeGenerationConfig

        llm = MockLLM('{"candidates": [{"text": "probe", "probability": 1}]}')
        config = ProbeGenerationConfig(domain="radiology")
        flags = VSFeatureFlags()

        result = await generate_probes_with_vs("Q", config, llm, flags)
        assert result.vs_metadata is not None
        assert "vs_probe_domain" in result.vs_metadata


class TestZeroMagicNumbers:
    def test_all_vs_phases_import_constants(self) -> None:
        """Every VS phase file with a tunable literal must source it from
        reasoner_vs_constants.

        Scoped to files that actually contain such a literal. The check used to
        require the import from every vs_*.py unconditionally, which a file with
        no magic numbers can only satisfy by adding an import nothing uses --
        the opposite of what this class is guarding. 0/1 and the 2 of a
        halving/midpoint are structural, not tunable thresholds, so they do not
        by themselves oblige a module to reach for the constants table.
        """
        phases_dir = Path(__file__).parent.parent / "src" / "reasoner" / "phases"
        vs_files = sorted(phases_dir.glob("vs_*.py"))
        assert vs_files, "No vs_*.py files found"

        # A bare int/float literal, ignoring attribute access, identifiers and
        # anything inside a string.
        literal_re = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
        structural = {"0", "1", "2"}

        missing = []
        for fpath in vs_files:
            source = fpath.read_text(encoding="utf-8")
            if "reasoner_vs_constants" in source:
                continue
            tunable = [
                m.group()
                for line in source.splitlines()
                if not line.lstrip().startswith("#")
                for m in literal_re.finditer(line)
                if m.group() not in structural
            ]
            if tunable:
                missing.append(f"{fpath.name} (literals: {sorted(set(tunable))})")

        if missing:
            pytest.fail(f"Files with tunable literals not importing reasoner_vs_constants: {missing}")
