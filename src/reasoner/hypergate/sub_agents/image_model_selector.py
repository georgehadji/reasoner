"""
ImageModelSelector — ONE JOB: map an image prompt to a capability family and a
cost tier hint. Invoked on demand by the image-generation endpoint; it is NOT
part of the HyperGate Phase-1 parallel gather.

Real model names never appear in the prompt (same discipline as
method_classifier's opaque letters) — the agent only names a capability family.

Output schema: {family, tier_hint, confidence, rationale}
"""

from __future__ import annotations

from typing import Any

from reasoner.core.constants import HYPERGATE_MAX_TOKENS_IMAGE_MODEL
from reasoner.hypergate.base_sub_agent import BaseSubAgent

_SYSTEM = (
    "Classify the image request into the capability family an image model must have.\n"
    "- 'vector': logo, icon, flat mark, SVG-style artwork with crisp shapes\n"
    "- 'photoreal': photographic realism, people, products, scenes, lighting\n"
    "- 'text_in_image': posters, signage, labels, UI copy — legible text inside the image\n"
    "- 'design': layouts, marketing/brand assets, illustration with composition constraints\n"
    "- 'reference_edit': edits or restyles a supplied reference image\n"
    "- 'general': anything else, or unclear\n"
    "Also give 'tier_hint': 'budget' for simple/casual requests, "
    "'premium' when the request needs high fidelity, fine detail, or professional output.\n"
    "Output ONLY valid JSON with exactly these keys: "
    "'family' (one of: vector, photoreal, text_in_image, design, reference_edit, general), "
    "'tier_hint' (one of: budget, premium), "
    "'confidence' (float 0.0-1.0), "
    "'rationale' (one short sentence). "
    "No markdown, no explanation."
)

_VALID_TIERS = {"budget", "premium"}
# Mirrors infrastructure.llm.image_model_catalogue.FAMILIES, duplicated because
# hypergate may not import infrastructure (see .importlinter). Drift is safe:
# select_models() coerces an unrecognised family to "general" as well.
_VALID_FAMILIES = {
    "vector",
    "photoreal",
    "text_in_image",
    "design",
    "reference_edit",
    "general",
}


class ImageModelSelector(BaseSubAgent):
    AGENT_NAME = "image_model"
    MAX_TOKENS = HYPERGATE_MAX_TOKENS_IMAGE_MODEL

    def _system_prompt(self) -> str:
        return _SYSTEM

    def _parse_result(self, raw: str) -> dict[str, Any]:
        try:
            data = self._extract_json(raw)
            family = str(data.get("family", "general")).lower().strip()
            if family not in _VALID_FAMILIES:
                family = "general"
            tier_hint = str(data.get("tier_hint", "budget")).lower().strip()
            if tier_hint not in _VALID_TIERS:
                tier_hint = "budget"
            return {
                "family": family,
                "tier_hint": tier_hint,
                "confidence": min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
                "rationale": str(data.get("rationale", "")),
            }
        except Exception:
            return {
                "family": "general",
                "tier_hint": "budget",
                "confidence": 0.0,
                "rationale": "",
            }
