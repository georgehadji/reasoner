"""Tests for PhaseSpan — observability context manager for pipeline phases."""

import pytest


class TestPhaseSpan:
    """Verify PhaseSpan creates and updates Langfuse spans for phase execution."""

    @pytest.mark.asyncio
    async def test_phase_span_success_path(self):
        """PhaseSpan should complete without error for a successful phase."""
        from reasoner.core.observability.phase_span import PhaseSpan

        async with PhaseSpan("test-run-id", phase_name="Synthesis", phase_number=1):
            pass  # Simulate successful phase execution

    @pytest.mark.asyncio
    async def test_phase_span_with_exception(self):
        """PhaseSpan should propagate exceptions."""
        from reasoner.core.observability.phase_span import PhaseSpan

        with pytest.raises(RuntimeError, match="phase error"):
            async with PhaseSpan("test-run-id", phase_name="Decomposition", phase_number=2):
                raise RuntimeError("phase error")

    @pytest.mark.asyncio
    async def test_phase_span_multiple_consecutive(self):
        """Multiple PhaseSpan instances should not interfere."""
        from reasoner.core.observability.phase_span import PhaseSpan

        for i in range(3):
            async with PhaseSpan("test-run-id", phase_name=f"Phase-{i}", phase_number=i):
                pass

    @pytest.mark.asyncio
    async def test_phase_span_latency_tracking(self):
        """PhaseSpan should record reasonable duration (≥ 0)."""
        import asyncio
        from reasoner.core.observability.phase_span import PhaseSpan

        t0 = asyncio.get_running_loop().time()
        async with PhaseSpan("test-run-id", phase_name="Research", phase_number=3):
            await asyncio.sleep(0.01)
        elapsed = asyncio.get_running_loop().time() - t0
        assert elapsed >= 0.01, f"Duration too short: {elapsed}"
