"""Each model may serve at most one phase of any given preset.

A preset that routes two phases to the same model pays twice for one
perspective: the second call inherits the first's blind spots, its training
cut-off and its refusal boundaries. That is the echo chamber the cross-bloc
invariants in test_preset_bloc_diversity.py exist to prevent -- but those
only constrain the generator and synthesis/scoring roles, so a preset could
(and 37 of 50 did) satisfy every bloc rule while running one model across
half its phases.

Distinctness is judged on the RESOLVED model string, never the alias. The
registry deliberately contains cross-vendor aliases -- `gemini-pro` and
`claude-sonnet` both resolve to `anthropic/claude-sonnet-5` -- so two slots
can look different and be the same served model. An alias-level check would
report those presets clean.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from reasoner.domain.preset_registry import _REGISTRY as PRESETS  # noqa: E402
from reasoner.infrastructure.llm.registry import resolved_model_of  # noqa: E402

_ALL = sorted(PRESETS)


def _slots(preset_id: str) -> list[tuple[str, str]]:
    """(role, alias) for every model slot a preset declares.

    primary_id is included: it is the model every unrouted role falls back to,
    so a routed role naming the same model really is that model serving twice.
    """
    cfg = PRESETS[preset_id]
    slots = [(r, m) for r, m in (cfg.get("routing") or {}).items() if m]
    primary = cfg.get("primary_id")
    if primary:
        slots.append(("primary_id", primary))
    return slots


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _ALL)
def test_no_model_serves_two_phases(preset_id):
    by_served: dict[str, list[str]] = {}
    for role, alias in _slots(preset_id):
        by_served.setdefault(resolved_model_of(alias), []).append(role)

    repeated = {s: sorted(r) for s, r in by_served.items() if len(r) > 1}
    assert not repeated, (
        f"{preset_id}: these models each serve more than one phase "
        f"{repeated}; every phase of a preset must use a distinct model"
    )


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _ALL)
def test_every_slot_resolves_to_a_real_model(preset_id):
    """A slot whose alias does not resolve would make uniqueness vacuous.

    resolved_model_of() falls back to returning its input unchanged for an
    unknown alias, so an unregistered model yields a bare alias string that
    happens to be distinct from everything else -- passing the test above for
    the wrong reason.
    """
    from reasoner.infrastructure.llm.registry import _MODEL_WHITELIST

    unknown = [
        (role, alias)
        for role, alias in _slots(preset_id)
        if alias not in _MODEL_WHITELIST
    ]
    assert not unknown, f"{preset_id}: slots naming unregistered models: {unknown}"


@pytest.mark.unit
def test_uniqueness_is_checked_on_resolved_models_not_aliases():
    """Guard the guard: two aliases for one served model must not read as two.

    If this ever fails, the registry no longer has a cross-vendor alias pair
    and test_no_model_serves_two_phases could silently weaken to an
    alias-level check without anyone noticing.
    """
    assert resolved_model_of("gemini-pro") == resolved_model_of("claude-sonnet")
    assert resolved_model_of("gemini-pro") != "gemini-pro"


@pytest.mark.unit
def test_retired_grok_420_is_not_routable():
    """grok-4.20 was removed 2026-08-20; the catalogue snapshot still lists it.

    The snapshot mirrors upstream, where the model is still live, so a future
    catalogue refresh must not quietly reinstate the alias.
    """
    from reasoner.infrastructure.llm.registry import _MODEL_WHITELIST

    routable = [m for m in _MODEL_WHITELIST if "grok-4.20" in m]
    assert not routable, f"grok-4.20 aliases came back: {routable}"

    pinned = [
        (pid, role, alias)
        for pid in PRESETS
        for role, alias in _slots(pid)
        if "grok-4.20" in alias
    ]
    assert not pinned, f"presets still pin grok-4.20: {pinned}"
