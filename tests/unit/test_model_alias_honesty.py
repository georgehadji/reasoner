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


# A deprecated alias may be routed ONLY where no behaviour-neutral rename
# exists. Each entry must say why, and be justified at its preset call site.
_ROUTED_WITHOUT_DROP_IN: frozenset[str] = frozenset({
    # multi-perspective-budget.constructive. "deepseek-v4-flash" serves the same
    # model but adds reasoning.effort=high; swapping bills reasoning tokens at
    # output rate on Phase 2 of the default budget preset.
    "deepseek-v3",
})


@pytest.mark.unit
def test_presets_do_not_route_a_deprecated_alias_that_has_a_drop_in():
    """Where an honest, behaviour-identical name exists, the preset must use it."""
    replaceable = {a for a, r in DEPRECATED_ALIASES.items() if r is not None}
    routed = sorted(_preset_aliases() & replaceable)
    assert not routed, (
        f"presets route deprecated aliases {routed} that have behaviour-identical "
        f"replacements; use the alias naming the served model instead"
    )


@pytest.mark.unit
def test_routing_a_deprecated_alias_without_a_drop_in_is_declared():
    """None must not become a loophole for routing any misleading name."""
    no_drop_in = {a for a, r in DEPRECATED_ALIASES.items() if r is None}
    undeclared = sorted((_preset_aliases() & no_drop_in) - _ROUTED_WITHOUT_DROP_IN)
    assert not undeclared, (
        f"presets route deprecated aliases {undeclared} with no drop-in and no "
        f"entry in _ROUTED_WITHOUT_DROP_IN explaining why that is acceptable"
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
def test_every_stated_replacement_is_a_true_drop_in():
    """Equality on the WHOLE registry entry, not just the served model string.

    An earlier version of this guard compared ``resolved_model_of()`` only, and
    so reported deepseek-v3 -> deepseek-v4-flash as safe. Both serve
    deepseek/deepseek-v4-flash, but the replacement also carries
    ``extra_body={"reasoning": {"effort": "high"}}``. Repointing a preset
    across that difference silently bills reasoning tokens at output rate --
    which is what happened to Phase 2 of multi-perspective-budget before this
    test was tightened. A replacement that is not a true drop-in must be None.
    """
    for alias, replacement in DEPRECATED_ALIASES.items():
        assert alias in _MODEL_WHITELIST, f"{alias} is not registered"
        if replacement is None:
            continue
        assert replacement in _MODEL_WHITELIST, (
            f"{alias} points at replacement {replacement!r}, which is not registered"
        )
        assert _MODEL_WHITELIST[alias] == _MODEL_WHITELIST[replacement], (
            f"{alias} and its stated replacement {replacement} differ beyond the "
            f"name: {_MODEL_WHITELIST[alias]} vs {_MODEL_WHITELIST[replacement]}. "
            f"Swapping is not behaviour-neutral, so the replacement must be None."
        )


@pytest.mark.unit
def test_aliases_without_a_drop_in_are_not_silently_equivalent():
    """Guard the guard: None must mean 'differs', never 'nobody checked'."""
    for alias, replacement in DEPRECATED_ALIASES.items():
        if replacement is not None:
            continue
        twins = [
            other
            for other in _MODEL_WHITELIST
            if other != alias and _MODEL_WHITELIST[other] == _MODEL_WHITELIST[alias]
        ]
        assert not twins, (
            f"{alias} is marked as having no drop-in, but {twins} are entry-identical "
            f"to it -- name one of them as the replacement"
        )
