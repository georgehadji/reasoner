"""Test that harness_guard's registry-backed lab lookup covers all preset-referenced models."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_all_preset_models_have_lab_entries():
    """Every model alias used in any preset must resolve to a lab via the registry port.

    get_model_lab (application/services/harness_guard.py) used to check a
    hand-maintained dict that mirrored the registry and drifted from it; it
    now delegates to ModelRegistryPort.vendor_of and raises ValueError for
    anything the registry doesn't know (W6). This test now exercises that
    path directly instead of checking dict membership.
    """
    from reasoner.application.services.harness_guard import get_model_lab
    from reasoner.domain.preset_registry import _REGISTRY as PRESETS

    used_models: set[str] = set()
    for _name, cfg in PRESETS.items():
        if cfg.get("primary_id"):
            used_models.add(cfg["primary_id"])
        for m in cfg.get("routing", {}).values():
            used_models.add(m)
        for m in cfg.get("fallback_routing", {}).values():
            used_models.add(m)
        for chain in cfg.get("cascading_routing", {}).values():
            for m in chain:
                used_models.add(m)

    missing: list[str] = []
    for model in sorted(used_models):
        try:
            get_model_lab(model)
        except ValueError:
            missing.append(model)

    assert not missing, (
        f"{len(missing)} model(s) used in presets but not registered in "
        f"infrastructure/llm/registry.py, so harness_guard.get_model_lab() "
        f"rejects them: {missing}"
    )


def test_all_preset_role_names_are_known():
    """Every routing role must be in _KNOWN_ROUTING_ROLES."""
    from reasoner.domain.preset_core import _KNOWN_ROUTING_ROLES
    from reasoner.domain.preset_registry import _REGISTRY as PRESETS

    unknown: set[str] = set()
    for name, cfg in PRESETS.items():
        for role in cfg.get("routing", {}):
            if role not in _KNOWN_ROUTING_ROLES:
                unknown.add(f"{name}: routing['{role}']")
        for role in cfg.get("fallback_routing", {}):
            if role not in _KNOWN_ROUTING_ROLES:
                unknown.add(f"{name}: fallback_routing['{role}']")

    assert not unknown, (
        f"{len(unknown)} unknown role(s) found. Add to _KNOWN_ROUTING_ROLES "
        f"in src/reasoner/domain/preset_core.py: {sorted(unknown)}"
    )


def test_all_preset_model_aliases_valid():
    """Every model alias must be registered in the model registry."""
    from reasoner.domain.preset_registry import _REGISTRY as PRESETS
    from reasoner.infrastructure.llm.registry import _REGISTRY as MODELS

    invalid: list[str] = []
    for name, cfg in PRESETS.items():
        pid = cfg.get("primary_id", "")
        if pid and pid not in MODELS:
            invalid.append(f"{name}: primary_id='{pid}'")
        for role, model in cfg.get("routing", {}).items():
            if model not in MODELS:
                invalid.append(f"{name}: routing['{role}']='{model}'")
        for role, model in cfg.get("fallback_routing", {}).items():
            if model not in MODELS:
                invalid.append(f"{name}: fallback_routing['{role}']='{model}'")
        for role, chain in cfg.get("cascading_routing", {}).items():
            for model in chain:
                if model not in MODELS:
                    invalid.append(f"{name}: cascading_routing['{role}']='{model}'")

    assert not invalid, (
        f"{len(invalid)} invalid model alias(es) in presets:\n  "
        + "\n  ".join(invalid)
    )
