import sys
from pathlib import Path

import pytest

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reasoner.pipeline import ReasonerPipeline
from reasoner.presets import get_preset

# Real-pipeline audit: every case runs pipeline.run() against live providers and
# writes test_audit_results.log. Requires a funded OPENROUTER_API_KEY + network,
# so it belongs to the integration lane, not the unit suite.
pytestmark = pytest.mark.integration

TEST_CASES = [
    ("multi-perspective-budget", "Should I bootstrap or raise VC for my AI startup?"),
    ("debate-budget", "Is remote work more productive than in-office work? Debate the merits."),
    ("jury-budget", "Evaluate the potential impact of universal basic income on the global economy."),
    ("research-budget", "Provide a deep research report on the current state of solid-state battery technology."),
    ("scientific-budget", "Hypothesize why the rate of obesity is increasing despite increased health awareness."),
    ("socratic-budget", "What is justice? Help me understand the concept through questioning."),
    ("pre-mortem-budget", "Our new SaaS product launch is in 3 months. What could go wrong?"),
    ("bayesian-budget", "What is the probability that a coin flip comes up heads if it has come up heads 10 times in a row? Explain using Bayesian reasoning."),
    ("dialectical-budget", "Explore the tension between individual privacy and national security."),
    ("analogical-budget", "How is building a software project like building a house?"),
    ("delphi-budget", "What will be the most significant technological breakthrough of the 2030s?"),
    ("cove-budget", "List 5 facts about the Roman Empire and verify each one."),
    ("sot-budget", "Outline the steps to create a successful marketing campaign for a new consumer app."),
    ("tot-budget", "Solve the following riddle: I speak without a mouth and hear without ears. I have no body, but I come alive with wind. What am I?"),
    ("pot-budget", "Calculate the 10th Fibonacci number using Python code."),
    ("self-discover-budget", "How can I optimize my morning routine for maximum productivity and well-being?"),
    ("writing-budget", "Write a research-backed article about the history and future of synthetic biology."),
    ("coding-budget", "Generate a complete Python script for a web scraper that extracts news headlines from a given URL."),
    ("brainstorming-budget", "Brainstorm 10 innovative ways to reduce plastic waste in urban environments."),
]

@pytest.mark.parametrize("preset_name, problem", TEST_CASES)
@pytest.mark.asyncio
async def test_method_execution(preset_name, problem):
    output = f"\n>>> TESTING PRESET: {preset_name}\n>>> PROBLEM: {problem}\n"
    print(output)
    with open("test_audit_results.log", "a", encoding="utf-8") as f:
        f.write(output)

    preset = get_preset(preset_name)
    router = preset.build_router()

    pipeline = ReasonerPipeline(
        router=router,
        preset_name=preset_name,
        verbose=True,
    )

    try:
        state = await pipeline.run(problem)

        assert state.final_solution is not None, f"Final solution is missing for {preset_name}"
        assert state.final_solution.core_solution is not None, f"Core solution is missing for {preset_name}"
        assert len(state.final_solution.core_solution) > 100, f"Synthesis too short for {preset_name}"
        assert not state.errors, f"Errors in pipeline run for {preset_name}: {state.errors}"

        msg = f">>> SUCCESS: {preset_name}\n"
        print(msg)
        with open("test_audit_results.log", "a", encoding="utf-8") as f:
            f.write(msg)
    except Exception as e:
        msg = f">>> FAILED: {preset_name} with error: {str(e)}\n"
        print(msg)
        with open("test_audit_results.log", "a", encoding="utf-8") as f:
            f.write(msg)
        raise e
