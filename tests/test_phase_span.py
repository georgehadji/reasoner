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


class _FakeSpan:
    def __init__(self) -> None:
        self.updates: list[dict] = []

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class _FakeLangfuse:
    def __init__(self) -> None:
        self.span_kwargs: dict | None = None
        self.span_obj = _FakeSpan()

    def span(self, **kwargs):
        self.span_kwargs = kwargs
        return self.span_obj


@pytest.fixture
def fake_langfuse(monkeypatch):
    """Turn the span-creating path on with a client that records what it is told."""
    from reasoner.infrastructure.observability import langfuse_subscriber

    client = _FakeLangfuse()
    monkeypatch.setattr(langfuse_subscriber, "_langfuse_client", client)
    monkeypatch.setattr(langfuse_subscriber, "_is_langfuse_enabled", True)
    return client


def _state_with(phase_key: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        degradations=[],
        phase_tokens={phase_key: {"input": 11, "output": 7}},
        cost_state=SimpleNamespace(phase_costs_by_key={phase_key: 0.001234}),
        meta=SimpleNamespace(fallback_events=["a", "b"]),
    )


@pytest.mark.asyncio
async def test_span_records_a_wall_clock_start_and_the_state_enrichment(fake_langfuse):
    """P5, docs/plans/root-cause-remediation-2026-09-07.md.

    The span input carried ``time.monotonic()`` as "start_time" while the span
    output carried a ``time.time()`` end_time, so every Langfuse span recorded a
    start counted from an arbitrary origin and an end in epoch seconds.
    """
    from reasoner.core.observability.phase_span import PhaseSpan

    state = _state_with("Phase 2: Perspectives")
    async with PhaseSpan(
        "run-1", phase_name="Perspectives", phase_number=2, state=state
    ):
        pass

    started = fake_langfuse.span_kwargs["input"]["start_time"]
    ended = fake_langfuse.span_obj.updates[0]["end_time"]
    assert abs(ended - started) < 60, (
        f"start_time {started} is not on the same clock as end_time {ended}"
    )

    # The enrichment reads state by the same key the runner writes, so a rename
    # on either side silently empties every span rather than failing.
    output = fake_langfuse.span_obj.updates[0]["output"]
    assert output["tokens_total"] == 18
    assert output["cost_usd"] == 0.001234
    assert output["fallback_count"] == 2


@pytest.mark.asyncio
async def test_a_failing_router_describe_is_recorded_not_swallowed():
    """An empty model_hint is indistinguishable from a phase that had no model."""
    from types import SimpleNamespace

    from reasoner.core.observability.phase_span import PhaseSpan

    class _BrokenRouter:
        def describe(self):
            raise RuntimeError("router not wired")

    state = SimpleNamespace(degradations=[])
    async with PhaseSpan(
        "run-2",
        phase_name="Critique",
        phase_number=3,
        router=_BrokenRouter(),
        state=state,
    ):
        pass

    assert any(
        d.startswith("observability.phase_span.router_describe") for d in state.degradations
    ), f"expected the describe() failure to be recorded, got: {state.degradations}"
