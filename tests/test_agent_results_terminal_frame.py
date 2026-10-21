"""RUN-6: agent and MCP results read the run's `done` frame, not a later `end`.

The handler used to emit `{"type": "end"}` after the real `done`, and
`extract_terminal_frame` returned the last `done`/`end` frame. Every agent and
MCP result therefore reported cost 0, tokens 0 and no errors. Phase errors also
carry their text under `message`, which the error collector ignored.
"""

from __future__ import annotations

import pytest

from reasoner.application.services.agent_results import extract_terminal_frame, summarise

pytestmark = pytest.mark.unit


def test_done_frame_wins_over_a_trailing_end_frame() -> None:
    events = [
        {"type": "done", "total_cost_usd": 0.12, "total_tokens": {"input": 10, "output": 5, "total": 15}},
        {"type": "end", "data": {"synthesis": {"core_solution": "Completed"}}},
    ]

    assert extract_terminal_frame(events)["total_cost_usd"] == 0.12
    summary = summarise(events, preset="p")
    assert summary.total_cost_usd == 0.12
    assert summary.total_tokens["total"] == 15


def test_end_alone_is_not_a_terminal_frame() -> None:
    assert extract_terminal_frame([{"type": "end"}]) == {}


def test_phase_errors_keyed_by_message_are_reported() -> None:
    events = [
        {"type": "error", "phase": 2, "message": "Phase 2 timed out"},
        {"type": "done", "total_cost_usd": 0.12},
    ]

    summary = summarise(events, preset="p")

    assert "Phase 2 timed out" in summary.errors
    assert summary.total_cost_usd == 0.12
