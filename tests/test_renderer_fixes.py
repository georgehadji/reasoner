"""
Regression tests for renderer bugs.
"""


from reasoner.models import FinalSolution, MetaCognitiveAudit, PipelineState
from reasoner.renderer import console, render_pipeline_result

# ─────────────────────────────────────────────────────────────────────
# Bug 2: action_blueprint shows `?:` for empty dicts / strings
# ─────────────────────────────────────────────────────────────────────

def test_render_action_blueprint_mixed_types(capsys):
    """Renderer must handle dicts, strings, empty dicts, and None gracefully."""
    state = PipelineState(problem="test", preset_name="multi-perspective-budget")
    state.final_solution = FinalSolution(
        core_solution="done",
        critical_insights=[],
        action_blueprint=[
            {},  # empty dict -> should not render as `?:`
            "plain string step",
            {"step": 1, "action": "do X", "time_horizon": "1 week"},
        ],
        open_questions=[],
        claim_labels={},
        meta_audit=MetaCognitiveAudit(
            most_dangerous_assumption="",
            dominant_bias="",
            remaining_uncertainty="",
            assumption_failure_impact="",
            non_obvious_insight="",
        ),
    )

    # Capture rich console output
    with console.capture() as capture:
        render_pipeline_result(state)
    text = capture.get()

    assert "?:" not in text, f"Renderer produced `?:` placeholder: {text[:500]}"
    assert "plain string step" in text
    assert "do X" in text


# ─────────────────────────────────────────────────────────────────────
# Bug 5: Meta audit hallucination — empty meta_audit should be hidden
# ─────────────────────────────────────────────────────────────────────

def test_renderer_skips_empty_meta_audit():
    """Empty meta_audit fields should not produce any meta-cognitive panel."""
    state = PipelineState(problem="test", preset_name="multi-perspective-budget")
    state.final_solution = FinalSolution(
        core_solution="done",
        critical_insights=[],
        action_blueprint=["step 1"],
        open_questions=[],
        claim_labels={},
        meta_audit=MetaCognitiveAudit(
            most_dangerous_assumption="",
            dominant_bias="",
            remaining_uncertainty="",
            assumption_failure_impact="",
            non_obvious_insight="",
        ),
    )

    with console.capture() as capture:
        render_pipeline_result(state)
    text = capture.get()

    # Panel titles for meta audit vary by method; check common substrings
    assert "Meta Audit" not in text, f"Empty meta_audit rendered unexpectedly: {text[:500]}"
    assert "Meta Cognitive" not in text
    assert "Most dangerous assumption" not in text
