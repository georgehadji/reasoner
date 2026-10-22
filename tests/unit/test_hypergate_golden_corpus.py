"""HyperGate fast paths against a labelled corpus of real prompts (FLOW-5).

docs/plans/audit-remediation-2-2026-10-20.md FLOW-5: the regex fast paths
misrouted common inputs ("write a report generator" went to the writing
pipeline, "current value of a bond" to live web search, "what is the best
database" to a one-shot direct answer). Regexes drift silently; this corpus is
the spec they are held to. Rows live in tests/_data/hypergate_routing.jsonl:

- ``route``: what the fast paths alone decide, before any sub-agent runs.
  ``sub_agents`` means no fast path fires and the LLM sub-agents decide.
- ``research``: whether the research override (never answer directly) fires.

Add a row for every misroute you fix.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reasoner.hypergate.hyperagent import _RESEARCH_INDICATORS, fast_path

_ROWS = [
    json.loads(line)
    for line in (Path(__file__).resolve().parents[1] / "_data" / "hypergate_routing.jsonl")
    .read_text(encoding="utf-8").splitlines()
    if line.strip()
]


def _route(prompt: str) -> str:
    decision = fast_path(prompt)
    if decision is None:
        return "sub_agents"
    if decision.action == "pipeline":
        return decision.method or "pipeline"
    return decision.action


@pytest.mark.parametrize(
    "row", [r for r in _ROWS if "route" in r], ids=lambda r: r["prompt"][:50],
)
def test_fast_path_route(row):
    assert _route(row["prompt"]) == row["route"], row.get("note", "")


@pytest.mark.parametrize(
    "row", [r for r in _ROWS if "research" in r], ids=lambda r: r["prompt"][:50],
)
def test_research_override(row):
    fired = any(p.search(row["prompt"]) for p in _RESEARCH_INDICATORS)
    assert fired is row["research"], row.get("note", "")


def test_corpus_covers_every_route():
    assert {r["route"] for r in _ROWS if "route" in r} == {
        "direct", "web_search", "writing", "sub_agents",
    }
    assert len(_ROWS) >= 60
