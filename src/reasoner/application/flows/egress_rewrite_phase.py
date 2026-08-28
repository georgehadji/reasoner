"""Layer B: optional best-effort statistical-rewrite pass on the synthesis output.

Runs when `EgressPolicy.layer_b_enabled` (WATERMARK_LAYER_B_ENABLED, on by
default as of 2026-08-19). Never replaces
`state.final_solution.core_solution` unless every post-condition guard
passes; on any rejection the original text is kept and the reason is
reported on the phase's own SSE payload -- a silent downgrade
is not an option (docs/plans/watermark-removal-integration.md Part X.2,
"silent no-op mistaken for success").

Scope: rewrites `core_solution` only, not critical_insights/action_blueprint/
open_questions -- keeps the guard logic to one text blob instead of N, and
matches the reference tool's own single-blob design.

Guards (plan §5.5, enforced here rather than trusted to the model):
  1. Citation integrity   -- no URL present before is missing after.
  2. Number/identifier    -- no invented numbers; backtick identifiers exact.
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

# Sentence punctuation that a model routinely leaves glued to a trailing URL
# ("...see https://example.com/x."). Without stripping it the citation guard
# rejects the rewrite for "dropping" a URL that is plainly still there --
# observed on the very first live run against a real model.
_URL_TRAILING = ".,;:!?'\"" + "/"

# Paraphrasing legitimately spells small numbers out ("3 regions" -> "three
# regions"); the guard exists to catch a model *changing* 42 into 99, not to
# forbid English. Only the range that actually shows up spelled in prose.
_NUMBER_WORDS: dict[str, str] = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40",
    "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
}
_WORD_RE = re.compile(r"[a-z]+")

_MIN_LENGTH_RATIO = 0.6
_MAX_LENGTH_RATIO = 1.6

# Methods whose deliverable does not live in final_solution.core_solution, or
# already passes through an equivalent editorial rewrite before this phase
# ever runs. The article flow is the concrete case: its deliverable is
# writing_state["final_article"], produced by two dedicated passes
# (humanize + developmental edit — application/flows/article_phases.py) that
# already do what Layer B does for other methods' raw synthesis output.
# core_solution for this method holds a short generic synthesis summary, not
# the article, so a rewrite here protects nothing the reader ever sees and the
# guards reject it near-certainly (confirmed 2026-08-28: 542-char summary,
# 3.8x drift). Skipping is a product decision, not a guard tweak — revisit
# alongside docs/plans/watermark-removal-integration.md before adding to this
# set, since it takes a method out of Layer B protection entirely rather than
# just tuning when the guards fire.
_SKIP_FOR_METHODS: frozenset[str] = frozenset({"article"})

_REWRITE_SYSTEM_PROMPT = "You rewrite text exactly as instructed. Output only the rewritten text."


def _urls(text: str) -> set[str]:
    return {u.rstrip(_URL_TRAILING) for u in _URL_RE.findall(text)}


def _numbers(text: str) -> set[str]:
    """Numeric facts, with spelled-out small numbers folded to their digits."""
    found = {n.rstrip(".,") for n in _NUMBER_RE.findall(text)}
    for word in _WORD_RE.findall(text.lower()):
        if word in _NUMBER_WORDS:
            found.add(_NUMBER_WORDS[word])
    return found


def _identifiers(text: str) -> set[str]:
    return set(_IDENTIFIER_RE.findall(text))


def _record(state: PipelineState, report: dict) -> None:
    state.meta.provenance_report = {
        **(state.meta.provenance_report or {}),
        "egress_rewrite": report,
    }


async def run_egress_rewrite_phase(state: PipelineState, services: WorkflowServices) -> None:
    policy = resolve_egress_policy()
    if not policy.layer_b_enabled:
        return

    if state.method in _SKIP_FOR_METHODS:
        reason = f"method '{state.method}' already editorial-rewritten before this phase"
        services.log("EGRESS_REWRITE", f"Skipping rewrite: {reason}", state)
        _record(state, {"rewritten": False, "rejected_reason": reason})
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

    # Bind the chosen model to this phase's role. ProviderRouter.resolve()
    # falls back to the preset's primary for any role it doesn't know, so
    # without this the "non-origin model" guarantee is cosmetic: the rewrite
    # would run on the very model whose output it is meant to launder.
    try:
        from reasoner.core.ports.model_registry_port import get_model_registry_port

        provider = get_model_registry_port().get_provider(model)
        services.router.routing_table["egress_rewrite"] = provider
    except Exception as exc:
        reason = f"could not bind rewrite model {model}: {exc}"
        services.log("EGRESS_REWRITE", f"Skipping rewrite: {reason}", state)
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

    # Numbers: asymmetric. A figure appearing in the rewrite that was never in
    # the original means the model altered or invented one (42 -> 99), which is
    # the actual danger. Numbers *missing* from the rewrite are not rejected --
    # "one"/"two" occur non-numerically in ordinary prose ("one of the
    # services"), so requiring equality rejected valid paraphrases on live runs.
    invented = _numbers(rewritten) - _numbers(original)
    if invented:
        reason = f"introduced number(s) not in the original: {sorted(invented)}"
        services.log("EGRESS_REWRITE", f"Rewrite rejected: {reason}", state)
        _record(state, {"rewritten": False, "rejected_reason": reason})
        return

    # Identifiers: exact. Backticked names are code, not prose -- there is no
    # legitimate reason for a rewrite to add, drop, or respell one.
    if _identifiers(original) != _identifiers(rewritten):
        reason = "backtick identifiers changed"
        services.log("EGRESS_REWRITE", f"Rewrite rejected: {reason}", state)
        _record(state, {"rewritten": False, "rejected_reason": reason})
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
