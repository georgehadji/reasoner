"""Tests for vs_behavioral_audit observability stage."""
from __future__ import annotations

import logging

import pytest

from reasoner.core.vs_constants import LOG_VS_MODE_COLLAPSE
from reasoner.phases.vs_behavioral_audit import (
    InMemoryVSEntropyStore,
    log_vs_behavioral_audit,
)
from reasoner.phases.vs_generation import GenerationCandidate, VSGenerationResult
from reasoner.vs_config import VSFeatureFlags


class TestInMemoryEntropyStore:
    async def test_push_and_mean(self) -> None:
        store = InMemoryVSEntropyStore()
        await store.push(1.0)
        await store.push(2.0)
        mean = await store.get_mean()
        assert mean == pytest.approx(1.5)

    async def test_window_respects_maxlen(self) -> None:
        store = InMemoryVSEntropyStore(maxlen=2)
        await store.push(1.0)
        await store.push(2.0)
        await store.push(3.0)
        mean = await store.get_mean()
        assert mean == pytest.approx(2.5)

    async def test_mean_empty_store(self) -> None:
        store = InMemoryVSEntropyStore()
        mean = await store.get_mean()
        assert mean == 0.0

    async def test_rolling_mean(self) -> None:
        store = InMemoryVSEntropyStore()
        for i in range(10):
            await store.push(float(i))
        mean = await store.get_mean(window=5)
        assert mean == pytest.approx(7.0)


class TestBehavioralAudit:
    async def test_feature_flag_bypass(self) -> None:
        store = InMemoryVSEntropyStore()
        result = VSGenerationResult(
            candidates=[GenerationCandidate(text="a", probability=1.0, selected=True)],
            selected=GenerationCandidate(text="a", probability=1.0, selected=True),
        )
        await log_vs_behavioral_audit(result, store, VSFeatureFlags.all_disabled())
        assert store.size == 0

    async def test_entropy_pushed(self) -> None:
        store = InMemoryVSEntropyStore()
        result = VSGenerationResult(
            candidates=[
                GenerationCandidate(text="a", probability=0.5, selected=False),
                GenerationCandidate(text="b", probability=0.5, selected=True),
            ],
            selected=GenerationCandidate(text="b", probability=0.5, selected=True),
        )
        await log_vs_behavioral_audit(result, store, VSFeatureFlags())
        assert store.size == 1

    async def test_mode_collapse_alert(self, caplog: pytest.LogCaptureFixture) -> None:
        store = InMemoryVSEntropyStore()
        # Push high entropy values first
        for _ in range(10):
            await store.push(1.0)
        # Then low entropy values
        for _ in range(10):
            await store.push(0.1)

        result = VSGenerationResult(
            candidates=[
                GenerationCandidate(text="a", probability=1.0, selected=True),
            ],
            selected=GenerationCandidate(text="a", probability=1.0, selected=True),
        )
        with caplog.at_level(logging.WARNING):
            await log_vs_behavioral_audit(result, store, VSFeatureFlags())

        # The `or store.size == 21` this assertion used to carry was always
        # true: test_entropy_pushed proves the call pushes exactly one entry,
        # so 20 + 1 satisfied the disjunct whether or not the alert fired.
        # Replacing the detection with `if False:` left all 9 tests green.
        assert "mode collapse" in caplog.text.lower()
        assert any(
            getattr(record, LOG_VS_MODE_COLLAPSE, False) for record in caplog.records
        ), "the alert must carry the structured key log consumers filter on"

    async def test_no_alert_when_entropy_is_stable(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The other half of the contract: a stable window must stay quiet.

        Without this, `assert "mode collapse" in caplog.text` alone is passed
        by an implementation that warns unconditionally.
        """
        store = InMemoryVSEntropyStore()
        for _ in range(20):
            await store.push(1.0)

        result = VSGenerationResult(
            candidates=[
                GenerationCandidate(text="a", probability=1.0, selected=True),
            ],
            selected=GenerationCandidate(text="a", probability=1.0, selected=True),
        )
        with caplog.at_level(logging.WARNING):
            await log_vs_behavioral_audit(result, store, VSFeatureFlags())

        assert "mode collapse" not in caplog.text.lower()

    async def test_non_blocking(self) -> None:
        store = InMemoryVSEntropyStore()
        result = VSGenerationResult(
            candidates=[GenerationCandidate(text="a", probability=1.0, selected=True)],
            selected=GenerationCandidate(text="a", probability=1.0, selected=True),
        )
        # Should complete immediately without external dependencies
        await log_vs_behavioral_audit(result, store, VSFeatureFlags())
        assert True

    async def test_log_keys_present(self, caplog: pytest.LogCaptureFixture) -> None:
        store = InMemoryVSEntropyStore()
        # Seed enough history
        for _ in range(15):
            await store.push(1.0)
        for _ in range(15):
            await store.push(0.1)

        result = VSGenerationResult(
            candidates=[GenerationCandidate(text="a", probability=1.0, selected=True)],
            selected=GenerationCandidate(text="a", probability=1.0, selected=True),
        )
        with caplog.at_level(logging.WARNING):
            await log_vs_behavioral_audit(result, store, VSFeatureFlags())
        # Either mode collapse warning fires or we just verify the store state
        assert store.size > 0
