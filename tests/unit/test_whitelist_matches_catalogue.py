"""D9: a price in a freeform comment cannot be tested. A structured field can.

docs/plans/root-cause-remediation-2026-09-07.md P4 step 1 added price_in /
price_out / context fields to _MODEL_WHITELIST entries, derived from
domain/openrouter_models.json by scripts/update_openrouter_catalogue.py
--sync-whitelist. These tests pin that the structured fields actually agree
with the catalogue they were synced from, so drift is a test failure instead
of a stale comment nobody notices.

A "base"-routed entry (Ollama, and the direct-NIM `nvidia-nemotron-super`
pin) must carry none of these fields: that route does not bill at the
OpenRouter catalogue price, so a synced field there would misrepresent what
actually bills.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from reasoner.infrastructure.llm.registry import _MODEL_WHITELIST  # noqa: E402

_CATALOGUE = Path(__file__).resolve().parents[2] / "src" / "reasoner" / "domain" / "openrouter_models.json"


def _catalogue() -> dict:
    if not _CATALOGUE.exists():
        pytest.skip("catalogue snapshot missing")
    return json.loads(_CATALOGUE.read_text(encoding="utf-8"))


def _by_id(catalogue: dict) -> dict:
    return {m["id"]: m for m in catalogue.get("data", []) if isinstance(m, dict)}


@pytest.mark.unit
def test_base_routed_entries_carry_no_synced_price_fields():
    """Ollama and the NVIDIA-direct pin route off-gateway; no catalogue price applies."""
    offenders = [
        alias for alias, cfg in _MODEL_WHITELIST.items()
        if "base" in cfg and ("price_in" in cfg or "price_out" in cfg or "context" in cfg)
    ]
    assert not offenders, (
        f"these route via a direct base URL, not OpenRouter billing, and must not "
        f"carry synced catalogue fields: {offenders}"
    )


@pytest.mark.unit
def test_synced_price_fields_match_the_catalogue():
    """Every price_in/price_out on a whitelist entry equals catalogue pricing * 1e6."""
    by_id = _by_id(_catalogue())
    mismatches = []
    for alias, cfg in _MODEL_WHITELIST.items():
        if "price_in" not in cfg and "price_out" not in cfg:
            continue
        model_id = cfg["model"].lstrip("~")
        entry = by_id.get(model_id)
        if entry is None:
            mismatches.append((alias, model_id, "absent from catalogue"))
            continue
        pricing = entry.get("pricing") or {}
        expected_in = round(float(pricing["prompt"]) * 1_000_000, 6)
        expected_out = round(float(pricing["completion"]) * 1_000_000, 6)
        if cfg.get("price_in") != expected_in or cfg.get("price_out") != expected_out:
            mismatches.append((
                alias, model_id,
                f"whitelist=({cfg.get('price_in')}, {cfg.get('price_out')}) "
                f"catalogue=({expected_in}, {expected_out})",
            ))
    assert not mismatches, (
        "whitelist price fields drifted from the catalogue; rerun "
        "`python scripts/update_openrouter_catalogue.py --sync-whitelist`:\n"
        + "\n".join(f"  {a} ({m}): {r}" for a, m, r in mismatches)
    )


@pytest.mark.unit
def test_synced_context_matches_the_catalogue():
    by_id = _by_id(_catalogue())
    mismatches = []
    for alias, cfg in _MODEL_WHITELIST.items():
        if "context" not in cfg:
            continue
        model_id = cfg["model"].lstrip("~")
        entry = by_id.get(model_id)
        if entry is None:
            mismatches.append((alias, model_id, "absent from catalogue"))
            continue
        expected = entry.get("context_length")
        if cfg["context"] != expected:
            mismatches.append((alias, model_id, f"whitelist={cfg['context']} catalogue={expected}"))
    assert not mismatches, (
        "whitelist context fields drifted from the catalogue; rerun "
        "`python scripts/update_openrouter_catalogue.py --sync-whitelist`:\n"
        + "\n".join(f"  {a} ({m}): {r}" for a, m, r in mismatches)
    )


@pytest.mark.unit
def test_every_routed_non_base_entry_has_synced_price_fields():
    """A routed model absent from sync coverage would mean D9's bug is only half-fixed.

    Exempts OpenRouter's -1 "variable pricing" sentinel (e.g. openrouter/pareto-code):
    the real price depends on whichever underlying model a router alias picks per
    call, so there is no fixed per-token rate to sync -- see sync_whitelist()'s own
    comment in scripts/update_openrouter_catalogue.py.
    """
    by_id = _by_id(_catalogue())
    missing = []
    for alias, cfg in _MODEL_WHITELIST.items():
        if "base" in cfg or "/" not in cfg.get("model", "").lstrip("~") or "price_in" in cfg:
            continue
        entry = by_id.get(cfg["model"].lstrip("~"))
        pricing = (entry or {}).get("pricing") or {}
        if float(pricing.get("prompt", 0)) < 0 or float(pricing.get("completion", 0)) < 0:
            continue  # variable pricing -- correctly unsynced
        missing.append(alias)
    assert not missing, (
        f"these OpenRouter-routed aliases have no synced price_in/price_out: {missing}. "
        f"Run `python scripts/update_openrouter_catalogue.py --sync-whitelist`."
    )
