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
    async def test_phase_span_latency_tracking(self, fake_langfuse):
        """The duration PhaseSpan records is its own subtraction, driven by a fake clock.

        This measured ``asyncio.sleep(0.01)`` on the test's own loop clock and
        asserted the sleep had slept -- a fact about the OS timer rather than
        about PhaseSpan, and one that is false on Windows, where the default
        timer granularity (~15.6ms) lets both reads land in the same tick and
        return an identical value. It also never looked at the duration
        PhaseSpan reports, which is the only number that reaches Langfuse.
        """
        from reasoner.core.observability.phase_span import PhaseSpan

        clock = _FakeClock()
        async with PhaseSpan(
            "test-run-id", phase_name="Research", phase_number=3, clock=clock
        ):
            clock.advance(0.25)

        recorded = fake_langfuse.span_obj.updates[0]["output"]["duration_seconds"]
        assert recorded == 0.25, f"expected the elapsed 0.25s, got {recorded}"

    @pytest.mark.asyncio
    async def test_phase_span_duration_is_never_negative(self, fake_langfuse):
        """A clock that does not move must still yield a sane duration, not a negative.

        Guards the mixed-clock class of bug that
        test_span_records_a_wall_clock_start_and_the_state_enrichment covers on
        the timestamp side: subtracting two reads of different clocks can go
        backwards, and a negative duration is silently plausible to Langfuse.
        """
        from reasoner.core.observability.phase_span import PhaseSpan

        async with PhaseSpan(
            "test-run-id", phase_name="Research", phase_number=3, clock=_FakeClock()
        ):
            pass

        assert fake_langfuse.span_obj.updates[0]["output"]["duration_seconds"] == 0.0


class _FakeClock:
    """Deterministic Clock double (core/ports/clock.py): time only moves when a
    test moves it. A duration measured against the real clock is a measurement
    of the platform's timer resolution, not of the code under test.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def monotonic(self) -> float:
        return self._now

    def time(self) -> float:
        # Epoch-shaped, so a test asserting start_time/end_time are on the same
        # clock still sees two wall-clock-looking numbers.
        return 1_700_000_000.0 + self._now


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
