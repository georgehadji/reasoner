"""Unit tests for the Verbalized Sampling brainstorming method.

Covers:
- vs_generation_prompt: threshold, round number, VS-Multi previous-ideas list, VS-CoT prefix
- vs_cluster_prompt: basic construction
- vs_develop_prompt: basic construction
- evaluate_rules for VS Idea Generation, Cluster & Score, Deep Development
- reset_phase_state for brainstorming phases
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

import pytest

from reasoner.phases.brainstorming import (
    vs_cluster_prompt,
    vs_develop_prompt,
    vs_generation_prompt,
)
from reasoner.quality.criteria import evaluate_rules, reset_phase_state


# ─────────────────────────────────────────────────────────────────────────────
# Minimal state stubs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _State:
    """Minimal PipelineState-like stub for prompt builders."""
    problem: str = "How can we reduce urban heat islands?"
    task_type: Any = None
    decomposition: Any = None
    candidates: list = field(default_factory=list)
    scores: list = field(default_factory=list)
    top_candidates: list = field(default_factory=list)
    stress_results: list = field(default_factory=list)
    final_solution: Any = None
    writing_state: dict = field(default_factory=dict)
    phase_tokens: dict = field(default_factory=dict)
    quality_hints: dict = field(default_factory=dict)
    brainstorming_state: dict = field(default_factory=dict)
    # get_language_instruction reads state.language
    language: str = "English"


# ─────────────────────────────────────────────────────────────────────────────
# vs_generation_prompt
# ─────────────────────────────────────────────────────────────────────────────

class TestVsGenerationPrompt:
    def test_includes_threshold(self):
        state = _State(problem="How to reduce urban heat islands?")
        prompt = vs_generation_prompt(state, round_num=1, k=5, threshold=0.10,
                                      n_tail=2, previous_ideas=[])
        # Python repr of 0.10 is "0.1"; check both forms
        assert "0.1" in prompt

    def test_includes_k(self):
        state = _State(problem="Design a better commute.")
        prompt = vs_generation_prompt(state, round_num=1, k=7, threshold=0.10,
                                      n_tail=2, previous_ideas=[])
        assert "7 ideas" in prompt

    def test_includes_round_number(self):
        state = _State(problem="...")
        prompt = vs_generation_prompt(state, round_num=3, k=5, threshold=0.10,
                                      n_tail=2, previous_ideas=[])
        assert "Round 3" in prompt

    def test_vs_multi_includes_previous_ideas(self):
        state = _State(problem="...")
        prev = [{"title": "Green Roofs"}, {"title": "Cool Pavements"}]
        prompt = vs_generation_prompt(state, round_num=2, k=5, threshold=0.10,
                                      n_tail=2, previous_ideas=prev)
        assert "Green Roofs" in prompt
        assert "Cool Pavements" in prompt
        assert "do not repeat" in prompt.lower()

    def test_no_previous_section_on_first_round(self):
        state = _State(problem="...")
        prompt = vs_generation_prompt(state, round_num=1, k=5, threshold=0.10,
                                      n_tail=2, previous_ideas=[])
        assert "Previously generated" not in prompt

    def test_cot_prefix_present_when_enabled(self):
        state = _State(problem="...")
        prompt = vs_generation_prompt(state, round_num=1, k=5, threshold=0.10,
                                      n_tail=2, previous_ideas=[], use_cot=True)
        assert "step by step" in prompt.lower()

    def test_no_cot_prefix_when_disabled(self):
        state = _State(problem="...")
        prompt = vs_generation_prompt(state, round_num=1, k=5, threshold=0.10,
                                      n_tail=2, previous_ideas=[], use_cot=False)
        assert "step by step" not in prompt.lower()

    def test_n_tail_in_prompt(self):
        state = _State(problem="...")
        prompt = vs_generation_prompt(state, round_num=1, k=5, threshold=0.10,
                                      n_tail=3, previous_ideas=[])
        assert "3 ideas" in prompt or "at least 3" in prompt

    def test_problem_in_prompt(self):
        state = _State(problem="Make hospitals more efficient.")
        prompt = vs_generation_prompt(state, round_num=1, k=5, threshold=0.10,
                                      n_tail=2, previous_ideas=[])
        assert "hospitals" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# vs_cluster_prompt
# ─────────────────────────────────────────────────────────────────────────────

class TestVsClusterPrompt:
    def test_includes_idea_count(self):
        state = _State(problem="...")
        ideas = [{"id": f"I{i}", "title": f"Idea {i}"} for i in range(8)]
        prompt = vs_cluster_prompt(state, ideas)
        assert "8 ideas" in prompt

    def test_problem_in_prompt(self):
        state = _State(problem="Improve public transport.")
        prompt = vs_cluster_prompt(state, [])
        assert "transport" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# vs_develop_prompt
# ─────────────────────────────────────────────────────────────────────────────

class TestVsDevelopPrompt:
    def test_includes_idea_count(self):
        state = _State(problem="...")
        ideas = [{"id": "I1", "title": "Green Corridor"}, {"id": "I2", "title": "Mist Systems"}]
        prompt = vs_develop_prompt(state, ideas)
        assert "2 selected ideas" in prompt

    def test_idea_titles_in_prompt(self):
        state = _State(problem="...")
        ideas = [{"id": "I1", "title": "Green Corridor"}]
        prompt = vs_develop_prompt(state, ideas)
        assert "Green Corridor" in prompt


# ─────────────────────────────────────────────────────────────────────────────
# Quality rules — VS Idea Generation
# ─────────────────────────────────────────────────────────────────────────────

class TestBrainstormGenerateRules:
    def test_fail_no_ideas(self):
        state = _State(brainstorming_state={})
        result = evaluate_rules("VS Idea Generation", state)
        assert not result.passed

    def test_fail_empty_raw_ideas(self):
        state = _State(brainstorming_state={"raw_ideas": []})
        result = evaluate_rules("VS Idea Generation", state)
        assert not result.passed

    def test_pass_with_tail_ideas(self):
        state = _State(brainstorming_state={
            "raw_ideas": [
                {"probability": 0.08},   # tail idea
                {"probability": 0.50},   # conventional
            ]
        })
        result = evaluate_rules("VS Idea Generation", state)
        assert result.passed
        assert result.score == 9.0

    def test_partial_pass_no_tail(self):
        """Ideas generated but none are tail — diversity warning, still passes."""
        state = _State(brainstorming_state={
            "raw_ideas": [
                {"probability": 0.50},
                {"probability": 0.60},
            ]
        })
        result = evaluate_rules("VS Idea Generation", state)
        assert result.passed
        assert result.score < 9.0

    def test_pass_score_reflects_tail_presence(self):
        state_with_tail = _State(brainstorming_state={"raw_ideas": [{"probability": 0.05}]})
        state_no_tail = _State(brainstorming_state={"raw_ideas": [{"probability": 0.80}]})
        with_tail = evaluate_rules("VS Idea Generation", state_with_tail)
        no_tail = evaluate_rules("VS Idea Generation", state_no_tail)
        assert with_tail.score > no_tail.score


# ─────────────────────────────────────────────────────────────────────────────
# Quality rules — Cluster & Score
# ─────────────────────────────────────────────────────────────────────────────

class TestBrainstormClusterRules:
    def test_fail_no_clusters(self):
        state = _State(brainstorming_state={"clusters": []})
        result = evaluate_rules("Cluster & Score", state)
        assert not result.passed

    def test_fail_no_top_ideas(self):
        state = _State(brainstorming_state={
            "clusters": [{"theme": "T1", "ideas": []}],
            "top_ideas": [],
        })
        result = evaluate_rules("Cluster & Score", state)
        assert not result.passed

    def test_pass(self):
        state = _State(brainstorming_state={
            "clusters": [{"theme": "T1", "ideas": [{"title": "A", "keep": True}]}],
            "top_ideas": [{"title": "A"}],
        })
        result = evaluate_rules("Cluster & Score", state)
        assert result.passed

    def test_fail_missing_clusters_key(self):
        state = _State(brainstorming_state={})
        result = evaluate_rules("Cluster & Score", state)
        assert not result.passed


# ─────────────────────────────────────────────────────────────────────────────
# Quality rules — Deep Development
# ─────────────────────────────────────────────────────────────────────────────

class TestBrainstormDevelopRules:
    def test_fail_no_developments(self):
        state = _State(brainstorming_state={})
        result = evaluate_rules("Deep Development", state)
        assert not result.passed

    def test_fail_all_thin(self):
        state = _State(brainstorming_state={
            "developments": [{"use_case": "short"}, {"use_case": "also short"}]
        })
        result = evaluate_rules("Deep Development", state)
        assert not result.passed
        assert result.score <= 4.0

    def test_pass(self):
        long_use_case = "This idea involves a comprehensive urban redesign that..." + "x" * 100
        state = _State(brainstorming_state={
            "developments": [{"use_case": long_use_case}]
        })
        result = evaluate_rules("Deep Development", state)
        assert result.passed

    def test_partial_thin_still_passes(self):
        """Some thin, some good — should pass (only fails if ALL are thin)."""
        long_use_case = "x" * 60
        state = _State(brainstorming_state={
            "developments": [
                {"use_case": "short"},
                {"use_case": long_use_case},
            ]
        })
        result = evaluate_rules("Deep Development", state)
        assert result.passed


# ─────────────────────────────────────────────────────────────────────────────
# State reset
# ─────────────────────────────────────────────────────────────────────────────

class TestBrainstormReset:
    def test_reset_vs_idea_generation_clears_state(self):
        state = _State(brainstorming_state={"raw_ideas": [{"title": "A"}], "config": {"rounds": 3}})
        reset_phase_state("VS Idea Generation", state)
        assert state.brainstorming_state == {}

    def test_reset_cluster_and_score_removes_clusters(self):
        state = _State(brainstorming_state={
            "clusters": [{"theme": "T1"}],
            "top_ideas": [{"title": "A"}],
            "raw_ideas": [{"title": "A"}],   # should survive
        })
        reset_phase_state("Cluster & Score", state)
        assert "clusters" not in state.brainstorming_state
        assert "top_ideas" not in state.brainstorming_state
        # raw_ideas should survive (not cleared by cluster reset)
        assert "raw_ideas" in state.brainstorming_state

    def test_reset_deep_development_removes_developments(self):
        state = _State(brainstorming_state={
            "developments": [{"title": "A"}],
            "top_ideas": [{"title": "A"}],   # should survive
        })
        reset_phase_state("Deep Development", state)
        assert "developments" not in state.brainstorming_state
        assert "top_ideas" in state.brainstorming_state

    def test_reset_clears_phase_tokens(self):
        state = _State(
            brainstorming_state={"raw_ideas": []},
            phase_tokens={"Phase VS Idea Generation attempt 1": {"input": 100, "output": 200}},
        )
        reset_phase_state("VS Idea Generation", state)
        assert state.phase_tokens == {}
