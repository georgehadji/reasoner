"""
Reasoner v2.0 Pipeline — Entry Point
Reasoner

================================================================
USAGE — PRESETS (recommended)
================================================================
# List all available presets + key status:
python main.py --list-presets

# Run with a named preset:
python main.py --problem "..." --preset multi-perspective-budget
python main.py --problem "..." --preset multi-perspective-premium
python main.py --problem "..." --preset research-budget
python main.py --problem "..." --preset research-premium
python main.py --problem "..." --preset debate-budget
python main.py --problem "..." --preset debate-premium

================================================================
USAGE — CUSTOM ROUTING
================================================================
# Fully custom routing (JSON dict, must include "primary"):
python main.py --problem "..." --routing '{
  "primary":       "deepseek-v4-flash",
  "constructive":  "kimi-k2-6",
  "destructive":   "qwen3-max",
  "scoring":       "sonar-pro",
  "synthesis":     "glm-5.2"
}'

================================================================
USAGE — MODEL DISCOVERY
================================================================
# List all available model IDs grouped by ecosystem:
python main.py --list-models

================================================================
USAGE — I/O OPTIONS
================================================================
python main.py --problem-file problem.txt --preset multi-perspective-budget
python main.py --problem "..." --preset research-budget --output result.json
python main.py --problem "..." --preset multi-perspective-premium --sequential --quiet
python main.py --problem "..." --preset research-premium --top-k 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from reasoner.application.orchestrator import PipelineOrchestrator
from reasoner.application.services.adaptive_routing import build_adaptive_routing_service
from reasoner.application.services.preset_service import PresetService
from reasoner.renderer import export_to_json, render_pipeline_result
from reasoner.infrastructure.llm.registry import list_models
from reasoner.core.settings import settings  # triggers dotenv load
from reasoner.core.constants import (
    DEFAULT_CLI_PRESET,
    DIRECT_ANSWER_MAX_TOKENS,
    DIRECT_ANSWER_TEMPERATURE,
)
from reasoner.presets import (
    PRESETS,
    get_preset,
    is_valid_preset_name,
    print_presets_summary,
    resolve_preset_name,
)
# GateAgent / HyperGateAgent — handled by PipelineOrchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────────────────

def cmd_list_models() -> None:
    from rich.console import Console
    from rich.table import Table
    from rich import box

    groups = list_models()
    console = Console()

    for ecosystem, model_ids in sorted(groups.items()):
        if not model_ids:
            continue
        table = Table(
            title=f"[cyan]{ecosystem.upper()}[/cyan]",
            box=box.SIMPLE,
            show_header=False,
            min_width=40,
        )
        table.add_column("Model ID", style="white")
        for mid in sorted(model_ids):
            table.add_row(mid)
        console.print(table)


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    if args.list_presets:
        print_presets_summary()
        return

    if args.list_models:
        cmd_list_models()
        return

    # Benchmark mode
    if args.benchmark:
        import asyncio
        from reasoner.infrastructure.benchmarks.engine import BenchmarkEngine
        from reasoner.infrastructure.llm.registry import build_provider

        async def _run_benchmark():
            engine = BenchmarkEngine()
            provider = build_provider(args.benchmark)
            result = await engine.benchmark_model(args.benchmark, provider)
            print(f"\nBenchmark results for '{args.benchmark}':")
            for dim, score in sorted(result["scores"].items()):
                print(f"  {dim:20s}: {score:.3f}")
            print(f"\nCost: ${result['cost_usd']:.4f}")
            print(f"Duration: {result['duration_seconds']:.1f}s")

        await _run_benchmark()
        return

    if args.benchmark_all:
        from reasoner.infrastructure.benchmarks.engine import BenchmarkEngine
        from reasoner.infrastructure.llm.registry import _MODEL_WHITELIST, build_provider

        async def _run_benchmark_all():
            engine = BenchmarkEngine()
            model_ids = list(_MODEL_WHITELIST.keys())
            print(f"\nBenchmarking {len(model_ids)} models...")
            for mid in model_ids:
                try:
                    provider = build_provider(mid)
                    result = await engine.benchmark_model(mid, provider)
                    print(f"  {mid:30s}: {', '.join(f'{d}={s:.2f}' for d,s in sorted(result['scores'].items())[:3])} ...")
                except Exception as exc:
                    print(f"  {mid:30s}: FAILED ({exc})")
            print("\nDone.")

        await _run_benchmark_all()
        return

    # Handle resume from saved state
    if args.resume:
        from reasoner.models import load as load_state
        state_path = Path(args.resume)
        if not state_path.exists():
            print(f"[ERROR] State file not found: {args.resume}")
            sys.exit(1)
        try:
            state = load_state(args.resume)
            print(f"\n{'='*60}")
            print(f"  Reasoner v2.0 — Resumed from saved state")
            print(f"{'='*60}")
            print(f"  Problem: {state.problem[:120]}...")
            print(f"  Resumed at: {state.task_type.value if state.task_type else 'start'}")
            print(f"{'='*60}\n")
            render_pipeline_result(state)
            problem = state.problem # Initialize problem for continued pipeline run
        except Exception as exc:
            print(f"[ERROR] Failed to load state: {exc}")
            sys.exit(1)
    else: # If not resuming, load problem normally
        # Load problem
        if getattr(args, 'problem_file', None) and isinstance(args.problem_file, str):
            problem_path = Path(args.problem_file)
            if not problem_path.exists():
                print(f"[ERROR] File not found: {args.problem_file}")
                sys.exit(1)
            problem = problem_path.read_text(encoding="utf-8").strip()
        else:
            problem = args.problem.strip()

    if not problem:
        print("[ERROR] No problem provided. Use --problem or --problem-file.")
        print("        Run 'python main.py --help' for usage.")
        sys.exit(1)


    try:
        # Determine initial_state for the pipeline
        initial_state = None
        if args.resume:
            try:
                from reasoner.models import load as load_state
                initial_state = load_state(args.resume)
            except Exception as exc:
                print(f"[ERROR] Failed to load initial state for pipeline: {exc}")
                sys.exit(1)

        print(f"\n{'='*60}")
        print(f"  Reasoner v2.0 — Reasoner")
        print(f"{'='*60}")
        short_problem = problem[:120] + ("..." if len(problem) > 120 else "")
        print(f"  Problem: {short_problem}")
        print(f"  Top-K candidates: {args.top_k}")
        print(f"  Parallel perspectives: {not args.sequential}")
        print(f"{'='*60}\n")

        # SECURITY: Prompt-injection defense for CLI input
        from reasoner.sanitization import sanitize_for_prompt
        problem, _ = sanitize_for_prompt(problem)

        # Inject core → infra DI hooks (mirrors api/__init__.py lifespan wiring;
        # the CLI entry point has no lifespan, so it must wire this itself).
        from reasoner.core.ports.model_registry_port import set_model_registry_port
        from reasoner.infrastructure.llm.registry import RegistryAdapter
        set_model_registry_port(RegistryAdapter())

        # ?? Orchestrator Preflight: preset resolution, HyperGate, neuro recall ??
        preset_service = PresetService()
        orchestrator = PipelineOrchestrator(
            preset_service, None, None,
            adaptive_routing=build_adaptive_routing_service(),
        )
        preflight = await orchestrator.preflight(args, initial_state)

        if preflight.action == "direct":
            print("  [Gate] Direct answer selected.\n")
            response, _ = await preflight.router.call(
                role="primary",
                system_prompt="You are an analytical assistant. Provide a clear, concise answer.",
                user_prompt=problem,
                max_tokens=DIRECT_ANSWER_MAX_TOKENS,
                temperature=DIRECT_ANSWER_TEMPERATURE,
            )
            from reasoner.infrastructure.llm.ports import DegradedLLMResponse
            if isinstance(response, DegradedLLMResponse):
                print(f"[Error] {response.error}")
                return
            print(response)
            return

        if preflight.action == "web_search":
            print("  [Gate] Web search selected.\n")
            from reasoner.infrastructure.search.discovery import get_search_client
            try:
                client, _ = await get_search_client(source_type="general")
                if settings.PRISM_RESEARCHER_ENABLED:
                    from reasoner.application.flows.prism_research import run_prism_standalone
                    print("  [Prism] Iterative research mode active.\n")
                    results, _ = await run_prism_standalone(
                        problem, preflight.router, client, mode="balanced"
                    )
                else:
                    results = await client.search(problem, num_results=10, source_type="general")
            except Exception as exc:
                logger.warning("Web search failed: %s", exc)
                results = []
            if not results:
                print("No relevant web search results were found for your query.")
                return
            print("### Web Search Results\n")
            for i, r in enumerate(results, 1):
                title = r.get("title") or "Untitled"
                url = r.get("url") or ""
                snippet = r.get("snippet") or r.get("content") or ""
                print(f"{i}. [{title}]({url})")
                if snippet:
                    print(f"   > {snippet}")
                print()
            return

        router = preflight.router
        effective_preset_name = preflight.effective_preset_name
        auto_selected_method = preflight.auto_selected_method

        if auto_selected_method:
            print(f"  [Gate] Auto-selected method: {auto_selected_method} -> preset: {effective_preset_name}\n")

        final_preset = get_preset(effective_preset_name)

        from reasoner.pipeline import ReasonerPipeline
        pipeline = ReasonerPipeline(
            router=router,
            initial_state=initial_state,
            top_k=args.top_k,
            parallel_perspectives=not args.sequential,
            verbose=not args.quiet,
            preset_name=effective_preset_name,
            source_type=args.source_type,
            domain=args.domain or None,
            enhance_prompt=args.enhance_prompt,
            batch_critique_jury=final_preset.batch_critique_jury if final_preset else False,
            augmentation_methods=preflight.augmentation_methods,
        )
        state = await pipeline.run(problem)

        render_pipeline_result(state)

        if getattr(args, 'output', None) and isinstance(args.output, str):
            export_to_json(state, args.output)
            print(f"\n[OK] Full state exported -> {args.output}")

        if getattr(args, 'save_state', None) and isinstance(args.save_state, str):
            from reasoner.models import save
            save(state, args.save_state)
            print(f"\n[OK] State saved -> {args.save_state}")

    finally:
        # ── Cleanup ──
        from reasoner.scraper import close_scraper_client
        await close_scraper_client()
        
        from reasoner.infrastructure.llm.providers.openai_compat import OpenAICompatibleProvider
        await OpenAICompatibleProvider.close_shared_pool()


# ─────────────────────────────────────────────────────────────────────
# CLI ARGS
# ─────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args. argv=None (default) reads sys.argv, matching prior
    behavior. Callers building args programmatically (e.g. headless.py) pass
    an explicit list instead of mutating the process-global sys.argv, which
    would not be safe under concurrent calls."""
    # Build preset choices dynamically
    preset_choices = sorted(PRESETS.keys())

    def _preset_arg(value: str) -> str:
        if not value:  # Allow empty string to pass through (will use default)
            return value
        if not is_valid_preset_name(value):
            raise argparse.ArgumentTypeError(
                f"Unknown preset {value!r}. Choices: {', '.join(preset_choices)}"
            )
        return resolve_preset_name(value)

    parser = argparse.ArgumentParser(
        description="Reasoner v2.0 — Reasoner Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # ── Problem input
    input_group = parser.add_argument_group("Problem Input")
    input_group.add_argument(
        "--problem", "-p",
        type=str, default="",
        help="Problem statement (wrap in quotes)",
    )
    input_group.add_argument(
        "--problem-file",
        type=str, default="",
        metavar="PATH",
        help="Path to .txt file containing the problem statement",
    )

    # ── Model/Routing selection
    routing_group = parser.add_argument_group("Model Selection (mutually exclusive)")
    routing_ex = routing_group.add_mutually_exclusive_group()
    routing_ex.add_argument(
        "--preset",
        type=_preset_arg,
        default="",
        metavar="PRESET_ID",
        help=(
            "Named routing preset. Choices: "
            + ", ".join(preset_choices)
            + " (default: multi-perspective-budget)"
        ),
    )
    routing_ex.add_argument(
        "--routing",
        type=str,
        default="",
        metavar="JSON",
        help=(
            'Custom JSON routing dict. Must include "primary". '
            'Example: \'{"primary":"deepseek-v4-flash","scoring":"sonar-pro"}\''
        ),
    )

    # ── Pipeline options
    pipeline_group = parser.add_argument_group("Pipeline Options")
    pipeline_group.add_argument(
        "--top-k",
        type=int, default=2,
        help="Number of candidates to keep after pruning (default: 2)",
    )
    pipeline_group.add_argument(
        "--sequential",
        action="store_true",
        help="Run Phase 2 perspectives sequentially (for rate-limited providers)",
    )
    pipeline_group.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress phase-by-phase logging",
    )
    pipeline_group.add_argument(
        "--force-pipeline",
        action="store_true",
        help="Bypass the GateAgent and always run the full multi-phase pipeline",
    )
    pipeline_group.add_argument(
        "--source-type",
        type=str, default="general",
        choices=["general", "academic", "social", "news", "code"],
        help="Source type for iterative RAG: general, academic, social, news, code (default: general)",
    )
    pipeline_group.add_argument(
        "--domain",
        type=str, default="",
        metavar="DOMAIN",
        help="Limit search to specific domain (e.g., github.com, stackoverflow.com)",
    )
    pipeline_group.add_argument(
        "--enhance-prompt",
        action="store_true",
        help="Use LLM to rewrite and clarify the user's problem before execution",
    )

    # ── Output
    output_group = parser.add_argument_group("Output")
    output_group.add_argument(
        "--output", "-o",
        type=str, default="",
        metavar="PATH",
        help="Export full pipeline state to JSON file",
    )
    output_group.add_argument(
        "--save-state",
        type=str, default="",
        metavar="PATH",
        help="Save pipeline state to file for later resume",
    )

    # ── State Management
    state_group = parser.add_argument_group("State Management")
    state_group.add_argument(
        "--resume",
        type=str, default="",
        metavar="PATH",
        help="Resume pipeline from saved state file",
    )

    # ── Discovery
    info_group = parser.add_argument_group("Discovery")
    info_group.add_argument(
        "--list-presets",
        action="store_true",
        help="List all available presets with API key status, then exit",
    )
    info_group.add_argument(
        "--list-models",
        action="store_true",
        help="List all available model IDs grouped by ecosystem, then exit",
    )

    # ── Benchmark
    benchmark_group = parser.add_argument_group("Benchmark (ACR Phase 7)")
    benchmark_group.add_argument(
        "--benchmark",
        type=str,
        default="",
        metavar="MODEL_ID",
        help="Run all benchmark suites on a model to evaluate its capabilities",
    )
    benchmark_group.add_argument(
        "--benchmark-all",
        action="store_true",
        help="Run benchmarks on all models in the whitelist",
    )

    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
