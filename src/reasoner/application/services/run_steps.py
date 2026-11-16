"""Unbilled run-level steps that every driver (CLI, headless, SSE) must apply.

These used to live on ``ReasonerPipeline.run`` only, which the web path never
calls: it hands the strategy straight to ``WorkflowRunner``. Anything that
makes no LLM call and that a consumer reads belongs here, not on one driver.
Billed steps (translation, fusion, post-synthesis verification) stay on the
CLI path on purpose (audit finding A-01).
"""

from __future__ import annotations

from typing import Any

from reasoner.core.degrade import degraded
from reasoner.domain.pipeline_state import PipelineState


def record_answerability(state: PipelineState) -> None:
    """Imperative shell: record the pure assessment on a high-stakes run's solution."""
    fs = state.final_solution
    if fs is None or not fs.scope:  # scope is set only for an active high-stakes run
        return
    try:
        from reasoner.application.services.answerability import assess_answerability

        picks = [c.ranking[0] for c in state.critic_scores if c.ranking]
        fs.reliability = assess_answerability(
            fs.claim_labels, fs.verification_audit, picks
        ).to_dict()
    except Exception as exc:
        degraded("pipeline.answerability", None, exc=exc, state=state)


def drain_fallback_events(state: PipelineState, router: Any) -> None:
    """Move fallback events the router buffered (E4) onto the run's state.

    The buffer is attached in ``PipelineOrchestrator.preflight``. Draining
    clears it, so calling this more than once never duplicates an event.
    """
    buffer = getattr(router, "_fallback_buffer", None)
    if buffer:
        state.meta.fallback_events.extend(buffer)
        buffer.clear()
