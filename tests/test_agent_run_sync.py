"""Tests for POST /api/agent/run/sync result assembly.

Regression cover for a bug where ``critical_insights``, ``open_questions``, and
``citations`` were read off the terminal ``done`` SSE frame. That frame has
never carried them — it holds only ``type``, ``errors``, ``total_tokens``,
``duration``, ``total_cost_usd``, and ``phase_costs`` — so every caller of this
endpoint received three permanently empty lists.

The values live on phase payloads instead:

* ``critical_insights`` / ``open_questions`` — beside ``core_solution`` in the
  synthesis payload built by ``_ser_synthesis``.
* ``citations`` — on their own phase via ``_ser_5``, which emits no
  ``core_solution``, so they need a scan of their own.

The extraction lives in ``application/services/agent_results.py`` precisely so
it can be tested without importing the FastAPI app, which takes minutes.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from reasoner.application.services.agent_results import (
    coerce_dict_list,
    coerce_string_list,
    extract_citations,
    extract_synthesis_payload,
)


def _phase(phase: int, name: str, data: dict[str, Any] | None = None, **extra: Any) -> dict:
    event: dict[str, Any] = {"type": "phase_complete", "phase": phase, "name": name}
    if data is not None:
        event["data"] = data
    event.update(extra)
    return event


SYNTHESIS_DATA: dict[str, Any] = {
    "core_solution": "Migrate incrementally, starting with billing.",
    "critical_insights": ["The monolith is not the bottleneck; the deploy pipeline is."],
    "action_blueprint": [{"step": "1", "action": "Extract billing"}],
    "open_questions": ["What is the current deploy cadence?"],
    "claim_labels": {"The pipeline is the bottleneck": "VERIFIED"},
    "tokens": {"input": 5100, "output": 2400},
}

CITATIONS = [
    {"url": "https://example.com/a", "title": "A", "source_type": "web"},
    {"url": "https://example.com/b", "title": "B", "source_type": "academic"},
]

DONE_FRAME: dict[str, Any] = {
    "type": "done",
    "errors": [],
    "total_tokens": {"input": 8213, "output": 3944, "total": 12157},
    "duration": 41.2,
    "total_cost_usd": 0.0191,
    "phase_costs": {"5": 0.012},
}


def _full_stream() -> list[dict]:
    """A research-method stream: citations and synthesis land on different phases."""
    return [
        {"type": "start", "preset": "research-budget"},
        _phase(2, "Search", {"citations": CITATIONS}),
        _phase(3, "Analysis", {"models": ["deepseek-v3"]}),
        _phase(5, "Synthesis", SYNTHESIS_DATA),
        DONE_FRAME,
    ]


# ── The regression ──────────────────────────────────────────────────


@pytest.mark.unit
def test_insights_and_open_questions_come_from_the_synthesis_payload():
    payload = extract_synthesis_payload(_full_stream())

    assert payload["core_solution"] == SYNTHESIS_DATA["core_solution"]
    assert payload["critical_insights"] == SYNTHESIS_DATA["critical_insights"]
    assert payload["open_questions"] == SYNTHESIS_DATA["open_questions"]


@pytest.mark.unit
def test_citations_come_from_their_own_phase_not_the_synthesis_one():
    events = _full_stream()

    # The heart of the bug: these two live in different places.
    assert "citations" not in extract_synthesis_payload(events)
    assert extract_citations(events) == CITATIONS


@pytest.mark.unit
def test_the_done_frame_carries_none_of_these_fields():
    """Pins why reading them off `done` was always wrong.

    If someone reintroduces `done.get("critical_insights")`, this states plainly
    that the frame has nothing to offer, rather than leaving the next reader to
    rediscover it.
    """
    assert "critical_insights" not in DONE_FRAME
    assert "open_questions" not in DONE_FRAME
    assert "citations" not in DONE_FRAME


# ── Synthesis payload extraction ────────────────────────────────────


@pytest.mark.unit
def test_prefers_the_last_phase_that_produced_a_solution():
    events = [
        _phase(2, "Draft", {"core_solution": "early draft", "critical_insights": ["stale"]}),
        _phase(5, "Synthesis", {"core_solution": "final", "critical_insights": ["fresh"]}),
    ]

    payload = extract_synthesis_payload(events)

    assert payload["core_solution"] == "final"
    assert payload["critical_insights"] == ["fresh"]


@pytest.mark.unit
def test_unwraps_a_nested_core_solution():
    """Some methods nest the solution one level deeper."""
    events = [_phase(5, "Synthesis", {"core_solution": {"core_solution": "unwrapped"}})]

    assert extract_synthesis_payload(events)["core_solution"] == "unwrapped"


@pytest.mark.unit
def test_unwraps_a_nested_synthesis_key():
    events = [_phase(5, "Synthesis", {"core_solution": {"synthesis": "from synthesis key"}})]

    assert extract_synthesis_payload(events)["core_solution"] == "from synthesis key"


@pytest.mark.unit
def test_returns_empty_when_the_run_crashed_before_synthesising():
    crashed = [{"type": "done", "errors": ["Pipeline processing error: TimeoutError"]}]

    assert extract_synthesis_payload(crashed) == {}
    assert extract_citations(crashed) == []


@pytest.mark.unit
def test_ignores_phases_whose_data_is_missing_or_not_a_dict():
    events = [
        _phase(4, "No data at all", None),
        {"type": "phase_complete", "phase": 4, "data": "not a dict"},
        _phase(5, "Synthesis", SYNTHESIS_DATA),
    ]

    assert extract_synthesis_payload(events)["core_solution"] == SYNTHESIS_DATA["core_solution"]


@pytest.mark.unit
def test_ignores_a_blank_core_solution():
    events = [
        _phase(5, "Synthesis", {"core_solution": "", "critical_insights": ["should not win"]}),
    ]

    assert extract_synthesis_payload(events) == {}


@pytest.mark.unit
def test_skips_phases_with_empty_citations():
    events = [
        _phase(2, "Search", {"citations": []}),
        _phase(3, "Deeper search", {"citations": CITATIONS}),
    ]

    assert extract_citations(events) == CITATIONS


# ── Defensive coercion ──────────────────────────────────────────────


@pytest.mark.unit
def test_malformed_list_entries_are_dropped_rather_than_raising():
    """RunResult declares list[str]; a bad element would 500 an already-paid run."""
    assert coerce_string_list(["ok", 42, None, {"a": 1}, "also ok"]) == ["ok", "also ok"]
    assert coerce_string_list("not a list") == []
    assert coerce_string_list(None) == []


@pytest.mark.unit
def test_malformed_citation_entries_are_dropped():
    assert coerce_dict_list([{"url": "a"}, "junk", None]) == [{"url": "a"}]
    assert coerce_dict_list({"not": "a list"}) == []


@pytest.mark.unit
def test_a_wholly_malformed_synthesis_payload_yields_empty_lists():
    """End-to-end shape of what the handler passes to RunResult."""
    events = [
        _phase(
            5,
            "Synthesis",
            {"core_solution": "text", "critical_insights": "not a list", "open_questions": None},
        )
    ]
    payload = extract_synthesis_payload(events)

    assert coerce_string_list(payload.get("critical_insights")) == []
    assert coerce_string_list(payload.get("open_questions")) == []


# ── The endpoint itself ─────────────────────────────────────────────


@pytest.mark.slow
@pytest.mark.timeout(900)
@pytest.mark.integration
async def test_agent_run_sync_returns_populated_insights(monkeypatch):
    """Drive the real handler over a stubbed stream.

    Marked slow because importing ``reasoner.api`` takes minutes; the pure
    extraction above is what gives fast feedback. This exists to prove the
    handler is actually wired to that extraction, which is the thing the
    original bug got wrong.
    """
    import reasoner.api  # noqa: F401 -- import side effects register the app
    import reasoner.api.streaming as streaming
    from reasoner.api.routes.agent import agent_run_sync
    from reasoner.api.run_observability import CreditSink
    from reasoner.api.schemas import RunRequest

    async def fake_stream(
        req, request=None, user_id=None, preset_service=None, pipeline_service=None
    ):
        for event in _full_stream():
            yield f"data: {json.dumps(event)}\n\n"

    settled: list[dict] = []

    async def fake_settle(self, **kwargs):
        settled.append(kwargs)

    # The handler imports run_stream_cached at call time, so patching the
    # module attribute is enough.
    monkeypatch.setattr(streaming, "run_stream_cached", fake_stream)
    monkeypatch.setattr(CreditSink, "settle", fake_settle)

    fake_user = type("User", (), {"id": "test-user"})()

    result = await agent_run_sync(
        request=None,
        req=RunRequest(problem="Should we migrate off our monolith?", preset="auto-budget"),
        user=fake_user,
        _rate_limited=True,
        _quota=None,
        _credits=None,
    )

    assert result.synthesis == SYNTHESIS_DATA["core_solution"]
    assert result.critical_insights == SYNTHESIS_DATA["critical_insights"]
    assert result.open_questions == SYNTHESIS_DATA["open_questions"]
    assert result.citations == CITATIONS
    assert result.total_tokens == DONE_FRAME["total_tokens"]
    assert result.duration_seconds == DONE_FRAME["duration"]

    # And the whole point of this workstream: a sync agent run settles once,
    # at the cost the run actually reported.
    assert settled == [
        {
            "user_id": "test-user",
            "cost_usd": DONE_FRAME["total_cost_usd"],
            "reference_id": settled[0]["reference_id"],
            "preset": "auto-budget",
        }
    ]
