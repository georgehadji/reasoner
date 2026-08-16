"""Tests for ara_verbalized_sampling primitives."""
from __future__ import annotations

import json
import math
from typing import Any

import pytest

from reasoner.reasoner_verbalized_sampling import (
    VSMode,
    VSCandidate,
    VSResult,
    build_vs_prompt,
    parse_vs_response,
    sample_from_vs,
    top_candidate,
    _strip_markdown_fences,
    _extract_json_block,
)


class TestVSCandidateModel:
    def test_valid_candidate(self) -> None:
        c = VSCandidate(text="hello", probability=0.5)
        assert c.text == "hello"
        assert c.probability == pytest.approx(0.5)

    def test_probability_bounds_enforced(self) -> None:
        with pytest.raises(Exception):  # pydantic validation error
            VSCandidate(text="x", probability=-0.1)
        with pytest.raises(Exception):
            VSCandidate(text="x", probability=1.1)

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(Exception):
            VSCandidate(text="", probability=0.5)


class TestVSResultNormalization:
    def test_uniform_fallback_on_all_zero(self) -> None:
        candidates = [
            VSCandidate(text="a", probability=0.0),
            VSCandidate(text="b", probability=0.0),
            VSCandidate(text="c", probability=0.0),
        ]
        result = VSResult(candidates=candidates, mode=VSMode.STANDARD)
        for c in result.candidates:
            assert c.probability == pytest.approx(1.0 / 3)

    def test_renormalize_off_by_five_percent(self) -> None:
        candidates = [
            VSCandidate(text="a", probability=0.5),
            VSCandidate(text="b", probability=0.4),
        ]
        result = VSResult(candidates=candidates, mode=VSMode.STANDARD)
        total = sum(c.probability for c in result.candidates)
        assert total == pytest.approx(1.0, abs=0.001)

    def test_no_change_when_already_normalized(self) -> None:
        candidates = [
            VSCandidate(text="a", probability=0.6),
            VSCandidate(text="b", probability=0.4),
        ]
        result = VSResult(candidates=candidates, mode=VSMode.STANDARD)
        assert result.candidates[0].probability == pytest.approx(0.6)
        assert result.candidates[1].probability == pytest.approx(0.4)

    def test_renormalize_large_deviation(self) -> None:
        candidates = [
            VSCandidate(text="a", probability=1.0),
            VSCandidate(text="b", probability=1.0),
            VSCandidate(text="c", probability=1.0),
        ]
        result = VSResult(candidates=candidates, mode=VSMode.STANDARD)
        for c in result.candidates:
            assert c.probability == pytest.approx(1.0 / 3)


class TestBuildVSPrompt:
    def test_returns_tuple(self) -> None:
        system, user = build_vs_prompt("What is 2+2?", VSMode.STANDARD)
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_standard_mode_no_tail_hint(self) -> None:
        system, _ = build_vs_prompt("Q", VSMode.STANDARD)
        assert "tail" not in system.lower()
        assert "step-by-step" not in system.lower()

    def test_tail_mode_includes_hint(self) -> None:
        system, _ = build_vs_prompt("Q", VSMode.TAIL)
        assert "tail" in system.lower()

    def test_cot_mode_includes_hint(self) -> None:
        system, _ = build_vs_prompt("Q", VSMode.COT)
        assert "step-by-step" in system.lower()

    def test_custom_k_override(self) -> None:
        system, _ = build_vs_prompt("Q", VSMode.STANDARD, k=7)
        assert "exactly 7" in system

    def test_default_k_present(self) -> None:
        system, _ = build_vs_prompt("Q", VSMode.STANDARD)
        assert "exactly" in system

    def test_user_prompt_contains_query(self) -> None:
        _, user = build_vs_prompt("What is 2+2?", VSMode.STANDARD)
        assert "What is 2+2?" in user

    def test_user_prompt_contains_json_schema(self) -> None:
        _, user = build_vs_prompt("Q", VSMode.STANDARD)
        assert '"candidates"' in user


class TestStripMarkdownFences:
    def test_no_fences_unchanged(self) -> None:
        raw = '{"candidates": []}'
        assert _strip_markdown_fences(raw) == raw

    def test_json_fence_removed(self) -> None:
        raw = '```json\n{"candidates": []}\n```'
        assert _strip_markdown_fences(raw) == '{"candidates": []}'

    def test_generic_fence_removed(self) -> None:
        raw = '```\n{"candidates": []}\n```'
        assert _strip_markdown_fences(raw) == '{"candidates": []}'

    def test_fences_with_extra_whitespace(self) -> None:
        raw = '   ```json   \n{"candidates": []}\n   ```   '
        assert _strip_markdown_fences(raw) == '{"candidates": []}'

    def test_multiple_fences_only_outer(self) -> None:
        raw = '```json\n{"candidates": [{"text": "```code```"}]}\n```'
        result = _strip_markdown_fences(raw)
        assert result.startswith('{"candidates"')
        assert not result.startswith('```')
        assert not result.endswith('```')

    def test_inline_backticks_preserved(self) -> None:
        raw = '`{"candidates": []}`'
        assert _strip_markdown_fences(raw) == raw

    def test_text_before_fence_preserved(self) -> None:
        raw = 'Here is the JSON:\n```json\n{"candidates": []}\n```'
        result = _strip_markdown_fences(raw)
        assert "Here is the JSON:" in result


