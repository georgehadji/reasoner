"""Smoke test every budget preset through the live pipeline.

Requirements:
    - Backend running on REASONER_TEST_URL (default http://localhost:8003)
    - API keys configured in .env (LLM calls are made)
    - Run with: pytest tests/integration/test_preset_pipeline.py -s

Tags:
    @pytest.mark.integration — requires live server
    @pytest.mark.slow         — makes real LLM calls
"""

import pytest

from .sse_utils import collect_pipeline_events

# ── Parameterized test cases ──────────────────────────────────────────
# Each tuple: (preset, prompt, expected_phases, min_phases)
# - prompt: complex enough to trigger full pipeline (not a direct answer)
# - expected_phases: phase names that MUST appear; empty means just check no errors
# - min_phases: minimum number of completed phases (lenient)
# ───────────────────────────────────────────────────────────────────────

PRESET_CASES = [
    # ── Scientific method pipeline ──
    (
        "scientific-budget",
        "Why does ice float on water while most solids sink?",
        ["Hypothesize", "Falsification Tests", "Synthesis"],
        3,
    ),
    # ── Bayesian reasoning ──
    (
        "bayesian-budget",
        (
            "A disease affects 1 in 10,000 people. A test is 99% accurate for "
            "both positives and negatives. If you test positive, how likely are "
            "you to actually have the disease? Walk through the prior, likelihood, "
            "and posterior."
        ),
        ["Prior Elicitation", "Likelihood Assessment", "Posterior Update", "Synthesis"],
        2,
    ),
    # ── Debate ──
    (
        "debate-budget",
        "Should artificial intelligence be regulated at the international level?",
        ["Opening Statements", "Rebuttals", "Synthesis"],
        2,
    ),
    # ── Multi-perspective ──
    (
        "multi-perspective-budget",
        "What would be the global economic impact if we transitioned to 100% renewable energy by 2040?",
        ["Perspectives", "Synthesis"],
        2,
    ),
    # ── Dialectical ──
    (
        "dialectical-budget",
        "Is free will compatible with determinism?",
        ["Synthesis"],
        1,
    ),
    # ── Socratic ──
    (
        "socratic-budget",
        "What is justice?",
        ["Synthesis"],
        1,
    ),
    # ── Jury deliberation ──
    (
        "jury-budget",
        "Which is the best programming language for building a real-time trading system: Rust, Go, or C++?",
        ["Generation Pool", "Critic Pool", "Synthesis"],
        2,
    ),
    # ── Chain-of-Verification ──
    (
        "cove-budget",
        "How many piano tuners are there in Chicago? Provide a step-by-step estimate and verify each assumption.",
        ["Synthesis"],
        1,
    ),
    # ── Brainstorming ──
    (
        "brainstorming-budget",
        "Propose 10 novel uses for blockchain technology beyond cryptocurrency.",
        ["Synthesis"],
        1,
    ),
    # ── Delphi ──
    (
        "delphi-budget",
        "When will human-level AGI be achieved? Provide a forecast with confidence intervals.",
        ["Synthesis"],
        1,
    ),
    # ── Analogical ──
    (
        "analogical-budget",
        "How is managing a software team similar to conducting an orchestra?",
        ["Synthesis"],
        1,
    ),
    # ── Coding ──
    (
        "coding-budget",
        "Write a Python function that implements a thread-safe LRU cache with O(1) get and put operations. Use a doubly-linked list and hash map.",
        ["Synthesis"],
        1,
    ),
    # ── Self-discover ──
    (
        "self-discover-budget",
        "What reasoning structures should I use to determine the best career path for someone with skills in both art and mathematics?",
        ["Synthesis"],
        1,
    ),
    # ── Iterative critique ──
    (
        "iterative-critique-budget",
        "Draft a proposal for a four-day work week, then critique and improve it.",
        ["Synthesis"],
        1,
    ),
    # ── Cross-language ──
    (
        "cross-language-budget",
        "Explain the concept of 'Schadenfreude' and provide equivalent concepts in Japanese and Arabic.",
        ["Synthesis"],
        1,
    ),
    # ── Article ──
    (
        "article-budget",
        "Write a short article about the Fermi paradox suitable for a science magazine audience.",
        ["Synthesis"],
        1,
    ),
    # ── Image generation (no LLM phases to assert beyond success) ──
    (
        "image-gen-budget",
        "Describe a futuristic cityscape with floating gardens and vertical farms.",
        [],
        0,
    ),
]

# ══════════════════════════════════════════════════════════════════════


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.parametrize(
    "preset,prompt,expected_phases,min_phases",
    PRESET_CASES,
    ids=[p for p, _, _, _ in PRESET_CASES],
)
async def test_preset_pipeline(
    api_client,
    csrf_token,
    preset: str,
    prompt: str,
    expected_phases: list[str],
    min_phases: int,
) -> None:
    """Run a pipeline with the given preset and validate output structure."""
    collector = await collect_pipeline_events(api_client, csrf_token, prompt, preset)

    # ── No errors ──
    assert not collector.errors, (
        f"Pipeline for {preset} returned errors: {collector.errors}"
    )

    # ── A done/end event was emitted ──
    assert collector.done_event is not None, (
        f"Pipeline for {preset} never emitted a done/end event. "
        f"Events received: {[e.type for e in collector.events]}"
    )

    # ── At least min_phases completed ──
    actual_phases = collector.phase_complete_names
    assert collector.total_phases >= min_phases, (
        f"Pipeline for {preset} completed {collector.total_phases} phases "
        f"({sorted(actual_phases)}), expected at least {min_phases}. "
        f"Phase starts seen: {sorted(collector.phase_start_names)}"
    )

    # ── Required phases present ──
    for phase in expected_phases:
        assert phase in actual_phases, (
            f"Pipeline for {preset} missing expected phase '{phase}'. "
            f"Phases completed: {sorted(actual_phases)}"
        )

    # ── Token usage is plausible ──
    tokens = collector.total_tokens
    total = tokens.get("total", 0)
    assert total > 0, (
        f"Pipeline for {preset} reported 0 total tokens — likely a dummy provider"
    )
