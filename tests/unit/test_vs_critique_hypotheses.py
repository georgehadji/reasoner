"""Unit tests for Verbalized-Sampling critique (review-hypotheses distribution).

Covers:
- _parse_review_hypotheses: happy path, probability sort/clamp, severity
  normalisation, dict->list coercion, malformed/empty skipping, non-list input
- critique_prompt: premium emits the review_hypotheses block; budget does not
- stress_test_prompt: seeds priority hypotheses when present, no-op when empty
- PipelineState round-trip: review_hypotheses survives to_dict/_from_dict
- premium gating maps through get_preset_price_tier
"""

from __future__ import annotations

from reasoner.core.parsing import _parse_review_hypotheses
from reasoner.domain.core_types import ReviewHypothesis
from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.preset_core import get_preset_price_tier
from reasoner.phases.multi_perspective import critique_prompt, stress_test_prompt


def _raw(claim: str, prob: float, **kw) -> dict:
    base = {
        "claim": claim,
        "probability": prob,
        "severity": "MED",
        "evidence_for": "f",
        "evidence_against": "a",
        "verification": "run test X",
        "cost_if_wrong": "data loss",
    }
    base.update(kw)
    return base


# ── _parse_review_hypotheses ────────────────────────────────────────────────

def test_parse_happy_path_sorted_descending_by_probability():
    raw = [_raw("low", 0.1), _raw("high", 0.8), _raw("mid", 0.4)]
    out = _parse_review_hypotheses(raw)
    assert [h.claim for h in out] == ["high", "mid", "low"]
    assert all(isinstance(h, ReviewHypothesis) for h in out)


def test_parse_clamps_probability_to_unit_interval():
    out = _parse_review_hypotheses([_raw("over", 1.7), _raw("under", -0.3)])
    probs = {h.claim: h.probability for h in out}
    assert probs["over"] == 1.0
    assert probs["under"] == 0.0


def test_parse_normalises_unknown_severity_to_low():
    out = _parse_review_hypotheses([_raw("x", 0.5, severity="catastrophic")])
    assert out[0].severity == "LOW"


def test_parse_uppercases_known_severity():
    out = _parse_review_hypotheses([_raw("x", 0.5, severity="high")])
    assert out[0].severity == "HIGH"


def test_parse_skips_entry_without_claim():
    out = _parse_review_hypotheses([_raw("", 0.9), _raw("keep", 0.2)])
    assert [h.claim for h in out] == ["keep"]


def test_parse_skips_non_dict_entries():
    out = _parse_review_hypotheses(["garbage", 42, _raw("keep", 0.5)])
    assert [h.claim for h in out] == ["keep"]


def test_parse_coerces_keyed_dict_to_list():
    out = _parse_review_hypotheses({"a": _raw("one", 0.3), "b": _raw("two", 0.6)})
    assert {h.claim for h in out} == {"one", "two"}


def test_parse_non_list_returns_empty():
    assert _parse_review_hypotheses(None) == []
    assert _parse_review_hypotheses("string") == []
    assert _parse_review_hypotheses([]) == []


def test_parse_missing_optional_fields_default_empty():
    out = _parse_review_hypotheses([{"claim": "bare", "probability": 0.5}])
    assert out[0].evidence_for == ""
    assert out[0].verification == ""
    assert out[0].cost_if_wrong == ""


# ── critique_prompt gating ──────────────────────────────────────────────────

def _state_with_candidates() -> PipelineState:
    from reasoner.domain.core_types import SolutionCandidate
    st = PipelineState(problem="Design a rate limiter")
    st.candidates = [
        SolutionCandidate(perspective="constructive", content="token bucket", key_insights=["a"], model_used="m"),
        SolutionCandidate(perspective="destructive", content="leaky bucket", key_insights=["b"], model_used="m"),
    ]
    return st


def test_critique_prompt_budget_omits_hypotheses_block():
    st = _state_with_candidates()
    prompt = critique_prompt(st, with_hypotheses=False)
    assert "review_hypotheses" not in prompt
    assert '"scores"' in prompt


def test_critique_prompt_premium_includes_hypotheses_block():
    st = _state_with_candidates()
    prompt = critique_prompt(st, with_hypotheses=True)
    assert "review_hypotheses" in prompt
    assert "cost_if_wrong" in prompt
    assert "NON-OVERLAPPING" in prompt


def test_critique_prompt_default_is_budget():
    st = _state_with_candidates()
    assert "review_hypotheses" not in critique_prompt(st)


# ── stress_test_prompt seeding ──────────────────────────────────────────────

def test_stress_prompt_seeds_priority_hypotheses():
    st = _state_with_candidates()
    st.top_candidates = st.candidates[:1]
    st.review_hypotheses = _parse_review_hypotheses(
        [_raw("race condition", 0.7), _raw("cache corruption", 0.5), _raw("stale state", 0.3), _raw("tail", 0.1)]
    )
    prompt = stress_test_prompt(st)
    assert "PRIORITY FAILURE HYPOTHESES" in prompt
    assert "race condition" in prompt
    # Only top-N (3) seeded — the 4th (lowest prob) is excluded.
    assert "tail" not in prompt


def test_stress_prompt_noop_without_hypotheses():
    st = _state_with_candidates()
    st.top_candidates = st.candidates[:1]
    prompt = stress_test_prompt(st)
    assert "PRIORITY FAILURE HYPOTHESES" not in prompt


# ── PipelineState round-trip ────────────────────────────────────────────────

def test_review_hypotheses_survive_serialization_round_trip():
    st = _state_with_candidates()
    st.review_hypotheses = _parse_review_hypotheses([_raw("flaw one", 0.6), _raw("flaw two", 0.3)])
    restored = PipelineState._from_dict(st.to_dict())
    assert [h.claim for h in restored.review_hypotheses] == ["flaw one", "flaw two"]
    assert restored.review_hypotheses[0].severity == "MED"
    assert all(isinstance(h, ReviewHypothesis) for h in restored.review_hypotheses)


def test_old_state_without_hypotheses_loads_clean():
    data = PipelineState(problem="x").to_dict()
    data["core"].pop("review_hypotheses", None)  # simulate pre-feature state file
    restored = PipelineState._from_dict(data)
    assert restored.review_hypotheses == []


# ── gating mapping ──────────────────────────────────────────────────────────

def test_premium_tier_gating_mapping():
    assert get_preset_price_tier("multi-perspective-premium") == "premium"
    assert get_preset_price_tier("multi-perspective-budget") == "budget"
    assert get_preset_price_tier("") == "unknown"
