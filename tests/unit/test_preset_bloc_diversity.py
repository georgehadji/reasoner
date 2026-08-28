"""Cross-bloc diversity invariants for pipeline presets.

Buyl et al. (npj AI 2026, "LLMs reflect the ideology of their creators") show the
creator's geopolitical bloc — not the company — is the dominant axis of an LLM's
ideological bias. Two Chinese labs (e.g. DeepSeek + Qwen) do NOT provide
ideological diversity. These tests enforce that the consequential pipeline roles
span blocs so no single bloc owns the result.

Invariants:
  A. synthesis bloc != scoring bloc (the final user-facing voice and the critic
     that prunes candidates must be cross-bloc).
  B. the perspective/debate generator roles span >=2 known blocs, with <=2 of any
     single bloc.

bloc_of() resolves aliases through the registry's real model string, so
cross-vendor aliases (e.g. gemini-flash-lite -> Qwen -> CN) are scored correctly.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from reasoner.domain.preset_registry import _REGISTRY as PRESETS  # noqa: E402
from reasoner.infrastructure.llm.registry import _REGISTRY as _REGISTRY_MODELS  # noqa: E402
from reasoner.infrastructure.llm.registry import bloc_of  # noqa: E402

# Experimental presets are intentionally single-model / single-bloc.
_EXEMPT = {p for p in PRESETS if "test" in p or "experimental" in PRESETS[p].get("tags", [])}

_NON_EXEMPT = sorted(p for p in PRESETS if p not in _EXEMPT)


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _NON_EXEMPT)
def test_synthesis_and_scoring_are_cross_bloc(preset_id):
    """Invariant A: the final voice and its pruning critic must differ in bloc."""
    routing = PRESETS[preset_id].get("routing", {})
    synth, score = routing.get("synthesis"), routing.get("scoring")
    if not synth or not score:
        pytest.skip("preset has no synthesis/scoring pair")
    b_synth, b_score = bloc_of(synth), bloc_of(score)
    if b_synth == "OTHER":
        pytest.skip("synthesis bloc unknown")
    assert b_synth != b_score, (
        f"{preset_id}: synthesis ({synth} -> {b_synth}) and scoring "
        f"({score} -> {b_score}) share a bloc; the final voice and its critic "
        f"must be cross-bloc"
    )


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _NON_EXEMPT)
def test_generation_spans_multiple_blocs(preset_id):
    """Invariant B: generator roles span >=2 blocs, <=2 of any single bloc."""
    preset = PRESETS[preset_id]
    method = preset.get("method")
    if method == "multi-perspective":
        roles = ("constructive", "destructive", "systemic", "minimalist")
    elif method == "debate":
        roles = ("constructive", "destructive", "systemic")
    else:
        pytest.skip("method has no explicit generator roles")

    routing = preset.get("routing", {})
    primary = preset.get("primary_id", "")
    blocs: dict[str, list[str]] = {}
    for r in roles:
        blocs.setdefault(bloc_of(routing.get(r) or primary), []).append(r)

    known = {b: rs for b, rs in blocs.items() if b != "OTHER"}
    assert len(known) >= 2, (
        f"{preset_id}: generator roles span <2 known blocs ({blocs}); "
        f"generation must be cross-bloc"
    )
    dominant = {b: rs for b, rs in known.items() if len(rs) > 2}
    assert not dominant, (
        f"{preset_id}: bloc(s) dominate generation {dominant}; "
        f"max 2 generator roles per bloc"
    )


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _NON_EXEMPT)
def test_primary_is_key_safe(preset_id):
    """primary_id must build without a provider-specific key.

    filter_routing() rewrites any role whose ``env`` is unset in the
    environment to primary_id, so a primary that is itself gated on a
    provider-specific key cannot act as its own fallback: the downgrade is a
    no-op and build_provider() raises, taking the whole preset down. Every
    non-local registry entry resolves to OPENROUTER_API_KEY, so this asserts
    the primary is not pinned to some other provider's key.
    """
    primary = PRESETS[preset_id].get("primary_id")
    if not primary:
        pytest.skip("preset declares no primary_id")
    entry = _REGISTRY_MODELS.get(primary)
    assert entry is not None, f"{preset_id}: primary_id '{primary}' is not in the registry"
    env = entry.get("env")
    assert env in (None, "OPENROUTER_API_KEY"), (
        f"{preset_id}: primary_id '{primary}' is gated on {env}. primary_id is "
        f"the downgrade target for every key-missing role, so it must not need "
        f"a provider-specific key of its own."
    )


# NOTE: "primary_id must be a different bloc from synthesis" is deliberately
# NOT asserted here. It sounds like it belongs beside invariants A and B, but
# 28 of the 48 presets violate it, so it is not a property this registry holds
# — asserting it would be introducing new routing policy under the guise of a
# regression test. The cross-bloc rule in CLAUDE.md §5 is about the *routed*
# roles, which invariants A and B already cover. Left as a judgment call for
# whoever tunes an individual preset.


@pytest.mark.unit
@pytest.mark.parametrize(
    "preset_id", [p for p in _NON_EXEMPT if PRESETS[p].get("method") == "article"]
)
def test_article_critique_roles_are_cross_bloc(preset_id):
    """Article method's draft->critique and style->audit pairs must be cross-bloc.

    The article flow has no parallel generator roles (test_generation_spans_
    multiple_blocs skips method == "article" for exactly that reason), but it
    does have two sequential draft/critique pairs where the same failure mode
    applies: if the critic shares the drafter's bloc, the critique inherits
    the same blind spots it exists to catch — the same reasoning invariant A
    applies to synthesis/scoring, here applied to article's own editorial
    chain. See docs/plans/article-flow-truncation-remediation.md W6.

    Written as a ratchet, not a blanket assertion (house convention — see the
    "primary_id must differ from synthesis" note below this test): a known
    violation is named explicitly rather than silently exempted, so it stays
    visible instead of disappearing into a passing suite.
    """
    _KNOWN_VIOLATIONS: frozenset[tuple[str, str]] = frozenset({
        # article-premium: writing_draft=gpt-5 and article_critic=grok-4.6 are
        # both US. Found 2026-08-28 while investigating a routing anomaly on a
        # live run (this static check is not itself what produced that
        # anomaly — the preset's definition is internally consistent; the
        # anomaly was the ROUTER's runtime resolution diverging from this
        # definition, which a traced run has not yet explained. See W6.1).
        # Fix by picking a non-US critic for article-premium's article_critic
        # slot, or replace this entry with a comment explaining why premium's
        # critic stays US.
        ("article-premium", "draft_vs_critic"),
    })

    routing = PRESETS[preset_id].get("routing", {})
    primary = PRESETS[preset_id].get("primary_id", "")

    draft = routing.get("writing_draft") or primary
    critic = routing.get("article_critic")
    if critic and (preset_id, "draft_vs_critic") not in _KNOWN_VIOLATIONS:
        assert bloc_of(draft) != bloc_of(critic), (
            f"{preset_id}: writing_draft ({draft} -> {bloc_of(draft)}) and "
            f"article_critic ({critic} -> {bloc_of(critic)}) share a bloc; "
            f"the critic must not share the drafter's blind spots"
        )

    humanize = routing.get("article_humanize") or routing.get("writing_assemble") or primary
    verifier = routing.get("article_verifier")
    if verifier and (preset_id, "humanize_vs_verifier") not in _KNOWN_VIOLATIONS:
        assert bloc_of(humanize) != bloc_of(verifier), (
            f"{preset_id}: article_humanize/writing_assemble ({humanize} -> "
            f"{bloc_of(humanize)}) and article_verifier ({verifier} -> "
            f"{bloc_of(verifier)}) share a bloc; the final audit must not "
            f"share the style pass's blind spots"
        )


@pytest.mark.unit
def test_bloc_of_resolves_cross_vendor_aliases():
    """Aliases that route to another vendor must be scored by the real vendor."""
    # gemini-flash-lite routes to qwen (CN); gemini-pro routes to anthropic (US).
    assert bloc_of("gemini-flash-lite") == "CN"
    assert bloc_of("gemini-pro") == "US"
    assert bloc_of("deepseek-v4-pro") == "CN"
    assert bloc_of("mistral-large-3") == "EU"
    assert bloc_of("gpt-5.5") == "US"
