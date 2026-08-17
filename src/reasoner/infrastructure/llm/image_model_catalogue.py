"""
Image model catalogue — capability families + measured price for every image
model that is BOTH registered in ``registry._REGISTRY`` and present in
``domain/openrouter_models.json`` with ``image`` in its output modalities.

Intent picks the family; the tier picks *cheapest* (budget) or *most capable*
(premium). Pure functions, no LLM, no network — fully unit-testable.

This module must NOT import ``reasoner.hypergate`` (hypergate → infrastructure
is the sanctioned direction; the reverse would be a new layering violation).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Price normalisation ───────────────────────────────────────────────
#
# OpenRouter prices image models two incompatible ways:
#   * ``image``        — flat USD per generated image (pure generators only)
#   * ``image_output`` — USD per *output image token*
# To compare them we convert the token rate to USD/image with a fixed
# tokens-per-image estimate. 1290 is Gemini's measured output-token count for a
# 1024px image; it reproduces the published per-image list prices closely
# (gemini-2.5-flash-image → $0.039, gpt-image-2 → $0.039, recraft-v4.1-pro-vector
# → $0.093). It is an APPROXIMATION: real token counts vary with resolution, so
# these numbers rank models correctly but are not billing-accurate.
TOKENS_PER_IMAGE: int = 1290

# A flat ``image`` price is only the per-image output price for *pure* image
# generators (no chat token pricing). On hybrid chat+image models (Gemini) the
# same field is the per-*input*-image price and is 100x too low, so those are
# always priced from ``image_output``.

# ── Capability ranking ────────────────────────────────────────────────
#
# "Premium" means MOST CAPABLE, not most expensive — price is only a tiebreak.
# Capability is derived from the catalogue id (a size/quality word plus the
# version number), so a newly listed model ranks itself with no code change:
# gpt-image-2 > gpt-image-1, recraft-v4.1 > recraft-v4 > recraft-v3,
# seedream-5 > seedream-4.5, riverflow-v2.5 > riverflow-v2.
#
# THIS IS THE ONLY HAND-MAINTAINED RANKING IN THE MODULE. Size/quality words
# that appear in image model ids, weakest → strongest. The empty string is the
# rank of an id carrying none of them (a plain, full-size model), which is why
# flux.2-max > flux.2-pro > flux.2-flex > flux.2-klein-4b falls out for free.
# "preview" sits at the bottom: a preview build loses to its stable twin.
# Add a word here only when a lab ships a size suffix that is not yet listed.
_TIER_WORDS: tuple[str, ...] = (
    "preview", "klein", "nano", "mini", "lite", "turbo", "fast", "flash",
    "flex", "medium", "", "large", "quality", "pro", "max",
)
_PLAIN_TIER_RANK: int = _TIER_WORDS.index("")
_VERSION_RE = re.compile(r"\d+(?:\.\d+)?")
# Whole-token match only: "mini" is a substring of "gemini", which would demote
# every Gemini model to the mini tier.
_TOKEN_RE = re.compile(r"[a-z]+")

# ── Capability families ───────────────────────────────────────────────
FAMILY_VECTOR = "vector"
FAMILY_PHOTOREAL = "photoreal"
FAMILY_TEXT_IN_IMAGE = "text_in_image"
FAMILY_DESIGN = "design"
FAMILY_GENERAL = "general"
FAMILY_REFERENCE_EDIT = "reference_edit"

FAMILIES: tuple[str, ...] = (
    FAMILY_VECTOR,
    FAMILY_PHOTOREAL,
    FAMILY_TEXT_IN_IMAGE,
    FAMILY_DESIGN,
    FAMILY_GENERAL,
    FAMILY_REFERENCE_EDIT,
)


@dataclass(frozen=True)
class ImageModelInfo:
    """One registered image-capable model alias."""

    alias: str
    model_id: str
    lab: str                    # org prefix of the catalogue id
    families: frozenset[str]
    price_per_image: float      # normalised USD/image
    accepts_image_input: bool


def _families_for(model_id: str, accepts_image_input: bool) -> frozenset[str]:
    """Derive capability families from the catalogue id (data-driven, no table)."""
    lowered = model_id.lower()
    tags = {FAMILY_GENERAL}
    if "vector" in lowered:
        tags |= {FAMILY_VECTOR, FAMILY_DESIGN}
    if "recraft" in lowered or "riverflow" in lowered:
        tags.add(FAMILY_DESIGN)
    # Recraft and the OpenAI image family are the reliable in-image text renderers.
    if "recraft" in lowered or "openai/" in lowered:
        tags.add(FAMILY_TEXT_IN_IMAGE)
    if any(t in lowered for t in ("flux", "seedream", "krea", "grok", "qwen", "gemini")):
        tags.add(FAMILY_PHOTOREAL)
    if accepts_image_input:
        tags.add(FAMILY_REFERENCE_EDIT)
    return frozenset(tags)


def _price_per_image(pricing: dict[str, object]) -> float | None:
    """Normalise OpenRouter pricing to comparable USD/image. None if unpriced."""
    def _f(key: str) -> float | None:
        try:
            return float(pricing[key])  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError):
            return None

    prompt = _f("prompt")
    flat = _f("image")
    # Pure generator (no chat token pricing) → the flat `image` field is USD/image.
    if flat and not prompt:
        return flat
    token_rate = _f("image_output")
    if token_rate:
        return token_rate * TOKENS_PER_IMAGE
    return flat or None


def _load_catalogue_entries() -> list[dict]:
    """Load raw OpenRouter catalogue entries (same file domain/pricing.py reads)."""
    path = Path(__file__).resolve().parents[2] / "domain" / "openrouter_models.json"
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except Exception as exc:  # missing/corrupt catalogue must not break generation
        logger.warning("Failed to load image catalogue from %s: %s", path, exc)
        return []
    return payload.get("data", []) if isinstance(payload, dict) else payload


@lru_cache(maxsize=1)
def image_catalogue() -> dict[str, ImageModelInfo]:
    """alias → ImageModelInfo for every registered, image-output-capable model."""
    from reasoner.infrastructure.llm.registry import _REGISTRY

    by_id = {e.get("id"): e for e in _load_catalogue_entries()}
    out: dict[str, ImageModelInfo] = {}
    for alias, cfg in _REGISTRY.items():
        entry = by_id.get(cfg.get("model"))
        if not entry:
            continue
        arch = entry.get("architecture") or {}
        if "image" not in (arch.get("output_modalities") or []):
            continue
        price = _price_per_image(entry.get("pricing") or {})
        if price is None:
            continue
        model_id = str(entry["id"])
        accepts_image_input = "image" in (arch.get("input_modalities") or [])
        out[alias] = ImageModelInfo(
            alias=alias,
            model_id=model_id,
            lab=model_id.split("/")[0],
            families=_families_for(model_id, accepts_image_input),
            price_per_image=price,
            accepts_image_input=accepts_image_input,
        )
    return out


def _emits_svg(m: ImageModelInfo) -> bool:
    """True for SVG/vector generators. The catalogue id suffix is the contract."""
    return m.model_id.endswith("-vector")


def emits_svg_only(aliases: list[str]) -> bool:
    """True when every alias in `aliases` is an SVG generator (empty → False).

    The one signal a generation caller needs to tell a *shallow* selection apart
    from a *failed* one. Only the vector family is exempt from returning `count`
    models (see ``select_models``), so an all-SVG selection that came back short
    is correct-and-complete, not broken: substituting raster models to reach
    `count` would change the requested output format.
    """
    catalogue = image_catalogue()
    infos = [catalogue[a] for a in aliases if a in catalogue]
    return len(infos) == len(aliases) and bool(infos) and all(_emits_svg(m) for m in infos)


def _capability(m: ImageModelInfo) -> tuple[int, float, float]:
    """(tier rank, version, price) — higher is more capable. Derived from the id.

    Price is the last element, so it only breaks ties between models of the same
    tier word and version.
    """
    lowered = m.model_id.lower()
    tokens = set(_TOKEN_RE.findall(lowered))
    ranks = [i for i, word in enumerate(_TIER_WORDS) if word and word in tokens]
    versions = [float(v) for v in _VERSION_RE.findall(lowered)]
    return (
        min(ranks, default=_PLAIN_TIER_RANK),
        max(versions, default=0.0),
        m.price_per_image,
    )


def _candidates(family: str, tier: str, needs_reference_input: bool) -> list[ImageModelInfo]:
    """Family members, cheapest-first (budget) or most-capable-first (premium).

    SVG models are hard-filtered both ways: they are the ONLY members of the
    "vector" family and are excluded from every other family at any price. An
    SVG returned for a photo prompt is a broken response, not a cheaper one.
    """
    want_svg = family == FAMILY_VECTOR
    pool = [
        m for m in image_catalogue().values()
        if family in m.families
        and _emits_svg(m) == want_svg
        and (m.accepts_image_input or not needs_reference_input)
    ]
    # Alias-sorted first so the stable sorts below break every tie deterministically.
    pool.sort(key=lambda m: m.alias)
    if tier == "premium":
        return sorted(pool, key=_capability, reverse=True)
    return sorted(pool, key=lambda m: m.price_per_image)


def _take(
    pool: list[ImageModelInfo],
    count: int,
    picked: list[str],
    labs: set[str],
    allow_repeat_lab: bool = False,
) -> None:
    """Append best-first picks from `pool` into `picked`, one per lab by default."""
    for m in pool:
        if len(picked) >= count:
            return
        if m.alias in picked or (m.lab in labs and not allow_repeat_lab):
            continue
        picked.append(m.alias)
        labs.add(m.lab)


def select_models(
    family: str,
    tier: str,
    count: int,
    needs_reference_input: bool,
) -> tuple[list[str], list[str]]:
    """Pick `count` cross-lab primaries plus >=4 fallbacks for a family and tier.

    Family picks come first; if the family is too lab-thin to fill `count` with
    distinct labs, the pool widens to "general" rather than returning fewer.
    Returned aliases are always present in ``registry._REGISTRY``.

    EXEMPTION — the "vector" family is exempt from BOTH the `count` and the
    >=4-distinct-labs invariants, and never widens. Only Recraft ships SVG
    models, so lab diversity and vector output are in direct conflict; widening
    would hand a caller who asked for SVG a raster PNG, which is a wrong answer
    rather than a less diverse one. Diversity loses. The vector family therefore
    returns however many vector models exist (possibly fewer than `count`, and
    possibly no fallbacks at all) and nothing else.
    """
    if family not in FAMILIES:
        family = FAMILY_GENERAL
    tier = tier if tier in ("budget", "premium") else "budget"

    pool = _candidates(family, tier, needs_reference_input)

    if family == FAMILY_VECTOR:
        vector_aliases = [m.alias for m in pool]
        return vector_aliases[:count], vector_aliases[count:]

    wider = pool if family == FAMILY_GENERAL else _candidates(
        FAMILY_GENERAL, tier, needs_reference_input
    )

    primaries: list[str] = []
    labs: set[str] = set()
    # Family first, one model per lab; a lab-thin family widens to "general"
    # rather than doubling up on one lab or returning fewer than `count`.
    _take(pool, count, primaries, labs)
    _take(wider, count, primaries, labs)
    _take(pool, count, primaries, labs, allow_repeat_lab=True)
    _take(wider, count, primaries, labs, allow_repeat_lab=True)

    used = set(primaries)
    fallbacks = [m.alias for m in pool if m.alias not in used]
    fallbacks += [m.alias for m in wider if m.alias not in used and m.alias not in fallbacks]
    return primaries, fallbacks[: max(4, count)]
