"""P5: a swallowed failure must leave evidence.

docs/plans/root-cause-remediation-2026-09-07.md P5. D11 is the archetype --
rerank_via_nemotron returned its input unchanged for every call, for as long as
its default model id was absent from the catalogue, and the only trace was a
DEBUG line nobody reads. The contract is that a site which chooses to continue
logs at WARNING, increments a counter, and records to PipelineState so the run
can say it degraded.
"""

from __future__ import annotations

import logging

import pytest

from reasoner.core.degrade import degraded
from reasoner.domain.pipeline_state import PipelineState


def _state() -> PipelineState:
    return PipelineState(problem="p")


def test_returns_the_fallback_unchanged():
    """`return degraded(...)` must be a drop-in for `return fallback`."""
    sentinel = ["a", "b"]
    assert degraded("t.site", sentinel, exc=ValueError("x")) is sentinel


def test_records_to_pipeline_state():
    state = _state()
    degraded("rerank.nemotron", None, exc=RuntimeError("404"), state=state)

    assert len(state.degradations) == 1
    entry = state.degradations[0]
    assert entry.startswith("rerank.nemotron: ")
    assert "RuntimeError" in entry
    assert "404" in entry


def test_logs_at_warning_not_debug(caplog):
    """DEBUG is what made D11 invisible for as long as it lasted."""
    with caplog.at_level(logging.WARNING, logger="reasoner.core.degrade"):
        degraded("t.site", None, exc=ValueError("boom"))

    records = [r for r in caplog.records if r.name == "reasoner.core.degrade"]
    assert records, "nothing logged"
    assert records[0].levelno == logging.WARNING
    assert "site=t.site" in records[0].getMessage()


def test_state_is_optional_and_a_bad_state_never_raises():
    """The helper sits in an except block; it must not raise a second error."""
    assert degraded("t.site", 42, exc=ValueError("x")) == 42
    assert degraded("t.site", 42, exc=ValueError("x"), state=object()) == 42


def test_degradations_defaults_empty_on_a_fresh_state():
    """Additive and defaulted, so `--resume` on older state files still loads."""
    assert _state().degradations == []


def test_detail_is_appended_to_the_reason():
    state = _state()
    degraded("t.site", None, exc=ValueError("x"), state=state, detail="model=foo")
    assert "model=foo" in state.degradations[0]


# ── P5 step 5: which provider failures must stop the run ──

@pytest.mark.parametrize(
    "factory, fatal",
    [
        (lambda: __import__("reasoner.core.exceptions", fromlist=["x"])
            .ProviderCreditsExhaustedError("no credit"), True),
        (lambda: __import__("reasoner.core.exceptions", fromlist=["x"])
            .AuthenticationError("bad key"), True),
        # Not run-fatal: the next phase routes to a different model.
        (lambda: __import__("reasoner.core.exceptions", fromlist=["x"])
            .ModelNotFoundError("no such model"), False),
        (lambda: __import__("reasoner.core.exceptions", fromlist=["x"])
            .RateLimitError("429"), False),
        (lambda: __import__("reasoner.core.exceptions", fromlist=["x"])
            .ProviderUnavailableError("503"), False),
        (lambda: ValueError("unrelated"), False),
    ],
)
def test_is_run_fatal_separates_run_ending_from_phase_ending(factory, fatal):
    """`not is_retryable` is too broad to decide this.

    A 404 is not retryable, but the run should continue: the next phase routes
    elsewhere. An empty credit balance fails every remaining phase identically,
    so continuing only produces a synthesis over missing phases and reports it
    as a success.
    """
    from reasoner.core.exceptions import is_run_fatal

    assert is_run_fatal(factory()) is fatal
