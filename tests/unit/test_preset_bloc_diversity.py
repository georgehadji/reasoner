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
def test_bloc_of_resolves_cross_vendor_aliases():
    """Aliases that route to another vendor must be scored by the real vendor."""
    # gemini-flash-lite routes to qwen (CN); gemini-pro routes to anthropic (US).
    assert bloc_of("gemini-flash-lite") == "CN"
    assert bloc_of("gemini-pro") == "US"
    assert bloc_of("deepseek-v4-pro") == "CN"
    assert bloc_of("mistral-large-3") == "EU"
    assert bloc_of("gpt-5.5") == "US"
