"""Run every budget preset sequentially and capture results.

MAKES REAL, BILLED OpenRouter CALLS -- one full pipeline per budget preset.
This lived in tests/ under a test_* name, where pytest imported it on every
run and where a single added test_ function would have fired the whole thing
under CI. It is a script, so it lives with the scripts.

    python scripts/run_all_presets.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

from reasoner.application.pipeline import ReasonerPipeline
from reasoner.application.services.preset_service import PresetService
from reasoner.presets import PRESETS

METHOD_PROMPTS = {
    "analogical-budget": "How is software architecture similar to city planning? Draw structural analogies.",
    "article-budget": "Write a short article about the benefits of test-driven development.",
    "bayesian-budget": "What is the probability that a coin is biased if it lands heads 8 out of 10 times?",
    "brainstorming-budget": "Generate creative ideas for reducing food waste in restaurants.",
    "coding-budget": "Write a Python function that finds the longest palindromic substring in a string.",
    "cove-budget": "Is it true that the Great Wall of China is visible from space? Verify this claim.",
    "cross-language-budget": "Explain the concept of recursion in simple terms.",
    "debate-budget": "Should programming languages enforce strict typing? Argue both sides.",
    "delphi-budget": "What will be the most important programming language in 2030?",
    "dialectical-budget": "Is AI a net positive or negative for employment? Explore thesis and antithesis.",
    "image-gen-budget": "Generate a conceptual image of a futuristic city.",
    "iterative-critique-budget": "Propose a solution for urban traffic congestion and critique it.",
    "jury-budget": "Evaluate whether microservices are better than monoliths for startups.",
    "multi-perspective-budget": "What are the trade-offs of remote work vs office work?",
    "multi-perspective-ultra-budget": "Analyze the ethical implications of gene editing in humans.",
    "pot-budget": "Calculate the compound interest on $1000 at 5% annual rate for 10 years.",
    "pre-mortem-budget": "A startup is launching a new social media app. What could go wrong?",
    "research-budget": "What are the latest advances in quantum computing error correction?",
    "scientific-budget": "Why do some people get motion sickness while others don't?",
    "self-discover-budget": "How should a small team prioritize technical debt vs new features?",
    "socratic-budget": "What does it mean for something to be conscious?",
    "sot-budget": "Explain the process of photosynthesis step by step.",
    "subagent-budget": "Compare the performance characteristics of PostgreSQL vs MySQL.",
    "tot-budget": "Solve this logic puzzle: Three people have hats, red or blue. Each can see others but not their own. A says: I don't know my color. B says: I don't know either. C says: I know mine. What color is C's hat?",
    "writing-budget": "Write a short story about a robot discovering emotions.",
}

RESULTS_FILE = _REPO_ROOT / "method_test_results.json"


async def run_single_preset(preset_id: str, prompt: str) -> dict:
    """Run a single preset and return result dict."""
    result = {
        "preset_id": preset_id,
        "method": PRESETS[preset_id].method if preset_id in PRESETS else "unknown",
        "status": "pending",
        "error": None,
        "error_type": None,
        "duration_s": 0,
        "phases_completed": [],
        "output_length": 0,
    }

    start = time.time()
    try:
        preset_service = PresetService()
        effective_name, router = preset_service.build_router(preset_id)

        pipeline = ReasonerPipeline(
            router=router,
            preset_name=effective_name,
            top_k=2,
            parallel_perspectives=True,
            verbose=False,
        )

        state = await asyncio.wait_for(
            pipeline.run(prompt),
            timeout=180,
        )
        result["duration_s"] = round(time.time() - start, 2)
        result["status"] = "success"
        result["phases_completed"] = list(range(getattr(state, "current_phase", 0) + 1))
        final = getattr(state, "final_synthesis", None) or getattr(state, "final_answer", "")
        result["output_length"] = len(str(final))
        if result["output_length"] == 0:
            result["status"] = "empty_output"
    except TimeoutError:
        result["duration_s"] = round(time.time() - start, 2)
        result["status"] = "timeout"
        result["error"] = "Exceeded 180s timeout"
        result["error_type"] = "TimeoutError"
    except Exception as e:
        result["duration_s"] = round(time.time() - start, 2)
        result["status"] = "error"
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        import traceback
        result["traceback"] = traceback.format_exc()

    return result


async def main():
    results = []
    preset_ids = sorted(METHOD_PROMPTS.keys())

    print(f"\n{'='*70}")
    print(f"  REASONER METHOD TEST - {len(preset_ids)} budget presets")
    print(f"{'='*70}\n")

    for i, preset_id in enumerate(preset_ids, 1):
        prompt = METHOD_PROMPTS[preset_id]
        print(f"[{i:2d}/{len(preset_ids)}] {preset_id}...", end=" ", flush=True)

        result = await run_single_preset(preset_id, prompt)
        results.append(result)

        status_icon = {
            "success": "OK",
            "error": "FAIL",
            "timeout": "TIMEOUT",
            "empty_output": "EMPTY",
        }.get(result["status"], "?")

        print(f"{status_icon} ({result['duration_s']}s)", flush=True)
        if result["error"]:
            err_msg = result['error'][:150]
            print(f"     -> {result['error_type']}: {err_msg}")

        # Save intermediate results
        RESULTS_FILE.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    # Summary
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    success = sum(1 for r in results if r["status"] == "success")
    errors = sum(1 for r in results if r["status"] == "error")
    timeouts = sum(1 for r in results if r["status"] == "timeout")
    empty = sum(1 for r in results if r["status"] == "empty_output")
    print(f"  Success: {success}/{len(results)}")
    print(f"  Errors:  {errors}")
    print(f"  Timeouts: {timeouts}")
    print(f"  Empty:   {empty}")

    if errors or timeouts or empty:
        print("\n  FAILURES:")
        for r in results:
            if r["status"] != "success":
                print(f"    {r['preset_id']}: {r['status']} - {r.get('error_type', '')} {r.get('error', '')[:100]}")

    return results


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.WARNING)
    results = asyncio.run(main())
