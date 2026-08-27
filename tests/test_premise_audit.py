"""W2 — premise audit.

See docs/plans/sycophancy-mitigation.md W2. Phase 1's assumptions gain
origin/load_bearing/falsifier/resolvable_by; _parse_premises is the defensive
projection that also enforces the one rule that matters: a user-origin
assumption cannot stay VERIFIED on the user's word alone.
"""

from __future__ import annotations

from reasoner.core.parsing import _parse_premises
from reasoner.domain.models import ClaimLabel
from reasoner.domain.pipeline_state import PipelineState
from reasoner.phases.multi_perspective import perspective_prompt


def test_parse_premises_normalizes_origin_and_label() -> None:
    out = _parse_premises([
        {"text": "They never listen", "origin": "USER_STATED", "label": "hypothesis"},
    ])
    assert len(out) == 1
    assert out[0].origin == "user_stated"
    assert out[0].label == ClaimLabel.HYPOTHESIS


def test_parse_premises_skips_malformed_entries() -> None:
    out = _parse_premises([
        {"text": ""},              # no text — skipped
        "not a dict",               # wrong type — skipped
        {"text": "valid one"},
    ])
    assert len(out) == 1
    assert out[0].text == "valid one"


def test_parse_premises_handles_dict_input() -> None:
    out = _parse_premises({"0": {"text": "a"}, "1": {"text": "b"}})
    assert len(out) == 2


def test_parse_premises_rejects_non_list_non_dict() -> None:
    assert _parse_premises("garbage") == []
    assert _parse_premises(None) == []


def test_user_origin_premise_cannot_be_verified_without_source_hint() -> None:
    out = _parse_premises([
        {"text": "my sibling never repays me", "origin": "user_stated", "label": "VERIFIED"},
    ])
    assert out[0].label == ClaimLabel.HYPOTHESIS  # downgraded — user is not a source
    assert out[0].resolvable_by == "other_party"  # defaulted for user-origin claims


def test_user_origin_premise_with_source_hint_stays_verified() -> None:
    out = _parse_premises([
        {"text": "the invoice is dated March 3", "origin": "user_stated", "label": "VERIFIED", "source_hint": "invoice.pdf"},
    ])
    assert out[0].label == ClaimLabel.VERIFIED


def test_analyst_origin_premise_can_be_verified_without_source_hint() -> None:
    # The downgrade rule is specific to user-origin claims; an analyst-introduced
    # assumption the model itself verified is not subject to it.
    out = _parse_premises([
        {"text": "the sky is blue", "origin": "analyst", "label": "VERIFIED"},
    ])
    assert out[0].label == ClaimLabel.VERIFIED


def test_premises_cap_and_load_bearing_first() -> None:
    raw = [{"text": f"p{i}", "load_bearing": i % 2 == 0} for i in range(10)]
    out = _parse_premises(raw)
    assert len(out) == 6  # PREMISE_MAX_CLAIMS
    assert all(p.load_bearing for p in out[:5])  # 5 load-bearing entries exist (i=0,2,4,6,8)


def _state_with_assumptions(assumptions: list[dict]) -> PipelineState:
    state = PipelineState(problem="Should I cut off my sibling over unpaid debt?")
    state.decomposition = {"causal_chain": [], "assumptions": assumptions, "failure_modes": [], "critical_sources": []}
    return state


def test_destructive_perspective_receives_user_premises() -> None:
    state = _state_with_assumptions([
        {"text": "my sibling never repays me", "origin": "user_stated", "label": "HYPOTHESIS"},
    ])
    prompt = perspective_prompt(state, "destructive")
    assert "USER PREMISES" in prompt
    assert "my sibling never repays me" in prompt


def test_other_perspectives_do_not_receive_premises() -> None:
    """Phase-2 blindness invariant — only destructive sees user premises."""
    state = _state_with_assumptions([
        {"text": "my sibling never repays me", "origin": "user_stated", "label": "HYPOTHESIS"},
    ])
    for perspective in ("constructive", "systemic", "minimalist"):
        prompt = perspective_prompt(state, perspective)
        assert "USER PREMISES" not in prompt


def test_analyst_only_premises_do_not_trigger_destructive_block() -> None:
    state = _state_with_assumptions([
        {"text": "markets are efficient", "origin": "analyst", "label": "HYPOTHESIS"},
    ])
    prompt = perspective_prompt(state, "destructive")
    assert "USER PREMISES" not in prompt


def test_premises_survive_resume_from_old_state_file() -> None:
    """A pre-W2 saved assumption (no new keys) must still load without crashing."""
    from reasoner.application.services.pipeline_service import PipelineSerializationService

    old_state_dict = {
        "core": {
            "problem": "test",
            "decomposition": {
                "sub_problems": [],
                "assumptions": [{"text": "old-format assumption", "label": "UNKNOWN"}],
                "failure_modes": [],
                "critical_sources": [],
            },
        },
    }
    restored = PipelineSerializationService._from_dict(old_state_dict)
    assert restored.decomposition.assumptions[0].text == "old-format assumption"
    assert restored.decomposition.assumptions[0].origin == "analyst"  # default, not a crash
