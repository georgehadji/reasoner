"""A phase's tuned temperature must actually reach the model routed to it.

Some models reject a custom ``temperature`` and run at a fixed 1.0: the OpenAI
gpt-* and o-series tiers, plus claude-opus / claude-sonnet / claude-fable-5.
Routing one of those into a tuned phase does NOT raise -- the provider simply
omits the parameter (``OpenAICompatibleProvider._supports_temperature``) and the
model samples at its default. A synthesis role tuned to 0.5, or a fusion role
tuned to 0.2, then runs two to five times more random than intended, and nothing
in the response says so.

That was the state of 45 slots before 2026-08-21: 43 ``synthesis`` (41 on
gpt-5.6-luna, the registry's designated default synthesis voice) and 2
``deep_read``. All were rerouted to temperature-honouring models.

Distinct from the two existing temperature suites: ``test_temperature.py``
checks the provider's per-model-name support flag in isolation, and
``test_core_temperatures.py`` checks the PHASE_TEMPERATURES table. Neither
cross-references presets against model capability, which is how 45 slots drifted.

Roles targeting >= 0.7 (perspectives, generators) are exempt -- a fixed 1.0 is
close enough to their intent that it changes nothing meaningful.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from reasoner.core.temperatures import PHASE_TEMPERATURES  # noqa: E402
from reasoner.domain.preset_registry import _REGISTRY as PRESETS  # noqa: E402
from reasoner.infrastructure.llm.registry import (  # noqa: E402
    honours_tuned_temperature,
    resolved_model_of,
)

TOLERANCE_FLOOR = 0.7

_GENERATOR_ROLES = {
    "constructive", "destructive", "systemic", "minimalist", "perspective",
    "expert_1", "expert_2", "expert_3", "expert_4",
}

_ALL = sorted(PRESETS)


def target_temperature(role: str) -> float | None:
    if role in PHASE_TEMPERATURES:
        return PHASE_TEMPERATURES[role]
    if role in _GENERATOR_ROLES or role.startswith("perspective_"):
        return PHASE_TEMPERATURES["perspective"]
    return None


def _slots(preset_id: str) -> list[tuple[str, str]]:
    cfg = PRESETS[preset_id]
    slots = [(r, m) for r, m in (cfg.get("routing") or {}).items() if m]
    if cfg.get("primary_id"):
        slots.append(("primary_id", cfg["primary_id"]))
    return slots


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _ALL)
def test_low_temperature_phases_use_temperature_honouring_models(preset_id):
    offenders = [
        (role, alias, resolved_model_of(alias), target_temperature(role))
        for role, alias in _slots(preset_id)
        if (t := target_temperature(role)) is not None
        and t < TOLERANCE_FLOOR
        and not honours_tuned_temperature(alias)
    ]
    assert not offenders, (
        f"{preset_id}: these roles declare a temperature below "
        f"{TOLERANCE_FLOOR} but route to a model that ignores it and runs at "
        f"1.0: {offenders}"
    )


@pytest.mark.unit
@pytest.mark.parametrize("preset_id", _ALL)
def test_fallbacks_also_honour_the_phase_temperature(preset_id):
    """A fallback inherits the role's temperature, so the rule applies to it too.

    Failing over from a tuned model to a fixed-temperature one would silently
    change sampling behaviour at exactly the moment something is already wrong.
    """
    fallbacks = (PRESETS[preset_id].get("fallback_routing") or {}).items()
    offenders = [
        (role, alias, target_temperature(role))
        for role, alias in fallbacks
        if alias
        and (t := target_temperature(role)) is not None
        and t < TOLERANCE_FLOOR
        and not honours_tuned_temperature(alias)
    ]
    assert not offenders, (
        f"{preset_id}: fallback models ignore their role's temperature: {offenders}"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "alias, expected",
    [
        # Provider denylist: refuses to send temperature at all.
        ("gpt-5.6-luna", False),
        ("gpt-5", False),
        ("o3", False),
        ("claude-opus", False),
        ("claude-fable-5", False),
        # Catalogue says no temperature, even though the denylist misses it.
        ("claude-sonnet", False),
        # Genuinely tunable.
        ("deepseek-v4-flash", True),
        ("llama-4-maverick", True),
        ("gemini-3.7-flash", True),
        # OpenAI open-weight DOES accept temperature -- the "gpt-" denylist
        # prefix must not swallow it.
        ("gpt-oss-120b", True),
    ],
)
def test_honours_tuned_temperature_classifies_known_models(alias, expected):
    assert honours_tuned_temperature(alias) is expected


@pytest.mark.unit
def test_helper_fails_closed_when_denylist_and_catalogue_disagree():
    """claude-sonnet is the live example of the two sources drifting apart.

    The provider denylist (hand-maintained, Jun 2026) does not match it, so the
    provider still SENDS temperature; the refreshed catalogue reports no
    temperature support. The helper must take the pessimistic reading, or the
    validator would bless a routing the model cannot honour.
    """
    from reasoner.domain.pricing import MODEL_CATALOGUE
    from reasoner.infrastructure.llm.providers.openai_compat import (
        OpenAICompatibleProvider,
    )

    served = resolved_model_of("claude-sonnet")
    entry = MODEL_CATALOGUE.get(served) or {}
    catalogue_allows = "temperature" in set(entry.get("supported_parameters") or ())
    denylisted = any(
        m in served.lower()
        for m in OpenAICompatibleProvider._FIXED_TEMPERATURE_MARKERS
    )

    assert not catalogue_allows, "catalogue now reports temperature for claude-sonnet"
    assert not denylisted, "denylist now covers claude-sonnet; update this test"
    assert honours_tuned_temperature("claude-sonnet") is False
