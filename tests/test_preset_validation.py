"""Test that harness_guard lab map covers all preset-referenced models."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def test_all_preset_models_have_lab_entries():
    """Every model alias used in any preset must have a lab entry."""
    from reasoner.application.services.harness_guard import _MODEL_LABS
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

    missing = used_models - set(_MODEL_LABS.keys())
    assert not missing, (
        f"{len(missing)} model(s) used in presets but missing from harness_guard "
        f"_MODEL_LABS: {sorted(missing)}. Add lab entries to "
        f"src/reasoner/application/services/harness_guard.py"
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
