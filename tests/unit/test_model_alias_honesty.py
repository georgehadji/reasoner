"""A model alias must not lie about the model it serves.

This registry deliberately contains aliases whose key differs from the served
model string, and that is not itself a bug -- cost-motivated redirection
(`qwen3.6-plus` -> `qwen/qwen3.7-plus`) and back-compat pins are legitimate.
The bug is a *preset* routing through a name that misstates what will actually
run, because every downstream judgement -- the cross-bloc invariants, the
one-model-per-phase rule, cost estimates, the Delphi panel's independence --
is made by a human reading the preset.

Two aliases used to serve another lab outright: `gemini-pro` ->
`anthropic/claude-sonnet-5` and `gemini-flash-lite` ->
`qwen/qwen3.5-flash-02-23`. Both were retired. A third, `MODEL_GEMINI_FLASH`,
had its value swapped to `"grok-4.3"` without renaming, colliding with the
literal `"grok-4.3"` key so that the dict silently held one fewer model than it
appeared to. These tests exist so none of that returns silently.

See docs/ENSEMBLE_DIVERSITY.md §4 for what a misleading alias cost in practice.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from reasoner.domain.preset_registry import _REGISTRY as PRESETS  # noqa: E402
from reasoner.infrastructure.llm.registry import (  # noqa: E402
    DEPRECATED_ALIASES,
    _MODEL_WHITELIST,
    _vendor_of,
    resolved_model_of,
)

# Alias-name token -> the OpenRouter vendor prefix it implies.
# Order matters: the first token found in the alias wins.
_IMPLIED_VENDOR: tuple[tuple[str, str], ...] = (
    ("claude", "anthropic"), ("fable", "anthropic"),
    ("gpt", "openai"), ("codex", "openai"),
    ("gemini", "google"), ("gemma", "google"),
    ("grok", "x-ai"),
    ("sonar", "perplexity"),
    ("ministral", "mistralai"), ("mistral", "mistralai"), ("codestral", "mistralai"),
    ("deepseek", "deepseek"),
    ("kimi", "moonshotai"), ("moonshot", "moonshotai"),
    ("glm", "z-ai"),
    ("minimax", "minimax"),
    ("mimo", "xiaomi"),
    ("laguna", "poolside"),
    ("inkling", "thinkingmachines"),
    ("recraft", "recraft"),
    ("seedream", "bytedance-seed"),
)

# The canonical list lives in the registry (infrastructure owns alias facts) so
# PresetService can warn on it at runtime; this test only pins its properties.
# Removing an entry requires either fixing the alias name or deleting the alias
# -- and deleting one is a breaking API change, see the registry's own comment.
_DEPRECATED_MISLEADING: frozenset[str] = frozenset(DEPRECATED_ALIASES)

_CATALOGUE = Path(__file__).resolve().parents[2] / "src" / "reasoner" / "domain" / "openrouter_models.json"


def _preset_aliases() -> set[str]:
    out: set[str] = set()
    for cfg in PRESETS.values():
        out |= {a for a in (cfg.get("routing") or {}).values() if a}
        out |= {a for a in (cfg.get("fallback_routing") or {}).values() if a}
        if cfg.get("primary_id"):
            out.add(cfg["primary_id"])
    return out


@pytest.mark.unit
def test_no_alias_implies_the_wrong_vendor():
    """`gemini-pro` -> anthropic must never come back."""
    wrong = []
    for alias in _MODEL_WHITELIST:
        low = alias.lower()
        if low.startswith("ollama-"):
            continue  # local models have no vendor prefix
        served = resolved_model_of(alias).lstrip("~")
        if "/" not in served:
            continue
        for token, expected in _IMPLIED_VENDOR:
            if token in low:
                actual = _vendor_of(alias)
                if actual != expected:
                    wrong.append((alias, served, token, expected, actual))
                break
    assert not wrong, (
        "aliases naming one vendor but serving another:\n"
        + "\n".join(f"  {a} -> {s} (name says {t!r}={e}, serves {v})" for a, s, t, e, v in wrong)
    )


@pytest.mark.unit
def test_presets_do_not_route_known_misleading_aliases():
    """A preset must name what will actually run."""
    routed = sorted(_preset_aliases() & _DEPRECATED_MISLEADING)
    assert not routed, (
        f"presets route deprecated/misleading aliases {routed}; use the alias "
        f"that names the served model instead (same model, honest name)"
    )


@pytest.mark.unit
@pytest.mark.parametrize("alias", sorted(_DEPRECATED_MISLEADING))
def test_deprecated_aliases_still_resolve(alias):
    """Kept for back-compat, so they must keep working -- just not be routed."""
    assert alias in _MODEL_WHITELIST, (
        f"{alias} was deleted; older saved states referencing it now fail to "
        f"resolve. Either restore it or drop it from _DEPRECATED_MISLEADING."
    )


@pytest.mark.unit
def test_every_preset_routed_model_exists_in_the_catalogue():
    """A routed alias pointing at a withdrawn model fails only at call time.

    Checked against domain/openrouter_models.json -- the copy that pricing.py
    and image_model_catalogue.py actually load, and now the only one any code
    reads. A stale 346-entry duplicate used to sit at the repo root (a local
    scratch dump per docs/openrouter-catalogue-2026-08.md); auditing against it
    reported 124 false "dead model" hits, so it was deleted. An equally stale
    copy remains under docs/ as a dated archive -- see
    tests/unit/test_catalogue_source.py.
    """
    if not _CATALOGUE.exists():
        pytest.skip("catalogue snapshot missing")
    data = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
    items = data.get("data", data) if isinstance(data, dict) else data
    ids = {m.get("id") for m in items if isinstance(m, dict)}

    missing = []
    for alias in sorted(_preset_aliases()):
        served = resolved_model_of(alias).lstrip("~")
        if "/" not in served or served.endswith("-latest"):
            continue  # local models; auto-updating pseudo-ids are not catalogue rows
        if served not in ids and served.split(":")[0] not in ids:
            missing.append((alias, served))
    assert not missing, (
        "presets route aliases whose served model is absent from the catalogue "
        f"snapshot (verify upstream before trusting): {missing}"
    )


# ── Phase 1 of the deprecation: observe, do not break ──────────────────────
# `routing` is a public request field (api/schemas.py), so a caller may still
# name a deprecated alias. It must keep working -- and it must be visible that
# they did, so a later decision to delete rests on evidence rather than hope.


@pytest.mark.unit
def test_caller_supplied_deprecated_alias_is_warned_about(caplog):
    from reasoner.application.services.preset_service import PresetService

    with caplog.at_level("WARNING", logger="reasoner.application.services.preset_service"):
        PresetService().build_router(
            "multi-perspective-budget",
            custom_routing={"primary": "claude-sonnet", "constructive": "deepseek-v3"},
        )

    warned = [r.getMessage() for r in caplog.records if "Deprecated model alias" in r.getMessage()]
    assert warned, f"no deprecation warning; saw {[r.getMessage() for r in caplog.records]}"
    msg = warned[0]
    assert "deepseek-v3" in msg and "constructive" in msg
    assert "deepseek-v4-flash" in msg, "warning must name the honest replacement"


@pytest.mark.unit
def test_deprecated_alias_still_routes(caplog):
    """Warning only. The alias resolves exactly as before -- no behaviour change."""
    from reasoner.application.services.preset_service import PresetService

    _, router = PresetService().build_router(
        "multi-perspective-budget",
        custom_routing={"primary": "claude-sonnet", "constructive": "deepseek-v3"},
    )
    assert router.resolve("constructive").model == resolved_model_of("deepseek-v3")


@pytest.mark.unit
def test_honest_alias_produces_no_warning(caplog):
    from reasoner.application.services.preset_service import PresetService

    with caplog.at_level("WARNING", logger="reasoner.application.services.preset_service"):
        PresetService().build_router(
            "multi-perspective-budget",
            custom_routing={"primary": "claude-sonnet", "constructive": "deepseek-v4-flash"},
        )
    assert not [r for r in caplog.records if "Deprecated model alias" in r.getMessage()]


@pytest.mark.unit
def test_every_deprecated_alias_names_a_resolvable_replacement():
    for alias, replacement in DEPRECATED_ALIASES.items():
        assert replacement in _MODEL_WHITELIST, (
            f"{alias} points at replacement {replacement!r}, which is not registered"
        )
        assert resolved_model_of(alias) == resolved_model_of(replacement), (
            f"{alias} serves {resolved_model_of(alias)} but its stated replacement "
            f"{replacement} serves {resolved_model_of(replacement)} -- the warning "
            f"would send callers to a different model"
        )
