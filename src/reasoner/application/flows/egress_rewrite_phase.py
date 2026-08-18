"""Layer B: optional best-effort statistical-rewrite pass on the synthesis output.

Runs only when `EgressPolicy.layer_b_enabled` (WATERMARK_LAYER_B_ENABLED, off
by default). Never replaces `state.final_solution.core_solution` unless every
post-condition guard passes; on any rejection the original text is kept and
the reason is reported on the phase's own SSE payload -- a silent downgrade
is not an option (docs/plans/watermark-removal-integration.md Part X.2,
"silent no-op mistaken for success").

Scope: rewrites `core_solution` only, not critical_insights/action_blueprint/
open_questions -- keeps the guard logic to one text blob instead of N, and
matches the reference tool's own single-blob design.

Guards (plan §5.5, enforced here rather than trusted to the model):
  1. Citation integrity   -- no URL present before is missing after.
  2. Number/identifier    -- numbers and backtick-identifiers unchanged as a set.
  3. Length drift          -- output within [0.6x, 1.6x] of input.
  4. Evidence label        -- holds by construction: only core_solution is ever
                              reassigned; claim_labels/evidence are untouched.
  5. Layer A after         -- the rewrite is re-scrubbed before acceptance.
"""

from __future__ import annotations

import re

from reasoner.application.flows.base import WorkflowServices
from reasoner.application.services.egress_policy import resolve_egress_policy
from reasoner.domain.pipeline_state import PipelineState
from reasoner.domain.watermark import scrub_text
from reasoner.domain.watermark.divergence import lexical_divergence
from reasoner.infrastructure.watermark.rewriter import build_rewrite_prompt, select_rewrite_model

_NUMBER_RE = re.compile(r"\b\d[\d.,]*\b")
_IDENTIFIER_RE = re.compile(r"`[^`]+`")
_URL_RE = re.compile(r"https?://[^\s\)\]]+")

_MIN_LENGTH_RATIO = 0.6
_MAX_LENGTH_RATIO = 1.6

_REWRITE_SYSTEM_PROMPT = "You rewrite text exactly as instructed. Output only the rewritten text."


def _urls(text: str) -> set[str]:
    return {u.rstrip("/") for u in _URL_RE.findall(text)}


def _facts(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text)) | set(_IDENTIFIER_RE.findall(text))


def _record(state: PipelineState, report: dict) -> None:
    state.meta.provenance_report = {
        **(state.meta.provenance_report or {}),
        "egress_rewrite": report,
    }


async def run_egress_rewrite_phase(state: PipelineState, services: WorkflowServices) -> None:
    policy = resolve_egress_policy()
    if not policy.layer_b_enabled:
        return

    fs = state.final_solution
    original = getattr(fs, "core_solution", "") if fs else ""
    if not fs or not original.strip():
        return

    origin_model = state.phase_models.get("synthesis", "")
    model = select_rewrite_model(origin_model)
    if model is None:
        reason = "no peer-tier cross-bloc candidate available"
        services.log("EGRESS_REWRITE", f"No rewrite model available ({reason}); skipping", state)
        _record(state, {"rewritten": False, "rejected_reason": reason})
        return

    strategy = policy.layer_b_strategy
    prompt = build_rewrite_prompt(strategy, original)
    try:
        rewritten, _meta = await services.call_llm(
            role="egress_rewrite",
            system_prompt=_REWRITE_SYSTEM_PROMPT,
            user_prompt=prompt,
            state=state,
        )
    except Exception as exc:
        services.log("EGRESS_REWRITE", f"Rewrite call failed, keeping original: {exc}", state)
        _record(state, {"rewritten": False, "rejected_reason": f"rewrite call failed: {exc}"})
        return

    dropped_urls = _urls(original) - _urls(rewritten)
    if dropped_urls:
        reason = f"dropped {len(dropped_urls)} citation(s)"
        services.log("EGRESS_REWRITE", f"Rewrite rejected: {reason}", state)
        _record(state, {"rewritten": False, "rejected_reason": reason})
        return

    if _facts(original) != _facts(rewritten):
        services.log("EGRESS_REWRITE", "Rewrite rejected: numbers/identifiers changed", state)
        _record(state, {"rewritten": False, "rejected_reason": "numbers/identifiers changed"})
        return

    ratio = len(rewritten) / len(original) if original else 1.0
    if not (_MIN_LENGTH_RATIO <= ratio <= _MAX_LENGTH_RATIO):
        reason = f"length drift {ratio:.2f}x outside [{_MIN_LENGTH_RATIO}, {_MAX_LENGTH_RATIO}]"
        services.log("EGRESS_REWRITE", f"Rewrite rejected: {reason}", state)
        _record(state, {"rewritten": False, "rejected_reason": reason})
        return

    divergence = lexical_divergence(original, rewritten)
    scrub_result = scrub_text(rewritten)  # guard 5: Layer A after
    fs.core_solution = scrub_result.text

    services.log(
        "EGRESS_REWRITE",
        f"Rewrote core_solution via {strategy}/{model}, divergence={divergence:.2f}",
        state,
    )
    _record(
        state,
        {
            "rewritten": True,
            "strategy": strategy,
            "model": model,
            "divergence_score": round(divergence, 3),
            "before_len": len(original),
            "after_len": len(scrub_result.text),
        },
    )


__all__ = ["run_egress_rewrite_phase"]
