"""MP-7: a link the run never retrieved must not reach the answer.

The synthesis citation check used to log a warning and return the text
unchanged, for every method, so a model-invented URL shipped as a citation.
"""
from __future__ import annotations

import json

from reasoner.application.flows.synthesis_phase import (
    CITATION_REMOVED,
    enforce_citations,
    finalize_solution,
)
from reasoner.domain.pipeline_state import PipelineState

_ALLOWED = {"https://ok.example/a", "https://user.example/doc"}


def test_fabricated_markdown_link_is_unlinked_and_title_kept():
    text, removed = enforce_citations("See [Fake](https://fake.example/x) now.", _ALLOWED)

    assert text == f"See Fake {CITATION_REMOVED} now."
    assert removed == ["https://fake.example/x"]


def test_allowed_links_survive_including_trailing_slash_variants():
    src = "A [one](https://ok.example/a/) and https://ok.example/a, and [two](https://user.example/doc)."

    text, removed = enforce_citations(src, _ALLOWED)

    assert text == src
    assert removed == []


def test_bare_fabricated_url_is_removed_and_allowed_one_kept():
    text, removed = enforce_citations(
        "Read https://fake.example/y or https://ok.example/a.", _ALLOWED
    )

    assert "fake.example" not in text
    assert "https://ok.example/a." in text
    assert removed == ["https://fake.example/y"]


def test_urls_inside_code_are_left_alone():
    src = "Run `curl https://api.example/v1` or:\n```\nwget https://api.example/v2\n```\n"

    text, removed = enforce_citations(src, set())

    assert text == src
    assert removed == []


def test_repeated_fabricated_url_is_reported_once():
    _, removed = enforce_citations("https://f.example/z and [t](https://f.example/z)", set())

    assert removed == ["https://f.example/z"]


class _Services:
    def __init__(self):
        self.logs: list[str] = []

    def log(self, tag, message, state=None):
        self.logs.append(message)


def _reply(prose: str, sources) -> str:
    body = json.dumps({"critical_insights": [], "sources": sources})
    return "[SOLUTION]" + prose + "[/SOLUTION]\n```json\n" + body + "\n```"


def test_finalize_removes_disallowed_links_sources_and_reports_them():
    state = PipelineState(problem="Compare these. Context: https://user.example/doc")
    state.vetted_context = [{"url": "https://ok.example/a", "summary": "s"}]
    services = _Services()
    reply = _reply(
        "Good [A](https://ok.example/a), bad [B](https://fake.example/b), mine https://user.example/doc.",
        [
            {"title": "A", "url": "https://ok.example/a"},
            {"title": "B", "url": "https://fake.example/b"},
            {"title": "No link", "url": ""},
        ],
    )

    fs = finalize_solution(reply, state, services)

    assert "fake.example" not in fs.core_solution
    assert "https://ok.example/a" in fs.core_solution
    assert "https://user.example/doc" in fs.core_solution
    assert [s["title"] for s in fs.sources] == ["A", "No link"]
    assert state.meta.provenance_report["citations_removed"] == 1
    warnings = [e for e in state.pending_events if e.get("type") == "phase_warning"]
    assert len(warnings) == 1
    assert any("Citation integrity warning" in m for m in services.logs)


def test_prism_citations_count_as_retrieved():
    state = PipelineState(problem="p")
    state.method_state.set(
        "prism", {"citations": [{"title": "T", "url": "https://prism.example/p", "snippet": "s"}]}
    )

    fs = finalize_solution(_reply("See [T](https://prism.example/p).", []), state, _Services())

    assert "https://prism.example/p" in fs.core_solution
    assert state.meta.provenance_report["citations_removed"] == 0
