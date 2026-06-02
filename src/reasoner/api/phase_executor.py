"""Phase execution helpers extracted from streaming.py.

Contains:
  - _PHASE_ROLE_HINTS: mapping of phase names to provider router roles
  - _get_phase_start_models(): resolve which models will handle a phase
  - _run_phase_with_keepalive(): async generator for keepalive-punctuated phase execution
  - CRITICAL_PHASE_NAMES: legacy critical phase set
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Callable

from reasoner.domain.pipeline_state import PipelineState
from reasoner.infrastructure.llm.router import ProviderRouter

logger = logging.getLogger(__name__)

# ── Phase Role Hints (maps phase name → router role keys) ────────────
_PHASE_ROLE_HINTS: dict[str, list[str]] = {
    "Classification": ["classification"],
    "Decomposition": ["decomposition"],
    "Deep Read": ["primary"],
    "Perspectives": ["constructive", "destructive", "systemic", "minimalist"],
    "Opening Statements": ["constructive", "destructive"],
    "Rebuttals": ["constructive", "destructive"],
    "Cross-Examination": ["systemic"],
    "Hypotheses": ["primary"],
    "Falsification Tests": ["scoring"],
    "Maieutic Questions": ["destructive"],
    "Dialectic Answers": ["constructive"],
    "Generation Pool": ["generator_1", "generator_2", "generator_3"],
    "Critic Pool": ["critic_1", "critic_2", "critic_3"],
    "Verification & Meta": ["verifier", "meta_evaluator"],
    "Deep Research": ["primary"],
    "Critique & Pruning": ["scoring"],
    "Stress Testing": ["stress_testing"],
    "Synthesis": ["synthesis"],
    "Decompose Topic": ["article_decompose"],
    "Retrieve Sources": ["primary"],
    "Extract Claims (CoVE)": ["article_claim_extract"],
    "Adversarial Verify": ["article_verifier"],
    "Synthesize (SoT)": ["article_synthesize"],
    "Pre-Mortem": ["article_pre_mortem"],
    "Journal Review": ["article_critic"],
    "Final Assembly": ["article_assemble"],
    "Humanize": ["article_humanize"],
}

# ── Legacy critical phases ───────────────────────────────────────────
_LEGACY_CRITICAL = {
    "Decomposition", "Perspectives", "Opening Statements",
    "Hypotheses", "Maieutic Questions", "Generation Pool",
    "Deep Research", "Retrieve Sources", "Adversarial Verify",
}


def get_phase_start_models(phase_name: str, router: ProviderRouter) -> list[str]:
    """Resolve which model IDs will handle a given phase."""
    roles = _PHASE_ROLE_HINTS.get(phase_name, [])
    models: list[str] = []
    for role in roles:
        try:
            provider = router.get(role)
            if provider and hasattr(provider, "model") and provider.model and provider.model not in models:
                models.append(provider.model)
        except Exception:
            continue
    return models


def get_critical_phases(phases: list, step_metadata: dict) -> set[str]:
    """Compute the set of critical phase names for the current run."""
    return {
        name for _, name, _, _ in phases
        if step_metadata.get(name, {}).get("critical") or name in _LEGACY_CRITICAL
    }


async def run_phase_with_keepalive(
    coro_fn: Callable,
    state: PipelineState,
    cancel_event: asyncio.Event,
    timeout_seconds: float = 90.0,
    keepalive_interval: float = 15.0,
) -> AsyncGenerator[str, None]:
    """Run a phase coroutine, yielding SSE keepalive comments.
    
    Yields ": keepalive\n\n" every keepalive_interval seconds so the
    browser/proxy never sees an idle connection. Raises TimeoutError if
    the phase exceeds timeout_seconds.
    """
    phase_task = asyncio.ensure_future(coro_fn(state))
    cancel_watch = asyncio.ensure_future(cancel_event.wait())
    deadline = time.monotonic() + timeout_seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if not phase_task.done():
                    phase_task.cancel()
                    try:
                        await phase_task
                    except (asyncio.CancelledError, Exception):
                        pass
                raise asyncio.TimeoutError(
                    f"Phase timed out after {timeout_seconds}s"
                )
            wait = min(keepalive_interval, remaining)
            done, _ = await asyncio.wait(
                {phase_task, cancel_watch},
                timeout=wait,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancel_watch in done:
                if not phase_task.done():
                    phase_task.cancel()
                    try:
                        await phase_task
                    except (asyncio.CancelledError, Exception):
                        pass
                return
            if phase_task in done:
                exc = phase_task.exception()
                if exc:
                    raise exc
                return
            # Phase still running — send a keepalive SSE comment
            yield ": keepalive\n\n"
    finally:
        for t in (phase_task, cancel_watch):
            if not t.done():
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
