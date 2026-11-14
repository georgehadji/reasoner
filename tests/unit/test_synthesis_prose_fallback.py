"""Prose rebuilt from a JSON-only synthesis keeps its action steps.

A model that skips the [SOLUTION] block gets its prose rebuilt from the JSON.
Plain-string blueprint steps were dropped there while the heading stayed, so
a live CoVE run showed "Action Blueprint:" with nothing under it.
"""
import json
from types import SimpleNamespace

from reasoner.application.flows.synthesis_phase import finalize_solution
from reasoner.domain.pipeline_state import PipelineState


def _prose(blueprint) -> str:
    raw = "```json\n" + json.dumps({
        "critical_insights": ["A"], "action_blueprint": blueprint, "open_questions": ["Q?"],
    }) + "\n```"
    services = SimpleNamespace(log=lambda *a, **k: None)
    return finalize_solution(raw, PipelineState(problem="p"), services).core_solution


def test_string_steps_are_kept():
    assert "Action Blueprint:\n- Do X\n- Do Y" in _prose(["Do X", "Do Y"])


def test_no_heading_without_steps():
    assert "Action Blueprint" not in _prose([{"description": "neither step nor action"}])
