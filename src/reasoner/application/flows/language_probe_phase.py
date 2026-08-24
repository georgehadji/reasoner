"""Cross-lingual probe phase (Part B) — language-bias mitigation.

Runs synthesis a second time on a state copy that reasons in the user's
native language, then measures divergence from the English-pivot synthesis.
Diverged results surface an epistemic warning and downgrade top-line claims.

Gate: language_sensitive AND output_language != English AND premium preset
      AND LANGUAGE_PROBE_ENABLED=true (default false).
"""

from __future__ import annotations

import copy
import logging
from typing import Any

from reasoner.application.flows.base import WorkflowServices
from reasoner.domain.pipeline_state import PipelineState

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM = (
    "You are an impartial evaluator. "
    "Compare two AI-generated assessments of the same problem. "
    "Determine whether they differ *materially* in conclusions, "
    "recommendations, or ideological framing — not just wording. "
    "Output ONLY valid JSON: "
    "{\"diverged\": bool, \"reason\": \"one sentence\"}"
)


async def run_language_probe_phase(state: PipelineState, services: WorkflowServices) -> None:
    """Re-run synthesis in user language; measure and label divergence."""
    from reasoner.core.settings import settings

    if not settings.LANGUAGE_PROBE_ENABLED:
        return
    if not state.language_sensitive:
        return
    if not state.output_language or state.output_language == "English":
        return
    if not state.pivot_active:
        return

    english_solution = state.final_solution
    if english_solution is None:
        return

    english_text = english_solution.core_solution
    if not english_text:
        return

    services.log(
        "LANG-PROBE",
        f"Probing sensitivity in {state.output_language} (axis: {state.language_divergence.get('axis', '?')}).",
        state,
    )

    # ── B2: Re-run synthesis on a state clone with native language ────
    probe_state = copy.deepcopy(state)
    probe_state.language = state.output_language
    probe_state.pivot_active = False
    probe_state.final_solution = None

    try:
        from reasoner.application.flows.synthesis_phase import run_synthesis_phase
        await run_synthesis_phase(probe_state, services)
    except Exception as exc:
        services.log("LANG-PROBE", f"Probe synthesis failed: {exc}; skipping.", state)
        return

    probe_solution = probe_state.final_solution
    if probe_solution is None:
        services.log("LANG-PROBE", "Probe synthesis returned no solution; skipping.", state)
        return

    probe_text = probe_solution.core_solution

    # ── B3: Divergence detection via LLM judge ────────────────────────
    judge_prompt = (
        f"Assessment A (English reasoning):\n{english_text[:3000]}\n\n"
        f"Assessment B ({state.output_language} reasoning):\n{probe_text[:3000]}"
    )
    diverged = False
    reason = ""
    try:
        from reasoner.parsing import extract_json
        raw, _ = await services.call_llm(
            role="synthesis",
            system_prompt=_JUDGE_SYSTEM,
            user_prompt=judge_prompt,
            state=state,
            phase_key="lang_probe_judge",
            max_tokens=256,
            temperature=0.0,
        )
        parsed: dict[str, Any] = extract_json(raw) or {}
        diverged = bool(parsed.get("diverged", False))
        reason = str(parsed.get("reason", ""))
    except Exception as exc:
        services.log("LANG-PROBE", f"Divergence judge failed: {exc}; treating as not diverged.", state)
        return

    state.language_divergence = {
        "diverged": diverged,
        "reason": reason,
        "english_claim": english_text[:500],
        "inlang_claim": probe_text[:500],
        "probe_language": state.output_language,
    }

    if not diverged:
        services.log("LANG-PROBE", f"No material divergence detected. {reason}", state)
        return

    # ── B4: Downgrade claims + attach epistemic note ──────────────────
    services.log("LANG-PROBE", f"Divergence detected: {reason}", state)

    from reasoner.domain.models import ClaimLabel
    fs = state.final_solution
    if fs is not None:
        # Downgrade any VERIFIED top-level claims to HYPOTHESIS
        updated_labels: dict[str, Any] = {}
        for claim, label in (fs.claim_labels or {}).items():
            if label == ClaimLabel.VERIFIED:
                updated_labels[claim] = ClaimLabel.HYPOTHESIS
            else:
                updated_labels[claim] = label
        fs.claim_labels = updated_labels

        # Attach language note to meta_audit
        language_note = (
            f"[LANGUAGE-SENSITIVITY] This answer was generated using English-language "
            f"reasoning (pivot). A parallel {state.output_language}-language synthesis "
            f"produced materially different conclusions ({reason}). "
            f"Top claims downgraded to HYPOTHESIS. Treat with epistemic caution."
        )
        if fs.meta_audit is not None:
            existing = getattr(fs.meta_audit, "remaining_uncertainty", "") or ""
            fs.meta_audit.remaining_uncertainty = (
                f"{existing}\n{language_note}".strip() if existing else language_note
            )
        state.language_divergence["language_note"] = language_note
