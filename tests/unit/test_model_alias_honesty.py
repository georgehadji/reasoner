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

# Aliases whose NAME misstates the version or tier they serve. Every one is a
# deliberate back-compat or cost redirection, documented at its registry entry.
# They may exist; a preset may not route them. Removing an entry from this set
# requires either fixing the alias name or deleting the alias.
_DEPRECATED_MISLEADING: frozenset[str] = frozenset({
    "deepseek-v3",             # serves deepseek/deepseek-v4-flash
    "deepseek-v4-flash-0424",  # a "pin" that pins nothing
    "qwen3-turbo",             # serves qwen/qwen3.5-flash-02-23
    "qwen3-max",               # serves qwen/qwen3.7-plus (the real one is qwen3-max-real)
    "qwen3-plus",              # serves qwen/qwen3.7-plus
    "qwen3.5-plus",            # serves qwen/qwen3.7-plus
    "qwen3.6-plus",            # serves qwen/qwen3.7-plus
    "mimo-v2-flash",           # serves xiaomi/mimo-v2.5
    "mimo-v2-pro",             # serves xiaomi/mimo-v2.5-pro
    "gemini-3.1-flash-lite",   # duplicate of gemini-flash-lite-real
})

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
    and capability_registry.py actually load. The stale duplicate at the repo
    root is ~74 models behind and must not be used for this.
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