class TestExtractJsonBlock:
    def test_valid_json_extracted(self) -> None:
        text = 'prefix {"candidates": [], "mode": "standard"} suffix'
        block = _extract_json_block(text)
        data = json.loads(block)
        assert "candidates" in data

    def test_no_candidates_raises(self) -> None:
        with pytest.raises(ValueError, match="No JSON candidate block"):
            _extract_json_block('{"other": []}')

    def test_nested_braces_balanced(self) -> None:
        text = '{"candidates": [{"text": "a", "probability": 0.5}]}'
        block = _extract_json_block(text)
        data = json.loads(block)
        assert data["candidates"][0]["text"] == "a"

    def test_multiple_objects_takes_first_with_candidates(self) -> None:
        text = '{"other": 1} {"candidates": [{"text": "x", "probability": 1}]}'
        block = _extract_json_block(text)
        data = json.loads(block)
        assert "candidates" in data

    def test_skips_invalid_json_objects(self) -> None:
        text = '{broken json} {"candidates": [{"text": "x", "probability": 1}]}'
        block = _extract_json_block(text)
        data = json.loads(block)
        assert "candidates" in data


class TestParseVSResponse:
    def test_basic_json(self) -> None:
        raw = '{"candidates": [{"text": "a", "probability": 0.5}, {"text": "b", "probability": 0.5}], "mode": "standard"}'
        result = parse_vs_response(raw)
        assert len(result.candidates) == 2
        assert result.mode == VSMode.STANDARD

    def test_json_with_fences(self) -> None:
        raw = '```json\n{"candidates": [{"text": "a", "probability": 1}], "mode": "tail"}\n```'
        result = parse_vs_response(raw)
        assert result.candidates[0].text == "a"
        assert result.mode == VSMode.TAIL

    def test_mode_defaults_to_standard(self) -> None:
        raw = '{"candidates": [{"text": "a", "probability": 1}]}'
        result = parse_vs_response(raw)
        assert result.mode == VSMode.STANDARD

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(Exception):
            parse_vs_response("not json at all")

    def test_missing_candidates_raises(self) -> None:
        with pytest.raises(ValueError, match="candidate block"):
            parse_vs_response('{"mode": "standard"}')

    def test_candidates_not_list_raises(self) -> None:
        with pytest.raises(ValueError, match="list"):
            parse_vs_response('{"candidates": "bad"}')

    def test_plain_text_with_embedded_json(self) -> None:
        raw = 'Sure! Here is the JSON:\n```json\n{"candidates": [{"text": "answer", "probability": 1.0}]}\n```'
        result = parse_vs_response(raw)
        assert result.candidates[0].text == "answer"


class TestSampleFromVS:
    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError):
            sample_from_vs([])

    def test_single_candidate_always_returns_it(self) -> None:
        c = VSCandidate(text="only", probability=1.0)
        for _ in range(10):
            assert sample_from_vs([c]).text == "only"

    def test_distribution_approximates_weights(self) -> None:
        """KL divergence between empirical and theoretical < 0.05."""
        candidates = [
            VSCandidate(text="a", probability=0.7),
            VSCandidate(text="b", probability=0.2),
            VSCandidate(text="c", probability=0.1),
        ]
        n = 10_000
        counts: dict[str, int] = {"a": 0, "b": 0, "c": 0}
        for _ in range(n):
            sampled = sample_from_vs(candidates)
            counts[sampled.text] += 1

        theoretical = [0.7, 0.2, 0.1]
        empirical = [counts["a"] / n, counts["b"] / n, counts["c"] / n]

        kl = 0.0
        for p, q in zip(theoretical, empirical, strict=False):
            if p > 0 and q > 0:
                kl += p * math.log(p / q)
        assert kl < 0.05, f"KL divergence {kl} too high"

    def test_zero_probability_candidate_never_sampled(self) -> None:
        candidates = [
            VSCandidate(text="a", probability=1.0),
            VSCandidate(text="b", probability=0.0),
        ]
        for _ in range(100):
            assert sample_from_vs(candidates).text == "a"


class TestTopCandidate:
    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError):
            top_candidate([])

    def test_single_candidate(self) -> None:
        c = VSCandidate(text="only", probability=1.0)
        assert top_candidate([c]).text == "only"

    def test_highest_probability_selected(self) -> None:
        candidates = [
            VSCandidate(text="low", probability=0.1),
            VSCandidate(text="high", probability=0.9),
        ]
        assert top_candidate(candidates).text == "high"

    def test_tie_breaks_to_first(self) -> None:
        c1 = VSCandidate(text="first", probability=0.5)
        c2 = VSCandidate(text="second", probability=0.5)
        assert top_candidate([c1, c2]).text == "first"
        assert top_candidate([c2, c1]).text == "second"

    def test_near_tie_resolved_by_precision(self) -> None:
        c1 = VSCandidate(text="a", probability=0.5000001)
        c2 = VSCandidate(text="b", probability=0.5)
        assert top_candidate([c1, c2]).text == "a"
