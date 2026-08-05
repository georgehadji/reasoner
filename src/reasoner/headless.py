"""Headless integration module — call the Reasoner pipeline in-process,
without spinning up FastAPI/uvicorn.

Usage (host app):

    import sys
    sys.path.insert(0, "/path/to/Reasoner/src")   # or pip install -e it
    from reasoner import headless

    result = await headless.ask("Is X better than Y?", preset="research-budget")
    if result.action == "pipeline":
        print(result.state.final_synthesis)
    elif result.action == "direct":
        print(result.answer)
    else:  # "web_search"
        print(result.search_results)

    # Once, at the HOST app's own shutdown (not per-call — see shutdown()):
    await headless.shutdown()

Design notes (see plans/ or ask the maintainer for the fuller write-up):

- ask() builds an argv list and goes through the real argparse parser
  (reasoner.main.parse_args) rather than hand-rolling an args namespace, so
  preset validation, --routing/--preset mutual exclusivity, and every default
  main() and ReasonerPipeline read off `args` stay authoritative in one place.
- Cleanup is NOT done per ask() call. OpenAICompatibleProvider._shared_pool and
  the scraper module's shared httpx client are process-wide singletons — the
  CLI's `finally: close pool` pattern is safe there because the CLI process is
  one-shot. A host app calling ask() repeatedly (possibly concurrently) would
  have call A's cleanup tear down the pool call B is still using, producing a
  "client has been closed" error in B. Instead, headless.shutdown() exists for
  the host app to call once at its own process shutdown — mirrors exactly what
  reasoner.api's FastAPI `lifespan` shutdown phase already does for the same
  two singletons (src/reasoner/api/__init__.py).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from reasoner.application.orchestrator import PipelineOrchestrator
from reasoner.domain.pipeline_state import PipelineState

logger = logging.getLogger(__name__)


@dataclass
class HeadlessResult:
    """Unifies the three outcomes PipelineOrchestrator.preflight() can select
    (mirrors main.py:229-298 / api/execution/pipeline.py:95-117) — no existing
    type in the codebase covers all three, since the API path streams SSE
    chunks instead of returning a value and the CLI path prints and discards.

    Exactly one of (answer, search_results, state) is populated, matching
    `action`.
    """

    action: str  # "direct" | "web_search" | "pipeline"
    answer: str | None = None
    search_results: list[dict[str, Any]] | None = None
    state: PipelineState | None = None
    auto_selected_method: str | None = None
    effective_preset_name: str | None = None


def _build_argv(
    problem: str,
    preset: str | None,
    routing: str | None,
    **overrides: Any,
) -> list[str]:
    """Translate ask()'s keyword arguments into a CLI argv list for
    reasoner.main.parse_args — keeps argparse's own defaults/validation
    (preset choices, --preset/--routing mutual exclusivity) authoritative
    instead of duplicating them here."""
    argv: list[str] = ["--problem", problem]

    if preset and routing:
        raise ValueError(
            "pass at most one of preset= or routing= (mutually exclusive, like the CLI)"
        )
    if preset:
        argv += ["--preset", preset]
    if routing:
        argv += ["--routing", routing]

    flag_options = {"sequential", "quiet", "force_pipeline", "enhance_prompt"}
    for key, value in overrides.items():
        if value is None:
            continue
        flag = "--" + key.replace("_", "-")
        if key in flag_options:
            if value:
                argv.append(flag)
        else:
            argv += [flag, str(value)]
    return argv


async def ask(
    problem: str,
    preset: str | None = None,
    routing: str | None = None,
    **overrides: Any,
) -> HeadlessResult:
    """Run one problem through the Reasoner pipeline in-process.

    `overrides` maps to the same flags `main.py --help` lists (e.g.
    top_k=3, sequential=True, source_type="academic", domain="github.com",
    enhance_prompt=True). Unset ones use argparse's own CLI defaults.

    Does not close the shared httpx pools — call headless.shutdown() once at
    the host app's own process shutdown instead (see module docstring).

    Raises whatever the underlying pipeline raises (ValueError for a bad
    --routing JSON via argparse's own validation, etc.) — no swallowing here;
    the host app decides how to surface errors.
    """
    from reasoner.core.constants import DIRECT_ANSWER_MAX_TOKENS, DIRECT_ANSWER_TEMPERATURE
    from reasoner.main import parse_args
    from reasoner.presets import get_preset

    argv = _build_argv(problem, preset, routing, **overrides)
    args = parse_args(argv)

    from reasoner.sanitization import sanitize_for_prompt
    sanitized_problem, _ = sanitize_for_prompt(problem)

    from reasoner.application.services.preset_service import PresetService

    preset_service = PresetService()
    orchestrator = PipelineOrchestrator(preset_service, None, None)
    preflight = await orchestrator.preflight(args, initial_state=None)

    if preflight.action == "direct":
        response, _ = await preflight.router.call(
            role="primary",
            system_prompt="You are an analytical assistant. Provide a clear, concise answer.",
            user_prompt=sanitized_problem,
            max_tokens=DIRECT_ANSWER_MAX_TOKENS,
            temperature=DIRECT_ANSWER_TEMPERATURE,
        )
        from reasoner.infrastructure.llm.ports import DegradedLLMResponse
        if isinstance(response, DegradedLLMResponse):
            # main.py prints "[Error] {response.error}" and returns for this
            # case rather than treating it as a normal answer — headless
            # callers get the same signal via an exception instead of a
            # silently-empty result.
            from reasoner.core.exceptions import ProviderUnavailableError
            raise ProviderUnavailableError(
                f"All providers failed for the direct-answer path: {response.error}"
            )
        return HeadlessResult(
            action="direct",
            answer=response,
            effective_preset_name=preflight.effective_preset_name,
        )

    if preflight.action == "web_search":
        from reasoner.infrastructure.search.discovery import get_search_client

        try:
            client, _ = await get_search_client(source_type="general")
            results = await client.search(sanitized_problem, num_results=10, source_type="general")
        except Exception:
            logger.warning("headless.web_search_failed", exc_info=True)
            results = []
        return HeadlessResult(
            action="web_search",
            search_results=results,
            effective_preset_name=preflight.effective_preset_name,
        )

    router = preflight.router
    effective_preset_name = preflight.effective_preset_name
    final_preset = get_preset(effective_preset_name)

    from reasoner.pipeline import ReasonerPipeline

    pipeline = ReasonerPipeline(
        router=router,
        initial_state=None,
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
    state = await pipeline.run(sanitized_problem)

    return HeadlessResult(
        action="pipeline",
        state=state,
        auto_selected_method=preflight.auto_selected_method,
        effective_preset_name=effective_preset_name,
    )


async def shutdown() -> None:
    """Release the process-wide shared connection pools ask() uses.

    Call this ONCE at the host app's own shutdown (FastAPI lifespan shutdown
    phase, atexit, etc.) — never per ask() call; see module docstring for why.
    Each close is isolated so one failure doesn't skip the other, matching
    reasoner.api's lifespan shutdown handler.
    """
    try:
        from reasoner.infrastructure.llm.providers.openai_compat import OpenAICompatibleProvider
        await OpenAICompatibleProvider.close_shared_pool()
    except Exception:
        logger.warning("headless.shutdown.pool_close_failed", exc_info=True)

    try:
        from reasoner.scraper import close_scraper_client
        await close_scraper_client()
    except Exception:
        logger.warning("headless.shutdown.scraper_close_failed", exc_info=True)
