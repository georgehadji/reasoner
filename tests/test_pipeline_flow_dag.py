"""Tests for DAG-based phase execution in PipelineFlow."""

from __future__ import annotations

import asyncio

import pytest

from reasoner.application.flows.pipeline_flow import PhaseStep, execute_phases_dag
from reasoner.models import PipelineState


class TestExecutePhasesDag:
    """Dependency-aware parallel phase execution."""

    @pytest.fixture
    def state(self):
        return PipelineState(problem="test dag")

    @pytest.fixture
    def run_phase_fn(self):
        """A simple runner that just calls the phase function."""
        async def _run(fn, st):
            await fn(st)
        return _run

    @pytest.mark.asyncio
    async def test_sequential_phases(self, state, run_phase_fn):
        order = []

        async def phase_a(st):
            order.append("A")

        async def phase_b(st):
            order.append("B")

        phases = [
            PhaseStep(0, "A", phase_a, lambda s: {}),
            PhaseStep(1, "B", phase_b, lambda s: {}, depends_on=["A"]),
        ]
        await execute_phases_dag(phases, state, run_phase_fn)
        assert order == ["A", "B"]

    @pytest.mark.asyncio
    async def test_parallel_independent_phases(self, state, run_phase_fn):
        order = []
        barrier = asyncio.Barrier(2)

        async def phase_a(st):
            await barrier.wait()
            order.append("A")

        async def phase_b(st):
            await barrier.wait()
            order.append("B")

        phases = [
            PhaseStep(0, "A", phase_a, lambda s: {}),
            PhaseStep(0, "B", phase_b, lambda s: {}),
        ]
        await execute_phases_dag(phases, state, run_phase_fn)
        # Both ran (order may vary due to parallelism)
        assert set(order) == {"A", "B"}

    @pytest.mark.asyncio
    async def test_mixed_parallel_and_serial(self, state, run_phase_fn):
        order = []
        barrier = asyncio.Barrier(2)

        async def phase_a(st):
            await barrier.wait()
            order.append("A")

        async def phase_b(st):
            await barrier.wait()
            order.append("B")

        async def phase_c(st):
            order.append("C")

        phases = [
            PhaseStep(0, "A", phase_a, lambda s: {}),
            PhaseStep(0, "B", phase_b, lambda s: {}),
            PhaseStep(1, "C", phase_c, lambda s: {}, depends_on=["A", "B"]),
        ]
        await execute_phases_dag(phases, state, run_phase_fn)
        assert set(order[:2]) == {"A", "B"}
        assert order[2] == "C"

    @pytest.mark.asyncio
    async def test_circular_dependency_raises(self, state, run_phase_fn):
        async def phase_a(st):
            pass

        async def phase_b(st):
            pass

        phases = [
            PhaseStep(0, "A", phase_a, lambda s: {}, depends_on=["B"]),
            PhaseStep(0, "B", phase_b, lambda s: {}, depends_on=["A"]),
        ]
        with pytest.raises(RuntimeError, match="Circular dependency"):
            await execute_phases_dag(phases, state, run_phase_fn)

    @pytest.mark.asyncio
    async def test_phase_exception_is_recorded_not_propagated(self, state, run_phase_fn):
        """A failing phase is captured on state.errors rather than aborting the run.

        The DAG gathers with return_exceptions=True so one broken non-critical phase
        cannot take down the whole pipeline; only a critical phase stops execution.
        """
        async def phase_a(st):
            raise ValueError("boom")

        phases = [
            PhaseStep(0, "A", phase_a, lambda s: {}),
        ]
        await execute_phases_dag(phases, state, run_phase_fn)

        assert any("boom" in err for err in state.errors)

    @pytest.mark.asyncio
    async def test_critical_phase_failure_halts_dag(self, state, run_phase_fn):
        ran = []

        async def phase_a(st):
            raise ValueError("boom")

        async def phase_b(st):
            ran.append("B")

        phases = [
            PhaseStep(0, "A", phase_a, lambda s: {}, critical=True),
            PhaseStep(1, "B", phase_b, lambda s: {}, depends_on=["A"]),
        ]
        await execute_phases_dag(phases, state, run_phase_fn)

        assert ran == []

    @pytest.mark.asyncio
    async def test_empty_phases(self, state, run_phase_fn):
        await execute_phases_dag([], state, run_phase_fn)
        # Should complete without error
