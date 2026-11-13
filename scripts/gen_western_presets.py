#!/usr/bin/env python3
"""Generate the Western-only preset tier from the base presets.

Writes ``src/reasoner/domain/preset_registry_western.py``: one
``<method>-western-<tier>`` preset per base preset, with every CN or OTHER
model swapped for a US or EU one. The output is literal dicts so a reviewer
reads exactly what runs; ``tests/unit/test_preset_western.py`` fails when the
checked-in file drifts from what this script would write.

Swap rule, per slot: among Western chat models already trusted by some preset
(plus every Mistral model), pick the closest in price to the model it
replaces, prefer EU and less-used vendors, and keep every rule in
``scripts/validate_presets.check_preset``. A depth-first search backtracks
when a group rule (bloc spread, lab diversity, synthesis vs scoring) fails.

Usage:
  python scripts/gen_western_presets.py          # write the file
  python scripts/gen_western_presets.py --check  # exit 1 if it would change
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from validate_presets import check_preset, target_temperature  # noqa: E402

from reasoner.core.model_policy import WESTERN_BLOCS, WESTERN_TAG  # noqa: E402
from reasoner.core.ports.model_registry_port import set_model_registry_port  # noqa: E402
from reasoner.domain.preset_core import PipelinePreset, western_variant  # noqa: E402
from reasoner.domain.preset_registry import _REGISTRY as PRESETS  # noqa: E402
from reasoner.domain.pricing import blended_usd_per_mtok, fallback_within_budget  # noqa: E402
from reasoner.infrastructure.llm.pricing_resolver import get_pricing  # noqa: E402
from reasoner.infrastructure.llm.registry import _REGISTRY as MODELS  # noqa: E402
from reasoner.infrastructure.llm.registry import (  # noqa: E402
    RegistryAdapter,
    _vendor_of,
    bloc_of,
    honours_tuned_temperature,
    resolved_model_of,
)

set_model_registry_port(RegistryAdapter())  # get_pricing reads the registry through the port

OUT = ROOT / "src" / "reasoner" / "domain" / "preset_registry_western.py"

# Hand fixes the search gets wrong: {western_id: {slot: alias}}. Empty today.
OVERRIDES: dict[str, dict[str, str]] = {}

# Search-grounded models are kept where a base preset put them, never used as
# a stand-in for a plain chat model.
_NO_SUBSTITUTE_PREFIXES = ("sonar",)
_MAX_LEAVES = 50_000


def _is_image(alias: str) -> bool:
    return bool(MODELS[alias].get("extra_body", {}).get("include_images"))


def _price(alias: str) -> float:
    e = MODELS[alias]
    return max(float(e.get("price_in", 0)) + float(e.get("price_out", 0)), 0.01)


def _western(alias: str | None) -> bool:
    return bool(alias) and bloc_of(alias) in WESTERN_BLOCS


def _base_presets() -> dict[str, dict]:
    return {pid: p for pid, p in PRESETS.items() if WESTERN_TAG not in p.get("tags", [])}


def _pool() -> list[str]:
    seen: set[str] = set()
    for p in _base_presets().values():
        seen.add(p["primary_id"])
        seen.update(p.get("routing", {}).values())
        seen.update(p.get("fallback_routing", {}).values())
        for chain in p.get("cascading_routing", {}).values():
            seen.update(chain)
    seen.update(a for a in MODELS if bloc_of(a) == "EU")
    return sorted(
        a for a in seen
        if a in MODELS and _western(a) and not a.startswith(_NO_SUBSTITUTE_PREFIXES)
        and MODELS[a].get("env") in (None, "OPENROUTER_API_KEY")
        and not MODELS[a].get("is_local")
    )


POOL = _pool()


def _ranked(original: str, role: str, vendor_use: dict[str, int]) -> list[str]:
    """Western candidates for one slot, best first."""
    image = _is_image(original)
    target = target_temperature(role)
    need_temp = target is not None and target < 0.7
    base = _price(original)

    def key(a: str) -> tuple[float, str]:
        score = abs(math.log(_price(a) / base))
        score -= 0.5 if bloc_of(a) == "EU" else 0.0
        score += 0.4 * vendor_use.get(_vendor_of(a), 0)
        return (score, a)

    cands = [
        a for a in POOL
        if _is_image(a) == image and (not need_temp or honours_tuned_temperature(a))
    ]
    return sorted(cands, key=key)


def _build(pid: str, base: dict) -> dict:
    wid = western_variant(pid)
    preset = {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
              for k, v in base.items()}
    preset["tags"] = [*base.get("tags", []), WESTERN_TAG]

    overrides = OVERRIDES.get(wid, {})
    for slot, alias in overrides.items():
        if slot == "primary_id":
            preset["primary_id"] = alias
        else:
            preset["routing"][slot] = alias

    # Slots that need a Western model; "primary_id" counts as a slot.
    slots = [("primary_id", preset["primary_id"])] + list(preset.get("routing", {}).items())
    todo = [(s, m) for s, m in slots if not _western(m)]
    fixed = [m for s, m in slots if _western(m)]

    vendor_use: dict[str, int] = {}
    for m in fixed:
        vendor_use[_vendor_of(m)] = vendor_use.get(_vendor_of(m), 0) + 1
    used = {resolved_model_of(m) for m in fixed}

    def assign(slot: str, alias: str) -> None:
        if slot == "primary_id":
            preset["primary_id"] = alias
        else:
            preset["routing"][slot] = alias

    leaves = 0

    def dfs(i: int) -> bool:
        nonlocal leaves
        if i == len(todo):
            leaves += 1
            if leaves > _MAX_LEAVES:
                raise RuntimeError(f"{wid}: search exhausted {_MAX_LEAVES} leaves")
            return not check_preset(PipelinePreset(**preset, id=wid))
        slot, original = todo[i]
        for cand in _ranked(original, slot, vendor_use)[:8]:
            served = resolved_model_of(cand)
            if served in used:
                continue
            used.add(served)
            v = _vendor_of(cand)
            vendor_use[v] = vendor_use.get(v, 0) + 1
            assign(slot, cand)
            if dfs(i + 1):
                return True
            used.discard(served)
            vendor_use[v] -= 1
        return False

    if not dfs(0):
        raise RuntimeError(f"{wid}: no Western assignment satisfies check_preset")

    # Fallbacks: Western, and never the model the role already runs on.
    fallbacks = dict(preset.get("fallback_routing", {}))
    for role, model in list(fallbacks.items()):
        runs_on = resolved_model_of(preset["routing"].get(role, preset["primary_id"]))
        if _western(model) and resolved_model_of(model) != runs_on:
            continue
        fallbacks[role] = next(
            a for a in _ranked(model, role, {}) if resolved_model_of(a) != runs_on
        )

    # A role with no fallback retries on the primary; when that costs more than
    # the router allows (tests/test_preset_fallback_budget.py), name one.
    def within(model: str, fallback: str) -> bool:
        return fallback_within_budget(
            blended_usd_per_mtok(get_pricing(model)), blended_usd_per_mtok(get_pricing(fallback))
        )

    for role, model in preset["routing"].items():
        if model == preset["primary_id"] or role in fallbacks:
            continue
        if within(model, preset["primary_id"]):
            continue
        fallbacks[role] = next(
            a for a in _ranked(model, role, {})
            if resolved_model_of(a) != resolved_model_of(model) and within(model, a)
        )
    if fallbacks:
        preset["fallback_routing"] = fallbacks

    # Cascades: swap non-Western links, drop duplicates, keep order.
    for role, chain in preset.get("cascading_routing", {}).items():
        out: list[str] = []
        for model in chain:
            pick = model if _western(model) else next(
                a for a in _ranked(model, role, {}) if a not in out
            )
            if pick not in out:
                out.append(pick)
        preset["cascading_routing"][role] = out

    return preset


def _literal(value: object, level: int = 0) -> str:
    """Python literal with flat 4-space nesting, so lines stay under 100 chars."""
    pad, end = "    " * (level + 1), "    " * level
    if isinstance(value, dict) and value:
        items = "".join(f"{pad}{k!r}: {_literal(v, level + 1)},\n" for k, v in value.items())
        return "{\n" + items + end + "}"
    if isinstance(value, list) and len(repr(value)) > 60:
        return "[\n" + "".join(f"{pad}{_literal(v, level + 1)},\n" for v in value) + end + "]"
    return repr(value)


def render() -> str:
    western = {western_variant(pid): _build(pid, p) for pid, p in sorted(_base_presets().items())}
    body = _literal(western)
    return (
        '"""Western-only presets (US/EU models only). GENERATED, do not edit.\n\n'
        "Regenerate with ``python scripts/gen_western_presets.py``; hand fixes go in\n"
        "that script's OVERRIDES. tests/unit/test_preset_western.py checks drift.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        f"WESTERN_PRESETS: dict[str, dict] = {body}\n"
    )


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} is stale: run scripts/gen_western_presets.py")
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
